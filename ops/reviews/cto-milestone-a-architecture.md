# CTO — Milestone A Architecture: Active Work Dashboard + Task Detail Page (TASK-019)

Date: 2026-08-31
Author: CTO
Directive: DEC-009 (`ops/DECISIONS.md`), `ops/ROADMAP.md`'s "Founder UI
Completeness" section — Founder-approved four-milestone plan, Milestone A,
authorized to proceed without a further approval round.
Scope discipline: **architecture only.** Nothing here is implemented.
This document makes concrete and buildable what
`ops/reviews/cto-product-architecture-completion.md` (Part 3) and
`cto-product-architecture-completion-v2.md` (Parts 3 and 5) already
sketched — it does not re-litigate their reasoning, it finishes it.
Read-only pages, zero new write routes, zero change to the Founder
session/CSRF gate. Does not touch TASK-017, `risks.id=3`, or any
remaining Phase 3 orchestration automation.

---

## Part 0 — What carries over unchanged from the prior two documents

Reused verbatim, not re-derived:

- **No `task_gates` table.** A gate is a computed read over
  `task_status_history` + `review_results` + `qa_results` + `approvals`.
  I looked again, specifically for this document, for a concrete reason
  the no-new-table approach would fail at this milestone's actual scope
  (real TASK-017 data, real query shapes below) — found none. Confirmed,
  not re-litigated.
- **Precedent for a dynamic per-entity page**: `/agents/<name>.html` and
  `/meetings/<id>.html` — regex/digit-bounded validation, a 404 on a
  missing row, a `build_*_detail(conn, row, token=...)` function shared
  between `server.py`'s live GET handler and a batch `generate_*.py`
  script. `/tasks/<id>.html` follows this exactly.
- **The bounce-count query** (prior doc §3.2), **the gate-occupancy
  definition** (prior doc §3.1: a gate = one `tasks.status` occupancy,
  bounded by `task_status_history` rows), and **the DONE/CURRENT/WAITING
  lane model with REJECTED as an inline outcome, not a fourth lane**
  (v2 doc §5.1) — all reused unchanged.
- **The `review_type` widening recommendation** (`('code','security')` →
  `('code','security','red-team')`, prior doc §3.1) stays a
  recommendation, not implemented here. Its absence is worked around the
  same way both prior documents worked around it: label by
  `reviewed_by_agent`, not `review_type`, wherever the two would
  otherwise be lumped together (Red Team and CTO Conformance rows both
  carry `review_type='code'` today).
- **CTO Conformance labeling** (v2 doc §5.2): `review_results` rows with
  `reviewed_by_agent='cto'` are labeled "CTO Conformance" in rendered
  history, not folded into "Code Review."
- **Cost honesty**: `SUM(automation_events.cost_usd)` is the only real
  number available per task until Milestone B ships; everything else
  renders "not available," never a fabricated or estimated figure.

---

## Part 1 — The gate model, made concrete

### 1.1 The real problem the prior sketches left open

Both prior documents illustrated a gate timeline for TASK-017 but never
specified a precise, generalizable algorithm for two things every task
needs: (1) which `tasks.status` value is "current" when the task is
sitting in an interrupt state (`BLOCKED`/`FOUNDER_APPROVAL`), and (2) what
"N of M gates complete" means as a number, not just a rendered list. I
resolved both by querying the live database directly rather than assuming.

**Finding, confirmed by direct query**: real tasks in this project
routinely skip ladder positions. TASK-016, TASK-017, TASK-018, and
TASK-019 all transition `BACKLOG → ARCHITECTURE` directly — `PLANNING`,
`MOCKUP`, and `MOCKUP_REVIEW` are never entered for architecture/ops-only
work. TASK-017 also transitions `RED_TEAM_REVIEW → IN_DEVELOPMENT`
directly, skipping `READY_FOR_DEVELOPMENT`. This means a naive "gates
completed = index of current status in the fixed 13-status ladder" is
**fabricated progress** for the majority of real tasks in this database —
it would silently claim PLANNING/MOCKUP/MOCKUP_REVIEW were "done" when
they were never entered at all. This directly violates the no-fabrication
constraint, so the design below does not do this.

### 1.2 `GATE_STATUS_ORDER` — the real, schema-backed ladder

```python
# ops/db/derived_state.py — new constant, additive, next to STAGE_MAP.
GATE_STATUS_ORDER = [
    "PLANNING", "MOCKUP", "MOCKUP_REVIEW", "ARCHITECTURE", "RED_TEAM_REVIEW",
    "READY_FOR_DEVELOPMENT", "IN_DEVELOPMENT", "CODE_REVIEW", "QA",
    "SECURITY_REVIEW", "READY_TO_RELEASE", "DEPLOYED", "DONE",
]
```

