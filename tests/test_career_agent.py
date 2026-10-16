"""Local career positioning and bounded discovery; synthetic cases only."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import career_positioning
import career_workspace
import daily_job_search
import foreign_opportunities
import job_data
import resume_pipeline
from evidence_quality import exclusion_reason, usable_entries


class CareerEvidenceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='career-agent-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name) / 'case'
        shutil.copytree(ROOT / 'tests/fixtures/synthetic-case', self.case)
        self.evidence = resume_pipeline.load_evidence(self.case)

    def test_unidentified_review_notes_do_not_exclude_every_entry(self):
        data = dict(self.evidence)
        data['unconfirmed'] = [{'field': 'salary.preference'}]
        self.assertEqual(len(usable_entries(data)), len(data['entries']))

    def test_explicit_entry_reference_still_excludes_only_that_entry(self):
        data = dict(self.evidence)
        excluded_id = data['entries'][0]['id']
        data['unconfirmed'] = [{'entry_id': excluded_id, 'field': 'role.scope'}]
        self.assertTrue(exclusion_reason(data, data['entries'][0]))
        remaining = usable_entries(data)
        self.assertEqual(len(remaining), len(data['entries']) - 1)

    def test_positioning_has_five_bilingual_roles_with_source_refs(self):
        report = career_positioning.build_report(self.case)
        self.assertEqual(len(report['roles']), 5)
        self.assertTrue(all(role['title_zh'] and role['title_en'] for role in report['roles']))
        evaluation = next(role for role in report['roles'] if role['id'] == 'llm-evaluation-ai-quality')
        self.assertNotIn('有个人项目评测实践', evaluation['difficulty'])
        self.assertIn('日期和贡献待复核', evaluation['difficulty'])
        self.assertTrue(all(item['source_ref'] and item['bullet_id'] for role in report['roles'] for item in role['evidence']))
        self.assertIn('录用概率', ''.join(report['limitations']))
        self.assertNotIn('candidate@example.test', json.dumps(report))

    def test_workspace_joins_material_details_from_manifest_without_new_store(self):
        key = 'opportunity-' + 'c' * 20
        row = {'job_key': key, 'company': 'Synthetic Co', 'role': 'AI Operations Associate',
               'url': 'https://example.test/job', 'status': 'preparing', 'execution_status': 'idle',
               'sync_status': 'not_requested'}
        job_data.save_rows(self.case, [row], job_data.FIELDS.copy())
        manifest_path = self.case / 'applications' / key / 'manifest.json'
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps({
            'job_key': key, 'status': 'preparing', 'resume_variant': 'ai-content-operations-v1',
            'resume_path': 'generated/v1/resume-en.pdf', 'email_path': 'generated/v1/email.md',
            'channel': 'email', 'prepared_materials': [{'language': 'en', 'output_dir': 'generated/v1',
                'files': {'pdf': 'generated/v1/resume-en.pdf'}, 'family': 'ai-content-operations',
                'status': 'preparing', 'prepared_at': '2026-10-17T00:00:00+00:00'}]
        }), encoding='utf-8')
        snapshot = career_workspace.snapshot(self.case)
        application = next(item for item in snapshot['applications'] if item['job_key'] == key)
        self.assertEqual(application['resume_variant'], 'ai-content-operations-v1')
        self.assertEqual(application['channel'], 'email')
        self.assertEqual(application['prepared_materials'][0]['language'], 'en')
        with (self.case / 'application-tracker.csv').open(encoding='utf-8') as handle:
            header = handle.readline().strip().split(',')
        self.assertEqual(header, job_data.FIELDS)


class DailyDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='daily-search-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name) / 'case'
        shutil.copytree(ROOT / 'tests/fixtures/synthetic-case', self.case)

    def test_daily_discovery_distributes_bounded_scan_and_never_submits(self):
        calls = []

        def discover(case, tenant, limit, transport=None):
            calls.append((tenant, limit))
            return {'results': [{'job_key': tenant + str(i), 'status': 'discovered',
                                 'job': {'job_key': tenant + str(i), 'company': 'Synthetic Co',
                                         'title': 'Synthetic AI Operations Associate',
                                         'url': 'https://example.test/job', 'location': 'Shanghai',
                                         'verification': {'status': 'verified_open'},
                                         'match': {'grade': 'B', 'employment_category': 'full_time'}}}
                                for i in range(limit)]}

        with patch.object(foreign_opportunities, 'discover', side_effect=discover), \
             patch.object(foreign_opportunities, 'list_jobs', return_value={'jobs': []}):
            result = daily_job_search.discover_daily(self.case, limit=7)
        self.assertEqual(sum(limit for _, limit in calls), 7)
        self.assertLessEqual(result['results_count'], 7)
        self.assertEqual(result['external_actions'], {'emails_sent': 0, 'applications_submitted': 0})
        self.assertEqual(result['scheduler'], 'not_configured')

    def test_daily_discovery_rejects_more_than_ten_and_unreviewed_tenants(self):
        with self.assertRaises(ValueError): daily_job_search.discover_daily(self.case, limit=11)
        with self.assertRaises(ValueError): daily_job_search.discover_daily(self.case, tenants=['unknown'])

    def test_unconfirmed_internship_is_blocked_from_material_preparation(self):
        key = 'opportunity-' + 'a' * 20
        job = {'job_key': key, 'title': 'Synthetic Internship', 'company': 'Synthetic Co',
               'jd': 'Responsibilities include AI content operations and quality review. ' * 2,
               'verification': {'status': 'verified_open'},
               'match': {'grade': 'B', 'employment_category': 'internship',
                         'internship_qualification': {'status': 'needs_confirmation'},
                         'posted_compensation': {'paid_status': 'paid'}}}
        with patch.object(foreign_opportunities, 'list_jobs', return_value={'jobs': [job]}), \
             patch.object(job_data, 'manifests', return_value=[]):
            with self.assertRaisesRegex(ValueError, '毕业资格未被官方确认'):
                daily_job_search._load_selected_jobs(self.case, [key])

    def test_preparing_materials_uses_existing_pipeline_and_does_not_create_submission(self):
        key = 'opportunity-' + 'b' * 20
        folder = self.case / 'applications' / key
        folder.mkdir(parents=True)
        manifest_path = folder / 'manifest.json'
        manifest = {'job_key': key, 'status': 'discovered'}
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        job = {'job_key': key, 'title': 'Synthetic AI Operations Associate', 'company': 'Synthetic Co',
               'url': 'https://example.test/job',
               'jd': 'Responsibilities include AI content operations and quality review. ' * 2,
               'verification': {'status': 'verified_open'},
               'match': {'grade': 'B', 'employment_category': 'full_time',
                         'posted_compensation': {'paid_status': 'paid'}}}
        def generate(case, request, font=None):
            return {'output_dir': 'generated/synthetic-' + request['language'], 'files': {},
                    'family': 'ai-content-operations', 'status': 'preparing', 'reused': False,
                    'rules_version': 'test'}
        with patch.object(foreign_opportunities, 'list_jobs', return_value={'jobs': [job]}), \
             patch.object(daily_job_search, 'generate', side_effect=generate) as generator:
            result = daily_job_search.prepare_selected(self.case, [key])
        self.assertEqual([c.args[1]['language'] for c in generator.call_args_list], ['en', 'zh'])
        self.assertEqual(result['external_actions'], {'emails_sent': 0, 'applications_submitted': 0})
        self.assertEqual(result['jobs'][0]['tracker_status'], 'discovered')
        self.assertEqual(job_data.events(self.case), [])
        stored = json.loads(manifest_path.read_text())
        self.assertEqual(stored['status'], 'discovered')
        self.assertEqual(len(stored['prepared_materials']), 2)
