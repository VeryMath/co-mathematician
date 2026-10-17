from __future__ import annotations

import argparse
import json
from pathlib import Path

from .context import project_summary, render_next, render_resume
from .gating import check_gate
from .messages import append_message
from .project import (
    DEFAULT_PROJECTS_HOME,
    Project,
    archive_project,
    configure_projects_home,
    create_project,
    list_projects,
    projects_home as get_projects_home,
    reopen_project,
    resolve_project,
)
from .reports import render_final
from .schemas import (
    VALID_MESSAGE_TYPES,
    VALID_SKILL_HANDOFF_MODES,
    VALID_WORKSTREAM_KINDS,
)
from .skill_handoff import record_skill_handoff
from .skills import refresh_skill_registry, suggest_skills
from .workspace import init_workspace, new_workstream


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="co-math")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser(
        "setup", help="Choose the parent directory for Co-Math projects"
    )
    setup_parser.add_argument(
        "--projects-home", default=str(DEFAULT_PROJECTS_HOME)
    )
    setup_parser.add_argument("--json", action="store_true")
    setup_parser.set_defaults(func=_cmd_setup)

    new_parser = subparsers.add_parser(
        "new", help="Create an independent Co-Math project"
    )
    new_parser.add_argument("name")
    new_parser.add_argument("--projects-home")
    new_parser.add_argument("--no-git", action="store_true")
    new_parser.add_argument("--json", action="store_true")
    new_parser.set_defaults(func=_cmd_new_project)

    list_parser = subparsers.add_parser("list", help="List Co-Math projects")
    list_parser.add_argument("--projects-home")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=_cmd_list_projects)

    status_parser = subparsers.add_parser(
        "status", help="Show the current project state"
    )
    _add_project_target(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=_cmd_project_status)

    resume_parser = subparsers.add_parser(
        "resume", help="Summarize a project before continuing"
    )
    _add_project_target(resume_parser)
    resume_parser.add_argument("--json", action="store_true")
    resume_parser.set_defaults(func=_cmd_project_resume)

    next_parser = subparsers.add_parser(
        "next", help="Show one useful next project action"
    )
    _add_project_target(next_parser)
    next_parser.add_argument("--json", action="store_true")
    next_parser.set_defaults(func=_cmd_project_next)

    archive_parser = subparsers.add_parser(
        "archive", help="Archive a project without deleting its files"
    )
    _add_project_target(archive_parser)
    archive_parser.add_argument("--json", action="store_true")
    archive_parser.set_defaults(func=_cmd_project_archive)

    reopen_parser = subparsers.add_parser(
        "reopen", help="Reopen an archived project"
    )
    _add_project_target(reopen_parser)
    reopen_parser.add_argument("--json", action="store_true")
    reopen_parser.set_defaults(func=_cmd_project_reopen)

    init_parser = subparsers.add_parser("init", help="Initialize workspace scaffold")
    init_parser.add_argument("--workspace", default="workspace")
    init_parser.set_defaults(func=_cmd_init)

    message_parser = subparsers.add_parser("append-message", help="Append JSONL message")
    message_parser.add_argument("--workspace", default="workspace")
    message_parser.add_argument("--sender", required=True)
    message_parser.add_argument("--recipient", required=True)
    message_parser.add_argument("--type", dest="message_type", choices=VALID_MESSAGE_TYPES, required=True)
    message_parser.add_argument("--content", required=True)
    message_parser.add_argument("--provenance", action="append", default=[])
    message_parser.add_argument("--uncertainty", action="append", default=[])
    message_parser.set_defaults(func=_cmd_append_message)

    ws_parser = subparsers.add_parser("new-workstream", help="Create approved-goal workstream")
    ws_parser.add_argument("--workspace", default="workspace")
    ws_parser.add_argument("--goal-id", required=True)
    ws_parser.add_argument("--title", required=True)
    ws_parser.add_argument("--kind", choices=VALID_WORKSTREAM_KINDS, required=True)
    ws_parser.add_argument(
        "--input", dest="inputs", action="append", default=[],
        help="Reuse an existing workspace-relative file without copying; repeat for multiple inputs",
    )
    ws_parser.set_defaults(func=_cmd_new_workstream)

    gate_parser = subparsers.add_parser("check-gate", help="Check a harness gate")
    gate_parser.add_argument("--workspace", default="workspace")
    gate_parser.add_argument(
        "--gate",
        choices=("goal_approval", "workstream_completion", "final_render"),
        required=True,
    )
    gate_parser.add_argument("--goal-id")
    gate_parser.add_argument("--workstream-id")
    gate_parser.add_argument("--json", action="store_true")
    gate_parser.set_defaults(func=_cmd_check_gate)

    render_parser = subparsers.add_parser("render-final", help="Render final working paper")
    render_parser.add_argument("--workspace", default="workspace")
    render_parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace an existing working_paper.md; existing edits will be lost",
    )
    render_parser.set_defaults(func=_cmd_render_final)

    refresh_skills_parser = subparsers.add_parser(
        "refresh-skills",
        help="Scan project-local skills and write workspace skill registry",
    )
    refresh_skills_parser.add_argument("--workspace", default="workspace")
    refresh_skills_parser.add_argument("--repo-root", default=".")
    refresh_skills_parser.add_argument("--json", action="store_true")
    refresh_skills_parser.set_defaults(func=_cmd_refresh_skills)

    suggest_skills_parser = subparsers.add_parser(
        "suggest-skills",
        help="Suggest project-local skills for a query",
    )
    suggest_skills_parser.add_argument("--workspace", default="workspace")
    suggest_skills_parser.add_argument("--repo-root", default=".")
    suggest_skills_parser.add_argument("--query", required=True)
    suggest_skills_parser.add_argument("--limit", type=int, default=5)
    suggest_skills_parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Use the existing registry instead of scanning project-local skills first",
    )
    suggest_skills_parser.add_argument("--json", action="store_true")
    suggest_skills_parser.set_defaults(func=_cmd_suggest_skills)

    handoff_parser = subparsers.add_parser(
        "skill-handoff",
        help="Record that inner workflow control is delegated to a project-local skill",
    )
    handoff_parser.add_argument("--workspace", default="workspace")
    handoff_parser.add_argument("--skill", required=True)
    handoff_parser.add_argument("--mode", choices=VALID_SKILL_HANDOFF_MODES, required=True)
    handoff_parser.add_argument("--reason", required=True)
    handoff_parser.add_argument("--query", default="")
    handoff_parser.add_argument("--skill-path", default="")
    handoff_parser.add_argument("--status", default="active")
    handoff_parser.add_argument("--json", action="store_true")
    handoff_parser.set_defaults(func=_cmd_skill_handoff)

    return parser


