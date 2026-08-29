from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .gating import check_final_render, check_workstream_completion
from .messages import read_messages
from .project import ResolvedProject, is_project_archived, resolve_project
from .skill_handoff import read_skill_handoffs
from .storage import resolve_managed_directory, resolve_managed_file
from .workspace import (
    _active_workstream_state_is_valid,
    duplicate_goal_ids,
    goal_approval_issues,
    load_goals,
    read_yaml,
    validate_workstream_id,
)


PROJECT_CONTEXT_SCHEMA_VERSION = 1


def project_snapshot(
    project: ResolvedProject,
    *,
    recent_limit: int = 10,
) -> dict[str, Any]:
    if recent_limit < 0:
        raise ValueError("recent_limit must be non-negative")
    snapshot = _empty_snapshot(project)
    try:
        current = resolve_project(project=project.root)
        if current is None:  # pragma: no cover - explicit projects never return None
            raise ValueError("Project could not be resolved")
        if current.manifest.project_id != project.manifest.project_id:
            raise ValueError("Project identity changed since it was resolved")

        try:
            goals_data = load_goals(current.workspace)
        except Exception as exc:
            raise ValueError(f"GOALS.yaml parsing failed: {exc}") from exc
        goals = _project_goals(goals_data, snapshot["errors"])
        workstreams = _project_workstreams(
            current.workspace,
            goals_data,
            snapshot["errors"],
        )
        messages = read_messages(current.workspace)
        handoffs = read_skill_handoffs(current.workspace)
        final_gate = check_final_render(current.workspace)
        final_dir = resolve_managed_directory(current.workspace, "final")
        generated = (final_dir / "generated_draft.md").is_file()
        working_paper = (final_dir / "working_paper.md").is_file()

        snapshot["language_policy"] = goals_data.get("language_policy", {})
        snapshot["research_question"] = goals_data.get("research_question", {})
        snapshot["goals"] = goals
        snapshot["workstreams"] = workstreams
        snapshot["recent_messages"] = messages[-recent_limit:] if recent_limit else []
        snapshot["active_skill_handoffs"] = [
            handoff for handoff in handoffs if handoff.get("status") == "active"
        ]
        snapshot["final"] = {
            "generated_draft": generated,
            "working_paper": working_paper,
            "render_gate_passed": final_gate.passed,
        }
        snapshot["archived"] = is_project_archived(current)

        if snapshot["errors"]:
            snapshot["status"] = "invalid"
        elif snapshot["archived"]:
            snapshot["status"] = "archived"
        else:
            policy_status = str(
                snapshot["language_policy"].get("status", "pending_user_choice")
            )
            research_status = str(
                snapshot["research_question"].get("status", "onboarding")
            )
            if policy_status in {"", "pending", "pending_user_choice"} or research_status != "approved":
                snapshot["status"] = "onboarding"
            elif final_gate.passed and working_paper:
                snapshot["status"] = "final_ready"
            else:
                snapshot["status"] = "active"
        snapshot["next_gate"] = _next_gate(snapshot)
    except Exception as exc:
        snapshot["status"] = "invalid"
        snapshot["errors"].append(str(exc))
        snapshot["next_gate"] = "doctor"
    snapshot["guidance"] = project_guidance(snapshot)
    return snapshot


def render_resume_text(snapshot: Mapping[str, Any]) -> str:
    summary = project_guidance(snapshot)
    lines = [
        f"Co-Math project: {summary['name']}",
        f"Question: {summary['question']}",
        f"Progress: {summary['progress']}",
    ]
    if summary["recent_update"]:
        lines.append(f"Recent: {summary['recent_update']}")
    if summary["blocker"]:
        lines.append(f"Blocked by: {summary['blocker']}")
    lines.extend(
        (
            f"Next: {summary['next_action']}",
            f"Path: {summary['path']}",
        )
    )
    return "\n".join(lines)


def render_next_text(snapshot: Mapping[str, Any]) -> str:
    summary = project_guidance(snapshot)
    lines = [
        f"{summary['name']}: {summary['current']}",
    ]
    if summary["blocker"]:
        lines.append(f"Blocked by: {summary['blocker']}")
    lines.append(f"Next: {summary['next_action']}")
    return "\n".join(lines)


