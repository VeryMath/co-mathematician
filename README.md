# Co-Mathematician

> English | [中文](README.zh-CN.md)

A lightweight, coding-agent-driven Co-Mathematician workspace pattern for mathematical research.
It is designed to work after cloning in Codex, Claude Code, Cursor, or another
repository-aware coding agent.

This project is inspired by the public design principles described in Google
DeepMind's [AI Co-Mathematician paper](https://arxiv.org/abs/2605.06651), but
it is **not** a reproduction of their system. It adapts those ideas into a
coding-agent-native, filesystem-based workflow.

This repository does **not** implement a new multi-agent platform. The coding
agent is the driver, the repository filesystem is the shared artifact store,
native subagents or independent reviewer passes act as workstream coordinators,
specialists, and reviewers, and the harness only provides schema, state, gating,
report skeletons, and validation scripts.

## What Is Included

- `AGENTS.md`: hard operating rules for Codex and other coding agents.
- `CLAUDE.md`: Claude Code entry instructions.
- `.cursor/rules/`: Cursor Agent rules.
- `.agents/skills/co-mathematician/`: the Skill and reusable templates.
- `.codex/`: narrow custom agent definitions for proof, computation, review, citation checking, and synthesis.
- `harness/co_math/`: a small Python harness for workspace state and gates.
- `workspace/`: an empty scaffold for a new project.

## What Is Not Included

- No solved research project.
- No downloaded paper corpus.
- No external repository snapshots.
- No web app or agent runtime.
- No proprietary prompts or private systems.

## Install

Python 3.9+ is supported.

```bash
python3 -m pip install -e .
co-math --help
```

Without installing:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli --help
```

## Use With A Coding Agent

Clone the repository, open it in your coding agent, and ask the agent to read the
right entry file before starting:

| Agent | Entry files |
| --- | --- |
| Codex | `AGENTS.md`, `.agents/skills/co-mathematician/SKILL.md`, `.codex/config.toml` |
| Claude Code | `CLAUDE.md`, `AGENTS.md`, `.agents/skills/co-mathematician/SKILL.md` |
| Cursor | `.cursor/rules/co-mathematician.mdc`, `AGENTS.md`, `.agents/skills/co-mathematician/SKILL.md` |

Suggested first prompt:

```text
Use this repository as a coding-agent-driven AI Co-Mathematician workspace.
Read the repository instructions first. You are the Project Coordinator.

Initialize the workspace, then start onboarding. First ask me to choose the
workspace document language policy. Do not solve the math problem, do not create
a workstream, and do not mark anything complete until the required goal approval
and reviewer gates pass.
```

The agent should then run:

```bash
python3 -m pip install -e ".[dev]"
co-math init --workspace workspace
```

## Use The Skill

Ask your coding agent to use the `co-mathematician` Skill or the local
instructions in `.agents/skills/co-mathematician/SKILL.md`. The workflow is:

```text
onboarding -> research question formalization -> goal approval -> workstreams -> reviewer loop -> final working paper
```

The core rule is simple: no workstream starts until the user explicitly approves
a goal, and no workstream is complete until an independent reviewer approves its
report. If the agent environment has no native subagent feature, use a separate
reviewer pass with a fresh prompt and save that review under the workstream
`reviews/` directory.

## Start A New Project

Initialize a workspace:

```bash
co-math init --workspace workspace
```

During onboarding, the Project Coordinator should update:

```text
workspace/project/PROJECT.md
workspace/project/GOALS.yaml
workspace/project/PROJECT_STATUS.md
workspace/project/messages.jsonl
```

The first onboarding preference should be the document language policy. Suggested
options:

1. English for all workspace documents.
2. User language for research notes, English for schemas, gates, and reviews.
3. User language for all human-readable research documents.
4. Match each project or conversation.

Record the selected policy in `PROJECT.md`, `PROJECT_STATUS.md`, and the
`language_policy` block of `GOALS.yaml`. Schema keys, gate names, statuses, and
harness commands stay in English.

Draft goals are not executable. A goal can receive workstreams only when its
status is exactly:

```yaml
status: approved
```

Check approval:

```bash
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
```

Create a workstream for an approved goal:

```bash
co-math new-workstream \
  --workspace workspace \
  --goal-id G1 \
  --title "Literature baseline review" \
  --kind literature
```

Allowed workstream kinds are `proof`, `computation`, `literature`, and `review`.

## Agent Roles

The Project Coordinator may delegate narrow work to subagents, task agents, or
separate reviewer passes:

- `proof_explorer`: proof strategies, reductions, examples, and proof gaps.
- `computational_experimenter`: scoped computations and reproducibility checks.
- `logic_reviewer`: logical correctness and dependency review.
- `adversarial_reviewer`: counterexamples, hidden assumptions, and overclaim checks.
- `citation_checker`: provenance and source-to-claim alignment.
- `synthesis_agent`: synthesis from reviewer-approved workstream reports only.

These roles are intentionally narrow. They cannot approve goals, start
unapproved workstreams, or mark their own reports complete.

## Harness Commands

```bash
co-math init --workspace workspace
co-math append-message --workspace workspace --sender project_coordinator --recipient user --type status --content "..."
co-math new-workstream --workspace workspace --goal-id G1 --title "..." --kind proof
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
co-math check-gate --workspace workspace --gate workstream_completion --workstream-id WS-G1-001-example
co-math render-final --workspace workspace
```

## Tests

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest harness/tests -q
```

## License

MIT. See `LICENSE`.
