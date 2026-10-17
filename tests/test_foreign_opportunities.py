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

    def test_response_limit_is_larger_only_for_reviewed_lever_feeds(self):
        self.assertEqual(jobs.response_limit('https://api.lever.co/v0/postings/rws?mode=json'), jobs.MAX_LEVER_FEED_BYTES)
        self.assertEqual(jobs.response_limit('https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true'), jobs.MAX_REVIEWED_ATS_FEED_BYTES)
        self.assertEqual(jobs.response_limit('https://api.ashbyhq.com/posting-api/job-board/openai?includeCompensation=true'), jobs.MAX_REVIEWED_ATS_FEED_BYTES)
        self.assertEqual(jobs.response_limit('https://api.lever.co/v0/postings/unknown?mode=json'), jobs.MAX_BYTES)
        self.assertEqual(jobs.response_limit(URL), jobs.MAX_BYTES)

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

    def test_application_benefits_and_vendor_sections_are_not_hard_requirements(self):
        jd = '''Requirements:
Currently reside in China.
Must pass training modules and a required test.
Work benefits:
Flexible home-based work.
Work-life balance.
Vendor Type:
When applying, select the option describing your working status.
Equal Employment Opportunity:
RWS is an equal opportunity employer.'''
        items = assess(jd, self.evidence())
        required_text = [item['text'] for item in items if item['level'] == 'required']
        self.assertTrue(any(item.startswith('Currently reside in China') for item in required_text))
        self.assertTrue(any('Must pass training modules' in item for item in required_text))
        self.assertFalse(any('Flexible home-based' in item or 'Work-life balance' in item
                             or 'Vendor Type' in item or 'working status' in item
                             or 'equal opportunity employer' in item.lower() for item in required_text))

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

    def test_greenhouse_public_job_detail_is_parsed_and_allowlisted(self):
        url = 'https://boards.greenhouse.io/anthropic/jobs/1234567'
        body = {'id': 1234567, 'title': 'AI Operations Associate',
                'content': '<p>Maintain AI content quality operations.</p><p>Bachelor degree.</p>',
                'location': {'name': 'Remote - China'}, 'absolute_url': url,
                'updated_at': '2026-10-16T10:00:00Z'}
        origin = jobs.source(url)
        self.assertEqual(origin['adapter'], 'greenhouse')
        self.assertIn('/v1/boards/anthropic/jobs/1234567', origin['fetch_url'])
        row = jobs.observe(url, lambda requested: (200, requested, json.dumps(body)))
        self.assertEqual(row['verification']['status'], 'verified_open')
        self.assertEqual(row['company'], 'Anthropic')
        self.assertIn('AI content quality', row['jd'])
        self.assertEqual(row['location'], 'Remote - China')

    def test_html_entities_are_decoded_before_requirement_matching(self):
        url = 'https://boards.greenhouse.io/anthropic/jobs/1234567'
        body = {'id': 1234567, 'title': 'AI Operations Associate',
                'content': '&lt;h2&gt;Minimum qualifications&lt;/h2&gt;&lt;ul&gt;&lt;li&gt;Clear written communication&lt;/li&gt;&lt;/ul&gt;',
                'location': {'name': 'Remote - China'}, 'absolute_url': url}
        row = jobs.observe(url, lambda requested: (200, requested, json.dumps(body)))
        self.assertNotIn('&lt;h2&gt;', row['jd'])
        self.assertIn('Minimum qualifications', row['jd'])

    def test_ashby_public_board_feed_selects_requested_job(self):
        url = 'https://jobs.ashbyhq.com/openai/12345678-1234-1234-1234-123456789012'
        body = {'apiVersion': '1', 'jobs': [
            {'id': '12345678-1234-1234-1234-123456789012', 'title': 'Product Operations Associate',
             'location': 'Remote - China', 'employmentType': 'Full time',
             'descriptionHtml': '<p>Support product operations and customer feedback.</p>',
             'jobUrl': url, 'applyUrl': url + '/application', 'publishedAt': '2026-10-15T12:00:00Z'}]}
        origin = jobs.source(url)
        self.assertEqual(origin['adapter'], 'ashby')
        self.assertIn('/posting-api/job-board/openai', origin['fetch_url'])
        row = jobs.observe(url, lambda requested: (200, requested, json.dumps(body)))
        self.assertEqual(row['verification']['status'], 'verified_open')
        self.assertEqual(row['title'], 'Product Operations Associate')
        self.assertEqual(row['company'], 'OpenAI')

    def test_discover_daily_accepts_non_lever_sources_without_changing_tracker_model(self):
        preferences = {'job_search_strategy': {'geographic_scope': 'global', 'target_directions': [
            {'priority': 'P1', 'label': 'Product Operations', 'keywords': ['Product Operations']} ]}}
        (self.case / 'search-preferences.json').write_text(json.dumps(preferences), encoding='utf-8')
        ident = '12345678-1234-1234-1234-123456789012'
        url = 'https://jobs.ashbyhq.com/openai/' + ident
        board = {'jobs': [{'id': ident, 'title': 'Product Operations Associate', 'location': 'Remote - China',
                           'employmentType': 'Full time', 'descriptionHtml': '<p>Support product operations and customer feedback.</p>',
                           'jobUrl': url, 'applyUrl': url + '/application', 'publishedAt': '2026-10-15T12:00:00Z'}]}
        def fake(requested):
            if 'posting-api/job-board/openai' in requested:
                return 200, requested, json.dumps(board)
            return 200, requested, json.dumps(board)
        from daily_job_search import discover_daily
        result = discover_daily(self.case, 1, ['ashby:openai'], fake)
        self.assertEqual(result['results_count'], 1)
        self.assertEqual(result['jobs'][0]['source_id'], 'ashby:openai')
        self.assertEqual(result['jobs'][0]['adapter'], 'ashby')
        self.assertEqual(len(job_data.rows(self.case)[0]), 1)

    def test_workday_search_feed_uses_exact_tenant_and_imports_official_job(self):
        preferences = {'job_search_strategy': {'geographic_scope': 'global', 'target_directions': [
            {'priority': 'P0', 'label': 'AI Operations', 'keywords': ['AI Operations']} ]}}
        (self.case / 'search-preferences.json').write_text(json.dumps(preferences), encoding='utf-8')
        path = '/en-US/Cerence/job/Shanghai/AI-Operations_R123'
        feed = {'jobPostings': [{'title': 'AI Operations Associate', 'locationsText': 'Shanghai, China',
                                 'externalPath': path, 'postedOn': '2026-10-15'}]}
        detail = {'jobPostingInfo': {'title': 'AI Operations Associate', 'jobDescription': '<p>Support AI operations and quality review.</p>',
                                     'jobReqId': 'R123', 'location': 'Shanghai, China', 'timeType': 'Full time',
                                     'canApply': True, 'posted': True}}
        requests = []
        def fake(requested, payload=None):
            requests.append((requested, payload))
            if requested.endswith('/jobs'):
                return 200, requested, json.dumps(feed)
            return 200, requested, json.dumps(detail)
        result = jobs.discover(self.case, 'cerence', 1, fake, adapter='workday')
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['job']['title'], 'AI Operations Associate')
        self.assertEqual(requests[0][1]['limit'], 5)

    def test_unverified_source_is_U_and_unpaid_is_deprioritized(self):
        unverified = jobs.observe(URL, lambda u: (200, u, '{}'))
        self.assertEqual(jobs.matching(self.case, unverified)['grade'], 'U')
        unpaid = jobs.parse(URL, payload('Required:\nBachelor degree.\nThis is an unpaid internship.'))
        unpaid['verification'] = {'status': 'verified_open', 'checked_at': '2026-10-16T00:00:00+00:00'}
        self.assertEqual(jobs.matching(self.case, unpaid)['grade'], 'C')
        self.assertEqual(jobs.matching(self.case, unpaid)['posted_compensation']['paid_status'], 'unpaid')

    def test_discover_uses_private_priority_and_excludes_out_of_scope_locations(self):
        preferences = {'job_search_strategy': {'target_directions': [
            {'priority': 'P0', 'label': 'AI Operations', 'keywords': ['AI Operations']},
            {'priority': 'P1', 'label': 'Product Operations', 'keywords': ['Product Operations', 'Product Assistant']},
            {'priority': 'P2', 'label': 'UX Research', 'keywords': ['UX Research']},
        ]}}
        (self.case / 'search-preferences.json').write_text(json.dumps(preferences), encoding='utf-8')
        identifiers = [f'{i:08x}-1111-1111-1111-111111111111' for i in range(1, 7)]
        feed_items = [
            {'id': identifiers[0], 'text': 'Product Assistant Intern', 'hostedUrl': 'https://jobs.lever.co/weloglobal/' + identifiers[0], 'categories': {'location': 'Shanghai, China', 'commitment': 'Internship'}},
            {'id': identifiers[1], 'text': 'AI Operations Associate', 'hostedUrl': 'https://jobs.lever.co/weloglobal/' + identifiers[1], 'categories': {'location': 'Shanghai, China', 'commitment': 'Full-time'}},
            {'id': identifiers[2], 'text': 'Senior AI Operations Associate', 'hostedUrl': 'https://jobs.lever.co/weloglobal/' + identifiers[2], 'categories': {'location': 'Shanghai, China', 'commitment': 'Full-time'}},
            {'id': identifiers[3], 'text': 'AI Operations Intern', 'hostedUrl': 'https://jobs.lever.co/weloglobal/' + identifiers[3], 'categories': {'location': 'Remote', 'commitment': 'Internship'}},
            {'id': identifiers[4], 'text': 'UX Research Assistant', 'hostedUrl': 'https://jobs.lever.co/weloglobal/' + identifiers[4], 'categories': {'location': 'London, UK', 'commitment': 'Full-time'}},
            {'id': identifiers[5], 'text': 'AI Operations Associate', 'hostedUrl': 'https://jobs.lever.co/weloglobal/' + identifiers[5], 'categories': {'location': 'Remote, China', 'commitment': 'Full-time'}},
        ]
        def fake_transport(url):
            if '?mode=json' in url:
                return 200, url, json.dumps(feed_items)
            ident = url.rsplit('/', 1)[-1]
            item = next(row for row in feed_items if row['id'] == ident)
            detail = {'id': ident, 'text': item['text'], 'descriptionPlain': JD,
                      'categories': item['categories'], 'applyUrl': item['hostedUrl'] + '/apply'}
            return 200, url, json.dumps(detail)
        result = jobs.discover(self.case, 'weloglobal', limit=10, transport=fake_transport)
        titles = [item['job']['title'] for item in result['results']]
        self.assertEqual(titles, ['AI Operations Associate', 'AI Operations Associate', 'Product Assistant Intern'])
        self.assertTrue(all(item['job']['location'] != 'London, UK' for item in result['results']))
        self.assertNotIn('Senior AI Operations Associate', titles)
        self.assertNotIn(identifiers[3], [item['job']['requisition_id'] for item in result['results']])

    def test_discover_keeps_china_remote_evaluator_when_feed_office_city_is_different(self):
        ident = '77777777-1111-1111-1111-111111111111'
        url = 'https://jobs.lever.co/rws/' + ident
        jd = 'China (Work from Home). Search Engine Evaluator: evaluate search results and provide quality feedback for AI data. Paid contract.'
        feed = [{'id': ident, 'text': 'Search Engine Evaluator - Chinese Simplified (China)',
                 'hostedUrl': url, 'categories': {'location': 'Beijing', 'commitment': 'Temporary/Contract'},
                 'descriptionPlain': jd}]
        def fake_transport(requested):
            if '?mode=json' in requested:
                return 200, requested, json.dumps(feed)
            return 200, requested, json.dumps({'id': ident, 'text': feed[0]['text'],
                'descriptionPlain': jd, 'categories': feed[0]['categories'], 'applyUrl': url + '/apply'})
        result = jobs.discover(self.case, 'rws', limit=10, transport=fake_transport)
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['job']['company'], 'RWS Group')
        self.assertEqual(result['results'][0]['job']['location'], 'Beijing')

    def test_china_remote_listing_counts_as_in_scope_despite_ats_office_city(self):
        job = {'title': 'Search Engine Evaluator - Chinese Simplified (China)',
               'company': 'RWS Group', 'location': 'Beijing', 'employment_type': 'Temporary/Contract',
               'jd': 'China (Work from Home). Search Engine Evaluator: evaluate search results and provide quality feedback for AI data. Paid contract. Currently reside in China.',
               'url': 'https://jobs.lever.co/rws/77777777-1111-1111-1111-111111111111',
               'verification': {'status': 'verified_open', 'verified_at': '2026-10-16T17:08:57Z'}}
        match = jobs.matching(self.case, job)
        self.assertEqual(match['grade'], 'B')  # Permit and compensation still need confirmation.
        self.assertNotIn('地点尚未证明符合上海、苏州或中国远程范围。', match['grade_reasons'])
        self.assertTrue(any('远程雇佣国家' in reason for reason in match['grade_reasons']))

    def test_discover_includes_early_career_software_implementation_consultant(self):
        ident = '88888888-1111-1111-1111-111111111111'
        url = 'https://jobs.lever.co/veeva/' + ident
        jd = 'Support software implementation, customer workshops, data migration, system testing and training documentation.'
        feed = [{'id': ident, 'text': 'Associate Consultant', 'hostedUrl': url,
                 'categories': {'location': 'China - Shanghai', 'commitment': 'Full-time'},
                 'descriptionPlain': jd}]
        def fake_transport(requested):
            if '?mode=json' in requested:
                return 200, requested, json.dumps(feed)
            return 200, requested, json.dumps({'id': ident, 'text': feed[0]['text'],
                'descriptionPlain': jd, 'categories': feed[0]['categories'], 'applyUrl': url + '/apply'})
        result = jobs.discover(self.case, 'veeva', limit=10, transport=fake_transport)
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['job']['title'], 'Associate Consultant')

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

    def test_employment_type_salary_and_work_mode_are_explicit_or_unknown(self):
        internship = {'title': 'AI Quality Intern', 'employment_type': 'Internship',
                      'jd': 'Paid internship. Compensation: CNY 8,000 per month. Work from home in China.',
                      'location': 'Remote - China'}
        self.assertEqual(jobs.employment_category(internship), 'internship')
        self.assertEqual(jobs.compensation_details(internship)['paid_status'], 'paid')
        self.assertIn('CNY 8,000', jobs.compensation_details(internship)['published'])
        structured = jobs.compensation_details({'compensation': {'currency': 'CNY', 'value': {'minValue': 8000, 'maxValue': 10000, 'unitText': 'MONTH'}}})
        self.assertEqual(structured['paid_status'], 'paid')
        self.assertIn('CNY', structured['published'])
        self.assertEqual(jobs.work_arrangement(internship)['status'], 'remote')
        self.assertEqual(jobs.employment_category({'title': 'Content Quality', 'employment_type': 'Freelance project'}), 'project_freelance')
        self.assertEqual(jobs.employment_category({'title': 'Graduate Program Associate', 'employment_type': 'Full-time'}), 'graduate_program')
        self.assertEqual(jobs.employment_category({'title': 'Operations Associate', 'employment_type': 'Full-time'}), 'full_time')
        self.assertEqual(jobs.compensation_details({'jd': 'Responsibilities: organize knowledge articles.'})['paid_status'], 'unknown')
        hourly = jobs.compensation_details({'jd': 'Pay: Up to 6 USD/hour.'})
        self.assertEqual(hourly['paid_status'], 'paid')
        self.assertEqual(hourly['published'], 'Pay: Up to 6 USD/hour.')
        company_overview = jobs.compensation_details({'jd': 'About us: We are a global SaaS company. We discuss salary philosophy and reached $3B revenue.'})
        self.assertEqual(company_overview['paid_status'], 'unknown')
        self.assertEqual(company_overview['published'], '未知（来源未披露）')
        competitive = jobs.compensation_details({'jd': 'Salary: Competitive. Our company revenue exceeded $3B.'})
        self.assertEqual(competitive['paid_status'], 'unknown')
        self.assertEqual(competitive['published'], 'Salary: Competitive.')
        annual = jobs.compensation_details({'jd': 'Annual Salary:\n$120,000—$160,000 USD'})
        self.assertEqual(annual['paid_status'], 'paid')
        self.assertIn('$120,000', annual['published'])
        self.assertEqual(jobs.work_arrangement({'location': 'Shanghai', 'jd': 'Responsibilities: organize knowledge articles.'})['status'], 'unknown')

    def test_internship_graduate_eligibility_requires_current_official_acceptance(self):
        official = {'title': 'AI Content Intern', 'employment_type': 'Internship',
                    'jd': 'Paid internship. Graduates are welcome. Mentorship and training provided.',
                    'verification': {'status': 'verified_open'}}
        eligible = jobs.internship_qualification(official, [], 'verified_open')
        self.assertEqual(eligible['status'], 'eligible')
        self.assertEqual(jobs.internship_growth(official)['status'], 'supported')

        recent_only = dict(official, jd='Paid internship. Recent graduates are welcome.')
        self.assertEqual(jobs.internship_qualification(recent_only, [], 'verified_open')['status'], 'needs_confirmation')
        self.assertEqual(jobs.internship_qualification(official, [], 'stale')['status'], 'needs_confirmation')
        unspecified = dict(official, jd='Paid internship. Organize content quality reviews.')
        self.assertEqual(jobs.internship_qualification(unspecified, [], 'verified_open')['status'], 'needs_confirmation')

        student_only = [dict(level='required', status='not_met', text='Currently enrolled university student required')]
        blocked = jobs.internship_qualification(official, student_only, 'verified_open')
        self.assertEqual(blocked['status'], 'ineligible')
        self.assertIn('Currently enrolled', blocked['reason'])
        explicitly_student_only = dict(official, jd='Paid internship. Current university students only.')
        self.assertEqual(jobs.internship_qualification(explicitly_student_only, [], 'verified_open')['status'], 'ineligible')
        self.assertEqual(jobs.internship_qualification(explicitly_student_only, student_only, 'stale')['status'], 'needs_confirmation')

        year_requirements = assess("Required: Bachelor's degree, graduating in 2026 or 2027.",
                                   self.evidence(graduation_date='2023-06', graduation_source_ref='evidence.md#education'))
        year_blocked = jobs.internship_qualification(official, year_requirements, 'verified_open')
        self.assertEqual(year_blocked['status'], 'ineligible')

    def test_unconfirmed_internship_eligibility_cannot_receive_a_grade(self):
        job = jobs.parse(URL, payload('Paid internship. Assist with AI content quality and data review.'))
        job.update(title='AI Content Intern', employment_type='Internship',
                   verification={'status': 'verified_open', 'verified_at': '2026-10-16T00:00:00+00:00'})
        match = jobs.matching(self.case, job)
        self.assertEqual(match['internship_qualification']['status'], 'needs_confirmation')
        self.assertNotEqual(match['grade'], 'A')
        self.assertIn('已毕业', ' '.join(match['warnings']))

    def test_capability_fit_is_separate_from_eligibility_and_has_project_trace(self):
        job = jobs.parse(URL, payload('Responsibilities:\nMaintain a knowledge base, content operations and data annotation quality checks.\nRequired:\nBachelor degree.\nEnglish communication.'))
        job.update(title='AI Content Operations Associate', location='Shanghai',
                   verification={'status': 'verified_open', 'verified_at': '2026-10-16T00:00:00+00:00'})
        match = jobs.matching(self.case, job)
        self.assertIn(match['capability_match']['level'], {'A', 'B', 'C', 'U'})
        self.assertIn('assessment_type', match['capability_match'])
        self.assertIn('evidence_by_kind', match['capability_match'])
        self.assertIn('eligibility', match)
        self.assertIn('project_recommendations', match)
        self.assertEqual(match['ready_to_apply'], False)

    def test_private_target_directions_override_generic_legacy_ranking(self):
        job = {'title': 'Operations Associate', 'jd': 'Required: Bachelor degree. Support onboarding.',
               'verification': {'status': 'verified_open'}}
        prefs = {'job_search_strategy': {'target_directions': [
            {'priority': 'P0', 'label': 'Private target', 'keywords': ['Operations Associate']}]}}
        self.assertEqual(jobs.target_alignment(job, prefs), ('P0', 'Private target', 'Operations Associate'))
        self.assertEqual(jobs.target_alignment(job, {}), (None, None, None))

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
