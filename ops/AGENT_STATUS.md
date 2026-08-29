# AGENT_STATUS.md — Workflow Statuses

## Pipeline (sequential)

```
BACKLOG → PLANNING → MOCKUP → MOCKUP_REVIEW → ARCHITECTURE → RED_TEAM_REVIEW →
READY_FOR_DEVELOPMENT → IN_DEVELOPMENT → CODE_REVIEW → QA → SECURITY_REVIEW →
READY_TO_RELEASE → DEPLOYED → DONE
```

This maps directly to the founder's stated workflow:
`IDEA → BRAINSTORM → PRODUCT REQUIREMENTS → DESIGN/MOCKUP → MOCKUP REVIEW →
ARCHITECTURE → RED TEAM REVIEW → READY FOR DEVELOPMENT → DEVELOPMENT →
CODE REVIEW → QA → SECURITY REVIEW → MARKETING/LAUNCH PREP → READY TO
RELEASE → RELEASE/DEPLOYMENT → DONE`

- `BACKLOG` + `PLANNING` cover Idea → Brainstorm → Product Requirements
  (owned by Product).
- `MOCKUP` is owned by Design; `MOCKUP_REVIEW` is the Product/Founder gate
  before `ARCHITECTURE` can start.
- `IN_DEVELOPMENT` covers Development (owned by Developer).
- Marketing is **not** a pipeline column — see "Parallel tracks" below.

## Interrupt states (reachable from any stage, return to the prior stage when resolved)

- `BLOCKED` — something external or unresolved is stopping progress.
- `FOUNDER_APPROVAL` — a founder-only decision (see `PROJECT.md`) is pending.

## Parallel tracks (not pipeline-blocking)

- **Marketing** engages during `PLANNING` (positioning input) and again
  before `READY_TO_RELEASE` (launch prep). It does not own a status.
- **Financial** engages whenever a task or company decision has a meaningful
  financial dimension, at any stage. It does not own a status.
- **CEO** and **Red Team** can be invoked at any stage for strategic or
  adversarial review; they don't own a stage either — they own outcomes
  (PASS/REJECT, a recommendation) recorded against whichever task or
  decision triggered them.

## Rules

- Failed QA returns the task to `IN_DEVELOPMENT`.
- A significant fix must go through `CODE_REVIEW` again — it does not skip
  back into QA directly.
- Do not invent additional statuses. If a real gap appears once Phase 1
  is running real tasks, propose a new decision (see `DECISIONS.md`) rather
  than adding a status silently.

## Release checklist — before any task moves to `DONE`

`ops/reports/CURRENT_STATUS.md` is generated from the live database
(`python3 ops/db/report.py`) — it is not a second source of truth, but a
stale copy of one is still misleading, and it went stale across three
milestones (TASK-005/006/007) before anyone noticed. Before recording a
task's final `task-status --to DONE`:

1. Run `python3 ops/db/report.py` and commit the regenerated
   `ops/reports/CURRENT_STATUS.md` in the same change as the task's
   completion.
2. Run `python3 ops/db/report.py --check` to confirm — it diffs a fresh
   generation against the committed file (ignoring only the
   "Generated &lt;timestamp&gt;" line) and exits non-zero if they differ.
   A non-zero exit means step 1 was skipped or something changed after
   the last regeneration; do not move the task to `DONE` until `--check`
   passes.

This is deliberately lightweight (one flag on the existing generator, no
new file, no CI system) — it makes staleness *checkable*, not just
documented as a convention to remember.
