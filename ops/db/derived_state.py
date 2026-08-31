"""ops/db/derived_state.py — the single, shared implementation of every
formula documented in DATA_MODEL.md, "Deterministic derived state".

Imported by both ops/db/report.py and ops/control-center/generate_overview.py
so Company Health, agent status, and task progress are computed identically
everywhere they're shown — never a second hand-typed copy that could drift.
See ops/ARCHITECTURE.md, "Derived UI state must be deterministic."

Read-only. Zero third-party dependencies. Every function takes an open
sqlite3.Connection (with row_factory = sqlite3.Row) and a scalar/id — none
of them open a connection themselves, so callers control the database path
(including OPSDB_PATH-based test isolation, see ops/db/README.md).
"""
from __future__ import annotations

import sqlite3

_DISPLAY_NAMES = {"orchestrator": "Chief of Staff"}


def display_name(machine_key: str) -> str:
    """Founder-facing label for an agents.name value. Out of scope for
    every agent except 'orchestrator' by explicit Founder instruction —
    do not add entries for the other 13; the default fallback (the key
    itself, unchanged) is correct for all of them. Never apply this to a
    stored DB value, a query predicate, a thread_id, or historical
    message/decision/review body text — only to a label rendered for the
    Founder to read. See ops/reviews/cto-chief-of-staff-rename.md."""
    return _DISPLAY_NAMES.get(machine_key, machine_key)


def company_health(conn: sqlite3.Connection) -> tuple[str, str]:
    high_risks = conn.execute(
        "SELECT COUNT(*) FROM risks WHERE status = 'open' AND severity = 'high'"
    ).fetchone()[0]
    blocked_tasks = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status = 'BLOCKED'"
    ).fetchone()[0]
    if high_risks == 0 and blocked_tasks <= 1:
        label = "Good"
    elif high_risks <= 1 or (2 <= blocked_tasks <= 3):
        label = "Fair"
    else:
        label = "Poor"
    detail = f"{blocked_tasks} task(s) blocked, {high_risks} high-severity open risk(s)"
    return label, detail


def scope_label(scope_type: str, scope_id: int | None) -> str:
    """'company' scope has no scope_id by schema design (see DATA_MODEL.md) —
    render that as bare 'company', not the confusing 'company:None'."""
    return scope_type if scope_id is None else f"{scope_type}:{scope_id}"


