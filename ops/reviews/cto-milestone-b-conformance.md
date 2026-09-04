# CTO — Milestone B Post-Implementation Conformance (TASK-020)

Date: 2026-09-01
Author: CTO
Reviewing: the final, merged state of TASK-020 (Milestone B: company-wide
AI cost visibility) against `ops/reviews/cto-milestone-b-architecture.md`,
after Design review, Red Team, three Development rounds, three Code
Review rounds, QA (including a genuine live end-to-end invocation), and
a focused Security review — all PASSED. This is the final DEC-009 gate:
architectural conformance of what actually got built, not a re-review of
correctness already covered eight times over.

## Verdict: CONFORMS — Milestone B is ready to be marked DONE.

No drift found. What shipped matches the original architecture,
incorporating only the legitimate corrections the gate sequence itself
produced (Design's layout choice, Red Team's fifth-path resolution and
required wording fix, and the three-round copy-defect fix), with no
undisclosed departure and no Milestone C/D scope leakage.

---

## 1. Schema / migration — matches, and is durably documented

`schema.sql`'s `agent_runs` comment block and `opsdb.py`'s
`_apply_additive_column_migrations()` extend the exact same
`PRAGMA table_info()`-guarded, `cmd_init`-only pattern already
established for `handoffs.base_commit_sha`/`head_commit_sha` — no new
migration mechanism, per §1.2 of the architecture doc. Verified directly
against the live `operations.sqlite3`: `cost_usd` is present on
`agent_runs`, and all 13 pre-existing rows are `NULL` (not `0`), exactly
the "additive column, honest historical NULL" shape specified.

