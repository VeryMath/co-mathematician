from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from .completion import COMPLETION_MANIFEST_FILENAME
from .storage import (
    atomic_write_json,
    file_sha256,
    resolve_managed_directory,
    resolve_managed_file,
    workspace_lock,
)
from .workspace import (
    find_goal,
    goal_approval_issues,
    load_goals,
    read_yaml,
    resolve_workstream_path,
)


REVIEW_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json$")


@lru_cache(maxsize=1)
def _review_validator() -> Draft202012Validator:
    schema_text = (
        files("harness.co_math.assets")
        .joinpath("reviewer_output_schema.json")
        .read_text(encoding="utf-8")
    )
    schema = json.loads(schema_text)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def review_schema_issues(payload: Any) -> list[str]:
    errors = sorted(
        _review_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    issues = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "review"
        issues.append(f"{location}: {error.message}")
    return issues


def report_sha256(path: str | Path) -> str:
    return file_sha256(path)


def submit_review(
    workspace: str | Path,
    *,
    workstream_id: str,
    reviewer: str,
    reviewer_run_id: str,
    approved: bool,
    severity: str,
    issue_type: str,
    comment: str,
    suggested_fix: str = "",
    resolves: list[str] | None = None,
    checked_artifacts: list[str] | None = None,
    review_id: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    root = Path(workspace)
    with workspace_lock(root):
        workstream = resolve_workstream_path(root, workstream_id)
        status_path = resolve_managed_file(workstream, "status.yaml")
        status = read_yaml(status_path)
        if not isinstance(status, dict):
            raise ValueError(f"Workstream {workstream_id} has invalid status.yaml")
        if status.get("id") != workstream_id:
            raise ValueError(f"Workstream {workstream_id} has mismatched status id")

        reviewed_dir = resolve_managed_directory(workstream, "reviewed", create=True)
        completion_manifest = reviewed_dir / COMPLETION_MANIFEST_FILENAME
        if completion_manifest.exists() or completion_manifest.is_symlink():
            raise ValueError(
                f"Workstream {workstream_id} has a completion bundle and cannot "
                "be treated as active for review submission"
            )
        if status.get("status") != "active":
            raise ValueError(
                f"Workstream {workstream_id} must be active to accept a review"
            )
        goals = load_goals(root)
        goal = find_goal(goals, str(status.get("goal_id", "")))
        if goal is None or goal_approval_issues(goals, goal):
            raise ValueError(
                f"Workstream {workstream_id} is not linked to an approved goal"
            )
        references = goal.get("workstreams", [])
        if not isinstance(references, list) or workstream_id not in references:
            raise ValueError(
                f"Workstream {workstream_id} is not linked from its approved goal"
            )
        author_run_id = str(status.get("author_run_id", ""))
        if not author_run_id:
            raise ValueError(f"Workstream {workstream_id} is missing author_run_id")
        if reviewer_run_id == author_run_id:
            raise ValueError("Reviewer run must be independent from the report author run")

        try:
            report = resolve_managed_file(workstream, "report.md")
        except ValueError as exc:
            raise ValueError(
                f"Workstream {workstream_id} report.md is invalid: {exc}"
            ) from exc
        reviews_dir = resolve_managed_directory(workstream, "reviews", create=True)
        payload: dict[str, Any] = {
            "approved": approved,
            "severity": severity,
            "issue_type": issue_type,
            "reviewer": reviewer,
            "reviewer_run_id": reviewer_run_id,
            "reviewed_at": _next_reviewed_at(reviews_dir),
            "report_sha256": report_sha256(report),
            "comment": comment,
            "suggested_fix": suggested_fix,
            "resolves": resolves or [],
            "checked_artifacts": _checked_artifact_records(
                workstream,
                checked_artifacts or [],
            ),
        }
        schema_issues = review_schema_issues(payload)
        if schema_issues:
            raise ValueError("Invalid reviewer output schema: " + "; ".join(schema_issues))

        filename = review_id or _default_review_id(reviewer)
        if not REVIEW_ID_PATTERN.fullmatch(filename):
            raise ValueError(f"Invalid review id: {filename}")
        output = reviews_dir / filename
        if output.exists() or output.is_symlink():
            raise ValueError(f"Review already exists: {filename}")
        atomic_write_json(output, payload)
        return output, payload


def _default_review_id(reviewer: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", reviewer).strip("-.") or "reviewer"
    return f"{slug}-{uuid.uuid4().hex[:12]}.json"


def _next_reviewed_at(reviews_dir: Path) -> str:
    candidate = datetime.now(timezone.utc)
    latest: datetime | None = None
    for path in reviews_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            value = str(payload.get("reviewed_at", "")).replace("Z", "+00:00")
            reviewed_at = datetime.fromisoformat(value)
            if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
                continue
        except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if latest is None or reviewed_at > latest:
            latest = reviewed_at
    if latest is not None and candidate <= latest:
        candidate = latest + timedelta(microseconds=1)
    return candidate.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _checked_artifact_records(
    workstream: Path,
    checked_artifacts: list[str],
) -> list[dict[str, str]]:
    records = []
    seen: set[str] = set()
    for value in checked_artifacts:
        artifact = resolve_managed_file(workstream, value)
        relative = artifact.relative_to(workstream).as_posix()
        if relative in seen:
            continue
        seen.add(relative)
        records.append({"path": relative, "sha256": file_sha256(artifact)})
    return records