def project_guidance(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    project = snapshot.get("project", {})
    research_question = snapshot.get("research_question", {})
    question = "Not confirmed yet."
    if isinstance(research_question, Mapping):
        text = str(research_question.get("text", "")).strip()
        if text:
            question = _short_text(text)
    return {
        "name": str(project.get("name", "unknown")),
        "path": str(project.get("path", "unknown")),
        "status": str(snapshot.get("status", "invalid")),
        "current": _current_text(snapshot),
        "question": question,
        "progress": _progress_text(snapshot),
        "recent_update": _recent_update(snapshot),
        "blocker": _blocker_text(snapshot),
        "next_action": _next_action_text(str(snapshot.get("next_gate", "doctor"))),
    }


def _empty_snapshot(project: ResolvedProject) -> dict[str, Any]:
    return {
        "schema_version": PROJECT_CONTEXT_SCHEMA_VERSION,
        "project": {
            "project_id": project.manifest.project_id,
            "name": project.manifest.name,
            "path": str(project.root),
            "workspace": str(project.workspace),
            "created_at": project.manifest.created_at,
            "created_with": project.manifest.created_with,
            "template_version": project.manifest.template_version,
        },
        "status": "invalid",
        "archived": False,
        "language_policy": {},
        "research_question": {},
        "goals": {"draft": [], "approved": [], "other": []},
        "workstreams": {"active": [], "blocked": [], "complete": [], "invalid": []},
        "recent_messages": [],
        "active_skill_handoffs": [],
        "final": {
            "generated_draft": False,
            "working_paper": False,
            "render_gate_passed": False,
        },
        "next_gate": "doctor",
        "guidance": {},
        "errors": [],
    }


def _project_goals(
    goals_data: Mapping[str, Any],
    errors: list[str],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "draft": [],
        "approved": [],
        "other": [],
    }
    raw_goals = goals_data.get("goals", [])
    if not isinstance(raw_goals, list):
        errors.append("GOALS.yaml goals must be a list")
        return result
    duplicates = duplicate_goal_ids(dict(goals_data))
    if duplicates:
        errors.append("Duplicate goal ids: " + ", ".join(sorted(duplicates)))
    for raw_goal in raw_goals:
        if not isinstance(raw_goal, dict):
            errors.append("GOALS.yaml contains a non-object goal")
            continue
        goal = dict(raw_goal)
        status = str(goal.get("status", ""))
        if status == "approved":
            issues = goal_approval_issues(dict(goals_data), goal)
            if issues:
                errors.extend(issues)
            result["approved"].append(goal)
        elif status == "draft":
            result["draft"].append(goal)
        else:
            result["other"].append(goal)
    for values in result.values():
        values.sort(key=lambda goal: str(goal.get("id", "")))
    return result


def _project_workstreams(
    workspace: Path,
    goals_data: dict[str, Any],
    errors: list[str],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "active": [],
        "blocked": [],
        "complete": [],
        "invalid": [],
    }
    workstreams_dir = resolve_managed_directory(workspace, "workstreams")
    for directory in sorted(workstreams_dir.iterdir()):
        if not directory.is_dir() or directory.is_symlink():
            continue
        status_candidate = directory / "status.yaml"
        if not status_candidate.exists() and not status_candidate.is_symlink():
            continue
        try:
            validate_workstream_id(directory.name)
            status_path = resolve_managed_file(directory, "status.yaml")
            status = read_yaml(status_path)
            if not isinstance(status, dict):
                raise ValueError("status.yaml must contain an object")
            summary = _workstream_summary(directory, status)
            if status.get("status") == "complete":
                gate = check_workstream_completion(workspace, directory.name)
                if not gate.passed:
                    raise ValueError("; ".join(gate.issues))
                result["complete"].append(summary)
            elif status.get("status") == "active":
                if not _active_workstream_state_is_valid(
                    directory,
                    status,
                    goals_data,
                ):
                    raise ValueError("active workstream state failed lifecycle validation")
                bucket = "blocked" if _has_unresolved_blocking_review(directory) else "active"
                result[bucket].append(summary)
            else:
                raise ValueError(f"unsupported status: {status.get('status')!r}")
        except Exception as exc:
            result["invalid"].append(
                {
                    "id": directory.name,
                    "error": str(exc),
                }
            )
            errors.append(f"{directory.name}: {exc}")
    return result


def _workstream_summary(directory: Path, status: Mapping[str, Any]) -> dict[str, Any]:
    if status.get("id") != directory.name:
        raise ValueError("status id does not match workstream directory")
    required = ("goal_id", "title", "kind", "status", "author_run_id")
    missing = [field for field in required if not str(status.get(field, "")).strip()]
    if missing:
        raise ValueError("status is missing: " + ", ".join(missing))
    return {
        "id": directory.name,
        "goal_id": str(status["goal_id"]),
        "title": str(status["title"]),
        "kind": str(status["kind"]),
        "status": str(status["status"]),
        "author_run_id": str(status["author_run_id"]),
    }


def _has_unresolved_blocking_review(workstream: Path) -> bool:
    reviews_dir = resolve_managed_directory(workstream, "reviews")
    reviews: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(reviews_dir.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            reviews.append((path.name, data))
    resolved = {
        str(name)
        for _, review in reviews
        if review.get("approved") is True
        for name in review.get("resolves", [])
    }
    return any(
        review.get("severity") == "blocking" and name not in resolved
        for name, review in reviews
    )


def _next_gate(snapshot: Mapping[str, Any]) -> str:
    status = snapshot.get("status")
    if status == "invalid":
        return "doctor"
    if status == "archived":
        return "reopen_project"
    if status == "onboarding":
        return "onboarding"
    if status == "final_ready":
        return "archive_project"

    workstreams = snapshot["workstreams"]
    goals = snapshot["goals"]
    final = snapshot["final"]
    if workstreams["blocked"]:
        return "resolve_blocking_review"
    if workstreams["active"]:
        for workstream in workstreams["active"]:
            report = (
                Path(snapshot["project"]["workspace"])
                / "workstreams"
                / workstream["id"]
                / "report.md"
            )
            if not report.is_file():
                return "workstream_execution"
        return "workstream_review"
    if workstreams["complete"]:
        if not final["generated_draft"]:
            return "final_render"
        if not final["working_paper"]:
            return "synthesis"
    if goals["approved"]:
        return "workstream_creation"
    if goals["draft"]:
        return "goal_approval"
    return "goal_formalization"


def _current_text(snapshot: Mapping[str, Any]) -> str:
    status = str(snapshot.get("status", "invalid"))
    return {
        "archived": "The project is archived.",
        "onboarding": "Project setup is still in progress.",
        "active": "Research is in progress.",
        "final_ready": "The working paper is ready.",
        "invalid": "The project files need attention.",
    }.get(status, "Project state is available.")


def _progress_text(snapshot: Mapping[str, Any]) -> str:
    if snapshot.get("status") == "archived":
        return "All files are preserved; no work is currently active."
    final = snapshot.get("final", {})
    if isinstance(final, Mapping) and final.get("working_paper"):
        return "The working paper exists."
    goals = snapshot.get("goals", {})
    workstreams = snapshot.get("workstreams", {})
    approved = len(goals.get("approved", [])) if isinstance(goals, Mapping) else 0
    draft = len(goals.get("draft", [])) if isinstance(goals, Mapping) else 0
    active = len(workstreams.get("active", [])) if isinstance(workstreams, Mapping) else 0
    blocked = len(workstreams.get("blocked", [])) if isinstance(workstreams, Mapping) else 0
    complete = len(workstreams.get("complete", [])) if isinstance(workstreams, Mapping) else 0
    if not any((approved, draft, active, blocked, complete)):
        return "No goals or workstreams have started."
    return (
        f"{approved} approved goals; {active} active, {blocked} blocked, "
        f"{complete} completed workstreams."
    )


def _recent_update(snapshot: Mapping[str, Any]) -> str:
    messages = snapshot.get("recent_messages", [])
    if not isinstance(messages, list):
        return ""
    preferred_types = {"artifact", "decision", "review", "status"}
    for message in reversed(messages):
        if not isinstance(message, Mapping):
            continue
        if str(message.get("type", "")) not in preferred_types:
            continue
        content = str(message.get("content", "")).strip()
        if content:
            return _short_text(content)
    return ""


def _blocker_text(snapshot: Mapping[str, Any]) -> str:
    errors = snapshot.get("errors", [])
    if isinstance(errors, list) and errors:
        return _short_text(str(errors[0]))
    workstreams = snapshot.get("workstreams", {})
    blocked = workstreams.get("blocked", []) if isinstance(workstreams, Mapping) else []
    if isinstance(blocked, list) and blocked:
        titles = [
            str(item.get("title") or item.get("id") or "workstream")
            for item in blocked
            if isinstance(item, Mapping)
        ]
        if titles:
            return _short_text(", ".join(titles))
    return ""


def _next_action_text(next_gate: str) -> str:
    return {
        "doctor": "Run co-math doctor and address the first reported issue.",
        "reopen_project": "Reopen the project when you want to continue.",
        "onboarding": "Describe the research question and confirm the document language.",
        "resolve_blocking_review": "Address the blocking review before continuing.",
        "workstream_execution": "Continue the active workstream and update its report.",
        "workstream_review": "Ask an independent reviewer to review the report.",
        "final_render": "Assemble completed workstream reports into a draft.",
        "synthesis": "Write or revise the final working paper.",
        "workstream_creation": "Create a workstream for an approved goal.",
        "goal_approval": "Review the draft goals and ask the user to approve or revise them.",
        "goal_formalization": "Turn the research question into a small set of draft goals.",
        "archive_project": "Review the working paper, then archive the project if finished.",
    }.get(next_gate, "Inspect the project and choose the next useful action.")


def _short_text(value: str, limit: int = 180) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
