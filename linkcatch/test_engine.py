import os, sys, unittest, time
from unittest.mock import patch, AsyncMock, MagicMock
from tempfile import TemporaryDirectory
from pathlib import Path
os.environ['ENGINE_API_KEY']='test-only-'+'x'*40
sys.path.insert(0,os.path.dirname(__file__))
from fastapi.testclient import TestClient
import app
from engine import normalize, check_address, tiktok_resolver_info, analyze_video

class EngineTests(unittest.TestCase):
    def test_download_request_is_idempotent_and_delivery_is_tracked(self):
        app.JOBS.clear()
        with TemporaryDirectory() as directory, patch.object(app,'DATA',Path(directory)), patch('app.run_engine',new_callable=AsyncMock) as run:
            with TestClient(app.app) as client:
                headers={'X-Engine-Key':app.API_KEY}
                source=app.new_job('analysis')
                source.update(state='done',url='https://x.com/a/status/123',result={'title':'Video'},selectors={'v0':{'format':'best'}})
                body={'analysis_id':source['id'],'option_id':'v0','request_id':'r'*32}
                first=client.post('/download',json=body,headers=headers)
                second=client.post('/download',json=body,headers=headers)
                self.assertEqual(first.status_code,202)
                self.assertEqual(first.json()['id'],second.json()['id'])
                self.assertEqual(run.call_count,1)
                job=app.JOBS[first.json()['id']]
                job.update(state='done',file='video.mp4')
                path=app.DATA/job['id']/'video.mp4';path.write_bytes(b'video-test-content')
                response=client.get('/files/'+job['id'],headers=headers)
                self.assertEqual(response.content,b'video-test-content')
                self.assertEqual(client.get('/jobs/'+job['id'],headers=headers).json()['delivery_state'],'sent')
                self.assertEqual(client.get('/files/'+job['id'],headers={**headers,'Range':'bytes=0-3'}).content,b'vide')
                other=app.new_job('analysis')
                other.update(state='done',url=source['url'],result=source['result'],selectors=source['selectors'])
                mismatch=client.post('/download',json={**body,'analysis_id':other['id']},headers=headers)
                self.assertEqual(mismatch.status_code,409)
                self.assertEqual(client.post('/download',json={**body,'request_id':'../invalid'},headers=headers).status_code,422)
        app.JOBS.clear()

    def test_analysis_retry_and_shared_link_do_not_duplicate_extraction(self):
        app.JOBS.clear();app.ALIASES.clear()
        with patch('app.run_engine',new_callable=AsyncMock) as run,TestClient(app.app) as client:
            h={'X-Engine-Key':app.API_KEY};url='https://www.tiktok.com/@one/video/123?utm_source=share'
            first=client.post('/analyze',json={'url':url,'request_id':'a'*32},headers=h)
            retry=client.post('/analyze',json={'url':url,'request_id':'a'*32},headers=h)
            friend=client.post('/analyze',json={'url':'https://www.tiktok.com/@two/video/123','request_id':'b'*32},headers=h)
            self.assertEqual(first.json()['id'],retry.json()['id'])
            self.assertEqual(first.json()['id'],friend.json()['id'])
            self.assertEqual(run.call_count,1)
            self.assertEqual(client.get('/jobs/'+'b'*32,headers=h).json()['id'],first.json()['id'])
            bad=client.post('/analyze',json={'url':'https://www.tiktok.com/@one/video/999','request_id':'b'*32},headers=h)
            self.assertEqual(bad.status_code,409)
        app.JOBS.clear();app.ALIASES.clear()

    def test_ready_download_is_reused_with_independent_file_and_range_headers(self):
        app.JOBS.clear();app.ALIASES.clear()
        with TemporaryDirectory() as directory,patch.object(app,'DATA',Path(directory)),patch('app.run_engine',new_callable=AsyncMock) as run,TestClient(app.app) as client:
            h={'X-Engine-Key':app.API_KEY};source=app.new_job('analysis')
            source.update(state='done',url='https://x.com/a/status/123',result={'title':'فيديو جديد'},selectors={'v0':{'format':'best'}})
            body={'analysis_id':source['id'],'option_id':'v0','request_id':'c'*32}
            first=client.post('/download',json=body,headers=h);self.assertEqual(first.status_code,202)
            original=app.JOBS[first.json()['id']];original.update(state='done',file='video.mp4')
            path=app.DATA/original['id']/'video.mp4';path.write_bytes(b'0123456789video')
            second=client.post('/download',json={**body,'request_id':'d'*32},headers=h);self.assertEqual(second.status_code,202)
            for _ in range(100):
                state=client.get('/jobs/'+'d'*32,headers=h).json()
                if state['state'] in ('done','error'):break
                time.sleep(.01)
            self.assertEqual(state['state'],'done')
            self.assertEqual(run.call_count,1)
            # Expiring the original must not remove the reused file.
            path.unlink()
            response=client.get('/files/'+'d'*32,headers={**h,'Range':'bytes=2-5'})
            self.assertEqual(response.status_code,206);self.assertEqual(response.content,b'2345')
            self.assertEqual(response.headers['content-type'],'video/mp4')
            self.assertIn('filename="DoobaSave.mp4"',response.headers['content-disposition'])
            self.assertIn("filename*=UTF-8''",response.headers['content-disposition'])
        app.JOBS.clear();app.ALIASES.clear()

    def test_twitter_falls_back_when_primary_api_omits_media(self):
        first=MagicMock();first.__enter__.return_value=first
        first.extract_info.side_effect=ValueError('No video could be found in this tweet')
        second=MagicMock();second.__enter__.return_value=second
        info={'id':'123','title':'Video','formats':[{'format_id':'mp4-720','height':720,'ext':'mp4','protocol':'https','url':'https://video.twimg.com/video.mp4','vcodec':'avc1','acodec':'aac'}]}
        second.extract_info.return_value=info;second.sanitize_info.return_value=info
        with patch('engine.yt_dlp.YoutubeDL',side_effect=[first,second]) as constructor:
            public,selectors,media=analyze_video('https://x.com/a/status/123',{})
            self.assertEqual(constructor.call_args_list[1].args[0]['extractor_args'],{'twitter':{'api':['syndication']}})
            self.assertEqual(selectors['v0']['_profile'],'twitter_syndication')
            self.assertTrue(public['options'][0]['audio'])

    def test_hls_audio_without_codec_is_merged(self):
        info={'title':'Twitter regression','formats':[
            {'format_id':'hls-audio','vcodec':'none','acodec':None,'ext':'mp4','protocol':'m3u8_native','url':'https://public.test/audio.m3u8'},
            {'format_id':'hls-video','height':720,'vcodec':'avc1','acodec':'none','ext':'mp4','protocol':'m3u8_native','url':'https://public.test/video.m3u8'}]}
        data,selectors=normalize(info)
        self.assertTrue(data['options'][0]['audio'])
        self.assertEqual(data['options'][0]['ext'],'mp4')
        self.assertEqual(selectors['v0']['format'],'hls-video+hls-audio')
        self.assertEqual(selectors['audio']['format'],'hls-audio')

    def test_resolver_binds_video_and_preserves_limits(self):
        url='https://www.tiktok.com/@_/video/123'
        response={'code':0,'data':{'id':'123','title':'Public video','wmplay':'https://v19.tiktokcdn-us.com/video.mp4','wm_size':500,'duration':38,'cover':'https://p16.tiktokcdn.com/cover.jpg'}}
        info=tiktok_resolver_info(url,response)
        self.assertEqual(info['formats'][0]['filesize'],500)
        self.assertEqual(normalize(info)[0]['thumbnail'],'https://p16.tiktokcdn.com/cover.jpg')
        self.assertEqual(normalize(info)[0]['options'][0]['label'],'الجودة الأصلية')
        response['data']['id']='456'
        with self.assertRaises(ValueError):tiktok_resolver_info(url,response)
        response['data'].update(id='123',duration=1201)
        with self.assertRaises(ValueError):tiktok_resolver_info(url,response)
        response['data'].update(duration=38,wmplay='file:///etc/passwd')
        with self.assertRaises(ValueError):tiktok_resolver_info(url,response)
        response['data']['wmplay']='https://attacker.example/video.mp4'
        with self.assertRaises(ValueError):tiktok_resolver_info(url,response)
    def test_private_and_unrelated_urls_rejected(self):
        for url in ['http://youtube.com/a','https://127.0.0.1/a','https://youtube.com.attacker.test/a','https://youtube.com@127.0.0.1/a','https://youtube.com:8443/a','file:///etc/passwd']:
            with self.subTest(url=url),self.assertRaises(Exception):app.valid_url(url)
        self.assertEqual(app.valid_url('https://www.youtube.com/watch?v=test'),'https://www.youtube.com/watch?v=test')
        for address in [('127.0.0.1',80),('10.0.0.1',443),('169.254.169.254',80),('::1',80)]:
            with self.assertRaises(OSError):check_address(address)

    def test_tiktok_api_watermark_url_falls_back_to_valid_cdn_copy(self):
        # Actual failing post from the user's screenshot, 2026-10-18.
        url='https://www.tiktok.com/@norhan.ehab20/video/7658543058962763026'
        data={'id':'7658543058962763026','duration':5,
              'wmplay':'https://api16-normal-useast5.tiktokv.us/aweme/v1/play/?video_id=example',
              'wm_size':900,'play':'https://v19.tiktokcdn-us.com/video.mp4','size':700}
        info=tiktok_resolver_info(url,{'code':0,'data':data})
        self.assertEqual(info['formats'][0]['url'],data['play'])
        self.assertEqual(info['formats'][0]['filesize'],700)
        for bad in ('https://127.0.0.1/video','https://tiktokcdn-us.com.attacker.test/video',
                    'https://v19.tiktokcdn-us.com:bad/video','file:///etc/passwd'):
            with self.subTest(bad=bad):
                data['wmplay']=bad
                self.assertEqual(tiktok_resolver_info(url,{'code':0,'data':data})['formats'][0]['url'],data['play'])
        data['play']='https://attacker.test/video'
        with self.assertRaisesRegex(ValueError,'RESOLVER_FAILED: NO_ACCEPTED_MEDIA_URL'):
            tiktok_resolver_info(url,{'code':0,'data':data})

    def test_separate_video_and_audio_are_merged_and_sizes_summed(self):
        info={'title':'Test','formats':[
          {'format_id':'137','height':1080,'vcodec':'avc1','acodec':'none','ext':'mp4','protocol':'https','url':'https://public.test/video','filesize':1000},
          {'format_id':'140','vcodec':'none','acodec':'aac','ext':'m4a','protocol':'https','url':'https://public.test/audio','filesize':100},
          {'format_id':'18','height':360,'vcodec':'avc1','acodec':'aac','ext':'mp4','protocol':'https','url':'https://public.test/combined','filesize':500}]}
        data,selectors=normalize(info)
        self.assertEqual(data['options'][0]['label'],'1080p')
        self.assertEqual(data['options'][0]['size'],1100)
        self.assertTrue(data['options'][0]['audio'])
        self.assertEqual(selectors['v0']['format'],'137+140')
        self.assertEqual(selectors['v1']['format'],'18')
        self.assertIn('mp3',selectors)

    def test_unknown_codecs_keep_direct_video(self):
        data, selectors = normalize({'title':'Snap', 'formats':[{'format_id':'0','height':960,'ext':'mp4','protocol':'https','url':'https://public.test/video'}]})
        self.assertEqual(data['options'][0]['label'],'960p')
        self.assertTrue(data['options'][0]['audio'])
        self.assertEqual(selectors['v0']['format'],'0')
        self.assertIn('mp3',selectors)

    def test_drm_live_and_playlists_rejected(self):
        for info in [{'_type':'playlist'},{'is_live':True},{'has_drm':True},{'duration':1201}]:
            with self.assertRaises(ValueError):normalize(info)

    def test_api_auth_and_option_binding(self):
        with TestClient(app.app) as client:
            self.assertEqual(client.get('/health').status_code,200)
            self.assertEqual(client.post('/analyze',json={'url':'https://youtube.com/x'}).status_code,401)
            headers={'X-Engine-Key':app.API_KEY}
            self.assertEqual(client.post('/analyze',json={'url':'https://127.0.0.1/a'},headers=headers).status_code,400)
            job=app.new_job('analysis')
            job.update(state='done',url='https://youtube.com/watch?v=test',result={'title':'T'},selectors={'v0':{'format':'18'}})
            self.assertEqual(client.post('/download',json={'analysis_id':job['id'],'option_id':'../../x'},headers=headers).status_code,400)
            self.assertEqual(client.get('/jobs/not-an-existing-id',headers=headers).status_code,404)
            self.assertEqual(client.get('/files/'+job['id'],headers=headers).status_code,409)
            self.assertNotIn('selectors',client.get('/jobs/'+job['id'],headers=headers).json())
            job['media']={'formats':[{'url':'https://private-signed-cdn.test/secret'}]}
            self.assertNotIn('media',client.get('/jobs/'+job['id'],headers=headers).json())
        app.JOBS.clear()

if __name__=='__main__':unittest.main()
