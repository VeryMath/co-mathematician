from __future__ import annotations

import json

from harness.co_math.skills import refresh_skill_registry, suggest_skills
from harness.co_math.workspace import init_workspace


def write_skill(root, name, description):
    skill_dir = root / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: {description}
---

# {name}

Use this skill for testing project-local discovery.
""",
        encoding="utf-8",
    )


def write_nested_skill(root, category, name, description):
    skill_dir = root / ".agents" / "skills" / category / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: {description}
---

# {name}
""",
        encoding="utf-8",
    )


def test_refresh_skill_registry_discovers_project_local_skills(tmp_path):
    repo = tmp_path / "repo"
    workspace = repo / "workspace"
    init_workspace(workspace)
    write_skill(
        repo,
        "optimization-skill",
        "Use when modeling optimization problems over cones, manifolds, or matrices.",
    )
    write_skill(
        repo,
        "co-mathematician",
        "Use when running a durable mathematical research workspace.",
    )
    write_nested_skill(
        repo,
        "optimization",
        "semidefinite-solver",
        "Use when routing semidefinite optimization problems.",
    )

    registry = refresh_skill_registry(workspace, repo_root=repo)

    assert [entry["name"] for entry in registry["skills"]] == [
        "co-mathematician",
        "optimization-skill",
        "semidefinite-solver",
    ]
    assert registry["skill_root"] == ".agents/skills"
    assert registry["skills"][1]["path"] == ".agents/skills/optimization-skill/SKILL.md"
    assert registry["skills"][2]["path"] == (
        ".agents/skills/optimization/semidefinite-solver/SKILL.md"
    )

    registry_path = workspace / "project" / "skill_registry.json"
    markdown_path = workspace / "project" / "SKILL_REGISTRY.md"
    assert json.loads(registry_path.read_text(encoding="utf-8")) == registry
    assert "optimization-skill" in markdown_path.read_text(encoding="utf-8")


def test_suggest_skills_matches_query_against_registry(tmp_path):
    repo = tmp_path / "repo"
    workspace = repo / "workspace"
    init_workspace(workspace)
    write_skill(
        repo,
        "optimization-skill",
        "Use when modeling conic, semidefinite, nonlinear, or manifold optimization problems.",
    )
    write_skill(
        repo,
        "citation-checker",
        "Use when checking bibliographic references and citation provenance.",
    )
    refresh_skill_registry(workspace, repo_root=repo)

    matches = suggest_skills(
        workspace,
        "Stiefel manifold optimization with semidefinite constraints",
        limit=1,
    )

    assert len(matches) == 1
    assert matches[0]["name"] == "optimization-skill"
    assert matches[0]["score"] > 0


def test_suggest_skills_can_refresh_before_matching(tmp_path):
    repo = tmp_path / "repo"
    workspace = repo / "workspace"
    init_workspace(workspace)
    write_skill(
        repo,
        "optimization-skill",
        "Use when modeling conic, semidefinite, nonlinear, or manifold optimization problems.",
    )

    matches = suggest_skills(
        workspace,
        "manifold optimization",
        repo_root=repo,
        refresh=True,
        limit=1,
    )

    assert matches[0]["name"] == "optimization-skill"
    assert (workspace / "project" / "skill_registry.json").is_file()
