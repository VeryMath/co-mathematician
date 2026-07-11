from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

fcntl: Any
try:  # pragma: no cover - platform-specific import
    import fcntl as _fcntl

    fcntl = _fcntl
except ImportError:  # pragma: no cover
    fcntl = None

msvcrt: Any
try:  # pragma: no cover - platform-specific import
    import msvcrt as _msvcrt

    msvcrt = _msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None


_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[Path, threading.RLock] = {}
_LOCK_STATE = threading.local()
DEFAULT_FILE_MODE = 0o644
LOCK_TIMEOUT_SECONDS = 300.0


def atomic_write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target_mode = (
        stat.S_IMODE(target.stat().st_mode)
        if target.exists()
        else DEFAULT_FILE_MODE
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), target_mode)
            handle.flush()
            os.fsync(handle.fileno())
        if not hasattr(os, "fchmod"):
            os.chmod(temporary, target_mode)
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: str | Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_managed_directory(
    parent: str | Path,
    name: str,
    *,
    create: bool = False,
) -> Path:
    """Resolve one harness-owned directory without following a sidecar symlink."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError(f"Invalid managed directory name: {name}")

    parent_path = Path(parent)
    parent_resolved = parent_path.resolve(strict=True)
    candidate = parent_path / name
    if candidate.is_symlink():
        raise ValueError(f"Managed directory must not be a symlink: {candidate}")
    if create:
        candidate.mkdir(exist_ok=True)
    if candidate.is_symlink():
        raise ValueError(f"Managed directory must not be a symlink: {candidate}")
    if not candidate.is_dir():
        raise ValueError(f"Managed directory is missing: {candidate}")

    resolved = candidate.resolve(strict=True)
    if resolved.parent != parent_resolved:
        raise ValueError(f"Managed directory escapes its parent: {candidate}")
    return resolved


def resolve_managed_file(
    parent: str | Path,
    relative_path: str | Path,
    *,
    must_exist: bool = True,
) -> Path:
    """Resolve a harness-owned file without following symlinks or escaping."""
    parent_path = Path(parent)
    parent_resolved = parent_path.resolve(strict=True)
    relative = Path(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"Invalid managed file path: {relative_path}")

    candidate = parent_path
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(f"Managed file path must not contain a symlink: {candidate}")

    if not candidate.exists():
        if must_exist:
            raise ValueError(f"Managed file is missing: {candidate}")
        return parent_resolved.joinpath(*relative.parts)
    if not candidate.is_file():
        raise ValueError(f"Managed file is not a regular file: {candidate}")

    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(parent_resolved)
    except ValueError as exc:
        raise ValueError(f"Managed file escapes its parent: {candidate}") from exc
    return resolved


def append_jsonl(path: str | Path, record: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def workspace_lock(workspace: str | Path) -> Iterator[None]:
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    project = resolve_managed_directory(root, "project", create=True)
    lock_path = project / ".co-math.lock"
    thread_lock = _thread_lock(lock_path)

    with thread_lock:
        depths = _held_lock_depths()
        depth = depths.get(lock_path, 0)
        if depth:
            depths[lock_path] = depth + 1
            try:
                yield
            finally:
                depths[lock_path] -= 1
            return

        with lock_path.open("a+b") as handle:
            _lock_file(handle)
            depths[lock_path] = 1
            try:
                yield
            finally:
                depths.pop(lock_path, None)
                _unlock_file(handle)


def _thread_lock(path: Path) -> threading.RLock:
    with _LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(path, threading.RLock())


def _held_lock_depths() -> dict[Path, int]:
    current_pid = os.getpid()
    if getattr(_LOCK_STATE, "pid", None) != current_pid:
        _LOCK_STATE.pid = current_pid
        _LOCK_STATE.depths = {}
    depths = getattr(_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _LOCK_STATE.depths = depths
    return depths


def _reset_lock_state_after_fork() -> None:  # pragma: no cover - exercised by fork test
    global _LOCKS_GUARD, _THREAD_LOCKS
    _LOCKS_GUARD = threading.Lock()
    _THREAD_LOCKS = {}
    _LOCK_STATE.pid = os.getpid()
    _LOCK_STATE.depths = {}


if hasattr(os, "register_at_fork"):  # pragma: no branch - POSIX-only hook
    os.register_at_fork(after_in_child=_reset_lock_state_after_fork)


def _lock_file(handle) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return
    if msvcrt is not None:  # pragma: no cover - Windows fallback
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Timed out waiting for workspace lock after "
                        f"{LOCK_TIMEOUT_SECONDS:.0f}s"
                    ) from exc
                time.sleep(0.05)


def _unlock_file(handle) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if msvcrt is not None:  # pragma: no cover - Windows fallback
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
