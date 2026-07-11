from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .completion import (
    COMPLETION_MANIFEST_PATH,
    completion_manifest_schema_issues,
)
from .reviews import report_sha256, review_schema_issues
from .schemas import GateResult, VALID_WORKSTREAM_KINDS
from .storage import file_sha256, resolve_managed_directory, resolve_managed_file
from .workspace import (
    WORKSTREAM_ID_PATTERN,
    duplicate_goal_ids,
    find_goal,
    find_goals,
    goal_approval_issues,
    load_goals,
    read_yaml,
    resolve_workstream_path,
    validate_goal_id,
    validate_workstream_id,
)


def check_goal_approval(workspace: str | Path, goal_id: str | None = None) -> GateResult:
    try:
        goals_data = load_goals(workspace)
    except ValueError as exc:
        return GateResult("goal_approval", False, [str(exc)], {"goal_id": goal_id})
    goals = goals_data.get("goals", [])
    issues: list[str] = []

    if goal_id is not None:
        try:
            validate_goal_id(goal_id)
        except ValueError as exc:
            issues.append(str(exc))
        else:
            matching_goals = find_goals(goals_data, goal_id)
            if not matching_goals:
                issues.append(f"Goal {goal_id} was not found.")
            elif len(matching_goals) > 1:
                issues.append(f"Goal registry contains duplicate goal id: {goal_id}.")
            else:
                issues.extend(goal_approval_issues(goals_data, matching_goals[0]))
    else:
        duplicates = duplicate_goal_ids(goals_data)
        if duplicates:
            issues.append(
                "Goal registry contains duplicate goal ids: "
                + ", ".join(sorted(duplicates))
                + "."
            )
        elif not any(
            isinstance(goal, dict) and not goal_approval_issues(goals_data, goal)
            for goal in goals
        ):
            issues.append("No approved goals with approval evidence are recorded.")

    return GateResult("goal_approval", not issues, issues, {"goal_id": goal_id})


def check_workstream_readiness(
    workspace: str | Path, workstream_id: str | None = None
) -> GateResult:
    return _check_workstreams(
        workspace,
        workstream_id,
        gate_name="workstream_readiness",
        require_completed=False,
    )


def check_workstream_completion(
    workspace: str | Path, workstream_id: str | None = None
) -> GateResult:
    return _check_workstreams(
        workspace,
        workstream_id,
        gate_name="workstream_completion",
        require_completed=True,
    )


def _check_workstreams(
    workspace: str | Path,
    workstream_id: str | None,
    *,
    gate_name: str,
    require_completed: bool,
) -> GateResult:
    root = Path(workspace)
    issues: list[str] = []
    try:
        workstreams = _selected_workstreams(root, workstream_id)
    except ValueError as exc:
        workstreams = []
        issues.append(str(exc))

    details: dict[str, Any] = {"workstreams": [path.name for path in workstreams]}
    if not workstreams and not issues:
        issues.append("No workstream directories were found.")

    for workstream in workstreams:
        issues.extend(
            _workstream_issues(root, workstream, require_completed=require_completed)
        )

    return GateResult(gate_name, not issues, issues, details)


