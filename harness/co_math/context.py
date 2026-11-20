from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .gating import check_workstream_completion
from .messages import read_messages
from .project import Project, is_project_archived
from .workspace import load_goals, read_yaml


def project_summary(project: Project) -> dict[str, object]:
    summary: dict[str, object] = {
        "name": project.name,
        "path": str(project.root),
        "workspace": str(project.workspace),
        "status": "invalid",
        "current": "The project files need attention.",
        "question": "",
        "progress": "No goals or workstreams have started.",
        "recent_update": "",
        "open_question": "",
        "resume_prompt": "",
        "latest_note": "",
        "blocker": "",
        "reports": [],
        "working_paper": "",
        "paper_outline": "",
        "next_action": "检查项目文件并处理首个问题。",
    }
    errors: list[str] = []

    try:
        goals_path = project.workspace / "project" / "GOALS.yaml"
        if goals_path.is_symlink() or not goals_path.is_file():
            raise ValueError(f"GOALS.yaml is missing or unsafe: {goals_path}")
        goals_data = load_goals(project.workspace)
        question = goals_data.get("research_question", {})
        if isinstance(question, Mapping):
            text = str(question.get("text", "")).strip()
            if text:
                summary["question"] = text

        goals = goals_data.get("goals", [])
        if not isinstance(goals, list):
            errors.append("GOALS.yaml goals must be a list.")
            goals = []
        draft_goals = [goal for goal in goals if _goal_status(goal) == "draft"]
        approved_goals = [goal for goal in goals if _goal_status(goal) == "approved"]

        workstreams = _workstream_state(project.workspace, errors)
        recent_update = _recent_update(project.workspace, errors)
        archived = is_project_archived(project)
        paper = _safe_path(project.root, project.workspace / "final" / "working_paper.md")
        working_paper = paper is not None and paper.is_file()
        if working_paper:
            summary["working_paper"] = paper.relative_to(project.root).as_posix()
        outline = _safe_path(project.root, project.workspace / "final" / "working_paper_outline.md")
        if outline is not None and outline.is_file():
            summary["paper_outline"] = outline.relative_to(project.root).as_posix()
        summary["reports"] = workstreams["reports"]

        summary["recent_update"] = recent_update
        summary["progress"] = _progress_text(
            approved=len(approved_goals),
            draft=len(draft_goals),
            active=len(workstreams["active"]),
            complete=len(workstreams["complete"]),
            working_paper=working_paper,
        )

        language = goals_data.get("language_policy", {})
        language_status = (
            str(language.get("status", "pending_user_choice"))
            if isinstance(language, Mapping)
            else "pending_user_choice"
        )
        question_status = (
            str(question.get("status", "onboarding"))
            if isinstance(question, Mapping)
            else "onboarding"
        )

        blocker = errors[0] if errors else workstreams["blocker"]
        summary["blocker"] = _short(blocker) if blocker else ""

        if errors:
            summary["status"] = "invalid"
            summary["current"] = "The project files need attention."
            summary["next_action"] = "处理概览中列出的项目文件问题。"
        elif archived:
            summary["status"] = "archived"
            summary["current"] = "The project is archived."
            summary["next_action"] = "继续研究时，在 coding agent 中重新打开已归档的项目。"
        elif workstreams["blocker"]:
            summary["status"] = "active"
            summary["current"] = "Research is waiting on review changes."
            summary["next_action"] = "打开相关报告和审查意见，处理需要修订的内容。"
        elif language_status in {"", "pending", "pending_user_choice"} or question_status != "approved":
            summary["status"] = "onboarding"
            summary["current"] = "Project setup is still in progress."
            summary["next_action"] = (
                "确认研究问题并选择项目文档的语言。"
            )
        elif workstreams["needs_execution"]:
            summary["status"] = "active"
            summary["current"] = "Research is in progress."
            summary["next_action"] = (
                f"继续处理任务「{workstreams['needs_execution'][0]}」。"
            )
        elif workstreams["needs_review"]:
            summary["status"] = "active"
            summary["current"] = "A workstream report is ready for review."
            summary["next_action"] = (
                f"请独立审查者检查「{workstreams['needs_review'][0]}」的报告。"
            )
        elif working_paper:
            summary["status"] = "final_ready"
            summary["current"] = "The working paper is ready."
            summary["next_action"] = "阅读工作论文并确认是否可以归档项目。"
        elif workstreams["complete"]:
            summary["status"] = "active"
            summary["current"] = "Reviewed workstreams are ready for synthesis."
            summary["next_action"] = "根据通过审查的报告整理工作论文。"
        elif approved_goals:
            summary["status"] = "active"
            summary["current"] = "Approved goals are ready for research."
            summary["next_action"] = "为已确认的研究目标创建具体任务。"
        elif draft_goals:
            summary["status"] = "active"
            summary["current"] = "Draft goals are waiting for a decision."
            summary["next_action"] = "请用户确认或修订研究目标。"
        else:
            summary["status"] = "active"
            summary["current"] = "The research question is ready."
            summary["next_action"] = "根据研究问题提出具体目标，请用户确认。"
    except Exception as exc:
        summary["blocker"] = _short(str(exc))

    _add_continuation(project, summary)
    return summary


