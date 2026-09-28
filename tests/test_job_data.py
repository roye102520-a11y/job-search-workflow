import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('job_data', Path(__file__).parents[1] / 'scripts/job_data.py')
j = importlib.util.module_from_spec(spec); spec.loader.exec_module(j)

class JobDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        clock = patch.object(j, 'now', return_value='2026-09-01T08:00:00+00:00')
        clock.start(); self.addCleanup(clock.stop)
        self.root = Path(self.tmp.name)
        for name in ['jd.md','resume.pdf','evidence.md','receipt.md']:
            (self.root/name).write_text('synthetic fixture '+name)
        self.m = dict(job_key='test-123', company='Test', role='Analyst', role_family='operations',
            resume_variant='v1', url='https://example.test/job?id=123', jd_path='jd.md', resume_path='resume.pdf',
            evidence_refs=['evidence.md#entry'], status='ready', unresolved_required_fields=[],
            authorization_scope='Synthetic test authorization, never real', channel='web',
            recipient_or_endpoint='https://example.test/job?id=123',
            artifacts=[dict(path='resume.pdf',sha256=j.digest(self.root/'resume.pdf'))])
        folder=self.root/'applications/test-123'; folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps(self.m))
        j.upsert(self.root,self.m)
    def event(self, attempt, result='submitted', event_id='result-1'):
        return dict(event_id=event_id,attempt_id=attempt,job_key='test-123',timestamp='2026-09-01T10:00:00+00:00',
            occurred_at='2026-09-01T09:00:00+00:00',action='attempt_result',result=result,
            source='user_report',evidence_path='receipt.md')
    def test_hash_tampering(self):
        (self.root/'resume.pdf').write_text('changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'): j.validate(self.root,self.m)
    def test_missing_and_outside_paths(self):
        for path in ['missing.pdf','../outside.pdf']:
            with self.assertRaises(ValueError): j.local(self.root,path)
    def test_tracking_params_and_job_identity(self):
        self.assertEqual(j.canonical(self.m['url']+'&utm_source=x'), self.m['url'])
        self.assertNotEqual(j.canonical(self.m['url']),j.canonical('https://example.test/job?id=124'))
        other=dict(self.m,job_key='other',url=self.m['url']+'&utm_source=x')
        with self.assertRaisesRegex(ValueError,'Duplicate'): j.duplicate(self.root,other)
    def test_same_title_different_job_allowed(self):
        j.duplicate(self.root,dict(self.m,job_key='other',url='https://example.test/job?id=124'))

    def test_key_collision_with_different_requisition(self):
        old=dict(self.m,employer_namespace='test',requisition_id='123')
        (self.root/'applications/test-123/manifest.json').write_text(json.dumps(old))
        with self.assertRaisesRegex(ValueError,'conflicting requisition'):
            j.duplicate(self.root,dict(old,requisition_id='124'))
    def test_unresolved_blocks_start(self):
        self.m['unresolved_required_fields']=['work authorization']
        with self.assertRaisesRegex(ValueError,'Unresolved'): j.start(self.root,self.m)
    def test_crash_after_start_blocks_retry_and_snapshot_survives(self):
        result=j.start(self.root,self.m)
        (self.root/'resume.pdf').write_text('new draft')
        self.assertTrue((self.root/result['artifacts'][0]['path']).read_text().startswith('synthetic'))
        self.m['artifacts'][0]['sha256']=j.digest(self.root/'resume.pdf')
        with self.assertRaisesRegex(ValueError,'unresolved'): j.start(self.root,self.m)
        j.reconcile(self.root)
        self.assertEqual(j.rows(self.root)[0][0]['execution_status'],'submission_unknown')
    def test_unknown_then_success_and_idempotent_record(self):
        result=j.start(self.root,self.m)
        j.record(self.root,self.event(result['attempt_id'],'unknown','unknown-1'))
        event=self.event(result['attempt_id'])
        j.record(self.root,event); j.record(self.root,event); j.reconcile(self.root)
        self.assertEqual(len(j.events(self.root)),3)
        self.assertEqual(j.rows(self.root)[0][0]['status'],'submitted')
        with self.assertRaises(ValueError): j.start(self.root,self.m)
    def test_evidence_required_and_draft_rejected(self):
        attempt=j.start(self.root,self.m)['attempt_id']
        event=self.event(attempt,'draft')
        with self.assertRaises(ValueError): j.record(self.root,event)
        event=self.event(attempt); event['evidence_path']='missing.md'
        with self.assertRaises(ValueError): j.record(self.root,event)
    def test_preserve_extra_columns_and_sync(self):
        data,fields=j.rows(self.root); fields+=['custom']
        data[0].update(custom='keep',sync_status='failed')
        j.save_rows(self.root,data,fields)
        attempt=j.start(self.root,self.m)['attempt_id']; j.record(self.root,self.event(attempt)); j.reconcile(self.root)
        row=j.rows(self.root)[0][0]
        self.assertEqual((row['custom'],row['sync_status'],row['status']),('keep','failed','submitted'))
    def test_empty_report_does_not_count_prepared(self):
        self.assertIn('暂无',j.report(self.root,'2026-10-01T00:00:00+00:00',90,14))
    def test_report_uses_submission_version_and_past_interview(self):
        attempt=j.start(self.root,self.m)['attempt_id']
        # Fix fixture's observed start time so as-of report is deterministic.
        log=j.events(self.root); log[0]['timestamp']='2026-09-01T08:00:00+00:00'
        (self.root/'application-events.jsonl').write_text(json.dumps(log[0])+'\n')
        j.record(self.root,self.event(attempt))
        for action,date in [('interview','2026-09-05'),('rejected','2026-09-06')]:
            j.record(self.root,dict(event_id=action,job_key='test-123',timestamp=date+'T00:00:00+00:00',action=action,source='user_report',evidence_path='receipt.md'))
        self.m['resume_variant']='v2'; j.reconcile(self.root); j.upsert(self.root,self.m)
        report=j.report(self.root,'2026-10-01T00:00:00+00:00',90,14)
        self.assertIn('| operations | v1 | 1 | 1 | 1/1 (100%) | 1/1 (100%)',report)
        self.assertNotIn('| v2 |',report)
    def test_unknown_submission_date_is_not_now(self):
        attempt=j.start(self.root,self.m)['attempt_id']; event=self.event(attempt); event.pop('occurred_at')
        j.record(self.root,event); j.reconcile(self.root)
        self.assertEqual(j.rows(self.root)[0][0]['submitted_at'],'')
    def test_consultation_not_submission(self):
        j.record(self.root,dict(event_id='outreach',job_key='test-123',timestamp='2026-09-01T00:00:00+00:00',action='outreach',source='user_report',evidence_path='receipt.md'))
        j.reconcile(self.root)
        self.assertEqual(j.rows(self.root)[0][0]['status'],'ready')

    def test_frozen_attachment_tamper_blocks_success_record(self):
        result=j.start(self.root,self.m)
        (self.root/result['artifacts'][0]['path']).write_text('tampered')
        with self.assertRaisesRegex(ValueError,'Frozen attachment'):
            j.record(self.root,self.event(result['attempt_id']))

    def test_out_of_order_observation_rejected(self):
        attempt=j.start(self.root,self.m)['attempt_id']
        event=self.event(attempt); event['timestamp']='2026-08-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'Observation time'):
            j.record(self.root,event)

    def test_legacy_results_not_silently_ignored(self):
        data,fields=j.rows(self.root); data[0]['status']='interview'; j.save_rows(self.root,data,fields)
        report=j.report(self.root,'2026-10-01T00:00:00+00:00',90,14)
        self.assertIn('未纳入本报告：1 个岗位',report)

