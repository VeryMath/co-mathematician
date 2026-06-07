from __future__ import annotations

import json
from pathlib import Path

from .schemas import (
    VALID_SKILL_HANDOFF_MODES,
    SkillHandoffRecord,
    utc_timestamp,
)


def record_skill_handoff(
    workspace: str | Path,
    *,
    skill: str,
    mode: str,
    reason: str,
    query: str = "",
    skill_path: str = "",
    status: str = "active",
) -> SkillHandoffRecord:
    if mode not in VALID_SKILL_HANDOFF_MODES:
        raise ValueError(f"Unsupported skill handoff mode: {mode}")

    record: SkillHandoffRecord = {
        "timestamp": utc_timestamp(),
        "skill": skill,
        "mode": mode,
        "status": status,
        "reason": reason,
        "query": query,
        "skill_path": skill_path,
    }

    project = Path(workspace) / "project"
    project.mkdir(parents=True, exist_ok=True)
    jsonl_path = project / "skill_handoffs.jsonl"
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    _write_markdown(project / "SKILL_HANDOFFS.md", read_skill_handoffs(workspace))
    return record


def read_skill_handoffs(workspace: str | Path) -> list[SkillHandoffRecord]:
    path = Path(workspace) / "project" / "skill_handoffs.jsonl"
    if not path.exists():
        return []
    records: list[SkillHandoffRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _write_markdown(path: Path, records: list[SkillHandoffRecord]) -> None:
    lines = [
        "# Skill Handoffs",
        "",
        "This file records when the workspace delegates inner workflow control to a project-local domain Skill.",
        "",
    ]
    if not records:
        lines.append("No skill handoffs have been recorded.")
    for record in records:
        lines.extend(
            [
                f"## {record['skill']}",
                "",
                f"- timestamp: `{record['timestamp']}`",
                f"- mode: `{record['mode']}`",
                f"- status: `{record['status']}`",
                f"- skill_path: `{record['skill_path']}`",
                f"- query: {record['query']}",
                f"- reason: {record['reason']}",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