def render_resume(summary: Mapping[str, object]) -> str:
    lines = [
        f"Co-Math project: {summary['name']}",
        f"Question: {summary['question'] or 'Not recorded yet.'}",
        f"Progress: {summary['progress']}",
    ]
    if summary.get("recent_update"):
        lines.append(f"Recent: {_short(str(summary['recent_update']), 300)}")
    if summary.get("open_question"):
        lines.append(f"Open question: {summary['open_question']}")
    if summary.get("blocker"):
        lines.append(f"Blocked by: {summary['blocker']}")
    if summary.get("latest_note"):
        lines.append(f"Latest note (relative to project): {summary['latest_note']}")
    for report in summary.get("reports", []):
        lines.append(f"Report ({report['review_status']}): {report['title']} ({report['path']})")
    if summary.get("working_paper"):
        lines.append(f"Working paper (relative to project): {summary['working_paper']}")
    if summary.get("paper_outline"):
        lines.append(f"Paper outline (relative to project): {summary['paper_outline']}")
    lines.extend((f"Next: {summary['next_action']}", f"Path: {summary['path']}"))
    return "\n".join(lines)


def render_next(summary: Mapping[str, object]) -> str:
    lines = [f"{summary['name']}: {summary['current']}"]
    if summary.get("blocker"):
        lines.append(f"Blocked by: {summary['blocker']}")
    lines.append(f"Next: {summary['next_action']}")
    return "\n".join(lines)


def _add_continuation(project: Project, summary: dict[str, object]) -> None:
    sections = _status_sections(project)
    note_path, note_title = _latest_note(project)
    summary["latest_note"] = note_path
    summary["open_question"] = sections.get("open_question", "")

    if sections.get("recent_update"):
        summary["recent_update"] = sections["recent_update"]
    else:
        activity = [str(summary["recent_update"])] if summary["recent_update"] else []
        if note_path:
            activity.append(_short(f"最近保存的笔记（内容待核对）：{note_title}", 90))
        summary["recent_update"] = _short("；".join(activity), 240)

    if summary["status"] == "onboarding" and not summary["blocker"] and note_path:
        summary["next_action"] = "先阅读最近笔记，再与用户确认研究问题及下一步目标。"

    if (
        sections.get("next_action")
        and not summary["blocker"]
        and summary["status"] not in {"invalid", "archived"}
    ):
        summary["next_action"] = sections["next_action"]

    files = [
        project.root / "AGENTS.md",
        project.root / "CLAUDE.md",
        project.root / ".agents" / "skills" / "co-mathematician" / "SKILL.md",
        *(project.workspace / "project" / name for name in (
            "PROJECT.md", "GOALS.yaml", "PROJECT_STATUS.md", "SKILL_HANDOFFS.md",
            "skill_handoffs.jsonl", "messages.jsonl",
        )),
    ]
    if note_path:
        files.append(project.root / note_path)
    existing = []
    for path in files:
        safe = _safe_path(project.root, path)
        try:
            if safe is not None and safe.is_file():
                existing.append(safe.relative_to(project.root).as_posix())
        except OSError:
            continue
    unresolved = summary["open_question"] or "尚未记录，请从现有文件确认。"
    lines = [
        "请在以下项目中继续已有研究，遵循项目内指引及已选领域 Skill 的流程。",
        f"项目路径：{project.root}",
        f"研究问题：{summary['question'] or '尚未记录。'}",
        f"目标与工作流进度：{summary['progress']}",
        f"最近进展：{summary['recent_update'] or '尚未记录。'}",
        f"未解决问题：{unresolved}",
    ]
    if summary["blocker"]:
        lines.append(f"当前阻塞：{summary['blocker']}")
    lines.extend((
        f"下一步：{summary['next_action']}",
        "先阅读以下现有文件（路径相对项目），再阅读其中引用的工作流和审阅记录：",
        *(f"- {path}" for path in existing),
        "请核对研究结论的原文与证据，并检查问题和目标的确认记录。",
    ))
    summary["resume_prompt"] = "\n".join(lines)


def _safe_path(root: Path, path: Path) -> Path | None:
    try:
        parts = path.relative_to(root).parts
        if root.is_symlink() or ".." in parts:
            return None
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                return None
        return current
    except (OSError, ValueError):
        return None


def _optional_text(root: Path, path: Path) -> str:
    try:
        safe = _safe_path(root, path)
        if safe is None or not safe.is_file() or safe.stat().st_size > 8_000_000:
            return ""
        with safe.open("rb") as handle:
            data = handle.read(8_000_001)
        return data.decode("utf-8") if len(data) <= 8_000_000 else ""
    except (OSError, UnicodeError):
        return ""


