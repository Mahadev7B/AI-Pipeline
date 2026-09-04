# Milestone D Design Review — Project / Phase Progress (`/progress.html`)

Design-review mockups for TASK-022 (DEC-009 Milestone D, the fourth and
final Founder UI Completeness milestone), reviewing CTO's architecture
in `ops/reviews/cto-milestone-d-architecture.md`. Static mockups (not a
clickable prototype) — matches CTO's own zero-client-side-JS constraint
and every prior Control Center screen, same discipline as
`ops/mockups/milestone-a/`, `-b/`, `-c/`.

Visual language copied verbatim from
`ops/mockups/control-center-phase-0/Main.dc.html` / `ops/control-center/layout.py`
(Style A, dark) — no new visual system introduced. Nav bar shows the
full 13-item list with "Progress" placed after Decisions, before Risks,
per CTO's Part 8.1.

Content is **real data**, sourced directly from the live database and
CTO's own architecture document as of 2026-09-01. The `phases` table
itself does not exist in the live `operations.sqlite3` yet (confirmed:
`SELECT name FROM sqlite_master WHERE type='table' AND name='phases'`
returns no rows) — CTO's document has not been implemented, only
designed. These mockups render exactly the real values CTO's Parts 3–5
name for the eventual backfill (Phase 0/1/2/3/3A statuses, the UI
Completeness sub-plan's real 3-of-4, DEC ids 2/5/10/12/13, TASK ids
15/16/17/18/19/20/21/22 and their real live statuses queried this
session — TASK-016/017 both `FOUNDER_APPROVAL`, TASK-018 `ARCHITECTURE`,
TASK-022 `MOCKUP_REVIEW`), not hand-typed placeholder data.

## Three artboards, published as one canvas

- `Main.dc.html` — **Concept A, recommended.** CTO's flat phase tree
  exactly as specified (Part 4.3), plus one addition: a "Right now"
  panel between the readiness header and the phase tree, surfacing the
  Founder UI Completeness sub-plan's 3-of-4 state and the three
  in-flight tasks (TASK-016/017/018) above the fold — before the
  Founder has to scroll past three "Complete" historical phase rows.
  The readiness header (two booleans, pill + one honest clause each)
  matches CTO's Part 4.2 almost verbatim.
- `TwoZone.dc.html` — **Concept B, alternate, not recommended.** A
  genuinely different information architecture: a dominant "Live now"
  zone (Phase 3's full subtree, expanded, plus the in-flight tasks
  colocated in the same zone) versus a visually receded, single-line-
  per-row "Company history" zone below it — reordering by recency
  instead of CTO's fixed phase-number order.
- `Closeup.dc.html` — three isolated comparisons: (1) readiness-boolean
  treatment (stark boolean-only vs. full narrated sentence vs. the
  recommended pill + one honest clause), (2) the new `paused` status
  pill's color against this project's already-established semantics
  (red/violet rejected, blue recommended), (3) whether one level of
  tree nesting (Phase 3 → Founder UI Completeness → Milestone D) reads
  clearly with indent + left-border connector alone, no accordion.

Published as one multi-artboard canvas — an Artifact, not application
code: https://claude.ai/code/artifact/ec86a51c-365e-4621-95d2-5bab56c92cfd

See `ops/reviews/design-review-milestone-d.md` for the full review,
verdict, and specific recommendations relative to CTO's architecture.
