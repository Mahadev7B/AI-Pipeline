# Red Team Review — Milestone B: Company-wide AI Cost Visibility (TASK-020)

Date: 2026-09-01
Reviewing: `ops/reviews/cto-milestone-b-architecture.md` (CTO) and
`ops/reviews/design-review-milestone-b.md` (Design), per DEC-009's
Red Team gate, before Development starts.

## Verdict

**PASS**, with a small set of named, low-cost refinements Development
must incorporate (wording/documentation/one QA checklist item — no new
query, no new table, no architectural rework, no second Design or CTO
round required). This mirrors the proportionality precedent DEC-009
itself sets and that Design's own review already used for its own
items 3/4/5/8.

Nothing found here is a concrete blocking defect in the architecture.
Everything below is either confirmation that CTO's/Design's design
holds up against the real code and the real live database, or a small,
disclosed addition in the same spirit as the ones Design already made.

---

## 1. The fifth-path question — resolved, with one important correction to the record

**`reviewer_invocations` does NOT exist in the live database today.**
Verified directly:

```
$ python3 -c "... PRAGMA table_info / sqlite_master ..."
live tables: agent_activity, agent_runs, agents, approvals,
automation_events, automation_state, decisions, deployments, handoffs,
meetings, messages, projects, qa_results, review_results, risks,
sqlite_sequence, task_status_history, task_steps, tasks
```
No `reviewer_invocations`. It **is** specified in `schema.sql:344-364`
(added by commit `fdaf253`, "TASK-017: Development pass complete,
PAUSED per Founder directive (DEC-008)") as `CREATE TABLE IF NOT
EXISTS`. The reason for the gap is mechanical, not a mystery: that
`CREATE TABLE IF NOT EXISTS` only ever runs inside `opsdb.py cmd_init`'s
`conn.executescript(SCHEMA_PATH.read_text())` (`opsdb.py:118-121`) — it
is **not** re-applied automatically on server startup or by any other
code path. Nobody has re-run `opsdb.py init` against the live DB since
that commit, so the table specified in `schema.sql` was simply never
created live. (By contrast, the `handoffs.base_commit_sha`/
`head_commit_sha` precedent CTO cites *is* live-verified present —
`PRAGMA table_info(handoffs)` on the real DB shows both columns — so
`init` clearly *was* re-run at some point after Phase 3A. It just
wasn't re-run again after the TASK-017 commit.)

**This does not make Design's flag hypothetical, though — it's more
precise than "future path" or "current path."** The grouping key
Design is worried about (`REVIEWER_SYNC_ACTIVITY_LIKE = "Synchronous
review:%"`) is not a property of `reviewer_invocations` at all — it's a
value written into `agent_runs.current_activity`, and `agent_runs` is a
live, populated table today. Tracing `reviewer_sync.py`'s
`_invoke_and_record()` (`reviewer_sync.py:221-345`) directly:
`opsdb.start_ask_agent_run()` (which writes the `agent_runs` row with
that activity label) runs **before** `opsdb.start_reviewer_invocation()`
(which would hit the missing table) — by design, per the function's own
docstring ("agent_runs is started... BEFORE the reviewer_invocations
row, so a failure creating the latter still leaves a clean, ended
agent_runs row"). So: **the three POST routes that produce this
activity label are fully merged and live-reachable right now** —
`server.py:1185-1218` dispatches `/api/tasks/<id>/review/{code,
security,red-team}`, and `generate_reviews.py:91` renders a real,
clickable `<form method="POST">` button for each on the live,
nav-linked `/reviews.html` page (`layout.py:54`). Clicking one today
would create a real `agent_runs` row with `current_activity =
"Synchronous review: ..."`, then immediately fail with `sqlite3.
OperationalError: no such table: reviewer_invocations` inside
`start_reviewer_invocation()` — caught by `_invoke_and_record()`'s own
broad `except Exception:` (line 310), which ends that `agent_runs` row
as `"failed"` before returning a normal HTTP error response. No
orphaned row, no crash reaches the Founder — but no successful
"Synchronous review" row is possible today, either.

**Net correction to the record**: it is not that this fifth path
"doesn't exist yet" (Design's zero-live-rows finding is accurate, but
for a subtly different reason than an unbuilt feature) — it's that the
path is fully wired, live, and reachable via an existing Founder-facing
button, but currently guaranteed to fail every time due to one missing
table. This is a **pre-existing defect independent of Milestone B**,
not introduced or worsened by it, and fixing it (re-running `opsdb.py
init`, or otherwise reconciling `schema.sql` against the live DB) is
squarely TASK-017/`risks.id=3` territory — per DEC-009's explicit
boundary, Milestone B must not touch it, and this review is not asking
it to. **Recommendation: flag this defect separately** (to CTO/whoever
owns the TASK-017 resume checkpoint) so it isn't rediscovered by
surprise later; it is out of scope for this task's Development pass.

**For Milestone B's own by-path grouping**: since `REVIEWER_SYNC_
ACTIVITY_LIKE` is a real constant already used against a real, live
table (`agent_runs`), and CTO's own `company_cost_digest()` composition
already lists all five constants (§3.2), **Design's recommendation to
render it as an explicit fifth row stands and should ship** — this is
zero new attribution logic, not future-proofing a paused feature's own
schema, and not scope creep into TASK-017 (Milestone B never touches
`reviewer_invocations`, `reviewer_sync.py`, or any TASK-017 write path).
It is simply not silently dropping a category CTO's own grouping key
already produces.

**One consequence worth documenting, not fixing, in this milestone**:
`reviewer_sync.py`'s own three `opsdb.end_run()` calls
(`reviewer_sync.py:281, 322, 341`) never pass `cost_usd`, even though a
real, already-computed `result.cost_usd` sits right next to each call
(passed into `end_reviewer_invocation()` on the very next line/lines
262, 273, 291, 343). After Milestone B extends `end_run()`'s signature,
these calls will keep defaulting to `cost_usd=None` — so, as long as
TASK-017 stays paused, **every future "Synchronous review" `agent_runs`
row will have `cost_usd = NULL` forever**, not just historically. This
is correct and required by the DEC-009 boundary (Milestone B must not
touch `reviewer_sync.py`), but it means the fifth by-path row's
eventual real data (once/if TASK-017 resumes and is separately fixed)
won't just be "recorded before cost tracking" — it will remain
uncosted by construction until someone updates `reviewer_sync.py`
itself. Recommend one line in `generate_costs.py`'s by-path row caption
or a code comment noting this, so a future reader doesn't mistake it
for a Milestone B bug.

## 2. Call-site completeness — verified against the real code, list holds

Grepped every `agent_runtime.invoke_agent(`/`_run_claude(` call site
across `ops/control-center/*.py`. Full list, with CTO's coverage:

| Call site | File:line | Covered by CTO's design |
|---|---|---|
| `_handle_ask()` | `server.py:795` | Yes (§2.2) |
| `ask_chief_of_staff()` `result` | `chief_of_staff.py:374` | Yes (§2.2) |
| `ask_chief_of_staff()` `narration_result` | `chief_of_staff.py:400` | Yes (§2.2) |
| `_select_participants()` | `meeting_orchestrator.py:95` | Yes (§2.4, new bracket) |
| `_gather_position()` | `meeting_orchestrator.py:191` | Yes (§2.2) |
| `_synthesize()` | `meeting_orchestrator.py:236` | Yes (§2.4, new bracket) |
| `gather_requested_position()` | `meeting_orchestrator.py:485` | Yes (§2.2) |
| `gather_followup_reply()` | `meeting_orchestrator.py:582` | Yes (§2.4, new bracket) |
| `retry_position()` | `meeting_orchestrator.py:627` | Yes (§2.2) |
| `_invoke_and_record()` (automation) | `automation.py:473` | Yes (§2.2) |
| `_invoke_and_record()` (reviewer_sync) | `reviewer_sync.py:254` | **Not covered — correctly, see §1 above** |

CTO's §2.3 claim ("exhaustive... for every `agent_runs`-writing call
site in `server.py`, `meeting_orchestrator.py`, `chief_of_staff.py`,
and `automation.py`") is accurate as literally scoped — it never
claimed to cover `reviewer_sync.py`, and per §1 above, that exclusion
is correct, not an oversight. **No call site anywhere in this codebase
was missed that Milestone B is actually responsible for.**

Spot-checked CTO's own line-number citations directly against the real
files (not just trusting the document): `server.py:791/795/799/804/807`
match exactly; `automation.py:483/505/515` match exactly;
`chief_of_staff.py:374/400/420/423` match (one citation, "line 383,"
is off by one — the real `end_run()` call for that branch is on line
382, with `return` on 383 — a trivial citation slip, not a logic
error); `_select_participants()`/`_synthesize()`/`gather_followup_
reply()` confirmed to have **no** existing `start_run()`/`end_run()`
bracket today, matching CTO's §2.4 claim precisely. `end_run()`'s
current live signature (`opsdb.py:408`) has no `cost_usd` parameter,
confirming the "extended, not replaced" framing is accurate (nothing
currently calls it with a cost argument).

## 3. Design's launch-state concern — structurally addressed, one refinement recommended

CTO's/Design's "count decides availability" discipline (§3.4 of CTO's
doc; §1.1/§3.4/§5.1-item-3 of Design's review) is real and, if built as
specified, does prevent the "$0.00 Ask-Agent = free" misreading for the
**zero-total-rows** case (Design's Concept A renders "No invocations
recorded yet," no dollar sign) and for the **partially-covered** case
(CTO's own format, `"$12.34 across 9 of 14 invocations... (5 predate
cost tracking)"`, always shows the denominator inline on the same row,
not in a separate footnote a Founder could miss).

**One gap neither document's wording branch covers**: rows/buckets
where invocations *did* happen (`M > 0`) but **none** of them have a
real cost (`N = 0` — e.g., every one predates the migration, or every
one failed before a cost was captured, or — per §1 above — an entire
path like "Synchronous review" that structurally never gets a cost
today). Under CTO's literal format string, this renders as `"$0.00
across 0 of 5 invocations (5 recorded before cost tracking)"` — factually
correct, and not literally alarmist, but it still puts a numeral `$0.00`
as the leading, most visually prominent token on the row, which is
exactly the misreading risk item 3 of this review's brief asks about.
A Founder skimming (not reading the full sentence) sees "$0.00" first.

**Recommendation**: extend Design's own §1.1 branch one step further —
when the covered count is `0` (`N == 0`), regardless of whether `M` is
also `0`, render the same no-dollar-sign treatment ("not available —
0 of M invocations have a recorded cost" / similar), never a bare
`"$0.00 across 0 of M..."` string. This is the identical principle
Design already established (a `$` figure implies a real, meaningful
number; when there is none, don't print one), applied consistently to
one more case it currently misses — zero new queries, one more
conditional branch in the same rendering function Design's item 3
already touches. Small enough that, per this project's own
proportionality precedent, it should be folded into the same
implementation pass as Design's items 3/4/5/8, not routed back through
another Design review round.

## 4. Migration correctness — pattern is real and idempotent; one operational step is currently unstated

`_apply_additive_column_migrations()` (`opsdb.py:93-113`) is real,
reads as advertised (a `PRAGMA table_info()` guard before each `ALTER
TABLE ADD COLUMN`, called once from `cmd_init` at `opsdb.py:118-121`),
and the pattern's precedent genuinely works in production: the live
database's `handoffs` table was checked directly and does have both
`base_commit_sha` and `head_commit_sha` columns already, confirming the
`opsdb.py init` re-run for that earlier migration was actually done.
CTO's plan (extend the same function, same guard, one more table) does
not violate the "only `opsdb.py` writes the live DB" invariant — the
new code is entirely inside `opsdb.py` itself, called from its own
`cmd_init`.

**What's not stated anywhere in CTO's document**: this migration only
takes effect on the live database if a human (or a deploy step) runs
`python3 ops/db/opsdb.py init` again after this code merges.
`_apply_additive_column_migrations()` is not invoked anywhere else —
not on server startup, not from any other command. This project already
has one live, currently-undiscovered example of exactly this gap: the
`reviewer_invocations` table (§1 above) has been sitting correctly
specified in `schema.sql` and incorrectly absent from the live database
since commit `fdaf253`, because nobody re-ran `init` after that commit.
The same failure mode, applied to `agent_runs.cost_usd`, would mean
every one of Milestone B's new `SUM(agent_runs.cost_usd)` queries
crashes with "no such column" the moment `/costs.html` or the Meeting
Detail cost section is first hit post-deploy — not a subtle bug, but
one this review would rather see explicitly guarded against than
discovered live a second time.

**Recommendation (required, cheap)**: add one explicit line to this
milestone's Development/QA checklist — confirm, against the actual live
`operations.sqlite3` (not a scratch/test DB), that `PRAGMA table_info
(agent_runs)` includes `cost_usd` before this milestone is marked
complete. This is a process/checklist addition, not an architecture
change — no document needs to be re-approved for it, and it costs one
command to run and one line to check off.

## 5. Scope discipline — confirmed clean

- No `risks.id=3`/TASK-017 write path is touched. `reviewer_sync.py`,
  `reviewer_invocations`, and the synchronous reviewer routes are
  correctly left alone (§1 above) — the only relevant fact Milestone B
  legitimately relies on is a pre-existing, already-defined constant in
  `agent_runtime.py`, not a new dependency on TASK-017's own tables.
- No new HTTP write route. Verified: the only new server.py route is
  `/costs.html`, a `GET` dispatched the same way as every other
  top-level page (`server.py`'s existing `if path == "..."` ladder);
  every write in this design is an *existing* `opsdb.end_run()` call
  carrying one additional already-computed field, exactly as Part 0
  claims.
- No Milestone C/D implementation found anywhere in either document —
  both stay inside company-wide cost visibility.
- DEC-009's four named paths (Ask-Agent, Executive Meetings, Chief of
  Staff, automated Code Review) match `ROADMAP.md`'s wording exactly;
  the fifth constant is additional, not a departure from what was
  approved (§1 above explains why surfacing it, without wiring anything
  new into TASK-017, is still in-bounds).

## 6. Proportionality

Per the brief's own instruction: the fifth-path question and the
call-site audit both resolved cleanly enough that no additional
findings were manufactured beyond what's above. Items in §3 and §4 are
real, evidence-backed, and cheap to fix — not filler. Nothing here rises
to a blocking architectural defect; PASS stands.

---

## Summary of required follow-through (not a second architecture/Design round)

1. Include the `REVIEWER_SYNC_ACTIVITY_LIKE` bucket as an explicit
   fifth by-path row (Design already specified this; confirmed correct
   and in-scope, §1).
2. One-line disclosure (comment or row caption) that "Synchronous
   review" cost will remain `NULL` by construction until TASK-017's own
   file is separately updated — not a Milestone B defect (§1).
3. Extend the "no bare `$0.00`" wording principle to the `N == 0, M > 0`
   case, not just `M == 0` (§3).
4. Add an explicit Development/QA checklist item: confirm
   `agent_runs.cost_usd` actually exists on the live database (not just
   a test DB) via `opsdb.py init`, before sign-off (§4).
5. Separately flag (outside this task) the pre-existing, live,
   currently-reachable-but-broken `/reviews.html` synchronous-review
   buttons for whoever owns the TASK-017 resume checkpoint (§1) — not
   Milestone B's responsibility to fix.

VERDICT: PASS
