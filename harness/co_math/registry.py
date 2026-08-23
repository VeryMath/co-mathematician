from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project import MANIFEST_FILENAME, resolve_project
from .schemas import utc_timestamp
from .storage import atomic_write_json, file_lock


CONFIG_SCHEMA_VERSION = 1
REGISTRY_SCHEMA_VERSION = 1
CONFIG_FILENAME = "config.json"
REGISTRY_FILENAME = "projects.json"

_CONFIG_FIELDS = {"schema_version", "projects_home", "allowed_project_roots"}
_REGISTRY_FIELDS = {"schema_version", "projects"}
_ENTRY_FIELDS = {
    "project_id",
    "manifest_path",
    "registered_at",
    "last_opened_at",
}


@dataclass(frozen=True)
class UserConfig:
    projects_home: Path
    allowed_project_roots: tuple[Path, ...]


def config_home() -> Path:
    override = os.environ.get("CO_MATH_CONFIG_HOME")
    if override:
        return Path(override).expanduser().resolve()
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        return (Path(xdg_home).expanduser() / "co-mathematician").resolve()
    app_data = os.environ.get("APPDATA")
    if os.name == "nt" and app_data:  # pragma: no cover - Windows-specific
        return (Path(app_data).expanduser() / "co-mathematician").resolve()
    return (Path.home() / ".config" / "co-mathematician").resolve()


def registry_path() -> Path:
    return config_home() / REGISTRY_FILENAME


def load_user_config() -> UserConfig:
    path = config_home() / CONFIG_FILENAME
    if not path.exists():
        projects_home = (Path.home() / "CoMathProjects").resolve()
        return UserConfig(
            projects_home=projects_home,
            allowed_project_roots=(projects_home,),
        )
    if path.is_symlink():
        raise ValueError(f"User config must not be a symlink: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid user config JSON: {exc}") from exc
    return _parse_user_config(data, require_existing=False)


def save_user_config(config: UserConfig) -> UserConfig:
    normalized = _normalize_user_config(config, create=True)
    root = config_home()
    root.mkdir(parents=True, exist_ok=True)
    path = root / CONFIG_FILENAME
    if path.is_symlink():
        raise ValueError(f"User config must not be a symlink: {path}")
    data = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "projects_home": str(normalized.projects_home),
        "allowed_project_roots": [
            str(path) for path in normalized.allowed_project_roots
        ],
    }
    with file_lock(root / ".config.lock"):
        atomic_write_json(path, data)
    return normalized


def register_project(
    project_root: str | Path,
    *,
    opened_at: str | None = None,
) -> dict[str, str]:
    project = resolve_project(project=project_root)
    if project is None:  # pragma: no cover - explicit projects never return None
        raise ValueError(f"Co-Math project was not found: {project_root}")
    manifest_path = (project.root / MANIFEST_FILENAME).resolve(strict=True)
    timestamp = opened_at or utc_timestamp()
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Project registry must not be a symlink: {path}")

    with file_lock(path.parent / ".registry.lock"):
        data = _load_registry(path)
        entries: list[dict[str, str]] = data["projects"]
        manifest_value = str(manifest_path)
        matching_id = next(
            (
                entry
                for entry in entries
                if entry["project_id"] == project.manifest.project_id
            ),
            None,
        )
        matching_path = next(
            (
                entry
                for entry in entries
                if entry["manifest_path"] == manifest_value
            ),
            None,
        )
        if matching_id is not None and matching_id["manifest_path"] != manifest_value:
            raise ValueError(
                f"Project id {project.manifest.project_id} is already registered "
                f"at {matching_id['manifest_path']}"
            )
        if matching_path is not None and matching_path["project_id"] != project.manifest.project_id:
            raise ValueError(
                f"Manifest path {manifest_value} is registered with a different project id"
            )

        if matching_id is None:
            entry = {
                "project_id": project.manifest.project_id,
                "manifest_path": manifest_value,
                "registered_at": timestamp,
                "last_opened_at": timestamp,
            }
            entries.append(entry)
        else:
            matching_id["last_opened_at"] = timestamp
            entry = matching_id
        entries.sort(key=lambda item: (item["registered_at"], item["project_id"]))
        atomic_write_json(path, data)
        return dict(entry)


