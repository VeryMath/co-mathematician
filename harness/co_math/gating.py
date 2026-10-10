from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from .schemas import GateResult
from .workspace import find_goal, load_goals, read_yaml


def check_goal_approval(workspace: str | Path, goal_id: str | None = None) -> GateResult:
    goals_data = load_goals(workspace)
    goals = goals_data.get("goals", [])
    issues: list[str] = []

    if goal_id is not None:
        goal = find_goal(goals_data, goal_id)
        if goal is None:
            issues.append(f"Goal {goal_id} was not found.")
        elif str(goal.get("status", "")).lower() != "approved":
            issues.append(
                f"Goal {goal_id} is not approved (status: {goal.get('status', 'missing')})."
            )
    elif not any(str(goal.get("status", "")).lower() == "approved" for goal in goals):
        issues.append("No approved goals are recorded.")

    return GateResult("goal_approval", not issues, issues, {"goal_id": goal_id})


def check_workstream_completion(
    workspace: str | Path, workstream_id: str | None = None
) -> GateResult:
    root = Path(workspace)
    workstreams = _selected_workstreams(root, workstream_id)
    issues: list[str] = []
    details: dict[str, Any] = {"workstreams": [path.name for path in workstreams]}

    if not workstreams:
        issues.append("No workstream directories were found.")

    for workstream in workstreams:
        issues.extend(_workstream_issues(workstream))

    return GateResult("workstream_completion", not issues, issues, details)


def check_final_render(workspace: str | Path) -> GateResult:
    root = Path(workspace)
    approved = []
    rejected = {}
    for workstream in _selected_workstreams(root, None):
        gate = check_workstream_completion(root, workstream.name)
        if gate.passed:
            approved.append(workstream.name)
        else:
            rejected[workstream.name] = gate.issues

    issues = [] if approved else ["No reviewed workstream reports are ready to render."]
    return GateResult(
        "final_render",
        not issues,
        issues,
        {"approved_workstreams": approved, "rejected_workstreams": rejected},
    )


def check_gate(
    workspace: str | Path,
    gate: str,
    *,
    goal_id: str | None = None,
    workstream_id: str | None = None,
) -> GateResult:
    if gate == "goal_approval":
        return check_goal_approval(workspace, goal_id)
    if gate == "workstream_completion":
        return check_workstream_completion(workspace, workstream_id)
    if gate == "final_render":
        return check_final_render(workspace)
    raise ValueError(f"Unsupported gate: {gate}")


def _selected_workstreams(root: Path, workstream_id: str | None) -> list[Path]:
    workstreams_dir = root / "workstreams"
    if workstreams_dir.is_symlink():
        return []
    if workstream_id:
        if Path(workstream_id).name != workstream_id or workstream_id in {".", ".."}:
            return []
        path = workstreams_dir / workstream_id
        return [path] if path.is_dir() and not path.is_symlink() else []
    if not workstreams_dir.exists():
        return []
    return sorted(
        path
        for path in workstreams_dir.iterdir()
        if path.is_dir() and _is_workstream_dir(path)
    )


def _workstream_issues(workstream: Path) -> list[str]:
    label = workstream.name
    issues: list[str] = []
    status = _load_status(workstream)
    report = workstream / "report.md"
    reviews = _load_reviews(workstream)

    if not status:
        issues.append(f"{label}: status.yaml is missing or invalid.")
    elif str(status.get("status", "")).lower() != "complete":
        issues.append(f"{label}: status.yaml is not marked complete.")

    if not _regular_file(report):
        issues.append(f"{label}: report.md is missing.")

    report_hash = _sha256(report) if _regular_file(report) else None

    approved_reviewers = [
        str(review.get("reviewer", "")).strip()
        for path, review in reviews
        if review.get("approved") is True and isinstance(review.get("reviewer"), str)
    ]
    coordinator_value = status.get("coordinator")
    coordinator = coordinator_value.strip() if isinstance(coordinator_value, str) else ""
    independent_approvals = [
        reviewer for reviewer in approved_reviewers if reviewer != coordinator
    ]
    if not independent_approvals:
        issues.append(f"{label}: missing independent reviewer approval.")

    resolved_reviews = _resolved_review_names(reviews)
    for path, review in reviews:
        if review.get("report_sha256") != report_hash:
            issues.append(f"{label}: review in {path.name} is not bound to the current report.")
        if review.get("severity") == "blocking" and not _review_is_resolved(
            path, review, resolved_reviews
        ):
            issues.append(f"{label}: blocking review in {path.name}.")

    if _regular_file(report):
        text = report.read_text(encoding="utf-8")
        if not _has_section(text, "Provenance"):
            issues.append(f"{label}: report.md is missing a Provenance section.")
        if not _has_section(text, "Uncertainty"):
            issues.append(f"{label}: report.md is missing an Uncertainty section.")
        if not _has_section(text, "Failed Explorations"):
            issues.append(f"{label}: report.md is missing a Failed Explorations section.")

    return issues