Durability of the pattern itself, not just this one application, is now
explicitly documented in two places: Red Team's review named the live,
real precedent for this exact failure mode (`reviewer_invocations`,
`risks.id=4` — specified in `schema.sql` since commit `fdaf253` but never
created live because `init` was never re-run), and Development copied
that warning verbatim into `opsdb.py`'s own docstring for
`_apply_additive_column_migrations()` ("Red Team's Milestone B review...
found a real, live example of exactly this gap left unaddressed... do
not repeat that gap here"). A future contributor reading this function
before adding a sixth additive column will find the risk named in the
code itself, not only in a review document. `risks.id=4` is separately
recorded and has since moved to `resolved` (confirmed live) — unrelated
to, but consistent with, this milestone's own migration having been
verified applied.

## 2. Wiring — every call site matches the architecture doc exactly

Read and cross-checked against the doc's §2.2/§2.4 line-by-line list:
`server.py::_handle_ask()` (3 sites + `result = None` init),
`meeting_orchestrator.py`'s `_gather_position()`,
`gather_requested_position()`, `retry_position()` (6 sites, unchanged
from the original three-function scope), plus the three new
instrumentation brackets (`_select_participants()`, `_synthesize()`,
`gather_followup_reply()`) that Design/Red Team confirmed should ship
rather than fall back to the disclosed partial-total alternative;
`chief_of_staff.py::ask_chief_of_staff()` (3 sites + dual `= None` init +
`_sum_costs()`); `automation.py::_invoke_and_record()` (3
consistency-only sites, same value already flowing to
`end_automation_event()`, no behavior change). `reviewer_sync.py` is
confirmed untouched functionally — its three `end_run()` calls still
withhold `cost_usd` by construction, with the required one-line
disclosure comment present at the call site and mirrored in
`generate_costs.py`'s by-path caption, exactly as Red Team required.
`test_cost_tracking.py` (22/22) and `test_gates_remaining.py` (34/34)
both pass against the current code.

## 3. Cost-tracking model — genuinely one source of truth, not just claimed

Traced concretely, not assumed: `generate_costs.py`'s subtitle,
`_stat_card()`, `render_advisory()`, and `render_by_path()` all read
exclusively from one `digest = ds.company_cost_digest(conn)` call built
at the top of `build_html()`; every dollar figure and every coverage
string on the page — and on `generate_meetings.py`'s Cost panel — passes
through `derived_state.cost_coverage()` / `format_cost_coverage()`, one
shared implementation, not two hand-rolled copies. A live grep of
`ops/control-center/*.py` and `derived_state.py` for the specific defect
pattern (a hardcoded "four" path count) turns up exactly one remaining
hit — a docstring-only comment in `company_cost_digest()`'s own
docstring, never rendered, already identified and dismissed as such in
Code Review round 3's own handoff note.

This is more than a fix — it is now a documented pattern for the future.
`company_cost_digest()`'s docstring, `cost_coverage()`'s docstring, and
`generate_costs.py`'s module docstring each independently state that
every new cost figure must be built through `cost_coverage()`/
`format_cost_coverage()`, never a second hand-typed wording branch. A
sixth invocation path would require: one more `*_ACTIVITY_LIKE` constant
mirrored from `agent_runtime.py` (already the established, documented
convention — see `derived_state.py`'s own comment on why these are
restated as plain literals rather than imported), one more `_path_row()`
call, and no new rendering logic — the copy that broke three times
(subtitle, stat-card zero-state, advisory banner) was broken precisely
*because* those three spots didn't yet route through the shared digest;
they now do, structurally, not by convention alone. This is a reasonable
level of documentation for the next contributor — not bulletproof
against someone hand-typing a new string outside the established
functions, but the pattern is stated in enough places (three separate
docstrings plus the module header) that repeating the saga would require
actively bypassing documented guidance, not merely missing it.

## 4. Test coverage — organized by scenario, not accreted by round

`ops/db/test_cost_tracking.py` reads as six clearly-numbered cases (1:
`end_run()` persistence, 2: the three-way wording branch including Red
Team's required fix, 3: `company_cost_digest()` by-path grouping and the
no-double-count guarantee, 4: `meeting_cost_usd()` scope isolation, 5:
historical-NULL rendering, 6: `chief_of_staff._sum_costs()`), each with a
docstring explaining which review round required it. It does not read as
three stapled-together patches — the module docstring synthesizes all
three review rounds' requirements into one coherent scenario list up
front, and the checks themselves are ordered by subject (schema → wording
→ digest → meeting scoping → historical data → Chief-of-Staff
aggregation), not by when each was added.

## 5. Scope boundary — held end to end

- No new HTTP write route: `/costs.html` is GET-only, dispatched through
  the same `if path == ...` ladder as every other top-level page, same
  session/CSRF gate, `dbutil.connect()`'s read-only (`mode=ro`) discipline
  used throughout `generate_costs.py`. QA independently confirmed `POST
  /costs.html` → 404.
- `risks.id=3`/TASK-017: untouched beyond the one disclosed
  `reviewer_sync.py` comment (verified — no functional change to that
  file's control flow, routing, or write paths).
- Nothing from Milestones C/D (Risks register, Project/Phase Progress)
  implemented early — no risks page, no phase/progress schema or
  rendering appears anywhere in this milestone's diff.

## 6. TASK-017 dependency check (independent confirmation, not a re-investigation)

Confirmed directly in code: the "Synchronous review" by-path row in
`company_cost_digest()` is built entirely from `agent_runs` (populated by
`opsdb.start_ask_agent_run()`/`end_run()`, called before
`start_reviewer_invocation()` in `reviewer_sync.py`'s own documented
ordering) — it has no read or write dependency on the
`reviewer_invocations` table or on TASK-017's security hook. Milestone
B's cost figures for this path would render identically (all `NULL`,
honestly labeled "not available") whether or not TASK-017's hook fires
correctly. This matches Security's own review scope and is confirmed
independently here, not re-litigated.

---

## Files reviewed for this conformance check

`ops/db/schema.sql`, `ops/db/opsdb.py`, `ops/db/derived_state.py`,
`ops/control-center/generate_costs.py`,
`ops/control-center/generate_meetings.py`, `ops/control-center/server.py`,
`ops/control-center/meeting_orchestrator.py`,
`ops/control-center/chief_of_staff.py`, `ops/control-center/automation.py`,
`ops/control-center/reviewer_sync.py`, `ops/control-center/layout.py`,
`ops/db/test_cost_tracking.py`; live `operations.sqlite3` schema and row
state; `ops/reviews/red-team-milestone-b-review.md`,
`ops/reviews/design-review-milestone-b.md`; `review_results`, `qa_results`,
and `handoffs` rows for `task_id=20`.

No follow-up items raised beyond what Development/Code Review already
disclosed (the `gather_followup_reply()`-and-siblings send-before-end_run
race, deferred consistently across four functions; the sub-cent
`$0.00`-rounding display nuance QA noted as non-blocking). Neither rises
to an architectural concern.
