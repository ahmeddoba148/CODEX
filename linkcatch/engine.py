"""Isolated yt-dlp process. Only JSON result/progress is written to stdout."""
import sys, json, socket, ipaddress, os, re
from pathlib import Path

# Enforce public network destinations for Python downloader connections.
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
def check_address(address):
    if isinstance(address, tuple):
        host = address[0].split('%')[0]
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            for record in socket.getaddrinfo(host, address[1], type=socket.SOCK_STREAM):
                if not ipaddress.ip_address(record[4][0]).is_global:
                    raise OSError('Non-public network destination blocked')
        else:
            if not ip.is_global:
                raise OSError('Non-public network destination blocked')
def safe_connect(self, address):
    check_address(address)
    return _original_connect(self, address)
def safe_connect_ex(self, address):
    check_address(address)
    return _original_connect_ex(self, address)
socket.socket.connect = safe_connect
socket.socket.connect_ex = safe_connect_ex

import yt_dlp
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, urlopen
from yt_dlp.networking.impersonate import ImpersonateTarget
WARNINGS=[]
class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): WARNINGS.append(str(msg))
    def error(self, msg): pass

def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)

def options():
    return dict(quiet=True, no_warnings=False, logger=QuietLogger(), noplaylist=True,
        skip_download=True, socket_timeout=15, retries=1, fragment_retries=1,
        extractor_retries=1, cachedir=False, playlistend=1, hls_prefer_native=True,
        js_runtimes={'deno': {}}, max_filesize=300*1024*1024,
        allowed_extractors=['default', '-generic'],
        format='bestvideo+bestaudio/best')

def normalize(info):
    if not info or info.get('_type') in ('playlist', 'multi_video'):
        raise ValueError('PLAYLIST')
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming'):
        raise ValueError('LIVE')
    if (info.get('duration') or 0) > 1200:
        raise ValueError('TOO_LONG')
    if info.get('has_drm'):
        raise ValueError('DRM')
    formats = [f for f in info.get('formats', []) if f.get('url') and not f.get('has_drm')
        and f.get('protocol') in ('https','http','m3u8_native','m3u8','http_dash_segments')
        and (f.get('ext') or '') not in ('mhtml','jpg','png')]
    if not formats and info.get('url') and info.get('ext'):
        formats = [dict(info, format_id=info.get('format_id') or 'best')]
    # Audio-only HLS renditions can omit acodec. vcodec='none' still identifies
    # them as audio; dropping them produces silent Twitter downloads.
    audio = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
    aud = max(audio, key=lambda f:(f.get('ext')=='m4a', f.get('abr') or f.get('tbr') or 0), default=None)
    grouped = {}
    for f in formats:
        if f.get('vcodec') == 'none' or f.get('ext') in ('m4a','mp3','aac','opus','ogg','wav'): continue
        h = int(f.get('height') or 0)
        key = h or 'original'
        score = (f.get('ext')=='mp4', str(f.get('vcodec')).startswith(('avc','h264')), f.get('tbr') or 0)
        if key not in grouped or score > grouped[key][0]: grouped[key] = (score, f)
    result, selectors = [], {}
    for key, (_, f) in sorted(grouped.items(), key=lambda item: item[0] if isinstance(item[0], int) else 0, reverse=True):
        has_audio = f.get('acodec') != 'none'
        merge = not has_audio and aud is not None
        ext = ('mp4' if f.get('ext')=='mp4' and aud.get('ext') in ('m4a','mp4') else 'mkv') if merge else (f.get('ext') or 'mp4')
        fid = str(f['format_id'])
        selector = fid+'+'+str(aud['format_id']) if merge else fid
        size = f.get('filesize') or f.get('filesize_approx')
        if merge:
            asize = aud.get('filesize') or aud.get('filesize_approx')
            size = size+asize if size and asize else None
        if size and size > 300*1024*1024: continue
        oid = 'v'+str(len(result))
        result.append(dict(id=oid, kind='video', label=f'{key}p' if isinstance(key,int) else 'الجودة الأصلية',
            ext=ext, size=size, fps=f.get('fps'), audio=has_audio or merge,
            approximate=not bool(f.get('filesize')) or merge))
        selectors[oid] = dict(format=selector, merge_output_format=ext)
    if aud:
        result.append(dict(id='audio',kind='audio',label='الصوت الأصلي',ext=aud.get('ext') or 'm4a',size=aud.get('filesize') or aud.get('filesize_approx'),approximate=not bool(aud.get('filesize'))))
        selectors['audio'] = dict(format=str(aud['format_id']))
    if aud or any(f.get('acodec') != 'none' for f in formats):
        result.append(dict(id='mp3',kind='audio',label='تحويل إلى MP3',ext='mp3',size=None,approximate=True))
        selectors['mp3'] = dict(format=str(aud['format_id']) if aud else 'bestaudio/best', postprocessors=[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'192'}])
    if not result: raise ValueError('NO_FORMATS')
    thumbs = info.get('thumbnails') or []
    thumb = info.get('thumbnail') or (thumbs[-1].get('url') if thumbs else None)
    if thumb and not thumb.startswith('https://'): thumb = None
    return dict(title=(info.get('title') or 'فيديو')[:300], uploader=(info.get('uploader') or info.get('channel') or '')[:150],
        duration=info.get('duration'),thumbnail=thumb,platform=info.get('extractor_key') or info.get('extractor') or '',options=result), selectors

