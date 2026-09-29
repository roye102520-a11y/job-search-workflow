"""Synthetic HTTP acceptance checks for BOSS local-import endpoints."""

import http.client
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('resume_server_boss_http', ROOT / 'scripts/resume_server.py')
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class BossHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-boss-http-')
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name)
        self.server = server_module.StudioServer(self.case, port=0)
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .01}, daemon=True)
        self.worker.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, method, path, payload=None, token=True, origin=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Local-Token'] = self.server.local_token
        if origin:
            headers['Origin'] = origin
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_screen_persists_reclassifies_and_never_updates_tracker(self):
        self.assertEqual(self.request('GET', '/api/boss', token=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/boss', origin='https://evil.example')[0], 403)
        status, before = self.request('GET', '/api/boss')
        self.assertEqual(status, 200)
        self.assertIsNone(before['screen'])
        row = {'url': 'https://www.zhipin.com/job_detail/Ab1234567890.html?lid=private',
               'company': '合成公司', 'title': 'AI 运营', 'city': '上海',
               'salary': '10-15K', 'tags': '双休',
               'description': '岗位职责：维护内容。任职要求：沟通能力。'}
        status, screened = self.request('POST', '/api/boss/screen', {'data': json.dumps([row], ensure_ascii=False)})
        self.assertEqual(status, 200, screened)
        self.assertEqual(screened['screen']['summary']['shortlist'], 1)
        self.assertFalse(screened['automated_actions'])
        self.assertNotIn('lid=', screened['screen']['results'][0]['job']['url'])
        settings = {**before['settings'], 'min_salary_k': 20}
        status, changed = self.request('POST', '/api/boss/settings', {'settings': settings})
        self.assertEqual(status, 200, changed)
        self.assertEqual(changed['screen']['summary']['excluded'], 1)
        self.assertEqual(self.request('GET', '/api/boss')[1]['screen']['summary']['excluded'], 1)
        self.assertFalse((self.case / 'application-tracker.csv').exists())
        self.assertFalse((self.case / 'application-events.jsonl').exists())

    def test_bad_payload_and_blocked_import(self):
        self.assertEqual(self.request('POST', '/api/boss/settings', {'settings': {'oops': 1}})[0], 400)
        self.assertEqual(self.request('POST', '/api/boss/blocked', {'data': '合成甲公司\n合成乙公司'})[1]['settings']['excluded_companies'], ['合成甲公司', '合成乙公司'])
        self.assertEqual(self.request('POST', '/api/boss/blocked', {'data': 123})[0], 400)
        self.assertEqual(self.request('POST', '/api/boss/screen', {'data': '[broken'})[0], 400)
        self.assertEqual(self.request('POST', '/api/boss/screen', {'data': '[]'}, token=False)[0], 403)


if __name__ == '__main__':
    unittest.main()
