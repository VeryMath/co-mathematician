from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .context import project_snapshot, render_resume_text
from .gating import check_gate
from .messages import append_message
from .opencode import (
    inspect_opencode_adapter,
    install_opencode_adapter,
    remove_opencode_adapter,
)
from .project import CORE_VERSION, ResolvedProject, resolve_project
from .registry import config_home, list_registered_projects, load_user_config
from .reports import render_final
from .reviews import submit_review
from .scaffold import adopt_project, create_project
from .schemas import (
    VALID_MESSAGE_TYPES,
    VALID_REVIEW_ISSUE_TYPES,
    VALID_REVIEW_SEVERITIES,
    VALID_SKILL_HANDOFF_MODES,
    VALID_WORKSTREAM_KINDS,
)
from .skill_handoff import record_skill_handoff
from .skills import refresh_skill_registry, suggest_skills
from .workspace import (
    VALID_LANGUAGE_POLICIES,
    approve_goal,
    complete_workstream,
    init_workspace,
    new_workstream,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="co-math")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Create an independent Co-Math project")
    new_parser.add_argument("name")
    new_parser.add_argument("--path")
    new_parser.add_argument("--language", choices=VALID_LANGUAGE_POLICIES)
    new_parser.add_argument("--no-git", action="store_true")
    new_parser.add_argument("--json", action="store_true")
    new_parser.set_defaults(func=_cmd_new_project)

    list_parser = subparsers.add_parser("list", help="List registered Co-Math projects")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=_cmd_list_projects)

    status_parser = subparsers.add_parser("status", help="Inspect project state without writing")
    _add_project_target(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=_cmd_project_status)

    resume_parser = subparsers.add_parser("resume", help="Reconstruct project context from files")
    _add_project_target(resume_parser)
    resume_parser.add_argument("--json", action="store_true")
    resume_parser.set_defaults(func=_cmd_project_resume)

    adopt_parser = subparsers.add_parser("adopt", help="Add an existing workspace as a project")
    adopt_parser.add_argument("path")
    adopt_parser.add_argument("--json", action="store_true")
    adopt_parser.set_defaults(func=_cmd_adopt_project)

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose Core and project state")
    doctor_parser.add_argument("--project")
    doctor_parser.add_argument("--opencode-config-dir")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=_cmd_doctor)

    install_opencode_parser = subparsers.add_parser(
        "install-opencode",
        help="Install global Co-Math tools for OpenCode",
    )
    install_opencode_parser.add_argument("--config-dir")
    install_opencode_parser.add_argument("--cli-path")
    install_opencode_parser.add_argument("--projects-home")
    install_opencode_parser.add_argument(
        "--allow-root",
        action="append",
        dest="allowed_roots",
    )
    install_opencode_parser.add_argument("--json", action="store_true")
    install_opencode_parser.set_defaults(func=_cmd_install_opencode)

    uninstall_opencode_parser = subparsers.add_parser(
        "uninstall-opencode",
        help="Remove managed global Co-Math tools from OpenCode",
    )
    uninstall_opencode_parser.add_argument("--config-dir")
    uninstall_opencode_parser.add_argument("--json", action="store_true")
    uninstall_opencode_parser.set_defaults(func=_cmd_uninstall_opencode)

    init_parser = subparsers.add_parser("init", help="Initialize workspace scaffold")
    init_parser.add_argument("--workspace", default="workspace")
    init_parser.set_defaults(func=_cmd_init)

    message_parser = subparsers.add_parser("append-message", help="Append JSONL message")
    _add_project_target(message_parser)
    message_parser.add_argument("--sender", required=True)
    message_parser.add_argument("--recipient", required=True)
    message_parser.add_argument("--type", dest="message_type", choices=VALID_MESSAGE_TYPES, required=True)
    message_parser.add_argument("--content", required=True)
    message_parser.add_argument("--provenance", action="append", default=[])
    message_parser.add_argument("--uncertainty", action="append", default=[])
    message_parser.set_defaults(func=_cmd_append_message)

    approve_parser = subparsers.add_parser(
        "approve-goal", help="Record explicit user approval for a draft goal"
    )
    _add_project_target(approve_parser)
    approve_parser.add_argument("--goal-id", required=True)
    approve_parser.add_argument("--approved-by", required=True)
    approve_parser.add_argument("--approval-id", required=True)
    approve_parser.set_defaults(func=_cmd_approve_goal)

    ws_parser = subparsers.add_parser("new-workstream", help="Create approved-goal workstream")
    _add_project_target(ws_parser)
    ws_parser.add_argument("--goal-id", required=True)
    ws_parser.add_argument("--title", required=True)
    ws_parser.add_argument("--kind", choices=VALID_WORKSTREAM_KINDS, required=True)
    ws_parser.add_argument("--author-run-id", required=True)
    ws_parser.set_defaults(func=_cmd_new_workstream)

    review_parser = subparsers.add_parser(
        "submit-review", help="Validate and append a report-bound reviewer record"
    )
    _add_project_target(review_parser)
    review_parser.add_argument("--workstream-id", required=True)
    review_parser.add_argument("--reviewer", required=True)
    review_parser.add_argument("--reviewer-run-id", required=True)
    approval_group = review_parser.add_mutually_exclusive_group(required=True)
    approval_group.add_argument("--approved", dest="approved", action="store_true")
    approval_group.add_argument("--rejected", dest="approved", action="store_false")
    review_parser.add_argument(
        "--severity", choices=VALID_REVIEW_SEVERITIES, required=True
    )
    review_parser.add_argument(
        "--issue-type", choices=VALID_REVIEW_ISSUE_TYPES, required=True
    )
    review_parser.add_argument("--comment", required=True)
    review_parser.add_argument("--suggested-fix", default="")
    review_parser.add_argument("--resolves", action="append", default=[])
    review_parser.add_argument("--checked-artifact", action="append", default=[])
    review_parser.add_argument("--review-id")
    review_parser.set_defaults(func=_cmd_submit_review)

    complete_parser = subparsers.add_parser(
        "complete-workstream", help="Freeze a reviewed report and complete its lifecycle"
    )
    _add_project_target(complete_parser)
    complete_parser.add_argument("--workstream-id", required=True)
    complete_parser.set_defaults(func=_cmd_complete_workstream)

    gate_parser = subparsers.add_parser("check-gate", help="Check a harness gate")
    _add_project_target(gate_parser)
    gate_parser.add_argument(
        "--gate",
        choices=(
            "goal_approval",
            "workstream_readiness",
            "workstream_completion",
            "final_render",
        ),
        required=True,
    )
    gate_parser.add_argument("--goal-id")
    gate_parser.add_argument("--workstream-id")
    gate_parser.add_argument("--json", action="store_true")
    gate_parser.set_defaults(func=_cmd_check_gate)

    render_parser = subparsers.add_parser(
        "render-final", help="Render a generated draft from reviewed snapshots"
    )
    _add_project_target(render_parser)
    render_parser.set_defaults(func=_cmd_render_final)

    refresh_skills_parser = subparsers.add_parser(
        "refresh-skills",
        help="Scan project-local skills and write workspace skill registry",
    )
    _add_project_target(refresh_skills_parser)
    refresh_skills_parser.add_argument("--repo-root")
    refresh_skills_parser.add_argument("--json", action="store_true")
    refresh_skills_parser.set_defaults(func=_cmd_refresh_skills)

    suggest_skills_parser = subparsers.add_parser(
        "suggest-skills",
        help="Suggest project-local skills for a query",
    )
    _add_project_target(suggest_skills_parser)
    suggest_skills_parser.add_argument("--repo-root")
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
    _add_project_target(handoff_parser)
    handoff_parser.add_argument("--skill", required=True)
    handoff_parser.add_argument("--mode", choices=VALID_SKILL_HANDOFF_MODES, required=True)
    handoff_parser.add_argument("--reason", required=True)
    handoff_parser.add_argument("--query", default="")
    handoff_parser.add_argument("--skill-path", default="")
    handoff_parser.add_argument("--status", default="active")
    handoff_parser.add_argument("--json", action="store_true")
    handoff_parser.set_defaults(func=_cmd_skill_handoff)

    return parser


