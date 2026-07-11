from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import harness.co_math.messages as messages_module
from harness.co_math.messages import append_message, read_messages
from harness.co_math.workspace import init_workspace


ROOT = Path(__file__).resolve().parents[2]


def test_init_creates_workspace_scaffold_and_is_idempotent(tmp_path):
    workspace = tmp_path / "workspace"

    init_workspace(workspace)
    init_workspace(workspace)

    assert (workspace / "project" / "PROJECT.md").is_file()
    assert (workspace / "project" / "GOALS.yaml").is_file()
    assert (workspace / "project" / "PROJECT_STATUS.md").is_file()
    assert (workspace / "project" / "messages.jsonl").is_file()
    assert (workspace / "project" / "skill_handoffs.jsonl").is_file()
    assert (workspace / "workstreams").is_dir()
    assert (workspace / "final").is_dir()

    goals_text = (workspace / "project" / "GOALS.yaml").read_text()
    assert "language_policy:" in goals_text
    assert "pending_user_choice" in goals_text
    assert "goals:" in goals_text
    assert "approved" not in goals_text

    project_text = (workspace / "project" / "PROJECT.md").read_text()
    assert "Language Policy" in project_text

    status_text = (workspace / "project" / "PROJECT_STATUS.md").read_text()
    assert "onboarding" in status_text
    assert "language_policy: pending_user_choice" in status_text


def test_append_message_writes_jsonl_records(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)

    record = append_message(
        workspace,
        sender="project_coordinator",
        recipient="user",
        message_type="status",
        content="Initialized the project shell only.",
        provenance=["literature/papers/2605.06651_ai_co_mathematician.pdf"],
        uncertainty=["No research goal has been approved yet."],
    )

    assert record["timestamp"].endswith("Z")
    assert record["sender"] == "project_coordinator"
    assert record["recipient"] == "user"
    assert record["type"] == "status"
    assert record["provenance"] == [
        "literature/papers/2605.06651_ai_co_mathematician.pdf"
    ]
    assert record["uncertainty"] == ["No research goal has been approved yet."]

    raw_line = (workspace / "project" / "messages.jsonl").read_text().strip()
    assert json.loads(raw_line) == record
    assert read_messages(workspace) == [record]


def test_append_message_accepts_goal_proposal_records(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)

    record = append_message(
        workspace,
        sender="project_coordinator",
        recipient="user",
        message_type="proposal",
        content="Proposed goals G1-G3 and await user approval.",
    )

    assert record["type"] == "proposal"


def test_append_message_uses_workspace_lock(tmp_path, monkeypatch):
    existing_lock = getattr(messages_module, "workspace_lock", None)
    assert callable(existing_lock), "message writes must use the workspace lock"
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    entered = []

    @contextmanager
    def spy_lock(root):
        entered.append(root)
        yield

    monkeypatch.setattr(messages_module, "workspace_lock", spy_lock)
    append_message(
        workspace,
        sender="project_coordinator",
        recipient="user",
        message_type="status",
        content="Locked message.",
    )

    assert entered == [workspace]


def test_checked_in_workspace_scaffold_includes_skill_handoff_state():
    project_text = (ROOT / "workspace" / "project" / "PROJECT.md").read_text(
        encoding="utf-8"
    )
    status_text = (ROOT / "workspace" / "project" / "PROJECT_STATUS.md").read_text(
        encoding="utf-8"
    )
    handoff_log = ROOT / "workspace" / "project" / "skill_handoffs.jsonl"

    assert "skill-guided mode" in project_text
    assert "co-math skill-handoff" in project_text
    assert "active_skill_handoffs: 0" in status_text
    assert handoff_log.is_file()
