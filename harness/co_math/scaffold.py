from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .project import (
    MANIFEST_FILENAME,
    ResolvedProject,
    new_manifest,
    resolve_project,
    validate_project_name,
    write_manifest,
)
from .registry import config_home, load_user_config, register_project
from .storage import file_lock, resolve_managed_directory
from .workspace import init_workspace, select_language_policy


@dataclass(frozen=True)
class CreateProjectResult:
    project: ResolvedProject
    warnings: tuple[str, ...] = ()


def create_project(
    name: str,
    *,
    path: str | Path | None = None,
    language: str | None = None,
    initialize_git: bool = True,
) -> CreateProjectResult:
    normalized_name = validate_project_name(name)
    target = _resolve_target(normalized_name, path)
    temporary: Path | None = None

    with file_lock(config_home() / ".create.lock"):
        target_was_empty = _validate_target_state(target)
        _reject_nested_project(target)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{target.name}.co-math-tmp-",
                dir=target.parent,
            )
        )
        try:
            _copy_project_template(temporary)
            workspace = init_workspace(temporary / "workspace")
            if language is not None:
                select_language_policy(workspace, language)
            write_manifest(temporary, new_manifest(normalized_name))
            if initialize_git:
                _initialize_git(temporary)
            _publish_temporary_project(
                temporary,
                target,
                target_was_empty=target_was_empty,
            )
            temporary = None
        finally:
            if temporary is not None:
                shutil.rmtree(temporary, ignore_errors=True)

        project = resolve_project(project=target)
        if project is None:  # pragma: no cover - a published project always resolves
            raise RuntimeError(f"Created project could not be resolved: {target}")
        warnings = _register_with_warning(project)
        return CreateProjectResult(project=project, warnings=warnings)


def adopt_project(path: str | Path) -> CreateProjectResult:
    requested = Path(path).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    _assert_no_symlink_components(requested)
    if requested.is_symlink() or not requested.is_dir():
        raise ValueError(f"Project directory is missing or unsafe: {requested}")
    root = requested.resolve(strict=True)

    with file_lock(config_home() / ".create.lock"):
        _reject_descendant_projects(root)
        manifest_path = root / MANIFEST_FILENAME
        if manifest_path.exists() or manifest_path.is_symlink():
            project = resolve_project(project=root)
        else:
            _reject_nested_project(root)
            workspace = resolve_managed_directory(root, "workspace")
            for directory in ("project", "workstreams", "final"):
                resolve_managed_directory(workspace, directory)
            write_manifest(root, new_manifest(validate_project_name(root.name)))
            project = resolve_project(project=root)
        if project is None:  # pragma: no cover - an adopted project always resolves
            raise RuntimeError(f"Adopted project could not be resolved: {root}")
        warnings = _register_with_warning(project, replace_stale=True)
        return CreateProjectResult(project=project, warnings=warnings)


def _resolve_target(name: str, path: str | Path | None) -> Path:
    if path is None:
        parent = load_user_config().projects_home
        parent.mkdir(parents=True, exist_ok=True)
        requested = parent / name
    else:
        requested = Path(path).expanduser()
        if ".." in requested.parts:
            raise ValueError(f"Project path traversal is not allowed: {requested}")
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        parent = requested.parent
        if not parent.exists():
            raise ValueError(f"Project parent directory is missing: {parent}")
    _assert_no_symlink_components(requested)
    resolved_parent = requested.parent.resolve(strict=True)
    return resolved_parent / requested.name


def _validate_target_state(target: Path) -> bool:
    _assert_no_symlink_components(target)
    if not target.exists():
        return False
    if target.is_symlink():
        raise ValueError(f"Project target must not be a symlink: {target}")
    if not target.is_dir():
        raise ValueError(f"Project target is not a directory: {target}")
    if (target / MANIFEST_FILENAME).exists():
        raise ValueError(f"Co-Math project already exists: {target}")
    if any(target.iterdir()):
        raise ValueError(f"Project target is not empty: {target}")
    return True


def _reject_nested_project(target: Path) -> None:
    for ancestor in (target.parent, *target.parent.parents):
        manifest = ancestor / MANIFEST_FILENAME
        if manifest.exists() or manifest.is_symlink():
            raise ValueError(
                f"Refusing to create a nested Co-Math project inside {ancestor}"
            )


def _reject_descendant_projects(root: Path) -> None:
    for current, directory_names, file_names in os.walk(
        root,
        topdown=True,
        onerror=_raise_walk_error,
        followlinks=False,
    ):
        current_path = Path(current)
        directory_names[:] = [
            name
            for name in directory_names
            if name != ".git" and not (current_path / name).is_symlink()
        ]
        if current_path == root:
            continue
        manifest = current_path / MANIFEST_FILENAME
        if MANIFEST_FILENAME in file_names or manifest.is_symlink():
            raise ValueError(
                f"Refusing to adopt a directory containing descendant "
                f"Co-Math project: {current_path}"
            )


def _raise_walk_error(error: OSError) -> None:
    raise error


def _assert_no_symlink_components(path: Path) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Project path must not contain a symlink: {current}")


def _copy_project_template(destination: Path) -> None:
    source = resources.files("harness.co_math.project_template")
    _copy_resource_tree(source, destination)


def _copy_resource_tree(source: Any, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name in {"__init__.py", "__pycache__"}:
            continue
        target = destination / child.name
        if child.is_dir():
            _copy_resource_tree(child, target)
        elif child.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(child.read_bytes())


def _initialize_git(root: Path) -> None:
    try:
        subprocess.run(
            ["git", "init", "--quiet", str(root)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git init failed: git executable was not found") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or f"exit code {exc.returncode}"
        raise RuntimeError(f"git init failed: {message}") from exc


def _publish_temporary_project(
    temporary: Path,
    target: Path,
    *,
    target_was_empty: bool,
) -> None:
    removed_empty_target = False
    if target_was_empty:
        target.rmdir()
        removed_empty_target = True
    try:
        os.replace(temporary, target)
    except Exception:
        if removed_empty_target and not target.exists():
            target.mkdir()
        raise


def _register_with_warning(
    project: ResolvedProject,
    *,
    replace_stale: bool = False,
) -> tuple[str, ...]:
    try:
        if replace_stale:
            register_project(project.root, replace_stale=True)
        else:
            register_project(project.root)
    except Exception as exc:
        return (
            "Project created, but registry update failed: "
            f"{exc}. Run `co-math adopt` to repair the registry.",
        )
    return ()
