# Red Team Review — Milestone A: Active Work Dashboard + Task Detail Page (TASK-019)

Date: 2026-08-31
Reviewing: `ops/reviews/cto-milestone-a-architecture.md` (CTO) and
`ops/reviews/design-review-milestone-a.md` (Design), per DEC-009's gate
sequence (CTO architecture → Design review → **Red Team** → Development
→ Code Review → QA → focused Security review → CTO final conformance).

## Verdict

**PASS.** Development may proceed. One real, general, blocking defect
exists in `gates_remaining()` as CTO specified it — it is fixed below
with a precise, minimal specification Development must implement
exactly (no new query, no schema change, no architecture change beyond
one function signature). Design's layout recommendations (items 1–3,
7, 8, 10 in Design's own summary table) are confirmed sound and require
no Red Team override — that is a settled UX call, not a data-model or
security question, and this review does not re-litigate it. Nothing
else found rises to blocking severity.

---

## 1. The `gates_remaining()` bug — reproduced, characterized, and fixed

### 1.1 Reproduction against the live database (not hypothetical)

I queried `ops/db/operations.sqlite3` directly and independently
re-implemented CTO's §1.2–§1.5 pseudocode exactly as written, then ran
it against real `task_status_history` rows.

**TASK-019's own history** (the case Design found):

```
row 135  BACKLOG        -> ARCHITECTURE     22:48:49
row 136  ARCHITECTURE   -> MOCKUP_REVIEW    22:57:28   (backward: idx 2 < idx 3)
row 137  MOCKUP_REVIEW  -> RED_TEAM_REVIEW  23:08:35
```

At the point where `tasks.status = 'MOCKUP_REVIEW'` (between rows 136
and 137), running CTO's algorithm exactly as specified produces:

```
gates_completed() = ['MOCKUP_REVIEW', 'ARCHITECTURE']
gates_remaining() = ['ARCHITECTURE', 'RED_TEAM_REVIEW', 'READY_FOR_DEVELOPMENT',
                      'IN_DEVELOPMENT', 'CODE_REVIEW', 'QA', 'SECURITY_REVIEW',
                      'READY_TO_RELEASE', 'DEPLOYED']
```

`ARCHITECTURE` appears in **both lists simultaneously** — the page
would render "Architecture: done" (gate timeline, §4.2 item 2) and
"Architecture: remaining" (progress chips, §3.2) at the same time, for
the same task, from the same render call. This is not a crash and not
a negative number — it is **silent, internally contradictory output**,
which is the worst of the three failure modes named in the task brief
(throw / negative / silent nonsense) because it ships without any
error signal.

### 1.2 Second, independent reproduction: this is general, not a TASK-019 quirk

I scanned the entire `task_status_history` table for every backward
transition through `GATE_STATUS_ORDER` (a later row whose `to_status`
sits at a lower index than the row's own `from_status`). Real,
already-happened backward transitions exist for **five** separate
history rows across **four** tasks, independent of anything to do with
this milestone:

```
task 1,  row 5:   MOCKUP_REVIEW  -> MOCKUP           (2026-08-28)
task 1,  row 13:  QA             -> IN_DEVELOPMENT   (2026-08-28)
task 6,  row 61:  SECURITY_REVIEW -> CODE_REVIEW      (2026-08-29)
task 10, row 99:  DONE           -> IN_DEVELOPMENT   (2026-08-29)
task 19, row 136: ARCHITECTURE   -> MOCKUP_REVIEW    (2026-08-31)
```

Reconstructing TASK-6's state **as of row 61** (right after its
`SECURITY_REVIEW → CODE_REVIEW` bounce — a completely ordinary
Security-reject-and-rework transition, nothing to do with the
MOCKUP_REVIEW operational quirk Design flagged):

```
gates_completed() = [..., 'CODE_REVIEW', 'QA', 'SECURITY_REVIEW']
gates_remaining() = ['QA', 'SECURITY_REVIEW', 'READY_TO_RELEASE', 'DEPLOYED']
```

