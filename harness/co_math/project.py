from __future__ import annotations

import json
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .schemas import utc_timestamp
from .storage import atomic_write_text

try:  # pragma: no cover - Python version dependent
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9-3.10
    import tomli as tomllib  # type: ignore[no-redef,import-not-found]


MANIFEST_FILENAME = "co-math.toml"
PROJECT_SCHEMA_VERSION = 1
PROJECT_TEMPLATE_VERSION = 1
CORE_VERSION = "0.3.0"

_MANIFEST_FIELDS = {
    "schema_version",
    "project_id",
    "name",
    "workspace",
    "created_at",
    "created_with",
    "template_version",
}
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_WINDOWS_INVALID_CHARACTERS = set('<>:"/\\|?*')


@dataclass(frozen=True)
class ProjectManifest:
    schema_version: int
    project_id: str
    name: str
    workspace: str
    created_at: str
    created_with: str
    template_version: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedProject:
    root: Path
    workspace: Path
    manifest: ProjectManifest


def validate_project_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Invalid project name: expected text")
    normalized = unicodedata.normalize("NFKC", name).strip()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("Invalid project name: value must not be empty or dot-only")
    if len(normalized) > 120:
        raise ValueError("Invalid project name: use at most 120 characters")
    if any(character in _WINDOWS_INVALID_CHARACTERS for character in normalized):
        raise ValueError("Invalid project name: path or platform-reserved character")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError("Invalid project name: control characters are not allowed")
    if normalized.endswith((".", " ")):
        raise ValueError("Invalid project name: trailing dots or spaces are not allowed")
    reserved_stem = normalized.split(".", 1)[0].upper()
    if reserved_stem in _WINDOWS_RESERVED_NAMES:
        raise ValueError("Invalid project name: platform-reserved name")
    return normalized


def new_manifest(
    name: str,
    *,
    workspace: str = "workspace",
    project_id: str | None = None,
    created_at: str | None = None,
    created_with: str = CORE_VERSION,
) -> ProjectManifest:
    return _validate_manifest_data(
        {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project_id": project_id or str(uuid.uuid4()),
            "name": validate_project_name(name),
            "workspace": workspace,
            "created_at": created_at or utc_timestamp(),
            "created_with": created_with,
            "template_version": PROJECT_TEMPLATE_VERSION,
        }
    )


def read_manifest(path: str | Path) -> ProjectManifest:
    manifest_path = _manifest_path(path)
    if manifest_path.is_symlink():
        raise ValueError(f"Project manifest must not be a symlink: {manifest_path}")
    if not manifest_path.is_file():
        raise ValueError(f"Project manifest is missing: {manifest_path}")
    try:
        with manifest_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid project manifest TOML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Invalid project manifest: top level must be a table")
    return _validate_manifest_data(data)


def write_manifest(path: str | Path, manifest: ProjectManifest) -> Path:
    manifest_path = _manifest_path(path)
    root = manifest_path.parent
    if root.is_symlink():
        raise ValueError(f"Project root must not be a symlink: {root}")
    if not root.is_dir():
        raise ValueError(f"Project root is missing: {root}")
    if manifest_path.is_symlink():
        raise ValueError(f"Project manifest must not be a symlink: {manifest_path}")
    checked = _validate_manifest_data(manifest.to_dict())
    lines = [
        f"schema_version = {checked.schema_version}",
        f"project_id = {_toml_string(checked.project_id)}",
        f"name = {_toml_string(checked.name)}",
        f"workspace = {_toml_string(checked.workspace)}",
        f"created_at = {_toml_string(checked.created_at)}",
        f"created_with = {_toml_string(checked.created_with)}",
        f"template_version = {checked.template_version}",
        "",
    ]
    atomic_write_text(manifest_path, "\n".join(lines))
    return manifest_path


def discover_project(start: str | Path | None = None) -> ResolvedProject:
    candidate = Path(start) if start is not None else Path.cwd()
    if not candidate.exists():
        raise ValueError(f"Project discovery path does not exist: {candidate}")
    if candidate.is_file():
        candidate = candidate.parent
    candidate = candidate.resolve(strict=True)
    for root in (candidate, *candidate.parents):
        if (root / MANIFEST_FILENAME).exists() or (root / MANIFEST_FILENAME).is_symlink():
            return _resolved_project(root)
    raise ValueError(f"No {MANIFEST_FILENAME} found from {candidate}")


