from __future__ import annotations

import json

import pytest
import yaml

from harness.co_math.gating import (
    check_final_render,
    check_goal_approval,
    check_workstream_completion,
    check_workstream_readiness,
)
from harness.co_math.reviews import submit_review
from harness.co_math.workspace import complete_workstream, init_workspace, new_workstream


def write_goals(workspace, goals):
    normalized_goals = []
    for index, goal in enumerate(goals, start=1):
        normalized = dict(goal)
        normalized.setdefault("workstreams", [])
        if normalized.get("status") == "approved":
            normalized.setdefault("approved_by", "user")
            normalized.setdefault("approved_at", "2026-07-11T00:00:00Z")
            normalized.setdefault("approval_id", f"approval-{index}")
        normalized_goals.append(normalized)
    path = workspace / "project" / "GOALS.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "language_policy": {"status": "selected"},
                "research_question": {"status": "approved", "text": "Question"},
                "goals": normalized_goals,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def valid_report() -> str:
    return """# Workstream Report

## Summary
This is a scaffold validation report, not a mathematical result.

## Claims
- Claim C1: The initialization gate has an auditable report.

## Provenance
- Claim C1: harness/tests/test_gating.py

## Uncertainty
- No mathematical claim is being made.

## Failed Explorations
- None for this scaffold-only workstream.
"""


def test_goal_approval_gate_blocks_unapproved_goal(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [{"id": "G1", "title": "Draft goal", "status": "draft"}])

    gate = check_goal_approval(workspace, goal_id="G1")
    assert not gate.passed
    assert "not approved" in gate.issues[0]

    with pytest.raises(ValueError, match="not approved"):
        new_workstream(workspace, goal_id="G1", title="Should not start", kind="proof")


def test_workstream_completion_gate_requires_report_review_and_provenance(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [{"id": "G1", "title": "Approved goal", "status": "approved"}])
    workstream = new_workstream(
        workspace, goal_id="G1", title="Initialization validation", kind="review"
    )

    missing_report = check_workstream_readiness(workspace, workstream.name)
    assert not missing_report.passed
    assert any("report.md" in issue for issue in missing_report.issues)

    (workstream / "report.md").write_text("# Report without provenance", encoding="utf-8")
    no_review = check_workstream_readiness(workspace, workstream.name)
    assert not no_review.passed
    assert any("reviewer approval" in issue for issue in no_review.issues)

    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="logic-review-run-1",
        approved=True,
        severity="info",
        issue_type="logic",
        comment="Looks consistent.",
        review_id="logic_reviewer-initial.json",
    )
    no_provenance = check_workstream_readiness(workspace, workstream.name)
    assert not no_provenance.passed
    assert any("Provenance" in issue for issue in no_provenance.issues)

    (workstream / "report.md").write_text(valid_report(), encoding="utf-8")
    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="logic-review-run-2",
        approved=True,
        severity="info",
        issue_type="logic",
        comment="Updated report is consistent.",
        review_id="logic_reviewer-final.json",
    )
    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="adversarial_reviewer",
        reviewer_run_id="adversarial-review-run-1",
        approved=False,
        severity="blocking",
        issue_type="missing_provenance",
        comment="A blocking issue remains.",
        suggested_fix="Add provenance.",
        review_id="adversarial_reviewer.json",
    )
    blocked = check_workstream_readiness(workspace, workstream.name)
    assert not blocked.passed
    assert any("blocking review" in issue for issue in blocked.issues)

    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="adversarial_reviewer_followup",
        reviewer_run_id="adversarial-review-run-2",
        approved=True,
        severity="info",
        issue_type="missing_provenance",
        comment="The blocking issue is resolved.",
        resolves=["adversarial_reviewer.json"],
        review_id="adversarial_reviewer-followup.json",
    )
    ready = check_workstream_readiness(workspace, workstream.name)
    assert ready.passed
    complete_workstream(workspace, workstream_id=workstream.name)
    passed = check_workstream_completion(workspace, workstream.name)
    assert passed.passed
    assert passed.issues == []


def test_workstream_completion_gate_allows_preserved_resolved_blocking_reviews(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [{"id": "G1", "title": "Approved goal", "status": "approved"}])
    workstream = new_workstream(
        workspace, goal_id="G1", title="Resolved review validation", kind="review"
    )
    (workstream / "report.md").write_text(valid_report(), encoding="utf-8")

    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="logic-review-run-1",
        approved=False,
        severity="blocking",
        issue_type="logic",
        comment="A blocking issue remains.",
        suggested_fix="Clarify the proof dependency.",
        review_id="logic_initial.json",
    )
    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer_followup",
        reviewer_run_id="logic-review-run-2",
        approved=True,
        severity="info",
        issue_type="logic",
        comment="The proof dependency has been clarified.",
        resolves=["logic_initial.json"],
        review_id="logic_followup.json",
    )

    readiness = check_workstream_readiness(workspace, workstream.name)
    assert readiness.passed
    complete_workstream(workspace, workstream_id=workstream.name)
    gate = check_workstream_completion(workspace, workstream.name)

    assert gate.passed
    assert gate.issues == []


def test_final_render_gate_ignores_empty_residue_directories(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    residue = workspace / "workstreams" / "WS-G1-001-stale-empty-dir"
    (residue / "artifacts").mkdir(parents=True)
    (residue / "failures").mkdir()

    gate = check_final_render(workspace)

    assert not gate.passed
    assert gate.issues == ["No reviewed workstream reports are ready to render."]
    assert gate.details["rejected_workstreams"] == {}
