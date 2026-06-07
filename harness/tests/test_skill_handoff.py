from __future__ import annotations

import json

from harness.co_math.skill_handoff import read_skill_handoffs, record_skill_handoff
from harness.co_math.workspace import init_workspace


def test_record_skill_guided_handoff_writes_durable_registry(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)

    record = record_skill_handoff(
        workspace,
        skill="optimization-skill",
        mode="skill_guided",
        reason="ODL is a Stiefel manifold optimization problem.",
        query="orthogonal dictionary learning Stiefel manifold optimization",
        skill_path=".agents/skills/optimization-skill/SKILL.md",
    )

    assert record["timestamp"].endswith("Z")
    assert record["skill"] == "optimization-skill"
    assert record["mode"] == "skill_guided"
    assert record["status"] == "active"

    raw_line = (workspace / "project" / "skill_handoffs.jsonl").read_text().strip()
    assert json.loads(raw_line) == record
    assert read_skill_handoffs(workspace) == [record]

    markdown = (workspace / "project" / "SKILL_HANDOFFS.md").read_text()
    assert "optimization-skill" in markdown
    assert "skill_guided" in markdown
    assert ".agents/skills/optimization-skill/SKILL.md" in markdown
