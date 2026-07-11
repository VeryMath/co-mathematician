from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

import harness.co_math.workspace as workspace_module
from harness.co_math.gating import (
    check_goal_approval,
    check_workstream_completion,
    check_workstream_readiness,
)
from harness.co_math.reports import render_final
from harness.co_math.workspace import init_workspace, new_workstream, read_yaml, write_yaml


def approved_goal(goal_id: str, *, workstreams: list[str] | None = None) -> dict:
    return {
        "id": goal_id,
        "title": "Approved goal",
        "status": "approved",
        "approved_by": "user",
        "approved_at": "2026-07-11T00:00:00Z",
        "approval_id": "approval-001",
        "workstreams": workstreams or [],
    }


def write_goals(workspace, goals: list[dict]) -> None:
    (workspace / "project" / "GOALS.yaml").write_text(
        yaml.safe_dump(
            {
                "language_policy": {
                    "status": "selected",
                    "schema_language": "English",
                    "project_docs_language": "Chinese",
                },
                "research_question": {"status": "approved", "text": "Test question"},
                "goals": goals,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def valid_report(marker: str = "reviewed") -> str:
    return f"""# Report

## Provenance
- Source: test

## Uncertainty
- None

## Failed Explorations
- None

{marker}
"""


def valid_review(report_text: str, **overrides) -> dict:
    payload = {
        "approved": True,
        "severity": "info",
        "issue_type": "logic",
        "reviewer": "logic_reviewer",
        "reviewer_run_id": "review-run-001",
        "reviewed_at": "2026-07-11T00:01:00Z",
        "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
        "comment": "Approved.",
        "suggested_fix": "",
        "resolves": [],
        "checked_artifacts": [],
    }
    payload.update(overrides)
    return payload


def prepare_workstream(tmp_path, *, title: str = "Integrity"):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [approved_goal("G1")])
    workstream = new_workstream(
        workspace,
        goal_id="G1",
        title=title,
        kind="proof",
    )
    status = read_yaml(workstream / "status.yaml")
    status["author_run_id"] = "author-run-001"
    write_yaml(workstream / "status.yaml", status)
    return workspace, workstream


def write_review(workstream, name: str, payload: dict) -> None:
    (workstream / "reviews" / name).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def test_goal_gate_requires_recorded_user_approval(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(
        workspace,
        [{"id": "G1", "title": "Forged", "status": "approved", "workstreams": []}],
    )

    gate = check_goal_approval(workspace, "G1")

    assert not gate.passed
    assert any("approval" in issue.lower() for issue in gate.issues)


def test_unlinked_workstream_cannot_pass_gate_or_enter_generated_draft(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    workstream = workspace / "workstreams" / "WS-G9-001-injected"
    (workstream / "reviews").mkdir(parents=True)
    report = valid_report("INJECTED_SENTINEL")
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "fake.json", valid_review(report))

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    with pytest.raises(ValueError, match="No reviewed workstream"):
        render_final(workspace)


def test_review_must_match_schema(tmp_path):
    workspace, workstream = prepare_workstream(tmp_path)
    report = valid_report()
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "invalid.json", {"approved": True, "reviewer": "alias"})

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("schema" in issue.lower() for issue in gate.issues)


def test_review_is_invalid_after_report_changes(tmp_path):
    workspace, workstream = prepare_workstream(tmp_path)
    reviewed = valid_report("ORIGINAL")
    (workstream / "report.md").write_text(reviewed, encoding="utf-8")
    write_review(workstream, "approval.json", valid_review(reviewed))
    (workstream / "report.md").write_text(
        valid_report("REPLACED_AFTER_APPROVAL"),
        encoding="utf-8",
    )

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("sha256" in issue.lower() for issue in gate.issues)


def test_unapproved_review_cannot_resolve_blocker(tmp_path):
    workspace, workstream = prepare_workstream(tmp_path)
    report = valid_report()
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "approval.json", valid_review(report))
    write_review(
        workstream,
        "blocking.json",
        valid_review(
            report,
            approved=False,
            severity="blocking",
            reviewer="adversarial_reviewer",
            reviewer_run_id="review-run-002",
        ),
    )
    write_review(
        workstream,
        "resolver.json",
        valid_review(
            report,
            approved=False,
            reviewer="anonymous",
            reviewer_run_id="review-run-003",
            resolves=["blocking.json"],
        ),
    )

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("blocking review" in issue.lower() for issue in gate.issues)


def test_completion_gate_requires_completed_lifecycle_state(tmp_path):
    workspace, workstream = prepare_workstream(tmp_path)
    report = valid_report()
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "approval.json", valid_review(report))

    gate = check_workstream_completion(workspace, workstream.name)

    assert not gate.passed
    assert any("status" in issue.lower() for issue in gate.issues)


