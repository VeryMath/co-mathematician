from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Sequence

from .registry import (
    CONFIG_FILENAME,
    UserConfig,
    config_home as core_config_home,
    normalize_user_config,
    save_user_config,
)
from .storage import atomic_write_text, file_lock


TOOL_FILENAMES = (
    "comath_project_new.ts",
    "comath_project_list.ts",
    "comath_project_status.ts",
    "comath_project_resume.ts",
    "comath_project_next.ts",
    "comath_project_lifecycle.ts",
    "comath_project_adopt.ts",
)
SKILL_RESOURCE_FILENAME = "co_math_skill.md"
RESOURCE_FILENAMES = ("runner.ts", SKILL_RESOURCE_FILENAME, *TOOL_FILENAMES)


@dataclass(frozen=True)
class OpenCodeInstallResult:
    config_dir: Path
    tool_files: tuple[Path, ...]
    runner_file: Path
    config_file: Path
    skill_file: Path


@dataclass(frozen=True)
class OpenCodeRemovalResult:
    config_dir: Path
    removed_files: tuple[Path, ...]
    preserved_files: tuple[Path, ...]
    warnings: tuple[str, ...]


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
    user_config = normalize_user_config(
        UserConfig(
            projects_home=Path(projects_home),
            allowed_project_roots=tuple(Path(path) for path in allowed_roots),
        ),
        create=False,
    )
    root.mkdir(parents=True, exist_ok=True)
    desired = _desired_files(executable, user_config)

    with file_lock(root / ".co-math-adapter.lock"):
        snapshots = _snapshot_managed_files(root, tuple(desired))
        core_snapshot = _snapshot_text_file(core_config_home() / CONFIG_FILENAME)
        try:
            for relative_path, content in desired.items():
                target = _managed_target(root, relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(target, content)
            save_user_config(user_config)
        except Exception:
            _restore_managed_files(root, snapshots)
            _restore_text_file(core_snapshot)
            raise

    return _install_result(root)


def remove_opencode_adapter(
    *,
    config_dir: str | Path | None = None,
) -> OpenCodeRemovalResult:
    root = resolve_opencode_config_dir(config_dir)
    removed: list[Path] = []
    preserved: list[Path] = []
    warnings: list[str] = []
    if not root.exists():
        return OpenCodeRemovalResult(root, (), (), ())

    with file_lock(root / ".co-math-adapter.lock"):
        for relative_path in _managed_relative_paths():
            target = _managed_target(root, relative_path)
            if not target.exists() and not target.is_symlink():
                continue
            if target.is_symlink() or not target.is_file():
                preserved.append(target)
                warnings.append(f"Preserved unsafe Co-Math path: {target}")
                continue
            target.unlink()
            removed.append(target)
        for directory in (
            root / "skills" / "co-math",
            root / "co-math",
            root / "tools",
        ):
            try:
                directory.rmdir()
            except OSError:
                pass

    return OpenCodeRemovalResult(
        config_dir=root,
        removed_files=tuple(sorted(removed)),
        preserved_files=tuple(sorted(preserved)),
        warnings=tuple(warnings),
    )


def inspect_opencode_adapter(
    *,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_opencode_config_dir(config_dir)
    targets = [_managed_target(root, path) for path in _managed_relative_paths()]
    installed = any(path.exists() or path.is_symlink() for path in targets)
    result: dict[str, Any] = {
        "config_dir": str(root),
        "installed": installed,
        "healthy": False,
        "cli_path": None,
        "cli_exists": False,
        "skill_file": str(root / "skills" / "co-math" / "SKILL.md"),
        "files": [str(path) for path in targets],
        "issues": [],
    }
    if not installed:
        return result

    for target in targets:
        if target.is_symlink() or not target.is_file():
            result["issues"].append(f"Co-Math OpenCode file is missing or unsafe: {target}")

    config_path = root / "co-math" / "config.json"
    if config_path.is_file() and not config_path.is_symlink():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("OpenCode config must contain an object")
            cli_path = config.get("cli_path")
            if not isinstance(cli_path, str) or not Path(cli_path).is_absolute():
                raise ValueError("OpenCode config is missing an absolute cli_path")
            result["cli_path"] = cli_path
            candidate = Path(cli_path)
            result["cli_exists"] = candidate.is_file() and os.access(candidate, os.X_OK)
            if not result["cli_exists"]:
                result["issues"].append(
                    f"Configured Co-Math executable is missing or not executable: {candidate}"
                )
            roots = config.get("allowed_project_roots")
            if not isinstance(roots, list) or not roots or not all(
                isinstance(item, str) and Path(item).is_absolute() for item in roots
            ):
                result["issues"].append(
                    "OpenCode config needs at least one absolute allowed project root"
                )
        except (json.JSONDecodeError, ValueError) as exc:
            result["issues"].append(str(exc))

    result["healthy"] = not result["issues"]
    return result


def _desired_files(executable: Path, config: UserConfig) -> dict[str, str]:
    config_data = {
        "cli_path": str(executable),
        "projects_home": str(config.projects_home),
        "allowed_project_roots": [str(path) for path in config.allowed_project_roots],
    }
    return {
        **{
            f"tools/{filename}": adapter_resource_text(filename)
            for filename in TOOL_FILENAMES
        },
        "co-math/runner.ts": adapter_resource_text("runner.ts"),
        "co-math/config.json": json.dumps(config_data, ensure_ascii=False, indent=2) + "\n",
        "skills/co-math/SKILL.md": adapter_resource_text(SKILL_RESOURCE_FILENAME),
    }


def _managed_relative_paths() -> tuple[str, ...]:
    return (
        *(f"tools/{filename}" for filename in TOOL_FILENAMES),
        "co-math/runner.ts",
        "co-math/config.json",
        "skills/co-math/SKILL.md",
    )


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
        raise ValueError(f"Invalid OpenCode path: {relative_path}")
    target = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"OpenCode path contains a symlink: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"OpenCode path parent must be a directory: {current}")
    return target


def _snapshot_managed_files(
    root: Path,
    relative_paths: Sequence[str],
) -> tuple[_ManagedFileSnapshot, ...]:
    return tuple(
        _snapshot_text_file(_managed_target(root, relative_path))
        for relative_path in relative_paths
    )


def _snapshot_text_file(path: Path) -> _ManagedFileSnapshot:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Managed text file is unsafe: {path}")
    content = path.read_text(encoding="utf-8") if path.exists() else None
    return _ManagedFileSnapshot(path=path, content=content)


def _restore_text_file(snapshot: _ManagedFileSnapshot) -> None:
    if snapshot.content is None:
        if snapshot.path.is_symlink() or snapshot.path.is_file():
            snapshot.path.unlink()
        elif snapshot.path.exists():
            raise ValueError(f"Restore target is not a file: {snapshot.path}")
        return
    if snapshot.path.is_symlink() or (
        snapshot.path.exists() and not snapshot.path.is_file()
    ):
        raise ValueError(f"Restore target is unsafe: {snapshot.path}")
    atomic_write_text(snapshot.path, snapshot.content)


def _restore_managed_files(
    root: Path,
    snapshots: Sequence[_ManagedFileSnapshot],
) -> None:
    for snapshot in reversed(snapshots):
        _restore_text_file(snapshot)
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


def _install_result(root: Path) -> OpenCodeInstallResult:
    return OpenCodeInstallResult(
        config_dir=root,
        tool_files=tuple(root / "tools" / filename for filename in TOOL_FILENAMES),
        runner_file=root / "co-math" / "runner.ts",
        config_file=root / "co-math" / "config.json",
        skill_file=root / "skills" / "co-math" / "SKILL.md",
    )
