from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .gating import check_workstream_completion
from .schemas import utc_timestamp


def render_final(
    workspace: str | Path, *, overwrite: bool = False, outline: bool = False
) -> Path:
    root = Path(workspace)
    final_dir = root / "final"
    if final_dir.is_symlink():
        raise ValueError("The final directory must not be a symlink.")
    final_dir.mkdir(parents=True, exist_ok=True)
    filename = "working_paper_outline.md" if outline else "working_paper.md"
    output = final_dir / filename
    if output.is_symlink():
        raise ValueError(f"{filename} must not be a symlink.")
    if output.exists() and not overwrite:
        raise FileExistsError(
            f"{filename} already exists. Keep your edits, or use "
            "render-final --overwrite to replace it."
        )

    sections: list[str] = []
    for workstream in sorted((root / "workstreams").glob("*")):
        if workstream.is_symlink() or not workstream.is_dir():
            continue
        report = workstream / "report.md"
        if report.is_symlink() or not report.is_file():
            continue
        gate = check_workstream_completion(root, workstream.name)
        if not gate.passed:
            continue
        label = workstream.name.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        path = quote(report.relative_to(root).as_posix())
        link = f"[{label}](../{path})"
        if outline:
            sections.append(f"- {link}")
        else:
            sections.append(
                f"## Workstream: {label}\n\n"
                f"Source report: {link}\n\n"
                + report.read_text(encoding="utf-8").strip()
            )

    if not sections:
        raise ValueError("No reviewed workstream reports are ready to render.")

    content = (
        "# Working Paper\n\n"
        f"- rendered_at: {utc_timestamp()}\n"
    )
    if outline:
        content += (
            "- status: outline\n\n"
            "## Research Question and Assumptions\n\n"
            "## Results and Proofs\n\n"
            "## Limitations and Open Questions\n\n"
            "## Reviewed Source Reports\n\n"
            + "\n".join(sections) + "\n"
        )
    else:
        content += "- status: draft_from_reviewed_workstreams\n\n"
        content += "\n\n---\n\n".join(sections) + "\n"
    with output.open("w" if overwrite else "x", encoding="utf-8") as handle:
        handle.write(content)
    return output
