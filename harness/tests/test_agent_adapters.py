from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT_TEMPLATE = ROOT / "harness" / "co_math" / "project_template"
ROLE_IDS = {
    "workstream_coordinator",
    "proof_explorer",
    "computational_experimenter",
    "literature_researcher",
    "logic_reviewer",
    "adversarial_reviewer",
    "citation_checker",
    "synthesis_agent",
}


def test_canonical_role_cards_exist_and_define_boundaries():
    roles_dir = ROOT / "agents" / "roles"
    assert roles_dir.is_dir()

    role_files = sorted(path.stem for path in roles_dir.glob("*.md"))
    assert set(role_files) == ROLE_IDS

    for role_id in ROLE_IDS:
        text = (roles_dir / f"{role_id}.md").read_text(encoding="utf-8")
        assert f"role_id: {role_id}" in text
        assert "## Responsibilities" in text
        assert "## Boundaries" in text
        assert "Do not start new goals or workstreams." in text
        assert "Do not mark any workstream complete." in text
        assert "## Adapter Notes" in text


def test_platform_adapters_cover_the_same_role_ids():
    codex_agents = {
        path.stem for path in (ROOT / ".codex" / "agents").glob("*.toml")
    }
    claude_agents = {
        path.stem for path in (ROOT / ".claude" / "agents").glob("*.md")
    }
    opencode_agents = {
        path.stem for path in (ROOT / ".opencode" / "agents").glob("*.md")
    }

    assert codex_agents == ROLE_IDS
    assert claude_agents == ROLE_IDS
    assert opencode_agents == ROLE_IDS

    cursor_rules = (ROOT / ".cursor" / "rules" / "co-mathematician-roles.mdc").read_text(
        encoding="utf-8"
    )
    for role_id in ROLE_IDS:
        assert role_id in cursor_rules
        assert f"agents/roles/{role_id}.md" in cursor_rules


def test_adapters_point_back_to_canonical_role_cards():
    for role_id in ROLE_IDS:
        role_path = f"agents/roles/{role_id}.md"

        codex_text = (ROOT / ".codex" / "agents" / f"{role_id}.toml").read_text(
            encoding="utf-8"
        )
        assert role_path in codex_text

        claude_text = (ROOT / ".claude" / "agents" / f"{role_id}.md").read_text(
            encoding="utf-8"
        )
        assert role_path in claude_text
        assert re.search(r"^---\n.*?^name: " + role_id + r"\n", claude_text, re.S | re.M)
        assert "description:" in claude_text
        assert "Read the canonical role card" in claude_text

        opencode_text = (ROOT / ".opencode" / "agents" / f"{role_id}.md").read_text(
            encoding="utf-8"
        )
        assert role_path in opencode_text
        assert "mode: subagent" in opencode_text
        assert "Do not mark any workstream complete." in opencode_text


def test_packaged_opencode_adapters_cover_canonical_roles_and_reviewer_boundaries():
    template_agents = PROJECT_TEMPLATE / ".opencode" / "agents"
    assert {path.stem for path in template_agents.glob("*.md")} == ROLE_IDS

    reviewer_ids = {"logic_reviewer", "adversarial_reviewer", "citation_checker"}
    for role_id in ROLE_IDS:
        text = (template_agents / f"{role_id}.md").read_text(encoding="utf-8")
        assert "mode: subagent" in text
        assert f"agents/roles/{role_id}.md" in text
        assert "Do not mark any workstream complete." in text
        if role_id in reviewer_ids:
            assert "edit: deny" in text
            assert "Do not approve a report authored by this same run." in text

    synthesis = (template_agents / "synthesis_agent.md").read_text(encoding="utf-8")
    assert "workspace/final/working_paper.md" in synthesis
    assert "Do not write any other project file." in synthesis


def test_codex_config_points_to_existing_agent_adapter_files():
    config_text = (ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")
    config_paths = re.findall(r'config_file = "([^"]+)"', config_text)

    assert sorted(config_paths) == [
        f"./.codex/agents/{role_id}.toml" for role_id in sorted(ROLE_IDS)
    ]
    for config_path in config_paths:
        assert (ROOT / config_path).is_file()


def test_platform_entry_docs_mention_skill_guided_mode():
    claude_text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    cursor_text = (ROOT / ".cursor" / "rules" / "co-mathematician.mdc").read_text(
        encoding="utf-8"
    )

    for text in (claude_text, cursor_text):
        assert "skill-guided mode" in text
        assert "co-math skill-handoff" in text


def test_runtime_reviewer_schema_matches_project_skill_contract():
    runtime_schema = ROOT / "harness" / "co_math" / "assets" / "reviewer_output_schema.json"
    skill_schema = (
        ROOT
        / ".agents"
        / "skills"
        / "co-mathematician"
        / "assets"
        / "reviewer_output_schema.json"
    )

    assert runtime_schema.is_file()
    assert json.loads(runtime_schema.read_text(encoding="utf-8")) == json.loads(
        skill_schema.read_text(encoding="utf-8")
    )
