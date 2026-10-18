import asyncio, json, os, re, secrets, shutil, sys, time, socket, ipaddress, unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT=Path(__file__).parent
DATA=Path(os.getenv('DATA_DIR','/tmp/linkcatch'))
DATA.mkdir(parents=True,exist_ok=True)
API_KEY=os.getenv('ENGINE_API_KEY','')
JOBS={}
SLOTS=asyncio.Semaphore(2)
TTL=1800
DOMAINS=('youtube.com','youtu.be','youtube-nocookie.com','instagram.com','facebook.com','fb.watch','fb.com','tiktok.com','twitter.com','x.com','vimeo.com','dailymotion.com','dai.ly','reddit.com','redd.it','pinterest.com','pin.it','twitch.tv','clips.twitch.tv','snapchat.com','threads.net','threads.com','bsky.app','tumblr.com','linkedin.com')
ERRORS={
 'AUTH_REQUIRED':'الفيديو يحتاج تسجيل دخول أو تحقق من المنصة. جرّب رابط فيديو عام آخر.',
 'PLATFORM_BLOCKED':'المنصة منعت طلب السيرفر مؤقتًا. جرّب لاحقًا أو جرّب منصة أخرى.',
 'UNAVAILABLE':'الفيديو غير متاح أو تم حذفه من المنصة. جرّب رابطًا آخر.',
 'UNSUPPORTED':'هذا الرابط غير مدعوم حاليًا. استخدم الرابط المباشر لمنشور يحتوي على فيديو.',
 'EXTRACTION_FAILED':'تعذّر استخراج الفيديو. تأكد أن المنشور عام وأن الرابط يفتح مباشرة.',
 'NO_FORMATS':'لم تظهر صيغ قابلة للتحميل لهذا الفيديو.',
 'TOO_LONG':'الحد الحالي للفيديو 20 دقيقة.', 'TOO_LARGE':'الحد الحالي لحجم التحميل 300 ميجابايت.',
 'DRM':'هذا الفيديو محمي ولا يتوفر للتحميل.', 'LIVE':'البث المباشر غير مدعوم.',
 'PLAYLIST':'ألصق رابط فيديو واحد بدل قائمة تشغيل أو ألبوم.',
 'TIMEOUT':'استغرقت المنصة وقتًا أطول من المتوقع. حاول مرة أخرى.'}

async def cleanup():
    while True:
        await asyncio.sleep(60)
        now=time.monotonic()
        for key,job in list(JOBS.items()):
            if now-job['created']>TTL and job['state'] not in ('queued','running'):
                JOBS.pop(key,None)
                shutil.rmtree(DATA/key,ignore_errors=True)

@asynccontextmanager
async def lifespan(app):
    if len(API_KEY)<32: raise RuntimeError('Set ENGINE_API_KEY to a random value of at least 32 characters')
    task=asyncio.create_task(cleanup())
    yield
    task.cancel()
    for job in JOBS.values():
        if job.get('task'): job['task'].cancel()

