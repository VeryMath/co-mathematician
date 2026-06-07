from __future__ import annotations

import argparse
import json
from pathlib import Path

from .gating import check_gate
from .messages import append_message
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
    path = render_final(args.workspace)
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


if __name__ == "__main__":
    raise SystemExit(main())
