# CLAUDE.md

## Repository Contract

This repository is a coding-agent-driven AI Co-Mathematician workspace.

When Claude Code is operating in this repository:

- The main Claude Code conversation is the Project Coordinator.
- The repository filesystem is the shared artifact store.
- `agents/roles/` is the canonical role layer.
- `.claude/agents/` contains Claude Code adapters for the canonical roles.
- Task agents or clearly separated reviewer passes are workstream coordinators, specialized agents, and reviewers.
- The harness only provides schemas, state files, gates, report skeletons, and validation scripts.
- Do not build a new multi-agent platform here.
- Do not start a mathematical research project during workspace initialization.

## Required Flow

Default workspace mode:

```text
onboarding -> research question formalization -> goal approval -> workstreams -> reviewer loop -> final working paper
```

If the user explicitly invokes a project-local domain Skill, or accepts a Skill
suggested by `co-math suggest-skills`, enter skill-guided mode instead. Record
the handoff with `co-math skill-handoff` and follow that Skill's own opening,
modeling, and approval flow for the inner task. Promote the task into goals and
workstreams only when the user wants durable research output, reviewer-gated
claims, or a final working paper.

Hard rules:

- Default workspace mode runs onboarding before goal approval.
- During workspace-mode onboarding, ask the user to choose a workspace document language policy.
- Refresh the project-local skill registry at session start, after skill installation, and before formalizing goals.
- Before creating any workstream, match the workstream scope against the project-local skill registry and read any relevant `SKILL.md`.
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
- Treat `agents/roles/` as authoritative role definitions; `.claude/agents/` is only the Claude Code adapter layer.
- Install or copy project-specific Skills into `.agents/skills/` by default, not global skill roots, unless the user explicitly asks for a personal cross-project install.
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
co-math refresh-skills --workspace workspace
co-math suggest-skills --workspace workspace --query "..."
co-math skill-handoff --workspace workspace --skill optimization-skill --mode skill_guided --reason "..." --query "..."
co-math approve-goal --workspace workspace --goal-id G1 --approved-by user --approval-id approval-G1-001
co-math check-gate --workspace workspace --gate goal_approval --goal-id G1
co-math new-workstream --workspace workspace --goal-id G1 --title "..." --kind proof --author-run-id proof-run-001
co-math submit-review --workspace workspace --workstream-id <workstream-id> --reviewer logic_reviewer --reviewer-run-id review-run-001 --approved --severity info --issue-type logic --comment "Approved."
co-math check-gate --workspace workspace --gate workstream_readiness --workstream-id <workstream-id>
co-math complete-workstream --workspace workspace --workstream-id <workstream-id>
co-math check-gate --workspace workspace --gate workstream_completion --workstream-id <workstream-id>
co-math render-final --workspace workspace
python3 -m pytest harness/tests -q
```
