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
    """to_status values (restricted to GATE_STATUS_ORDER) the task has
    GENUINELY MOVED PAST — evaluated from each gate's MOST RECENT entry,
    never an earlier one. A gate counts as completed iff, after the last
    task_status_history row that entered it (MAX(id) grouped by
    to_status), a LATER row for this same task_id exists whose OWN
    to_status is also a real ladder position (GATE_STATUS_ORDER). Two
    things this rules out, both required to stay honest:

    1. A gate the task is currently sitting in — including one it's
       BLOCKED/FOUNDER_APPROVAL on top of — is not "completed": moving
       to an interrupt state is not a forward gate exit, only a pause on
       top of the gate the task is still effectively at (see
       effective_gate_status()). No later row with a ladder-position
       to_status exists yet, so the EXISTS check correctly returns
       false. This part was already correct as of Red Team's original
       review.

    2. A gate the task EXITED and later RE-ENTERED (a reject/resubmit
       loop landing back in the identical gate — e.g. Code Review
       REJECT -> IN_DEVELOPMENT -> resubmit -> Code Review again) is not
       "completed" merely because some EARLIER visit to that gate was
       once forward-exited. Grouping by MAX(id) per to_status before
       running the EXISTS check means only the gate's LATEST entry is
       ever evaluated — so if that latest entry is the task's current,
       unexited position, the gate reports as not-completed regardless
       of what an earlier round of the same gate did. This generalizes
       to any number of bounces through the same gate (see TASK-017's
       real three-round Code Review history) and to bouncing through two
       different gates and returning to both — each gate is judged
       solely by what happened after its own most recent entry.

    Bug history on this exact function, in order:
      - Architecture doc's original SQL sketch (ops/reviews/
        cto-milestone-a-architecture.md §1.4) checked only "does ANY
        later row exist" with no to_status restriction at all, which
        would have counted a move to BLOCKED as a forward gate exit.
        Fixed during initial Development by requiring the later row's
        own to_status to be a real ladder position — reproduced live
        against TASK-17's real history (case 3 in this module's test
        script).
      - That first fix still evaluated EVERY historical entry into a
        gate (via DISTINCT h1.to_status over an unrestricted h1), so a
        gate's FIRST entry could satisfy the EXISTS check via a row that
        happened before a later re-entry into that same gate — wrongly
        marking a task's own CURRENT gate as DONE the moment it had ever
        been forward-exited even once in the past, including a case
        where the gate was subsequently re-entered and is where the
        task is live right now. QA reproduced this live on TASK-019's
        own real Code Review reject-then-resubmit history (this task's
        own second Code Review round) — see qa_results id=68. Fixed
        here by evaluating only each gate's MOST RECENT entry, per the
        MAX(id)-grouped query above.

    Returned in GATE_STATUS_ORDER order (stable rendering), not
    insertion order."""
    rows = conn.execute(
        f"""
        WITH last_entry AS (
          SELECT to_status, MAX(id) AS last_id
          FROM task_status_history
          WHERE task_id = ? AND to_status IN ({_GATE_PLACEHOLDERS})
          GROUP BY to_status
        )
        SELECT le.to_status
        FROM last_entry le
        WHERE EXISTS (
          SELECT 1 FROM task_status_history h2
          WHERE h2.task_id = ? AND h2.id > le.last_id
            AND h2.to_status IN ({_GATE_PLACEHOLDERS})
        )
        """,
        (task_id, *GATE_STATUS_ORDER, task_id, *GATE_STATUS_ORDER),
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
    days. Returns (is_stuck, last_event_at).

    DONE is also excluded defensively: Active Work never calls this for a
    DONE task (active_work_rows() filters status != 'DONE'), but a future
    caller of task_progress_row() for a finished task should not see a
    spurious 'stuck' flag on completed work.

    BACKLOG is deliberately NOT excluded here — this is a disclosed,
    unresolved ambiguity in the CTO architecture doc (ops/reviews/
    cto-milestone-a-architecture.md §2.1's own text: 'not BLOCKED/
    FOUNDER_APPROVAL, i.e. nominally "in progress"' only ever names those
    two statuses), not a Development deviation: the doc's exclusion list
    is literally BLOCKED/FOUNDER_APPROVAL only, so this matches it exactly
    as written, even though a not-yet-started BACKLOG task arguably isn't
    'nominally in progress' either. Currently latent (no active BACKLOG
    task exists), flagged for CTO to resolve, not changed unilaterally."""
    if status in ("BLOCKED", "FOUNDER_APPROVAL", "DONE"):
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
    — the count, not just the sum, decides availability.

    TASK-020 (Milestone B), CTO's architecture doc §3.1: this function is
    NOT widened to also read agent_runs.cost_usd — none of the three
    newly-wired paths (Ask-Agent, Meeting, Chief of Staff) ever produce a
    task-scoped agent_runs row (they're company- or meeting-scoped
    conversations, not task work units; see start_ask_agent_run() and
    meeting_orchestrator.py), so there is nothing new for a per-task query
    to pick up. Only the note text below changed — the old wording ("is
    not persisted until Milestone B ships") became false the moment this
    milestone shipped; company-wide figures for the other three paths now
    live on the dedicated company_cost_digest()-backed /costs.html page
    instead."""
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS total "
        "FROM automation_events WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    available = bool(row["n"])
    return {
        "available": available,
        "usd": float(row["total"]) if available else None,
        "note": ("automation-poller cost only — Ask-Agent, Meeting, and Chief-of-Staff "
                 "conversations are not tied to a specific task in this system's data "
                 "model; see the company-wide Costs page for those figures."),
    }


# --------------------------------------------------------- TASK-020 (Milestone B) --

# Mirrors agent_runtime.py's own ASK_AGENT_ACTIVITY_LIKE / MEETING_ACTIVITY_LIKE /
# CHIEF_OF_STAFF_ACTIVITY_LIKE / AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE /
# REVIEWER_SYNC_ACTIVITY_LIKE — restated here as plain literals (not
# imported) for the same control-center -> db layering reason
# automation_status_digest()'s own docstring gives for SPEND_CEILING_USD
# in generate_automation.py: this module is db-layer, read-only rendering
# support, not a control-center -> db -> control-center import cycle.
# Development must keep these in sync with agent_runtime.py if those
# constants are ever revised.
_ASK_AGENT_ACTIVITY_LIKE = "Ask-Agent:%"
_MEETING_ACTIVITY_LIKE = "Meeting:%"
_CHIEF_OF_STAFF_ACTIVITY_LIKE = "Chief of Staff:%"
_AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE = "Automated Code Review:%"
_REVIEWER_SYNC_ACTIVITY_LIKE = "Synchronous review:%"


def cost_coverage(n: int, covered: int, total_usd: float) -> dict:
    """{"n": int, "covered": int, "usd": float | None} — the shared
    'count decides availability' shape every SUM(...cost_usd) figure this
    milestone introduces uses (company_cost_digest(), meeting_cost_usd()),
    extending task_cost_usd()'s original discipline two ways:

    Design's review (item 3): n == 0 ("no invocations recorded yet" — a
    real fact, hasn't happened) must render differently from n > 0 with
    covered == 0 ("recorded before cost tracking" — a real invocation
    happened, its cost just wasn't captured) — two different facts,
    never conflated into the same wording.

    Red Team's review (§3, required fix): extends the "never show a bare
    $0.00" rule to ALSO cover covered == 0 when n > 0 (not just n == 0
    alone) — a Founder skimming a row must never see a leading "$0.00"
    token for a bucket where no real cost was ever captured, even though
    real invocations happened.

    `usd` is None whenever covered == 0, regardless of n — callers render
    the three-way wording branch (see generate_costs.py's/
    generate_meetings.py's own cost-line renderers) from n/covered
    directly, never by testing `usd` alone."""
    return {"n": n, "covered": covered, "usd": float(total_usd) if covered else None}


def format_cost_coverage(cov: dict, noun: str = "invocations") -> str:
    """Plain-text rendering of cost_coverage()'s three-way branch — one
    shared implementation so generate_costs.py and generate_meetings.py
    never hand-roll two copies of this wording that could drift (the same
    DRY reasoning every other shared formula in this module follows). No
    HTML markup — callers wrap this in whatever element/color styling
    their own layout needs."""
    n, covered, usd = cov["n"], cov["covered"], cov["usd"]
    if n == 0:
        return f"No {noun} recorded yet."
    if covered == 0:
        return f"not available — 0 of {n} {noun} have a recorded cost (recorded before cost tracking)"
    missing = n - covered
    base = f"${usd:.2f} across {covered} of {n} {noun}"
    return f"{base} ({missing} recorded before cost tracking)" if missing else f"{base}."


def company_cost_digest(conn: sqlite3.Connection) -> dict:
    """TASK-020 (Milestone B), CTO's architecture doc §3.2. Company-wide
    AI invocation cost across all five real invocation paths — Ask-Agent,
    Executive Meetings, Chief of Staff, Automated Code Review, and
    Synchronous review (a genuinely distinct, human-triggered path per
    Design's review item 6/Red Team's §1 — grouped here because CTO's own
    composition already lists all five constants, even though this
    milestone's own Founder-facing framing names only four; see
    reviewer_sync.py's own disclosure comment for why Synchronous review
    stays uncosted by construction while TASK-017 stays paused, DEC-008).

    Returns {"today": cost_coverage(), "all_time": cost_coverage(),
    "by_path": [{"label", "cov"} ...], "by_agent": [{"name", "cov"} ...],
    "recent_meetings": [{"id","topic","created_at","cov"} ...]}.

    Today's/all-time's headline totals: SUM(agent_runs.cost_usd) for the
    four non-automation paths (Ask-Agent/Meeting/Chief of Staff/
    Synchronous review) PLUS SUM(automation_events.cost_usd) —
    automation_events remains the historically authoritative source for
    that one path (it has real cost data going back further than this
    milestone's agent_runs.cost_usd column does), so automation's own
    agent_runs rows are deliberately excluded from the first sum to avoid
    double-counting the same real spend twice. The by-path breakdown's own
    'Automated Code Review' row is, for the identical reason, built from
    automation_events directly, not from agent_runs — every other row
    there IS built from agent_runs (the only source that exists for those
    four paths)."""
    today = conn.execute("SELECT strftime('%Y-%m-%d', 'now')").fetchone()[0]

    def _headline(date_filter: str | None) -> dict:
        agent_runs_where = (
            "current_activity LIKE ? OR current_activity LIKE ? OR "
            "current_activity LIKE ? OR current_activity LIKE ?"
        )
        agent_runs_params = [
            _ASK_AGENT_ACTIVITY_LIKE, _MEETING_ACTIVITY_LIKE,
            _CHIEF_OF_STAFF_ACTIVITY_LIKE, _REVIEWER_SYNC_ACTIVITY_LIKE,
        ]
        automation_where = "1=1"
        automation_params: list = []
        if date_filter is not None:
            agent_runs_where = f"({agent_runs_where}) AND started_at LIKE ?"
            agent_runs_params.append(date_filter)
            automation_where = "started_at LIKE ?"
            automation_params.append(date_filter)

        ar = conn.execute(
            f"SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE cost_usd IS NOT NULL) AS covered, "
            f"COALESCE(SUM(cost_usd), 0) AS total FROM agent_runs WHERE {agent_runs_where}",
            agent_runs_params,
        ).fetchone()
        ae = conn.execute(
            f"SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE cost_usd IS NOT NULL) AS covered, "
            f"COALESCE(SUM(cost_usd), 0) AS total FROM automation_events WHERE {automation_where}",
            automation_params,
        ).fetchone()
        return cost_coverage(ar["n"] + ae["n"], ar["covered"] + ae["covered"], ar["total"] + ae["total"])

    def _path_row(label: str, activity_like: str) -> dict:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE cost_usd IS NOT NULL) AS covered, "
            "COALESCE(SUM(cost_usd), 0) AS total FROM agent_runs WHERE current_activity LIKE ?",
            (activity_like,),
        ).fetchone()
        return {"label": label, "cov": cost_coverage(row["n"], row["covered"], row["total"])}

    ae_row = conn.execute(
        "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE cost_usd IS NOT NULL) AS covered, "
        "COALESCE(SUM(cost_usd), 0) AS total FROM automation_events"
    ).fetchone()

    by_path = [
        _path_row("Ask-Agent", _ASK_AGENT_ACTIVITY_LIKE),
        _path_row("Meetings", _MEETING_ACTIVITY_LIKE),
        _path_row("Chief of Staff", _CHIEF_OF_STAFF_ACTIVITY_LIKE),
        {"label": "Automated Code Review",
         "cov": cost_coverage(ae_row["n"], ae_row["covered"], ae_row["total"])},
        _path_row("Synchronous review", _REVIEWER_SYNC_ACTIVITY_LIKE),
    ]

    # Ordered in Python by display_name(), not SQL — same reasoning
    # agent_status_rows() above already gives: sorting must happen on the
    # same displayed label callers render, not the raw machine key.
    agent_rows = conn.execute(
        """
        SELECT a.name AS name, COUNT(*) AS n,
               COUNT(*) FILTER (WHERE r.cost_usd IS NOT NULL) AS covered,
               COALESCE(SUM(r.cost_usd), 0) AS total
        FROM agent_runs r JOIN agents a ON a.id = r.agent_id
        WHERE r.scope_type = 'company' AND
              (r.current_activity LIKE ? OR r.current_activity LIKE ?)
        GROUP BY a.id
        """,
        (_ASK_AGENT_ACTIVITY_LIKE, _CHIEF_OF_STAFF_ACTIVITY_LIKE),
    ).fetchall()
    by_agent = sorted(
        [{"name": r["name"], "cov": cost_coverage(r["n"], r["covered"], r["total"])} for r in agent_rows],
        key=lambda x: display_name(x["name"]).lower(),
    )

    recent_meetings = conn.execute(
        "SELECT id, topic, created_at FROM meetings ORDER BY id DESC LIMIT 10"
    ).fetchall()
    recent_meetings = [
        {"id": m["id"], "topic": m["topic"], "created_at": m["created_at"],
         "cov": meeting_cost_usd(conn, m["id"])}
        for m in recent_meetings
    ]

    return {
        "today": _headline(today + "%"),
        "all_time": _headline(None),
        "by_path": by_path,
        "by_agent": by_agent,
        "recent_meetings": recent_meetings,
    }