def _cmd_setup(args: argparse.Namespace) -> int:
    home = configure_projects_home(args.projects_home)
    output = {"projects_home": str(home)}
    if args.json:
        _print_json(output)
    else:
        print(f"Co-Math projects directory: {home}")
    return 0


def _cmd_new_project(args: argparse.Namespace) -> int:
    project, git_initialized = create_project(
        args.name,
        projects_home_path=args.projects_home,
        initialize_git=not args.no_git,
    )
    output = {
        "name": project.name,
        "path": str(project.root),
        "workspace": str(project.workspace),
        "git_initialized": git_initialized,
        "next_action": "Open this directory in your coding agent.",
    }
    if args.json:
        _print_json(output)
    else:
        print(f"Created Co-Math project: {project.name}")
        print(f"Path: {project.root}")
        if not args.no_git and not git_initialized:
            print("Git was not initialized; run git init in the project if needed.")
        print("Next: Open this directory in your coding agent.")
    return 0


def _cmd_list_projects(args: argparse.Namespace) -> int:
    home = get_projects_home(args.projects_home)
    found = list_projects(args.projects_home)
    output = [
        {
            "name": project.name,
            "path": str(project.root),
            "workspace": str(project.workspace),
            **project_summary(project),
        }
        for project in found
    ]
    if args.json:
        _print_json(output)
    elif not output:
        print(f"No Co-Math projects found under {home}.")
    else:
        for item in output:
            print(f"{item['name']}: {item['path']}")
            print(f"  {item['current']}")
            print(f"  Next: {item['next_action']}")
    return 0