def agent_status_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Ordered by display_name(a.name), not the raw machine key — callers
    render display_name() at render time, so sorting must happen here on
    the same displayed label or the sort order and the labels disagree
    (e.g. "Chief of Staff" landing in orchestrator's alphabetical slot
    instead of between "ceo" and "code-review"). See
    ops/reviews/code-review-chief-of-staff-rename.md."""
    rows = conn.execute(
        """
        SELECT a.name, r.status, r.scope_type, r.scope_id, r.current_activity
        FROM agents a
        LEFT JOIN agent_runs r ON r.agent_id = a.id AND r.ended_at IS NULL
        """
    ).fetchall()
    return sorted(rows, key=lambda row: display_name(row["name"]).lower())


def task_progress_fraction(conn: sqlite3.Connection, task_id: int) -> tuple[float, float] | None:
    """Returns (done_weight, total_weight), or None if the task has no
    steps yet — "not broken into steps" is the honest answer then, not 0%."""
    row = conn.execute(
        "SELECT SUM(weight) AS total, "
        "SUM(CASE WHEN status='done' THEN weight ELSE 0 END) AS done "
        "FROM task_steps WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if not row or row["total"] in (None, 0):
        return None
    return (row["done"], row["total"])


def task_progress_pct(conn: sqlite3.Connection, task_id: int) -> str:
    """String form used by report.py: 'not broken into steps' or 'NN%'."""
    fraction = task_progress_fraction(conn, task_id)
    if fraction is None:
        return "not broken into steps"
    done, total = fraction
    return f"{round(100 * done / total)}%"


# Six major stages, in pipeline order, per AGENT_STATUS.md. BLOCKED and
# FOUNDER_APPROVAL are deliberately absent — they are interrupt states,
# never a pipeline column (see AGENT_STATUS.md, "Interrupt states").
PIPELINE_STAGES = ["Product", "Design", "Architecture", "Development", "Review", "Release"]

# tasks.status -> (major stage, substate). Mirrors AGENT_STATUS.md exactly;
# change AGENT_STATUS.md first if this ever needs to change, not the other
# way around.
STAGE_MAP: dict[str, tuple[str, str]] = {
    "PLANNING": ("Product", "Requirements"),
    "MOCKUP": ("Design", "Mockup"),
    "MOCKUP_REVIEW": ("Design", "Mockup Review"),
    "ARCHITECTURE": ("Architecture", "Architecture"),
    "RED_TEAM_REVIEW": ("Architecture", "Red Team Review"),
    "READY_FOR_DEVELOPMENT": ("Development", "Ready"),
    "IN_DEVELOPMENT": ("Development", "In Development"),
    "CODE_REVIEW": ("Review", "Code Review"),
    "QA": ("Review", "QA"),
    "SECURITY_REVIEW": ("Review", "Security"),
    "READY_TO_RELEASE": ("Release", "Ready"),
    "DEPLOYED": ("Release", "Deployment"),
    "DONE": ("Release", "Deployment"),  # shown as done-within-deployment, not a 7th stage
}


def stage_and_substate(status: str) -> tuple[str, str] | None:
    """None for BACKLOG/BLOCKED/FOUNDER_APPROVAL — none of these are a
    pipeline column; callers render them separately (a Backlog tray, a
    Needs Attention callout)."""
    return STAGE_MAP.get(status)


# ---- Milestone A (TASK-019): the gate model ----
# See ops/reviews/cto-milestone-a-architecture.md Parts 1-2 and Red
# Team's fix (ops/reviews/red-team-milestone-a-review.md §1.4) for the
# full reasoning. Backs both /active-work.html and /tasks/<id>.html —
# the "single shared computed function" the milestone brief requires,
# not duplicated logic between the two pages.

# The same 13 tasks.status values STAGE_MAP already maps, in the same
# order. BACKLOG, BLOCKED, FOUNDER_APPROVAL deliberately excluded —
# consistent with STAGE_MAP's own exclusion of them as interrupt/entry
# states, not pipeline columns.
GATE_STATUS_ORDER = [
    "PLANNING", "MOCKUP", "MOCKUP_REVIEW", "ARCHITECTURE", "RED_TEAM_REVIEW",
    "READY_FOR_DEVELOPMENT", "IN_DEVELOPMENT", "CODE_REVIEW", "QA",
    "SECURITY_REVIEW", "READY_TO_RELEASE", "DEPLOYED", "DONE",
]

_GATE_PLACEHOLDERS = ",".join("?" * len(GATE_STATUS_ORDER))

# See §2.1 of the architecture doc for the full justification (this
# project's own observed cycle time is ~hours, not days; a single-operator
# system must not false-positive "stuck" on an ordinary overnight/weekend
# gap). One named constant, used everywhere this threshold is checked.
STUCK_THRESHOLD_DAYS = 3


def gate_display_label(status: str | None) -> str:
    """Founder-facing label for a GATE_STATUS_ORDER value — STAGE_MAP's
    own substate, prefixed with the major stage only when the substate
    alone is the ambiguous 'Ready' (READY_FOR_DEVELOPMENT and
    READY_TO_RELEASE both have substate 'Ready' — see architecture doc
    §3.2). '—' for None (task has never entered any gate)."""
    if status is None:
        return "—"
    mapped = STAGE_MAP.get(status)
    if mapped is None:
        return status
    stage, substate = mapped
    if substate == "Ready":
        return f"{stage} · {substate}"
    return substate


def effective_gate_status(conn: sqlite3.Connection, task_id: int, current_status: str) -> str | None:
    """current_status if it's already in GATE_STATUS_ORDER. Otherwise
    (BLOCKED or FOUNDER_APPROVAL, or BACKLOG which has never entered the
    ladder at all), walk task_status_history backward for this task_id
    and return the most recent to_status that IS in GATE_STATUS_ORDER —
    the real gate this interrupt is sitting on top of. None only if a
    task has literally never entered any ladder gate (e.g. still
    BACKLOG)."""
    if current_status in GATE_STATUS_ORDER:
        return current_status
    row = conn.execute(
        f"SELECT to_status FROM task_status_history "
        f"WHERE task_id = ? AND to_status IN ({_GATE_PLACEHOLDERS}) "
        f"ORDER BY id DESC LIMIT 1",
        (task_id, *GATE_STATUS_ORDER),
    ).fetchone()
    return row["to_status"] if row else None


def gates_completed(conn: sqlite3.Connection, task_id: int) -> list[str]:
    """DISTINCT to_status values (restricted to GATE_STATUS_ORDER) that
    this task has both ENTERED and since EXITED FORWARD — i.e. a LATER
    task_status_history row for this same task_id exists whose OWN
    to_status is also a real ladder position (GATE_STATUS_ORDER). A gate
    the task is currently sitting in — including one it's
    BLOCKED/FOUNDER_APPROVAL on top of — is not yet "completed": moving
    to an interrupt state is not a forward gate exit, only a pause on top
    of the gate the task is still effectively at (see
    effective_gate_status()). Never infers that an earlier ladder
    position was visited just because a later one was.

    Correction to the architecture doc's literal SQL sketch (ops/reviews/
    cto-milestone-a-architecture.md §1.4): that snippet's EXISTS subquery
    checked only "does ANY later row exist," which — followed literally
    — would have counted a task moving BLOCKED as having "completed" the
    gate it was actually just paused on, directly contradicting the same
    document's own §1.4 prose ("IN_DEVELOPMENT... does not [qualify] —
    row 132 moves it to BLOCKED, an interrupt, not a forward gate exit")
    and its Part 5 TASK-17 worked acceptance example. Reproduced live
    against TASK-17's real history while implementing this milestone;
    fixed here to require the later row's own to_status to be a real
    ladder position, matching the documented intent and worked example
    exactly. Returned in GATE_STATUS_ORDER order (stable rendering), not
    insertion order."""
    rows = conn.execute(
        f"""
        SELECT DISTINCT h1.to_status
        FROM task_status_history h1
        WHERE h1.task_id = ?
          AND h1.to_status IN ({_GATE_PLACEHOLDERS})
          AND EXISTS (
            SELECT 1 FROM task_status_history h2
            WHERE h2.task_id = h1.task_id AND h2.id > h1.id
              AND h2.to_status IN ({_GATE_PLACEHOLDERS})
          )
        """,
        (task_id, *GATE_STATUS_ORDER, *GATE_STATUS_ORDER),
    ).fetchall()
    completed_set = {r["to_status"] for r in rows}
    return [s for s in GATE_STATUS_ORDER if s in completed_set]


def gates_remaining(effective_status: str | None, completed: list[str]) -> list[str]:
    """Every GATE_STATUS_ORDER entry strictly after effective_status, up
    to but excluding DONE (DONE is a completion marker, not a 6th/7th
    "remaining gate") — MINUS any entry already present in `completed`
    (the same list gates_completed() returned for this task), regardless
    of that entry's position relative to effective_status.

    Red Team's required fix (ops/reviews/red-team-milestone-a-review.md
    §1.4): this makes "remaining" a high-water-mark quantity. Once a gate
    has been evidenced forward-exited even once, it is never again
    reported as both completed and remaining on the same render, even
    when a later backward status transition (a REJECT-triggered rework
    loop, or a status like MOCKUP_REVIEW used as an ad hoc Design-review
    proxy) moves effective_status to a ladder position earlier than that
    gate's own position. Reproduced and verified against TASK-19's real
    ARCHITECTURE->MOCKUP_REVIEW history and TASK-6's real
    SECURITY_REVIEW->CODE_REVIEW bounce — see this module's test script
    for both cases. Requires the caller to compute gates_completed()
    first and pass its result in — task_progress_row() already calls
    both in that order, so this costs zero new queries."""
    completed_set = set(completed)
    start = -1 if effective_status is None else GATE_STATUS_ORDER.index(effective_status)
    return [s for s in GATE_STATUS_ORDER[start + 1:]
            if s != "DONE" and s not in completed_set]


def task_bounce_count(conn: sqlite3.Connection, task_id: int) -> int:
    """COUNT(review_results WHERE result='reject') + COUNT(qa_results
    WHERE result='fail'), for this task_id."""
    reject_count = conn.execute(
        "SELECT COUNT(*) FROM review_results WHERE task_id = ? AND result = 'reject'",
        (task_id,),
    ).fetchone()[0]
    fail_count = conn.execute(
        "SELECT COUNT(*) FROM qa_results WHERE task_id = ? AND result = 'fail'",
        (task_id,),
    ).fetchone()[0]
    return reject_count + fail_count


def interrupt_reason(conn: sqlite3.Connection, task_id: int, status: str) -> str | None:
    """The note recorded on the task_status_history row that most
    recently moved this task INTO its current interrupt state (BLOCKED /
    FOUNDER_APPROVAL) — the real, already-written explanation of why,
    never an invented one. None if status isn't currently an interrupt
    state, or (should not happen post-transition, but handled honestly
    rather than assumed) no matching row exists."""
    if status not in ("BLOCKED", "FOUNDER_APPROVAL"):
        return None
    row = conn.execute(
        "SELECT note FROM task_status_history WHERE task_id = ? AND to_status = ? "
        "ORDER BY id DESC LIMIT 1",
        (task_id, status),
    ).fetchone()
    return row["note"] if row else None


def task_is_stuck(conn: sqlite3.Connection, task_id: int, status: str,
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
    if status in ("BLOCKED", "FOUNDER_APPROVAL"):
        return (False, None)
    row = conn.execute(
        """
        SELECT MAX(at) AS last_at FROM (
          SELECT MAX(changed_at) AS at FROM task_status_history WHERE task_id = ?
          UNION ALL
          SELECT MAX(created_at) AS at FROM review_results WHERE task_id = ?
          UNION ALL
          SELECT MAX(created_at) AS at FROM qa_results WHERE task_id = ?
        )
        """,
        (task_id, task_id, task_id),
    ).fetchone()
    last_at = row["last_at"] if row else None
    if last_at is None:
        return (True, None)
    days = conn.execute("SELECT julianday('now') - julianday(?)", (last_at,)).fetchone()[0]
    is_stuck = bool(days is not None and days > threshold_days)
    return (is_stuck, last_at)


def task_last_event(conn: sqlite3.Connection, task_id: int) -> dict | None:
    """The single most recent row (by created_at/changed_at) across
    task_status_history / review_results / qa_results for this task,
    normalized to {"kind": "status_change"|"review"|"qa",
    "summary": str, "at": str}. None only for a task with zero history
    (shouldn't happen post-creation — task_status_history always gets a
    'created' row — but handled honestly rather than assumed away)."""
    row = conn.execute(
        """
        SELECT kind, summary, at FROM (
          SELECT 'status_change' AS kind,
                 (COALESCE(from_status, '(created)') || ' -> ' || to_status) AS summary,
                 changed_at AS at
          FROM task_status_history WHERE task_id = ?
          UNION ALL
          SELECT 'review' AS kind,
                 (review_type || ' review, ' || reviewed_by_agent || ': ' || result) AS summary,
                 created_at AS at
          FROM review_results WHERE task_id = ?
          UNION ALL
          SELECT 'qa' AS kind,
                 ('QA, ' || tested_by_agent || ': ' || result) AS summary,
                 created_at AS at
          FROM qa_results WHERE task_id = ?
        )
        ORDER BY at DESC
        LIMIT 1
        """,
        (task_id, task_id, task_id),
    ).fetchone()
    if row is None or row["at"] is None:
        return None
    return {"kind": row["kind"], "summary": row["summary"], "at": row["at"]}


def task_cost_usd(conn: sqlite3.Connection, task_id: int) -> dict:
    """{"available": bool, "usd": float | None, "note": str}.
    A real $0.00 (automation ran but a zero-cost event, e.g. a 'skipped'
    row) must not be conflated with 'automation never touched this task'
    — the count, not just the sum, decides availability."""
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS total "
        "FROM automation_events WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    available = bool(row["n"])
    return {
        "available": available,
        "usd": float(row["total"]) if available else None,
        "note": ("automation-poller cost only; Ask-Agent/Meeting/Chief-of-Staff "
                 "invocation cost is not persisted until Milestone B ships."),
    }


def _format_duration_days(days: float) -> str:
    total_minutes = int(round(days * 24 * 60))
    if total_minutes < 1:
        return "0m"
    if total_minutes < 60:
        return f"{total_minutes}m"
    hours, minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    d, hours = divmod(hours, 24)
    return f"{d}d{hours}h"


def elapsed_since(conn: sqlite3.Connection, since_iso: str | None) -> str:
    """Human-readable elapsed time from an ISO timestamp to now, computed
    via SQLite's julianday() (avoids Python ISO-parsing edge cases across
    the timestamp formats different tables use). '—' if since_iso is
    None or in the future (a clock-skew/data artifact, not a real
    duration to display)."""
    if not since_iso:
        return "—"
    days = conn.execute("SELECT julianday('now') - julianday(?)", (since_iso,)).fetchone()[0]
    if days is None or days < 0:
        return "—"
    return _format_duration_days(days)


def task_progress_row(conn: sqlite3.Connection, task_id: int) -> dict | None:
    """The one shared row-builder. Composes: tasks + projects (LEFT
    JOIN), effective_gate_status(), gates_completed(), gates_remaining(),
    task_bounce_count(), task_is_stuck(), task_last_event(),
    task_cost_usd(), and a founder_action_required check (status ==
    'FOUNDER_APPROVAL' OR an approvals row for this task_id with
    decision IN ('pending','discuss')). Returns one plain dict — the
    single shared computation both generate_active_work.py (called once
    per active task) and generate_task.py (called once, for the page's
    own header/summary fields only) render from. None if task_id does
    not exist."""
    task = conn.execute(
        "SELECT t.*, p.name AS project_name FROM tasks t "
        "LEFT JOIN projects p ON p.id = t.project_id WHERE t.id = ?",
        (task_id,),
    ).fetchone()
    if task is None:
        return None

    status = task["status"]
    effective_status = effective_gate_status(conn, task_id, status)
    completed = gates_completed(conn, task_id)
    remaining = gates_remaining(effective_status, completed)
    bounces = task_bounce_count(conn, task_id)
    is_stuck, stuck_last_event_at = task_is_stuck(conn, task_id, status)
    last_event = task_last_event(conn, task_id)
    cost = task_cost_usd(conn, task_id)

    gate_entered_at = None
    if effective_status is not None:
        gate_row = conn.execute(
            "SELECT changed_at FROM task_status_history WHERE task_id = ? AND to_status = ? "
            "ORDER BY id DESC LIMIT 1",
            (task_id, effective_status),
        ).fetchone()
        gate_entered_at = gate_row["changed_at"] if gate_row else None

    pending_approval = conn.execute(
        "SELECT 1 FROM approvals WHERE task_id = ? AND decision IN ('pending','discuss') LIMIT 1",
        (task_id,),
    ).fetchone()
    founder_action_required = (status == "FOUNDER_APPROVAL") or (pending_approval is not None)

    return {
        "id": task["id"],
        "title": task["title"],
        "status": status,
        "project_name": task["project_name"],
        "current_owner": task["current_owner"],
        "effective_gate_status": effective_status,
        "gates_completed": completed,
        "gates_remaining": remaining,
        "gate_entered_at": gate_entered_at,
        "bounce_count": bounces,
        "is_stuck": is_stuck,
        "stuck_last_event_at": stuck_last_event_at,
        "last_event": last_event,
        "next_action": task["next_action"],
        "founder_action_required": founder_action_required,
        "created_at": task["created_at"],
        "cost": cost,
    }


def active_work_rows(conn: sqlite3.Connection) -> list[dict]:
    """SELECT id FROM tasks WHERE status != 'DONE' ORDER BY id, then
    task_progress_row(conn, id) for each — one query for the id list plus
    N calls to task_progress_row (each a handful of small, indexed,
    single-task-scoped queries), same N+1-but-small-N shape
    render_stage_column() already uses today for task_progress_fraction()
    per pipeline card. Sort order for display is a rendering choice made
    by the caller (generate_active_work.py), not by this function."""
    ids = [r["id"] for r in conn.execute("SELECT id FROM tasks WHERE status != 'DONE' ORDER BY id").fetchall()]
    return [row for row in (task_progress_row(conn, i) for i in ids) if row is not None]


# ---- Phase 3A Part A (TASK-015): Chief of Staff state-digest helpers ----
# Read-only, each capped by its own `limit=` — deliberate, justified
# content selection ("recent + open + actionable state," never "every row
# ever written"), not an oversight. Composed by
# ops/control-center/chief_of_staff.py into the bounded state digest
# assembled fresh before every Founder message — see
# ops/reviews/cto-phase3a-architecture.md §A.2. Same DRY rule as every
# other function in this module: the single, shared implementation, not a
# second hand-typed copy of company-state logic living inside
# chief_of_staff.py itself. automation_status_digest() (Part B, the
# automation poller/automation_events/automation_state tables) is defined
# further down, once Part A's own state-digest helpers end.


def open_risks_digest(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """Open risks first, then most-recently-changed (mitigated/resolved)
    ones — id/title/severity/status/mitigation. `resolved_at` is the only
    "last changed" signal this table has (no updated_at column); for a
    still-open risk that's always NULL, so COALESCE falls back to
    created_at."""
    return conn.execute(
        """
        SELECT id, title, severity, status, mitigation
        FROM risks
        ORDER BY (status = 'open') DESC, COALESCE(resolved_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def active_tasks_digest(conn: sqlite3.Connection, limit: int = 15) -> list[sqlite3.Row]:
    """Tasks not in DONE, most-recently-updated first — id/title/status/
    current_owner/blockers."""
    return conn.execute(
        """
        SELECT id, title, status, current_owner, blockers
        FROM tasks
        WHERE status != 'DONE'
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def pending_approvals_digest(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """decision IN ('pending','discuss') — the real, not-yet-decided
    Founder approval queue."""
    return conn.execute(
        """
        SELECT id, task_id, request, requested_by_agent, decision, created_at
        FROM approvals
        WHERE decision IN ('pending', 'discuss')
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def recent_decisions_digest(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, title, decision, recommending_agent, created_at
        FROM decisions
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def recent_status_transitions_digest(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, task_id, from_status, to_status, changed_by_agent, changed_at, note
        FROM task_status_history
        ORDER BY changed_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def recent_review_qa_digest(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """Code/security review results AND QA results, merged and ordered by
    real recency together (a single UNION ALL query, `LIMIT` applied to
    the combined result — not `limit` from each table separately, which
    would silently double the intended cap)."""
    return conn.execute(
        """
        SELECT 'review' AS kind, id, task_id, review_type AS subtype,
               reviewed_by_agent AS by_agent, result, created_at
        FROM review_results
        UNION ALL
        SELECT 'qa' AS kind, id, task_id, NULL AS subtype,
               tested_by_agent AS by_agent, result, created_at
        FROM qa_results
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def recent_deployments_digest(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, task_id, version, environment, deployed_by_agent, deployed_at
        FROM deployments
        ORDER BY deployed_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


# ---- Phase 3A Part B (TASK-015): automation status digest ----
# §B.12: "/automation.html and the Chief of Staff's state digest read the
# SAME query" — this is that one, shared query. Not implemented until Part
# B ships (Part A's own version of this file explicitly left this out,
# since automation_events/automation_state didn't exist yet).

AUTOMATION_RECENT_TERMINAL_LIMIT = 10


def automation_status_digest(conn: sqlite3.Connection) -> dict:
    """Reads automation_state (the kill-switch) + every automation_events
    row currently status='running' + the most recent N terminal
    (completed/failed/skipped) ones, joined to tasks for display. Returns
    a plain dict — {"enabled": bool, "changed_by": str|None,
    "reason": str|None, "changed_at": str|None, "running": [rows],
    "recent_terminal": [rows], "spend_today_usd": float,
    "spend_ceiling_usd": float} — so both /automation.html
    (generate_automation.py) and the Chief of Staff's own digest render
    from one shared computation, never two hand-typed copies of the same
    fact (ops/ARCHITECTURE.md, "Derived UI state must be deterministic").

    `spend_today_usd` mirrors automation.py's own §B.6 spend-guard query
    exactly (SUM(cost_usd) for rows started today) — the same number the
    guard itself enforces, not a second, possibly-inconsistent estimate;
    this module does not import automation.py's own
    MAX_AUTOMATION_SPEND_USD_PER_DAY constant (avoiding a
    control-center -> db import direction this project's layering doesn't
    otherwise have), so the ceiling is passed back as a plain float
    literal here and callers that need the live constant read it from
    automation.py directly."""
    state_row = conn.execute(
        "SELECT enabled, changed_by, reason, changed_at FROM automation_state WHERE id = 1"
    ).fetchone()

    running = conn.execute(
        """
        SELECT ae.id, ae.task_id, ae.started_at, ae.trigger_status_history_id,
               t.title AS task_title
        FROM automation_events ae
        JOIN tasks t ON t.id = ae.task_id
        WHERE ae.status = 'running'
        ORDER BY ae.started_at
        """
    ).fetchall()

    recent_terminal = conn.execute(
        """
        SELECT ae.id, ae.task_id, ae.status, ae.outcome, ae.skip_reason, ae.cost_usd,
               ae.truncated, ae.started_at, ae.ended_at, ae.review_result_id,
               t.title AS task_title
        FROM automation_events ae
        JOIN tasks t ON t.id = ae.task_id
        WHERE ae.status != 'running'
        ORDER BY ae.started_at DESC, ae.id DESC
        LIMIT ?
        """,
        (AUTOMATION_RECENT_TERMINAL_LIMIT,),
    ).fetchall()

    today = conn.execute("SELECT strftime('%Y-%m-%d', 'now')").fetchone()[0]
    spend_today = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM automation_events WHERE started_at LIKE ?",
        (today + "%",),
    ).fetchone()[0]

    return {
        "enabled": bool(state_row["enabled"]) if state_row else False,
        "changed_by": state_row["changed_by"] if state_row else None,
        "reason": state_row["reason"] if state_row else None,
        "changed_at": state_row["changed_at"] if state_row else None,
        "running": running,
        "recent_terminal": recent_terminal,
        "spend_today_usd": float(spend_today),
    }


def release_readiness_gap(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Milestone 2B5 (TASK-014): tasks whose status is READY_TO_RELEASE,
    DEPLOYED, or DONE but that have no matching row in `deployments` at
    all. A computed fact from two real columns (tasks.status,
    deployments.task_id) — same category as company_health()/STAGE_MAP,
    not invented structure. This function only computes the list; it is
    NOT an assertion that every such task was expected to carry a
    deployments row (Red Team's Milestone 2B5 review, blocking finding —
    see ops/reviews/cto-milestone2b5-architecture.md, Decision 3). Callers
    must present this as a neutral data observation, never as a
    process-discipline failure claim."""
    return conn.execute(
        """
        SELECT id, title, status
        FROM tasks
        WHERE status IN ('READY_TO_RELEASE', 'DEPLOYED', 'DONE')
          AND NOT EXISTS (SELECT 1 FROM deployments d WHERE d.task_id = tasks.id)
        ORDER BY id
        """
    ).fetchall()
