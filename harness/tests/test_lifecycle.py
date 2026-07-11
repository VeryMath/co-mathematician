from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

import harness.co_math.workspace as workspace_module
import harness.co_math.gating as gating_module
import harness.co_math.reports as reports_module
from harness.co_math.gating import (
    check_final_render,
    check_workstream_completion,
    check_workstream_readiness,
)
from harness.co_math.reports import render_final
from harness.co_math.reviews import submit_review
from harness.co_math.workspace import (
    approve_goal,
    init_workspace,
    new_workstream,
    read_yaml,
    refresh_project_status,
)


REPORT = """# Reviewed Report

## Provenance
- Source: lifecycle test

## Uncertainty
- None

## Failed Explorations
- None

REVIEWED_CONTENT
"""


def write_draft_goals(workspace: Path, goal_ids: list[str]) -> None:
    (workspace / "project" / "GOALS.yaml").write_text(
        yaml.safe_dump(
            {
                "language_policy": {
                    "status": "selected",
                    "schema_language": "English",
                    "project_docs_language": "Chinese",
                },
                "research_question": {"status": "approved", "text": "Question"},
                "goals": [
                    {
                        "id": goal_id,
                        "title": f"Goal {goal_id}",
                        "status": "draft",
                        "workstreams": [],
                    }
                    for goal_id in goal_ids
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def create_reviewed_workstream(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_draft_goals(workspace, ["G1"])
    approve_goal(
        workspace,
        goal_id="G1",
        approved_by="user",
        approval_id="approval-G1",
    )
    workstream = new_workstream(
        workspace,
        goal_id="G1",
        title="Lifecycle",
        kind="proof",
        author_run_id="author-run-001",
    )
    (workstream / "report.md").write_text(REPORT, encoding="utf-8")
    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="review-run-001",
        approved=True,
        severity="info",
        issue_type="logic",
        comment="Approved.",
        review_id="logic-review.json",
    )
    return workspace, workstream


def test_approval_event_id_must_be_unique(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_draft_goals(workspace, ["G1", "G2"])
    approve_goal(
        workspace,
        goal_id="G1",
        approved_by="user",
        approval_id="approval-shared",
    )

    with pytest.raises(ValueError, match="approval_id"):
        approve_goal(
            workspace,
            goal_id="G2",
            approved_by="user",
            approval_id="approval-shared",
        )


def test_goal_approval_is_idempotent_but_cannot_be_replaced(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_draft_goals(workspace, ["G1"])
    first = approve_goal(
        workspace,
        goal_id="G1",
        approved_by="user",
        approval_id="approval-G1",
    )

    repeated = approve_goal(
        workspace,
        goal_id="G1",
        approved_by="user",
        approval_id="approval-G1",
    )
    assert repeated == first

    with pytest.raises(ValueError, match="already approved"):
        approve_goal(
            workspace,
            goal_id="G1",
            approved_by="user",
            approval_id="replacement-approval",
        )


def test_submit_review_rejects_unlinked_workstream(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    workstream = workspace / "workstreams" / "WS-G9-001-unlinked"
    (workstream / "reviews").mkdir(parents=True)
    (workstream / "status.yaml").write_text(
        yaml.safe_dump(
            {
                "id": workstream.name,
                "goal_id": "G9",
                "status": "active",
                "author_run_id": "author-run-001",
            }
        ),
        encoding="utf-8",
    )
    (workstream / "report.md").write_text(REPORT, encoding="utf-8")

    with pytest.raises(ValueError, match="linked"):
        submit_review(
            workspace,
            workstream_id=workstream.name,
            reviewer="logic_reviewer",
            reviewer_run_id="review-run-001",
            approved=True,
            severity="info",
            issue_type="logic",
            comment="Invalid target.",
        )


def test_submit_review_rejects_completed_workstream(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)

    with pytest.raises(ValueError, match="active"):
        submit_review(
            workspace,
            workstream_id=workstream.name,
            reviewer="adversarial_reviewer",
            reviewer_run_id="review-run-002",
            approved=True,
            severity="info",
            issue_type="logic",
            comment="Too late.",
        )


def test_complete_workstream_freezes_reviewed_snapshot_and_updates_status(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream), "complete_workstream lifecycle API is required"
    workspace, workstream = create_reviewed_workstream(tmp_path)

    snapshot = complete_workstream(workspace, workstream_id=workstream.name)

    status = read_yaml(workstream / "status.yaml")
    assert status["status"] == "complete"
    assert status["reviewed_snapshot"] == snapshot.relative_to(workstream).as_posix()
    assert len(status["completed_report_sha256"]) == 64
    assert snapshot.read_text(encoding="utf-8") == REPORT
    assert check_workstream_completion(workspace, workstream.name).passed
    project_status = (workspace / "project" / "PROJECT_STATUS.md").read_text()
    assert "active_workstreams: 0" in project_status
    assert "completed_workstreams: 1" in project_status


def test_complete_workstream_rejects_report_change_during_snapshot(
    tmp_path, monkeypatch
):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    original_write = workspace_module.atomic_write_text

    def mutate_report_before_snapshot_write(path, text):
        target = Path(path)
        if target.parent.name == "reviewed" and target.name.startswith("report-"):
            (workstream / "report.md").write_text(
                REPORT.replace("REVIEWED_CONTENT", "CHANGED_DURING_COMPLETION"),
                encoding="utf-8",
            )
        return original_write(path, text)

    monkeypatch.setattr(workspace_module, "atomic_write_text", mutate_report_before_snapshot_write)

    with pytest.raises(ValueError, match="changed during completion"):
        complete_workstream(workspace, workstream_id=workstream.name)

    status = read_yaml(workstream / "status.yaml")
    assert status["status"] == "active"


def test_complete_workstream_rechecks_readiness_after_capture(tmp_path, monkeypatch):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    original_readiness = gating_module.check_workstream_readiness
    calls = 0

    def mutate_after_first_readiness(root, workstream_id):
        nonlocal calls
        calls += 1
        result = original_readiness(root, workstream_id)
        if calls == 1:
            (workstream / "report.md").write_text(
                REPORT.replace("REVIEWED_CONTENT", "CHANGED_AFTER_READINESS"),
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(
        gating_module,
        "check_workstream_readiness",
        mutate_after_first_readiness,
    )

    with pytest.raises(ValueError, match="sha256|reviewer approval"):
        complete_workstream(workspace, workstream_id=workstream.name)

    assert calls == 2
    assert read_yaml(workstream / "status.yaml")["status"] == "active"


def test_render_final_uses_snapshot_without_overwriting_synthesized_paper(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream), "complete_workstream lifecycle API is required"
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    (workstream / "report.md").write_text(
        REPORT.replace("REVIEWED_CONTENT", "UNREVIEWED_REPLACEMENT"),
        encoding="utf-8",
    )
    synthesized = workspace / "final" / "working_paper.md"
    synthesized.write_text("SYNTHESIZED_PAPER\n", encoding="utf-8")

    generated = render_final(workspace)

    assert generated == workspace / "final" / "generated_draft.md"
    assert "REVIEWED_CONTENT" in generated.read_text(encoding="utf-8")
    assert "UNREVIEWED_REPLACEMENT" not in generated.read_text(encoding="utf-8")
    assert synthesized.read_text(encoding="utf-8") == "SYNTHESIZED_PAPER\n"


def test_render_final_uses_gate_snapshot_descriptor_not_mutated_status(
    tmp_path, monkeypatch
):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    outside = tmp_path / "outside.md"
    outside.write_text("UNREVIEWED_OUTSIDE\n", encoding="utf-8")
    original_gate = reports_module.check_final_render

    def mutate_status_after_gate(root):
        result = original_gate(root)
        status = read_yaml(workstream / "status.yaml")
        status["reviewed_snapshot"] = "../../outside.md"
        workspace_module.write_yaml(workstream / "status.yaml", status)
        return result

    monkeypatch.setattr(reports_module, "check_final_render", mutate_status_after_gate)

    generated = render_final(workspace)

    assert "REVIEWED_CONTENT" in generated.read_text(encoding="utf-8")
    assert "UNREVIEWED_OUTSIDE" not in generated.read_text(encoding="utf-8")


def test_render_final_rechecks_snapshot_digest_after_gate(tmp_path, monkeypatch):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    snapshot = complete_workstream(workspace, workstream_id=workstream.name)
    original_gate = reports_module.check_final_render

    def mutate_snapshot_after_gate(root):
        result = original_gate(root)
        snapshot.write_text("UNREVIEWED_REPLACEMENT\n", encoding="utf-8")
        return result

    monkeypatch.setattr(reports_module, "check_final_render", mutate_snapshot_after_gate)

    with pytest.raises(ValueError, match="digest"):
        render_final(workspace)


def test_submit_review_rejects_symlinked_reviews_directory(tmp_path):
    workspace, workstream = create_reviewed_workstream(tmp_path)
    for path in (workstream / "reviews").iterdir():
        path.unlink()
    (workstream / "reviews").rmdir()
    external = tmp_path / "external-reviews"
    external.mkdir()
    (workstream / "reviews").symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        submit_review(
            workspace,
            workstream_id=workstream.name,
            reviewer="adversarial_reviewer",
            reviewer_run_id="review-run-002",
            approved=True,
            severity="info",
            issue_type="logic",
            comment="Must stay contained.",
        )

    assert list(external.iterdir()) == []


def test_submit_review_rejects_symlinked_report(tmp_path):
    workspace, workstream = create_reviewed_workstream(tmp_path)
    (workstream / "report.md").unlink()
    external_report = tmp_path / "external-report.md"
    external_report.write_text(REPORT, encoding="utf-8")
    (workstream / "report.md").symlink_to(external_report)

    with pytest.raises(ValueError, match="report.md.*symlink"):
        submit_review(
            workspace,
            workstream_id=workstream.name,
            reviewer="adversarial_reviewer",
            reviewer_run_id="review-run-002",
            approved=True,
            severity="info",
            issue_type="logic",
            comment="Must not review an external report.",
        )


def test_submit_review_rejects_symlinked_status_file(tmp_path):
    workspace, workstream = create_reviewed_workstream(tmp_path)
    status = (workstream / "status.yaml").read_text(encoding="utf-8")
    (workstream / "status.yaml").unlink()
    external_status = tmp_path / "external-status.yaml"
    external_status.write_text(status, encoding="utf-8")
    (workstream / "status.yaml").symlink_to(external_status)

    with pytest.raises(ValueError, match="symlink"):
        submit_review(
            workspace,
            workstream_id=workstream.name,
            reviewer="adversarial_reviewer",
            reviewer_run_id="review-run-002",
            approved=True,
            severity="info",
            issue_type="logic",
            comment="Must not trust external status.",
        )


def test_complete_workstream_rejects_symlinked_reviewed_directory(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    (workstream / "reviewed").rmdir()
    external = tmp_path / "external-reviewed"
    external.mkdir()
    (workstream / "reviewed").symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        complete_workstream(workspace, workstream_id=workstream.name)

    assert list(external.iterdir()) == []


def test_render_final_rejects_symlinked_final_directory(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    shutil.rmtree(workspace / "final")
    external = tmp_path / "external-final"
    external.mkdir()
    (workspace / "final").symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        render_final(workspace)

    assert list(external.iterdir()) == []


def test_completion_manifest_detects_review_mutation(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    status = read_yaml(workstream / "status.yaml")
    manifest = workstream / status["completion_manifest"]
    assert manifest.is_file()
    assert len(status["completion_manifest_sha256"]) == 64

    review_path = workstream / "reviews" / "logic-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["comment"] = "MUTATED AFTER COMPLETION"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("digest" in issue.lower() for issue in gate.issues)


def test_completion_manifest_detects_review_set_addition(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    (workstream / "reviews" / "injected.json").write_text("{}\n", encoding="utf-8")

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("review set" in issue.lower() for issue in gate.issues)


def test_completion_manifest_detects_snapshot_mutation(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    snapshot = complete_workstream(workspace, workstream_id=workstream.name)
    snapshot.write_text("MUTATED\n", encoding="utf-8")

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("sha256" in issue.lower() for issue in gate.issues)


def test_completion_manifest_detects_goal_approval_mutation(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    goals = read_yaml(workspace / "project" / "GOALS.yaml")
    goals["goals"][0]["approval_id"] = "replacement-approval"
    workspace_module.write_yaml(workspace / "project" / "GOALS.yaml", goals)

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("goal approval" in issue.lower() for issue in gate.issues)


def test_checked_artifact_digest_blocks_drift_before_completion(tmp_path):
    workspace, workstream = create_reviewed_workstream(tmp_path)
    for path in (workstream / "reviews").iterdir():
        path.unlink()
    artifact = workstream / "artifacts" / "evidence.txt"
    artifact.write_text("reviewed evidence\n", encoding="utf-8")
    _, review = submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="review-run-002",
        approved=True,
        severity="info",
        issue_type="code",
        comment="Artifact checked.",
        checked_artifacts=["artifacts/evidence.txt"],
        review_id="artifact-review.json",
    )
    assert review["checked_artifacts"][0]["path"] == "artifacts/evidence.txt"
    assert len(review["checked_artifacts"][0]["sha256"]) == 64
    artifact.write_text("changed after review\n", encoding="utf-8")

    gate = check_workstream_readiness(workspace, workstream.name)

    assert not gate.passed
    assert any("checked artifact digest" in issue.lower() for issue in gate.issues)


def test_checked_artifact_digest_blocks_drift_after_completion(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    for path in (workstream / "reviews").iterdir():
        path.unlink()
    artifact = workstream / "artifacts" / "evidence.txt"
    artifact.write_text("reviewed evidence\n", encoding="utf-8")
    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="review-run-002",
        approved=True,
        severity="info",
        issue_type="code",
        comment="Artifact checked.",
        checked_artifacts=["artifacts/evidence.txt"],
        review_id="artifact-review.json",
    )
    complete_workstream(workspace, workstream_id=workstream.name)
    artifact.write_text("changed after completion\n", encoding="utf-8")

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("checked artifact digest" in issue.lower() for issue in gate.issues)


def test_completion_manifest_prevents_status_only_reopen(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    status = read_yaml(workstream / "status.yaml")
    status["status"] = "active"
    workspace_module.write_yaml(workstream / "status.yaml", status)

    with pytest.raises(ValueError, match="completion bundle"):
        submit_review(
            workspace,
            workstream_id=workstream.name,
            reviewer="adversarial_reviewer",
            reviewer_run_id="review-run-002",
            approved=True,
            severity="info",
            issue_type="logic",
            comment="Must not reopen by editing status only.",
        )


def test_project_status_projection_rejects_status_only_reopen(tmp_path):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    complete_workstream(workspace, workstream_id=workstream.name)
    status = read_yaml(workstream / "status.yaml")
    status["status"] = "active"
    workspace_module.write_yaml(workstream / "status.yaml", status)

    refresh_project_status(workspace)
    project_status = (workspace / "project" / "PROJECT_STATUS.md").read_text()

    assert "active_workstreams: 0" in project_status
    assert "completed_workstreams: 0" in project_status
    assert "invalid_workstreams: 1" in project_status


def test_complete_workstream_idempotent_retry_repairs_project_status(
    tmp_path, monkeypatch
):
    complete_workstream = getattr(workspace_module, "complete_workstream", None)
    assert callable(complete_workstream)
    workspace, workstream = create_reviewed_workstream(tmp_path)
    original_refresh = workspace_module._refresh_project_status_unlocked

    def fail_projection(_root):
        raise OSError("projection failed")

    monkeypatch.setattr(
        workspace_module,
        "_refresh_project_status_unlocked",
        fail_projection,
    )
    with pytest.raises(OSError, match="projection failed"):
        complete_workstream(workspace, workstream_id=workstream.name)
    monkeypatch.setattr(
        workspace_module,
        "_refresh_project_status_unlocked",
        original_refresh,
    )

    complete_workstream(workspace, workstream_id=workstream.name)

    project_status = (workspace / "project" / "PROJECT_STATUS.md").read_text()
    assert "active_workstreams: 0" in project_status
    assert "completed_workstreams: 1" in project_status


def test_malformed_naive_review_time_does_not_block_new_review(tmp_path):
    workspace, workstream = create_reviewed_workstream(tmp_path)
    review_path = workstream / "reviews" / "logic-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewed_at"] = "2026-07-11T00:00:00"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    output, _ = submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="adversarial_reviewer",
        reviewer_run_id="review-run-002",
        approved=True,
        severity="info",
        issue_type="logic",
        comment="New valid review.",
        review_id="new-review.json",
    )

    assert output.is_file()
