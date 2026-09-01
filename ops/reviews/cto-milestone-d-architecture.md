# CTO — Milestone D Architecture: Project / Phase Progress (TASK-022)

Date: 2026-09-01
Author: CTO
Directive: DEC-009 (`ops/DECISIONS.md`), `ops/ROADMAP.md`'s "Founder UI
Completeness" section — Founder-approved four-milestone plan, Milestone D,
the fourth and **final** milestone. Milestones A (TASK-019), B (TASK-020),
C (TASK-021) are all DONE. Completing this milestone makes the
Founder-facing UI **100% feature-complete** per DEC-009's own definition
(A+B+C+D). Scope discipline: **architecture only.** Nothing here is
implemented. Read-only Founder-facing page, zero Founder-facing write UI,
zero change to the Founder session/CSRF gate. Does not touch TASK-017,
`risks.id=3`, DEC-010's sequencing decision, or any Phase 3 automation
scope — those are read here (as live data a computed function can query),
never modified.

All facts below were re-derived directly against the live database
(`python3 ops/db/opsdb.py query "..."`) and `ops/ROADMAP.md`/`ops/DECISIONS.md`
while writing this document, not assumed by analogy — this project's own
established discipline (Milestones A/B/C), applied again here.

---

## Part 0 — What carries over unchanged from Milestones A/B/C

- **Precedent for a top-level, read-only list page**: `generate_decisions.py`
  (`/decisions.html`), `generate_risks.py` (`/risks.html`) —
  `build_html(token=None)` self-connecting via `dbutil.connect(mode=ro)`,
  rendered through `layout.page()`, one new `NAV_LINKS` entry. `/progress.html`
  (Part 4) follows this exactly.
- **Precedent for a single shared computed function backing a page**:
  `derived_state.task_progress_row()` (A), `company_cost_digest()` (B),
  `risk_register_rows()` (C). This milestone adds `phase_progress_rows()`
  and `founder_readiness_summary()` to the same file (Part 3).
- **Precedent for honest, disclosed gaps instead of invented data**: no
  fabricated percentage, ever — the single hardest constraint on this
  milestone specifically, restated by the Founder across every round of
  this plan.
- **Precedent for a small, additive reference table, CLI-written only**:
  `risks`, `automation_state`, `reviewer_invocations` — a new
  `CREATE TABLE IF NOT EXISTS` block in `schema.sql`, no migration
  machinery needed (unlike Milestone B's `agent_runs.cost_usd`, which
  added a column to an *existing* table and therefore needed the
  additive-column-migration path — a brand-new table needs none of that).
