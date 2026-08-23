from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Sequence

from .project import CORE_VERSION
from .registry import UserConfig, normalize_user_config, save_user_config
from .storage import atomic_write_json, atomic_write_text, file_lock, file_sha256


ADAPTER_SCHEMA_VERSION = 1
INSTALL_MANIFEST_FILENAME = "install-manifest.json"
TOOL_FILENAMES = (
    "comath_project_new.ts",
    "comath_project_list.ts",
    "comath_project_status.ts",
    "comath_project_resume.ts",
    "comath_project_adopt.ts",
)
RESOURCE_FILENAMES = ("runner.ts", *TOOL_FILENAMES)
_INSTALL_MANIFEST_FIELDS = {"schema_version", "core_version", "files"}
_INSTALL_FILE_FIELDS = {"path", "sha256"}
_ADAPTER_CONFIG_FIELDS = {
    "schema_version",
    "core_version",
    "cli_path",
    "projects_home",
    "allowed_project_roots",
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OpenCodeInstallResult:
    config_dir: Path
    tool_files: tuple[Path, ...]
    runner_file: Path
    config_file: Path
    manifest_file: Path


@dataclass(frozen=True)
class OpenCodeRemovalResult:
    config_dir: Path
    removed_files: tuple[Path, ...]
    preserved_files: tuple[Path, ...]
    warnings: tuple[str, ...]
    manifest_retained: bool


@dataclass(frozen=True)
class _ManagedFileSnapshot:
    path: Path
    content: str | None


def resolve_opencode_config_dir(config_dir: str | Path | None = None) -> Path:
    if config_dir is not None:
        requested = Path(config_dir).expanduser()
    elif os.environ.get("OPENCODE_CONFIG_DIR"):
        requested = Path(os.environ["OPENCODE_CONFIG_DIR"]).expanduser()
    elif os.environ.get("XDG_CONFIG_HOME"):
        requested = Path(os.environ["XDG_CONFIG_HOME"]).expanduser() / "opencode"
    else:
        requested = Path.home() / ".config" / "opencode"
    if requested.is_symlink():
        raise ValueError(f"OpenCode config directory must not be a symlink: {requested}")
    return requested.resolve()


def adapter_resource_text(filename: str) -> str:
    if filename not in RESOURCE_FILENAMES:
        raise ValueError(f"Unknown OpenCode adapter resource: {filename}")
    resource = resources.files("harness.co_math.opencode_adapter").joinpath(filename)
    return resource.read_text(encoding="utf-8")


def install_opencode_adapter(
    *,
    config_dir: str | Path | None = None,
    cli_path: str | Path,
    projects_home: str | Path,
    allowed_roots: Sequence[str | Path],
) -> OpenCodeInstallResult:
    root = resolve_opencode_config_dir(config_dir)
    executable = _resolve_executable(cli_path)
    requested_user_config = UserConfig(
        projects_home=Path(projects_home),
        allowed_project_roots=tuple(Path(path) for path in allowed_roots),
    )
    user_config = normalize_user_config(
        requested_user_config,
        create=False,
    )
    if root.is_symlink():
        raise ValueError(f"OpenCode config directory must not be a symlink: {root}")
    root.mkdir(parents=True, exist_ok=True)

    config_data = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "core_version": CORE_VERSION,
        "cli_path": str(executable),
        "projects_home": str(user_config.projects_home),
        "allowed_project_roots": [
            str(path) for path in user_config.allowed_project_roots
        ],
    }
    desired = {
        **{
            f"tools/{filename}": adapter_resource_text(filename)
            for filename in TOOL_FILENAMES
        },
        "co-math/runner.ts": adapter_resource_text("runner.ts"),
        "co-math/config.json": json.dumps(
            config_data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
    manifest_path = root / "co-math" / INSTALL_MANIFEST_FILENAME

    with file_lock(root / ".co-math-adapter.lock"):
        if manifest_path.is_symlink():
            raise ValueError(
                f"OpenCode adapter install manifest must not be a symlink: {manifest_path}"
            )
        previous = _read_install_manifest(manifest_path) if manifest_path.exists() else None
        previous_digests = _manifest_digest_map(previous) if previous is not None else {}
        _check_safe_overwrite(root, desired, previous_digests)
        snapshots = _snapshot_managed_files(
            root,
            (*desired, f"co-math/{INSTALL_MANIFEST_FILENAME}"),
        )
        try:
            for relative_path, text in desired.items():
                target = _managed_target(root, relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(target, text)
            manifest = _build_install_manifest(root, desired)
            atomic_write_json(manifest_path, manifest)
            save_user_config(
                UserConfig(
                    projects_home=user_config.projects_home,
                    allowed_project_roots=user_config.allowed_project_roots,
                )
            )
        except Exception as exc:
            rollback_errors = _restore_managed_files(root, snapshots)
            if rollback_errors:
                details = "; ".join(rollback_errors)
                raise RuntimeError(
                    f"OpenCode adapter installation failed and rollback was incomplete: "
                    f"{details}"
                ) from exc
            raise

    return _install_result(root)


def remove_opencode_adapter(
    *,
    config_dir: str | Path | None = None,
) -> OpenCodeRemovalResult:
    root = resolve_opencode_config_dir(config_dir)
    manifest_path = root / "co-math" / INSTALL_MANIFEST_FILENAME
    if not manifest_path.exists():
        return OpenCodeRemovalResult(root, (), (), (), False)

    removed: list[Path] = []
    preserved: list[Path] = []
    warnings: list[str] = []
    with file_lock(root / ".co-math-adapter.lock"):
        manifest = _read_install_manifest(manifest_path)
        for relative_path, expected_digest in _manifest_digest_map(manifest).items():
            target = _managed_target(root, relative_path)
            if not target.exists() and not target.is_symlink():
                continue
            if target.is_symlink() or not target.is_file():
                preserved.append(target)
                warnings.append(f"Preserved unsafe managed path: {target}")
                continue
            if file_sha256(target) != expected_digest:
                preserved.append(target)
                warnings.append(f"Preserved modified managed file: {target}")
                continue
            target.unlink()
            removed.append(target)
        manifest_retained = bool(preserved)
        if manifest_retained:
            warnings.append(
                "Retained the install manifest because modified or unsafe managed "
                "files remain"
            )
        else:
            manifest_path.unlink(missing_ok=True)
        for directory in (root / "co-math", root / "tools"):
            try:
                directory.rmdir()
            except OSError:
                pass
    return OpenCodeRemovalResult(
        config_dir=root,
        removed_files=tuple(sorted(removed)),
        preserved_files=tuple(sorted(preserved)),
        warnings=tuple(warnings),
        manifest_retained=manifest_retained,
    )


def inspect_opencode_adapter(
    *,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_opencode_config_dir(config_dir)
    manifest_path = root / "co-math" / INSTALL_MANIFEST_FILENAME
    result: dict[str, Any] = {
        "config_dir": str(root),
        "installed": manifest_path.is_file() and not manifest_path.is_symlink(),
        "healthy": False,
        "core_version": None,
        "core_version_matches": False,
        "cli_path": None,
        "cli_exists": False,
        "cli_path_matches": False,
        "files": [],
        "issues": [],
    }
    if not result["installed"]:
        return result
    try:
        manifest = _read_install_manifest(manifest_path)
        result["core_version"] = manifest["core_version"]
        manifest_version_matches = manifest["core_version"] == CORE_VERSION
        if not manifest_version_matches:
            result["issues"].append(
                "OpenCode adapter Core version mismatch: "
                f"installed {manifest['core_version']}, current {CORE_VERSION}"
            )
        for relative_path, expected_digest in _manifest_digest_map(manifest).items():
            target = _managed_target(root, relative_path)
            result["files"].append(str(target))
            if target.is_symlink() or not target.is_file():
                result["issues"].append(f"Managed adapter file is missing or unsafe: {target}")
            elif file_sha256(target) != expected_digest:
                result["issues"].append(f"Managed adapter file digest mismatch: {target}")
        config_path = root / "co-math" / "config.json"
        if config_path.is_file() and not config_path.is_symlink():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict) or set(config) != _ADAPTER_CONFIG_FIELDS:
                raise ValueError("Invalid OpenCode adapter config fields")
            config_version = config.get("core_version")
            config_version_matches = config_version == CORE_VERSION
            result["core_version_matches"] = (
                manifest_version_matches and config_version_matches
            )
            if not config_version_matches:
                result["issues"].append(
                    "OpenCode adapter config Core version mismatch: "
                    f"installed {config_version!r}, current {CORE_VERSION}"
                )
            cli_path = config.get("cli_path") if isinstance(config, dict) else None
            if isinstance(cli_path, str):
                result["cli_path"] = cli_path
                candidate = Path(cli_path)
                result["cli_exists"] = candidate.is_file() and os.access(candidate, os.X_OK)
                if not result["cli_exists"]:
                    result["issues"].append(
                        f"Configured Co-Math executable is missing or not executable: {candidate}"
                    )
                elif not candidate.is_absolute() or candidate.resolve(strict=True) != candidate:
                    result["issues"].append(
                        f"Configured Co-Math executable path is not canonical: {candidate}"
                    )
                else:
                    result["cli_path_matches"] = result["core_version_matches"]
            else:
                result["issues"].append("Adapter config is missing cli_path")
        else:
            result["issues"].append(
                f"OpenCode adapter config is missing or unsafe: {config_path}"
            )
    except Exception as exc:
        result["issues"].append(str(exc))
    result["healthy"] = not result["issues"]
    return result


def _resolve_executable(cli_path: str | Path) -> Path:
    requested = Path(cli_path).expanduser()
    if not requested.is_absolute():
        raise ValueError("Co-Math CLI path must be absolute")
    if not requested.exists():
        raise ValueError(f"Co-Math CLI path does not exist: {requested}")
    resolved = requested.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"Co-Math CLI path is not a file: {resolved}")
    if not os.access(resolved, os.X_OK):
        raise ValueError(f"Co-Math CLI path is not executable: {resolved}")
    return resolved


def _managed_target(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"Invalid adapter managed path: {relative_path}")
    target = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Adapter managed path contains a symlink: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(
                f"Adapter managed parent must be a directory: {current}"
            )
    return target


def _snapshot_managed_files(
    root: Path,
    relative_paths: Sequence[str],
) -> tuple[_ManagedFileSnapshot, ...]:
    snapshots: list[_ManagedFileSnapshot] = []
    for relative_path in relative_paths:
        target = _managed_target(root, relative_path)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError(f"Adapter managed file is unsafe: {target}")
        content = target.read_text(encoding="utf-8") if target.exists() else None
        snapshots.append(_ManagedFileSnapshot(path=target, content=content))
    return tuple(snapshots)


def _restore_managed_files(
    root: Path,
    snapshots: Sequence[_ManagedFileSnapshot],
) -> tuple[str, ...]:
    errors: list[str] = []
    for snapshot in reversed(snapshots):
        try:
            if snapshot.content is None:
                if snapshot.path.is_symlink() or snapshot.path.is_file():
                    snapshot.path.unlink()
                elif snapshot.path.exists():
                    raise ValueError(f"Rollback target is not a file: {snapshot.path}")
            else:
                atomic_write_text(snapshot.path, snapshot.content)
        except Exception as exc:  # pragma: no cover - requires rollback failure
            errors.append(f"{snapshot.path}: {exc}")

    directories = {
        snapshot.path.parent
        for snapshot in snapshots
        if snapshot.path.parent != root
    }
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return tuple(errors)


def _check_safe_overwrite(
    root: Path,
    desired: dict[str, str],
    previous_digests: dict[str, str],
) -> None:
    for relative_path, text in desired.items():
        target = _managed_target(root, relative_path)
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_symlink() or not target.is_file():
            raise ValueError(f"Refusing to overwrite unsafe adapter path: {target}")
        current_digest = file_sha256(target)
        desired_digest = _text_sha256(text)
        if current_digest == desired_digest:
            continue
        if previous_digests.get(relative_path) == current_digest:
            continue
        raise ValueError(f"Refusing to overwrite modified adapter file: {target}")


def _build_install_manifest(root: Path, desired: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "core_version": CORE_VERSION,
        "files": [
            {
                "path": relative_path,
                "sha256": file_sha256(_managed_target(root, relative_path)),
            }
            for relative_path in sorted(desired)
        ],
    }


def _read_install_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"OpenCode adapter install manifest is missing or unsafe: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid OpenCode adapter install manifest JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) != _INSTALL_MANIFEST_FIELDS:
        raise ValueError("Invalid OpenCode adapter install manifest fields")
    if data.get("schema_version") != ADAPTER_SCHEMA_VERSION:
        raise ValueError("Invalid OpenCode adapter install manifest schema_version")
    if not isinstance(data.get("core_version"), str) or not data["core_version"]:
        raise ValueError("Invalid OpenCode adapter install manifest core_version")
    files = data.get("files")
    if not isinstance(files, list):
        raise ValueError("Invalid OpenCode adapter install manifest files")
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict) or set(record) != _INSTALL_FILE_FIELDS:
            raise ValueError("Invalid OpenCode adapter install file record")
        relative_path = record.get("path")
        digest = record.get("sha256")
        if not isinstance(relative_path, str) or relative_path in seen:
            raise ValueError("Invalid or duplicate OpenCode adapter install path")
        _managed_target(path.parents[1], relative_path)
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError("Invalid OpenCode adapter install digest")
        seen.add(relative_path)
    return data


def _manifest_digest_map(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        str(record["path"]): str(record["sha256"])
        for record in manifest["files"]
    }


def _install_result(root: Path) -> OpenCodeInstallResult:
    return OpenCodeInstallResult(
        config_dir=root,
        tool_files=tuple(root / "tools" / filename for filename in TOOL_FILENAMES),
        runner_file=root / "co-math" / "runner.ts",
        config_file=root / "co-math" / "config.json",
        manifest_file=root / "co-math" / INSTALL_MANIFEST_FILENAME,
    )


def _text_sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
