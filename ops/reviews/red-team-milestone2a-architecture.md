# Red Team Review — Phase 2, Milestone 2A Architecture

Reviewing `ops/reviews/cto-milestone2a-architecture.md` before Development.

## No live server, static multi-page nav, shared layout module
No objection. Same reasoning as Milestone 1, correctly extended — zero
JS, zero running process, real file-to-file navigation. Matches the
Founder's explicit scope boundary (no interactivity this milestone).

## Pipeline stage mapping as derived logic
No objection — correctly modeled as a deterministic function of
`tasks.status`, placed in `derived_state.py` rather than invented per
screen. Matches the existing `company_health()`/`task_progress_*`
pattern.

## Agent grouping resolution (option 3: group/sort by real state)
**Agree, and the reasoning is correct, not just acceptable.** The
Founder's data rules this milestone are explicit: no invented structure
the schema doesn't back. A hand-coded name→group table would be exactly
that, dressed up as "UI categorization" rather than "fake data" — same
problem, different label. Sorting by real `agent_runs` state answers a
more useful question anyway. No objection; this is the right call.

## Required before implementation (blocking)

1. **Backfill DEC-001 through DEC-003 into the `decisions` table,
   don't just footnote the gap.** CTO's plan shows 2 real rows with a
   note pointing to `DECISIONS.md` for "the rest." That's honest but
   weaker than it needs to be — these three decisions genuinely
   happened; they predate the database, not reality. The same pattern
   already used for TASK-002 (fast-forwarding its Architecture/Red Team
   stages into `task_status_history` with a disclosing note, because
   those stages were real work completed before the database existed)
   applies here: record them via `opsdb.py decision-record`, with a
   note or field making clear they were entered retroactively from
   `DECISIONS.md`, not invented. The Decisions screen then genuinely
   reflects the real decision history, not a partial one with an
   apology attached. DEC-004 is already a native database row
   (`decisions.id = 2`) — nothing to backfill there.
2. **QA must specifically verify the Agent Detail evaluation-history
   query doesn't attribute a review to the wrong agent** — confirm
   `review_results.reviewed_by_agent` (the reviewer) is never confused
   with the task's `current_owner` or any other agent whose work was
   under review. A mislabeled review is worse than an empty section.
3. **Meetings screen ships even though `meetings` has zero rows** —
   confirmed as correct, not something to defer or skip. Verify in QA
   that the empty state reads as "no meetings yet," not as a broken
   page.

## Alignment check
Confirmed against `DATA_MODEL.md`: no schema change, no new table, no
`opsdb.py` write-path usage anywhere in this milestone's code. No
objection.

## Verdict

**PASS, conditional on item 1 (backfill, not footnote) and items 2–3
being explicitly covered in QA.** Development may proceed.
