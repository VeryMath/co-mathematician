from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .completion import (
    COMPLETION_MANIFEST_FILENAME,
    COMPLETION_MANIFEST_PATH,
    completion_manifest_schema_issues,
)
from .schemas import VALID_WORKSTREAM_KINDS, utc_timestamp
from .storage import (
    atomic_write_json,
    atomic_write_text,
    bytes_sha256,
    file_sha256,
    resolve_managed_directory,
    resolve_managed_file,
    workspace_lock,
)

try:
    import yaml  # type: ignore[import-untyped]
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
- invalid_workstreams: 0
- active_skill_handoffs: 0
- final_output: not_started

No mathematical research project has started.
"""

GOAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
WORKSTREAM_ID_PATTERN = re.compile(
    r"^WS-(?P<goal>[A-Za-z0-9][A-Za-z0-9_-]{0,63})-"
    r"(?P<sequence>[0-9]{3,})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)


def init_workspace(workspace: str | Path) -> Path:
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    project = resolve_managed_directory(root, "project", create=True)
    resolve_managed_directory(root, "workstreams", create=True)
    resolve_managed_directory(root, "final", create=True)

    _write_text_if_missing(project / "PROJECT.md", DEFAULT_PROJECT_MD)
    _write_yaml_if_missing(project / "GOALS.yaml", DEFAULT_GOALS)
    _write_text_if_missing(project / "PROJECT_STATUS.md", DEFAULT_PROJECT_STATUS)
    (project / "messages.jsonl").touch(exist_ok=True)
    (project / "skill_handoffs.jsonl").touch(exist_ok=True)
    with workspace_lock(root):
        _refresh_project_status_unlocked(root)
    return root


def new_workstream(
    workspace: str | Path,
    *,
    goal_id: str,
    title: str,
    kind: str,
    author_run_id: str = "project-coordinator",
) -> Path:
    if kind not in VALID_WORKSTREAM_KINDS:
        raise ValueError(f"Unsupported workstream kind: {kind}")
    validate_goal_id(goal_id)
    if not author_run_id.strip():
        raise ValueError("author_run_id must not be empty")

    root = Path(workspace)
    with workspace_lock(root):
        goals = load_goals(root)
        matching_goals = find_goals(goals, goal_id)
        if not matching_goals:
            raise ValueError(f"Goal {goal_id} was not found")
        if len(matching_goals) > 1:
            raise ValueError(f"Goal registry contains duplicate goal id: {goal_id}")
        goal = matching_goals[0]
        approval_issues = goal_approval_issues(goals, goal)
        if approval_issues:
            raise ValueError(approval_issues[0])

        workstreams_dir = resolve_managed_directory(root, "workstreams", create=True)
        workstream_id = _next_workstream_id(workstreams_dir, goal_id, title)
        path = workstreams_dir / workstream_id
        path.mkdir(parents=True, exist_ok=False)

        try:
            for dirname in ("artifacts", "failures", "reviews", "reviewed"):
                (path / dirname).mkdir(exist_ok=True)

            status = {
                "schema_version": 1,
                "id": workstream_id,
                "goal_id": goal_id,
                "title": title,
                "kind": kind,
                "status": "active",
                "coordinator": "workstream_coordinator",
                "author_run_id": author_run_id,
                "created_at": utc_timestamp(),
            }
            write_yaml(path / "status.yaml", status)
            (path / "messages.jsonl").touch()
            atomic_write_text(path / "WORKSTREAM.md", _workstream_md(status))
            atomic_write_text(path / "plan.md", "# Plan\n\nPending coordinator plan.\n")
            atomic_write_text(path / "notes.md", "# Notes\n\nNo notes yet.\n")

            workstream_refs = goal.setdefault("workstreams", [])
            if workstream_id not in workstream_refs:
                workstream_refs.append(workstream_id)
                save_goals(root, goals)
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            raise

        _refresh_project_status_unlocked(root)
        return path


def approve_goal(
    workspace: str | Path,
    *,
    goal_id: str,
    approved_by: str,
    approval_id: str,
) -> dict[str, Any]:
    validate_goal_id(goal_id)
    if not approved_by.strip():
        raise ValueError("approved_by must not be empty")
    if not approval_id.strip():
        raise ValueError("approval_id must not be empty")

    root = Path(workspace)
    with workspace_lock(root):
        goals = load_goals(root)
        matching_goals = find_goals(goals, goal_id)
        if not matching_goals:
            raise ValueError(f"Goal {goal_id} was not found")
        if len(matching_goals) > 1:
            raise ValueError(f"Goal registry contains duplicate goal id: {goal_id}")
        goal = matching_goals[0]
        if goal.get("status") == "approved":
            if (
                goal.get("approval_id") == approval_id
                and goal.get("approved_by") == approved_by
            ):
                _refresh_project_status_unlocked(root)
                return dict(goal)
            raise ValueError(f"Goal {goal_id} is already approved")
        for existing_goal in goals.get("goals", []):
            if not isinstance(existing_goal, dict) or existing_goal is goal:
                continue
            if existing_goal.get("approval_id") == approval_id:
                raise ValueError(f"approval_id is already used: {approval_id}")
        policy_status = str(goals.get("language_policy", {}).get("status", ""))
        if policy_status in {"", "pending", "pending_user_choice"}:
            raise ValueError("Language policy must be selected before goal approval")
        research_status = str(goals.get("research_question", {}).get("status", ""))
        if research_status in {"", "onboarding", "draft"}:
            raise ValueError("Research question must be approved before goal approval")

        goal.update(
            {
                "status": "approved",
                "approved_by": approved_by,
                "approved_at": utc_timestamp(),
                "approval_id": approval_id,
            }
        )
        goal.setdefault("workstreams", [])
        save_goals(root, goals)
        _refresh_project_status_unlocked(root)
        return dict(goal)


def complete_workstream(
    workspace: str | Path,
    *,
    workstream_id: str,
) -> Path:
    from .gating import check_workstream_completion, check_workstream_readiness

    root = Path(workspace)
    with workspace_lock(root):
        workstream = resolve_workstream_path(root, workstream_id)
        status_path = resolve_managed_file(workstream, "status.yaml")
        status = read_yaml(status_path)
        if not isinstance(status, dict):
            raise ValueError(f"Workstream {workstream_id} has invalid status.yaml")

        if status.get("status") == "complete":
            completed_gate = check_workstream_completion(root, workstream_id)
            if not completed_gate.passed:
                raise ValueError("; ".join(completed_gate.issues))
            _refresh_project_status_unlocked(root)
            return workstream / str(status["reviewed_snapshot"])

        reviews_dir = resolve_managed_directory(workstream, "reviews", create=True)
        reviewed_dir = resolve_managed_directory(workstream, "reviewed", create=True)
        readiness = check_workstream_readiness(root, workstream_id)
        if not readiness.passed:
            raise ValueError("; ".join(readiness.issues))

        report = resolve_managed_file(workstream, "report.md")
        report_bytes = report.read_bytes()
        digest = bytes_sha256(report_bytes)
        snapshot = reviewed_dir / f"report-{digest}.md"
        completed_at = utc_timestamp()
        goals = load_goals(root)
        goal = find_goal(goals, str(status.get("goal_id", "")))
        if goal is None:
            raise ValueError(f"Workstream {workstream_id} has no unique approved goal")

        review_entries = []
        captured_reviews: list[tuple[Path, str, dict[str, Any]]] = []
        for review_path in sorted(reviews_dir.glob("*.json")):
            if (
                review_path.is_symlink()
                or not review_path.is_file()
                or review_path.resolve().parent != reviews_dir
            ):
                raise ValueError(
                    f"Review evidence path is invalid: {review_path.name}"
                )
            review_bytes = review_path.read_bytes()
            review_digest = bytes_sha256(review_bytes)
            review_payload = json.loads(review_bytes)
            captured_reviews.append((review_path, review_digest, review_payload))
            review_entries.append(
                {
                    "path": f"reviews/{review_path.name}",
                    "sha256": review_digest,
                }
            )

        checked_artifacts: dict[str, str] = {}
        for _, _, review_payload in captured_reviews:
            if review_payload.get("report_sha256") != digest:
                continue
            for artifact in review_payload.get("checked_artifacts", []):
                artifact_path = str(artifact["path"])
                artifact_digest = str(artifact["sha256"])
                previous_digest = checked_artifacts.get(artifact_path)
                if previous_digest is not None and previous_digest != artifact_digest:
                    raise ValueError(
                        f"Conflicting checked artifact digests: {artifact_path}"
                    )
                checked_artifacts[artifact_path] = artifact_digest

        manifest = {
            "schema_version": 1,
            "workstream_id": workstream_id,
            "goal_id": str(status["goal_id"]),
            "author_run_id": str(status["author_run_id"]),
            "completed_at": completed_at,
            "goal_approval": {
                "approval_id": str(goal["approval_id"]),
                "approved_by": str(goal["approved_by"]),
                "approved_at": str(goal["approved_at"]),
            },
            "report": {
                "path": snapshot.relative_to(workstream).as_posix(),
                "sha256": digest,
            },
            "reviews": review_entries,
            "checked_artifacts": [
                {"path": path, "sha256": checked_artifacts[path]}
                for path in sorted(checked_artifacts)
            ],
        }
        manifest_issues = completion_manifest_schema_issues(manifest)
        if manifest_issues:
            raise ValueError(
                "Invalid completion manifest: " + "; ".join(manifest_issues)
            )

        final_readiness = check_workstream_readiness(root, workstream_id)
        if not final_readiness.passed:
            raise ValueError("; ".join(final_readiness.issues))

        atomic_write_text(snapshot, report_bytes.decode("utf-8"))
        manifest_path = reviewed_dir / COMPLETION_MANIFEST_FILENAME
        atomic_write_json(manifest_path, manifest)
        if file_sha256(report) != digest:
            raise ValueError("report.md changed during completion")
        for review_path, review_digest, _ in captured_reviews:
            if file_sha256(review_path) != review_digest:
                raise ValueError(
                    f"Review evidence changed during completion: {review_path.name}"
                )
        for artifact_path, artifact_digest in checked_artifacts.items():
            artifact = resolve_managed_file(workstream, artifact_path)
            if file_sha256(artifact) != artifact_digest:
                raise ValueError(
                    f"Checked artifact changed during completion: {artifact_path}"
                )
        status.update(
            {
                "status": "complete",
                "completed_at": completed_at,
                "completed_report_sha256": digest,
                "reviewed_snapshot": snapshot.relative_to(workstream).as_posix(),
                "completion_manifest": COMPLETION_MANIFEST_PATH,
                "completion_manifest_sha256": file_sha256(manifest_path),
            }
        )
        write_yaml(status_path, status)
        _refresh_project_status_unlocked(root)
        return snapshot


def load_goals(workspace: str | Path) -> dict[str, Any]:
    root = Path(workspace)
    try:
        project = resolve_managed_directory(root, "project")
    except ValueError as exc:
        if "missing" in str(exc).lower():
            return json.loads(json.dumps(DEFAULT_GOALS))
        raise
    path = resolve_managed_file(project, "GOALS.yaml", must_exist=False)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_GOALS))
    data = read_yaml(path)
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT_GOALS))
    data.setdefault("goals", [])
    return data


def save_goals(workspace: str | Path, data: dict[str, Any]) -> None:
    project = resolve_managed_directory(workspace, "project", create=True)
    path = resolve_managed_file(project, "GOALS.yaml", must_exist=False)
    write_yaml(path, data)


def goal_approval_issues(
    goals_data: dict[str, Any], goal: dict[str, Any]
) -> list[str]:
    goal_id = str(goal.get("id", "missing"))
    issues: list[str] = []
    if str(goal.get("status", "")).lower() != "approved":
        issues.append(
            f"Goal {goal_id} is not approved (status: {goal.get('status', 'missing')})."
        )
    for field in ("approved_by", "approved_at", "approval_id"):
        if not str(goal.get(field, "")).strip():
            issues.append(f"Goal {goal_id} is missing approval evidence: {field}.")
    if not isinstance(goal.get("workstreams", []), list):
        issues.append(f"Goal {goal_id} has an invalid workstreams registry.")

    policy_status = str(goals_data.get("language_policy", {}).get("status", ""))
    if policy_status in {"", "pending", "pending_user_choice"}:
        issues.append(f"Goal {goal_id} cannot be approved before language policy selection.")
    research_status = str(goals_data.get("research_question", {}).get("status", ""))
    if research_status in {"", "onboarding", "draft"}:
        issues.append(f"Goal {goal_id} cannot be approved before the research question.")
    return issues


def find_goal(goals_data: dict[str, Any], goal_id: str) -> dict[str, Any] | None:
    matches = find_goals(goals_data, goal_id)
    return matches[0] if len(matches) == 1 else None


def find_goals(goals_data: dict[str, Any], goal_id: str) -> list[dict[str, Any]]:
    return [
        goal
        for goal in goals_data.get("goals", [])
        if isinstance(goal, dict) and str(goal.get("id")) == goal_id
    ]


def duplicate_goal_ids(goals_data: dict[str, Any]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for goal in goals_data.get("goals", []):
        if not isinstance(goal, dict):
            continue
        goal_id = str(goal.get("id", ""))
        if goal_id in seen:
            duplicates.add(goal_id)
        seen.add(goal_id)
    return duplicates


def read_yaml(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML is required to read non-JSON YAML files") from exc


def write_yaml(path: str | Path, data: dict[str, Any]) -> None:
    if yaml is not None:
        atomic_write_text(path, yaml.safe_dump(data, sort_keys=False))
        return
    atomic_write_text(path, json.dumps(data, indent=2) + "\n")


def _write_text_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        atomic_write_text(path, text)


def _write_yaml_if_missing(path: Path, data: dict[str, Any]) -> None:
    if not path.exists():
        write_yaml(path, data)


def _next_workstream_id(workstreams_dir: Path, goal_id: str, title: str) -> str:
    slug = _slugify(title)
    prefix = f"WS-{goal_id}-"
    sequences = [
        int(match.group(1))
        for path in workstreams_dir.iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and (match := re.match(rf"^{re.escape(prefix)}([0-9]+)-", path.name))
    ]
    return f"{prefix}{max(sequences, default=0) + 1:03d}-{slug}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "workstream"


def validate_goal_id(goal_id: str) -> None:
    if not GOAL_ID_PATTERN.fullmatch(goal_id):
        raise ValueError(
            "Invalid goal id; use 1-64 ASCII letters, digits, underscores, or hyphens"
        )


def validate_workstream_id(workstream_id: str) -> None:
    if not WORKSTREAM_ID_PATTERN.fullmatch(workstream_id):
        raise ValueError(f"Invalid workstream id: {workstream_id}")


def resolve_workstream_path(
    workspace: str | Path,
    workstream_id: str,
    *,
    must_exist: bool = True,
) -> Path:
    validate_workstream_id(workstream_id)
    workstreams_dir = resolve_managed_directory(workspace, "workstreams")
    candidate = workstreams_dir / workstream_id
    if candidate.is_symlink():
        raise ValueError(f"Workstream path must not be a symlink: {workstream_id}")
    resolved = candidate.resolve()
    if resolved.parent != workstreams_dir:
        raise ValueError(f"Workstream path escapes workspace: {workstream_id}")
    if must_exist and not resolved.is_dir():
        raise ValueError(f"Workstream {workstream_id} was not found")
    return resolved


def refresh_project_status(workspace: str | Path) -> Path:
    root = Path(workspace)
    with workspace_lock(root):
        return _refresh_project_status_unlocked(root)


def _refresh_project_status_unlocked(workspace: str | Path) -> Path:
    root = Path(workspace)
    goals = load_goals(root)
    goal_ids = {
        str(goal.get("id", ""))
        for goal in goals.get("goals", [])
        if isinstance(goal, dict)
    }
    approved_goals = sum(
        len(find_goals(goals, goal_id)) == 1
        and not goal_approval_issues(goals, find_goals(goals, goal_id)[0])
        for goal_id in goal_ids
    )
    active_workstreams = 0
    completed_workstreams = 0
    invalid_workstreams = 0
    workstreams_dir = resolve_managed_directory(root, "workstreams")
    for path in workstreams_dir.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            validate_workstream_id(path.name)
        except ValueError:
            if (path / "status.yaml").exists():
                invalid_workstreams += 1
            continue
        try:
            status_path = resolve_managed_file(
                path,
                "status.yaml",
                must_exist=False,
            )
        except ValueError:
            invalid_workstreams += 1
            continue
        if not status_path.exists():
            continue
        status = read_yaml(status_path)
        if not isinstance(status, dict):
            invalid_workstreams += 1
            continue
        if status.get("status") == "active":
            if not _active_workstream_state_is_valid(path, status, goals):
                invalid_workstreams += 1
                continue
            try:
                reviewed_dir = resolve_managed_directory(path, "reviewed")
            except ValueError:
                invalid_workstreams += 1
                continue
            completion_manifest = reviewed_dir / COMPLETION_MANIFEST_FILENAME
            if completion_manifest.exists() or completion_manifest.is_symlink():
                invalid_workstreams += 1
            else:
                active_workstreams += 1
        elif status.get("status") == "complete":
            from .gating import check_workstream_completion

            if check_workstream_completion(root, path.name).passed:
                completed_workstreams += 1
            else:
                invalid_workstreams += 1
        else:
            invalid_workstreams += 1

    active_skill_handoffs = 0
    handoffs_path = root / "project" / "skill_handoffs.jsonl"
    if handoffs_path.exists():
        for line in handoffs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("status") == "active":
                active_skill_handoffs += 1

    policy_status = str(
        goals.get("language_policy", {}).get("status", "pending_user_choice")
    )
    final_dir = resolve_managed_directory(root, "final")
    generated = final_dir / "generated_draft.md"
    synthesized = final_dir / "working_paper.md"
    final_output = (
        "synthesized" if synthesized.exists() else "generated_draft" if generated.exists() else "not_started"
    )
    phase = "onboarding"
    if approved_goals:
        phase = "research"
    if final_output != "not_started":
        phase = "synthesis"

    text = f"""# Project Status

