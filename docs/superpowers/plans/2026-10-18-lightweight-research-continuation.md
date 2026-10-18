# Lightweight Research Continuation Implementation Plan

**Goal:** Implement the user-approved improvements 1, 3, and 4, then push to
VeryMath main: project continuation, precise material ranges, directory browsing
and filename search.

**Architecture:** Keep the current Python Core, Node API, React UI, and local
Markdown/JSON files. Read existing research state; do not add storage services,
model calls, dependencies, or a second agent runtime.

**Spec:** User-approved five-item proposal in this conversation, narrowed by the
user to items 1, 3, and 4, with a lightweight implementation and main-branch push.

## Boundaries And Interfaces

| Owner | Files | Contract |
| --- | --- | --- |
| Continuation | `harness/co_math/context.py` | Existing summary fields plus `open_question`, `resume_prompt`, `latest_note`; summaries do not approve goals or change files. |
| Material reading | `harness/co_math/materials.py` | `read_material(path, *, selection=None)` accepts page or paragraph start/end; returns `selection`, `selectionLabel`, `paragraphCount` when applicable. |
| Integration | `web_service.py`, `server/api.mjs`, `server/runs.mjs` | Pass explicit selection through preview and model context; report actual scope and any budget truncation. |
| File browsing | Core `file.list`, new React `FileBrowser` | `directory`, `query`, `offset`, `limit`; return paged `files`, `directories`, `directory`, `parent`, `nextOffset`, `hasMore`. No fixed total-file cutoff. |
| UI | `App.tsx`, `api.ts`, small focused components, CSS | Four-line continuation card and copyable handoff; range preview and attachments; directory navigation and paginated filename search. |

Selections use `startPage`/`endPage` for PDF, or `startParagraph`/`endParagraph`
for other supported text. Bounds are one-based integers; invalid selections
fail visibly. Existing requests without a selection retain their default read.
`runs.start` retains its `files` list and accepts an optional `ranges` object
keyed by selected file path. No range selection automatically sends a model
request. Files and shared inputs remain unchanged.

## Work

- [x] Extend read-only continuation summaries from status sections, recent notes,
  and saved web discussion; keep explicit research approval rules intact.
- [x] Add bounded PDF page and text paragraph extraction with source labels.
- [x] Replace the flat capped list with directory pages and filename search.
- [x] Connect the UI, API and model context; preserve project-switch isolation.
- [x] Update Chinese and English usage documents, retaining README style.
- [x] Run syntax/type/build/package and existing appropriate regression checks,
  inspect the actual UI, and review the complete changes independently.

Delivery: commit the verified tree, check remote ancestry, push normally to
VeryMath main and verify its remote head. The user also requested white surfaces
and visible Version Updates; these are included in the UI and bilingual docs.

## Review Focus

- Invalid or out-of-range selections must not be described as fully read.
- Material, directory, and project switches must not reuse old selections.
- Search must reach files beyond the previous 1,500-file cutoff.
- Continuation reads must not modify notes, conversations or goal approval.
- Corrupt optional web history must not make a healthy CLI project unusable.

Use existing dependencies and checks. Do not introduce prohibited storage
identity mechanisms, schemas, new test directories or substitute research runs.
