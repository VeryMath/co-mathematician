# Co-Mathematician Workspace

> English | [中文](README.zh-CN.md)

Co-Mathematician is a lightweight research workspace for using a repository-aware
coding agent as an AI co-mathematician. It is designed to be cloned, opened in a
repository-aware coding agent, and used as a stateful mathematical research
environment. Codex, Claude Code, Cursor, OpenCode, and similar tools are
adapters to the same workspace protocol.

The core formula is:

```text
coding agent + repo filesystem + gates + reviewer loop = research workspace
```

This project is inspired by public design principles from Google DeepMind's
[AI Co-Mathematician paper](https://arxiv.org/abs/2605.06651), but it is **not**
a reproduction of their system.

## What This Workspace Does

Co-Mathematician turns a math research conversation into a file-backed project:

- the coding agent main thread acts as the Project Coordinator
- `workspace/project/` stores the research question, goals, status, and messages
- `workspace/workstreams/` stores proof, computation, literature, and review work
- reviewer agents or separate reviewer sessions check reports before completion
- `workspace/final/working_paper.md` is rendered only from reviewed reports

The Python harness does not run agents. It only initializes files, appends
messages, creates approved workstreams, checks gates, and renders the final
working paper.

## Install And Open The Workspace

You can set up the workspace manually, or ask your coding agent to do it.

### Agent-led setup

If your coding agent can run shell commands, start with:

```text
Please clone this repository:
https://github.com/VeryMath/co-mathematician

Open it as the current workspace, install the local harness, and initialize
`workspace/`. After that, start Co-Mathematician onboarding.
Do not start any mathematical workstream yet.
```

### Manual setup

Clone the repository:

```bash
git clone https://github.com/VeryMath/co-mathematician.git
cd co-mathematician
```

Install the local harness:

```bash
python3 -m pip install -e ".[dev]"
co-math --help
```

Initialize the workspace files:

```bash
co-math init --workspace workspace
```

Then open this folder in your coding agent.

Suggested options:

- **Any repository-aware coding agent**: read `AGENTS.md`,
  `.agents/skills/co-mathematician/SKILL.md`, and `agents/roles/`.
- **Codex adapter**: also use `.codex/config.toml` and `.codex/agents/*.toml`.
- **Claude Code**: open this repository and let Claude Code read `CLAUDE.md`,
  `AGENTS.md`, `agents/roles/`, and `.claude/agents/`.
- **Cursor**: open this repository and use the rules in `.cursor/rules/`.
- **OpenCode + DeepSeek or another provider**: configure your model provider
  first, then open this repository. Never paste API keys into repo files.

Without installing the package, use:

```bash
PYTHONPATH=. python3 -m harness.co_math.cli --help
```

### Project-local skills

For AI4Math skill libraries and project-specific research workflows, install
skills into this repository by default:

```text
.agents/skills/
```

The registry scanner discovers both `.agents/skills/<skill>/SKILL.md` and nested
layouts such as `.agents/skills/<category>/<skill>/SKILL.md`.

Use global skill roots such as `~/.codex/skills` or `~/.agents/skills` only when
you intentionally want a personal installation shared across projects.

For example, to bring a local AI4Math skill library into this workspace:

```bash
mkdir -p .agents/skills
rsync -a /path/to/AI4Math-Skill-Library/skills/ .agents/skills/
co-math refresh-skills --workspace workspace
co-math suggest-skills --workspace workspace --query "Stiefel manifold optimization"
```

`suggest-skills` refreshes the project-local registry by default, so newly copied
skills are visible to the workspace even when the coding agent's native skill
registry has not reloaded yet. If it suggests a relevant skill, ask the Project
Coordinator to read that `SKILL.md` before proposing goals or creating a
workstream.

## First Interaction

After opening the repository in your coding agent, start with a prompt like:

```text
I want to start a Co-Mathematician research project with this repository.

Please check the workspace state first, refresh the project-local skill registry,
and guide me through onboarding.
Do not start concrete research yet.
```

The first onboarding choice should be the workspace document language policy:

1. English for all workspace documents.
2. User language for research notes, English for schemas, gates, and reviews.
3. User language for all human-readable research documents.
4. Match each project or conversation.

## Starting A Research Project

Give the agent your problem context only after onboarding starts:

```text
I want to start a mathematical research project.

Problem context:
...

Known definitions, notation, and constraints:
...

Relevant references or files:
...

Please formalize the research question and propose goals.
Do not create workstreams yet.
```

The Project Coordinator should update:

```text
workspace/project/PROJECT.md
workspace/project/GOALS.yaml
workspace/project/PROJECT_STATUS.md
workspace/project/messages.jsonl
```

Draft goals are not executable. A goal can receive workstreams only when its
status is:

```yaml
status: approved
```

Check a goal gate:

```bash
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
```

Approve goals in chat with a clear instruction:

```text
I approve goal G1 as written.
You may create workstreams for G1.
```

## Creating Workstreams

After goal approval, ask the Project Coordinator to create focused workstreams:

```text
Create a literature workstream for approved goal G1.
The workstream should identify relevant known results, exact theorem
statements, assumptions, and citation provenance.
```

or:

```text
Create a proof exploration workstream for approved goal G1.
Preserve failed attempts and expose unresolved uncertainty in the report.
```

The harness command is:

```bash
co-math new-workstream \
  --workspace workspace \
  --goal-id G1 \
  --title "Literature baseline review" \
  --kind literature
```

Allowed workstream kinds are `proof`, `computation`, `literature`, and `review`.

Each workstream should produce a report with:

- provenance for important claims
- explicit uncertainty
- failed explorations
- independent reviewer output under `reviews/`

Check completion:

```bash
co-math check-gate \
  --workspace workspace \
  --gate workstream_completion \
  --workstream-id WS-G1-001-example
```

## Rendering The Working Paper

When workstream reports pass independent review, render the final working paper:

```bash
co-math render-final --workspace workspace
```

The output is:

```text
workspace/final/working_paper.md
```

This is a working paper, not a chat summary. It should preserve provenance,
uncertainty, failed explorations, and reviewer status.

## Workspace Framework

```mermaid
flowchart TD
    User["Human mathematician"] --> Coordinator["Coding agent main thread<br/>Project Coordinator"]

    Coordinator --> Onboarding["Onboarding<br/>context, language policy, notation, constraints"]
    Onboarding --> ProjectFiles["Project state<br/>PROJECT.md<br/>GOALS.yaml<br/>PROJECT_STATUS.md<br/>messages.jsonl"]

    ProjectFiles --> GoalGate{"Goal approved?"}
    GoalGate -- "no" --> Onboarding
    GoalGate -- "yes" --> Workstreams["Approved workstreams"]

    Workstreams --> Proof["Proof exploration"]
    Workstreams --> Compute["Computational experiment"]
    Workstreams --> Literature["Literature / citation check"]
    Workstreams --> ReportDraft["Report drafting"]

    Proof --> Artifacts["Durable artifacts<br/>notes, code, logs, failures"]
    Compute --> Artifacts
    Literature --> Artifacts
    ReportDraft --> Report["workstreams/*/report.md"]
    Artifacts --> Report

    Report --> Reviewers["Independent reviewers<br/>logic, adversarial, citation"]
    Reviewers --> ReviewGate{"Review passed?"}
    ReviewGate -- "no" --> Revision["Revise or escalate<br/>preserve uncertainty and failures"]
    Revision --> Workstreams
    ReviewGate -- "yes" --> Complete["Workstream complete"]

    Complete --> Final["final/working_paper.md"]

    Harness["co-math harness<br/>init, messages, workstreams, gates, render-final"]
    Harness -. validates .-> GoalGate
    Harness -. validates .-> ReviewGate
    Harness -. renders .-> Final
```

## Harness Commands

```bash
co-math init --workspace workspace
co-math refresh-skills --workspace workspace
co-math suggest-skills --workspace workspace --query "..."
co-math append-message --workspace workspace --sender project_coordinator --recipient user --type status --content "..."
co-math new-workstream --workspace workspace --goal-id G1 --title "..." --kind proof
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
co-math check-gate --workspace workspace --gate workstream_completion --workstream-id WS-G1-001-example
co-math render-final --workspace workspace
```

## Agent Adapters

Co-Mathematician separates role definitions from platform-specific adapters:

```text
agents/roles/       canonical, platform-neutral role cards
.codex/agents/      Codex TOML adapters
.claude/agents/     Claude Code Markdown subagent adapters
.cursor/rules/      Cursor project-rule adapters
```

| Coding agent | Reads first | Native adapter |
| --- | --- | --- |
| Generic repository-aware agent | `AGENTS.md`, `.agents/skills/co-mathematician/SKILL.md`, `agents/roles/` | no native adapter required |
| Codex | same generic files | `.codex/config.toml`, `.codex/agents/*.toml` |
| Claude Code | `CLAUDE.md`, `AGENTS.md`, `agents/roles/` | `.claude/agents/*.md` |
| Cursor | `.cursor/rules/co-mathematician.mdc`, `.cursor/rules/co-mathematician-roles.mdc`, `agents/roles/` | Cursor project rules and focused Agent sessions |

If your coding-agent environment has no native subagent feature, use a fresh
reviewer prompt or a separate session and save the review under the workstream
`reviews/` directory.

## Repository Layout

```text
AGENTS.md
CLAUDE.md
.agents/skills/co-mathematician/
agents/roles/
.codex/
.claude/
.cursor/
harness/co_math/
workspace/
```

## Tests

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest harness/tests -q
```

## License

MIT. See `LICENSE`.
