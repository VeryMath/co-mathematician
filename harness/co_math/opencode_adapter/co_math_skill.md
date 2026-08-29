---
name: co-math
description: Use when creating, finding, resuming, archiving, or reopening Co-Math research projects in OpenCode.
compatibility: opencode
---

# Co-Math Projects

Keep project management short and use the Co-Math tools for file changes.

- For a new project, ask only for the project name when it is missing. Use `match` for language, the configured project home, and Git by default.
- After creation, return the project path and ask the user to open that folder. Do not start research in the creation conversation.
- For an existing project, use `comath_project_resume` or `comath_project_next` before suggesting work.
- Use `comath_project_list` when the user asks what projects exist or which one to continue.
- Ask for confirmation before `comath_project_lifecycle` archives a project. Reopening is reversible and needs no extra ceremony.
- Reply in the user's language. Show the current situation and one next action, not internal status names.
