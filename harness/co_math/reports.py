from __future__ import annotations

from pathlib import Path

from .gating import check_workstream_completion
from .schemas import utc_timestamp


def render_final(workspace: str | Path, *, overwrite: bool = False) -> Path:
    root = Path(workspace)
    final_dir = root / "final"
    if final_dir.is_symlink():
        raise ValueError("The final directory must not be a symlink.")
    final_dir.mkdir(parents=True, exist_ok=True)
    output = final_dir / "working_paper.md"
    if output.is_symlink():
        raise ValueError("working_paper.md must not be a symlink.")
    if output.exists() and not overwrite:
        raise FileExistsError(
            "working_paper.md already exists. Keep your edits, or use "
            "render-final --overwrite to replace it."
        )

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

    content = (
        "# Working Paper\n\n"
        f"- rendered_at: {utc_timestamp()}\n"
        "- status: draft_from_reviewed_workstreams\n"
        "- note: This is a working paper, not a chat summary.\n\n"
        + "\n\n---\n\n".join(sections)
        + "\n"
    )
    with output.open("w" if overwrite else "x", encoding="utf-8") as handle:
        handle.write(content)
    return output
