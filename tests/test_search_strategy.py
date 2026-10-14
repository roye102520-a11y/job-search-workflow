import csv
import json
import shutil
import sys
import tempfile
import unittest
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from search_strategy import rank_jobs, followups, run


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name)
        fixture = Path(__file__).parent / 'fixtures' / 'synthetic-case'
        for path in fixture.iterdir():
            shutil.copyfile(path, self.case / path.name)
        self.today = date(2026, 10, 11)
        self.now = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
        (self.case / 'receipt.md').write_text('Synthetic observation evidence')

    def job(self, **extra):
        return dict(company='合成公司', title='内容运营', jd='任职要求：知识库整理', **extra)

    def rank(self, jobs):
        return rank_jobs(self.case, {'jobs': jobs}, self.today)

    def tracked(self, rows):
        fields = ['job_key', 'company', 'role', 'url', 'status', 'execution_status']
        with (self.case / 'application-tracker.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def events(self, extra=()):
        events = [self.event('attempt_started', '', '2026-09-01T00:00:00Z', attempt_id='a'),
                  self.event('attempt_result', 'submitted', '2026-09-01T12:00:00Z', attempt_id='a')] + list(extra)
        (self.case / 'application-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))

    def event(self, action, result, timestamp='2026-09-20T12:00:00+00:00', **extra):
        return dict(job_key='one', event_id=str(uuid.uuid4()), source='user_report', evidence_path='receipt.md',
                    action=action, result=result, timestamp=timestamp, **extra)

    def active(self):
        self.tracked([dict(job_key='one', company='合成公司', role='运营', status='submitted')])

    def test_hard_fail_and_unknown_never_outrank_review(self):
        good = self.job()
        unknown = {**good, 'jd': '任职要求：知识库整理；SQL'}
        blocked = {**good, 'jd': '任职要求：至少10年用户运营经验；知识库整理'}
        result = self.rank([unknown, blocked, good])
        self.assertEqual([x['status'] for x in result['jobs']], ['review', 'needs_review', 'blocked'])
        self.assertTrue(result['jobs'][0]['requirements'][0]['evidence_refs'])

    def test_dedup_preserves_job_ids_and_does_not_merge_titles(self):
        jobs = [self.job(url='https://example.test/job?id=1&utm_source=x'),
                self.job(url='https://example.test/job?id=1'),
                self.job(url='https://example.test/job?id=2'), self.job(), self.job()]
        result = self.rank(jobs)
        self.assertEqual(sum(r['status'] == 'duplicate' for r in result['jobs']), 1)
        self.assertEqual(result['jobs'][-1]['duplicate_of'], '1')

    def test_dates_urgent_expired_invalid_and_stale(self):
        result = self.rank([self.job(deadline='2026-10-10'), self.job(deadline='2026-10-11'),
                            self.job(deadline='ASAP', posted_date='2020-01-01')])
        rows = {r['id']: r for r in result['jobs']}
        self.assertEqual(rows['1']['status'], 'expired')
        self.assertTrue(rows['2']['urgent'])
        self.assertEqual(rows['3']['status'], 'review')
        self.assertEqual(len(rows['3']['warnings']), 3)

    def test_hash_route_job_ids_are_not_merged(self):
        first = self.job(url='https://example.test/careers#/jobs/123')
        second = {**self.job(url='https://example.test/careers#/jobs/456'), 'jd': '任职要求：SQL 查询'}
        self.assertEqual([r['status'] for r in self.rank([first, second])['jobs']], ['review', 'needs_review'])
        self.tracked([dict(job_key='one', url=first['url'], status='preparing')])
        result = self.rank([first, second])
        self.assertEqual(result['jobs'][0]['status'], 'needs_review')
        self.assertEqual(result['gaps'][0]['topic'], 'SQL')

    def test_tracked_excluded_and_missing_not_scored(self):
        self.tracked([dict(job_key='one', url='https://example.test/one', status='preparing')])
        (self.case / 'search-preferences.json').write_text(json.dumps({'excluded_companies': ['排除公司']}))
        jobs = [self.job(url='https://example.test/one'), {**self.job(), 'company': '排除公司'}, {**self.job(), 'jd': ''}]
        result = self.rank(jobs)
        self.assertEqual({r['status'] for r in result['jobs']}, {'tracked', 'excluded', 'missing_jd'})
        self.assertTrue(all(r['score'] is None for r in result['jobs']))

    def test_gaps_count_jobs_once_and_separate_eligibility(self):
        jobs = [{**self.job(), 'jd': '任职要求：SQL查询；SQL报表；至少10年用户运营经验'},
                {**self.job(), 'jd': '任职要求：SQL查询'}]
        gaps = self.rank(jobs)['gaps']
        sql = next(g for g in gaps if g['topic'] == 'SQL')
        self.assertEqual((sql['job_count'], sql['required_count'], sql['priority']), (2, 2, 6))
        self.assertEqual(next(g for g in gaps if g['topic'] != 'SQL')['kind'], 'eligibility')

    def test_stale_evidence_and_bad_shapes_rejected(self):
        for request in ({'jobs': []}, {'jobs': [None]}, {'jobs': [self.job(url='javascript:alert(1)')]}):
            with self.assertRaises(ValueError):
                rank_jobs(self.case, request, self.today)
        (self.case / 'coaching-state.md').write_text('changed evidence')
        with self.assertRaises(ValueError):
            self.rank([self.job()])

    def test_report_preserves_inputs_and_tracker(self):
        self.active()
        before = (self.case / 'application-tracker.csv').read_bytes()
        result = run(self.case, {'jobs': [self.job()]})
        self.assertTrue((self.case / result['file']).is_file())
        self.assertTrue((self.case / result['file']).with_name('request.json').is_file())
        self.assertEqual(before, (self.case / 'application-tracker.csv').read_bytes())

    def test_no_submission_event_means_no_draft(self):
        self.active()
        result = followups(self.case, now=self.now)
        self.assertEqual(result['due'], [])
        self.assertEqual(len(result['held']), 1)

    def test_followup_draft_readonly_and_exact_threshold(self):
        self.active()
        self.events([self.event('reply', '', '2026-10-01T12:00:00+00:00')])
        before = (self.case / 'application-events.jsonl').read_bytes()
        result = followups(self.case, now=self.now)
        self.assertEqual(result['due'][0]['quiet_days'], 10)
        self.assertTrue(result['due'][0]['draft_only'])
        self.assertEqual(followups(self.case, 11, self.now)['due'], [])
        self.assertEqual(before, (self.case / 'application-events.jsonl').read_bytes())

    def test_sent_limit_recent_reply_and_unknown_submission(self):
        self.active()
        self.events([self.event('followup', 'sent'), self.event('followup', 'sent', '2026-09-25T12:00:00Z')])
        self.assertEqual(len(followups(self.case, now=self.now)['held']), 1)
        self.events([self.event('reply', '', '2026-10-10T00:00:00Z')])
        self.assertEqual(followups(self.case, now=self.now)['due'], [])
        self.events([self.event('attempt_started', '', attempt_id='pending')])
        self.assertEqual(len(followups(self.case, now=self.now)['held']), 1)

    def test_drafts_do_not_consume_sent_quota(self):
        self.active()
        self.events([self.event('followup', 'draft'), self.event('followup', 'draft')])
        self.assertEqual(followups(self.case, now=self.now)['due'][0]['followups_sent'], 0)

    def test_delayed_confirmation_preserves_sent_followups(self):
        self.active()
        events = [self.event('attempt_started', '', '2026-09-01T00:00:00Z', attempt_id='a'),
                  self.event('attempt_result', 'unknown', '2026-09-02T00:00:00Z', attempt_id='a'),
                  self.event('followup', 'sent', '2026-09-10T00:00:00Z', attempt_id='a'),
                  self.event('followup', 'sent', '2026-09-20T00:00:00Z', attempt_id='a'),
                  self.event('attempt_result', 'submitted', '2026-09-25T00:00:00Z', attempt_id='a')]
        (self.case / 'application-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        result = followups(self.case, now=self.now)
        self.assertEqual(result['due'], [])
        self.assertIn('两次', result['held'][0]['reason'])

    def test_conflicting_legacy_stage_aliases_rejected(self):
        (self.case / 'application-tracker.csv').write_text('job_key,status,application_status\none,submitted,withdrawn\n')
        self.events()
        with self.assertRaisesRegex(ValueError, 'Conflicting stage aliases'):
            followups(self.case, now=self.now)

    def test_invalid_or_future_events_not_used_for_drafts(self):
        self.active()
        self.events([self.event('reply', '', '2026-10-20T00:00:00Z')])
        self.assertEqual(len(followups(self.case, now=self.now)['held']), 1)
        self.events([self.event('reply', '', '2026-10-01')])
        with self.assertRaises(ValueError):
            followups(self.case, now=self.now)

    def test_incomplete_or_missing_submission_evidence_is_held(self):
        self.active()
        isolated = self.event('attempt_result', 'submitted')
        (self.case / 'application-events.jsonl').write_text(json.dumps(isolated))
        self.assertEqual(len(followups(self.case, now=self.now)['held']), 1)
        self.events()
        (self.case / 'receipt.md').unlink()
        result = followups(self.case, now=self.now)
        self.assertEqual(result['due'], [])
        self.assertEqual(len(result['held']), 1)

    def test_duplicate_event_id_does_not_consume_extra_quota(self):
        self.active()
        sent = self.event('followup', 'sent')
        self.events([sent, sent])
        self.assertEqual(followups(self.case, now=self.now)['due'][0]['followups_sent'], 1)


if __name__ == '__main__':
    unittest.main()
