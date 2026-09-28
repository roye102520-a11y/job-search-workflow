"""CLI integration and regression tests; synthetic temporary cases only.

These tests never use a real candidate, account, recruitment website or mailbox.
The fake PDF bytes test attachment handling, not rendering.
"""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "job_data.py"


def timestamp(offset=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()


class FullWorkflowCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="synthetic-job-workflow-")
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name)
        for name in ("jd.md", "resume.pdf", "evidence.md", "receipt.md"):
            (self.case / name).write_text("SYNTHETIC TEST ONLY: " + name, encoding="utf-8")
        self.manifest = {
            "job_key": "synthetic-100", "company": "Synthetic Company",
            "role": "Synthetic Operations", "role_family": "operations",
            "resume_variant": "v1", "location": "Test City",
            "url": "https://recruitment.example.test/jobs/100",
            "aliases": ["https://aggregator.example.test/vacancy/100"],
            "employer_namespace": "synthetic", "requisition_id": "100",
            "jd_path": "jd.md", "resume_path": "resume.pdf",
            "evidence_refs": ["evidence.md#synthetic"], "status": "ready",
            "unresolved_required_fields": [],
            "authorization_scope": "Synthetic test only; no external authorization",
            "channel": "web",
            "recipient_or_endpoint": "https://recruitment.example.test/jobs/100",
            "artifacts": [{"path": "resume.pdf", "sha256": hashlib.sha256(
                (self.case / "resume.pdf").read_bytes()).hexdigest()}],
        }
        self.manifest_path = self.case / "applications" / self.manifest["job_key"] / "manifest.json"
        self.write_manifest()

    def write_manifest(self):
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def cli(self, command, *args, success=True):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--case", str(self.case), command, *map(str, args)],
            capture_output=True, text=True, timeout=10,
        )
        if success:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        else:
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
        return proc

    def register(self):
        return self.cli("register", "--manifest", self.manifest_path)

    def start(self):
        proc = self.cli("start", "--manifest", self.manifest_path)
        return json.loads(proc.stdout.splitlines()[0])

    def rows(self):
        with (self.case / "application-tracker.csv").open(newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))

    def log(self):
        file = self.case / "application-events.jsonl"
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def event(self, action="attempt_result", result="submitted", attempt=None, event_id=None):
        event = {
            "event_id": event_id or "event-" + str(len(self.log())),
            "job_key": self.manifest["job_key"], "timestamp": timestamp(),
            "action": action, "source": "tool_observation", "evidence_path": "receipt.md",
        }
        if attempt:
            event["attempt_id"] = attempt
        if action == "attempt_result":
            event.update(result=result, occurred_at=event["timestamp"])
        return event

    def record(self, event, success=True):
        path = self.case / "event-input.json"
        path.write_text(json.dumps(event), encoding="utf-8")
        return self.cli("record", "--event", path, success=success)

    def tracker_bytes(self):
        return (self.case / "application-tracker.csv").read_bytes()

    def test_entire_cli_success_flow_and_report(self):
        self.cli("validate", "--manifest", self.manifest_path)
        self.register()
        attempt = self.start()
        self.assertEqual(self.rows()[0]["execution_status"], "submission_unknown")
        self.assertEqual(self.rows()[0]["status"], "ready")
        self.record(self.event(attempt=attempt["attempt_id"]))
        for action in ("reply", "assessment", "interview", "offer"):
            self.record(self.event(action=action, attempt=attempt["attempt_id"]))
        self.cli("reconcile")
        self.assertEqual(self.rows()[0]["status"], "offer")
        output = self.case / "report.md"
        self.cli("report", "--as-of", timestamp(2), "--min-age", 0, "--output", output)
        self.assertIn("| operations | v1 | 1 | 1 | 1/1 (100%) | 1/1 (100%) | 1 | 0 |", output.read_text())

    def test_unknown_failed_retry_then_success(self):
        self.register()
        attempt = self.start()
        self.record(self.event(result="unknown", attempt=attempt["attempt_id"]))
        before = self.tracker_bytes()
        self.cli("start", "--manifest", self.manifest_path, success=False)
        self.assertEqual(before, self.tracker_bytes())
        self.record(self.event(result="not_submitted", attempt=attempt["attempt_id"]))
        self.assertEqual(self.rows()[0]["execution_status"], "idle")
        retry = self.start()
        self.assertNotEqual(retry["attempt_id"], attempt["attempt_id"])
        self.record(self.event(attempt=retry["attempt_id"]))
        self.assertEqual(self.rows()[0]["resume_path"], retry["artifacts"][0]["path"])
        self.cli("start", "--manifest", self.manifest_path, success=False)

    def test_reconcile_recovers_stale_tracker_idempotently(self):
        self.register()
        attempt = self.start()
        before_result = self.tracker_bytes()
        self.record(self.event(attempt=attempt["attempt_id"]))
        correct = self.tracker_bytes()
        (self.case / "application-tracker.csv").write_bytes(before_result)
        self.cli("reconcile")
        self.assertEqual(self.tracker_bytes(), correct)
        self.cli("reconcile")
        self.assertEqual(self.tracker_bytes(), correct)

    def test_extra_columns_alias_and_sync_survive_commands(self):
        self.register()
        row = self.rows()[0]
        row.update(application_status="ready", notes="用户备注,保留", sync_status="failed")
        with (self.case / "application-tracker.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        attempt = self.start()
        self.record(self.event(attempt=attempt["attempt_id"]))
        self.register()
        saved = self.rows()[0]
        self.assertEqual(saved["status"], "submitted")
        self.assertEqual(saved["application_status"], "submitted")
        self.assertEqual(saved["notes"], "用户备注,保留")
        self.assertEqual(saved["sync_status"], "failed")

    def test_duplicate_by_alias_or_same_requisition(self):
        self.register()
        original = self.tracker_bytes()
        candidate = dict(self.manifest, job_key="synthetic-duplicate")
        candidate["url"] = self.manifest["aliases"][0] + "?utm_source=test"
        candidate["aliases"] = []
        candidate["requisition_id"] = "different"
        candidate_path = self.case / "candidate.json"
        for url, requisition in ((candidate["url"], "different"),
                                 ("https://different.example.test/jobs/one", "100")):
            candidate.update(url=url, requisition_id=requisition)
            candidate_path.write_text(json.dumps(candidate))
            self.cli("register", "--manifest", candidate_path, success=False)
            self.assertEqual(original, self.tracker_bytes())

    def test_evidence_missing_or_outside_case_fails_without_event(self):
        self.register()
        attempt = self.start()
        before = list(self.log())
        for path in ("missing.md", "../outside.md"):
            event = self.event(attempt=attempt["attempt_id"])
            event["evidence_path"] = path
            self.record(event, success=False)
            self.assertEqual(before, self.log())
        event = self.event(attempt=attempt["attempt_id"])
        event["source"] = "invented"
        self.record(event, success=False)

    def test_final_preflight_failure_does_not_create_tracker_or_attempt(self):
        for key, value in (("unresolved_required_fields", ["contact"]),
                           ("authorization_scope", ""), ("status", "preparing")):
            original = self.manifest[key]
            self.manifest[key] = value
            self.write_manifest()
            self.cli("start", "--manifest", self.manifest_path, success=False)
            self.assertFalse((self.case / "application-tracker.csv").exists())
            self.assertEqual([], self.log())
            self.manifest[key] = original

    def test_idempotent_record_and_conflicting_id(self):
        self.register()
        attempt = self.start()
        event = self.event(attempt=attempt["attempt_id"])
        self.record(event)
        self.record(event)
        self.assertEqual(len(self.log()), 2)
        changed = dict(event, result="not_submitted")
        self.record(changed, success=False)
        self.assertEqual(len(self.log()), 2)

    def test_tampered_frozen_attachment_blocks_submission(self):
        self.register()
        attempt = self.start()
        (self.case / attempt["artifacts"][0]["path"]).write_text("modified synthetic bytes")
        self.record(self.event(attempt=attempt["attempt_id"]), success=False)
        self.assertEqual(self.rows()[0]["execution_status"], "submission_unknown")

    def test_report_does_not_count_drafts_or_outreach(self):
        self.register()
        self.record(self.event(action="outreach"))
        self.record(self.event(action="followup"))
        output = self.case / "report.md"
        self.cli("report", "--output", output)
        self.assertIn("暂无窗口内的已确认投递", output.read_text())
        self.assertEqual(self.rows()[0]["status"], "ready")

    def test_invalid_intervals_and_future_observation_are_rejected(self):
        self.register()
        self.cli("report", "--days", 0, "--output", self.case / "report.md", success=False)
        self.cli("report", "--min-age", -1, "--output", self.case / "report.md", success=False)
        event = self.event(action="reply")
        event["timestamp"] = timestamp(86400)
        self.record(event, success=False)

    def test_conflicting_stage_alias_fails_without_overwriting_csv(self):
        self.register()
        row = self.rows()[0]
        row["application_status"] = "interview"
        with (self.case / "application-tracker.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        before = self.tracker_bytes()
        self.cli("register", "--manifest", self.manifest_path, success=False)
        self.assertEqual(before, self.tracker_bytes())

    def test_lock_contention_fails_cleanly(self):
        import fcntl
        with (self.case / ".job-data.lock").open("a") as file:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.cli("register", "--manifest", self.manifest_path, success=False)
            self.assertFalse((self.case / "application-tracker.csv").exists())
        self.register()

    def test_submission_attribution_survives_draft_edit_during_unknown(self):
        self.register()
        attempt = self.start()
        self.manifest["role_family"] = "product"
        self.manifest["resume_variant"] = "v2"
        self.write_manifest()
        self.register()
        self.record(self.event(attempt=attempt["attempt_id"]))
        saved = self.rows()[0]
        self.assertEqual(saved["role_family"], "operations")
        self.assertEqual(saved["resume_variant"], "v1")
        self.assertEqual(saved["resume_path"], attempt["artifacts"][0]["path"])

    def test_feedback_with_unknown_attempt_is_rejected(self):
        self.register()
        self.start()
        before = self.tracker_bytes()
        event = self.event(action="interview", attempt="nonexistent-attempt")
        self.record(event, success=False)
        self.assertEqual(before, self.tracker_bytes())
        self.assertEqual(len(self.log()), 1)

    def test_feedback_cannot_reference_another_jobs_attempt(self):
        self.register()
        self.start()
        other = dict(self.manifest, job_key="synthetic-200", requisition_id="200",
                     url="https://recruitment.example.test/jobs/200", aliases=[])
        other_path = self.case / "applications" / other["job_key"] / "manifest.json"
        other_path.parent.mkdir(parents=True)
        other_path.write_text(json.dumps(other))
        output = self.cli("start", "--manifest", other_path)
        other_attempt = json.loads(output.stdout.splitlines()[0])["attempt_id"]
        before = self.tracker_bytes()
        self.record(self.event(action="interview", attempt=other_attempt), success=False)
        self.assertEqual(before, self.tracker_bytes())
        self.assertEqual(len(self.log()), 2)

    def test_malformed_json_shapes_fail_cleanly(self):
        for malformed in ([], dict(self.manifest, evidence_refs=[123])):
            with self.subTest(malformed=malformed):
                self.manifest_path.write_text(json.dumps(malformed))
                self.cli("validate", "--manifest", self.manifest_path, success=False)
        self.write_manifest()
        self.register()
        path = self.case / "invalid-event.json"
        for malformed in ([], dict(self.event(action="reply"), timestamp=None)):
            with self.subTest(malformed=malformed):
                path.write_text(json.dumps(malformed))
                self.cli("record", "--event", path, success=False)
        self.assertEqual(self.log(), [])

    def test_duplicate_tracker_keys_block_event_before_append(self):
        self.register()
        row = self.rows()[0]
        with (self.case / "application-tracker.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerows([row, row])
        before = self.tracker_bytes()
        self.record(self.event(action="interview"), success=False)
        self.assertEqual(before, self.tracker_bytes())
        self.assertEqual(self.log(), [])

    def test_symlink_cannot_escape_case_for_attachment(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-outside-") as outside:
            external = Path(outside) / "outside.pdf"
            external.write_text("synthetic outside attachment")
            (self.case / "linked.pdf").symlink_to(external)
            self.manifest["resume_path"] = "linked.pdf"
            self.manifest["artifacts"] = [{"path": "linked.pdf", "sha256": hashlib.sha256(external.read_bytes()).hexdigest()}]
            self.write_manifest()
            self.cli("validate", "--manifest", self.manifest_path, success=False)
            self.assertFalse((self.case / "application-tracker.csv").exists())


if __name__ == "__main__":
    unittest.main()