def resolve_project(
    *,
    project: str | Path | None = None,
    workspace: str | Path | None = None,
    cwd: str | Path | None = None,
) -> ResolvedProject | None:
    if project is not None:
        explicit = Path(project).expanduser()
        if explicit.is_symlink():
            raise ValueError(f"Project path must not be a symlink: {explicit}")
        if explicit.name == MANIFEST_FILENAME:
            return _resolved_project(explicit.parent)
        if explicit.is_dir() and (explicit / MANIFEST_FILENAME).is_file():
            return _resolved_project(explicit)
        return discover_project(explicit)

    if workspace is not None:
        workspace_path = Path(workspace).expanduser()
        if workspace_path.is_symlink():
            raise ValueError(f"Workspace path must not be a symlink: {workspace_path}")
        if workspace_path.exists():
            parent = workspace_path.resolve(strict=True).parent
            if (parent / MANIFEST_FILENAME).is_file():
                resolved = _resolved_project(parent)
                if resolved.workspace == workspace_path.resolve(strict=True):
                    return resolved
        return None

    try:
        return discover_project(cwd)
    except ValueError as exc:
        if f"No {MANIFEST_FILENAME}" in str(exc):
            return None
        raise


def _resolved_project(root: str | Path) -> ResolvedProject:
    project_root = Path(root)
    if project_root.is_symlink():
        raise ValueError(f"Project root must not be a symlink: {project_root}")
    project_root = project_root.resolve(strict=True)
    manifest = read_manifest(project_root)
    workspace = project_root / manifest.workspace
    if workspace.is_symlink():
        raise ValueError(f"Project workspace must not be a symlink: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"Project workspace is missing: {workspace}")
    resolved_workspace = workspace.resolve(strict=True)
    if resolved_workspace.parent != project_root:
        raise ValueError(f"Project workspace escapes its root: {workspace}")
    return ResolvedProject(
        root=project_root,
        workspace=resolved_workspace,
        manifest=manifest,
    )


def _manifest_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.name == MANIFEST_FILENAME else candidate / MANIFEST_FILENAME


def _validate_manifest_data(data: Mapping[str, Any]) -> ProjectManifest:
    keys = set(data)
    missing = _MANIFEST_FIELDS - keys
    unknown = keys - _MANIFEST_FIELDS
    if missing:
        raise ValueError("Missing manifest fields: " + ", ".join(sorted(missing)))
    if unknown:
        raise ValueError("Unknown manifest fields: " + ", ".join(sorted(unknown)))

    schema_version = data["schema_version"]
    if type(schema_version) is not int or schema_version != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"Invalid schema_version: expected {PROJECT_SCHEMA_VERSION}, got {schema_version!r}"
        )
    template_version = data["template_version"]
    if type(template_version) is not int or template_version != PROJECT_TEMPLATE_VERSION:
        raise ValueError(
            "Invalid template_version: "
            f"expected {PROJECT_TEMPLATE_VERSION}, got {template_version!r}"
        )

    project_id = _required_string(data, "project_id")
    try:
        parsed_id = uuid.UUID(project_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid project_id: expected a UUID") from exc
    if str(parsed_id) != project_id.lower():
        raise ValueError("Invalid project_id: UUID must use canonical form")

    raw_name = _required_string(data, "name")
    name = validate_project_name(raw_name)
    if name != raw_name:
        raise ValueError("Invalid canonical project name: normalize and trim it first")
    workspace = _validate_workspace_name(_required_string(data, "workspace"))
    created_at = _required_string(data, "created_at")
    try:
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid created_at: expected an ISO-8601 timestamp") from exc
    if not created_at.endswith("Z") or timestamp.tzinfo is None:
        raise ValueError("Invalid created_at: expected a UTC timestamp ending in Z")
    created_with = _required_string(data, "created_with")

    return ProjectManifest(
        schema_version=schema_version,
        project_id=str(parsed_id),
        name=name,
        workspace=workspace,
        created_at=created_at,
        created_with=created_with,
        template_version=template_version,
    )


def _required_string(data: Mapping[str, Any], field: str) -> str:
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid {field}: expected non-empty text")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"Invalid {field}: control characters are not allowed")
    return value


def _validate_workspace_name(value: str) -> str:
    if (
        value in {"", ".", ".."}
        or Path(value).is_absolute()
        or "/" in value
        or "\\" in value
        or Path(value).name != value
    ):
        raise ValueError("Invalid workspace: expected one relative directory name")
    return value


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
