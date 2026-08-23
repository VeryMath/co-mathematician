# Workstream

## Scope

- goal_id:
- kind:
- coordinator:
- author_run_id:
- status: active

## Inputs

- Approved goal:
- Project context:
- Constraints:
- Language policy:

## Plan

1. Record assumptions.
2. Gather or create durable artifacts.
3. Track failed explorations.
4. Draft report with provenance and uncertainty.
5. Submit to independent reviewer.

## Completion Gate

- `report.md` exists.
- Independent reviewer approval exists in `reviews/`.
- Reviewer run differs from `author_run_id` and matches the report SHA-256.
- No blocking review remains.
- Provenance, uncertainty, and failed explorations are explicit.
- `co-math complete-workstream` freezes the report under `reviewed/`.
