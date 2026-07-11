from __future__ import annotations

from pathlib import Path

from .gating import check_final_render
from .schemas import utc_timestamp
from .storage import (
    atomic_write_text,
    bytes_sha256,
    resolve_managed_directory,
    resolve_managed_file,
    workspace_lock,
)
from .workspace import (
    _refresh_project_status_unlocked,
    resolve_workstream_path,
)


def render_final(workspace: str | Path) -> Path:
    root = Path(workspace)
    with workspace_lock(root):
        gate = check_final_render(root)
        if not gate.passed:
            raise ValueError("No reviewed workstream reports are ready to render.")

        sections: list[str] = []
        for workstream_id in gate.details["approved_workstreams"]:
            workstream = resolve_workstream_path(root, workstream_id)
            descriptor = gate.details["snapshots"][workstream_id]
            reviewed_dir = resolve_managed_directory(workstream, "reviewed")
            snapshot = resolve_managed_file(workstream, descriptor["path"])
            if snapshot.parent != reviewed_dir:
                raise ValueError(
                    f"Reviewed snapshot path is invalid: {descriptor['path']}"
                )
            snapshot_bytes = snapshot.read_bytes()
            if bytes_sha256(snapshot_bytes) != descriptor["sha256"]:
                raise ValueError(
                    f"Reviewed snapshot digest changed: {workstream_id}"
                )
            sections.append(
                f"## Workstream: {workstream_id}\n\n"
                f"- reviewed_report_sha256: `{descriptor['sha256']}`\n\n"
                + snapshot_bytes.decode("utf-8").strip()
            )

        final_dir = resolve_managed_directory(root, "final", create=True)
        output = final_dir / "generated_draft.md"
        atomic_write_text(
            output,
            "# Generated Working-Paper Draft\n\n"
            f"- rendered_at: {utc_timestamp()}\n"
            "- status: generated_from_reviewed_snapshots\n"
            "- note: A synthesis agent may revise this into working_paper.md.\n\n"
            + "\n\n---\n\n".join(sections)
            + "\n",
        )
        _refresh_project_status_unlocked(root)
        return output
