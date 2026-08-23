# Co-Math Research Project

This directory is one independent Co-Math research project. Its identity is in
`co-math.toml`; durable research state is under `workspace/`.

Open this directory in a repository-aware coding agent. At the start of a new
session, the Project Coordinator should:

1. Read `AGENTS.md` and `.agents/skills/co-mathematician/SKILL.md`.
2. Run `co-math resume --project .` to reconstruct the current state.
3. Run `co-math refresh-skills --workspace workspace`.
4. Continue from the next reported gate instead of relying on chat history.

Do not edit `co-math.toml` to record changing research status. Do not create a
workstream before its goal has explicit user approval, and do not complete a
workstream before an independent review passes.
