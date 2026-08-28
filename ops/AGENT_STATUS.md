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
