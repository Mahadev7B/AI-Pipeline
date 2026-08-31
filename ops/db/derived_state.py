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


# ---- Phase 3A Part A (TASK-015): Chief of Staff state-digest helpers ----
# Read-only, each capped by its own `limit=` — deliberate, justified
# content selection ("recent + open + actionable state," never "every row
# ever written"), not an oversight. Composed by
# ops/control-center/chief_of_staff.py into the bounded state digest
# assembled fresh before every Founder message — see
# ops/reviews/cto-phase3a-architecture.md §A.2. Same DRY rule as every
# other function in this module: the single, shared implementation, not a
# second hand-typed copy of company-state logic living inside
# chief_of_staff.py itself. NOTE: automation_status_digest() (Part B, the
# automation poller/automation_events/automation_state tables) is
# deliberately NOT implemented here yet — those tables don't exist until
# Phase 3A Part B ships; adding it now would read tables that don't exist.


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
