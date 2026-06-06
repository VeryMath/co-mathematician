---
name: co-mathematician
description: Use when conducting a coding-agent-driven mathematical research project that needs durable workspace state, approved goals, parallel workstreams, reviewer gates, provenance, uncertainty tracking, failed exploration records, and a final working paper.
---

# Co-Mathematician

Use this skill to run mathematical research as a stateful coding-agent workspace.
The repository-aware coding agent remains the driver; do not implement a new
platform. The harness is only for state, schema, gates, report skeletons, and
validation.

## Agent Model

- The active main conversation/session in the chosen coding agent is the Project Coordinator.
- Platform examples: Codex main thread, Claude Code main conversation, Cursor active Agent chat/session.
- The repository filesystem is the shared artifact store.
- Project-local skills under `.agents/skills/` are the default skill environment.
- `agents/roles/` is the canonical role layer.
- `.codex/agents/`, `.claude/agents/`, and `.cursor/rules/` are platform adapters.
- Native subagents, task agents, Cursor Agent sessions, or separate reviewer passes are workstream coordinators, specialized agents, and reviewers.
- If native subagents are unavailable, create an independent reviewer pass with a fresh prompt and save the review artifact under the workstream `reviews/` directory.
- No agent may self-approve its own report.

## Adapter Architecture

Use `agents/roles/` as the authoritative role definitions. Platform-specific
adapters may use different formats, but must preserve the same boundaries:

```text
agents/roles/       canonical role cards
.codex/agents/      Codex TOML adapters
.claude/agents/     Claude Code Markdown subagent adapters
.cursor/rules/      Cursor project-rule adapters
```

Adapters must not approve goals, start unapproved workstreams, mark workstreams
complete, or let a report author approve their own report.

## Project-Local Skill Environment

Install or copy additional research skills into this repository's
`.agents/skills/` directory by default. This keeps AI4Math skill libraries and
project-specific research workflows portable with the workspace.

Use global skill roots such as `~/.codex/skills` or `~/.agents/skills` only when
the user explicitly asks for a personal installation shared across projects.
Do not assume that a global skill install is visible to every coding agent or
collaborator who opens this repository.

Refresh the project-local skill registry at session start, after installing or
copying skills, and before formalizing goals:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli refresh-skills --workspace workspace
```

Before proposing goals or creating a workstream, match the scope against the
registry:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli suggest-skills --workspace workspace --query "..."
```

If a relevant project-local skill is suggested, read its `SKILL.md` before
planning the goal or workstream. This is a workspace-level discovery contract; it
does not replace the coding agent's native skill registry.

## Non-Negotiable Flow

```text
onboarding -> research question formalization -> goal approval -> workstreams -> reviewer loop -> final working paper
```

- Do not solve the math problem during onboarding.
- Ask the user to choose a workspace document language policy during onboarding.
- Do not start a workstream until the user explicitly approves a goal.
- Do not mark a workstream complete until an independent reviewer approves its report.
- Do not hide uncertainty, failed attempts, or missing provenance.

## Onboarding

Collect enough context to write `workspace/project/PROJECT.md`:

- workspace document language policy
- problem statement and mathematical setting
- definitions, notation, constraints, and allowed assumptions
- known references and user-provided artifacts
- desired output type and unacceptable shortcuts
- user expertise, steering preferences, and review expectations

Record durable status in `workspace/project/messages.jsonl`. Keep user-facing chat high level; put detailed logs in files.

Recommended language policy options:

1. English for all workspace documents.
2. User language for research notes, English for schemas, gates, and reviews.
3. User language for all human-readable research documents.
4. Match each project or conversation.

Record the selected policy in `workspace/project/PROJECT.md`,
`workspace/project/PROJECT_STATUS.md`, and the `language_policy` block of
`workspace/project/GOALS.yaml`. Schema keys, gate names, statuses, and harness
commands stay in English.

## Research Question And Goals

Write a formal research question and proposed goals in `workspace/project/GOALS.yaml`. Goals begin as drafts. Ask the user to approve or revise them. Only goals with `status: approved` may receive workstreams.

Use:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli check-gate --workspace workspace --gate goal_approval --goal-id G1
```

## Workstreams

Create workstreams only after goal approval:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli new-workstream --workspace workspace --goal-id G1 --title "..." --kind proof
```

Valid kinds are `proof`, `computation`, `literature`, and `review`.

Workstreams must write durable artifacts:

- `WORKSTREAM.md` for scope
- `plan.md` for route
- `notes.md` for running observations
- `messages.jsonl` for internal messages
- `artifacts/` for code, tables, figures, proof sketches, or citations
- `failures/` for dead ends and rejected attempts
- `reviews/` for independent reviewer output
- `report.md` for the reviewed workstream report

## Internal Messages As JSONL

Each message must include:

```json
{
  "timestamp": "...",
  "sender": "...",
  "recipient": "...",
  "type": "status",
  "content": "...",
  "provenance": [],
  "uncertainty": []
}
```

Use message types: `status`, `instruction`, `question`, `proposal`, `decision`, `artifact`, `review`, `failure`.

## Provenance And Uncertainty

Every important claim must be traceable to one or more of:

- user input
- literature reference
- internal artifact
- computation output
- proof sketch
- reviewer comment
- failed exploration

Reports must contain explicit `Provenance`, `Uncertainty`, and `Failed Explorations` sections.

## Reviewer Loop

Send each workstream report to an independent reviewer subagent, task agent, or fresh reviewer pass. Reviewers should output JSON matching `assets/reviewer_output_schema.json`.

If review fails:

- preserve the review in `reviews/`
- revise or escalate
- keep unresolved uncertainty visible
- do not mark the workstream complete

Use:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli check-gate --workspace workspace --gate workstream_completion --workstream-id <id>
```

## Final Working Paper

Render final output only from reviewed workstream reports:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli render-final --workspace workspace
```

The final output is `workspace/final/working_paper.md`. It is a working paper, not a chat summary.

## Assets

Use templates in `assets/` when creating project files, goals, workstreams, reports, or reviewer output.