def _status_sections(project: Project) -> dict[str, str]:
    text = _optional_text(project.root, project.workspace / "project" / "PROJECT_STATUS.md")
    names = {
        "recent progress": "recent_update", "最近进展": "recent_update",
        "open questions": "open_question", "未解决问题": "open_question",
        "next action": "next_action", "下一步": "next_action",
    }
    sections: dict[str, list[str]] = {}
    current = ""
    level = 0
    fence = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not fence:
                fence = marker
            elif fence == marker:
                fence = ""
            continue
        if fence:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            name = names.get(heading[2].casefold(), "")
            if name or len(heading[1]) <= level:
                current = name
                level = len(heading[1])
                if current:
                    sections.setdefault(current, [])
        elif current and stripped:
            sections[current].append(stripped)
    return {key: _short(" ".join(lines)) for key, lines in sections.items()}


def _latest_note(project: Project) -> tuple[str, str]:
    directory = _safe_path(project.root, project.workspace / "project" / "notes")
    candidates: list[tuple[int, Path]] = []
    try:
        if directory is None or not directory.is_dir():
            return "", ""
        for path in directory.iterdir():
            if path.name.startswith(".") or path.suffix.lower() != ".md":
                continue
            safe = _safe_path(project.root, path)
            try:
                if safe is not None and safe.is_file():
                    candidates.append((safe.stat().st_mtime_ns, safe))
            except OSError:
                continue
    except OSError:
        return "", ""
    for _, path in sorted(candidates, reverse=True):
        try:
            with path.open(encoding="utf-8") as handle:
                heading = handle.readline(300).strip()
            title = heading[2:].strip() if heading.startswith("# ") else path.stem
            return path.relative_to(project.root).as_posix(), _short(title or path.stem)
        except (OSError, UnicodeError):
            continue
    return "", ""


def _workstream_state(workspace: Path, errors: list[str]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "active": [],
        "complete": [],
        "needs_execution": [],
        "needs_review": [],
        "blocker": "",
        "reports": [],
    }
    directory = workspace / "workstreams"
    if directory.is_symlink() or not directory.is_dir():
        errors.append(f"Workstreams directory is missing or unsafe: {directory}")
        return state

    for workstream in sorted(directory.iterdir(), key=lambda item: item.name):
        if workstream.is_symlink() or not workstream.is_dir():
            continue
        status_path = workstream / "status.yaml"
        if status_path.is_symlink() or not status_path.is_file():
            continue
        try:
            status = read_yaml(status_path)
            if not isinstance(status, dict):
                raise ValueError("status.yaml must contain a mapping")
            title = str(status.get("title") or workstream.name)
            report = workstream / "report.md"
            marked_complete = status.get("status", "active") == "complete"
            if report.is_symlink():
                errors.append(f"{workstream.name}: report.md is a symbolic link.")
                continue
            if not report.is_file():
                if marked_complete:
                    errors.append(f"{workstream.name}: report.md is missing.")
                    continue
                state["active"].append(title)
                state["needs_execution"].append(title)
                continue
            gate = check_workstream_completion(workspace, workstream.name)
            blocking = next(
                (issue for issue in gate.issues if "blocking review" in issue.lower()),
                "",
            )
            reviews = workstream / "reviews"
            review_paths = [
                path.relative_to(workspace.parent).as_posix()
                for path in sorted(reviews.iterdir())
                if path.suffix in {".json", ".md"} and not path.name.startswith(".")
                and not path.is_symlink() and path.is_file()
            ] if reviews.is_dir() and not reviews.is_symlink() else []
            state["reports"].append({
                "title": title,
                "path": report.relative_to(workspace.parent).as_posix(),
                "review_status": "reviewed" if gate.passed else "blocked" if blocking else "pending",
                "reviews": review_paths,
            })
            if marked_complete and not gate.passed:
                errors.append(gate.issues[0])
                continue
            if blocking:
                state["active"].append(title)
                if not state["blocker"]:
                    state["blocker"] = blocking
            elif gate.passed:
                state["complete"].append(title)
            elif any("missing a" in issue.lower() for issue in gate.issues):
                state["active"].append(title)
                state["needs_execution"].append(title)
            else:
                state["active"].append(title)
                state["needs_review"].append(title)
        except Exception as exc:
            errors.append(f"{workstream.name}: {exc}")
    return state


def _recent_update(workspace: Path, errors: list[str]) -> str:
    try:
        messages = read_messages(workspace)
    except Exception as exc:
        errors.append(f"messages.jsonl: {exc}")
        return ""
    for message in reversed(messages):
        if message.get("type") not in {"artifact", "decision", "review", "status"}:
            continue
        content = str(message.get("content", "")).strip()
        if content:
            return _short(content)
    return ""


def _goal_status(goal: object) -> str:
    return str(goal.get("status", "")) if isinstance(goal, Mapping) else ""


def _progress_text(
    *,
    approved: int,
    draft: int,
    active: int,
    complete: int,
    working_paper: bool,
) -> str:
    if working_paper:
        return "The working paper exists."
    if not any((approved, draft, active, complete)):
        return "No goals or workstreams have started."
    return (
        f"{approved} approved goals; {active} active and {complete} reviewed "
        "workstreams."
    )


def _short(value: str, limit: int = 180) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