def check_final_render(workspace: str | Path) -> GateResult:
    root = Path(workspace)
    approved = []
    rejected = {}
    snapshots: dict[str, dict[str, str]] = {}
    try:
        workstreams = _selected_workstreams(root, None)
    except ValueError as exc:
        return GateResult("final_render", False, [str(exc)], {})
    for workstream in workstreams:
        gate = check_workstream_completion(root, workstream.name)
        if gate.passed:
            approved.append(workstream.name)
            status_issues: list[str] = []
            status = _load_status(workstream, status_issues)
            if status_issues:
                approved.pop()
                rejected[workstream.name] = status_issues
                continue
            snapshots[workstream.name] = {
                "path": str(status["reviewed_snapshot"]),
                "sha256": str(status["completed_report_sha256"]),
            }
        else:
            rejected[workstream.name] = gate.issues

    issues = [] if approved else ["No reviewed workstream reports are ready to render."]
    return GateResult(
        "final_render",
        not issues,
        issues,
        {
            "approved_workstreams": approved,
            "rejected_workstreams": rejected,
            "snapshots": snapshots,
        },
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
    if gate == "workstream_readiness":
        return check_workstream_readiness(workspace, workstream_id)
    if gate == "workstream_completion":
        return check_workstream_completion(workspace, workstream_id)
    if gate == "final_render":
        return check_final_render(workspace)
    raise ValueError(f"Unsupported gate: {gate}")


def _selected_workstreams(root: Path, workstream_id: str | None) -> list[Path]:
    if workstream_id:
        return [resolve_workstream_path(root, workstream_id)]
    try:
        workstreams_dir = resolve_managed_directory(root, "workstreams")
    except ValueError as exc:
        if "missing" in str(exc).lower():
            return []
        raise
    if not workstreams_dir.exists():
        return []

    workstreams = []
    for path in sorted(workstreams_dir.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            validate_workstream_id(path.name)
        except ValueError:
            continue
        if _is_workstream_dir(path):
            workstreams.append(path.resolve())
    return workstreams


def _workstream_issues(
    root: Path,
    workstream: Path,
    *,
    require_completed: bool,
) -> list[str]:
    label = workstream.name
    issues: list[str] = []
    status = _load_status(workstream, issues)

    if not status:
        issues.append(f"{label}: status.yaml is missing or invalid.")
    if status.get("id") != label:
        issues.append(f"{label}: status id does not match the workstream directory.")

    status_schema_issues = []
    if status.get("schema_version") != 1:
        status_schema_issues.append("schema_version must be 1")
    if status.get("kind") not in VALID_WORKSTREAM_KINDS:
        status_schema_issues.append("kind is invalid")
    for field in ("title", "coordinator", "created_at"):
        if not str(status.get(field, "")).strip():
            status_schema_issues.append(f"{field} is required")
    if status_schema_issues:
        issues.append(
            f"{label}: status schema invalid: " + "; ".join(status_schema_issues) + "."
        )

    goal_id = str(status.get("goal_id", ""))
    match = WORKSTREAM_ID_PATTERN.fullmatch(label)
    if match and match.group("goal") != goal_id:
        issues.append(f"{label}: workstream id does not match status goal_id.")
    try:
        goals = load_goals(root)
    except ValueError as exc:
        goals = {"goals": []}
        issues.append(f"{label}: {exc}")
    goal = find_goal(goals, goal_id) if goal_id else None
    if goal is None:
        issues.append(f"{label}: workstream is not linked to a recorded goal.")
    else:
        issues.extend(f"{label}: {issue}" for issue in goal_approval_issues(goals, goal))
        references = goal.get("workstreams", [])
        if not isinstance(references, list) or label not in references:
            issues.append(f"{label}: approved goal does not reference this workstream.")
        conflicting_goals = [
            str(other_goal.get("id", "missing"))
            for other_goal in goals.get("goals", [])
            if isinstance(other_goal, dict)
            and other_goal is not goal
            and isinstance(other_goal.get("workstreams"), list)
            and label in other_goal["workstreams"]
        ]
        if conflicting_goals:
            issues.append(
                f"{label}: workstream is also referenced by other goals: "
                + ", ".join(conflicting_goals)
                + "."
            )

    status_value = str(status.get("status", ""))
    if require_completed and status_value != "complete":
        issues.append(
            f"{label}: status must be complete before the completion gate can pass."
        )
    if not require_completed and status_value != "active":
        issues.append(
            f"{label}: status must be active before the readiness gate can pass."
        )

    completion_manifest = None
    if require_completed and status_value == "complete":
        completion_manifest = _load_completion_manifest(
            workstream,
            status,
            goal,
            issues,
        )

    report, expected_sha = _reviewed_report(
        workstream,
        status,
        require_completed,
        issues,
        completion_manifest,
    )
    report_text = ""
    if report is None:
        if require_completed and status.get("status") == "complete":
            issues.append(f"{label}: reviewed report snapshot is missing.")
        else:
            issues.append(f"{label}: report.md is missing.")
    else:
        report_text = report.read_text(encoding="utf-8")
        actual_sha = report_sha256(report)
        if expected_sha and actual_sha != expected_sha:
            issues.append(f"{label}: reviewed report sha256 does not match status.")
        expected_sha = actual_sha

    author_run_id = str(status.get("author_run_id", ""))
    if not author_run_id:
        issues.append(f"{label}: status is missing author_run_id.")

    reviews = _load_reviews(workstream, issues, completion_manifest)
    valid_reviews: list[tuple[Path, dict[str, Any]]] = []
    for path, review in reviews:
        schema_issues = review_schema_issues(review)
        if schema_issues:
            issues.append(
                f"{label}: review schema invalid in {path.name}: "
                + "; ".join(schema_issues)
            )
            continue
        artifact_issues = _checked_artifact_issues(workstream, review)
        if artifact_issues:
            issues.extend(f"{label}: {issue}" for issue in artifact_issues)
            continue
        valid_reviews.append((path, review))

    matching_reviews = [
        (path, review)
        for path, review in valid_reviews
        if expected_sha and review.get("report_sha256") == expected_sha
    ]
    if valid_reviews and not matching_reviews and expected_sha:
        issues.append(f"{label}: no review matches the current report sha256.")

    if completion_manifest is not None:
        expected_artifacts = _checked_artifact_map(matching_reviews)
        manifest_artifacts = {
            str(record["path"]): str(record["sha256"])
            for record in completion_manifest.get("checked_artifacts", [])
        }
        if manifest_artifacts != expected_artifacts:
            issues.append(
                f"{label}: completion manifest checked artifact set does not "
                "match current-report reviews."
            )

    independent_approvals = [
        review
        for _, review in matching_reviews
        if review.get("approved") is True
        and review.get("reviewer_run_id") != author_run_id
    ]
    if not independent_approvals:
        issues.append(f"{label}: missing independent reviewer approval.")

    resolved_reviews = _resolved_review_names(matching_reviews, author_run_id)
    for path, review in matching_reviews:
        if review.get("severity") == "blocking" and path.name not in resolved_reviews:
            issues.append(f"{label}: blocking review in {path.name}.")

    if report_text:
        if not _has_section(report_text, "Provenance"):
            issues.append(f"{label}: reviewed report is missing a Provenance section.")
        elif not _section_has_content(report_text, "Provenance"):
            issues.append(f"{label}: reviewed report has an empty Provenance section.")
        if not _has_section(report_text, "Uncertainty"):
            issues.append(f"{label}: reviewed report is missing an Uncertainty section.")
        elif not _section_has_content(report_text, "Uncertainty"):
            issues.append(f"{label}: reviewed report has an empty Uncertainty section.")
        if not _has_section(report_text, "Failed Explorations"):
            issues.append(f"{label}: reviewed report is missing a Failed Explorations section.")
        elif not _section_has_content(report_text, "Failed Explorations"):
            issues.append(
                f"{label}: reviewed report has an empty Failed Explorations section."
            )

    return issues


def _reviewed_report(
    workstream: Path,
    status: dict[str, Any],
    require_completed: bool,
    issues: list[str],
    completion_manifest: dict[str, Any] | None,
) -> tuple[Path | None, str]:
    if require_completed and status.get("status") == "complete":
        report_record = (
            completion_manifest.get("report", {})
            if completion_manifest is not None
            else {}
        )
        snapshot_value = report_record.get("path", status.get("reviewed_snapshot"))
        expected_sha = str(
            report_record.get("sha256", status.get("completed_report_sha256", ""))
        )
        if not isinstance(snapshot_value, str) or not snapshot_value:
            issues.append(f"{workstream.name}: status is missing reviewed_snapshot.")
            return None, expected_sha
        try:
            reviewed_root = resolve_managed_directory(workstream, "reviewed")
            snapshot = resolve_managed_file(workstream, snapshot_value)
        except ValueError as exc:
            issues.append(f"{workstream.name}: {exc}")
            return None, expected_sha
        if snapshot.is_symlink() or snapshot.resolve().parent != reviewed_root:
            issues.append(f"{workstream.name}: reviewed snapshot path is invalid.")
            return None, expected_sha
        return (snapshot.resolve() if snapshot.is_file() else None), expected_sha

    try:
        report = resolve_managed_file(workstream, "report.md", must_exist=False)
    except ValueError as exc:
        issues.append(f"{workstream.name}: {exc}")
        return None, ""
    return (report if report.is_file() else None), ""


def _load_status(workstream: Path, issues: list[str]) -> dict[str, Any]:
    try:
        path = resolve_managed_file(workstream, "status.yaml", must_exist=False)
    except ValueError as exc:
        issues.append(f"{workstream.name}: {exc}")
        return {}
    if not path.exists():
        return {}
    data = read_yaml(path)
    return data if isinstance(data, dict) else {}


def _load_reviews(
    workstream: Path,
    issues: list[str],
    completion_manifest: dict[str, Any] | None,
) -> list[tuple[Path, Any]]:
    try:
        reviews_dir = resolve_managed_directory(workstream, "reviews")
    except ValueError as exc:
        issues.append(f"{workstream.name}: {exc}")
        return []

    if completion_manifest is not None:
        paths = [
            workstream / str(entry["path"])
            for entry in completion_manifest.get("reviews", [])
            if isinstance(entry, dict) and isinstance(entry.get("path"), str)
        ]
    else:
        paths = sorted(reviews_dir.glob("*.json"))

    reviews = []
    for path in paths:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.resolve().parent != reviews_dir
        ):
            issues.append(
                f"{workstream.name}: review evidence path is invalid: {path.name}."
            )
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        reviews.append((path, data))
    return reviews


def _load_completion_manifest(
    workstream: Path,
    status: dict[str, Any],
    goal: dict[str, Any] | None,
    issues: list[str],
) -> dict[str, Any] | None:
    label = workstream.name
    manifest_value = status.get("completion_manifest")
    if manifest_value != COMPLETION_MANIFEST_PATH:
        issues.append(f"{label}: status is missing a valid completion_manifest path.")
        return None

    try:
        reviewed_dir = resolve_managed_directory(workstream, "reviewed")
    except ValueError as exc:
        issues.append(f"{label}: {exc}")
        return None

    manifest_path = workstream / COMPLETION_MANIFEST_PATH
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.resolve().parent != reviewed_dir
    ):
        issues.append(f"{label}: completion manifest path is invalid.")
        return None

    expected_manifest_digest = str(status.get("completion_manifest_sha256", ""))
    actual_manifest_digest = file_sha256(manifest_path)
    if actual_manifest_digest != expected_manifest_digest:
        issues.append(f"{label}: completion manifest digest does not match status.")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        issues.append(f"{label}: completion manifest is not valid JSON.")
        return None

    schema_issues = completion_manifest_schema_issues(manifest)
    if schema_issues:
        issues.append(
            f"{label}: completion manifest schema invalid: "
            + "; ".join(schema_issues)
        )
        return None
    assert isinstance(manifest, dict)

    expected_fields = {
        "workstream_id": status.get("id"),
        "goal_id": status.get("goal_id"),
        "author_run_id": status.get("author_run_id"),
        "completed_at": status.get("completed_at"),
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            issues.append(
                f"{label}: completion manifest {field} does not match status."
            )

    report_record = manifest["report"]
    if report_record["path"] != status.get("reviewed_snapshot"):
        issues.append(f"{label}: completion manifest report path does not match status.")
    if report_record["sha256"] != status.get("completed_report_sha256"):
        issues.append(f"{label}: completion manifest report digest does not match status.")

    if goal is not None:
        approval = manifest["goal_approval"]
        for field in ("approval_id", "approved_by", "approved_at"):
            if approval[field] != goal.get(field):
                issues.append(
                    f"{label}: completion manifest goal approval {field} "
                    "does not match GOALS.yaml."
                )

    try:
        reviews_dir = resolve_managed_directory(workstream, "reviews")
    except ValueError as exc:
        issues.append(f"{label}: {exc}")
        return manifest

    manifest_review_paths = [entry["path"] for entry in manifest["reviews"]]
    current_review_paths = sorted(
        f"reviews/{path.name}"
        for path in reviews_dir.iterdir()
        if path.name.endswith(".json")
    )
    if sorted(manifest_review_paths) != current_review_paths:
        issues.append(f"{label}: completion bundle review set has changed.")

    for entry in manifest["reviews"]:
        review_path = workstream / entry["path"]
        if (
            review_path.is_symlink()
            or not review_path.is_file()
            or review_path.resolve().parent != reviews_dir
        ):
            issues.append(
                f"{label}: completion bundle review path is invalid: "
                f"{entry['path']}."
            )
            continue
        if file_sha256(review_path) != entry["sha256"]:
            issues.append(
                f"{label}: completion bundle review digest changed: "
                f"{entry['path']}."
            )

    for entry in manifest["checked_artifacts"]:
        try:
            artifact = resolve_managed_file(workstream, entry["path"])
        except ValueError as exc:
            issues.append(f"{label}: completion bundle checked artifact invalid: {exc}")
            continue
        if file_sha256(artifact) != entry["sha256"]:
            issues.append(
                f"{label}: checked artifact digest changed: {entry['path']}."
            )

    return manifest


def _checked_artifact_issues(
    workstream: Path,
    review: dict[str, Any],
) -> list[str]:
    issues = []
    for record in review.get("checked_artifacts", []):
        artifact_path = str(record["path"])
        try:
            artifact = resolve_managed_file(workstream, artifact_path)
        except ValueError as exc:
            issues.append(f"checked artifact path is invalid: {exc}.")
            continue
        if file_sha256(artifact) != record["sha256"]:
            issues.append(f"checked artifact digest changed: {artifact_path}.")
    return issues


def _checked_artifact_map(
    reviews: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for _, review in reviews:
        for record in review.get("checked_artifacts", []):
            artifacts[str(record["path"])] = str(record["sha256"])
    return artifacts


def _is_workstream_dir(path: Path) -> bool:
    return any(
        (path / marker).exists()
        for marker in ("status.yaml", "WORKSTREAM.md", "report.md", "messages.jsonl")
    )


def _resolved_review_names(
    reviews: list[tuple[Path, dict[str, Any]]],
    author_run_id: str,
) -> set[str]:
    resolved: set[str] = set()
    by_name = {path.name: review for path, review in reviews}
    for _, review in reviews:
        if review.get("approved") is not True:
            continue
        if review.get("reviewer_run_id") == author_run_id:
            continue
        for target in review.get("resolves", []):
            if not isinstance(target, str):
                continue
            blocking_review = by_name.get(target)
            if not blocking_review or blocking_review.get("severity") != "blocking":
                continue
            if _review_time(review) <= _review_time(blocking_review):
                continue
            resolved.add(target)
    return resolved


def _has_section(text: str, section: str) -> bool:
    expected = f"## {section}".lower()
    return any(line.strip().lower() == expected for line in text.splitlines())


def _section_has_content(text: str, section: str) -> bool:
    expected = f"## {section}".lower()
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() == expected:
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            return False
        if in_section and stripped:
            return True
    return False


def _review_time(review: dict[str, Any]) -> datetime:
    value = str(review.get("reviewed_at", "")).replace("Z", "+00:00")
    return datetime.fromisoformat(value)
