from __future__ import annotations

import json

from harness.co_math.messages import append_message, read_messages
from harness.co_math.workspace import init_workspace


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