def _cmd_project_status(args: argparse.Namespace) -> int:
    summary = project_summary(_project_from_args(args))
    if args.json:
        _print_json(summary)
    else:
        print(render_resume(summary))
    return 1 if summary["status"] == "invalid" else 0


def _cmd_project_resume(args: argparse.Namespace) -> int:
    summary = project_summary(_project_from_args(args))
    if args.json:
        _print_json(summary)
    else:
        print(render_resume(summary))
    return 1 if summary["status"] == "invalid" else 0


def _cmd_project_next(args: argparse.Namespace) -> int:
    summary = project_summary(_project_from_args(args))
    if args.json:
        _print_json(summary)
    else:
        print(render_next(summary))
    return 1 if summary["status"] == "invalid" else 0


def _cmd_project_archive(args: argparse.Namespace) -> int:
    project = _project_from_args(args)
    archive_project(project)
    summary = project_summary(project)
    if args.json:
        _print_json(summary)
    else:
        print(f"Archived Co-Math project: {project.name}")
        print(f"Path: {project.root}")
    return 0


def _cmd_project_reopen(args: argparse.Namespace) -> int:
    project = _project_from_args(args)
    reopen_project(project)
    summary = project_summary(project)
    if args.json:
        _print_json(summary)
    else:
        print(f"Reopened Co-Math project: {project.name}")
        print(render_next(summary))
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    root = init_workspace(args.workspace)
    print(f"Initialized workspace: {Path(root)}")
    return 0


def _cmd_append_message(args: argparse.Namespace) -> int:
    record = append_message(
        args.workspace,
        sender=args.sender,
        recipient=args.recipient,
        message_type=args.message_type,
        content=args.content,
        provenance=args.provenance,
        uncertainty=args.uncertainty,
    )
    print(json.dumps(record, ensure_ascii=False))
    return 0


def _cmd_new_workstream(args: argparse.Namespace) -> int:
    path = new_workstream(
        args.workspace,
        goal_id=args.goal_id,
        title=args.title,
        kind=args.kind,
        inputs=args.inputs,
    )
    print(f"Created workstream: {path}")
    return 0


def _cmd_check_gate(args: argparse.Namespace) -> int:
    result = check_gate(
        args.workspace,
        args.gate,
        goal_id=args.goal_id,
        workstream_id=args.workstream_id,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "gate": result.gate,
                    "passed": result.passed,
                    "issues": result.issues,
                    "details": result.details,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{'PASS' if result.passed else 'FAIL'} {result.gate}")
        for issue in result.issues:
            print(f"- {issue}")
    return 0 if result.passed else 1


def _cmd_render_final(args: argparse.Namespace) -> int:
    path = render_final(args.workspace, overwrite=args.overwrite)
    print(f"Rendered final working paper: {path}")
    return 0


def _cmd_refresh_skills(args: argparse.Namespace) -> int:
    registry = refresh_skill_registry(args.workspace, repo_root=args.repo_root)
    if args.json:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
        return 0
    print(
        "Refreshed project skill registry: "
        f"{Path(args.workspace) / 'project' / 'skill_registry.json'}"
    )
    for skill in registry["skills"]:
        print(f"- {skill['name']}: {skill['path']}")
    return 0


def _cmd_suggest_skills(args: argparse.Namespace) -> int:
    matches = suggest_skills(
        args.workspace,
        args.query,
        repo_root=args.repo_root,
        refresh=not args.no_refresh,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        return 0
    if not matches:
        print("No matching project-local skills found.")
        return 1
    for match in matches:
        print(f"{match['name']} ({match['score']}): {match['path']}")
    return 0


def _cmd_skill_handoff(args: argparse.Namespace) -> int:
    record = record_skill_handoff(
        args.workspace,
        skill=args.skill,
        mode=args.mode,
        reason=args.reason,
        query=args.query,
        skill_path=args.skill_path,
        status=args.status,
    )
    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    print(
        "Recorded skill handoff: "
        f"{record['skill']} ({record['mode']}) -> "
        f"{Path(args.workspace) / 'project' / 'skill_handoffs.jsonl'}"
    )
    return 0


def _add_project_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        help="Project directory; defaults to discovery from the current directory",
    )


def _project_from_args(args: argparse.Namespace) -> Project:
    return resolve_project(getattr(args, "project", None))


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