def test_readiness_requires_active_lifecycle_state(tmp_path):
    from harness.co_math.gating import check_workstream_readiness

    workspace, workstream = prepare_workstream(tmp_path)
    report = valid_report()
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "approval.json", valid_review(report))
    status = read_yaml(workstream / "status.yaml")
    status["status"] = "paused"
    write_yaml(workstream / "status.yaml", status)

    gate = check_workstream_readiness(workspace, workstream.name)

    assert not gate.passed
    assert any("active" in issue.lower() for issue in gate.issues)


def test_goal_id_cannot_escape_workstreams_directory(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    goal_id = "../../../escaped"
    write_goals(workspace, [approved_goal(goal_id)])

    with pytest.raises(ValueError, match="goal id"):
        new_workstream(workspace, goal_id=goal_id, title="Traversal", kind="proof")

    assert not (workspace / "escaped-001-traversal").exists()


def test_workstreams_root_must_not_be_a_symlink(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [approved_goal("G1")])
    shutil.rmtree(workspace / "workstreams")
    outside = tmp_path / "outside-workstreams"
    outside.mkdir()
    (workspace / "workstreams").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        new_workstream(workspace, goal_id="G1", title="Escape", kind="proof")

    assert list(outside.iterdir()) == []


def test_workspace_lock_rejects_symlinked_project_root(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    shutil.rmtree(workspace / "project")
    outside = tmp_path / "outside-project"
    outside.mkdir()
    (workspace / "project").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        new_workstream(workspace, goal_id="G1", title="Escape", kind="proof")

    assert list(outside.iterdir()) == []


def test_goal_registry_file_must_not_be_a_symlink(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    outside = tmp_path / "outside-goals.yaml"
    outside.write_text(
        yaml.safe_dump(
            {
                "language_policy": {"status": "selected"},
                "research_question": {"status": "approved"},
                "goals": [approved_goal("G1")],
            }
        ),
        encoding="utf-8",
    )
    (workspace / "project" / "GOALS.yaml").unlink()
    (workspace / "project" / "GOALS.yaml").symlink_to(outside)

    gate = check_goal_approval(workspace, "G1")

    assert not gate.passed
    assert any("symlink" in issue.lower() for issue in gate.issues)
    with pytest.raises(ValueError, match="symlink"):
        new_workstream(workspace, goal_id="G1", title="External", kind="proof")


def test_workstream_creation_rolls_back_when_goal_update_fails(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [approved_goal("G1")])

    def fail_save(*args, **kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(workspace_module, "save_goals", fail_save)

    with pytest.raises(OSError, match="simulated write failure"):
        new_workstream(workspace, goal_id="G1", title="Rollback", kind="proof")

    assert list((workspace / "workstreams").iterdir()) == []


def test_workstream_number_uses_max_existing_sequence(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [approved_goal("G1")])
    (workspace / "workstreams" / "WS-G1-001-first").mkdir()
    (workspace / "workstreams" / "WS-G1-003-third").mkdir()

    created = new_workstream(workspace, goal_id="G1", title="Fourth", kind="proof")

    assert created.name == "WS-G1-004-fourth"


def test_workspace_lock_serializes_threads(tmp_path):
    lock = getattr(workspace_module, "workspace_lock", None)
    assert callable(lock), "workspace_lock must be part of the workspace write boundary"

    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    state_lock = threading.Lock()
    active = 0
    max_active = 0

    def enter_critical_section():
        nonlocal active, max_active
        with lock(workspace):
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with state_lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: enter_critical_section(), range(2)))

    assert max_active == 1


def test_new_workstream_uses_workspace_lock(tmp_path, monkeypatch):
    existing_lock = getattr(workspace_module, "workspace_lock", None)
    assert callable(existing_lock), "workspace_lock must exist before it can be enforced"

    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [approved_goal("G1")])
    entered = []

    @contextmanager
    def spy_lock(root):
        entered.append(root)
        yield

    monkeypatch.setattr(workspace_module, "workspace_lock", spy_lock)

    new_workstream(workspace, goal_id="G1", title="Locked", kind="proof")

    assert entered == [workspace]


def test_concurrent_workstream_creation_preserves_all_goal_references(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [approved_goal("G1")])

    def create(title: str):
        return new_workstream(
            workspace,
            goal_id="G1",
            title=title,
            kind="proof",
            author_run_id=f"author-{title.lower()}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(pool.map(create, ["Alpha", "Beta"]))

    goals = read_yaml(workspace / "project" / "GOALS.yaml")
    references = goals["goals"][0]["workstreams"]
    assert set(references) == {path.name for path in created}


def test_completion_gate_rejects_absolute_workstream_path(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    outside = tmp_path / "outside"
    outside.mkdir()

    gate = check_workstream_completion(workspace, str(outside))

    assert not gate.passed
    assert any("invalid workstream id" in issue.lower() for issue in gate.issues)


def test_final_gate_ignores_symlinked_external_workstream(tmp_path):
    from harness.co_math.gating import check_final_render

    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "workstreams" / "WS-G1-001-linked").symlink_to(
        outside,
        target_is_directory=True,
    )

    gate = check_final_render(workspace)

    assert not gate.passed
    assert gate.details["approved_workstreams"] == []
    assert gate.details["rejected_workstreams"] == {}


def test_duplicate_goal_ids_fail_closed(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    first = approved_goal("G1")
    second = approved_goal("G1")
    second["approval_id"] = "approval-002"
    write_goals(workspace, [first, second])

    gate = check_goal_approval(workspace, "G1")

    assert not gate.passed
    assert any("duplicate" in issue.lower() for issue in gate.issues)
    with pytest.raises(ValueError, match="duplicate"):
        new_workstream(workspace, goal_id="G1", title="Ambiguous", kind="proof")


def test_workstream_directory_goal_must_match_status_goal(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace, [approved_goal("G1"), approved_goal("G2")])
    workstream = new_workstream(
        workspace,
        goal_id="G1",
        title="Goal mismatch",
        kind="proof",
        author_run_id="author-run-001",
    )
    goals = read_yaml(workspace / "project" / "GOALS.yaml")
    goals["goals"][0]["workstreams"] = []
    goals["goals"][1]["workstreams"] = [workstream.name]
    write_yaml(workspace / "project" / "GOALS.yaml", goals)
    status = read_yaml(workstream / "status.yaml")
    status["goal_id"] = "G2"
    write_yaml(workstream / "status.yaml", status)
    report = valid_report()
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "approval.json", valid_review(report))

    gate = check_workstream_readiness(workspace, workstream.name)

    assert not gate.passed
    assert any("workstream id" in issue.lower() for issue in gate.issues)


def test_workstream_status_schema_is_enforced(tmp_path):
    workspace, workstream = prepare_workstream(tmp_path)
    status = read_yaml(workstream / "status.yaml")
    status["schema_version"] = 0
    status["kind"] = "unknown"
    write_yaml(workstream / "status.yaml", status)
    report = valid_report()
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "approval.json", valid_review(report))

    gate = check_workstream_readiness(workspace, workstream.name)

    assert not gate.passed
    assert any("status schema" in issue.lower() for issue in gate.issues)


def test_resolver_must_be_later_than_blocking_review(tmp_path):
    workspace, workstream = prepare_workstream(tmp_path)
    report = valid_report()
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(
        workstream,
        "resolver.json",
        valid_review(
            report,
            reviewed_at="2026-07-11T00:01:00Z",
            resolves=["blocking.json"],
        ),
    )
    write_review(
        workstream,
        "blocking.json",
        valid_review(
            report,
            approved=False,
            severity="blocking",
            reviewer="adversarial_reviewer",
            reviewer_run_id="review-run-002",
            reviewed_at="2026-07-11T00:02:00Z",
        ),
    )

    gate = check_workstream_readiness(workspace, workstream.name)

    assert not gate.passed
    assert any("blocking review" in issue.lower() for issue in gate.issues)


def test_required_report_sections_must_have_content(tmp_path):
    workspace, workstream = prepare_workstream(tmp_path)
    report = """# Empty Sections

## Provenance

## Uncertainty

## Failed Explorations
"""
    (workstream / "report.md").write_text(report, encoding="utf-8")
    write_review(workstream, "approval.json", valid_review(report))

    gate = check_workstream_readiness(workspace, workstream.name)

    assert not gate.passed
    assert any("empty" in issue.lower() for issue in gate.issues)