def meeting_cost_usd(conn: sqlite3.Connection, meeting_id: int) -> dict:
    """TASK-020 (Milestone B), CTO's architecture doc §3.3.
    cost_coverage()-shaped: {"n", "covered", "usd"}, built from every
    agent_runs row scoped to this meeting (every participant position,
    plus — since §2.4's three extra instrumentation brackets shipped —
    CEO's own synthesis and any follow-up replies). Deliberately excludes
    CEO's own participant-selection call for this meeting: that call is
    scope_type='company' (the meeting doesn't exist yet when it runs —
    see meeting_orchestrator._select_participants()'s own docstring), not
    attributable to one specific meeting; it is counted in the
    company-wide Meetings bucket on /costs.html instead, never both
    places (double-counting would overstate company-wide spend when
    summed)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE cost_usd IS NOT NULL) AS covered, "
        "COALESCE(SUM(cost_usd), 0) AS total FROM agent_runs WHERE scope_type = 'meeting' AND scope_id = ?",
        (meeting_id,),
    ).fetchone()
    return cost_coverage(row["n"], row["covered"], row["total"])


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


def elapsed_days_int(conn: sqlite3.Connection, since_iso: str | None) -> int | None:
    """Whole days elapsed since since_iso, floored — the granularity the
    stuck badge needs ('No activity in 4d'), distinct from elapsed_since()'s
    human 'Xd Xh' format used elsewhere on these pages. None if since_iso
    is falsy or in the future (clock-skew/data artifact, not a real
    duration)."""
    if not since_iso:
        return None
    days = conn.execute("SELECT julianday('now') - julianday(?)", (since_iso,)).fetchone()[0]
    if days is None or days < 0:
        return None
    return int(days)


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


# ---- Milestone C (TASK-021): company-wide Risks register ----
# See ops/reviews/cto-milestone-c-architecture.md Part 2. Additive; no
# existing function above is changed. open_risks_digest() (above) stays
# exactly as-is for the Chief of Staff's bounded conversational digest —
# it is not reused here, per the architecture doc's own reasoning.


def risk_register_rows(conn: sqlite3.Connection) -> list[dict]:
    """Every row in `risks`, grouped open-first/mitigated/resolved, newest
    (by resolved_at, falling back to created_at) first within each group,
    severity-descending within that. The single shared computation
    /risks.html reads from. For scope_type='task' rows, resolves the real
    task title via a LEFT JOIN so the register can render
    'TASK-017 — <title>' without a second query per row; for
    scope_type='project', resolves the real project name the same way
    (display-only — no per-project detail page exists yet, see the
    architecture doc Part 4.3). Returns one plain dict per risk:
    {"id", "scope_type", "scope_id", "scope_task_title",
     "scope_project_name", "raised_by_agent", "title", "description",
     "severity", "status", "mitigation", "owner_agent", "created_at",
     "resolved_at"}. No fabricated field — every key is a real column or
     a real LEFT JOIN result, NULL rendered honestly by the caller."""
    rows = conn.execute(
        """
        SELECT r.id, r.scope_type, r.scope_id, r.raised_by_agent, r.title,
               r.description, r.severity, r.status, r.mitigation,
               r.owner_agent, r.created_at, r.resolved_at,
               t.title AS scope_task_title,
               p.name  AS scope_project_name
        FROM risks r
        LEFT JOIN tasks t ON r.scope_type = 'task' AND t.id = r.scope_id
        LEFT JOIN projects p ON r.scope_type = 'project' AND p.id = r.scope_id
        ORDER BY
          CASE r.status WHEN 'open' THEN 0 WHEN 'mitigated' THEN 1 ELSE 2 END,
          CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
          COALESCE(r.resolved_at, r.created_at) DESC,
          r.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def related_decisions_for_risk(conn: sqlite3.Connection, risk_id: int) -> list[dict]:
    """Decisions whose recorded text literally names this risk, using the
    literal-string convention this project has already, consistently
    used in every relevant DECISIONS.md entry to date ('risks.id=3',
    'risks.id=2', etc. appear verbatim in the `decisions` table rows —
    real, already-established authorial practice, not a convention
    invented for this milestone). A prefilter LIKE query keeps the
    candidate set small and cheap; the exact match is then done in
    Python with a word-boundary regex so 'risks.id=3' does not
    false-match 'risks.id=30'. The regex tolerates optional whitespace
    around the '=' (Red Team's non-blocking suggestion on this milestone's
    review, review_results.id=65: loosen from the literal 'risks.id={id}'
    to allow 'risks.id = 3'-style variants too, at zero cost) — still a
    word-boundary match, so 'risks.id=30' still correctly does not match
    risk_id=3. Returns [] (never fabricates a relation) when no decision
    names this risk_id explicitly."""
    import re
    pattern = re.compile(rf"risks\.id\s*=\s*{risk_id}\b")
    candidates = conn.execute(
        "SELECT id, title, date, problem, decision, reason, tradeoffs "
        "FROM decisions WHERE problem LIKE '%risks.id%' OR decision LIKE '%risks.id%' "
        "OR reason LIKE '%risks.id%' OR tradeoffs LIKE '%risks.id%' ORDER BY id"
    ).fetchall()
    out = []
    for d in candidates:
        blob = " ".join(filter(None, (d["problem"], d["decision"], d["reason"], d["tradeoffs"])))
        if pattern.search(blob):
            out.append({"id": d["id"], "title": d["title"], "date": d["date"]})
    return out


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