- **Precedent for reusing an existing computed function rather than
  building a parallel one**: the "in-flight work" section of this
  milestone's page (Part 4.3) reuses `derived_state.active_tasks_digest()`
  (Milestone A's own base query) unchanged — not reinvented.

---

## Part 1 — Finding: Project Progress and Phase Progress are the same concept here, today

Confirmed directly against the live database, not assumed:

```
$ opsdb.py query "SELECT * FROM projects"
id | name                       | description | status | created_at
1  | AI-Pipeline Ops Bootstrap  | ...          | active | 2026-08-28...

$ opsdb.py query "SELECT COUNT(*) FROM tasks WHERE project_id IS NOT NULL"
4
```

Exactly one `projects` row has ever existed, and only 4 of 22 tasks were
ever linked to it (the earliest, TASK-001/002-era tasks) — every task
since has `project_id = NULL`. There is no second project, no
multi-project selector anywhere in the product, and no evidence this
codebase is heading toward one. Building a distinct "Project Progress"
concept (a second table, a second page, a project-picker) alongside
"Phase Progress" would be machinery for a multi-project future this
codebase shows zero present evidence of needing — exactly the kind of
premature generality this project's own architecture discipline has
consistently rejected (Milestone C's real-time `risk_history` deferral,
Milestone A's "no `task_gates` table" finding, Phase 3A's "no second
process" decision).

**Decision: one page, one table, called "Project / Phase Progress" in
the Founder-facing header (matching DEC-009's own literal phrase) but
backed by a single `phases` table (Part 2).** If a second real project
ever exists, `phases` gains an optional `project_id` column at that
time — not designed for speculatively now. This is stated as an explicit
non-goal, not an oversight.

---

## Part 2 — Schema: the `phases` table

```sql
-- Milestone D (TASK-022): phase/milestone state as real, queryable rows —
-- not parsed from ROADMAP.md's prose, not a hardcoded Python literal.
-- Written ONLY through opsdb.py's phase-add / phase-set-status commands
-- (Part 5) -- no HTTP write route, no Founder-facing write UI, matching
-- how risks/decisions/automation_state are written today.
CREATE TABLE IF NOT EXISTS phases (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  name                 TEXT NOT NULL UNIQUE,       -- 'Phase 0' .. 'Phase 3A',
                                                    -- 'Founder UI Completeness',
                                                    -- 'Milestone A' .. 'Milestone D',
                                                    -- 'Phase 4 (proposed)'
  parent_phase_id      INTEGER REFERENCES phases(id),  -- NULL for the 5 top-level
                                                        -- rows (Phase 0/1/2/3/4);
                                                        -- Phase 3A and "Founder UI
                                                        -- Completeness" point at
                                                        -- Phase 3; Milestones A-D
                                                        -- point at "Founder UI
                                                        -- Completeness"
  status               TEXT NOT NULL DEFAULT 'not_started'
                       CHECK (status IN ('not_started','in_progress','complete','paused')),
  sort_order           INTEGER NOT NULL,           -- explicit display order —
                                                    -- independent of id/insertion
                                                    -- order, since backfill and
                                                    -- future inserts won't match
  opened_decision_id   INTEGER REFERENCES decisions(id),  -- the DEC-00x that
                                                           -- approved/started it;
                                                           -- NULL, never guessed,
                                                           -- if no single decision
                                                           -- row cleanly covers it
  closed_decision_id   INTEGER REFERENCES decisions(id),  -- the DEC-00x that
                                                           -- marked it complete or
                                                           -- paused, if any
  task_id              INTEGER REFERENCES tasks(id),      -- ONLY when this phase
                                                           -- row is genuinely 1:1
                                                           -- with one task
                                                           -- (Milestones A-D, Phase
                                                           -- 3A); NULL for
                                                           -- multi-task phases
                                                           -- (0/1/2/3) — never
                                                           -- forced
  milestones_total     INTEGER,                     -- NULL if not honestly
                                                      -- countable — see Part 3
  milestones_complete  INTEGER,
  note                 TEXT,                        -- short, factual, structured
                                                      -- status note — NOT a copy
                                                      -- of ROADMAP.md's narrative
                                                      -- prose (Part 6)
  updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_phases_parent ON phases(parent_phase_id);
```

Why this shape, concretely:

- `status` uses the Founder's own four-value vocabulary verbatim
  (`not_started`/`in_progress`/`complete`/`paused`) — the v2 audit
  document's original three-value sketch (`not_started`/`in_progress`/
  `complete`) is widened by exactly one value to represent Phase 3's real
  current sub-state (TASK-017 paused mid-Development per DEC-008, resumed
  per DEC-010) without collapsing "paused" into "in_progress," which
  would misrepresent a Founder-directed pause as ordinary progress.
- `parent_phase_id` (self-referencing FK) is the smallest mechanism that
  nests Milestones A-D under the "Founder UI Completeness" sub-plan and
  nests that sub-plan and Phase 3A under Phase 3 — a plain adjacency
  list, one level of real nesting needed today (Phase → sub-plan/slice →
  milestone), not a generalized arbitrary-depth tree library.
- `opened_decision_id`/`closed_decision_id` are **nullable and never
  guessed** — Part 3.2 gives a concrete example (Phase 2) where the
  honest answer is `NULL` because no single `decisions` row cleanly
  marks that phase's start.
- `task_id` is nullable and deliberately **not** used for Phase 0-3
  (multi-task phases) — forcing a single task reference onto a phase
  built from 8+ real tasks (Phase 2) would either pick one arbitrarily or
  require a second junction table this scope doesn't need. It's used
  only where the mapping is genuinely 1:1 (Phase 3A → TASK-015,
  Milestone A → TASK-019, B → TASK-020, C → TASK-021, D → TASK-022).
- `milestones_total`/`milestones_complete` stay nullable — Part 3 decides,
  phase by phase, whether they're honestly populated or left `NULL`.

**Migration**: a plain new `CREATE TABLE IF NOT EXISTS` block, same as
`risks`/`automation_state`/`reviewer_invocations` — no additive-column
migration needed (that mechanism is only for adding a column to an
*existing* table, per the `agent_runs.cost_usd`/`handoffs` precedent).
**Explicit implementation checklist item, learned from a real prior gap**
(Milestone B's v2 audit found `reviewer_invocations`/`hook_denials`
specified in `schema.sql` but absent from the live `operations.sqlite3`
because `opsdb.py init` was never rerun after the edit): Development
**must** run `opsdb.py init` against the live database as part of this
milestone and CTO conformance **must** re-confirm the table exists live
(`sqlite_master` query) before marking this milestone DONE — not assumed
from the schema file alone.

---

## Part 3 — Classification: fraction vs. status, phase by phase

This is the load-bearing part of the design. Per row: what's genuinely
derivable as a fraction, and what must render as a status-only value.

### 3.1 Top-level phases

| Phase | Status | Fraction? | Reasoning |
|---|---|---|---|
| **Phase 0** — Design & Architecture Proposal | `complete` | **No — status only.** | Phase 0's scope (agent model, workflow, mockups) was never decomposed into a fixed, equal-weight, individually-tracked milestone count anywhere in the record. Inventing a count now (e.g. "3 mockups reviewed") would be exactly the fabricated-progress pattern the Founder has repeatedly forbidden. |
| **Phase 1** — Foundation | `complete` | **No — status only.** | ROADMAP.md lists 6 prose bullets (data model, DB instantiation, agent wiring, TASK-001 walkthrough, status reporting, durable-docs finalization) — real work, but never tracked as discrete, individually-completable milestone rows anywhere in the database. Counting the bullets retroactively would be a number invented for this document, not sourced from structured data that existed at the time. Status only. |
| **Phase 2** — Control Center | `complete` | **Yes — a real, disclosed bonus fact, not the primary status.** | Phase 2 *was* explicitly built as a named sequence of milestones (1, 2A, 2B1, 2B2, 2B3A, 2B3B, 2B3B-round-2, 2B4, 2B5 — 9 named slices, each with a real completed task row, confirmed: TASK-004/005/006/007/009/010/011/013/014 all `status='DONE'`). This is genuinely, honestly derivable — 9 of 9 named Phase 2 milestones DONE. Shown as a secondary line under the primary `complete` status pill, not the headline. |
| **Phase 3** — Automated Orchestration | `in_progress` | **No — status only, explicitly "scope not finalized."** | ROADMAP.md's own words: "the remainder of Phase 3 ... remains explicitly unauthorized." There is no fixed, Founder-approved total handoff count for Phase 3 as a whole (only individual pieces — Phase 3A, the UI-completeness sub-plan, TASK-017 — are separately scoped). Rendered as: **"Phase 3 — In Progress (scope not finalized)."** `note`: "Full automation (Code Review PASS→QA, QA→Security, Security→Release, deployment) unauthorized. TASK-017 security hardening resumed as a prerequisite before further automation — see DEC-010." (`decisions.id=13`, real, queried.) |
| **Phase 4 (proposed)** | `not_started` | **No — status only, and explicitly distinguished from a deprioritized in-progress phase.** | ROADMAP.md: "NOT STARTED, NOT APPROVED." `note`: "Proposed only (Founder directive 2026-08-31, Part 7) — not approved, not scoped in detail. Not the same as a paused phase; no Founder go-ahead has ever been given to start it." |

### 3.2 Phase 3's real sub-items (`parent_phase_id` = Phase 3's id)

| Row | Status | Fraction? | Reasoning |
|---|---|---|---|
| **Phase 3A** | `complete` | **Yes.** | ROADMAP.md itself names exactly two parts ("Two closely related capabilities shipped": the Chief of Staff conversational interface, and the one automated Developer→Code Review handoff) — both real, both shipped, both traceable to TASK-015 (`status='DONE'`). Rendered: "Phase 3A — Complete (2 of 2 parts shipped)." `opened_decision_id = closed_decision_id = 10` (DEC-007, confirmed live: `id=10, title='Phase 3A: automated Code Review invoked zero-tool...', date=2026-08-31`). `task_id = 15`. |
| **Founder UI Completeness (sub-plan)** | `in_progress` | **Yes — the flagship honest fraction in this whole design.** | DEC-009 itself defines exactly four named milestones (A/B/C/D). Three are DONE (TASK-019, 020, 021, all confirmed `status='DONE'` live), the fourth (TASK-022, this milestone) is `ARCHITECTURE` (confirmed live, this very session). **"3 of 4 milestones complete"** is real, current, and happening in this exact session — not hypothetical. `opened_decision_id = 12` (DEC-009, confirmed live). `milestones_total=4`, `milestones_complete=3` at backfill time (Part 5 shows exactly how this number advances). |

### 3.3 The four milestones themselves (`parent_phase_id` = "Founder UI Completeness"'s id)

| Row | Status | Fraction? |
|---|---|---|
| Milestone A | `complete` | No sub-fraction — a milestone is the atomic unit here, not further decomposed. `task_id=19`. |
| Milestone B | `complete` | Same. `task_id=20`. |
| Milestone C | `complete` | Same. `task_id=21`. |
| Milestone D | `in_progress` | Same. `task_id=22`. Set to `complete` at the very end of this milestone's own CTO final-conformance step (Part 7) — the last write this milestone's own lifecycle makes to its own row, a deliberately self-referential but entirely real update (the same way TASK-021's own row in `tasks` was itself marked DONE by the process it describes). |

### 3.4 Two distinct readiness booleans — computed, not narrated (DEC-009's own requirement)

DEC-009 requires two separately-tracked readiness states, kept visible
everywhere this project reports status. Today those exist only as a
sentence in `ROADMAP.md`/`DECISIONS.md`. This milestone makes them real,
computed values for the first time:

```python
# derived_state.py — additive
def founder_readiness_summary(conn) -> dict:
    """Reads the four Milestone A-D `phases` rows by name (not the
    'Founder UI Completeness' parent row's own status, which could in
    principle be set inconsistently with its children — this function
    is the ground truth, derived from the children directly, exactly
    the discipline task_progress_fraction() already applies to gates).
    Returns:
    {"exploratory_testing_ready": bool,   # A+B+C all status='complete'
     "ui_100pct_complete": bool,          # above AND D status='complete'
     "milestones_done": int, "milestones_total": 4}
    Never a percentage — two real booleans plus a real integer fraction,
    per DEC-009's own explicit requirement that these two states stay
    separate everywhere this project reports status."""
```

This is not scope creep beyond "a page" — it is DEC-009's own two-state
requirement, made real for the first time instead of living only as
prose repeated by hand in `ROADMAP.md` and `DECISIONS.md` each time a
milestone ships.

### 3.5 What is explicitly *not* given a `phases` row

TASK-016, TASK-017, TASK-018 (the risk-3 investigation, the risk-3
hardening milestone, and the product-architecture-completion review) are
**not** given their own `phases` rows. Reasoning: they are individual
tasks with their own real `tasks.status`, not named, Founder-approved
phase/milestone concepts the way Phase 0-4 and Milestones A-D are (no
`ROADMAP.md` `##`/named-milestone heading exists for any of them
individually — they're described in running prose within the Phase 3
section). Creating a `phases` row per arbitrary task would blur the
distinction this table exists to make (a *phase*, not *every task*) and
would need constant upkeep with no real payoff — `Active Work`
(Milestone A) already shows every non-DONE task, including these three,
with zero new data needed. Part 4.3 shows exactly how the page surfaces
them without a `phases` row.

---

## Part 4 — The page: `/progress.html`

### 4.1 Route and file

`GET /progress.html` — top-level, same shape as `/decisions.html`,
`/risks.html`. New file `ops/control-center/generate_progress.py`,
`build_html(token=None)`. New `server.py` GET route, same dispatch
pattern as every other top-level page.

**Naming**: `/progress.html`, not `/phases.html` or `/project-progress.html`.
Reasoning: DEC-009's own governing sentence is "Founder Work Progress" /
"Project/Phase Progress" — "Progress" is the noun the Founder has used
consistently across every round of this plan, and reads correctly for
what the page actually answers ("how far along is the company"), while
"Phases" alone would undersell that the page also answers the readiness
question (Part 3.4), not just phase status. Nav label: "Progress."

### 4.2 Header — the one place a real fraction and two real booleans appear together

```
PROJECT / PHASE PROGRESS

Founder UI 100% feature-complete:  NOT YET (3 of 4 UI Completeness milestones done)
Exploratory Founder Testing ready:  YES (Milestones A + B + C complete)
```

Both lines are `founder_readiness_summary()` output, rendered plainly —
no other number appears above the fold. This directly answers the
Founder's own repeatedly-stated bar without requiring a click into the
phase tree below.

### 4.3 Phase tree

`phase_progress_rows(conn) -> list[dict]` (additive, `derived_state.py`,
same discipline as `risk_register_rows()`): one query, `LEFT JOIN`s to
`decisions` (twice, aliased, for opened/closed) and `tasks` (for
`task_id`), ordered by `sort_order`. The page renders it as an indented
tree (one level of indentation per `parent_phase_id` hop — at most two
levels deep given Part 2's design, no recursive CTE needed):

```
Phase 0 — Complete                              (DEC-003, 2026-08-29)
Phase 1 — Complete                              (DEC-003 → DEC-004)
Phase 2 — Complete   (9 of 9 named milestones)
Phase 3 — In Progress (scope not finalized)
    Phase 3A — Complete (2 of 2 parts shipped)   (DEC-007)          → TASK-015
    Founder UI Completeness — In Progress (3 of 4 milestones)       (DEC-009)
        Milestone A — Complete                                     → TASK-019
        Milestone B — Complete                                     → TASK-020
        Milestone C — Complete                                     → TASK-021
        Milestone D — In Progress                                  → TASK-022
Phase 4 (proposed) — Not Started  (not approved)
```

Status pills reuse `_STATUS_COLOR`-style mapping already established by
`generate_risks.py` (green=complete, accent=in_progress, red/amber=paused,
text3/gray=not_started — one new value, `paused`, added to the existing
convention, not a new visual system). Each row with a real
`opened_decision_id`/`closed_decision_id` links to
`decisions.html#decision-{id}` (the anchor Milestone C already added to
every decision card — reused, not duplicated). Each row with a real
`task_id` links to `tasks/{id}.html` (Milestone A's real Task Detail
page — reused, not duplicated). `note` renders as a small line under the
status pill, exactly the "structured, factual, short" text specified in
Part 2 — never the full `ROADMAP.md` paragraph copied in.

### 4.4 "Currently in-flight work" section — reused, not reinvented

Below the phase tree, a small section listing every task from
`derived_state.active_tasks_digest()` (Milestone A's existing base query,
`status != 'DONE'`) that is **not** already reachable via a `task_id` on
a `phases` row above — i.e. TASK-016, TASK-017, TASK-018 today, whatever
the real set is at render time. Each row: task id/title, real live
`tasks.status`, link to `/tasks/<id>.html`. This is exactly how "TASK-017
— awaiting Founder decision" (the sketch from
`cto-product-architecture-completion-v2.md` Part 4.3) actually renders —
**not** a hardcoded phases row, but a live read of `tasks.status` through
Milestone A's own machinery, so it is never stale relative to the real
pipeline: whatever TASK-017's actual live status is right now (it has
changed at least twice already this project — `BLOCKED` per DEC-008,
`CODE_REVIEW`-directed per DEC-010, `FOUNDER_APPROVAL` as of this
session's live query) is exactly what renders, with zero additional
code and zero risk of this page drifting from the pipeline's own truth.

### 4.5 What this page explicitly does not add

No project column on Pipeline/Active Work (Part 1's finding — one
implicit project, not worth a UI concept). No phases row per individual
task (Part 3.5). No client-side JS — same anchor-based, no-filter,
single-page rendering model as `/risks.html`/`/decisions.html`. No new
write route.

---

## Part 5 — Backfill: real historical data, written once, via the same CLI this milestone ships

**Decision: yes, backfilled as part of this milestone, not deferred.**
A `phases` table with zero historical rows would answer "how far along
is the company" with nothing above Milestone D itself — useless for the
actual question DEC-009 exists to answer. This is not the same as
"hardcoding a Python literal that could drift": each backfilled value is
sourced from an already-real, already-approved row in `decisions` or
`tasks` — re-expressing existing structured facts in a new structured
table, not inventing new ones. Concretely, here is the exact backfill
sequence Development runs once, values sourced from the live queries
in this document's own preamble:

```
opsdb.py phase-add --name "Phase 0" --status complete --sort-order 10 \
  --closed-decision-id 5 --note "Design & Architecture Proposal"

opsdb.py phase-add --name "Phase 1" --status complete --sort-order 20 \
  --opened-decision-id 5 --closed-decision-id 2 --note "Foundation"

opsdb.py phase-add --name "Phase 2" --status complete --sort-order 30 \
  --milestones-total 9 --milestones-complete 9 \
  --note "Control Center — 9 of 9 named milestones (1, 2A, 2B1, 2B2, 2B3A, 2B3B, 2B3B-r2, 2B4, 2B5) DONE"
  # opened_decision_id intentionally omitted (left NULL): no single
  # `decisions` row cleanly records "Phase 2 begins" — confirmed by
  # direct query against the live `decisions` table while writing this
  # document; not guessed.

opsdb.py phase-add --name "Phase 3" --status in_progress --sort-order 40 \
  --note "Automated Orchestration — scope not finalized; full automation unauthorized. TASK-017 hardening resumed as prerequisite, see DEC-010 (decisions.id=13)."

opsdb.py phase-add --name "Phase 3A" --status complete --sort-order 41 \
  --parent-id <Phase 3's id> --opened-decision-id 10 --closed-decision-id 10 \
  --task-id 15 --milestones-total 2 --milestones-complete 2 \
  --note "Chief of Staff interface + one automated handoff, both shipped"

opsdb.py phase-add --name "Founder UI Completeness" --status in_progress --sort-order 42 \
  --parent-id <Phase 3's id> --opened-decision-id 12 \
  --milestones-total 4 --milestones-complete 3 \
  --note "Milestones A-D per DEC-009"

opsdb.py phase-add --name "Milestone A" --status complete --sort-order 421 \
  --parent-id <Founder UI Completeness's id> --task-id 19

opsdb.py phase-add --name "Milestone B" --status complete --sort-order 422 \
  --parent-id <Founder UI Completeness's id> --task-id 20

opsdb.py phase-add --name "Milestone C" --status complete --sort-order 423 \
  --parent-id <Founder UI Completeness's id> --task-id 21

opsdb.py phase-add --name "Milestone D" --status in_progress --sort-order 424 \
  --parent-id <Founder UI Completeness's id> --task-id 22

opsdb.py phase-add --name "Phase 4 (proposed)" --status not_started --sort-order 50 \
  --note "Proposed only (Founder directive 2026-08-31, Part 7) — not approved, not scoped"
```

Every `--opened-decision-id`/`--closed-decision-id`/`--task-id` above is
a real id, verified against the live database while writing this
document (shown in this document's preamble queries) — none invented.
Where no clean 1:1 decision exists (Phase 2's start), the field is
**omitted**, not filled with a plausible-looking guess — the concrete
demonstration of the anti-fabrication rule applied to this table's own
foreign keys, not just its status/percentage fields.

The final step of this milestone's own implementation — after
Development, Code Review, QA, Security, and CTO conformance all pass —
is `opsdb.py phase-set-status --name "Milestone D" --status complete
--closed-decision-id <this milestone's approval>`, which also updates
the parent row: `opsdb.py phase-set-status --name "Founder UI Completeness"
--status complete --milestones-complete 4 --closed-decision-id <same>`.
At that moment, and only at that moment, `founder_readiness_summary()`'s
`ui_100pct_complete` becomes `true` for the first time — a real,
traceable, non-fabricated transition, not a sentence someone remembers
to write.

---

## Part 6 — CLI: `opsdb.py phase-add` / `phase-set-status`

Same pattern as `risk-add`/`risk-resolve`, `decision-record` — the
*only* writers of this table, no HTTP write route, no Founder-facing
write UI (per this milestone's own stated constraint).

```python
pa = sub.add_parser("phase-add", help="record a phase/milestone row")
pa.add_argument("--name", required=True)
pa.add_argument("--status", required=True,
                choices=["not_started", "in_progress", "complete", "paused"])
pa.add_argument("--sort-order", type=int, required=True, dest="sort_order")
pa.add_argument("--parent-id", type=int, dest="parent_phase_id")
pa.add_argument("--opened-decision-id", type=int, dest="opened_decision_id")
pa.add_argument("--closed-decision-id", type=int, dest="closed_decision_id")
pa.add_argument("--task-id", type=int, dest="task_id")
pa.add_argument("--milestones-total", type=int, dest="milestones_total")
pa.add_argument("--milestones-complete", type=int, dest="milestones_complete")
pa.add_argument("--note")
pa.set_defaults(func=cmd_phase_add)

ps = sub.add_parser("phase-set-status", help="update a phase's status (the *only* writer of phases.status after creation)")
group = ps.add_mutually_exclusive_group(required=True)
group.add_argument("--id", type=int, dest="phase_id")
group.add_argument("--name", dest="phase_name")   # convenience lookup, resolved to id before UPDATE
ps.add_argument("--status", required=True,
                 choices=["not_started", "in_progress", "complete", "paused"])
ps.add_argument("--closed-decision-id", type=int, dest="closed_decision_id")
ps.add_argument("--milestones-complete", type=int, dest="milestones_complete")
ps.add_argument("--note")
ps.set_defaults(func=cmd_phase_set_status)
```

`cmd_phase_add()` validates `parent_phase_id` (if given) references an
existing row (mirrors `risk-add`'s own scope-validation discipline) and
inserts. `cmd_phase_set_status()` does a single `UPDATE ... SET status =
?, updated_at = strftime(...), closed_decision_id = COALESCE(?,
closed_decision_id), milestones_complete = COALESCE(?,
milestones_complete), note = COALESCE(?, note) WHERE id = ?` — same
`COALESCE`-preserves-unless-supplied shape `risk-resolve` already uses.
`milestones_total` is deliberately **not** settable via
`phase-set-status` (only at `phase-add` time) — changing what "total"
even means for an already-in-progress phase after the fact is exactly
the kind of retroactive scope redefinition DEC-009 itself forbade
("the Founder was explicit that this definition is not to be narrowed
after the fact"); if a phase's total genuinely needs to change, that is
itself a decision-worthy event, not a routine CLI update.

---

## Part 7 — Staleness prevention: the singular update path, and the one honestly-unavoidable duplication

**The mechanism**: `phases` has exactly one write path — `phase-add` at
creation, `phase-set-status` for every status change thereafter. No
other code writes this table (no HTTP route, no automatic derivation
from `tasks.status`, no trigger). This matches every other structured
concept in this system (`risks`, `decisions`, `automation_state`) and
is, on its own, no more or less "singular" than any of them.

**What this does *not* solve, stated plainly rather than papered over**:
`ROADMAP.md`'s own prose phase headings (`## PHASE 3 — Automated
Orchestration ...`) are **not** auto-generated from the `phases` table.
This is a real, disclosed limitation, not a solved problem — unlike
`DECISIONS.md`, which this project already mechanically regenerates from
the `decisions` table (stated explicitly in `DECISIONS.md`'s own header:
"this file is the git-readable mirror of the `decisions` table... SQLite
is the writable source of truth, this file is the durable, diffable
export"), `ROADMAP.md` is not proposed to become a generated mirror by
this milestone. Reasoning: `ROADMAP.md`'s value is its long-form
narrative — what was tried, why, what was rejected, in the Founder's and
each agent's own words — which a generated status table cannot and
should not try to reproduce; converting it into a generated file is a
materially larger, separately-scoped change (a real re-architecture of a
core project document, not "add a page"), explicitly out of this
milestone's DEC-009 boundary.

**The concrete, smallest mitigation adopted for this milestone**: the
same disclosed-procedural-convention pattern this project has already
used for a comparable gap (DEC-004's `approval-decide` flag — a
"deliberate act," not technically enforced authentication). Two things,
both real and checkable, neither requiring new automation:

1. `phase-set-status --help` text and this document both state the
   convention directly: *"Whenever a phase's status genuinely changes,
   update `ops/ROADMAP.md`'s prose heading for that phase in the same
   commit/task that runs this command — the two are companion edits, not
   independent ones."* This is the same discipline already implicitly
   required (and, per this project's own history, occasionally missed —
   see `risks.id=4`, the specified-but-never-created table, and
   Milestone B's "four vs. five paths" copy bug) — naming it explicitly
   here is the concrete improvement, not a claim that it becomes
   impossible to forget.
2. **`/progress.html` itself becomes the load-bearing check going
   forward, not `ROADMAP.md`.** Per DEC-009's own instruction and the
   Founder's original motivating complaint for this whole plan, the
   `phases` table (queried live, via `/progress.html`) is the
   authoritative, Founder-facing answer to "how far along is the
   company" from this milestone onward — `ROADMAP.md` remains the
   durable narrative record of *why*, exactly as `DECISIONS.md`'s
   individual entries stay the durable record of *why* even after a
   decision's practical effect (e.g. `risks.id=2` moving to `mitigated`)
   is visible structurally elsewhere. A future drift between the two is
   a real, disclosed possibility (Founder-visible on `/progress.html`
   independent of `ROADMAP.md`'s own text staying current) — not a
   silent one, and not one this milestone claims to have technically
   prevented.

**Named as explicit future work, not built here** (proportionate to this
milestone, following Milestone C's own precedent of naming rather than
building the `risk_history` table): a small, deliberately-run (never
scheduled/automatic — that would be new automation, out of this
milestone's scope) `opsdb.py phase-drift-check` command that greps
`ROADMAP.md` for known phase-name headings and flags (does not auto-fix)
any whose nearby text contains a status word inconsistent with the
`phases` table's own value — a lint, not a sync, and only if this drift
is later observed to actually recur.

---

## Part 8 — Nav placement and cross-links

### 8.1 `layout.py`

```python
NAV_LINKS = [
    ("overview.html", "Overview"),
    ("active-work.html", "Active Work"),
    ("pipeline.html", "Pipeline"),
    ("agents.html", "Agents"),
    ("decisions.html", "Decisions"),
    ("progress.html", "Progress"),   # NEW — Milestone D (TASK-022)
    ("risks.html", "Risks"),
    ("meetings.html", "Meetings"),
    ("inbox.html", "Inbox"),
    ("reviews.html", "Reviews"),
    ("releases.html", "Releases"),
    ("automation.html", "Automation"),
    ("costs.html", "Costs"),
]
```

Placed immediately after "Decisions," before "Risks" — continuing the
governance cluster Milestone C established (Decisions → Risks): a phase
row's `opened_decision_id`/`closed_decision_id` are literally built from
the `decisions` table, the same adjacency reasoning Milestone C used to
place Risks next to Decisions. Not placed next to "Overview"/"Active
Work" — those answer "what's happening right now, per task," while
Progress answers "how far along is the company, at the roadmap level,"
a distinct question the Founder has consistently kept separate across
every round of this plan (DEC-009's own two-readiness-state framing).

### 8.2 Cross-links

- Phase tree rows → `decisions.html#decision-{id}` (Milestone C's
  existing anchor), `tasks/{id}.html` (Milestone A's existing detail
  page) — both reused, zero new anchor mechanism.
- In-flight work rows → `tasks/{id}.html` (Milestone A, unchanged).
- **Not added**: a reverse link from `decisions.html` or `tasks/<id>.html`
  back to `/progress.html`. Considered and rejected as unnecessary
  surface area for this milestone — `/progress.html` is reachable from
  the nav bar on every page already (the same reasoning every prior
  milestone applied: a nav-bar top-level page does not also need
  individual inbound links from every page that happens to share data
  with it).

---

## Part 9 — Gates

Per DEC-009: CTO architecture (this document) → Design review (a real,
if compact, Founder-facing UI surface) → Red Team → Development → Code
Review → QA → a focused Security review scoped to newly introduced risk
only → CTO final conformance.

### 9.1 What the Design review gate should specifically weigh in on

1. The nested phase-tree layout (Part 4.3) vs. a flatter list with
   indentation conveyed only by typography — confirm or override.
2. The two-boolean readiness header (Part 4.2) — wording and prominence,
   matching the "informative, not alarmist" bar already applied to
   Milestone A's staleness badge and Milestone B's cost disclosures.
3. The `paused` status pill's color — a new value in the established
   color convention, needs a real design call, not an assumed reuse of
   an existing color.
4. Nav placement (Part 8.1) — confirm "Progress" belongs next to
   "Decisions," or propose otherwise.

### 9.2 The focused Security review

Same framing as every prior milestone in this plan: read-only page, no
new HTTP write route (`phase-add`/`phase-set-status` are CLI-only,
operator/agent-invoked, exactly like `risk-add`/`decision-record`),
reuses the existing Founder session/CSRF gate unchanged. Concretely,
Security should verify: `dbutil.connect(mode=ro)` used throughout
`generate_progress.py`; no data rendered on `/progress.html` more
sensitive than what `/decisions.html`/`/risks.html`/`/active-work.html`
already show (phase status, decision links, task links — all already
Founder-visible elsewhere); the new CLI commands validate
`parent_phase_id`/`task_id`/`opened_decision_id`/`closed_decision_id`
reference real rows (FK constraints plus explicit existence checks,
matching `risk-add`'s own scope-validation discipline) rather than
accepting an arbitrary integer.

---

## Part 10 — Files this milestone touches (complete list)

**New:**
- `ops/control-center/generate_progress.py` — `/progress.html`.

**Modified:**
- `ops/db/schema.sql` — new `CREATE TABLE IF NOT EXISTS phases (...)`
  block (Part 2), no change to any existing table.
- `ops/db/opsdb.py` — `cmd_phase_add()`, `cmd_phase_set_status()`, two
  new `add_parser()` blocks (Part 6).
- `ops/db/derived_state.py` — `phase_progress_rows()`,
  `founder_readiness_summary()`, both additive (Parts 3.4, 4.3).
- `ops/control-center/layout.py` — one new `NAV_LINKS` entry
  (`progress.html`, after `decisions.html`).
- `ops/control-center/server.py` — one new top-level GET route
  (`/progress.html`), same dispatch pattern as every other top-level page.

**Data (not code) — the backfill sequence, Part 5**: 10 real
`phase-add` invocations plus 2 `phase-set-status` invocations at the end
of this milestone's own lifecycle, run once by Development, values
sourced from the live `decisions`/`tasks` tables as shown in this
document.

**Explicitly not touched:** `ops/ROADMAP.md` (stays hand-authored prose,
Part 7's disclosed limitation, not auto-generated), `ops/DECISIONS.md`
(unaffected — this milestone reads `decisions`, never writes it), any
HTTP write route, any auth mechanism, TASK-017, `risks.id=3`,
DEC-010's sequencing decision, the `projects` table (Part 1 — no schema
change to it), Pipeline/Active Work (no phase column added, Part 4.5).

---

## Part 11 — What this design explicitly does not add

No multi-project machinery (Part 1). No `phases` row per individual task
(Part 3.5 — Active Work already covers every non-DONE task). No
Founder-facing write UI for phase status (CLI-only, Part 6, per this
milestone's own stated constraint). No auto-generation of `ROADMAP.md`
from `phases` (Part 7 — named as future work, not built). No automatic
drift-detection between `ROADMAP.md` and `phases` (Part 7 — same, and
explicitly not "automation" this milestone is authorized to build). No
invented percentage anywhere — every fraction shown (Phase 2's 9/9,
Phase 3A's 2/2, the UI-completeness plan's 3/4) is backed by a real,
named, individually-verified set of milestones with real completed-task
evidence; every phase without such a set (Phase 0, 1, 3, 4) renders
status-only, explicitly, per Part 3's own classification table. No
change to TASK-017, `risks.id=3`, or any Phase 3 automation scope.
