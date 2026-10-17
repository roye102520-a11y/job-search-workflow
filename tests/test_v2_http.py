"""Integration checks for preview selection and recovery with real HTTP calls."""
import http.client
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from resume_server import StudioServer


class V2HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='career-v2-http-')
        self.addCleanup(self.tmp.cleanup)
        self.case=Path(self.tmp.name)/'case';shutil.copytree(ROOT/'tests/fixtures/synthetic-case',self.case)
        self.server=StudioServer(self.case,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,payload=None,token=True):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1])
        headers={'Content-Type':'application/json'}
        if token: headers['X-Local-Token']=self.server.local_token
        conn.request('GET' if payload is None else 'POST',path,json.dumps(payload).encode() if payload is not None else None,headers)
        response=conn.getresponse();body=response.read();status=response.status;conn.close();return status,body

    def test_preview_is_authenticated_and_readonly(self):
        payload={'jd':'【合成】岗位职责：用户运营、客户服务、客户成功，整理用户分层和反馈，维护问题记录。','title':'用户运营'}
        self.assertEqual(self.request('/api/selection',payload,False)[0],403)
        status,body=self.request('/api/selection',payload);self.assertEqual(status,200,body)
        data=json.loads(body);self.assertEqual(data['routing']['family'],'user-operations');self.assertTrue(data['selection']['candidates'])
        self.assertFalse((self.case/'generated').exists())
        self.assertFalse((self.case/'application-tracker.csv').exists())

    def test_priority_and_budget_validation_recovers(self):
        payload={'jd':'【合成】岗位职责：用户运营、客户服务、客户成功，整理用户分层和反馈，维护问题记录。','title':'用户运营'}
        self.assertEqual(self.request('/api/selection',{**payload,'project_priorities':['other-candidate']})[0],400)
        self.assertEqual(self.request('/api/selection',{**payload,'selection_budget':True})[0],400)
        self.assertEqual(self.request('/api/selection',payload)[0],200)

    def test_public_demo_does_not_embed_private_data(self):
        status,body=self.request('/demo');self.assertEqual(status,200);self.assertNotIn('13800000000',body.decode());self.assertIn('合成数据演示',body.decode())
        self.assertEqual(self.request('/demo/preview.js')[0],200)
        self.assertEqual(self.request('/demo/../../resume-evidence.json')[0],404)

    def test_partial_blocks_generation_readiness(self):
        payload={'jd':'【合成】岗位职责：知识库维护、文档清洗、问答整理。必需：生产级 RAG 系统维护。','title':'知识库运营'}
        status,body=self.request('/api/generate',payload);self.assertEqual(status,200,body)
        data=json.loads(body);self.assertEqual(data['status'],'preparing')
        self.assertTrue(any(i['status']=='partial' for i in data['requirement_summary']['required_blockers']))
        self.assertFalse((self.case/'application-tracker.csv').exists())

    def test_original_fact_source_is_authenticated_and_allowlisted(self):
        self.assertEqual(self.request('/api/evidence/source?ref=career-evidence-bank.md',token=False)[0],403)
        status,body=self.request('/api/evidence/source?ref=career-evidence-bank.md%23beacon')
        self.assertEqual(status,200);self.assertGreater(len(json.loads(body)['text']),100)
        self.assertEqual(self.request('/api/evidence/source?ref=.env')[0],400)
