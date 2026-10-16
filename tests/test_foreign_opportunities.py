"""P0 audit: synthetic sources only. Expected failures are unresolved defects.

No live network, candidate data, external submission or mail is used here.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import foreign_opportunities as jobs
import job_data
from jd_requirements import assess
from resume_pipeline import generate, canonical_job_url

URL = 'https://jobs.lever.co/weloglobal/11111111-1111-1111-1111-111111111111'
FIXTURE = Path(__file__).parent / 'fixtures/synthetic-case'
JD = 'Responsibilities:\nMaintain a knowledge base, content operations and data annotation quality checks.\nRequired:\nBachelor degree.\nEnglish communication.'


def payload(jd=JD):
    return json.dumps({'id': URL.rsplit('/', 1)[-1], 'text': 'AI Content Operations',
                       'descriptionPlain': jd, 'categories': {'location': 'China', 'commitment': 'Freelance'},
                       'applyUrl': URL + '/apply'})


def transport(url):
    return 200, url, payload()


class ForeignDiscoveryAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-foreign-audit-')
        self.addCleanup(self.temp.cleanup)
        self.case = Path(self.temp.name) / 'case'
        shutil.copytree(FIXTURE, self.case)

    def evidence(self, **person):
        return {'person': {'education_zh': '英语本科，已毕业', 'education_complete': True, **person}, 'entries': []}

    def test_invalid_sources_and_client_verification_flags_are_rejected(self):
        for url in ['http://127.0.0.1/job', 'https://evil.test/job', 'https://jobs.lever.co/unknown/111',
                    'https://user:secret@jobs.lever.co/weloglobal/x', 'https://jobs.lever.co:444/weloglobal/x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                jobs.import_url(self.case, {'url': url}, transport)
        with self.assertRaises(ValueError):
            jobs.import_url(self.case, {'url': URL, 'verified': True}, transport)

    def test_http_200_landing_or_redirect_does_not_prove_job_open(self):
        for fake in [lambda u: (200, u, '{}'), lambda u: (200, 'https://api.lever.co/careers', payload())]:
            job = jobs.observe(URL, fake)
            self.assertEqual(job['verification']['status'], 'unknown')
            self.assertIsNone(job['verification']['verified_at'])

    def test_network_failure_and_closed_page_remain_non_actionable(self):
        def disconnected(url): raise OSError('synthetic network outage')
        self.assertEqual(jobs.observe(URL, disconnected)['verification']['status'], 'unknown')
        self.assertEqual(jobs.observe(URL, lambda u: (410, u, 'gone'))['verification']['status'], 'closed')

    def test_imported_jd_enters_existing_tracker_without_submit(self):
        result = jobs.import_url(self.case, {'url': URL}, transport)
        key = result['job_key']
        self.assertEqual(result['status'], 'discovered')
        self.assertEqual(result['job']['verification']['status'], 'verified_open')
        self.assertEqual(jobs.studio_job(self.case, key)['jd'], JD)
        rows = job_data.rows(self.case)[0]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'discovered')
        self.assertFalse(rows[0].get('submitted_at'))
        self.assertEqual(job_data.events(self.case), [])
        self.assertFalse(result['job']['match']['ready_to_apply'])

    def test_duplicate_import_preserves_stage_and_materials(self):
        first = jobs.import_url(self.case, {'url': URL}, transport)
        path = self.case / 'applications' / first['job_key'] / 'manifest.json'
        before = path.read_bytes()
        jd_path = self.case / 'applications' / first['job_key'] / 'jd.md'
        jd_before = jd_path.read_bytes()
        rows, fields = job_data.rows(self.case)
        rows[0]['status'] = 'interview'
        rows[0]['submitted_at'] = '2026-10-01T10:00:00+00:00'
        job_data.save_rows(self.case, rows, fields)
        row_before = job_data.rows(self.case)[0][0]
        events_before = job_data.events(self.case)
        second = jobs.import_url(self.case, {'url': URL + '?utm_source=test#apply'}, transport)
        self.assertTrue(second['duplicate'])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(jd_path.read_bytes(), jd_before)
        self.assertEqual(job_data.rows(self.case)[0][0], row_before)
        self.assertEqual(job_data.events(self.case), events_before)
        self.assertEqual(len(job_data.rows(self.case)[0]), 1)

    def test_snapshot_tampering_invalidates_verification(self):
        result = jobs.import_url(self.case, {'url': URL}, transport)
        row = jobs.list_jobs(self.case)['jobs'][0]
        (self.case / row['verification']['source_path']).write_text('changed')
        self.assertEqual(jobs.list_jobs(self.case)['jobs'][0]['verification']['status'], 'unknown')

    def test_expired_observation_needs_refresh(self):
        result = jobs.import_url(self.case, {'url': URL}, transport)
        path = self.case / 'applications' / result['job_key'] / 'opportunity.json'
        data = json.loads(path.read_text())
        data['verification']['verified_at'] = '2020-01-01T00:00:00+00:00'
        path.write_text(json.dumps(data))
        self.assertEqual(jobs.list_jobs(self.case)['jobs'][0]['verification']['status'], 'stale')

    def test_discovery_cannot_start_submission(self):
        result = jobs.import_url(self.case, {'url': URL}, transport)
        manifest = job_data.read_json(self.case / 'applications' / result['job_key'] / 'manifest.json')
        with self.assertRaises(ValueError): job_data.start(self.case, manifest)
        self.assertEqual(job_data.events(self.case), [])

    def test_hash_routed_jobs_are_distinct_across_modules(self):
        a, b = 'https://example.test/careers#/jobs/123', 'https://example.test/careers#/jobs/456'
        self.assertNotEqual(job_data.canonical(a), job_data.canonical(b))
        self.assertNotEqual(canonical_job_url(a), canonical_job_url(b))

    def test_regression_ordinary_page_anchors_do_not_create_duplicate_jobs(self):
        self.assertEqual(job_data.canonical('https://example.test/job/123#apply'),
                         job_data.canonical('https://example.test/job/123#description'))

    def test_enrolled_only_job_is_not_supported_by_completed_degree(self):
        evidence = self.evidence(enrollment={'value': 'not_enrolled', 'status': 'confirmed', 'source_ref': 'evidence.md#enrollment'})
        item = assess("Required: Currently enrolled in a Bachelor's degree program.", evidence)[0]
        self.assertEqual(item['status'], 'not_met')

    def test_graduation_window_rejects_wrong_year_and_preserves_unknown(self):
        jd = "Required: Bachelor's degree, graduating in 2026 or 2027."
        evidence = self.evidence(graduation_date='2023-06', graduation_source_ref='evidence.md#education')
        self.assertEqual(assess(jd, evidence)[0]['status'], 'not_met')
        self.assertNotEqual(assess(jd, self.evidence())[0]['status'], 'supported')

    def test_graduation_does_not_infer_current_enrolment(self):
        self.assertNotEqual(assess('Required: Currently enrolled university student.', self.evidence())[0]['status'], 'supported')

    def test_regression_realistic_what_you_bring_heading_preserves_graduation_gate(self):
        jd = "What you'll bring\nFull-time student who will be graduated in 2028 (Mandatory Requirement)\nQualifications\nWhat you'll build\nAssist with process documentation."
        evidence = self.evidence(graduation_date='2023-06', graduation_source_ref='evidence.md#education')
        items = assess(jd, evidence)
        self.assertTrue(any('2028' in item['text'] and item['level'] == 'required' and item['status'] == 'not_met' for item in items))

    def test_cn_permission_does_not_prove_uk_permission(self):
        evidence = self.evidence(capabilities={'work_authorization': {'status': 'confirmed', 'value': True, 'countries': ['CN'], 'source_ref': 'evidence.md#permit'}})
        self.assertNotEqual(assess('Required: UK work authorization.', evidence)[0]['status'], 'supported')

    def test_current_pipeline_can_generate_from_imported_source_without_new_manifest(self):
        try: import reportlab, pypdf
        except ImportError: self.skipTest('PDF dependencies unavailable')
        result = jobs.import_url(self.case, {'url': URL}, transport)
        request = {**jobs.studio_job(self.case, result['job_key']), 'family': 'ai-content-operations', 'language': 'en'}
        result = generate(self.case, request)
        self.assertIn('pdf', result['files'])
        self.assertNotIn('manifest', result['files'])
        self.assertEqual(len(job_data.manifests(self.case)), 1)
        self.assertEqual(job_data.rows(self.case)[0][0]['status'], 'discovered')

    def test_regression_compound_permit_must_not_hide_english_requirement(self):
        evidence = self.evidence(capabilities={'work_authorization': {'status': 'confirmed', 'value': True, 'countries': ['CN'], 'source_ref': 'evidence.md#permit'}})
        items = assess('Required: Fluent English and China work authorization.', evidence)
        self.assertEqual(len(items), 2)
        self.assertEqual({item['status'] for item in items}, {'supported', 'unknown'})

    def test_regression_false_cn_permission_must_not_reject_uk_permission(self):
        evidence = self.evidence(capabilities={'work_authorization': {'status': 'confirmed', 'value': False, 'countries': ['CN'], 'source_ref': 'evidence.md#permit'}})
        self.assertNotEqual(assess('Required: UK work authorization.', evidence)[0]['status'], 'not_met')

    def test_regression_discovery_resumes_after_manifest_before_tracker_crash(self):
        result = jobs.import_url(self.case, {'url': URL}, transport)
        (self.case / 'application-tracker.csv').unlink()
        retry = jobs.import_url(self.case, {'url': URL}, transport)
        self.assertTrue(retry['tracker_restored'])
        self.assertEqual(len(job_data.rows(self.case)[0]), 1)

    def test_regression_reimport_refreshes_previous_failed_verification(self):
        result = jobs.import_url(self.case, {'url': URL}, lambda u: (403, u, 'blocked'))
        retry = jobs.import_url(self.case, {'url': URL}, transport)
        self.assertTrue(retry['refreshed'])
        job = jobs.list_jobs(self.case)['jobs'][0]
        self.assertEqual(job['verification']['status'], 'verified_open')
        self.assertEqual(len(job['observations']), 2)
        self.assertTrue((self.case / job['verification']['source_path']).is_file())

    def test_regression_closed_flag_is_explicit_not_generic_unknown(self):
        info = {'jobPostingInfo': {'title': 'Closed synthetic UX Intern', 'jobDescription': JD, 'jobReqId': 'R1', 'canApply': False, 'posted': False}}
        url = 'https://cerence.wd5.myworkdayjobs.com/Cerence/job/Shanghai/Closed_R1'
        job = jobs.observe(url, lambda u: (200, u, json.dumps(info)))
        self.assertEqual(job['verification']['status'], 'closed')

    def test_smartrecruiters_official_api_detail_is_parsed(self):
        url = 'https://jobs.smartrecruiters.com/BoschGroup/744000123456789-AI-Quality-Intern'
        api_url = 'https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/744000123456789'
        body = {'id': '744000123456789', 'name': 'AI Quality Intern', 'active': True,
                'refNumber': 'R-100', 'postingUrl': url, 'applyUrl': url + '/apply',
                'releasedDate': '2026-10-15T10:00:00Z',
                'location': {'city': 'Shanghai', 'country': 'China'},
                'typeOfEmployment': {'label': 'Internship'},
                'jobAd': {'sections': {'qualifications': {'title': 'Qualifications', 'text': '<p>Bachelor degree.</p>'},
                                       'jobDescription': {'title': 'What you will do', 'text': '<p>Review LLM output quality and maintain annotation guidelines.</p>'}}}}
        origin = jobs.source(url)
        self.assertEqual(origin['fetch_url'], api_url)
        job = jobs.observe(url, lambda requested: (200, requested, json.dumps(body)))
        self.assertEqual(job['verification']['status'], 'verified_open')
        self.assertEqual(job['title'], 'AI Quality Intern')
        self.assertEqual(job['location'], 'Shanghai, China')
        self.assertEqual(job['posted_date'], '2026-10-15')
        self.assertIn('Bachelor degree', job['jd'])
        self.assertTrue(job['apply_url'].endswith('/apply'))

    def test_unverified_source_is_U_and_unpaid_is_D(self):
        unverified = jobs.observe(URL, lambda u: (200, u, '{}'))
        self.assertEqual(jobs.matching(self.case, unverified)['grade'], 'U')
        unpaid = jobs.parse(URL, payload('Required:\nBachelor degree.\nThis is an unpaid internship.'))
        unpaid['verification'] = {'status': 'verified_open', 'checked_at': '2026-10-16T00:00:00+00:00'}
        self.assertEqual(jobs.matching(self.case, unpaid)['grade'], 'D')

    def test_target_priority_is_separate_from_nonprobabilistic_evidence_coverage(self):
        p0 = jobs.parse(URL, payload())
        p0['verification'] = {'status': 'verified_open', 'checked_at': '2026-10-16T00:00:00+00:00'}
        match = jobs.matching(self.case, p0)
        self.assertEqual(match['target_priority'], 'P0')
        self.assertIn('不是录取概率', match['score_label'])
        p1 = dict(p0, title='Product Operations Associate', jd='Required:\nBachelor degree.\nAssist product operations and customer feedback tracking.')
        self.assertEqual(jobs.matching(self.case, p1)['target_priority'], 'P1')
        p2 = dict(p0, title='UX Research Assistant', jd='Required:\nBachelor degree.\nSupport UX research operations and participant scheduling.')
        self.assertEqual(jobs.matching(self.case, p2)['target_priority'], 'P2')

    def test_graduation_year_is_read_from_reviewed_source_with_traceable_reference(self):
        bank = self.case / 'career-evidence-bank.md'
        bank.write_text(bank.read_text(encoding='utf-8') + '\n- 毕业时间：2023.06\n', encoding='utf-8')
        cache_path = self.case / 'resume-evidence.json'
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        for source in cache['sources']:
            if source['path'] == 'career-evidence-bank.md':
                source['sha256'] = hashlib.sha256(bank.read_bytes()).hexdigest()
        cache_path.write_text(json.dumps(cache), encoding='utf-8')
        job = jobs.parse(URL, payload('Required:\nBachelor degree, graduating in 2026 or 2027.'))
        job['verification'] = {'status': 'verified_open', 'checked_at': '2026-10-16T00:00:00+00:00'}
        result = jobs.matching(self.case, job)
        graduation = next(item for item in result['requirements'] if '2026' in item['text'])
        self.assertEqual(graduation['status'], 'not_met')
        self.assertIn('career-evidence-bank.md#毕业时间', [proof['source_ref'] for proof in graduation['evidence']])
