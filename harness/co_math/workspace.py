from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schemas import VALID_WORKSTREAM_KINDS, utc_timestamp

try:
    import yaml
except Exception:  # pragma: no cover - fallback for minimal Python environments
    yaml = None


DEFAULT_PROJECT_MD = """# Co-Mathematician Project

This workspace is initialized but no mathematical research project has started.

## Current Phase
onboarding

## Research Question
Pending user discussion and formal approval.

## Language Policy
Status: pending user choice.

Ask the user which language policy to use for generated workspace artifacts
before writing project content:

1. English for all workspace documents.
2. User language for research notes, English for schemas, gates, and reviews.
3. User language for all human-readable research documents.
4. Match each project or conversation.

## Operating Rule
Default workspace mode does not start workstreams until the user approves
explicit goals in GOALS.yaml. If a project-local domain Skill is active, record
the handoff and follow that Skill's workflow until the task is promoted into
goals or workstreams.
"""

DEFAULT_GOALS = {
    "language_policy": {
        "status": "pending_user_choice",
        "schema_language": "English",
        "project_docs_language": "",
        "notes_language": "",
        "review_language": "English",
        "final_output_language": "",
    },
    "research_question": {"status": "onboarding", "text": ""},
    "goals": [],
}

DEFAULT_PROJECT_STATUS = """# Project Status

- phase: onboarding
- language_policy: pending_user_choice
- approved_goals: 0
- active_workstreams: 0
- active_skill_handoffs: 0
- final_output: not_started

No mathematical research project has started.
"""


def init_workspace(workspace: str | Path) -> Path:
    root = Path(workspace)
    project = root / "project"
    workstreams = root / "workstreams"
    final = root / "final"

    project.mkdir(parents=True, exist_ok=True)
    workstreams.mkdir(parents=True, exist_ok=True)
    final.mkdir(parents=True, exist_ok=True)

    _write_text_if_missing(project / "PROJECT.md", DEFAULT_PROJECT_MD)
    _write_yaml_if_missing(project / "GOALS.yaml", DEFAULT_GOALS)
    _write_text_if_missing(project / "PROJECT_STATUS.md", DEFAULT_PROJECT_STATUS)
    (project / "messages.jsonl").touch(exist_ok=True)
    (project / "skill_handoffs.jsonl").touch(exist_ok=True)
    return root


def new_workstream(
    workspace: str | Path,
    *,
    goal_id: str,
    title: str,
    kind: str,
) -> Path:
    if kind not in VALID_WORKSTREAM_KINDS:
        raise ValueError(f"Unsupported workstream kind: {kind}")

    root = Path(workspace)
    goals = load_goals(root)
    goal = find_goal(goals, goal_id)
    if goal is None:
        raise ValueError(f"Goal {goal_id} was not found")
    if str(goal.get("status", "")).lower() != "approved":
        raise ValueError(f"Goal {goal_id} is not approved")

    workstreams_dir = root / "workstreams"
    workstreams_dir.mkdir(parents=True, exist_ok=True)
    workstream_id = _next_workstream_id(workstreams_dir, goal_id, title)
    path = workstreams_dir / workstream_id
    path.mkdir(parents=True, exist_ok=False)

    for dirname in ("artifacts", "failures", "reviews"):
        (path / dirname).mkdir(exist_ok=True)

    status = {
        "id": workstream_id,
        "goal_id": goal_id,
        "title": title,
        "kind": kind,
        "status": "active",
        "coordinator": "workstream_coordinator",
        "created_at": utc_timestamp(),
    }
    write_yaml(path / "status.yaml", status)
    (path / "messages.jsonl").touch()
    (path / "WORKSTREAM.md").write_text(_workstream_md(status), encoding="utf-8")
    (path / "plan.md").write_text("# Plan\n\nPending coordinator plan.\n", encoding="utf-8")
    (path / "notes.md").write_text("# Notes\n\nNo notes yet.\n", encoding="utf-8")

    workstream_refs = goal.setdefault("workstreams", [])
    if workstream_id not in workstream_refs:
        workstream_refs.append(workstream_id)
        save_goals(root, goals)

    return path


def load_goals(workspace: str | Path) -> dict[str, Any]:
    path = Path(workspace) / "project" / "GOALS.yaml"
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_GOALS))
    data = read_yaml(path)
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT_GOALS))
    data.setdefault("goals", [])
    return data


def save_goals(workspace: str | Path, data: dict[str, Any]) -> None:
    write_yaml(Path(workspace) / "project" / "GOALS.yaml", data)


def find_goal(goals_data: dict[str, Any], goal_id: str) -> dict[str, Any] | None:
    for goal in goals_data.get("goals", []):
        if str(goal.get("id")) == goal_id:
            return goal
    return None


def read_yaml(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML is required to read non-JSON YAML files") from exc


def write_yaml(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    if yaml is not None:
        target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_text_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _write_yaml_if_missing(path: Path, data: dict[str, Any]) -> None:
    if not path.exists():
        write_yaml(path, data)


def _next_workstream_id(workstreams_dir: Path, goal_id: str, title: str) -> str:
    slug = _slugify(title)
    prefix = f"WS-{goal_id}-"
    existing = [
        path.name
        for path in workstreams_dir.iterdir()
        if path.is_dir() and path.name.startswith(prefix)
    ]
    return f"{prefix}{len(existing) + 1:03d}-{slug}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "workstream"


def _workstream_md(status: dict[str, Any]) -> str:
    return f"""# {status["title"]}

- id: {status["id"]}
- goal_id: {status["goal_id"]}
- kind: {status["kind"]}
- status: active

This workstream is a durable artifact directory. It is not complete until report.md
passes independent review and the completion gate.
"""