def list_registered_projects() -> list[dict[str, Any]]:
    path = registry_path()
    if not path.exists():
        return []
    if path.is_symlink():
        raise ValueError(f"Project registry must not be a symlink: {path}")
    data = _load_registry(path)
    results = [_project_entry(entry) for entry in data["projects"]]
    return sorted(
        results,
        key=lambda entry: (str(entry["last_opened_at"]), str(entry["project_id"])),
        reverse=True,
    )


def _project_entry(entry: dict[str, str]) -> dict[str, Any]:
    manifest_path = Path(entry["manifest_path"])
    result: dict[str, Any] = {
        **entry,
        "path": str(manifest_path.parent),
        "name": None,
        "registry_status": "stale",
        "error": None,
    }
    if not manifest_path.exists():
        return result
    try:
        project = resolve_project(project=manifest_path)
        if project is None:  # pragma: no cover - explicit projects never return None
            raise ValueError("Project could not be resolved")
        if project.manifest.project_id != entry["project_id"]:
            raise ValueError("Registered project id does not match the current manifest")
    except Exception as exc:
        result["registry_status"] = "invalid"
        result["error"] = str(exc)
        return result
    result["name"] = project.manifest.name
    result["path"] = str(project.root)
    result["registry_status"] = "valid"
    return result


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": REGISTRY_SCHEMA_VERSION, "projects": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid project registry JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Invalid project registry: expected an object")
    if set(data) != _REGISTRY_FIELDS:
        raise ValueError("Invalid project registry fields")
    if data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError(
            "Invalid registry schema_version: "
            f"expected {REGISTRY_SCHEMA_VERSION}, got {data.get('schema_version')!r}"
        )
    projects = data.get("projects")
    if not isinstance(projects, list):
        raise ValueError("Invalid project registry: projects must be a list")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for entry in projects:
        if not isinstance(entry, dict) or set(entry) != _ENTRY_FIELDS:
            raise ValueError("Invalid project registry entry fields")
        if any(not isinstance(entry[field], str) or not entry[field] for field in _ENTRY_FIELDS):
            raise ValueError("Invalid project registry entry values")
        if entry["project_id"] in seen_ids:
            raise ValueError(f"Duplicate project id in registry: {entry['project_id']}")
        if entry["manifest_path"] in seen_paths:
            raise ValueError(
                f"Duplicate manifest path in registry: {entry['manifest_path']}"
            )
        seen_ids.add(entry["project_id"])
        seen_paths.add(entry["manifest_path"])
    return data


def _parse_user_config(data: Any, *, require_existing: bool) -> UserConfig:
    if not isinstance(data, dict) or set(data) != _CONFIG_FIELDS:
        raise ValueError("Invalid user config fields")
    if data.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "Invalid config schema_version: "
            f"expected {CONFIG_SCHEMA_VERSION}, got {data.get('schema_version')!r}"
        )
    projects_home = data.get("projects_home")
    roots = data.get("allowed_project_roots")
    if not isinstance(projects_home, str) or not projects_home:
        raise ValueError("Invalid projects_home in user config")
    if not isinstance(roots, list) or not roots or not all(
        isinstance(root, str) and root for root in roots
    ):
        raise ValueError("Invalid allowed_project_roots in user config")
    return _normalize_user_config(
        UserConfig(
            projects_home=Path(projects_home),
            allowed_project_roots=tuple(Path(root) for root in roots),
        ),
        create=False,
        require_existing=require_existing,
    )


def _normalize_user_config(
    config: UserConfig,
    *,
    create: bool,
    require_existing: bool = False,
) -> UserConfig:
    requested_home = Path(config.projects_home).expanduser()
    requested_roots = [Path(root).expanduser() for root in config.allowed_project_roots]
    if not requested_roots:
        raise ValueError("allowed_project_roots must not be empty")
    if create:
        requested_home.mkdir(parents=True, exist_ok=True)
        for root in requested_roots:
            root.mkdir(parents=True, exist_ok=True)
    paths = [requested_home, *requested_roots]
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"Configured project path must not be a symlink: {path}")
        if require_existing and not path.is_dir():
            raise ValueError(f"Configured project directory is missing: {path}")
    projects_home = requested_home.resolve(strict=create or require_existing)
    roots: list[Path] = []
    for requested in requested_roots:
        resolved = requested.resolve(strict=create or require_existing)
        if resolved not in roots:
            roots.append(resolved)
    if not any(_is_within(projects_home, root) for root in roots):
        raise ValueError("projects_home must be inside an allowed project root")
    return UserConfig(projects_home=projects_home, allowed_project_roots=tuple(roots))


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