`QA` and `SECURITY_REVIEW` both appear as completed **and** remaining.
This confirms the task brief's framing precisely: **the defect is not
specific to this milestone's MOCKUP_REVIEW-for-Design-review
convention.** Any ordinary reject/rework loop — Code Review REJECT
sending a task from `CODE_REVIEW` back toward `IN_DEVELOPMENT`,
Security REJECT sending it back toward `CODE_REVIEW`, or (per
TASK-017's own real three-round history) Red Team REJECT — produces
the identical contradiction the moment `tasks.status` itself is moved
backward as part of that rework loop. Since the whole point of the
Active Work dashboard is to render every active task, and rejection
loops are a normal, expected, frequent part of this system's own
gate sequence (not a rare edge case), this bug would misrender for a
material fraction of real tasks over time, exactly as the task brief
warned.

### 1.3 Was CTO's "evidenced, not assumed" principle actually implemented for this function? No.

CTO's document is correct, and evidenced-not-assumed is correctly
implemented, for `gates_completed()` (§1.4) — it only counts a gate as
done when a later `task_status_history` row for the same `task_id`
proves a forward exit occurred. That part of the design is sound and
I found no flaw in it.

`gates_remaining()` (§1.5) is a **different, unguarded function**. Its
own docstring states the exposed reasoning explicitly: *"this direction
IS safe to compute structurally... 'what's ahead of here' does not
depend on what was skipped behind it."* That claim is true only for
tasks that never move backward — it silently assumes monotonic forward
progress through `GATE_STATUS_ORDER`, which is precisely the assumption
§1.1 already disproved for skip-forward cases and which the same
document's own §1.6 discusses backward-adjacent cases (Security
reviewed mid-`RED_TEAM_REVIEW` occupancy) without ever testing whether
`gates_remaining()` itself holds up under an actual backward status
move. It does not. **CTO's completion-summary claim that the whole
gate model is "evidenced, not assumed" is accurate for
`gates_completed()` and inaccurate, as literally written, for
`gates_remaining()`.** This is exactly the kind of self-report gap this
review exists to catch — verified against the document itself, not
CTO's own characterization of it.

### 1.4 The fix — precise enough to build

Design's own diagnosis already named the right shape of fix ("exclude
anything already present in `gates_completed()`"). I am specifying it
precisely so Development does not have to make design judgment calls:

```python
def gates_remaining(effective_status: str | None, completed: list[str]) -> list[str]:
    """Every GATE_STATUS_ORDER entry strictly after effective_status, up
    to but excluding DONE — MINUS any entry already present in
    `completed` (the same list gates_completed() returned for this
    task), regardless of that entry's position relative to
    effective_status. This makes "remaining" a high-water-mark
    quantity: once a gate has been evidenced forward-exited even once,
    it is never again reported as both completed and remaining on the
    same render, even when a later backward status transition (a
    REJECT-triggered rework loop, or any other cause) moves
    effective_status to a ladder position earlier than that gate's own
    position. Requires the caller to compute gates_completed() first
    and pass its result in — task_progress_row() already calls both,
    so this costs zero new queries, only a call-order dependency
    within one function."""
    completed_set = set(completed)
    start = -1 if effective_status is None else GATE_STATUS_ORDER.index(effective_status)
    return [s for s in GATE_STATUS_ORDER[start + 1:]
            if s != "DONE" and s not in completed_set]
```

This is a **one-parameter signature change** from CTO's Part 2
pseudocode (`gates_remaining(effective_status)` →
`gates_remaining(effective_status, completed)`) and a two-line body
change (filter by `completed_set`, in addition to position). No new
table, no new query, no schema change, no change to `gates_completed()`
itself. `task_progress_row()`'s existing composition order (§2,
"Composes: ... `effective_gate_status()`, `gates_completed()`,
`gates_remaining()`, ...") already calls `gates_completed()` before
`gates_remaining()` in that same order — Development only needs to
thread the already-computed list through.