def _add_project_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace")
    parser.add_argument("--project")


def _cmd_new_project(args: argparse.Namespace) -> int:
    result = create_project(
        args.name,
        path=args.path,
        language=args.language,
        initialize_git=not args.no_git,
    )
    snapshot = project_snapshot(result.project)
    output = {
        "project_id": result.project.manifest.project_id,
        "name": result.project.manifest.name,
        "path": str(result.project.root),
        "workspace": str(result.project.workspace),
        "status": snapshot["status"],
        "next_gate": snapshot["next_gate"],
        "warnings": list(result.warnings),
        "next_step": f"Open {result.project.root} in your coding-agent GUI.",
    }
    if args.json:
        _print_json(output)
    else:
        print(f"Created Co-Math project: {output['name']}")
        print(f"Path: {output['path']}")
        print(f"Status: {output['status']}")
        for warning in result.warnings:
            print(f"WARNING: {warning}")
        print(output["next_step"])
    return 0


def _cmd_list_projects(args: argparse.Namespace) -> int:
    projects = _listed_projects()
    if args.json:
        _print_json(projects)
        return 0
    if not projects:
        print("No registered Co-Math projects.")
        return 0
    for project in projects:
        print(f"{project.get('name') or project['project_id']} [{project['status']}]")
        print(f"  {project['path']}")
    return 0


