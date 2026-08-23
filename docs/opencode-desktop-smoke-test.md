# OpenCode Desktop Smoke Test

## Scope

- Release candidate: `0.3.0`
- Checklist date: `2026-08-23`
- Overall Desktop status: `not_run`
- Rule: CLI, unit, and wheel tests do not count as Desktop GUI verification.

## Automated Prerequisites

The following checks passed locally before this checklist was created:

- clean wheel build for `co_mathematician_workspace-0.3.0-py3-none-any.whl`
- wheel contents include the project template, canonical roles, OpenCode agents,
  and all five global typed tools
- wheel contents exclude `harness/tests`
- isolated Python 3.13 installation with declared dependencies
- `install-opencode` against a temporary OpenCode config directory
- independent project creation from the installed wheel
- `doctor` reports Core `0.3.0`, a valid project, and a healthy adapter
- `resume` reconstructs the new project's `onboarding` state from files

These results validate packaging and CLI integration only.

## Test Environment

Fill these fields during an actual Desktop run:

| Field | Value |
| --- | --- |
| OpenCode Desktop version | `not_recorded` |
| Operating system and version | `not_recorded` |
| Model/provider | `not_recorded` |
| Co-Math wheel or commit | `not_recorded` |
| Tester | `not_recorded` |
| Test date | `not_recorded` |

## Manual Gates

Do not change a result from `not_run` without recording direct GUI evidence.

| Gate | Result | Required evidence |
| --- | --- | --- |
| Global tool discovery after Desktop restart | `not_run` | Screenshot or log naming all five `comath_project_*` tools |
| Natural-language project creation | `not_run` | Prompt, tool call, and returned absolute project path |
| External-directory permission behavior | `not_run` | Observed permission prompt or documented absence |
| Open returned project directory | `not_run` | GUI shows the new project as the active folder |
| Project instructions and Skill discovery | `not_run` | Agent identifies `AGENTS.md` and the project-local Co-Math Skill |
| Project-local OpenCode agent discovery | `not_run` | GUI exposes the expected role adapters |
| Onboarding without premature workstream creation | `not_run` | First interaction asks for language policy and does not start research |
| Create a second independent project | `not_run` | Project B has a different path and project ID; project A is unchanged |
| Delete the OpenCode session and reopen the project | `not_run` | Old session is unavailable while project files remain |
| Natural-language resume in a fresh session | `not_run` | Tool reconstructs state and reports the correct next gate |

## Procedure

1. Install the release candidate in a stable Python environment.
2. Run `co-math install-opencode --projects-home <absolute-projects-root>`.
3. Restart OpenCode Desktop.
4. Ask OpenCode to create a Co-Math project using natural language.
5. Open the absolute directory returned by the tool.
6. Complete onboarding only; verify that no workstream starts before goal approval.
7. Create a second project from another conversation and verify isolation.
8. Delete the first project's OpenCode session, reopen its directory, and ask to resume.
9. Record exact evidence and change each observed result to `pass` or `fail`.

## Release Decision

OpenCode Desktop support is release-verified only when every manual gate is
`pass`. Any `not_run` or `fail` leaves the Desktop claim unverified, even when
all automated tests pass.