**Verified against both reproduction cases above**: applying this fix
to TASK-19's `MOCKUP_REVIEW` state removes `ARCHITECTURE` from
`gates_remaining()` (list becomes `RED_TEAM_REVIEW` through `DEPLOYED`,
8 items, no overlap with `gates_completed()`). Applied to TASK-6's
`row 61` state, `QA` and `SECURITY_REVIEW` are removed from remaining
(list becomes `READY_TO_RELEASE`, `DEPLOYED`, no overlap). Both cases
converge to a single, non-contradictory number regardless of which
formulation is used, confirming this fix is equivalent to the "N gates
remaining from the furthest point ever reached" high-water-mark model
the task brief offered as one candidate.

### 1.5 Which of the two candidate designs is right, and why

The task brief offered two options: (a) a high-water-mark
"still-N-remaining" model, or (b) a more honest "was at gate X,
returned to gate Y" display that doesn't collapse the bounce into a
single number.

**Recommend (a) as the required fix; (b) is unnecessary as an
additional requirement, because it already exists.** CTO's own §4.2
item 4 (full `task_status_history`, most recent first) and item 2
(gate timeline, DONE/CURRENT/WAITING) already render every real
backward transition on Task Detail exactly as it happened — a
task that bounced from `ARCHITECTURE` to `MOCKUP_REVIEW` shows that
transition, with its timestamp and `changed_by_agent`, in the status
history section regardless of what `gates_remaining()` reports. The bug
was never that the bounce was invisible; it was that the **summary
count** (`gates_remaining()`, feeding the Active Work dashboard's
compact "N completed / M remaining" chips) disagreed with the **detail
view**. Fixing the summary count to be monotonic (high-water-mark)
resolves that disagreement without inventing new UI for what the
detail page already shows. Building a second, bespoke "was at X,
returned to Y" summary widget on top of the fix would be adding a UI
surface the task brief's own proportionality principle (§6) does not
require — the existing status-history section already carries that
information honestly. I am not recommending it.

**One related, non-blocking observation**: `gates_completed()` counting
`MOCKUP_REVIEW` as "done" for TASK-19 (because it was operationally
used as a stand-in for a custom Design-review gate, then exited
forward) is technically evidenced-correct per CTO's own rule but
semantically odd — a task that has no real Mockup deliverable will
show "Mockup Review: done." This is the same category of
already-disclosed labeling quirk CTO's own §0/§1.6 name for
`review_type` mislabeling (Red Team vs. CTO Conformance) — a real,
minor, honestly-fixable-later oddity, not a blocking defect. Recorded
as follow-up: either the orchestrator should avoid reusing
`MOCKUP_REVIEW` as a proxy status for future ad hoc gates, or Task
Detail's gate timeline should carry a one-line disclosure note when a
ladder-position status is entered/exited without the deliverable that
name normally implies. Development's or a future milestone's call —
not required for this milestone to ship, and does not affect the
correctness of the `gates_remaining()` fix above (that fix is correct
regardless of *why* a backward transition happened).

---

## 2. Design's "three times" finding — display redundancy, plus a real minor query inefficiency

