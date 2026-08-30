# Red Team Review — Phase 2, Milestone 2B5 Architecture

Reviewing `ops/reviews/cto-milestone2b5-architecture.md` before Development.
Live-verified against `ops/db/operations.sqlite3`, `ops/db/schema.sql`,
`ops/control-center/server.py`, `ops/control-center/generate_pipeline.py`,
`ops/db/report.py`, `ops/AGENT_STATUS.md`, `ops/PROJECT.md`,
`ops/ROADMAP.md`, `ops/DATA_MODEL.md`. Verification queries and greps run
directly, not taken on the doc's word.

## Decision 1 — Two pages, not one
No objection. `review_results`+`qa_results` (per-task, multi-row,
constantly-accumulating work-history) and `deployments`/gap-list
(per-event, rare, structurally different question — "is this shippable")
are genuinely different concerns with different update cadence. Grouping
Code Review + Security + QA together on one `reviews.html` is defensible:
they share the same shape (task-scoped pass/fail history, same schema
family, same reader question — "did review/QA reject this work, and
why") and splitting them further would fragment one coherent story
across two pages for no real gain. Not overengineered, not
under-split.

## Decision 2 — No pagination, grouped by task
95 rows today confirmed live (`review_results`=39, `qa_results`=56).
"No pagination yet" is reasonable at this volume — no objection to the
top-line decision.

**However, the doc's own worst-case example understates the real
worst case.** The doc cites "12 QA rows for TASK-006" as its
illustration of why grouping matters. Live query shows TASK-006 does
have 12 QA rows — but TASK-007 has 16 QA rows + 5 review rows = **21
rows in one task-group**, the actual current maximum, not 12:

```
review+qa combined per task_id (top 3): task 7 = 21, task 6 = 18, task 10 = 17
```

21 interleaved rows under one header is not "broken," but it is real
enough that Development/QA should verify rendering against the actual
worst case (TASK-007), not the doc's smaller illustrative example, and
should add a cheap per-group affordance — e.g. a native `<details>`
"show all N" collapse once a group exceeds ~10 rows — so one actively-
developed task's history doesn't visually dominate the page as more
rows accumulate. This is not full pagination infrastructure; it's a
few lines, consistent with the doc's own "small, additive" standard
elsewhere. Non-blocking, but should be included in the file-by-file
change list before Development starts, not treated as a later
follow-up.

## Decision 3 — Release-readiness gap list

**Numbers verified accurate.** Of 11 `DONE` tasks, exactly 1 (TASK-001)
has a `deployments` row; the other 10 do not. No `READY_TO_RELEASE` or
`DEPLOYED` tasks exist today. The proposed
`release_readiness_gap()` logic (`tasks.status IN
('READY_TO_RELEASE','DEPLOYED','DONE')` AND no matching
`deployments.task_id`) is correct against the real schema — a plain
NOT EXISTS join on a real FK, same category of computation as
`company_health()`. No objection to the query itself.

**Blocking: the doc's framing of this gap as "a real, pre-existing gap
in this project's own process discipline around the `deployments`
table" is not supported by this project's own documented process, and
risks presenting a false narrative to the Founder.**

- `ops/AGENT_STATUS.md`'s actual "Release checklist — before any task
  moves to `DONE`" (the one enforceable gate this project has for
  reaching DONE) requires only running `report.py` and `report.py
  --check` before `task-status --to DONE`. It says nothing about the
  `deployments` table being a required step.