def _cmd_project_status(args: argparse.Namespace) -> int:
    snapshot = project_snapshot(_required_project(args))
    if args.json:
        _print_json(snapshot)
    else:
        print(f"{snapshot['project']['name']}: {snapshot['status']}")
        print(f"Path: {snapshot['project']['path']}")
        print(f"Next gate: {snapshot['next_gate']}")
    return 0 if snapshot["status"] != "invalid" else 1


def _cmd_project_resume(args: argparse.Namespace) -> int:
    snapshot = project_snapshot(_required_project(args))
    if args.json:
        _print_json(snapshot)
    else:
        print(render_resume_text(snapshot))
    return 0 if snapshot["status"] != "invalid" else 1


def _cmd_adopt_project(args: argparse.Namespace) -> int:
    result = adopt_project(args.path)
    snapshot = project_snapshot(result.project)
    output = {
        "project_id": result.project.manifest.project_id,
        "name": result.project.manifest.name,
        "path": str(result.project.root),
        "workspace": str(result.project.workspace),
        "status": snapshot["status"],
        "next_gate": snapshot["next_gate"],
        "warnings": list(result.warnings),
    }
    if args.json:
        _print_json(output)
    else:
        print(f"Adopted Co-Math project: {output['name']}")
        print(f"Path: {output['path']}")
        for warning in result.warnings:
            print(f"WARNING: {warning}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    config = load_user_config()
    issues: list[str] = []
    project_data: dict[str, object] | None = None
    try:
        project = _optional_project(args)
        if project is not None:
            snapshot = project_snapshot(project)
            project_data = {
                "project_id": project.manifest.project_id,
                "name": project.manifest.name,
                "path": str(project.root),
                "workspace": str(project.workspace),
                "status": snapshot["status"],
            }
            if snapshot["status"] == "invalid":
                issues.extend(str(issue) for issue in snapshot["errors"])
    except Exception as exc:
        issues.append(str(exc))
    opencode_data: dict[str, object]
    try:
        opencode_data = inspect_opencode_adapter(
            config_dir=args.opencode_config_dir,
        )
        if opencode_data["installed"] and not opencode_data["healthy"]:
            issues.extend(
                f"OpenCode: {issue}" for issue in opencode_data["issues"]
            )
    except Exception as exc:
        opencode_data = {
            "installed": False,
            "healthy": False,
            "issues": [str(exc)],
        }
        issues.append(f"OpenCode: {exc}")
    output = {
        "ok": not issues,
        "core_version": CORE_VERSION,
        "config_home": str(config_home()),
        "projects_home": str(config.projects_home),
        "allowed_project_roots": [str(path) for path in config.allowed_project_roots],
        "project": project_data,
        "opencode": opencode_data,
        "issues": issues,
    }
    if args.json:
        _print_json(output)
    else:
        print(f"Core {CORE_VERSION}: {'OK' if output['ok'] else 'ISSUES'}")
        if project_data is not None:
            print(f"Project: {project_data['path']} [{project_data['status']}]")
        if opencode_data["installed"]:
            state = "OK" if opencode_data["healthy"] else "ISSUES"
            print(f"OpenCode adapter: {state}")
        else:
            print("OpenCode adapter: not installed")
        for issue in issues:
            print(f"- {issue}")
    return 0 if output["ok"] else 1


def _cmd_install_opencode(args: argparse.Namespace) -> int:
    current = load_user_config()
    cli_path = args.cli_path or shutil.which("co-math")
    if not cli_path:
        raise ValueError(
            "Could not find the co-math executable; pass its absolute path with "
            "--cli-path PATH."
        )
    projects_home = (
        Path(args.projects_home).expanduser()
        if args.projects_home
        else current.projects_home
    )
    if args.allowed_roots:
        allowed_roots = [Path(path).expanduser() for path in args.allowed_roots]
    elif args.projects_home:
        allowed_roots = [projects_home]
    else:
        allowed_roots = list(current.allowed_project_roots)
    result = install_opencode_adapter(
        config_dir=args.config_dir,
        cli_path=cli_path,
        projects_home=projects_home,
        allowed_roots=allowed_roots,
    )
    output = {
        "installed": True,
        "config_dir": str(result.config_dir),
        "tool_files": [str(path) for path in result.tool_files],
        "runner_file": str(result.runner_file),
        "config_file": str(result.config_file),
        "manifest_file": str(result.manifest_file),
        "next_step": "Restart OpenCode, then ask it to create or list Co-Math projects.",
    }
    if args.json:
        _print_json(output)
    else:
        print(f"Installed Co-Math OpenCode tools in: {result.config_dir}")
        print(output["next_step"])
    return 0


def _cmd_uninstall_opencode(args: argparse.Namespace) -> int:
    result = remove_opencode_adapter(config_dir=args.config_dir)
    output = {
        "installed": False,
        "config_dir": str(result.config_dir),
        "removed_files": [str(path) for path in result.removed_files],
        "preserved_files": [str(path) for path in result.preserved_files],
        "warnings": list(result.warnings),
    }
    if args.json:
        _print_json(output)
    else:
        print(f"Removed managed Co-Math OpenCode tools from: {result.config_dir}")
        for warning in result.warnings:
            print(f"WARNING: {warning}")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    root = init_workspace(args.workspace)
    print(f"Initialized workspace: {Path(root)}")
    return 0


def _cmd_append_message(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    record = append_message(
        workspace,
        sender=args.sender,
        recipient=args.recipient,
        message_type=args.message_type,
        content=args.content,
        provenance=args.provenance,
        uncertainty=args.uncertainty,
    )
    print(json.dumps(record, ensure_ascii=False))
    return 0


def _cmd_approve_goal(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    goal = approve_goal(
        workspace,
        goal_id=args.goal_id,
        approved_by=args.approved_by,
        approval_id=args.approval_id,
    )
    print(
        f"Approved goal: {goal['id']} "
        f"(approval_id: {goal['approval_id']})"
    )
    return 0


def _cmd_new_workstream(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    path = new_workstream(
        workspace,
        goal_id=args.goal_id,
        title=args.title,
        kind=args.kind,
        author_run_id=args.author_run_id,
    )
    print(f"Created workstream: {path}")
    return 0


def _cmd_submit_review(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    path, record = submit_review(
        workspace,
        workstream_id=args.workstream_id,
        reviewer=args.reviewer,
        reviewer_run_id=args.reviewer_run_id,
        approved=args.approved,
        severity=args.severity,
        issue_type=args.issue_type,
        comment=args.comment,
        suggested_fix=args.suggested_fix,
        resolves=args.resolves,
        checked_artifacts=args.checked_artifact,
        review_id=args.review_id,
    )
    print(
        f"Submitted review: {path} "
        f"(report_sha256: {record['report_sha256']})"
    )
    return 0


def _cmd_complete_workstream(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    snapshot = complete_workstream(
        workspace,
        workstream_id=args.workstream_id,
    )
    print(f"Completed workstream with reviewed snapshot: {snapshot}")
    return 0


def _cmd_check_gate(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    result = check_gate(
        workspace,
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
    path = render_final(_workspace_for(args))
    print(f"Rendered generated working-paper draft: {path}")
    return 0


def _cmd_refresh_skills(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    registry = refresh_skill_registry(workspace, repo_root=_repo_root_for(args))
    if args.json:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
        return 0
    print(
        "Refreshed project skill registry: "
        f"{workspace / 'project' / 'skill_registry.json'}"
    )
    for skill in registry["skills"]:
        print(f"- {skill['name']}: {skill['path']}")
    return 0


def _cmd_suggest_skills(args: argparse.Namespace) -> int:
    workspace = _workspace_for(args)
    matches = suggest_skills(
        workspace,
        args.query,
        repo_root=_repo_root_for(args),
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
    workspace = _workspace_for(args)
    record = record_skill_handoff(
        workspace,
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
        f"{workspace / 'project' / 'skill_handoffs.jsonl'}"
    )
    return 0


def _workspace_for(args: argparse.Namespace) -> Path:
    explicit_workspace = getattr(args, "workspace", None)
    if explicit_workspace:
        return Path(explicit_workspace).expanduser()
    project = _optional_project(args)
    return project.workspace if project is not None else Path("workspace")


def _optional_project(args: argparse.Namespace) -> ResolvedProject | None:
    return resolve_project(
        project=getattr(args, "project", None),
        cwd=Path.cwd(),
    )


def _required_project(args: argparse.Namespace) -> ResolvedProject:
    explicit_workspace = getattr(args, "workspace", None)
    if explicit_workspace:
        project = resolve_project(workspace=explicit_workspace)
    else:
        project = _optional_project(args)
    if project is None:
        raise ValueError(
            "No Co-Math project was found. Open a directory containing co-math.toml "
            "or pass --project PATH."
        )
    return project


def _repo_root_for(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "repo_root", None)
    if explicit:
        return Path(explicit).expanduser()
    explicit_workspace = getattr(args, "workspace", None)
    if explicit_workspace:
        workspace_project = resolve_project(workspace=explicit_workspace)
        if workspace_project is not None:
            return workspace_project.root
        return Path(".")
    project = _optional_project(args)
    return project.root if project is not None else Path(".")


def _listed_projects() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for entry in list_registered_projects():
        item: dict[str, object] = dict(entry)
        registry_status = str(entry["registry_status"])
        if registry_status != "valid":
            item["status"] = registry_status
            item["next_gate"] = "adopt" if registry_status == "stale" else "doctor"
            results.append(item)
            continue
        try:
            project = resolve_project(project=str(entry["path"]))
            if project is None:  # pragma: no cover - valid entries always resolve
                raise ValueError("Project could not be resolved")
            snapshot = project_snapshot(project)
            item["status"] = snapshot["status"]
            item["next_gate"] = snapshot["next_gate"]
        except Exception as exc:
            item["status"] = "invalid"
            item["next_gate"] = "doctor"
            item["error"] = str(exc)
        results.append(item)
    return results


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