The same 13 `tasks.status` values `STAGE_MAP` already maps, in the same
order. `BACKLOG`, `BLOCKED`, `FOUNDER_APPROVAL` are deliberately excluded
— consistent with `STAGE_MAP`'s own existing exclusion of them as
interrupt/entry states, not pipeline columns.

### 1.3 Effective gate status (resolves the BLOCKED/FOUNDER_APPROVAL question)

```python
def effective_gate_status(conn, task_id: int, current_status: str) -> str | None:
    """current_status if it's already in GATE_STATUS_ORDER. Otherwise
    (BLOCKED or FOUNDER_APPROVAL), walk task_status_history backward for
    this task_id and return the most recent to_status that IS in
    GATE_STATUS_ORDER — the real gate this interrupt is sitting on top
    of. None only if a task has literally never entered any ladder gate
    (e.g. still BACKLOG)."""
```

TASK-017 worked example: `tasks.status = 'BLOCKED'` → walk back through
`task_status_history` → row 132's `from_status = 'IN_DEVELOPMENT'` → 
`effective_gate_status = 'IN_DEVELOPMENT'`. This is exactly what both
prior documents rendered by hand ("[CURRENT] Development — waiting,
paused"); this function makes it a deterministic, reusable computation
instead of a one-off sketch.

### 1.4 Gates completed — evidenced, not assumed

```python
def gates_completed(conn, task_id: int) -> list[str]:
    """DISTINCT to_status values (restricted to GATE_STATUS_ORDER) that
    this task has both ENTERED and since EXITED FORWARD — i.e. a later
    task_status_history row for this same task_id exists. A gate the task
    is currently sitting in (including one it's BLOCKED/FOUNDER_APPROVAL
    on top of) is not yet "completed." Never infers that an earlier
    ladder position was visited just because a later one was — see §1.1."""
```

SQL shape (task_id bound):

```sql
SELECT DISTINCT to_status
FROM task_status_history h1
WHERE task_id = ?
  AND to_status IN (<GATE_STATUS_ORDER>)
  AND EXISTS (
    SELECT 1 FROM task_status_history h2
    WHERE h2.task_id = h1.task_id AND h2.id > h1.id
  )
```

TASK-017: `ARCHITECTURE` (entered row 128, exited row 129) and
`RED_TEAM_REVIEW` (entered row 129, exited row 130) both qualify.
`IN_DEVELOPMENT` (entered row 130) does not — row 132 moves it to
`BLOCKED`, an interrupt, not a forward gate exit. **Gates completed = 2**
(`Architecture`, `Red Team Review`) — a real, defensible number, not an
assumed ladder index.

### 1.5 Gates remaining — structural, not retrospective

```python
def gates_remaining(effective_status: str | None) -> list[str]:
    """Every GATE_STATUS_ORDER entry strictly after effective_status, up
    to but excluding DONE — DONE is rendered as a separate completion
    marker (same convention STAGE_MAP already uses: DONE is shown within
    Release/Deployment, not a 7th stage). This direction IS safe to
    compute structurally, unlike §1.4: "what's ahead of here" does not
    depend on what was skipped behind it."""
```

TASK-017 (`effective_status = 'IN_DEVELOPMENT'`, index 6 of 13):
remaining = `Code Review, QA, Security Review, Ready to Release, Deployed`
(5 items), with `Done` shown as the finish line, not counted as a 6th
"remaining gate."

**No single "N / M" fraction is shown anywhere in this design.**
`gates_completed` and `gates_remaining` are reported as two separate,
independently-real facts (`"2 completed"`, `"5 remaining"`) rather than
combined into `2/7` — that fraction would silently assert a fixed total
of 7 gates applies to every task, which §1.1 already disproved for the
common case of tasks that skip ladder positions. This is a deliberate,
disclosed departure from the Founder's own illustrative example format
(`"Progress: 6/8 gates"`) — the spirit (a compact "how far along" signal)
is preserved; the specific fraction notation is dropped because it cannot
be made accurate for most real tasks in this database without inventing
a per-task-type "expected total gate count" the schema has no way to
express today. If the Founder wants the fraction notation specifically
(rather than the two-number form), that's a one-line rendering choice
Development/Design can make without an architecture change — the
underlying numbers are the same either way.

### 1.6 "Design review" and "CTO Conformance" — not new ladder gates

DEC-009's own 8-step milestone-review gate list (CTO architecture →
Design review → Red Team → Development → Code Review → QA → Security →
CTO final conformance) maps onto `GATE_STATUS_ORDER` as follows, verified
against TASK-017's real history (§5 below is the full walkthrough):

