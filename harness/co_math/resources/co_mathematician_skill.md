---
name: co-mathematician
description: Use when creating, continuing, reviewing, or completing a durable coding-agent-driven mathematical research project.
---

# Co-Mathematician

Use the repository files as durable project memory. The active coding-agent
conversation coordinates the work; `co-math` only manages project files and
reports their current state.

## Project Lifecycle

- Create a project with `co-math new "<name>"`. Return the new path and ask the
  user to open that directory. Do not start the research in the creation
  conversation.
- Use `co-math list` to find existing projects.
- At the start of a project session, run `co-math resume --project .`.
- When unsure what to do, run `co-math next --project .` and take only the next
  useful action.
- Ask the user to confirm before archiving finished work with
  `co-math archive --project .`. Archiving never deletes research files. Use
  `co-math reopen --project .` to continue later.

Keep replies short: current situation, first blocker if any, and one next action.

## Research Workflow

1. Read `AGENTS.md` and the current files under `workspace/project/`.
2. During onboarding, ask the user to choose the document language and clarify
   the research question. Do not solve the problem yet.
3. Check `.agents/skills/` for a relevant mathematical domain Skill. If one is
   selected, follow its inner workflow.
4. Record the research question and draft goals in
   `workspace/project/GOALS.yaml`.
5. Start a workstream only after the user explicitly approves its goal.
6. Save proof attempts, computations, literature notes, failed routes, and
   uncertainty in the workstream directory. Reuse upstream files with
   `co-math new-workstream --input <workspace-relative-path>`; read the links in
   `inputs.md` and keep shared inputs unchanged instead of copying them.
7. Ask an independent reviewer to inspect every completed workstream report.
   The report author cannot approve their own report.
8. Produce `workspace/final/working_paper.md` as the final research output, not
   a chat summary.

## Durable Files

```text
workspace/project/       question, goals, status, messages
workspace/workstreams/   proofs, computations, literature, failures, reviews
workspace/final/         final working paper
```

Important claims must point to user input, literature, a proof, a computation,
or a review. Keep failed attempts and unresolved uncertainty visible.