- phase: {phase}
- language_policy: {policy_status}
- approved_goals: {approved_goals}
- active_workstreams: {active_workstreams}
- completed_workstreams: {completed_workstreams}
- invalid_workstreams: {invalid_workstreams}
- active_skill_handoffs: {active_skill_handoffs}
- final_output: {final_output}
"""
    project = resolve_managed_directory(root, "project")
    output = resolve_managed_file(project, "PROJECT_STATUS.md", must_exist=False)
    atomic_write_text(output, text)
    return output


def _active_workstream_state_is_valid(
    workstream: Path,
    status: dict[str, Any],
    goals: dict[str, Any],
) -> bool:
    if status.get("id") != workstream.name or status.get("schema_version") != 1:
        return False
    if status.get("kind") not in VALID_WORKSTREAM_KINDS:
        return False
    if any(
        not str(status.get(field, "")).strip()
        for field in ("goal_id", "title", "coordinator", "author_run_id", "created_at")
    ):
        return False
    match = WORKSTREAM_ID_PATTERN.fullmatch(workstream.name)
    goal_id = str(status["goal_id"])
    if match is None or match.group("goal") != goal_id:
        return False
    goal = find_goal(goals, goal_id)
    if goal is None or goal_approval_issues(goals, goal):
        return False
    references = goal.get("workstreams", [])
    if not isinstance(references, list) or workstream.name not in references:
        return False
    return not any(
        isinstance(other_goal, dict)
        and other_goal is not goal
        and isinstance(other_goal.get("workstreams"), list)
        and workstream.name in other_goal["workstreams"]
        for other_goal in goals.get("goals", [])
    )


def _workstream_md(status: dict[str, Any]) -> str:
    return f"""# {status["title"]}

- id: {status["id"]}
- goal_id: {status["goal_id"]}
- kind: {status["kind"]}
- status: active

This workstream is a durable artifact directory. It is not complete until report.md
passes independent review and the completion gate.
"""
