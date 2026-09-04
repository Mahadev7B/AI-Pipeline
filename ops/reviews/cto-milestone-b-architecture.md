# CTO — Milestone B Architecture: Company-wide AI Cost Visibility (TASK-020)

Date: 2026-09-01
Author: CTO
Directive: DEC-009 (`ops/DECISIONS.md`), `ops/ROADMAP.md`'s "Founder UI
Completeness" section — Founder-approved four-milestone plan, Milestone B.
Milestone A (Active Work dashboard + Task Detail page, TASK-019) shipped
and is DONE; this document extends what it built, not a parallel system.
Scope discipline: **architecture only.** Nothing here is implemented.

**The governing fact this whole design is built around, established in
`ops/reviews/cto-product-architecture-completion-v2.md` Part 1 and
re-confirmed against the live code and schema while writing this
document**: all four invocation paths share one measurement function
(`agent_runtime._run_claude()`), and cost is persisted for exactly 1 of
4 (the automation poller, into `automation_events.cost_usd`). This
milestone closes that gap for the other 3 (Ask-Agent, Executive
Meetings, Chief of Staff).

**A second, load-bearing fact this design found while grounding the
brief against real code — stated plainly up front because it reshapes
where cost is shown, not just whether it's persisted**: only the
automation path's `agent_runs` row is ever `scope_type='task'`
(`automation.py:468`, `opsdb.start_run(conn, "code-review", "task",
..., scope_id=task_id)`). Ask-Agent and Chief of Staff runs are always
`scope_type='company'` (`opsdb.start_ask_agent_run()` hardcodes this).
Meeting runs are `scope_type='meeting'`. **None of the three paths this
milestone wires ever produce a task-scoped `agent_runs` row** — the
schema simply has no concept of "this Ask-Agent chat was about task
#17." So even after this milestone ships, `derived_state.task_cost_usd()`
— the function Milestone A's Task Detail/Active Work "Cost" field
already calls — correctly continues to show automation-only cost
per-task. That is not a shortfall of this design; it is the honest
consequence of what these three invocation paths actually are (company-
or meeting-scoped conversations, not task work units). Company-wide
visibility therefore needs its own dedicated surface, not a wider
`task_cost_usd()` — see Part 3.

---

## Part 0 — Write-path change, unlike Milestone A

Milestone A was read-only: new computed functions, new GET routes, zero
writes. **This milestone is a write-path change** — three existing
call sites currently discard a real, already-computed number
(`result.cost_usd`); this design makes them persist it. Per this
project's standing invariant, every write goes exclusively through
`opsdb.py`'s own functions — no call site in `server.py`,
`meeting_orchestrator.py`, `chief_of_staff.py`, or `automation.py` opens
its own write query for this; all of them already only call
`opsdb.start_run()` / `opsdb.start_ask_agent_run()` / `opsdb.end_run()`,
and this design extends `end_run()`'s own signature rather than adding
a parallel write path. No new HTTP route, no new write endpoint, no
auth change — the writes are the *existing* run-lifecycle writes,
carrying one more real field through.

---

## Part 1 — Schema change

### 1.1 `agent_runs.cost_usd` — same shape as `automation_events.cost_usd`

```sql
-- agent_runs.cost_usd REAL, nullable, no CHECK constraint — identical
-- shape to automation_events.cost_usd (schema.sql:303). NULL means
-- either "this run predates cost tracking" (added by this migration) or
-- "the invocation failed before producing a real total_cost_usd" (both
-- honest, both distinct from a genuine $0.00) — never fabricated,
-- never defaulted to 0.
```

**Why a same-shaped column, not a different design**: `automation_events`
already proves this exact shape works for this exact data (a nullable
`REAL` populated once, at run-end, from the same `RuntimeResult.cost_usd`
field). Inventing a second cost-tracking shape (a separate `costs` table,
a JSON blob, etc.) for the same kind of number from the same measurement
function would be duplication with no offsetting benefit — `agent_runs`
already has exactly the row-per-invocation shape cost needs to attach to
(start/end lifecycle, one row per real model call for 3 of the 4 paths;
see Part 2.4 for the two/three sub-invocation cases that need special
handling, not a schema difference).

