from __future__ import annotations

import yaml

from harness.co_math.cli import main


REPORT = """# CLI Report

## Provenance
- Source: CLI lifecycle test

## Uncertainty
- None

## Failed Explorations
- None
"""


def test_cli_runs_approved_reviewed_completion_lifecycle(tmp_path):
    workspace = tmp_path / "workspace"
    assert main(["init", "--workspace", str(workspace)]) == 0
    (workspace / "project" / "GOALS.yaml").write_text(
        yaml.safe_dump(
            {
                "language_policy": {"status": "selected"},
                "research_question": {"status": "approved", "text": "Question"},
                "goals": [
                    {
                        "id": "G1",
                        "title": "CLI goal",
                        "status": "draft",
                        "workstreams": [],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "approve-goal",
                "--workspace",
                str(workspace),
                "--goal-id",
                "G1",
                "--approved-by",
                "user",
                "--approval-id",
                "approval-cli-001",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "new-workstream",
                "--workspace",
                str(workspace),
                "--goal-id",
                "G1",
                "--title",
                "CLI lifecycle",
                "--kind",
                "proof",
                "--author-run-id",
                "author-cli-001",
            ]
        )
        == 0
    )
    workstream = next((workspace / "workstreams").iterdir())
    (workstream / "report.md").write_text(REPORT, encoding="utf-8")

    assert (
        main(
            [
                "submit-review",
                "--workspace",
                str(workspace),
                "--workstream-id",
                workstream.name,
                "--reviewer",
                "logic_reviewer",
                "--reviewer-run-id",
                "review-cli-001",
                "--approved",
                "--severity",
                "info",
                "--issue-type",
                "logic",
                "--comment",
                "Approved.",
                "--review-id",
                "logic-cli.json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "complete-workstream",
                "--workspace",
                str(workspace),
                "--workstream-id",
                workstream.name,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "check-gate",
                "--workspace",
                str(workspace),
                "--gate",
                "workstream_completion",
                "--workstream-id",
                workstream.name,
            ]
        )
        == 0
    )
    assert main(["render-final", "--workspace", str(workspace)]) == 0
    assert (workspace / "final" / "generated_draft.md").is_file()
