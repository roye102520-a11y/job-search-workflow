"""Real loopback HTTP tests with synthetic data and an injected fake generator."""
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location('resume_server', Path(__file__).parents[1] / 'scripts/resume_server.py')
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class StudioHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-studio-')
        self.case = Path(self.tmp.name)
        (self.case / 'profile.json').write_text('{"synthetic_private":true}')
        self.calls = []

        def generate(case, request, font=None):
            self.calls.append((case, request, font))
            folder = case / 'generated' / 'synthetic-result'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'resume.pdf').write_bytes(b'%PDF-synthetic-byte-fixture-not-a-real-PDF')
            (folder / 'match.md').write_text('# Synthetic match\nNo real candidate data')
            return {'output_dir': 'generated/synthetic-result', 'files': {
                'pdf': 'generated/synthetic-result/resume.pdf',
                'match': 'generated/synthetic-result/match.md'},
                'family': 'user-operations', 'label': '用户 / 客户运营', 'warnings': [], 'selected_bullet_ids': ['synthetic']}

        self.server = server_module.StudioServer(self.case, port=0, generate_func=generate)
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.worker.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def generate(self, request=None, headers=None):
        payload = request if request is not None else {'jd': '合成用户运营 JD', 'language': 'zh', 'family': 'auto'}
        actual_headers = {'Content-Type': 'application/json', 'X-Local-Token': self.server.local_token}
        actual_headers.update(headers or {})
        return self.request('POST', '/api/generate', json.dumps(payload).encode(), actual_headers)

    def test_binds_only_ipv4_loopback(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_bootstrap_has_random_token_and_families_no_cors(self):
        status, headers, body = self.request('GET', '/api/bootstrap')
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result['token'], self.server.local_token)
        self.assertGreaterEqual(len(result['token']), 40)
        self.assertEqual(set(result['families']), set(server_module.FAMILIES))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertNotIn('synthetic_private', body.decode())

    def test_html_has_nonce_csp_and_no_candidate_facts(self):
        status, headers, body = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn("script-src 'nonce-", headers['Content-Security-Policy'])
        self.assertNotIn('__CSP_NONCE__', body.decode())
        self.assertNotIn('synthetic_private', body.decode())
        self.assertIn('JD 正文', body.decode())

    def test_generate_returns_local_artifacts_and_passes_request(self):
        status, _, body = self.generate()
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertEqual(result['family'], 'user-operations')
        self.assertEqual(self.calls[0][0], self.case.resolve())
        self.assertEqual(self.calls[0][1]['jd'], '合成用户运营 JD')
        status, headers, body = self.request('GET', '/files/' + result['files']['pdf'])
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/pdf')
        self.assertTrue(body.startswith(b'%PDF'))

    def test_missing_wrong_or_nonascii_token_rejected(self):
        for token in ('', 'wrong', 'é'):
            with self.subTest(token=token):
                status, _, _ = self.generate(headers={'X-Local-Token': token})
                self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_host_and_origin_restricted(self):
        for headers in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'},
                        {'Origin': 'null'}, {'Origin': 'http://127.0.0.1:1'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET', '/api/bootstrap', headers=headers)[0], 403)
                self.assertEqual(self.generate(headers=headers)[0], 403)
        same = f'http://127.0.0.1:{self.server.server_port}'
        self.assertEqual(self.generate(headers={'Origin': same})[0], 200)

    def test_bad_json_shapes_and_unexpected_fields_rejected(self):
        for request in ([], {'jd': None}, {'jd': ''}, {'jd': 'test', 'case': '/tmp'},
                        {'jd': 'test', 'family': 'invented'}, {'jd': 'test', 'language': 'xx'}):
            with self.subTest(request=request):
                self.assertEqual(self.generate(request)[0], 400)
        self.assertEqual(self.calls, [])

    def test_invalid_json_content_type_and_body_limit(self):
        headers = {'Content-Type': 'application/json', 'X-Local-Token': self.server.local_token}
        self.assertEqual(self.request('POST', '/api/generate', b'{broken', headers)[0], 400)
        self.assertEqual(self.generate(headers={'Content-Type': 'text/plain'})[0], 415)
        oversized = dict(headers, **{'Content-Length': str(server_module.MAX_BODY + 1)})
        self.assertEqual(self.request('POST', '/api/generate', b'{}', oversized)[0], 413)
        self.assertEqual(self.calls, [])

    def test_private_files_traversal_and_symlinks_not_served(self):
        self.generate()
        folder = self.case / 'generated' / 'synthetic-result'
        (folder / 'linked.md').symlink_to(self.case / 'profile.json')
        (folder / 'active.html').write_text('<script>invalid</script>')
        for path in ('profile.json', '../profile.json', 'generated/../profile.json',
                     'generated/%2e%2e/profile.json', 'generated/synthetic-result/linked.md',
                     'generated/synthetic-result/active.html', '/etc/passwd'):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', '/files/' + path)[0], 404)
        self.assertEqual(self.request('GET', '/profile.json')[0], 404)

    def test_markdown_served_as_plain_text_with_nosniff(self):
        self.generate()
        status, headers, _ = self.request('GET', '/files/generated/synthetic-result/match.md')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/plain; charset=utf-8')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_business_error_is_friendly_and_releases_lock(self):
        original = self.server.generate_func
        def fail(*args, **kwargs):
            raise ValueError('合成错误：证据尚未确认')
        self.server.generate_func = fail
        status, _, body = self.generate()
        self.assertEqual(status, 400)
        self.assertIn('证据尚未确认', json.loads(body)['error'])
        self.server.generate_func = original
        self.assertEqual(self.generate()[0], 200)

    def test_parallel_generation_is_serialized(self):
        with self.server.generation_lock:
            self.assertEqual(self.generate()[0], 409)
        self.assertEqual(self.generate()[0], 200)

    def test_ambiguous_family_can_return_only_match_without_pdf(self):
        original = self.server.generate_func
        def ambiguous(*args, **kwargs):
            result = original(*args, **kwargs)
            result.update(family=None, label='待确认', warnings=['合成方向冲突'])
            result['files'].pop('pdf')
            return result
        self.server.generate_func = ambiguous
        status, _, body = self.generate()
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertIsNone(result['family'])
        self.assertNotIn('pdf', result['files'])

    def test_generator_cannot_publish_private_case_path(self):
        def invalid(*args, **kwargs):
            return {'files': {'match': 'profile.json'}}
        self.server.generate_func = invalid
        self.assertEqual(self.generate()[0], 400)

    def test_cors_preflight_is_not_enabled(self):
        status, headers, _ = self.request('OPTIONS', '/api/generate')
        self.assertEqual(status, 405)
        self.assertNotIn('Access-Control-Allow-Origin', headers)


if __name__ == '__main__':
    unittest.main()