class RecoveryRegressionTests(unittest.TestCase):
    setUp = JobDataTests.setUp
    event = JobDataTests.event
    def test_cli_closed_job_cannot_reopen(self):
        import subprocess,sys
        data,fields=j.rows(self.root); data[0]['status']='closed'; j.save_rows(self.root,data,fields)
        before=(self.root/'application-tracker.csv').read_bytes()
        result=subprocess.run([sys.executable,str(Path(j.__file__)), '--case',str(self.root),'start','--manifest',str(self.root/'applications/test-123/manifest.json')],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(before,(self.root/'application-tracker.csv').read_bytes())
        self.assertEqual(j.events(self.root),[])
    def test_late_confirmation_preserves_stage_and_interview_count(self):
        attempt=j.start(self.root,self.m)['attempt_id']
        unknown=self.event(attempt,'unknown','unknown'); j.record(self.root,unknown)
        j.record(self.root,dict(event_id='interview',job_key='test-123',attempt_id=attempt,timestamp='2026-09-05T00:00:00+00:00',action='interview',source='user_report',evidence_path='receipt.md'))
        j.reconcile(self.root)
        success=self.event(attempt); success['timestamp']='2026-09-10T00:00:00+00:00'
        j.record(self.root,success); j.reconcile(self.root)
        self.assertEqual(j.rows(self.root)[0][0]['status'],'interview')
        report=j.report(self.root,'2026-10-01T00:00:00+00:00',90,14)
        self.assertIn('| operations | v1 | 1 | 1 | 1/1 (100%) | 1/1 (100%)',report)
    def test_tracker_references_submitted_snapshot(self):
        result=j.start(self.root,self.m); j.record(self.root,self.event(result['attempt_id'])); j.reconcile(self.root)
        self.assertEqual(j.rows(self.root)[0][0]['resume_path'],result['artifacts'][0]['path'])

if __name__=='__main__': unittest.main()
