# Agent Role Architecture

`agents/roles/` is the canonical source for Co-Mathematician agent roles.
Platform-specific files under `.codex/`, `.claude/`, and `.cursor/` are adapters.
The workspace protocol does not depend on any single coding-agent platform.

```text
agents/roles/       canonical role cards
.codex/agents/      Codex adapter definitions
.claude/agents/     Claude Code adapter definitions
.cursor/rules/      Cursor rules and role-routing adapter
```

Adapters may use platform-specific syntax, model selectors, or delegation
mechanisms, but they must preserve the role boundaries from `agents/roles/`.

No adapter may approve goals, start workstreams for unapproved goals, or mark its
own report complete.