- `ops/PROJECT.md` and `ops/ROADMAP.md` both frame "production
  deployment" as a rare, Founder-gated, explicitly-authorized,
  irreversible event ("Production deployment stays gated behind
  explicit Founder approval — this is never automated"), not something
  every completed task is expected to produce a row for.
- The one `deployments` row that exists (TASK-001) is itself labeled,
  in its own `release_notes`, "Fake pause/resume toggle - Phase 1
  pipeline validation only" — i.e. a validation exercise, not a real
  production release.
- The 10 "gap" tasks are internal Control Center development
  milestones (Overview generator, Pipeline/Agents/Decisions/Meetings
  screens, Founder Inbox, Ask-Agent, concurrent runtime, Executive
  Meetings, a rename, Founder auth) — this project's own tooling,
  continuously deployed by virtue of being run from the working tree.
  There is no evidence a discrete "production deployment" event was
  ever expected for any of them, and the `tasks.deployment_result`
  column is empty for all 10, not populated-with-an-explanation —
  consistent with "not applicable," not "skipped."

Presenting "10 of 11 DONE tasks lack a deployment record" as an
actionable process gap, when this project's own actual DONE checklist
never required one, risks the Founder concluding there is a real
discipline problem where there may not be one. This is exactly the
kind of "hidden cost from an unsupported assumption" this review is
meant to catch. **Required before implementation:** either (a) confirm
with the Founder/CTO explicitly whether every `DONE` task genuinely was
supposed to get a `deployments` row (and if so, this finding is
correct and should say so with that evidence cited, not inferred), or
(b) — the more likely correct fix — soften `releases.html`'s and
`generate_releases.py`'s language to present the list as a neutral data
observation ("N of M DONE tasks have no `deployments` row — this may
reflect internal/tooling work with no discrete production release
step, not necessarily a process gap") rather than asserting a
pre-existing discipline failure. The underlying computed list itself
is fine to ship — an honest, real query — the copy/interpretation
around it is what needs to change.

## Decision 4 — Anchor-id addition to `generate_pipeline.py`
Verified low-risk. Grepped the file for any existing `id=` attribute on
its cards — there are none; `id="task-{id}"` is a genuinely new
addition, not a collision with anything already there. Also confirmed
a task can only be in exactly one of (stage column / Needs Attention /
Backlog) at a time (mutually exclusive on `status`), so no duplicate id
risk across the three render paths on one page. Touching an
already-shipped generator for this milestone is in-scope and
correctly disclosed rather than hidden as "free." No objection, but
Development should keep the diff to literally the `id=` attribute (no
incidental refactor of `render_stage_column`/`render_needs_attention`
while in the file) so QA's regression check on Pipeline stays cheap and
targeted.

## Decision 5 — Nav ordering (append)
No objection — matches the existing convention and precedent (2A did
the same). Not worth a finding.

## Decision 6 — Zero new auth code
**Verified independently by reading `server.py`'s `do_GET()` in full**,
not taken on the doc's description. Confirmed exact order: fail-closed
credential gate (`_check_credential_gate()`) → `/login` unauthenticated
allowlist check → `self._authenticated_session() is None` redirect →
the per-path `try:` dispatch block. Adding `reviews.html`/`releases.html`
as two more `if path ==` branches inside that same `try:` block, modeled
directly on the existing `/decisions.html` branch, would genuinely
inherit full session gating with zero new authentication code, exactly
as claimed. No objection.

## Decision 7 — `report.py` unchanged
Verified the doc's characterization of `report.py`'s existing "QA
failures (unresolved)" section against the real code: latest
`qa_results` row per task, filtered to `result='fail' AND
t.status != 'DONE'`. Accurate.

The "additive, not duplicative" framing is defensible in principle —
different question, different audience — but given all 12 tasks in
this database are currently either `DONE` or `BACKLOG`, `report.py`'s
section will show "none open" while `reviews.html` will simultaneously
show real historical `fail` rows (task 6 alone has 12 QA rows, several
presumably fails, now resolved and DONE). That is not a bug and not
duplicative data, but it is a real opportunity for the Founder to read
the two screens as contradicting each other at a glance ("report says
no QA problems, Control Center shows a wall of red FAIL pills").
**Non-blocking but should be addressed in implementation:** `reviews.html`
should carry a short, explicit label distinguishing "full historical
record, including resolved failures on now-DONE tasks" from
`CURRENT_STATUS.md`'s "unresolved right now" scope, so the two are
legible as complementary rather than conflicting on first read.

## Overengineering / simpler-alternative / hidden-cost check
- No new dependency, no new library, no schema change — confirmed
  against `ops/db/schema.sql` and the file-by-file change list. Not
  overengineered.
- `release_readiness_gap()` living in `derived_state.py` rather than
  hand-coded in `generate_releases.py` is the right call for the same
  reason `STAGE_MAP`/`company_health()` do — real, disclosed, not
  premature abstraction (the doc explicitly does not build the
  speculative `report.py` consumer it mentions).
- No beginner mistakes found in the technical design. The one real
  issue in this review is a framing/interpretation problem (Decision
  3), not a technical one.

## Verdict

**PASS, conditional on:**
1. **Blocking** — Decision 3's gap-list framing must be corrected
   before Development ships copy: either produce Founder/CTO
   confirmation that every `DONE` task was actually expected to carry
   a `deployments` row, or (more likely correct) soften
   `releases.html`'s language to present the 10-task gap as a neutral
   data observation, not an assertion of "a real, pre-existing gap in
   this project's own process discipline" — that specific claim is not
   supported by `AGENT_STATUS.md`'s actual DONE checklist or by
   `PROJECT.md`'s framing of production deployment as a rare,
   Founder-gated event.
2. Verify rendering against the real worst-case task-group (TASK-007,
   21 combined review+QA rows, not the doc's cited 12), and add a
   lightweight per-group `<details>`-style collapse past ~10 rows —
   small enough to fold into this milestone, not deferred as "later
   pagination."
3. Add explicit on-page labeling on `reviews.html` distinguishing its
   full-history scope from `CURRENT_STATUS.md`'s unresolved-only scope,
   so a Founder reading both doesn't perceive them as contradicting
   each other.

All other elements — the two-page split, no-pagination-yet at 95 rows,
the anchor-id addition to `generate_pipeline.py`, nav-append ordering,
and the zero-new-auth-code claim — are verified sound and require no
change.
