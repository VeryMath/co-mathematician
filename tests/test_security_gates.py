from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from harness.co_math.gating import check_workstream_completion
from harness.co_math.messages import append_message
from harness.co_math.reports import render_final
from harness.co_math.workspace import write_yaml


REPORT = """# Report

## Provenance
Evidence.

## Uncertainty
None.

## Failed Explorations
None.
"""


class SecurityGateTests(unittest.TestCase):
    def make_workstream(self, root: Path, *, status: str = "complete") -> Path:
        workstream = root / "workstreams" / "WS-G1-001-test"
        (workstream / "reviews").mkdir(parents=True)
        write_yaml(
            workstream / "status.yaml",
            {"status": status, "coordinator": "author", "title": "Test"},
        )
        report = workstream / "report.md"
        report.write_text(REPORT, encoding="utf-8")
        digest = hashlib.sha256(report.read_bytes()).hexdigest()
        review = {
            "approved": True,
            "severity": "none",
            "issue_type": "logic",
            "reviewer": "reviewer",
            "comment": "Approved.",
            "suggested_fix": "No change.",
            "report_sha256": digest,
        }
        (workstream / "reviews" / "approval.json").write_text(
            json.dumps(review), encoding="utf-8"
        )
        return workstream

    def test_completion_requires_complete_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_workstream(root, status="active")
            gate = check_workstream_completion(root)
            self.assertFalse(gate.passed)
            self.assertTrue(any("not marked complete" in issue for issue in gate.issues))

    def test_reviewer_must_differ_from_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workstream = self.make_workstream(root)
            review_path = workstream / "reviews" / "approval.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["reviewer"] = "author"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            gate = check_workstream_completion(root)
            self.assertFalse(gate.passed)
            self.assertTrue(any("independent reviewer" in issue for issue in gate.issues))

    def test_later_review_can_resolve_named_blocking_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workstream = self.make_workstream(root)
            digest = hashlib.sha256((workstream / "report.md").read_bytes()).hexdigest()
            blocking = {
                "approved": False,
                "severity": "blocking",
                "issue_type": "logic",
                "reviewer": "reviewer-1",
                "comment": "Fix this.",
                "suggested_fix": "Add evidence.",
                "report_sha256": digest,
            }
            resolution = {
                "approved": True,
                "severity": "none",
                "issue_type": "logic",
                "reviewer": "reviewer-2",
                "comment": "Resolved.",
                "suggested_fix": "No change.",
                "report_sha256": digest,
                "resolves": ["blocking.json"],
            }
            reviews = workstream / "reviews"
            (reviews / "blocking.json").write_text(json.dumps(blocking), encoding="utf-8")
            (reviews / "resolution.json").write_text(json.dumps(resolution), encoding="utf-8")
            self.assertTrue(check_workstream_completion(root).passed)

    def test_messages_append_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            victim = root / "victim"
            victim.write_text("unchanged", encoding="utf-8")
            (project / "messages.jsonl").symlink_to(victim)
            with self.assertRaises(ValueError):
                append_message(
                    root,
                    sender="a",
                    recipient="b",
                    message_type="status",
                    content="test",
                )
            self.assertEqual(victim.read_text(encoding="utf-8"), "unchanged")

    def test_final_render_rejects_symlink_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_workstream(root)
            final = root / "final"
            final.mkdir()
            victim = root / "victim"
            victim.write_text("unchanged", encoding="utf-8")
            (final / "working_paper.md").symlink_to(victim)
            with self.assertRaises(ValueError):
                render_final(root)
            self.assertEqual(victim.read_text(encoding="utf-8"), "unchanged")


if __name__ == "__main__":
    unittest.main()