app=FastAPI(title='LinkCatch Engine',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
@app.middleware('http')
async def authenticate(request:Request,call_next):
    if request.url.path!='/health' and not secrets.compare_digest(request.headers.get('X-Engine-Key',''),API_KEY):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Unauthorized'},status_code=401)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

class Analyze(BaseModel): url:str=Field(min_length=10,max_length=2048)
class Download(BaseModel): analysis_id:str=Field(max_length=100); option_id:str=Field(max_length=50)

def valid_url(value):
    try:
        url=urlsplit(value.strip())
        host=(url.hostname or '').lower().rstrip('.')
        if url.scheme!='https' or url.username or url.password or url.port not in (None,443): raise ValueError()
        if not any(host==d or host.endswith('.'+d) for d in DOMAINS): raise ValueError()
        return url.geturl()
    except (ValueError,TypeError): raise HTTPException(400,'ألصق رابط HTTPS من إحدى منصات التواصل المدعومة.')

def get_job(key):
    job=JOBS.get(key)
    if not job: raise HTTPException(404,'انتهت صلاحية الطلب. حلّل الرابط مرة أخرى.')
    return job

def new_job(kind):
    if len(JOBS)>=64 or sum(j['state'] in ('queued','running') for j in JOBS.values())>=8:
        raise HTTPException(429,'هناك طلبات كثيرة الآن. انتظر قليلًا ثم أعد المحاولة.')
    key=secrets.token_urlsafe(24)
    job={'id':key,'kind':kind,'created':time.monotonic(),'state':'queued','progress':None}
    JOBS[key]=job
    return job

async def run_engine(job,payload,timeout):
    process=None
    async with SLOTS:
        job['state']='running'
        try:
            process=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'engine.py'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True,limit=2*1024*1024)
            process.stdin.write(json.dumps(payload).encode())
            await process.stdin.drain()
            process.stdin.close()
            async def consume():
                async for line in process.stdout:
                    data=json.loads(line)
                    if 'progress' in data: job.update(progress=data['progress'],stage=data.get('status'))
                    elif 'error' in data:
                        job['error']=ERRORS.get(data['error'],ERRORS['EXTRACTION_FAILED'])
                        job['error_code']=data['error']
                        print(json.dumps({'event':'engine_error','platform':urlsplit(payload['url']).hostname,'code':data['error'],'diagnostic':data.get('diagnostic','')},ensure_ascii=False),flush=True)
                    elif 'result' in data: job.update(result=data['result'],selectors=data['selectors'],media=data.get('media'))
                    elif 'file' in data: job['file']=data['file']
                await process.wait()
            await asyncio.wait_for(consume(),timeout)
            if process.returncode!=0 or job.get('error'): job['state']='error';job.setdefault('error',ERRORS['EXTRACTION_FAILED'])
            elif job['kind']=='analysis' and 'result' in job or job['kind']=='download' and 'file' in job: job['state']='done'
            else: job.update(state='error',error=ERRORS['EXTRACTION_FAILED'])
        except asyncio.TimeoutError: job.update(state='error',error=ERRORS['TIMEOUT'])
        except asyncio.CancelledError:
            job.update(state='error',error='تم إيقاف الطلب. حاول مرة أخرى.')
            raise
        except Exception: job.update(state='error',error=ERRORS['EXTRACTION_FAILED'])
        finally:
            if process and process.returncode is None:
                import signal
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                await process.wait()
            if job['state']=='error' and job['kind']=='download': shutil.rmtree(DATA/job['id'],ignore_errors=True)

@app.get('/health')
async def health(): return {'ok':True,'engine':'yt-dlp','version':5}

@app.post('/analyze',status_code=202)
async def analyze(body:Analyze):
    url=valid_url(body.url)
    job=new_job('analysis');job['url']=url
    job['task']=asyncio.create_task(run_engine(job,{'action':'analyze','url':url},120))
    return {'id':job['id'],'state':job['state']}

@app.get('/jobs/{key}')
async def status(key:str):
    job=get_job(key)
    result={k:job[k] for k in ('id','kind','state','progress','stage','error','error_code','result') if k in job}
    if job['state']=='done' and job['kind']=='download':result['download_path']='/files/'+key
    return result

@app.post('/download',status_code=202)
async def download(body:Download):
    source=get_job(body.analysis_id)
    if source['kind']!='analysis' or source['state']!='done':raise HTTPException(400,'حلّل الرابط أولًا.')
    selector=source['selectors'].get(body.option_id)
    if not selector:raise HTTPException(400,'خيار التحميل غير صالح.')
    job=new_job('download');job['title']=source['result']['title']
    total=sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file())
    if total>800*1024*1024:
        JOBS.pop(job['id'],None)
        raise HTTPException(429,'مساحة الملفات المؤقتة مشغولة. حاول مرة أخرى لاحقًا.')
    directory=DATA/job['id'];directory.mkdir()
    job['task']=asyncio.create_task(run_engine(job,{'action':'download','url':source['url'],'selector':selector,'media':source.get('media'),'directory':str(directory)},600))
    return {'id':job['id'],'state':job['state']}

@app.get('/files/{key}')
async def file(key:str):
    job=get_job(key)
    if job['state']!='done' or job['kind']!='download':raise HTTPException(409,'الملف غير جاهز.')
    path=DATA/key/job['file']
    if not path.is_file():raise HTTPException(404,'انتهت صلاحية الملف. أعد التحميل.')
    title=re.sub(r'[^\w\s\-\u0600-\u06ff]','',unicodedata.normalize('NFKC',job['title']))[:100].strip() or 'LinkCatch'
    return FileResponse(path,filename=title+path.suffix,media_type='application/octet-stream')