def youtube_profile(name):
    if name=='pot':
        return {'extractor_args':{'youtube':{'player_client':['mweb']},'youtubepot-bgutilscript':{'server_home':[os.getenv('BGUTIL_HOME','/opt/bgutil/server')]}}}
    if name == 'android_api':
        return {'extractor_args': {'youtube': {'player_client': ['android_vr'], 'player_skip': ['webpage', 'configs'], 'innertube_host': ['youtubei.googleapis.com']}}}
    return {'impersonate': ImpersonateTarget.from_str('chrome')}

def tiktok_resolver_info(url, response):
    data=response.get('data') or {}
    requested=re.search(r'/video/(\d+)',url)
    video_id=str(data.get('id') or '')
    if response.get('code')!=0 or not video_id.isdigit() or requested and requested[1]!=video_id:
        raise ValueError('UNAVAILABLE')
    # Prefer the original watermarked copy. Never invent a resolution.
    key='wmplay' if data.get('wmplay') else 'play'
    media=data.get(key) or ''
    target=urlsplit(media)
    if target.scheme!='https' or not target.hostname or target.username or target.password or target.port not in (None,443):
        raise ValueError('UNAVAILABLE')
    if not re.search(r'(^|\.)(?:tiktokcdn(?:-[a-z0-9]+)?\.com|muscdn\.com)$',target.hostname):
        raise ValueError('UNAVAILABLE')
    info=dict(id=video_id,title=data.get('title') or 'فيديو',duration=data.get('duration'),
        uploader=(data.get('author') or {}).get('nickname') or '',extractor_key='TikTok',
        webpage_url=url,formats=[dict(format_id='resolver',url=media,ext='mp4',protocol='https',
            filesize=data.get('wm_size' if key=='wmplay' else 'size') or None)])
    cover=data.get('cover')
    if isinstance(cover,str) and cover.startswith('https://') and len(cover)<=4096:
        info['thumbnail']=cover
    normalize(info)  # Retain duration and size restrictions for the fallback too.
    return info

def resolve_tiktok(url):
    endpoint='https://www.tikwm.com/api/?'+urlencode({'url':url})
    with urlopen(Request(endpoint,headers={'User-Agent':'LinkCatch/1.0','Accept':'application/json'}),timeout=25) as response:
        raw=response.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('UNAVAILABLE')
    return tiktok_resolver_info(url,json.loads(raw))

