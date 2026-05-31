# CLAUDE.md

## Repository Contract

This repository is a coding-agent-driven AI Co-Mathematician workspace.

When Claude Code is operating in this repository:

- The main Claude Code conversation is the Project Coordinator.
- The repository filesystem is the shared artifact store.
- Task agents or clearly separated reviewer passes are workstream coordinators, specialized agents, and reviewers.
- The harness only provides schemas, state files, gates, report skeletons, and validation scripts.
- Do not build a new multi-agent platform here.
- Do not start a mathematical research project during workspace initialization.

## Required Flow

```text
onboarding -> research question formalization -> goal approval -> workstreams -> reviewer loop -> final working paper
```

Hard rules:

- Always run onboarding before goal approval.
- During onboarding, ask the user to choose a workspace document language policy.
- Always get explicit user approval of goals before starting any workstream.
- Never start a workstream for an unapproved goal.
- Important claims must include provenance.
- Failed explorations must be saved as durable artifacts.
- Uncertainty must be exposed explicitly in reports and status updates.
- Every workstream report must be reviewed by an independent reviewer pass or agent.
- A workstream whose review has not passed must not be marked complete.
- Final output must be a working paper, not a chat summary.

## Claude Code Operating Notes

- Treat this file and `AGENTS.md` as the repository-level contract.
- Use the `co-mathematician` Skill if it is installed; otherwise follow `.agents/skills/co-mathematician/SKILL.md`.
- Use `co-math` commands only for workspace state, gates, and report rendering.
- Use Claude Code Task/subagent-style delegation for narrow proof, computation, citation, logic-review, adversarial-review, or synthesis work when available.
- If no delegation mechanism is available, run a separate reviewer pass from a fresh reviewer prompt and save the output in `workspace/workstreams/<id>/reviews/`.
- Never let the author of a report approve that same report.
- Record the user's language policy in `workspace/project/PROJECT.md`,
  `workspace/project/PROJECT_STATUS.md`, and the `language_policy` block of
  `workspace/project/GOALS.yaml`; keep schema keys, gate names, statuses, and
  harness commands in English.

## Harness Commands

```bash
python3 -m pip install -e ".[dev]"
co-math init --workspace workspace
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
co-math new-workstream --workspace workspace --goal-id G1 --title "..." --kind proof
co-math check-gate --workspace workspace --gate workstream_completion --workstream-id <workstream-id>
co-math render-final --workspace workspace
python3 -m pytest harness/tests -q
```