def _load_status(workstream: Path) -> dict[str, Any]:
    path = workstream / "status.yaml"
    if _regular_file(path):
        data = read_yaml(path)
        return data if isinstance(data, dict) else {}
    return {}


def _load_reviews(workstream: Path) -> list[tuple[Path, dict[str, Any]]]:
    reviews_dir = workstream / "reviews"
    if reviews_dir.is_symlink() or not reviews_dir.is_dir():
        return []
    reviews = []
    for path in sorted(reviews_dir.glob("*.json")):
        if not _regular_file(path):
            reviews.append((path, {"_invalid": "Review must be a regular file."}))
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("review must be a JSON object")
            required = {
                "approved",
                "severity",
                "issue_type",
                "reviewer",
                "comment",
                "suggested_fix",
                "report_sha256",
            }
            optional = {"resolves", "resolved"}
            if not required.issubset(data) or set(data) - required - optional:
                raise ValueError("review has missing or unknown fields")
            if not isinstance(data["approved"], bool) or data["severity"] not in {"blocking", "major", "minor", "none"}:
                raise ValueError("review has invalid approval or severity")
            if not all(
                isinstance(data[field], str) and data[field].strip()
                for field in (
                    "issue_type",
                    "reviewer",
                    "comment",
                    "suggested_fix",
                    "report_sha256",
                )
            ):
                raise ValueError("review text fields must be non-empty strings")
            report_sha256 = data["report_sha256"]
            if not re.fullmatch(r"[0-9a-f]{64}", report_sha256):
                raise ValueError("report_sha256 must be a SHA-256 hex digest")
            if "resolved" in data and not isinstance(data["resolved"], bool):
                raise ValueError("resolved must be a boolean")
            if "resolves" in data:
                resolves = data["resolves"]
                if not isinstance(resolves, list) or not all(
                    isinstance(target, str)
                    and target.endswith(".json")
                    and Path(target).name == target
                    and target not in {".", ".."}
                    for target in resolves
                ):
                    raise ValueError("resolves must contain review filenames in this directory")
        except (json.JSONDecodeError, ValueError):
            data = {"_invalid": "Review JSON is invalid or has an invalid schema.", "severity": "blocking"}
        reviews.append((path, data))
    return reviews


def _is_workstream_dir(path: Path) -> bool:
    return any(
        (path / marker).exists()
        for marker in ("status.yaml", "WORKSTREAM.md", "report.md", "messages.jsonl")
    )


def _resolved_review_names(reviews: list[tuple[Path, dict[str, Any]]]) -> set[str]:
    resolved: set[str] = set()
    review_names = {
        key
        for path, _review in reviews
        for key in (path.name, path.stem)
    }
    for path, review in reviews:
        if review.get("resolved") is True:
            resolved.update((path.name, path.stem))
        resolves = review.get("resolves", [])
        if not isinstance(resolves, list):
            continue
        for target in resolves:
            if not isinstance(target, str) or target not in review_names:
                continue
            target_path = Path(target.strip())
            resolved.update((target.strip(), target_path.name, target_path.stem))
    return resolved


def _review_is_resolved(
    path: Path, review: dict[str, Any], resolved_reviews: set[str]
) -> bool:
    return (
        review.get("resolved") is True
        or path.name in resolved_reviews
        or path.stem in resolved_reviews
    )


def _has_section(text: str, section: str) -> bool:
    expected = f"## {section}".lower()
    return any(line.strip().lower() == expected for line in text.splitlines())


def _regular_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