def analyze_video(url, base):
    host=(urlsplit(url).hostname or '').lower()
    profiles=['pot', 'browser'] if host.endswith(('youtube.com','youtu.be')) else ['default']
    last=None
    for profile in profiles:
        opt=dict(base)
        if profile!='default':opt.update(youtube_profile(profile))
        try:
            with yt_dlp.YoutubeDL(opt) as ydl:
                info=ydl.extract_info(url,download=False)
            public, selectors=normalize(info)
            if profile!='default':
                for selector in selectors.values():selector['_profile']=profile
            return public, selectors, ydl.sanitize_info(info)
        except Exception as exc:
            last=exc
            if profile=='default':
                if host.endswith('tiktok.com') and any(s in str(exc).lower() for s in ('blocked','403','429','10204')):
                    try:
                        info=resolve_tiktok(url)
                        public,selectors=normalize(info)
                        for selector in selectors.values():selector['_provider']='tikwm'
                        return public,selectors,info
                    except Exception as resolver_error:
                        WARNINGS.append('Public resolver failed: '+str(resolver_error)[:200])
                raise
    raise last

def main():
    data = json.load(sys.stdin)
    opt = options()
    host=(urlsplit(data['url']).hostname or '').lower()
    if host.endswith(('facebook.com','fb.watch','fb.com')):
        opt['impersonate']=ImpersonateTarget.from_str('chrome-99')
    if data['action']=='analyze':
        if host.endswith('tiktok.com') and data.get('resolver'):
            media=tiktok_resolver_info(data['url'],data['resolver'])
            public,selectors=normalize(media)
            for selector in selectors.values():selector['_provider']='tikwm'
        else:
            public, selectors, media = analyze_video(data['url'], opt)
        emit(dict(result=public, selectors=selectors, media=media))
    else:
        output=Path(data['directory']).resolve()
        def progress(event):
            total=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
            if total>300*1024*1024: raise ValueError('TOO_LARGE')
            if event.get('status')=='downloading':
                size=event.get('total_bytes') or event.get('total_bytes_estimate')
                pct=round(100*event.get('downloaded_bytes',0)/size,1) if size else None
                emit(dict(progress=pct,status='downloading'))
            elif event.get('status')=='finished': emit(dict(progress=None,status='processing'))
        selector=dict(data['selector'])
        provider=selector.pop('_provider',None)
        profile=selector.pop('_profile',None)
        if profile:opt.update(youtube_profile(profile))
        opt.update(selector)
        opt.update(skip_download=False, outtmpl=str(output/'video.%(ext)s'), progress_hooks=[progress],
            continuedl=False, restrictfilenames=True, concurrent_fragment_downloads=1,
            match_filter=lambda info,**kw: 'TOO_LONG' if (info.get('duration') or 0)>1200 or info.get('is_live') else None)
        with yt_dlp.YoutubeDL(opt) as ydl:
            if data.get('media'):
                try:
                    ydl.process_ie_result(data['media'],download=True)
                except Exception:
                    if host.endswith(('youtube.com','youtu.be')):raise
                    for partial in output.iterdir():
                        if partial.is_file():partial.unlink()
                    if provider=='tikwm':ydl.process_ie_result(resolve_tiktok(data['url']),download=True)
                    else:ydl.extract_info(data['url'],download=True)
            else:
                ydl.extract_info(data['url'],download=True)
        files=[p for p in output.iterdir() if p.is_file() and p.suffix not in ('.part','.ytdl','.json')]
        if len(files)!=1: raise ValueError('DOWNLOAD_FAILED')
        if files[0].stat().st_size>300*1024*1024: raise ValueError('TOO_LARGE')
        emit(dict(file=files[0].name))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        message=str(exc)
        if WARNINGS: message+=' | '+ ' | '.join(WARNINGS[-4:])
        code=next((c for c in ('TOO_LONG','TOO_LARGE','DRM','LIVE','PLAYLIST','NO_FORMATS') if c in message),None)
        lower=message.lower()
        if not code:
            if any(x in lower for x in ('login','sign in','cookies','private','not a bot','confirm your age')): code='AUTH_REQUIRED'
            elif '404' in lower or 'not available' in lower or 'not found' in lower: code='UNAVAILABLE'
            elif 'unsupported' in lower: code='UNSUPPORTED'
            elif any(x in lower for x in ('403','429','blocked','forbidden','rate-limit')): code='PLATFORM_BLOCKED'
            elif any(x in lower for x in ('timed out','timeout')): code='TIMEOUT'
            else: code='EXTRACTION_FAILED'
        diagnostic=re.sub(r'https?://[^\s]+', '<url>', message)[:900]
        emit(dict(error=code, diagnostic=diagnostic))
        sys.exit(1)
