from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .gating import check_workstream_completion
from .schemas import utc_timestamp


def render_final(workspace: str | Path) -> Path:
    root = Path(workspace)
    final_dir = root / "final"
    if final_dir.is_symlink() or (final_dir.exists() and not final_dir.is_dir()):
        raise ValueError(f"Final directory is missing or unsafe: {final_dir}")
    final_dir.mkdir(parents=True, exist_ok=True)

    sections: list[str] = []
    for workstream in sorted((root / "workstreams").glob("*")):
        if not workstream.is_dir():
            continue
        gate = check_workstream_completion(root, workstream.name)
        if not gate.passed:
            continue
        report = workstream / "report.md"
        sections.append(
            f"## Workstream: {workstream.name}\n\n"
            + report.read_text(encoding="utf-8").strip()
        )

    if not sections:
        raise ValueError("No reviewed workstream reports are ready to render.")

    output = final_dir / "working_paper.md"
    content = (
        "# Working Paper\n\n"
        f"- rendered_at: {utc_timestamp()}\n"
        "- status: draft_from_reviewed_workstreams\n"
        "- note: This is a working paper, not a chat summary.\n\n"
        + "\n\n---\n\n".join(sections)
        + "\n"
    )
    _atomic_write_regular_file(output, content)
    return output


def _atomic_write_regular_file(path: Path, content: str) -> None:
    """Write beside the destination, then replace it without following a symlink."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Final report is not a regular file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # os.replace replaces a symlink itself; it does not follow the link.
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
