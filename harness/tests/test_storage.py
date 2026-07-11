from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import harness.co_math.storage as storage_module
from harness.co_math.storage import atomic_write_text, workspace_lock


ROOT = Path(__file__).resolve().parents[2]


def test_atomic_write_preserves_existing_file_mode(tmp_path):
    target = tmp_path / "state.yaml"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o640)

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_workspace_lock_is_reentrant_for_same_thread(tmp_path):
    script = """
from harness.co_math.storage import workspace_lock
from pathlib import Path
import sys
workspace = Path(sys.argv[1])
with workspace_lock(workspace):
    with workspace_lock(workspace):
        print("nested lock returned")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "workspace")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=2,
        check=True,
    )

    assert completed.stdout.strip() == "nested lock returned"


def test_atomic_write_uses_normal_collaboration_mode_for_new_file(tmp_path):
    target = tmp_path / "new-state.yaml"
    previous_umask = os.umask(0o022)
    try:
        atomic_write_text(target, "state\n")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_atomic_write_does_not_require_fchmod(tmp_path, monkeypatch):
    target = tmp_path / "state.yaml"
    target.write_text("old\n", encoding="utf-8")
    monkeypatch.delattr(storage_module.os, "fchmod")

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_workspace_lock_is_not_reentrant_after_fork(tmp_path):
    read_fd, write_fd = os.pipe()
    workspace = tmp_path / "workspace"

    with workspace_lock(workspace):
        started = time.monotonic()
        child = os.fork()
        if child == 0:  # pragma: no cover - assertion is made in the parent
            os.close(read_fd)
            with workspace_lock(workspace):
                elapsed = time.monotonic() - started
                os.write(write_fd, f"{elapsed}".encode())
            os.close(write_fd)
            os._exit(0)
        os.close(write_fd)
        time.sleep(0.2)

    payload = os.read(read_fd, 100)
    os.close(read_fd)
    _, status = os.waitpid(child, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    assert float(payload.decode()) >= 0.15