### 1.2 Migration — follows the `handoffs.base_commit_sha`/`head_commit_sha` precedent exactly

`schema.sql`'s `CREATE TABLE IF NOT EXISTS agent_runs (...)` is not
edited with a raw `ALTER TABLE` (SQLite's `ADD COLUMN` has no `IF NOT
EXISTS` form — a bare statement there would break `opsdb.py init`'s
documented idempotency the same way it would have for `handoffs`). Add
one comment block next to `agent_runs`' existing definition in
`schema.sql` documenting the column and pointing at `opsdb.py` for the
actual migration (mirroring the `handoffs` comment at `schema.sql:227-238`
verbatim in spirit), and extend the existing
`opsdb._apply_additive_column_migrations()` function
(`opsdb.py:93-113`):

```python
# opsdb.py — _apply_additive_column_migrations(), extended
cols = {row["name"] for row in conn.execute("PRAGMA table_info(agent_runs)").fetchall()}
if "cost_usd" not in cols:
    conn.execute("ALTER TABLE agent_runs ADD COLUMN cost_usd REAL")
```

Same function, same idempotency guard (`PRAGMA table_info` check first),
applied to a second table now instead of a new function — no new
migration mechanism invented.

---

## Part 2 — Wiring: `opsdb.end_run()` and every call site

### 2.1 `opsdb.end_run()` — extended, not replaced

```python
def end_run(conn: sqlite3.Connection, run_id: int, status: str = "ended",
            cost_usd: float | None = None) -> None:
    ...
    cur = conn.execute(
        "UPDATE agent_runs SET status = ?, cost_usd = ?, "
        "ended_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ? AND ended_at IS NULL",
        (status, cost_usd, run_id),
    )
    ...
```

`cost_usd` defaults to `None` — every existing caller that does not pass
it (there are none left after this milestone's own wiring, but the
default keeps the function's contract additive/backward-compatible, the
same discipline `end_automation_event()` already sets for its own
optional params). No new function is warranted: `end_run()` is already
the single terminal write for every `agent_runs` row across all four
paths (Ask-Agent, Meetings, Chief of Staff, automation's own task-scoped
run) — a second function would just be `end_run()` with cost, which is
exactly what extending the existing one already gives, with zero
duplication risk of the "two functions can drift" kind Red Team would
otherwise have to check for.

### 2.2 Full list of call sites — every one, named exactly

**`ops/control-center/server.py` — `_handle_ask()`** (`server.py:718-818`):
- Initialize `result = None` immediately before the `try:` at line 791
  (currently `result` is first assigned *inside* that try, at line 795)
  — required so the outer `except Exception:` block (805-810) can safely
  reference it; today that block calls `opsdb.end_run(conn, run_id,
  "failed")` with no cost argument, and an exception raised before line
  795 (e.g. `_build_transcript()` itself raising) would otherwise hit a
  `NameError` if `result.cost_usd` were referenced unconditionally.
- Line 799 (`result.ok` branch): `opsdb.end_run(conn, run_id, "ended",
  cost_usd=result.cost_usd)`.
- Line 804 (`else` branch, `result.ok is False`): `opsdb.end_run(conn,
  run_id, "failed", cost_usd=result.cost_usd)` — real for a parseable-
  but-`is_error` response, `None` for `capacity_exceeded`/`timeout`/
  `runtime_unavailable` (see §2.5).
- Line 807 (outer `except Exception:`): `opsdb.end_run(conn, run_id,
  "failed", cost_usd=(result.cost_usd if result is not None else None))`.

**`ops/control-center/meeting_orchestrator.py`** — three functions that
already open and close an `agent_runs` row around one `invoke_agent()`
call each; `result` is already safely in scope at every `end_run()` call
site below (no `NameError` risk — each function's own outer
`except Exception:` block does not call `end_run()` with a cost
argument, unchanged):
- `_gather_position()` (183-211): line 195 (`ended`) and line 200
  (`failed`) both get `cost_usd=result.cost_usd`.
- `gather_requested_position()` (410-511): line 495 (`ended`) and line
  489 (`failed`) both get `cost_usd=result.cost_usd`.
- `retry_position()` (594-645): line 631 (`ended`) and line 636
  (`failed`) both get `cost_usd=result.cost_usd`.

**`ops/control-center/chief_of_staff.py` — `ask_chief_of_staff()`**
(`chief_of_staff.py:340-429`) — the one call site needing real
aggregation logic; see §2.4 below for the multi-invocation design this
function specifically requires (up to two real invocations —
`result` and, when a CONSULT: is present, `narration_result` — charged
to the one `agent_runs` row this whole exchange already shares).
- Initialize `result = None` and `narration_result = None` before the
  inner `try:` at line 369 (today `result` is first assigned at line
  374, `narration_result` conditionally at line 400) — same `NameError`
  guard reasoning as `_handle_ask()`, needed because the outer
  `except Exception:` at line 421 wraps the whole exchange including
  `send_message()` at line 370, which can fail before either invocation
  ever runs.
- Line 383 (`if not result.ok`, early return): `opsdb.end_run(conn,
  run_id, "failed", cost_usd=result.cost_usd)`.
- Line 420 (`ended`, success path — reached whether or not a consult
  happened): `opsdb.end_run(conn, run_id, "ended",
  cost_usd=_sum_costs(result, narration_result))`.
- Line 423 (outer `except Exception:`): `opsdb.end_run(conn, run_id,
  "failed", cost_usd=_sum_costs(result, narration_result))`.
- New small helper (`chief_of_staff.py`, module-level, next to
  `_parse_consult()`): `_sum_costs(*results) -> float | None` — sums
  `r.cost_usd` for every `r` that is not `None` and whose `cost_usd` is
  not `None`; returns `None` (not `0.0`) if no real cost value was ever
  collected, preserving the same "don't fabricate a $0.00" discipline
  `task_cost_usd()` already established.

**`ops/control-center/automation.py` — `_invoke_and_record()`**
(`automation.py:456-543`) — the one path that already persists cost
correctly, into `automation_events.cost_usd`; per the milestone's own
constraint ("don't touch it except to confirm consistency"), the only
change here is that its own three `end_run()` calls (for the *separate*
task-scoped `agent_runs` row this function also opens, `automation.py:468`)
start passing the exact same `result.cost_usd` value already computed
and already passed to `end_automation_event()` two lines below each
call — lines 483, 505, 515 all get `cost_usd=result.cost_usd` added.
This is not new behavior, not a new number, not a decision-path change
— it is the same already-computed value additionally landing in the
column that now exists on the table it was always missing from. After
this, all four paths populate `agent_runs.cost_usd` uniformly, and
`automation_events.cost_usd` remains the authoritative, task-linked
source `automation.html`/`task_cost_usd()` already read — unchanged.

### 2.3 Nothing else calls `end_run()`

Confirmed by re-reading every `agent_runs`-writing call site in
`server.py`, `meeting_orchestrator.py`, `chief_of_staff.py`, and
`automation.py` while preparing this document — the list in §2.2 is
exhaustive for `end_run()`. §2.4 covers three *additional* invocations
inside `meeting_orchestrator.py` that today have no `agent_runs` row at
all (so there is no existing `end_run()` call to extend) — a distinct,
smaller piece of work, called out separately rather than folded silently
into "the three call sites."

### 2.4 What counts as cost for a Meeting or a Chief-of-Staff conversation — explicit design

**Chief of Staff**: one Founder message can trigger up to two real
model invocations under one `agent_runs` row (`ask_chief_of_staff()`'s
own `result` and, only when the reply contains a `CONSULT:` line, a
second `narration_result`). **Design: sum both into that one row's
`cost_usd`** (`_sum_costs()`, §2.2) — this is one Founder-visible
"turn," and the Founder should see one true total for it, not have to
add two numbers themselves. This does **not** include the cost of the
consult meeting itself (`meeting_orchestrator.run_consult_meeting()`,
called from inside this flow when a consult happens) — that meeting's
own participant invocations get their own `agent_runs` rows,
`scope_type='meeting'`, and are shown as that meeting's own cost (next
point), not folded into the Chief-of-Staff exchange's number. Rationale:
a Founder who opens that linked meeting should see a total that matches
what's shown there; double-counting the consult's cost into the Chief-
of-Staff turn *and* the meeting would overstate company-wide spend when
summed.

**Meetings — both per-invocation and a real per-meeting total, not one
or the other.** Every participant's position (`_gather_position()`,
`gather_requested_position()`, `retry_position()`) already gets its own
`agent_runs` row, `scope_type='meeting'`, `scope_id=<meeting_id>` — so
per-invocation cost is already naturally available, one row per
participant call, no new instrumentation needed for that part. A real
**meeting total** is `SUM(agent_runs.cost_usd) WHERE scope_type='meeting'
AND scope_id=?` — real, correct, and requires no schema change, **with
one disclosed, bounded gap**: `_select_participants()` (CEO's own "who
should attend" call, `meeting_orchestrator.py:75-98`) and `_synthesize()`
(CEO's synthesis call, `meeting_orchestrator.py:214-239`) — plus
`gather_followup_reply()` (`meeting_orchestrator.py:562-591`) — invoke
`agent_runtime.invoke_agent()` today with **no `agent_runs` row at all**,
confirmed directly against the v2 truth table and the code
(`meeting_orchestrator.py`'s own docstrings state this explicitly: "No
`agent_runs` row is created for this call"). Without a row, there is
nowhere for `end_run()` to attach a cost to, regardless of this
milestone's schema/wiring work — this is a distinct, smaller gap, not
closed by §2.2 alone.

**Recommendation: instrument these three, using the exact pattern
already established in the same file for an analogous case**
(`run_meeting()`'s own "Orchestrator: validating meeting participant
selection" bracket, `meeting_orchestrator.py:319-339`, which already
solves the identical "this call happens before the meeting exists"
problem):

- `_synthesize()` and `gather_followup_reply()` both run **after** the
  meeting row already exists — bracket each with
  `opsdb.start_run(conn, "ceo"/"<agent_name>", "meeting", "<label>",
  scope_id=meeting_id)` / `opsdb.end_run(conn, run_id, status,
  cost_usd=result.cost_usd)`, same try/except/finally discipline every
  other bracket in this file uses. Suggested `current_activity` labels:
  `"Meeting: synthesizing"` and `"Meeting: follow-up reply"` — both
  matching the existing `MEETING_ACTIVITY_LIKE = "Meeting:%"` grouping
  pattern (§3.2), so no new classification logic is needed anywhere
  that groups runs by path.
- `_select_participants()` runs **before** `run_meeting()` creates the
  meeting row — it must use `scope_type='company'`, same as the
  existing Orchestrator-validation bracket right next to it, for the
  identical structural reason (no `scope_id` exists yet). Suggested
  label: `"Meeting: selecting participants"`. This means this one
  specific invocation's cost is real, persisted, and grouped correctly
  into the company-wide Meetings bucket on the cost page (§3.2), but
  **cannot** be attributed to that specific meeting's own total once it
  exists — a small, disclosed, structural limit (exactly one invocation
  per *Founder-initiated* meeting; `run_consult_meeting()` never calls
  `_select_participants()` at all, so consult meetings have no such gap).
  The Meeting Detail page's rendered total (§3.3) states this plainly
  next to the number (e.g. a footnote: "excludes CEO's own participant-
  selection call, which is not attributable to one specific meeting —
  see company-wide Costs for that figure") rather than silently
  under-counting with no explanation.

**If Development/Red Team judge this extra instrumentation (three new
brackets, all bookkeeping-only, no behavior change to what a meeting
produces) out of proportion for this milestone**, the documented
fallback is to ship §2.2's wiring alone and label the Meeting Detail
total honestly as partial: *"Meeting cost: $X.XX — participant positions
only; CEO's selection/synthesis calls are not yet separately tracked."*
Both options are concretely specified here; my recommendation is to
include the three brackets, since the alternative silently omits real,
non-trivial cost (CEO's synthesis call processes every participant's
full position text — plausibly the single most expensive call in most
meetings) from a number labeled "total."

### 2.5 A pre-existing limitation this milestone does not change

`agent_runtime._run_claude()` only ever sets `RuntimeResult.cost_usd`
on its one success path (`agent_runtime.py:349-354`, `ok=True`) — every
failure branch (`capacity_exceeded`, `runtime_unavailable`, `timeout`,
`runtime_error`, including the `is_error` JSON case) returns
`RuntimeResult(ok=False, ...)` without a `cost_usd` value, so it is
always `None` on failure, **even for `runtime_error`/`is_error`, where
the CLI's own JSON might in principle have reported a real
`total_cost_usd` alongside the error**. This is an existing behavior of
`agent_runtime.py`, not something this milestone's `opsdb.end_run()`/
call-site wiring changes — a failed run persists `cost_usd=NULL`
honestly (not a fabricated `$0.00`), consistent with every other
"not available" convention in this design. Widening `_run_claude()`
itself to also capture cost on error paths is a real, disclosed,
separately-scoped improvement — flagged here, not undertaken, since it
touches the one shared measurement function every path depends on and
is out of proportion to "persist the number that's already computed."

---

## Part 3 — Company-wide visibility: where a Founder actually sees this

### 3.1 Task Detail / Active Work — unchanged mechanism, updated honesty note

Per the cross-cutting finding in the preamble, `task_cost_usd()`
(`derived_state.py:407-423`) and its two renderers
(`generate_task.py:156`, `generate_active_work.py:112`) are **not**
widened to read `agent_runs.cost_usd` — none of the three newly-wired
paths ever produce a task-scoped run, so there is nothing new for a
per-task query to pick up. What changes is the `note` text, which today
says *"...is not persisted until Milestone B ships"* — false the moment
this milestone ships (it is persisted, just not task-attributable).
Updated note: *"automation-poller cost only — Ask-Agent, Meeting, and
Chief-of-Staff conversations are not tied to a specific task in this
system's data model; see the company-wide Costs page for those
figures."* Same `{"available", "usd", "note"}` shape, same call sites,
one string literal changed, plus (new) a link from both renderers to
`/costs.html` next to the "not available" text so a Founder is never
left wondering where the rest of the number lives.

### 3.2 New dedicated `/costs.html` — the concrete recommendation

**Recommendation: a new dedicated page, not an extension of
`automation.html`.** Reasoning, concretely: `automation.html`'s spend
section (`render_spend()`, `generate_automation.py:110-121`) is scoped
to, and its $10.00/day ceiling is defined for, the automation poller
specifically (`automation.MAX_AUTOMATION_SPEND_USD_PER_DAY`) — mixing
in Ask-Agent/Meeting/Chief-of-Staff spend on that same page would make
"today's automation spend / $10.00 daily ceiling" read as if unrelated
conversational spend counted against automation's own ceiling, which it
structurally does not and must not (Part 3.5 confirms no such merge is
authorized). A dedicated page keeps that distinction visually and
architecturally honest, while still **reusing `render_spend()`'s
established visual pattern** (a large `$X.XX` figure, a labeled
comparison line, a colored progress bar) for its own company-wide
figure, per the brief's own instruction not to invent a new UI
convention.

New file `ops/control-center/generate_costs.py`, `build_html(token=None)`
— same shape as every other top-level `generate_*.py`. New nav entry in
`layout.py`'s `NAV_LINKS`, placed after "Automation" (spend is a
company-health concern adjacent to, but not part of, the automation
kill-switch page it sits next to).

New `derived_state.py` function, `company_cost_digest(conn) -> dict`,
composing:

- **Today's total AI spend** — `SUM(agent_runs.cost_usd)` for runs
  started today, plus `SUM(automation_events.cost_usd)` for events
  started today (automation's own run-row cost, post-§2.2, is a subset
  of the first sum — automation's contribution is counted once, via
  `automation_events`, the historically authoritative source for that
  path; the `agent_runs` sum for automation's own rows is used only for
  the "by path" breakdown's internal consistency check, not summed a
  second time into the headline total). No ceiling — see §3.5 — so no
  progress bar denominator; the figure is shown plainly, with
  automation's own existing $10.00/day ceiling and bar left exactly
  where it already is, unduplicated.
- **By invocation path** — grouped by `current_activity`'s existing,
  already-disclosed prefix convention (`ASK_AGENT_ACTIVITY_LIKE =
  "Ask-Agent:%"`, `MEETING_ACTIVITY_LIKE = "Meeting:%"`,
  `CHIEF_OF_STAFF_ACTIVITY_LIKE = "Chief of Staff:%"`,
  `AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE = "Automated Code Review:%"`,
  `REVIEWER_SYNC_ACTIVITY_LIKE = "Synchronous review:%"` — all defined
  once already in `agent_runtime.py:65-151`, reused here as the
  grouping key rather than inventing a new classification column). Each
  bucket shows its own `SUM`/count, and its own count of rows with
  `cost_usd IS NULL` (§3.4).
- **By agent (Ask-Agent + Chief of Staff)** — `SUM(cost_usd) GROUP BY
  agent_id` for `scope_type='company'` rows, joined to `agents.name` /
  `derived_state.display_name()` — this is where a Founder sees "how
  much have I spent talking to the CTO agent" without needing a new
  per-message cost tag inside the existing Ask-Agent chat panel
  (`generate_agents.py`'s `render_ask_agent_section()` is **not**
  touched by this milestone — lower risk, and the aggregate view already
  answers the real question without retrofitting a chat UI that has no
  natural place to attach a $-per-bubble tag today).
- **Recent meetings, with cost** — a small table, most recent first,
  reusing `meeting_cost_usd()` (§3.3) per row, linking to each meeting's
  own detail page.

### 3.3 Meeting Detail page — new cost section

`generate_meetings.py`'s meeting detail renderer currently has zero
references to cost (confirmed, matching the v2 truth table). New
`derived_state.meeting_cost_usd(conn, meeting_id) -> dict`, same
`{"available", "usd", "note"}` shape as `task_cost_usd()`, built from
`SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd),0) AS total,
COUNT(*) FILTER (WHERE cost_usd IS NULL) AS missing FROM agent_runs
WHERE scope_type='meeting' AND scope_id=?`. Rendered once, near the top
of the meeting detail page (mirroring where Task Detail's own cost line
sits), plus — if §2.4's three brackets are built — the CEO-selection
footnote described there.

### 3.4 Historical data — honest rendering, not a crash, not a fabrication

Every `agent_runs` row that exists before this migration ships has
`cost_usd = NULL` (the column didn't exist; SQLite's `ALTER TABLE ADD
COLUMN` backfills existing rows with `NULL`, not `0`). This is exactly
the same shape `task_cost_usd()` already handles for `automation_events`
(count decides availability, not just the sum) — reused, not
reinvented:

- **Per-row** (the "recent meetings"/"by agent" lists on `/costs.html`,
  the per-participant lines on Meeting Detail): a `NULL` `cost_usd`
  renders `"not available (recorded before cost tracking)"` — visually
  and textually distinct from `$0.00`, never silently omitted from the
  list (the run itself, and the fact that its cost is unknown, is still
  shown).
- **Aggregate** (`SUM`): SQLite's `SUM()` already silently skips `NULL`
  values — correct arithmetic, but silently under-representative on its
  own. Every aggregate figure this design introduces is therefore always
  paired with its own coverage count — *"$12.34 across 9 of 14
  invocations today (5 predate cost tracking)"* — the same "count, not
  just sum, decides what's shown" discipline `task_cost_usd()` already
  established, applied everywhere a `SUM` appears in this milestone's
  new code. No page in this design ever presents a `SUM` as if it were
  complete when rows with `NULL` cost exist in its own scope.

### 3.5 Founder-facing budget/ceiling — explicitly out of scope, visibility only

**No new ceiling, cap, or write-side control is introduced by this
milestone.** `automation.MAX_AUTOMATION_SPEND_USD_PER_DAY` stays exactly
where it is, governing exactly what it already governs (the automation
poller's own daily spend, enforced in `automation._check_daily_spend_cap()`
— untouched). `/costs.html`'s company-wide total is a **read-only
figure with no denominator, no bar tied to a limit, and no enforcement
mechanism** — stated this plainly per the brief's own instruction not to
silently add a new write-side control when only visibility was
authorized. If the Founder wants a company-wide spend ceiling once this
figure is visible and has been observed for a while, that is a
follow-on decision requiring its own architecture review (a
company-wide ceiling raises real design questions this milestone does
not resolve — e.g. does it gate Ask-Agent/Meetings the way automation's
ceiling gates the poller, and if so, what does "capacity_exceeded"-style
denial look like for a live Founder conversation rather than an
unattended background job) — explicitly not decided or implied here.

---

## Part 4 — Files this milestone touches (complete list)

**New:**
- `ops/control-center/generate_costs.py` — `/costs.html`.

**Modified — schema/migration:**
- `ops/db/schema.sql` — one new comment block documenting
  `agent_runs.cost_usd` (mirroring the `handoffs` precedent), no literal
  column added here.
- `ops/db/opsdb.py` — `_apply_additive_column_migrations()` (one new
  `PRAGMA table_info(agent_runs)` check + `ALTER TABLE`); `end_run()`
  (new `cost_usd: float | None = None` parameter, persisted
  unconditionally into the now-existing column).

**Modified — call sites wiring existing `end_run()` calls (§2.2):**
- `ops/control-center/server.py` — `_handle_ask()`: `result = None`
  initialization, 3 `end_run()` calls updated.
- `ops/control-center/meeting_orchestrator.py` — `_gather_position()`,
  `gather_requested_position()`, `retry_position()`: 6 `end_run()` calls
  updated (2 per function).
- `ops/control-center/chief_of_staff.py` — `ask_chief_of_staff()`:
  `result = None` / `narration_result = None` initialization, new
  `_sum_costs()` helper, 3 `end_run()` calls updated.
- `ops/control-center/automation.py` — `_invoke_and_record()`: 3
  `end_run()` calls updated for consistency (§2.2's last item) — no
  behavior change, same value already passed to `end_automation_event()`.

**Modified — new instrumentation for full meeting-cost attribution
(§2.4, recommended; see that section's stated fallback if descoped):**
- `ops/control-center/meeting_orchestrator.py` — `_select_participants()`,
  `_synthesize()`, `gather_followup_reply()`: new `start_run()`/
  `end_run()` brackets, 3 new call sites (not extensions of existing
  ones — these functions have no `agent_runs` row today).

**Modified — display:**
- `ops/db/derived_state.py` — `task_cost_usd()`'s `note` string updated
  (§3.1); new `company_cost_digest()` (§3.2) and `meeting_cost_usd()`
  (§3.3) functions, additive.
- `ops/control-center/generate_task.py`, `generate_active_work.py` — the
  existing "not available" branch gets a link to `/costs.html`; no
  structural change.
- `ops/control-center/generate_meetings.py` — new cost section on the
  meeting detail renderer (§3.3).
- `ops/control-center/layout.py` — one new `NAV_LINKS` entry
  (`costs.html`, after `automation.html`).
- `ops/control-center/server.py` — one new top-level GET route
  (`/costs.html`), same dispatch pattern as every other top-level page,
  same read-only `dbutil.connect()` discipline.

**Explicitly not touched:** `agent_runtime.py` (§2.5's disclosed,
separately-scoped limitation), `generate_agents.py`'s
`render_ask_agent_section()` (§3.2 — aggregate view instead of a new
per-message cost tag), `automation.py`'s spend-cap logic and
`generate_automation.py`'s existing `render_spend()` (unchanged, not
merged with company-wide figures per §3.5), any write route, any auth
mechanism, TASK-017/`risks.id=3`.

---

## Part 5 — Gates for this milestone

Per DEC-009: CTO architecture (this document) → Design review (there is
a real, if small, Founder-facing UI surface — the new `/costs.html`
page and the new Meeting Detail cost section — so this gate applies,
unlike a purely backend-only change) → Red Team → Development → Code
Review → QA → a focused Security review scoped to newly introduced risk
only → CTO final conformance.

### 5.1 What the Design review gate should specifically weigh in on

1. `/costs.html`'s layout and information density — the four sections
   in §3.2 (today's total, by-path breakdown, by-agent breakdown, recent
   meetings) vs. a denser or reordered presentation.
2. Whether the §2.4 CEO-selection/synthesis/follow-up instrumentation
   ships this milestone or is descoped to the disclosed fallback.
3. The exact wording of the "not available (recorded before cost
   tracking)" and coverage-count disclosures (§3.4) — these need to read
   as informative, not alarming, the same "informative not alarmist"
   note Milestone A's Design review gate already applied to the
   staleness badge.
4. Consistency with the existing dark visual system and `render_spend()`'s
   established visual pattern — a check, not an open design brief.

### 5.2 The focused Security review

This is the one milestone in the four-milestone plan that is a genuine
write-path change (Part 0), so Security's review should specifically
verify, not skip past:
- No new HTTP write route is introduced (true by construction — every
  write in this design is an existing `opsdb.end_run()` call carrying
  one additional, already-computed field; `/costs.html` and the Meeting
  Detail cost section are GET-only reads).
- The new `cost_usd` values written are exactly the values
  `agent_runtime.invoke_agent()` already returned to each existing
  caller — no new computation, no new external input reaches `opsdb.py`
  as a result of this milestone (the CLI's own reported
  `total_cost_usd` is the sole source, unchanged from what already flows
  into `automation_events.cost_usd` today).
- `/costs.html` renders no data more sensitive than what other pages in
  this Control Center already show today — dollar figures derived from
  already-Founder-visible agent activity, not new categories of
  information.
- `dbutil.connect()` read-only mode is used throughout the new
  `generate_costs.py` file, same discipline as every other generator.

---

## Part 6 — What this design explicitly does not add

No new table (the one schema change is a single additive column on an
existing table). No new write route, no auth change. No company-wide
spend ceiling or enforcement mechanism (§3.5). No change to
`automation.py`'s existing spend-cap behavior. No retrofit of the
Ask-Agent/Chief-of-Staff chat UI with per-message cost tags (an
aggregate view answers the real question at far lower risk). No
retroactive cost estimation for pre-migration rows — `NULL` renders as
an honest "not available," never a guessed number. No touch to
TASK-017, `risks.id=3`, or Milestones C/D's scope.
