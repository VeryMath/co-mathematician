from __future__ import annotations

import yaml

from harness.co_math.reports import render_final
from harness.co_math.reviews import submit_review
from harness.co_math.workspace import complete_workstream, init_workspace, new_workstream


def write_goals(workspace):
    (workspace / "project" / "GOALS.yaml").write_text(
        yaml.safe_dump(
            {
                "language_policy": {"status": "selected"},
                "research_question": {"status": "approved"},
                "goals": [
                    {
                        "id": "G1",
                        "title": "Approved goal",
                        "status": "approved",
                        "approved_by": "user",
                        "approved_at": "2026-07-11T00:00:00Z",
                        "approval_id": "approval-1",
                        "workstreams": [],
                    },
                    {
                        "id": "G2",
                        "title": "Second approved goal",
                        "status": "approved",
                        "approved_by": "user",
                        "approved_at": "2026-07-11T00:00:00Z",
                        "approval_id": "approval-2",
                        "workstreams": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def approve(workspace, workstream):
    submit_review(
        workspace,
        workstream_id=workstream.name,
        reviewer="logic_reviewer",
        reviewer_run_id="logic-review-run",
        approved=True,
        severity="info",
        issue_type="logic",
        comment="Approved for scaffold rendering.",
        review_id="logic_reviewer.json",
    )
    complete_workstream(workspace, workstream_id=workstream.name)


def test_render_final_includes_only_approved_workstream_reports(tmp_path):
    workspace = tmp_path / "workspace"
    init_workspace(workspace)
    write_goals(workspace)
    approved_ws = new_workstream(
        workspace, goal_id="G1", title="Approved workstream", kind="proof"
    )
    unapproved_ws = new_workstream(
        workspace, goal_id="G2", title="Unapproved workstream", kind="computation"
    )

    approved_ws.joinpath("report.md").write_text(
        """# Approved Workstream

## Summary
This report is eligible for final rendering.

## Provenance
- Source: harness/tests/test_report_rendering.py

## Uncertainty
- No mathematical uncertainty because this is scaffold-only.

## Failed Explorations
- No failed mathematical exploration was started.
""",
        encoding="utf-8",
    )
    approve(workspace, approved_ws)

    unapproved_ws.joinpath("report.md").write_text(
        """# Unapproved Workstream

## Summary
This should not appear because review approval is missing.

## Provenance
- Source: harness/tests/test_report_rendering.py

## Uncertainty
- Not approved.

## Failed Explorations
- None.
""",
        encoding="utf-8",
    )

    output_path = render_final(workspace)
    rendered = output_path.read_text(encoding="utf-8")

    assert output_path == workspace / "final" / "generated_draft.md"
    assert "Approved Workstream" in rendered
    assert "Unapproved Workstream" not in rendered
    assert "## Provenance" in rendered
    assert "## Uncertainty" in rendered
    assert "## Failed Explorations" in rendered