Design is right that this is primarily a display-redundancy problem:
CTO's own Part 5 worked example (TASK-017) shows the same four
`review_results` rows (#48–51) would render once inline in the Gate
timeline (§4.2 item 2), once in the Bounce Count section's row list
(§4.2 item 3, which explicitly says "plus the actual
`review_results`/`qa_results` rows it's built from"), and once more in
full in Findings (§4.2 item 6).

I checked whether this is *also* a real inefficiency, not just a UX
issue: per CTO's literal §4.2 spec, each of those three sections is
described as its own independent query over `review_results`/
`qa_results` filtered to the same `task_id`. At this project's real
scale (single-digit rows per task) three near-identical SELECTs
against an indexed, task-scoped table is computationally negligible —
this is not a performance blocker. But it is unnecessary duplication
Development should not build as three separate queries. Concrete,
non-blocking instruction for Development: fetch
`review_results`/`qa_results` for the task **once** in
`generate_task.py`, and have Gate timeline (short inline note),
Bounce Count (a count plus a link, per Design's §2.4 recommendation),
and Findings (full text) all render from that single result set. This
is naturally what Design's own recommended layout (Bounce Count
becomes a link, not a re-render) already produces if implemented as
Design describes — I am only making explicit that the *query* should
also be shared, not just the visual treatment, so Development doesn't
independently re-derive three separate `SELECT`s while implementing
Design's three-section layout fix.

---

## 3. Scope discipline — confirmed, no creep found

Checked CTO's and Design's output against DEC-009's exact Milestone A
scope (`ops/DECISIONS.md` id=12, `ops/ROADMAP.md` "Founder UI
Completeness" §Milestone A):

- Both new pages are GET-only; CTO's Part 8 explicitly lists what is
  *not* added (`task_gates` table, second status enum, new write
  route, CSRF change, `phases` table, `agent_runs.cost_usd` column,
  company-wide Risks register) — verified true by construction: no
  route in Part 4.1's `server.py` snippet is anything but a GET
  handler reading via `dbutil.connect()`.
- TASK-017 / `risks.id=3` are explicitly untouched — confirmed in
  Part 6.2 ("Explicitly not touched: `server.py` line 1172... part of
  the paused TASK-017 feature") and Part 8. The gate model reuses
  TASK-017's real historical data only as a read-only worked example,
  never as a write path or a change to TASK-017's own status.
  `risks.id=3` is correctly excluded from Task Detail's risk section
  (§4.2 item 8) since it is `scope_type='company'`, verified directly
  against the live `risks` table by CTO's own document and consistent
  with what I see in the schema.
- No Milestone B/C/D implementation appears anywhere: cost is rendered
  honestly as "not available" wherever the underlying data (Milestone
  B's job) doesn't exist yet (§0, §2 `task_cost_usd()`); no Risks
  register page is built (Milestone C); no `phases` structure is
  introduced (Milestone D).
- Design's one addition beyond CTO's literal spec (the 4-number
  summary strip, §1.6 of Design's review) reuses `active_work_rows()`
  verbatim with zero new query and is explicitly flagged optional by
  Design itself — in scope, not creep, and correctly not mandatory.
- The anchor-nav addition (Design §2.1) is plain `<a href="#id">`
  same-page HTML, zero script — consistent with this project's
  zero-client-side-JS constraint; not a new capability.

No scope violation found.

---

## 4. Proportionality (per DEC-009 / ROADMAP.md's explicit instruction)

Applying the Founder's own instruction directly: **exactly one
concrete blocking defect was found** — `gates_remaining()`'s
backward-transition contradiction, reproduced twice above with real
data, fixed precisely in §1.4. Everything else in this review is
named explicitly as follow-up, not grounds to reject:

- The `MOCKUP_REVIEW`-as-Design-review-proxy semantic oddity (§1.5) —
  follow-up, does not block.
- The three-section query duplication (§2) — follow-up guidance for
  Development, does not block; not a security or correctness issue.
- Design's layout change requests (items 1, 2, 3, 7, 8, 10 in Design's
  own table) — already Design's settled call, correctly scoped as
  "small... no new query, no new field," explicitly not requiring a
  second Design round. Red Team has no basis to add friction here and
  does not.

I am not manufacturing additional findings to justify a longer review.
The `gates_remaining()` fix plus confirmation of Design's layout
recommendation is the whole story.

---

## 5. What Development must do before Code Review

1. Implement `gates_remaining(effective_status, completed)` exactly as
   specified in §1.4 above (signature change from CTO's original
   pseudocode), threaded through `task_progress_row()`'s existing call
   order.
2. Add a regression check (unit test or equivalent) covering at least
   the two reproduction cases in this review: a task at `MOCKUP_REVIEW`
   with `ARCHITECTURE` already evidenced-completed (TASK-19's real
   case), and a task at `CODE_REVIEW` with `QA`/`SECURITY_REVIEW`
   already evidenced-completed (TASK-6's real historical case) — in
   both, assert zero overlap between `gates_completed()` and
   `gates_remaining()`.
3. Implement Design's layout items 1/2/3/7/8/10 as Design specified
   (no further Design round needed, per Design's own summary).
4. Fetch `review_results`/`qa_results` once per task in
   `generate_task.py` and render Gate timeline / Bounce Count /
   Findings from that single result set (§2 above).

VERDICT: PASS
