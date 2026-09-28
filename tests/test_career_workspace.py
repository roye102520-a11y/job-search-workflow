"""Career workspace storage and HTTP checks using a disposable synthetic case."""
import http.client
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
import uuid
import base64

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import career_workspace as workspace
from resume_server import StudioServer


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.case = Path(self.temp.name) / 'case'
        shutil.copytree(ROOT / 'tests/fixtures/synthetic-case', self.case)

    def tearDown(self):
        self.temp.cleanup()

    def review(self):
        return dict(id=str(uuid.uuid4()), date='2026-09-23', kind='practice',
                    question='如何验证需求？', answer='先做访谈', next_action='补充访谈提纲', scores={'证据': 2})

    def test_snapshot_has_no_invented_outcomes(self):
        data = workspace.snapshot(self.case)
        self.assertEqual(data['stats']['projects'], 3)
        self.assertEqual(data['stats']['submitted'], 0)
        self.assertEqual(data['reviews'], [])
        self.assertEqual(data['warnings'], [])

    def test_recommendation_reason_does_not_copy_another_candidates_metrics(self):
        evidence_file = self.case / 'resume-evidence.json'
        data = json.loads(evidence_file.read_text(encoding='utf-8'))
        for entry in data['entries']:
            for bullet in entry.get('bullets', []):
                bullet['zh'] = '处理与岗位方向相关的工作事项。'
                bullet['en'] = 'Handled work related to this role family.'
        evidence_file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        reasons = ' '.join(reason for job in workspace.recommendations(self.case) for reason in job['evidence'])
        self.assertIn('有用户或客户运营相关事实条目', reasons)
        self.assertNotIn('300+', reasons)
        self.assertNotIn('500+', reasons)
        self.assertNotIn('离线评测', reasons)

    def test_review_is_idempotent_and_does_not_change_facts(self):
        original = (self.case / 'career-evidence-bank.md').read_bytes()
        request = self.review()
        first = workspace.save_review(self.case, request)
        self.assertEqual(first, workspace.save_review(self.case, request))
        self.assertEqual(len(workspace.snapshot(self.case)['reviews']), 1)
        self.assertEqual(original, (self.case / 'career-evidence-bank.md').read_bytes())
        with self.assertRaises(ValueError):
            workspace.save_review(self.case, dict(request, next_action='修改'))

    def test_invalid_reviews_rejected(self):
        for override in [{'scores': {'证据': True}}, {'scores': {'证据': 6}}, {'scores': {'外貌': 1}},
                         {'date': 'tomorrow'}, {'question': ''}, {'kind': 'offer'}, {'job_key': 'missing'}]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                workspace.save_review(self.case, dict(self.review(), **override))

    def test_resource_allowlist_and_symlinks(self):
        for name in ['../secret', 'resume-evidence.json']:
            with self.assertRaises(ValueError):
                workspace.document(self.case, name)
        (self.case / 'alias').symlink_to(self.case, target_is_directory=True)
        with self.assertRaises(ValueError):
            workspace.local_file(self.case, 'alias/career-evidence-bank.md')

    def test_portfolio_uses_selected_facts_and_keeps_history(self):
        result = workspace.build_portfolio(self.case, {'project_ids': ['project-reflection']})
        self.assertFalse(result['published'])
        html = (self.case / 'generated' / result['id'] / 'website.html').read_text()
        self.assertIn('Reflection Lab', html)
        self.assertNotIn('Compass Knowledge', html)
        self.assertNotIn('candidate@example.test', html)
        self.assertNotIn('13800000000', html)
        self.assertEqual(workspace.snapshot(self.case)['portfolios'][0]['id'], result['id'])
        for ids in [[], ['project-reflection'] * 2, ['work-atlas'], [{}]]:
            with self.assertRaises(ValueError):
                workspace.build_portfolio(self.case, {'project_ids': ids})

    def test_stale_evidence_blocks_portfolio_and_warns_dashboard(self):
        with (self.case / 'career-evidence-bank.md').open('a') as handle:
            handle.write('\nnew fact')
        self.assertTrue(workspace.snapshot(self.case)['warnings'])
        with self.assertRaises(ValueError):
            workspace.build_portfolio(self.case, {'project_ids': ['project-reflection']})

    def test_project_links_tolerate_spaces_in_names(self):
        links = workspace.project_links('### 文脉 WenMai\n线上地址：https://example.test\n', {'title_zh': '文脉WenMai｜项目'})
        self.assertEqual(links['website'], 'https://example.test')

    def test_intake_deduplicates_without_modifying_facts(self):
        from material_intake import ingest, extract
        content = '# 提供的简历\n用户服务经历，项目与作品集。\n本人贡献尚待核对，不能当作已确认业绩。'
        request = {'name': 'resume.md', 'kind': 'resume', 'content': base64.b64encode(content.encode()).decode()}
        original = (self.case / 'resume-evidence.json').read_bytes()
        result = ingest(self.case, request)
        self.assertEqual(result, ingest(self.case, request))
        self.assertEqual(len(workspace.snapshot(self.case)['materials']), 1)
        self.assertEqual(original, (self.case / 'resume-evidence.json').read_bytes())
        for patch in [{'name': '../escape.md'}, {'content': '!'}, {'kind': 'verified'}, {'name': 'test.exe'}]:
            with self.assertRaises(ValueError):
                ingest(self.case, dict(request, **patch))

    def test_resume_variant_limits_website_to_selected_facts(self):
        data = json.loads((self.case / 'resume-evidence.json').read_text())
        folder = self.case / 'generated/variant'
        folder.mkdir(parents=True)
        selected = data['entries'][3]['bullets'][0]
        (folder / 'selection.json').write_text(json.dumps({'source_digests': data['sources'], 'family': 'product-operations', 'selected_bullet_ids': [selected['id']]}))
        result = workspace.build_portfolio(self.case, {'project_ids':['project-reflection'], 'resume_id':'variant'})
        html = (self.case / 'generated' / result['id'] / 'website.html').read_text()
        self.assertIn(selected['zh'], html)
        self.assertNotIn(data['entries'][3]['bullets'][1]['zh'], html)
        self.assertIn('--paper: #f6f2e9', html)
        with self.assertRaises(ValueError):
            workspace.build_portfolio(self.case, {'project_ids':['project-reflection'], 'resume_id':'missing'})

    def test_http_workspace_resources_save_and_preview(self):
        server = StudioServer(self.case, port=0)
        worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        worker.start()
        def request(method, path, body=None, auth=True):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'Content-Type': 'application/json'}
            if auth:
                headers['X-Local-Token'] = server.local_token
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            connection.close()
            return result
        try:
            self.assertEqual(request('GET', '/api/workspace', auth=False)[0], 403)
            self.assertEqual(request('GET', '/api/workspace')[0], 200)
            self.assertEqual(request('GET', '/studio')[0], 200)
            self.assertEqual(request('GET', '/assets/career-workspace.js')[0], 200)
            self.assertEqual(request('GET', '/resources/resume-evidence.json')[0], 404)
            self.assertEqual(request('GET', '/resources/career-evidence-bank.md')[0], 200)
            self.assertEqual(request('POST', '/api/workspace/review', self.review())[0], 200)
            material = {'name':'test.md', 'kind':'portfolio', 'content':base64.b64encode('合成作品集，记录项目问题、方案与本人贡献，需要来源复核。'.encode()).decode()}
            status, _, payload = request('POST', '/api/workspace/material', material)
            self.assertEqual(status, 200, payload)
            self.assertEqual(json.loads(payload)['status'], 'needs_review')
            status, _, raw = request('POST', '/api/workspace/portfolio', {'project_ids': ['project-reflection']})
            self.assertEqual(status, 200, raw)
            draft = json.loads(raw)
            status, headers, html = request('GET', draft['preview'])
            self.assertEqual(status, 200)
            self.assertIn('sandbox', headers['Content-Security-Policy'])
            self.assertNotIn(b'<script', html)
            self.assertEqual(request('GET', '/files/' + draft['markdown'])[0], 200)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
