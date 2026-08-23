from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from harness.co_math.context import project_snapshot, render_resume_text
from harness.co_math.messages import append_message
from harness.co_math.registry import UserConfig, save_user_config
from harness.co_math.reports import render_final
from harness.co_math.reviews import submit_review
from harness.co_math.scaffold import create_project
from harness.co_math.workspace import (
    approve_goal,
    complete_workstream,
    load_goals,
    new_workstream,
    save_goals,
)


REPORT = """# Context Report

## Provenance
- Source: context test

## Uncertainty
- None

## Failed Explorations
- None
"""


def _create_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    language: str | None = "en",
):
    config_home = tmp_path / "config"
    projects_home = tmp_path / "projects"
    monkeypatch.setenv("CO_MATH_CONFIG_HOME", str(config_home))
    save_user_config(
        UserConfig(projects_home=projects_home, allowed_project_roots=(projects_home,))
    )
    return create_project(
        "Context Project",
        language=language,
        initialize_git=False,
    ).project


def _approve_goal_and_create_workstream(project) -> Path:
    goals = load_goals(project.workspace)
    goals["research_question"] = {"status": "approved", "text": "Question"}
    goals["goals"] = [
        {
            "id": "G1",
            "title": "Context goal",
            "status": "draft",
            "workstreams": [],
        }
    ]
    save_goals(project.workspace, goals)
    approve_goal(
        project.workspace,
        goal_id="G1",
        approved_by="user",
        approval_id="approval-context-001",
    )
    return new_workstream(
        project.workspace,
        goal_id="G1",
        title="Context workstream",
        kind="proof",
        author_run_id="context-author-001",
    )


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_onboarding_snapshot_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch, language=None)
    before = _tree_hashes(project.root)

    snapshot = project_snapshot(project)

    assert snapshot["status"] == "onboarding"
    assert snapshot["project"]["project_id"] == project.manifest.project_id
    assert snapshot["language_policy"]["status"] == "pending_user_choice"
    assert snapshot["next_gate"] == "onboarding"
    assert _tree_hashes(project.root) == before


def test_active_snapshot_aggregates_goal_workstream_and_recent_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch)
    workstream = _approve_goal_and_create_workstream(project)
    for index in range(4):
        append_message(
            project.workspace,
            sender="project_coordinator",
            recipient="user",
            message_type="status",
            content=f"message-{index}",
        )
    before = _tree_hashes(project.root)

    snapshot = project_snapshot(project, recent_limit=2)

    assert snapshot["status"] == "active"
    assert [goal["id"] for goal in snapshot["goals"]["approved"]] == ["G1"]
    assert snapshot["goals"]["draft"] == []
    assert snapshot["workstreams"]["active"] == [
        {
            "id": workstream.name,
            "goal_id": "G1",
            "title": "Context workstream",
            "kind": "proof",
            "status": "active",
            "author_run_id": "context-author-001",
        }
    ]
    assert [message["content"] for message in snapshot["recent_messages"]] == [
        "message-2",
        "message-3",
    ]
    assert snapshot["next_gate"] == "workstream_execution"
    assert _tree_hashes(project.root) == before


def test_snapshot_projects_unresolved_blocking_review_as_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch)
    workstream = _approve_goal_and_create_workstream(project)
    (workstream / "report.md").write_text(REPORT, encoding="utf-8")
    submit_review(
        project.workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="context-review-001",
        approved=False,
        severity="blocking",
        issue_type="logic",
        comment="A proof step is missing.",
        review_id="blocking.json",
    )

    snapshot = project_snapshot(project)

    assert snapshot["workstreams"]["active"] == []
    assert snapshot["workstreams"]["blocked"][0]["id"] == workstream.name
    assert snapshot["next_gate"] == "resolve_blocking_review"


def test_snapshot_projects_completed_work_and_final_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch)
    workstream = _approve_goal_and_create_workstream(project)
    (workstream / "report.md").write_text(REPORT, encoding="utf-8")
    submit_review(
        project.workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="context-review-001",
        approved=True,
        severity="info",
        issue_type="logic",
        comment="Approved.",
        review_id="approved.json",
    )
    complete_workstream(project.workspace, workstream_id=workstream.name)
    render_final(project.workspace)
    (project.workspace / "final" / "working_paper.md").write_text(
        "# Working Paper\n", encoding="utf-8"
    )
    before = _tree_hashes(project.root)

    snapshot = project_snapshot(project)

    assert snapshot["status"] == "final_ready"
    assert snapshot["workstreams"]["complete"][0]["id"] == workstream.name
    assert snapshot["final"] == {
        "generated_draft": True,
        "working_paper": True,
        "render_gate_passed": True,
    }
    assert snapshot["next_gate"] == "explicit_project_completion_unavailable"
    assert _tree_hashes(project.root) == before


def test_snapshot_reports_invalid_workspace_state_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch)
    (project.workspace / "project" / "GOALS.yaml").write_text(
        "goals: [unterminated", encoding="utf-8"
    )
    before = _tree_hashes(project.root)

    snapshot = project_snapshot(project)

    assert snapshot["status"] == "invalid"
    assert snapshot["errors"]
    assert "GOALS" in snapshot["errors"][0] or "parsing" in snapshot["errors"][0]
    assert _tree_hashes(project.root) == before


def test_snapshot_marks_invalid_active_workstream_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch)
    workstream = _approve_goal_and_create_workstream(project)
    status_path = workstream / "status.yaml"
    status = yaml.safe_load(status_path.read_text(encoding="utf-8"))
    status["kind"] = "unknown"
    status_path.write_text(yaml.safe_dump(status, sort_keys=False), encoding="utf-8")

    snapshot = project_snapshot(project)

    assert snapshot["status"] == "invalid"
    assert snapshot["workstreams"]["invalid"][0]["id"] == workstream.name


def test_render_resume_text_contains_identity_status_and_next_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch)
    snapshot = project_snapshot(project)

    text = render_resume_text(snapshot)

    assert "Context Project" in text
    assert project.manifest.project_id in text
    assert str(project.root) in text
    assert "onboarding" in text


def test_snapshot_rejects_negative_recent_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="recent_limit"):
        project_snapshot(project, recent_limit=-1)
