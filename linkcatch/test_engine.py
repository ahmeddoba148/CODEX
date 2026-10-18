import os, sys, unittest
from unittest.mock import patch
os.environ['ENGINE_API_KEY']='test-only-'+'x'*40
sys.path.insert(0,os.path.dirname(__file__))
from fastapi.testclient import TestClient
import app
from engine import normalize, check_address, tiktok_resolver_info

class EngineTests(unittest.TestCase):
    def test_resolver_binds_video_and_preserves_limits(self):
        url='https://www.tiktok.com/@_/video/123'
        response={'code':0,'data':{'id':'123','title':'Public video','wmplay':'https://cdn.example/video.mp4','wm_size':500,'duration':38}}
        info=tiktok_resolver_info(url,response)
        self.assertEqual(info['formats'][0]['filesize'],500)
        self.assertEqual(normalize(info)[0]['options'][0]['label'],'الجودة الأصلية')
        response['data']['id']='456'
        with self.assertRaises(ValueError):tiktok_resolver_info(url,response)
        response['data'].update(id='123',duration=1201)
        with self.assertRaises(ValueError):tiktok_resolver_info(url,response)
        response['data'].update(duration=38,wmplay='file:///etc/passwd')
        with self.assertRaises(ValueError):tiktok_resolver_info(url,response)
    def test_private_and_unrelated_urls_rejected(self):
        for url in ['http://youtube.com/a','https://127.0.0.1/a','https://youtube.com.attacker.test/a','https://youtube.com@127.0.0.1/a','https://youtube.com:8443/a','file:///etc/passwd']:
            with self.subTest(url=url),self.assertRaises(Exception):app.valid_url(url)
        self.assertEqual(app.valid_url('https://www.youtube.com/watch?v=test'),'https://www.youtube.com/watch?v=test')
        for address in [('127.0.0.1',80),('10.0.0.1',443),('169.254.169.254',80),('::1',80)]:
            with self.assertRaises(OSError):check_address(address)

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
