# AGENTS.md

## Repository Contract

This repository is a coding-agent-driven AI Co-Mathematician workspace.

The coding agent is the driver:

- In Codex, the Codex main thread is the Project Coordinator.
- In Claude Code, the main Claude Code conversation is the Project Coordinator.
- In Cursor, the active Agent chat/session is the Project Coordinator.
- The repository filesystem is the shared artifact store.
- Native subagents, task agents, or separate reviewer passes are workstream coordinators, specialized agents, and reviewers.
- The harness only provides schemas, state files, gates, report skeletons, and validation scripts.
- Do not build a new multi-agent platform here.
- Do not start a mathematical research project during workspace initialization.

## Hard Rules

- Always run onboarding before goal approval.
- During onboarding, ask the user to choose a workspace document language policy.
- Always get explicit user approval of goals before starting any workstream.
- Never start a workstream for an unapproved goal.
- Important claims must include provenance.
- Failed explorations must be saved as durable artifacts.
- Uncertainty must be exposed explicitly in reports and status updates.
- Every workstream report must be reviewed by an independent reviewer subagent.
- A workstream whose review has not passed must not be marked complete.
- Final output must be a working paper, not a chat summary.

## Agent Compatibility

This workspace is intended to work after cloning in Codex, Claude Code, Cursor,
or another repository-aware coding agent.

- Codex should read `AGENTS.md`, `.codex/config.toml`, and the custom agent definitions in `.codex/agents/`.
- Claude Code should read `CLAUDE.md` and may use Task/subagent-style delegation for workstreams and reviews.
- Cursor should read `.cursor/rules/co-mathematician.mdc` and use Agent mode with durable file edits.
- If an environment has no native subagent feature, the Project Coordinator must still create an independent review pass with a fresh prompt and save the review artifact under the workstream `reviews/` directory.
- No agent may self-approve its own workstream report.

## Language Policy

At project start, ask the user which language policy to use for generated
workspace artifacts. Record the answer in `workspace/project/PROJECT.md`,
`workspace/project/PROJECT_STATUS.md`, and the `language_policy` block of
`workspace/project/GOALS.yaml`.

Schema keys, gate names, statuses, and harness commands must remain in English.
Human-readable research notes and final working papers may follow the user's
chosen project language.

## Architecture Principles

These rules are adapted from the public AI Co-Mathematician paper
`arXiv:2605.06651v2`:

- Mathematics research is broader than proof search: literature, examples, computation, counterexamples, definitions, and exposition are first-class work.
- Research intent is refined interactively; users should not need to front-load a perfect prompt.
- The workspace is stateful and artifact-centric; durable files matter more than transient chat.
- Workstreams can run in parallel, but all must remain tied to approved goals.
- Progressive disclosure matters: high-level project state belongs in project files, while low-level execution logs belong in workstream artifacts.
- Uncertainty is a managed project variable, not an error to hide.
- Failed attempts are permanent research artifacts and should inform later work.
- Review loops are hard gates against premature success claims.

## Fixed Workspace Layout

```text
workspace/
  project/
    PROJECT.md
    GOALS.yaml
    PROJECT_STATUS.md
    messages.jsonl
  workstreams/
  final/
```

Each workstream directory should contain:

```text
WORKSTREAM.md
status.yaml
messages.jsonl
plan.md
notes.md
artifacts/
failures/
reviews/
report.md
```

## Completion Gate

A workstream may be treated as complete only when:

- `report.md` exists.
- At least one independent reviewer has approved it.
- No blocking review remains unresolved.
- The report has explicit `Provenance`, `Uncertainty`, and `Failed Explorations` sections.
- Any code-backed claim has passing tests or is marked unverified.
- Project status has been updated to reflect the workstream state.

If the gate fails, preserve the failure and escalate rather than claiming completion.