| DEC-009 gate | `tasks.status` ladder position | How it's recorded |
|---|---|---|
| CTO architecture | `ARCHITECTURE` | the status occupancy itself |
| Design review | *(none — see below)* | a `review_results` row, `reviewed_by_agent='design'` (or the literal agent name the `design` skill/Product agent runs under), recorded while status is still `ARCHITECTURE` or `RED_TEAM_REVIEW` |
| Red Team | `RED_TEAM_REVIEW` | the status occupancy, **and** `review_results` rows with `reviewed_by_agent='red-team'` |
| Development | `IN_DEVELOPMENT` | the status occupancy |
| Code Review | `CODE_REVIEW` | the status occupancy |
| QA | `QA` | the status occupancy |
| Security (focused) | `SECURITY_REVIEW`, or a `review_results` row with `review_type='security'` recorded during an earlier occupancy (TASK-017's own real precedent, see below) | either |
| CTO final conformance | *(none — see below)* | a `review_results` row, `reviewed_by_agent='cto'` |

**This is not a new problem invented for this milestone — TASK-017's own
real history already establishes the precedent.** Its Security review
(`review_results` id 48, `reviewed_by_agent='security'`) and all three
Red Team review rounds (ids 49–51) happened **while `tasks.status` stayed
at `RED_TEAM_REVIEW` the entire time** — the status never moved to a
dedicated "security-at-architecture-stage" value, because no such value
exists, and none is needed: multiple reviewer types can and do occur
within one gate occupancy, and the rendered history lists each inline
(exactly the "`[DONE] Architecture — 1 pass (after 1 Security CONCERNS, 2
Red Team REJECTs)`" line both prior documents already showed). "Design
review" and "CTO Conformance" follow the identical pattern: they are
**events within a gate's history, labeled by `reviewed_by_agent`**, not
new `tasks.status` values and not new lanes in the DONE/CURRENT/WAITING
model. No schema change, no new status enum value — confirmed against
real, evidenced precedent rather than assumed by analogy.

---

## Part 2 — Shared computed functions (`ops/db/derived_state.py`)

All additive to the existing file; no existing function is changed.
Every function below takes an open `sqlite3.Connection` (row_factory =
`sqlite3.Row`), matching every existing function in this module.

```python
def task_bounce_count(conn, task_id: int) -> int:
    """The prior document's §3.2 query, unchanged:
    COUNT(review_results WHERE result='reject') + COUNT(qa_results WHERE
    result='fail'), for this task_id."""

def task_is_stuck(conn, task_id: int, status: str,
                   threshold_days: int = STUCK_THRESHOLD_DAYS) -> tuple[bool, str | None]:
    """False immediately if status in ('BLOCKED', 'FOUNDER_APPROVAL') —
    both already have their own, better-labeled treatment (an interrupt
    banner / Founder-action-required flag); flagging them as 'stuck' too
    would be a redundant, confusing second signal for the same fact.
    Otherwise: last_event_at = MAX(created_at) across
    task_status_history, review_results, qa_results for this task_id (no
    row at all is itself stuck — a task with zero recorded activity ever
    since creation). is_stuck = (now - last_event_at) > threshold_days
    days. Returns (is_stuck, last_event_at)."""

def task_last_event(conn, task_id: int) -> dict | None:
    """The single most recent row (by created_at) across
    task_status_history / review_results / qa_results for this task,
    normalized to {"kind": "status_change"|"review"|"qa",
    "summary": str, "at": str}. None only for a task with zero history
    (shouldn't happen post-creation — task_status_history always gets a
    'created' row — but handled honestly rather than assumed away)."""

def task_cost_usd(conn, task_id: int) -> dict:
    """{"available": bool, "usd": float | None, "note": str}.
    count, total = SELECT COUNT(*), COALESCE(SUM(cost_usd),0)
                   FROM automation_events WHERE task_id = ?
    available = (count > 0). A real $0.00 (automation ran but a
    zero-cost event, e.g. a 'skipped' row) must not be conflated with
    'automation never touched this task' — the count, not just the sum,
    decides availability. note explains the honest-partial scope:
    'automation-poller cost only; Ask-Agent/Meeting/Chief-of-Staff
    invocation cost is not persisted until Milestone B ships.'"""

def task_progress_row(conn, task_id: int) -> dict:
    """The one shared row-builder. Composes: tasks + projects (LEFT
    JOIN), effective_gate_status(), gates_completed(),
    gates_remaining(), task_bounce_count(), task_is_stuck(),
    task_last_event(), task_cost_usd(), and a founder_action_required
    check (status == 'FOUNDER_APPROVAL' OR an approvals row for this
    task_id with decision IN ('pending','discuss')). Returns one plain
    dict — the single shared computation both generate_active_work.py
    (called once per active task) and generate_task.py (called once, for
    the page's own header/summary fields only — the rest of Task
    Detail's sections are additional queries scoped to a single task,
    not part of this shared function) render from. This is the literal
    'single shared computed function... not duplicated logic' the
    milestone brief requires, and is exactly what backs the Chief of
    Staff's own future state-digest use (chief_of_staff.py can call this
    directly, the same way it already composes derived_state.py's other
    digest helpers — no code change to chief_of_staff.py is part of this
    milestone, only the function existing where it can reach it)."""

def active_work_rows(conn) -> list[dict]:
    """SELECT id FROM tasks WHERE status != 'DONE' ORDER BY <see §3.5>,
    then task_progress_row(conn, id) for each. One query for the id list
    plus N calls to task_progress_row (each a handful of small,
    indexed, single-task-scoped queries) — same N+1-but-small-N shape
    render_stage_column() already uses today for task_progress_fraction()
    per pipeline card; not a new performance pattern, and the tasks
    table has a low enough row count (dozens, not thousands) that this
    is not a real concern at this project's actual scale."""

STUCK_THRESHOLD_DAYS = 3
```

### 2.1 The staleness threshold: N = 3 days, justified

- This project's own real, observed cadence: TASK-017's entire
  architecture-stage review cycle (Security CONCERNS → 2 Red Team
  REJECTs → PASS) completed in **under 3 hours** in one session
  (19:38→21:42, 2026-08-31). TASK-018 and TASK-019 both moved
  `BACKLOG → ARCHITECTURE` same-day. Three full days of zero recorded
  activity on a task that is not `BLOCKED`/`FOUNDER_APPROVAL` (i.e.
  nominally "in progress") is already **~25x** the observed real cycle
  time for active work in this system — a strong, non-noisy signal that
  something stalled, not that the work is merely unhurried.
- It avoids false-positives from ordinary session gaps: this is
  presently a single-operator system, not staffed 24/7 — a task idle
  overnight or over a weekend must not read as "stuck" the next morning.
  A 1-day threshold would false-positive constantly under normal use; 3
  days comfortably absorbs a multi-day gap between Founder/agent
  sessions while still catching genuine multi-day neglect.
- It matches this codebase's existing convention of a single, disclosed
  constant governing a threshold (`automation.MAX_AUTOMATION_SPEND_USD_PER_DAY`,
  `IDLE_TIMEOUT_S`) rather than a tuned-per-context value — one number,
  named, in one place (`derived_state.STUCK_THRESHOLD_DAYS`), used
  identically everywhere it's checked.
- This is a CTO-proposed default, explicitly flagged (per the milestone
  brief) as needing its own confirmation at the Design review gate below
  — not a number I'm treating as beyond challenge.

---

## Part 3 — Active Work dashboard

### 3.1 Route

`GET /active-work.html` — top-level, same shape as `/pipeline.html`,
`/reviews.html`, etc. (not a dynamic per-entity route). New file
`ops/control-center/generate_active_work.py`, `build_html(token=None)`
self-connecting via `dbutil.connect()`, matching `generate_pipeline.py`'s
own pattern exactly.

I recommend `/active-work.html` over alternatives (`/progress.html`,
`/dashboard.html`) because it's the exact name `ROADMAP.md`'s own
Founder-approved DEC-009 text already uses ("Active Work dashboard") —
no invented naming.

### 3.2 One row = `task_progress_row(conn, task_id)`

Every field in the milestone brief's required list is covered:

| Field | Source (Part 2 function / column) |
|---|---|
| Project / Phase / Milestone | `tasks.project_id → projects.name`, or `"—"` (single-implicit `projects` table today; no phase concept exists until Milestone D — honestly rendered `"—"`, never fabricated) |
| Current gate | `effective_gate_status()`, rendered via `STAGE_MAP`'s substate label (disambiguated: `READY_FOR_DEVELOPMENT`/`READY_TO_RELEASE` both map to substate `"Ready"` — prefix with major stage, `"Development · Ready"` / `"Release · Ready"`, when substate alone is `"Ready"`) |
| Current owner | `tasks.current_owner`, via `display_name()` |
| Gates completed / remaining | `gates_completed()` count / `gates_remaining()` list — two numbers, not a fraction (§1.5) |
| Rejection/bounce count | `task_bounce_count()` |
| Whether work is stuck | `task_is_stuck()`, threshold disclosed inline on hover/label: `"No activity in 4d (threshold: 3d)"` |
| Last important event | `task_last_event()` |
| Next expected action | `tasks.next_action`, or `"—"` if NULL/empty (real column, populated inconsistently today — not invented) |
| Founder action required | `status == 'FOUNDER_APPROVAL'` OR pending/discuss `approvals` row |
| Elapsed time | `tasks.created_at → now` (total) and current-gate-entry → now (from the `task_status_history` row that set `effective_gate_status`) |
| Cost/usage | `task_cost_usd()` — real `$X.XX` or `"not available"` |

Every row links to `/tasks/<id>.html` (Part 4) — no row ever links to a
page that doesn't exist, per the prior document's own explicit reasoning
for shipping these two pages together.

### 3.3 Layout

Following the milestone brief's own example format literally, one row
per task, rendered as a `.card` (matching `pipeline.html`'s existing
card visual language, not a new visual system):

```
TASK-018 — Product architecture completion review          [Founder needed: No]
Development · Ready to Release ... — 6 completed, 1 remaining
Owner: CTO · Bounces: 0 · Last event: 2026-08-31 22:25 (status change)
Next: — · Elapsed: 26m · Cost: not available
```

```
TASK-017 — Risk id=3 reduction milestone                    [Founder needed: No]
BLOCKED — paused by Founder directive (DEC-008), not a technical block
Development · In Development — 2 completed, 5 remaining
Owner: Chief of Staff · Bounces: 3 · Last event: 2026-08-31 22:00 (status change)
Next: — · Elapsed: 2h22m (0m since last event) · Cost: not available
```

### 3.4 Two-line company-wide summary (the Founder's own example format)

The milestone brief's example format (`"TASK-018 Product Architecture |
Progress: 6/8 gates | Current: CTO Conformance | Owner: CTO | Founder
needed: No"`) is a compact single-line variant of the same fields above.
I recommend the card layout in §3.3 over a literal single dense line for
legibility (this is exactly the kind of information-density judgment
call the Design review gate below should confirm or override) — the
underlying data is identical either way, so this is a rendering choice,
not an architecture one.

One reconciliation worth stating plainly: the brief's own example uses
`"Current: CTO Conformance"` as the current-gate label. Per §1.6, "CTO
Conformance" is an **event label**, not a `tasks.status` value — it
cannot be the literal value of `effective_gate_status()`. My design
renders `Current gate` as the real status-derived label (e.g.
`"Architecture"`) and surfaces `"CTO Conformance: PASS"` separately under
`Last important event` when that's genuinely the most recent thing that
happened. This gives the Founder the same information the example
conveyed, without inventing a 14th pseudo-status that doesn't exist in
the schema.

### 3.5 Sort order (flagged for Design review, not fixed here)

Recommended default: (1) Founder action required first, (2) stuck next,
(3) remainder by most-recently-updated — mirroring the urgency ordering
Founder Inbox already uses. This is a UX/prioritization judgment, not a
data-availability question — every field needed for any of these three
sort keys is already computed by `task_progress_row()`, so changing the
sort order later is a one-line change in `generate_active_work.py`, not
an architecture change.

---

## Part 4 — Task Detail page

### 4.1 Route

`GET /tasks/<id>.html` — dynamic, digit-bounded, matching the numeric-id
precedent `/meetings/<id>.html` already establishes (task ids, like
meeting ids, are pure integers — not free-text like agent names, which is
why `/agents/<name>.html` needed a character-class regex and this doesn't).

```python
# server.py — new constant, next to the existing regexes
TASK_DETAIL_ID_RE = re.compile(r"^\d{1,15}$")  # same 15-digit bound as
                                                 # APPROVAL_PATH_RE/MEETING_DECIDE_PATH_RE
```

```python
# server.py do_GET(), alongside the existing /meetings/<id>.html block
if path == "/active-work.html":
    self._send_html(200, generate_active_work.build_html(token=SESSION_TOKEN).encode("utf-8"))
    return
if path.startswith("/tasks/") and path.endswith(".html"):
    id_part = path[len("/tasks/"):-len(".html")]
    if not TASK_DETAIL_ID_RE.match(id_part):
        self._send_html(404, _error_page(404, "Not found", "No such task."))
        return
    conn = dbutil.connect()
    try:
        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(id_part),)).fetchone()
        if task_row is None:
            self._send_html(404, _error_page(404, "Not found", f"No task #{id_part}."))
            return
        self._send_html(200, generate_task.build_task_detail(conn, task_row, token=SESSION_TOKEN).encode("utf-8"))
    finally:
        conn.close()
    return
```

New file `ops/control-center/generate_task.py`,
`build_task_detail(conn, task_row, token=None)`, generated files under
`ops/control-center/tasks/<id>.html` — same shape as
`generate_agents.py:build_agent_detail()` / `generate_meetings.py:build_meeting_detail()`.
`main()` writes one file per task (`for t in conn.execute("SELECT * FROM tasks")`).

### 4.2 Sections

1. **Header** — title, status (with interrupt banner if
   `BLOCKED`/`FOUNDER_APPROVAL`), owner, elapsed time.
2. **Gate timeline** — `GATE_STATUS_ORDER`, each entry rendered
   `DONE` / `CURRENT` / `WAITING` per §1.3–1.5, `DONE` entries carrying
   their inline pass/reject history (§1.6's Design/CTO-Conformance/
   Security/Red-Team events included, labeled by `reviewed_by_agent`).
3. **Bounce count** — `task_bounce_count()`, plus the actual
   `review_results`/`qa_results` rows it's built from (not just the number).
4. **Status history** — full `task_status_history` for this task, most
   recent first (as both prior documents already designed).
5. **Handoffs** — `SELECT * FROM handoffs WHERE task_id = ?`, currently
   invisible anywhere else in the product.
6. **Code Review / QA / Security findings** — `review_results` and
   `qa_results` filtered to this task, labeled by `reviewed_by_agent`
   (not `review_type` alone, per §0/§1.6's known mislabeling).
7. **Founder decisions/approvals** —
   `SELECT * FROM approvals WHERE task_id = ?`, plus
   `SELECT d.* FROM decisions d JOIN approvals a ON a.id = d.founder_approval_id WHERE a.task_id = ?`
   (the only real join path from a task to a `decisions` row —
   `decisions` has no `task_id` column of its own).
8. **Associated risks** — `SELECT * FROM risks WHERE scope_type='task' AND scope_id = ?`
   — company-scoped risks (like `risks.id=3`) correctly do **not**
   appear here (see §5's TASK-017 walkthrough for why this is the right
   behavior, not a gap).
9. **Activity timeline** — `SELECT * FROM agent_activity WHERE task_id = ?`.
10. **Next expected action** — `tasks.next_action`, or `"—"`.
11. **Cost/usage** — `task_cost_usd()`.

---

## Part 5 — Acceptance test: TASK-017, rendered exactly

Queried directly against the live `operations.sqlite3` while writing this
document (not reconstructed from memory or the prior two documents' own
sketches, though the result matches them). This is what
`generate_task.build_task_detail()` produces for TASK-017 under the
design above.

**Real data used** (verified this session):
`task_status_history` ids 127–130, 132; `review_results` ids 48–51;
zero rows in `handoffs`, `approvals`, `agent_activity` for `task_id=17`;
`risks.id=3` is `scope_type='company'` (not task-scoped).

```
TASK-017 — Risk id=3 reduction milestone: reviewer zero-tool rollout +
self-immune Developer denylist

Status: BLOCKED — paused by Founder directive (DEC-008), 2026-08-31.
        Not a technical block; not acceptance that risks.id=3 is solved.
Owner: Chief of Staff (orchestrator)
Elapsed: ~2h22m since created (19:38) · 0m since last event (22:00)
Bounces: 3

Gates:
  [DONE]    Architecture        1 pass (2026-08-31)
  [DONE]    Red Team Review     1 pass — after 1 Security CONCERNS
                                 (recorded as reject, reviewed_by_agent=
                                 security) and 2 Red Team REJECTs
                                 (reviewed_by_agent=red-team; recorded
                                 with review_type='code', a known,
                                 disclosed labeling gap — see Part 0)
  [CURRENT] Development         waiting — paused mid-Development,
                                 Founder-directed (DEC-008), not reached
                                 Code Review
  [WAITING] Code Review
  [WAITING] QA
  [WAITING] Security Review
  [WAITING] Ready to Release
  (Deployed / Done: not reached)

Bounce count: 3
  review_results #48  security  reject  2026-08-31 20:03  "CONCERNS ..."
  review_results #49  red-team  reject  2026-08-31 20:12  "REJECT ..."
  review_results #50  red-team  reject  2026-08-31 20:26  "sys.exit()
                                                            ordering bug"

Status history (most recent first):
  2026-08-31 22:00  IN_DEVELOPMENT -> BLOCKED         by orchestrator
    "Founder directive ... paused mid-Development by explicit Founder
    prioritization decision, not a technical blocker ..."
  2026-08-31 21:42  RED_TEAM_REVIEW -> IN_DEVELOPMENT by orchestrator
    "Architecture PASSED after Security CONCERNS (fixed) and two Red
    Team REJECT rounds (fixed and re-verified) ..."
  2026-08-31 19:53  ARCHITECTURE -> RED_TEAM_REVIEW    by orchestrator
  2026-08-31 19:38  BACKLOG -> ARCHITECTURE            by orchestrator
  2026-08-31 19:38  (created) -> BACKLOG               by orchestrator

Handoffs: none recorded for this task. (The Development pass was
committed directly — fdaf253 — without an automated Code Review handoff,
since Code Review never ran on it. Not an error; nothing has reached
that gate yet.)

Code Review / QA / Security findings: see Gates above — all four
architecture-stage findings (#48-51) shown inline; none yet from Code
Review, QA, or a post-Development Security pass (not reached).

Founder decisions/approvals: none recorded against this task_id directly
(no approvals row, no linked decisions row). The Founder's pause
directive is recorded as a task_status_history note, not a formal
approvals-table decision — an honest gap in how the pause itself was
captured, not something this page invents a value for.

Associated risks: none. risks.id=3 — the company-scoped risk this whole
task exists to reduce — is correctly NOT listed here: its scope_type is
'company', not 'task', so it does not belong under this task's
task-scoped risk section. It remains visible only via a future
company-wide Risks register (Milestone C) or Agent Detail pages today.
This is the exact, correctly-honest behavior the prior v2 document's
§5.4 already anticipated, not a defect discovered now.

Activity timeline: no agent_activity rows recorded for this task.
(Real, not an error — this task's real work was captured entirely via
task_status_history and review_results, not agent_activity logging.)

Next expected action: — (tasks.next_action is NULL for this task; not
populated, rendered honestly rather than invented.)

Founder action required: No. (BLOCKED by Founder direction, not a
pending decision — no FOUNDER_APPROVAL status, no pending/discuss
approvals row.)

Cost: not available. (Zero automation_events rows exist for this task —
TASK-017's own reviewer_invocations table, which would carry this cost,
does not even exist in the live database yet, per the v2 document's
§1.3 finding. Not fabricated.)
```

**This renders coherently.** Every section has either real data or an
honest, specific "none"/"not available"/"—" — nothing is invented, and
the two known, pre-existing schema quirks (the `review_type` Red Team
mislabeling, the missing `reviewer_invocations` table) are surfaced as
disclosed facts on the page itself, not hidden. The design is done.

---

## Part 6 — Navigation

### 6.1 `layout.py`

```python
NAV_LINKS = [
    ("overview.html", "Overview"),
    ("active-work.html", "Active Work"),   # NEW — inserted here
    ("pipeline.html", "Pipeline"),
    ("agents.html", "Agents"),
    ("decisions.html", "Decisions"),
    ("meetings.html", "Meetings"),
    ("inbox.html", "Inbox"),
    ("reviews.html", "Reviews"),
    ("releases.html", "Releases"),
    ("automation.html", "Automation"),
]
```

Placed immediately after Overview: Overview is the broad company-health
snapshot; Active Work is the specific "what needs my attention, per
task" follow-on — the natural next click. `/tasks/<id>.html` is **not**
a nav-bar item, matching the existing precedent that neither
`/agents/<name>.html` nor `/meetings/<id>.html` are nav-bar items either
— reached only by clicking through from a list.

### 6.2 Dead-anchor fix — every file touched, named exactly

Every `pipeline.html#task-{id}` outbound link becomes `tasks/{id}.html`
(or `../tasks/{id}.html` from a depth-1 page, matching the existing
`layout.nav_html()` `depth` convention):

- `ops/control-center/generate_releases.py` — lines 52 and 75 (two links).
- `ops/control-center/generate_automation.py` — lines 132 and 162 (two links).
- `ops/control-center/generate_reviews.py` — lines 90 and 195 (two links).
- `ops/control-center/generate_pipeline.py` — a distinct, additional fix:
  today's pipeline cards (`render_needs_attention()`, `render_backlog()`,
  `render_stage_column()`) are **not links at all** — plain
  `<div id="task-{id}">` elements, not `<a href>`. This milestone makes
  them real links to `/tasks/{id}.html` (keeping the existing
  `id="task-{id}"` attribute for backward compatibility with any
  same-page anchor still in use, which is harmless to retain). This is
  the exact fix `ROADMAP.md`'s own text names: "Pipeline (PARTIAL →
  COMPLETE, once cards link out)."

**Explicitly not touched**: `ops/control-center/server.py` line 1172
(`redirect_to = f"/pipeline.html#task-{task_id}"`, inside
`reviewer_sync.py`'s task-review POST redirect) — this is part of the
paused TASK-017 feature, out of scope per this milestone's explicit
constraint not to touch TASK-017. Flagged here so it isn't silently
missed in a future pass, not fixed now.

---

## Part 7 — Gates for this milestone (TASK-019)

Per DEC-009: CTO architecture (this document) → Design review → Red Team
→ Development → Code Review → QA → focused Security review → CTO final
conformance.

### 7.1 What the Design review gate should specifically weigh in on

Named explicitly, so this gate isn't vague:

1. **Information density of the Active Work dashboard** (§3.3 vs. §3.4)
   — card-per-task vs. a denser single-line-per-task table; how many of
   the ~11 fields are shown by default vs. behind a click/expand, given
   the task count today (single digits of active tasks) vs. what it
   should still read well at (dozens).
2. **Sort order** (§3.5) — confirm or override the recommended
   Founder-action-required-first, then-stuck, then-recency ordering.
3. **Gate-lane visual legibility** on Task Detail — the DONE/CURRENT/
   WAITING states (§4.2 item 2) need a clear, non-ambiguous visual
   treatment distinct from the existing Pipeline kanban's stage columns,
   since this is a single-task vertical timeline, a different shape.
4. **The staleness/stuck visual treatment** — should read as
   informative, not alarmist, given `STUCK_THRESHOLD_DAYS=3` will fire
   routinely on ordinary session gaps for a single-operator system;
   confirm the proposed threshold (§2.1) itself, or propose a different one.
5. **Nav placement** (§6.1) — confirm "Active Work" belongs immediately
   after "Overview," or propose a different position.
6. **Consistency with the Founder-approved dark visual system**
   (`layout.py` CSS tokens, `ops/mockups/control-center-phase-0/Main.dc.html`)
   — no new visual language should be introduced; this is a check, not
   an open design brief.

### 7.2 The focused Security review

Per DEC-009's own framing ("scoped to newly introduced risk only") and
the milestone brief's own expectation: these are two **read-only** pages,
reusing the existing Founder session/CSRF gate exactly as every other
GET route does, with **zero new write routes**. The concrete things
Security should verify, not skip past:

- No new HTTP write route is introduced anywhere in this design (true by
  construction — `/active-work.html` and `/tasks/<id>.html` are GET-only,
  matching every prior detail page).
- `TASK_DETAIL_ID_RE` correctly rejects non-numeric/oversized input
  before any query executes (same discipline as `APPROVAL_PATH_RE`).
- No task-scoped data rendered on either page is more sensitive than
  what's already rendered elsewhere in the Control Center today (task
  titles, statuses, review findings, and handoffs are all already
  Founder-visible via `pipeline.html`/`reviews.html`/individual Agent
  Detail pages — this milestone changes *reachability*, not *what data
  exists in the product*).
- The `dbutil.connect()` read-only (`mode=ro`) connection is used
  throughout, same as every other generator — no code path in either new
  file opens a writable connection.

I expect this review to conclude these pages introduce no new material
risk, for the reasons above — but the gate runs regardless, producing an
explicit "reviewed, no new risk found" record rather than being skipped,
per the milestone brief's own instruction.

---

## Part 8 — What this design explicitly does not add

No `task_gates` table, no second status enum, no new write route, no
change to the Founder session/CSRF gate, no `phases` table (Milestone
D's job), no `agent_runs.cost_usd` column (Milestone B's job), no
company-wide Risks register (Milestone C's job). The one schema
recommendation already on record from the prior documents
(`review_type` widening) remains a recommendation, not implemented here
— this milestone's design works correctly without it, using
`reviewed_by_agent`-based labeling throughout, exactly as demonstrated in
Part 5's real TASK-017 render.

---

## Part 9 — Files this milestone touches (complete list)

**New:**
- `ops/control-center/generate_active_work.py`
- `ops/control-center/generate_task.py` (writes `ops/control-center/tasks/<id>.html` per task)

**Modified:**
- `ops/db/derived_state.py` — `GATE_STATUS_ORDER`, `STUCK_THRESHOLD_DAYS`,
  `effective_gate_status()`, `gates_completed()`, `gates_remaining()`,
  `task_bounce_count()`, `task_is_stuck()`, `task_last_event()`,
  `task_cost_usd()`, `task_progress_row()`, `active_work_rows()` — all additive.
- `ops/control-center/layout.py` — one new `NAV_LINKS` entry.
- `ops/control-center/server.py` — `TASK_DETAIL_ID_RE`, two new GET
  routes, two new `import` lines (`generate_active_work`, `generate_task`).
- `ops/control-center/generate_pipeline.py` — cards become real links.
- `ops/control-center/generate_releases.py` — 2 links redirected.
- `ops/control-center/generate_automation.py` — 2 links redirected.
- `ops/control-center/generate_reviews.py` — 2 links redirected.

**Explicitly not touched:** `ops/control-center/reviewer_sync.py`,
`ops/control-center/server.py`'s task-review redirect (line 1172) — both
part of paused TASK-017, out of scope.
