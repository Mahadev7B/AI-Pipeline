#!/usr/bin/env python3
"""ops/db/opsdb.py — the only supported way to read or write the Phase 1
operational database (ops/db/operations.sqlite3 by default).

Zero third-party dependencies (Python 3 standard library only). Every
write goes through a parameterized query — never string-built SQL — and
every connection enables foreign-key enforcement, per the Red Team
review (ops/reviews/red-team-schema.md).

Usage:
    python3 ops/db/opsdb.py init
    python3 ops/db/opsdb.py <command> [--flag value ...]
    python3 ops/db/opsdb.py query "SELECT ..."   # read-only, SELECT only

Run `python3 ops/db/opsdb.py --help` for the full command list, or
`python3 ops/db/opsdb.py <command> --help` for one command's flags.

TESTING THIS TOOL vs. USING IT: real product QA work (testing a real
task's real feature) belongs in the live database — that's what
qa-result is for. Testing opsdb.py ITSELF — invalid input, edge cases,
"does this command behave" checks — must NEVER run against the live
database. Set OPSDB_PATH to a scratch file first:

    OPSDB_PATH=/tmp/opsdb-test-$$.sqlite3 python3 ops/db/opsdb.py init
    OPSDB_PATH=/tmp/opsdb-test-$$.sqlite3 python3 ops/db/opsdb.py <whatever you're testing>

See ops/db/README.md. This is not optional — a scratch task created
against the live database (TASK-003, removed 2026-08-28) is exactly the
mistake this convention exists to prevent.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ["OPSDB_PATH"]) if os.environ.get("OPSDB_PATH") else DB_DIR / "operations.sqlite3"
SCHEMA_PATH = DB_DIR / "schema.sql"


def connect(require_exists: bool = True) -> sqlite3.Connection:
    # Fail fast on a missing DB file — sqlite3.connect() otherwise silently
    # creates an empty 0-byte file, which then fails confusingly on the
    # first real query instead of here with a clear message. main() already
    # guarded this for CLI dispatch; moved into connect() itself (CTO's
    # Milestone 2B1 post-implementation review) so every caller gets it,
    # including server.py, which calls this directly and bypasses main().
    # require_exists=False is for cmd_init only — that command's whole job
    # is to create the file that doesn't exist yet.
    if require_exists and not DB_PATH.exists():
        raise SystemExit(f"error: {DB_PATH} does not exist — run `opsdb.py init` first")
    # timeout=5.0: how long a writer waits on SQLITE_BUSY before raising,
    # instead of the 5s-default-but-implicit sqlite3 behavior — explicit
    # per Red Team's Milestone 2B1 review (a long-lived server.py
    # connection and a concurrently-run opsdb.py CLI write can now
    # genuinely contend for the same file, which never happened when
    # opsdb.py was the only writer and every connection was short-lived).
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def cmd_query(args: argparse.Namespace) -> None:
    stmt = args.sql.strip()
    if not stmt.lstrip().upper().startswith("SELECT"):
        raise SystemExit("error: query only runs SELECT statements — use a proper command for writes")
    conn = connect()
    rows = conn.execute(stmt).fetchall()
    if not rows:
        print("(no rows)")
        return
    cols = rows[0].keys()
    print(" | ".join(cols))
    for row in rows:
        print(" | ".join(str(row[c]) for c in cols))


def cmd_project_create(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO projects (name, description, status) VALUES (?, ?, ?)",
            (args.name, args.description, args.status),
        )
    print(f"project created: id={cur.lastrowid} — {args.name}")


def _apply_additive_column_migrations(conn: sqlite3.Connection) -> None:
    """Plain nullable ADD COLUMN migrations that can't be expressed as
    idempotent raw SQL inside schema.sql's own executescript the way
    `CREATE TABLE IF NOT EXISTS` can — SQLite's `ALTER TABLE ADD COLUMN`
    has no `IF NOT EXISTS` form, so a bare ALTER TABLE statement in
    schema.sql would fail the second time `init` runs against an
    already-migrated database, breaking this command's own documented
    ("idempotent") contract. Checked via PRAGMA table_info() first, so
    this applies cleanly whether the target database is brand new or
    already has these columns.

    Phase 3A Part B (TASK-015), §B.13: handoffs.base_commit_sha/
    head_commit_sha — nullable TEXT, no CHECK constraint, a plain
    additive column exactly as the architecture doc specifies; only the
    *application* of it is made idempotent here, not the migration's own
    shape. See ops/DATA_MODEL.md."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(handoffs)").fetchall()}
    if "base_commit_sha" not in cols:
        conn.execute("ALTER TABLE handoffs ADD COLUMN base_commit_sha TEXT")
    if "head_commit_sha" not in cols:
        conn.execute("ALTER TABLE handoffs ADD COLUMN head_commit_sha TEXT")


def cmd_init(args: argparse.Namespace) -> None:
    conn = connect(require_exists=False)
    with conn:
        conn.executescript(SCHEMA_PATH.read_text())
        _apply_additive_column_migrations(conn)
    DB_PATH.chmod(0o600)  # defense in depth — nothing sensitive is stored, but no reason for group/other read
    print(f"initialized {DB_PATH}")


# ---------------------------------------------------------------- agents --

def cmd_agent_upsert(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            """
            INSERT INTO agents (name, role, model, skills, frameworks, tools,
                                 permissions_allow, permissions_deny)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                role=excluded.role, model=excluded.model, skills=excluded.skills,
                frameworks=excluded.frameworks, tools=excluded.tools,
                permissions_allow=excluded.permissions_allow,
                permissions_deny=excluded.permissions_deny,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (
                args.name, args.role, args.model,
                json.dumps(args.skills or []), json.dumps(args.frameworks or []),
                json.dumps(args.tools or []), json.dumps(args.allow or []),
                json.dumps(args.deny or []),
            ),
        )
    print(f"agent upserted: {args.name}")


def _agent_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM agents WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise SystemExit(f"error: no such agent '{name}' — run agent-upsert first")
    return row["id"]


# ----------------------------------------------------------------- tasks --

VALID_STATUSES = [
    "BACKLOG", "PLANNING", "MOCKUP", "MOCKUP_REVIEW", "ARCHITECTURE",
    "RED_TEAM_REVIEW", "READY_FOR_DEVELOPMENT", "IN_DEVELOPMENT",
    "CODE_REVIEW", "QA", "SECURITY_REVIEW", "BLOCKED", "FOUNDER_APPROVAL",
    "READY_TO_RELEASE", "DEPLOYED", "DONE",
]


def cmd_task_create(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (project_id, title, business_goal, user_story,
                                priority, current_owner, requirements,
                                acceptance_criteria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (args.project_id, args.title, args.business_goal, args.user_story,
             args.priority, args.owner, args.requirements, args.acceptance_criteria),
        )
        task_id = cur.lastrowid
        conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, "
            "changed_by_agent, note) VALUES (?, NULL, ?, ?, ?)",
            (task_id, "BACKLOG", args.by, "created"),
        )
    print(f"task created: TASK-{task_id:03d}")


def record_task_status(conn: sqlite3.Connection, task_id: int, to_status: str,
                        changed_by_agent: str, note: str | None = None,
                        owner: str | None = None) -> str:
    """Plain, directly-callable form of task-status — refactored out of
    cmd_task_status (Correction, Red Team's Phase 3A review, RT1: this
    document's original claim that `cmd_review_result` was "the one write
    path" in this file not yet following the plain-function shape was
    independently verified false — `cmd_task_status` had the identical
    problem, and §B.8's automated-REJECT path already depends on a plain
    function backing it). Same shape as every other refactored write
    function here (record_review_result() below, decide_approval(),
    end_run()): a caller-side contract violation raises a clear, typed
    ValueError, never only a SystemExit only the CLI wrapper could
    produce. automation.py (Phase 3A Part B) calls this in-process, never
    through the CLI, for the automated REJECT -> IN_DEVELOPMENT rollback
    (§B.8) — a pure bookkeeping status transition, never a new Developer
    invocation. Returns the task's previous status (for the CLI wrapper's
    own unchanged print message)."""
    if to_status not in VALID_STATUSES:
        raise ValueError(f"invalid status '{to_status}' — must be one of {VALID_STATUSES}")
    with conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"no such task TASK-{task_id:03d}")
        conn.execute(
            "UPDATE tasks SET status = ?, current_owner = COALESCE(?, current_owner), "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (to_status, owner, task_id),
        )
        conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, "
            "changed_by_agent, note) VALUES (?, ?, ?, ?, ?)",
            (task_id, row["status"], to_status, changed_by_agent, note),
        )
    return row["status"]


def cmd_task_status(args: argparse.Namespace) -> None:
    conn = connect()
    try:
        from_status = record_task_status(conn, args.task_id, args.to, args.by, args.note, args.owner)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")
    print(f"TASK-{args.task_id:03d}: {from_status} -> {args.to}")


TASK_UPDATE_FIELDS = [
    "business_goal", "user_story", "priority", "dependencies", "requirements",
    "acceptance_criteria", "mockup_design", "architecture_notes",
    "implementation_notes", "tests_required", "security_considerations",
    "developer_result", "code_review_result", "qa_result", "security_result",
    "marketing_notes", "deployment_result", "blockers", "next_action",
]


def cmd_task_update(args: argparse.Namespace) -> None:
    updates = {f: getattr(args, f) for f in TASK_UPDATE_FIELDS if getattr(args, f) is not None}
    if not updates:
        raise SystemExit("error: no fields given — pass at least one --<field> to update")
    set_clause = ", ".join(f"{f} = ?" for f in updates) + ", updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
    conn = connect()
    with conn:
        cur = conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            (*updates.values(), args.task_id),
        )
        if cur.rowcount == 0:
            raise SystemExit(f"error: no such task TASK-{args.task_id:03d}")
    print(f"TASK-{args.task_id:03d} updated: {', '.join(updates)}")


def cmd_task_step_add(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO task_steps (task_id, title, weight, owner_agent) "
            "VALUES (?, ?, ?, ?)",
            (args.task_id, args.title, args.weight, args.owner),
        )
    print(f"step added to TASK-{args.task_id:03d}: {args.title}")


def cmd_task_step_status(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        cur = conn.execute(
            "UPDATE task_steps SET status = ?, "
            "completed_at = CASE WHEN ? = 'done' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE NULL END "
            "WHERE id = ?",
            (args.status, args.status, args.step_id),
        )
        if cur.rowcount == 0:
            raise SystemExit(f"error: no such task step id={args.step_id}")
    print(f"step {args.step_id}: {args.status}")


def cmd_task_progress(args: argparse.Namespace) -> None:
    conn = connect()
    row = conn.execute(
        "SELECT SUM(weight) AS total, "
        "SUM(CASE WHEN status='done' THEN weight ELSE 0 END) AS done "
        "FROM task_steps WHERE task_id = ?",
        (args.task_id,),
    ).fetchone()
    if not row or row["total"] in (None, 0):
        print(f"TASK-{args.task_id:03d}: not yet broken into steps — no progress percentage")
        return
    pct = round(100 * row["done"] / row["total"])
    print(f"TASK-{args.task_id:03d}: {pct}% ({row['done']:g}/{row['total']:g} weighted steps done)")


# ------------------------------------------------------------- agent_runs --

def start_run(conn: sqlite3.Connection, agent_name: str, scope_type: str,
               activity: str | None, scope_id: int | None = None) -> int:
    """Plain, directly-callable form of run-start — the counterpart to
    decide_approval() (Milestone 2B1) and end_run() below. server.py's
    Ask-Agent write route (Milestone 2B2) calls this directly; the CLI
    command is a thin wrapper. Raises LookupError for an unknown agent,
    ValueError for a scope/scope_id mismatch."""
    row = conn.execute("SELECT id FROM agents WHERE name = ?", (agent_name,)).fetchone()
    if row is None:
        raise LookupError(f"no such agent '{agent_name}'")
    if scope_type == "company" and scope_id is not None:
        raise ValueError("company-scoped runs must not set scope_id")
    if scope_type != "company" and scope_id is None:
        raise ValueError("non-company scope requires scope_id")
    with conn:
        cur = conn.execute(
            "INSERT INTO agent_runs (agent_id, scope_type, scope_id, status, current_activity) "
            "VALUES (?, ?, ?, 'active', ?)",
            (row["id"], scope_type, scope_id, activity),
        )
    return cur.lastrowid


def start_ask_agent_run(conn: sqlite3.Connection, agent_name: str, activity_label: str, activity_like: str) -> int:
    """Milestone 2B3A: the atomic counterpart to start_run() for the
    Ask-Agent write path specifically. server.py's original
    SELECT-then-start_run() sequence was only race-free by accident —
    correct under the strictly single-threaded server 2B1/2B2 shipped
    with, because nothing could ever interleave between the SELECT and
    the INSERT. Once server.py became multi-threaded (this milestone),
    two threads asking the SAME agent at nearly the same moment could
    both see "no open run" before either had inserted its own row.

    BEGIN IMMEDIATE acquires SQLite's write lock up front, before any
    read, so a second thread's BEGIN IMMEDIATE genuinely blocks (up to
    the connection's busy timeout) until the first transaction commits —
    verified empirically with 5 real concurrent threads, zero lost
    writes, wall time matching full serialization.

    IMPORTANT (Red Team's Milestone 2B3A review, blocking finding): the
    BEGIN IMMEDIATE call itself is NOT inside the try/except below. If
    it fails (busy timeout expired waiting for the lock), no transaction
    is ever opened — attempting ROLLBACK in that case raises a SECOND,
    masking OperationalError ('cannot rollback - no transaction is
    active') instead of letting the real 'database is locked' one
    propagate. Only the block AFTER a successful BEGIN IMMEDIATE needs
    the rollback-on-exception guard. Callers must catch
    sqlite3.OperationalError from this function as a distinct, honest
    "busy, try again" case — the write lock was genuinely contended, not
    the same thing as an unknown agent or the run already being open.

    Raises LookupError (unknown agent), ValueError (a matching open run
    already exists), or sqlite3.OperationalError (lock contention,
    caller's responsibility to handle)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT id FROM agents WHERE name = ?", (agent_name,)).fetchone()
        if row is None:
            raise LookupError(f"no such agent '{agent_name}'")
        open_run = conn.execute(
            "SELECT id FROM agent_runs WHERE agent_id = ? AND ended_at IS NULL AND current_activity LIKE ?",
            (row["id"], activity_like),
        ).fetchone()
        if open_run is not None:
            raise ValueError(f"a request to '{agent_name}' is already in progress")
        cur = conn.execute(
            "INSERT INTO agent_runs (agent_id, scope_type, scope_id, status, current_activity) "
            "VALUES (?, 'company', NULL, 'active', ?)",
            (row["id"], activity_label),
        )
        conn.execute("COMMIT")
        return cur.lastrowid
    except Exception:
        conn.execute("ROLLBACK")
        raise


def cmd_run_start(args: argparse.Namespace) -> None:
    conn = connect()
    try:
        run_id = start_run(conn, args.agent, args.scope_type, args.activity, args.scope_id)
    except LookupError as exc:
        raise SystemExit(f"error: {exc} — run agent-upsert first")
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")
    print(f"run started: id={run_id} agent={args.agent} scope={args.scope_type}:{args.scope_id}")


def cmd_run_heartbeat(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE agent_runs SET last_heartbeat_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "current_activity = COALESCE(?, current_activity), "
            "status = COALESCE(?, status), blocked_reason = COALESCE(?, blocked_reason) "
            "WHERE id = ? AND ended_at IS NULL",
            (args.activity, args.status, args.blocked_reason, args.run_id),
        )
    print(f"run {args.run_id}: heartbeat")


RUN_END_STATUSES = ("ended", "failed")


def end_run(conn: sqlite3.Connection, run_id: int, status: str = "ended") -> None:
    """Plain, directly-callable form of run-end. Atomic and conditional
    (WHERE ended_at IS NULL) — same guard pattern as decide_approval():
    a run can only be ended once; a second call (duplicate/racing
    request) affects zero rows instead of silently overwriting ended_at
    or flipping a 'failed' run back to 'ended' (Red Team's Milestone 2B2
    review). Raises LookupError / ValueError, same convention as
    decide_approval() and start_run()."""
    if status not in RUN_END_STATUSES:
        raise ValueError(f"status must be one of {RUN_END_STATUSES}, got {status!r}")
    with conn:
        cur = conn.execute(
            "UPDATE agent_runs SET status = ?, "
            "ended_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ? AND ended_at IS NULL",
            (status, run_id),
        )
        if cur.rowcount == 0:
            row = conn.execute("SELECT status FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise LookupError(f"agent_run {run_id} does not exist")
            raise ValueError(f"agent_run {run_id} is already ended (status={row['status']})")


def reconcile_orphaned_runs(conn: sqlite3.Connection, activity_like_pattern: str, status: str = "failed") -> int:
    """Bulk counterpart to end_run() for startup recovery — e.g. a run
    left open (ended_at IS NULL) because the process that created it
    (server.py) crashed or was killed mid-request. Scoped by a
    current_activity LIKE pattern so it only ever touches runs a caller
    can identify as its own (never a blanket 'close every open run'),
    same reasoning as server.py's Ask-Agent-specific reconciliation.
    Added (CTO's Milestone 2B2 post-implementation review) so this stays
    a normal opsdb.py write like every other one — server.py must not
    hold a raw UPDATE of its own, even for a startup-only bulk case.
    Returns the number of rows updated."""
    if status not in RUN_END_STATUSES:
        raise ValueError(f"status must be one of {RUN_END_STATUSES}, got {status!r}")
    with conn:
        cur = conn.execute(
            "UPDATE agent_runs SET status = ?, "
            "ended_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE ended_at IS NULL AND current_activity LIKE ?",
            (status, activity_like_pattern),
        )
    return cur.rowcount


def cmd_run_reconcile(args: argparse.Namespace) -> None:
    conn = connect()
    count = reconcile_orphaned_runs(conn, args.activity_like, args.status)
    print(f"reconciled {count} run(s) matching {args.activity_like!r} -> {args.status}")


def cmd_run_end(args: argparse.Namespace) -> None:
    conn = connect()
    try:
        end_run(conn, args.run_id, args.status)
    except (LookupError, ValueError) as exc:
        raise SystemExit(f"error: {exc}")
    print(f"run {args.run_id}: {args.status}")


def cmd_agent_status(args: argparse.Namespace) -> None:
    conn = connect()
    rows = conn.execute(
        """
        SELECT a.name, r.status, r.scope_type, r.scope_id, r.current_activity, r.started_at
        FROM agents a
        LEFT JOIN agent_runs r ON r.agent_id = a.id AND r.ended_at IS NULL
        ORDER BY a.name
        """
    ).fetchall()
    for row in rows:
        if row["status"] is None:
            print(f"{row['name']:16s} available")
        else:
            print(f"{row['name']:16s} {row['status']:9s} "
                  f"{row['scope_type']}:{row['scope_id']}  {row['current_activity'] or ''}")


# ------------------------------------------------------------------ risks --

def cmd_risk_add(args: argparse.Namespace) -> None:
    if args.scope_type == "company" and args.scope_id is not None:
        raise SystemExit("error: company-scoped risks must not set --scope-id")
    if args.scope_type != "company" and args.scope_id is None:
        raise SystemExit("error: non-company scope requires --scope-id")
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO risks (scope_type, scope_id, raised_by_agent, title, "
            "description, severity, owner_agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (args.scope_type, args.scope_id, args.by, args.title, args.description,
             args.severity, args.owner),
        )
    print(f"risk added: id={cur.lastrowid} severity={args.severity}")


def cmd_risk_resolve(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE risks SET status = ?, mitigation = COALESCE(?, mitigation), "
            "resolved_at = CASE WHEN ? = 'resolved' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "ELSE resolved_at END WHERE id = ?",
            (args.status, args.mitigation, args.status, args.risk_id),
        )
    print(f"risk {args.risk_id}: {args.status}")


# --------------------------------------------------------------- meetings --

def _normalize_participant(entry) -> dict:
    """Milestone 2B3B round 2 (TASK-011): `meetings.participating_agents`
    rows created before this shipped are a flat JSON array of bare agent-
    name strings (create_meeting()'s original shape, Milestone 2B3B).
    From this round on, create_meeting() writes richer objects —
    `{"name": ..., "source": "selected"|"requested", "requested_by":
    None|"founder"}` — so a manually-requested addition (item 2,
    add_meeting_participant() below) can carry real provenance. Every
    reader, old row or new, goes through this helper (or
    normalized_participants() below, which applies it to a whole column)
    so no migration/backfill is needed — Red Team's Milestone 2B3B round 2
    review, finding 5a, considered a one-time backfill and left the choice
    to Development; a normalization helper used indefinitely is the
    smaller, lower-risk change for an early-stage feature with few rows,
    and is what this project already does for its other backward-
    compatible reads (e.g. `agent_runs.status` widening, Milestone 2B2).
    A bare string normalizes as `source="selected", requested_by=None` —
    the only thing every pre-existing row could have meant."""
    if isinstance(entry, str):
        return {"name": entry, "source": "selected", "requested_by": None}
    return {
        "name": entry["name"],
        "source": entry.get("source", "selected"),
        "requested_by": entry.get("requested_by"),
    }


def normalized_participants(participating_agents_json: str) -> list[dict]:
    """Parse and normalize a meetings.participating_agents column value in
    one step — the single place every reader (generate_meetings.py,
    server.py's new route handlers, add_meeting_participant(),
    start_meeting_retry_run()) gets a consistent list of
    `{"name","source","requested_by"}` dicts, whether the row predates
    this round's shape upgrade or not. Malformed/missing JSON degrades to
    an empty list, same defensive handling generate_meetings.py's own
    json_list() used before this centralized it."""
    try:
        raw = json.loads(participating_agents_json or "[]")
    except (json.JSONDecodeError, TypeError):
        raw = []
    if not isinstance(raw, list):
        raw = []
    return [_normalize_participant(entry) for entry in raw]


def create_meeting(conn: sqlite3.Connection, topic: str, initiated_by: str,
                    participating_agents: list[str]) -> int:
    """Milestone 2B3B: creates the meetings row early — before any
    participant is invoked — so a real record exists even if the
    invocation phase never completes (crash, or every participant
    failing), the same "record what was attempted, even on failure"
    principle Ask-Agent already established for its own founder-message-
    before-invoking sequence. `positions` is deliberately never written
    here or anywhere else — a meeting's positions are the messages table
    (scope='meeting', meeting_id=this row), the same "one conversation
    store" rule already applied to Ask-Agent. See
    ops/reviews/cto-milestone2b3b-architecture.md.

    Milestone 2B3B round 2: `participating_agents` is still accepted here
    as a plain list of names (the initial CEO+Orchestrator-validated
    batch — meeting_orchestrator.py's caller has no per-name provenance
    to report at creation time, every one of them is "selected") but is
    now WRITTEN as the upgraded object shape — see _normalize_participant()
    above. A later manual addition goes through add_meeting_participant()
    instead, never through this function again."""
    if initiated_by not in ("founder", "agent"):
        raise ValueError(f"initiated_by must be 'founder' or 'agent', got {initiated_by!r}")
    objects = [{"name": name, "source": "selected", "requested_by": None} for name in participating_agents]
    with conn:
        cur = conn.execute(
            "INSERT INTO meetings (topic, initiated_by, participating_agents) VALUES (?, ?, ?)",
            (topic, initiated_by, json.dumps(objects)),
        )
    return cur.lastrowid


def add_meeting_participant(conn: sqlite3.Connection, meeting_id: int, agent_name: str,
                             max_participants: int, requested_by: str = "founder") -> None:
    """Milestone 2B3B round 2 (item 2, POST /api/meetings/<id>/request-
    perspective). Atomically appends a manually-requested participant to
    `meetings.participating_agents` — a real JSON read-modify-write, so
    two concurrent requests against the same meeting must not race on the
    read. Modeled on decide_meeting()'s BEGIN IMMEDIATE shape, not
    start_ask_agent_run()'s — the invariant being protected here is a
    JSON blob read-modify-write, not an open-run-exists check, but it's
    the same "read this row, decide, write it back, atomically" fix this
    codebase already applies to that class of problem.

    Red Team's Milestone 2B3B round 2 review (finding 1 / condition 1) is
    the reason this takes `max_participants` as a caller-supplied cap
    rather than defining its own constant: CTO's original proposal for a
    new, separate MAX_REQUESTED_PARTICIPANTS was NOT affirmed. A manually-
    requested participant counts against the SAME total cap as every
    other participant — the caller (meeting_orchestrator.py) passes in
    agent_runtime.MAX_MEETING_PARTICIPANTS, the one already-approved
    constant, not a second one.

    TASK-011 QA round 2 (defect 2): called to RESERVE the slot BEFORE the
    real invocation, not after — see gather_requested_position()'s
    docstring in meeting_orchestrator.py. This closes a TOCTOU race QA
    reproduced: N truly concurrent requests for the same not-yet-
    participant agent could each pass a read-only pre-check and each
    make a real, costed invocation before only one of them won this
    append. Reserving first means a second concurrent caller fails the
    dup check below immediately and never reaches invoke_agent() at all.
    A reservation not backed by a real, successful position must not
    linger — see remove_meeting_participant(), the rollback counterpart
    a caller here uses if the invocation it reserved for doesn't pan out.

    Raises LookupError if the meeting doesn't exist, ValueError if
    `agent_name` is already a participant (by name) or the meeting is
    already at `max_participants`. Raises sqlite3.OperationalError on
    genuine lock contention (BEGIN IMMEDIATE itself, deliberately outside
    the try/except below — same non-masking discipline as
    start_ask_agent_run()/decide_meeting(); see either docstring)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT participating_agents FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise LookupError(f"meeting {meeting_id} does not exist")
        participants = normalized_participants(row["participating_agents"])
        if any(p["name"] == agent_name for p in participants):
            raise ValueError(f"'{agent_name}' is already a participant in meeting {meeting_id}")
        if len(participants) >= max_participants:
            raise ValueError(
                f"meeting {meeting_id} already has {max_participants} participants — the cap "
                "(selected + requested combined) — no further perspectives can be requested"
            )
        participants.append({"name": agent_name, "source": "requested", "requested_by": requested_by})
        conn.execute(
            "UPDATE meetings SET participating_agents = ? WHERE id = ?",
            (json.dumps(participants), meeting_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def remove_meeting_participant(conn: sqlite3.Connection, meeting_id: int, agent_name: str) -> None:
    """TASK-011 QA round 2 (defect 2): the rollback counterpart to
    add_meeting_participant()'s reservation. Called by
    meeting_orchestrator.gather_requested_position() when a reserved
    slot's invocation did not, in fact, succeed (a failed invocation, or
    any unhandled exception afterward) — a reservation with no real
    position behind it must not linger as a fabricated participant.

    Atomic (BEGIN IMMEDIATE), same JSON read-modify-write shape as
    add_meeting_participant(). Best-effort/idempotent by design (this is
    always called from a cleanup path, per _release_reservation()'s own
    "never let a cleanup-time error mask the real one" discipline in
    meeting_orchestrator.py): a missing meeting or an agent_name that
    isn't currently a participant is a silent no-op, not an error — there
    is nothing to roll back either way, and cleanup code must not itself
    raise a new, unrelated exception over the one already being handled.
    Raises sqlite3.OperationalError on genuine lock contention only (same
    non-masking discipline as every other BEGIN IMMEDIATE function here)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT participating_agents FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return
        participants = normalized_participants(row["participating_agents"])
        remaining = [p for p in participants if p["name"] != agent_name]
        if len(remaining) == len(participants):
            conn.execute("ROLLBACK")
            return
        conn.execute(
            "UPDATE meetings SET participating_agents = ? WHERE id = ?",
            (json.dumps(remaining), meeting_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def start_meeting_retry_run(conn: sqlite3.Connection, meeting_id: int, agent_name: str,
                             activity_label: str, max_retries: int) -> int:
    """Milestone 2B3B round 2 (item 5, POST /api/meetings/<id>/retry). The
    atomic counterpart to start_run() for retrying a participant whose
    original _gather_position() invocation failed. Same BEGIN IMMEDIATE /
    non-masking exception-handling discipline as start_ask_agent_run()
    (that function's docstring explains why the transaction start itself
    must stay outside the try/except).

    IMPORTANT (Red Team's Milestone 2B3B round 2 review, finding 4 /
    condition 4 — binding, not optional): the open-run check below
    matches on scope ALONE — `(agent_id, scope_type='meeting',
    scope_id=meeting_id, ended_at IS NULL)` — with NO `current_activity
    LIKE` filtering of any kind. This is deliberately different from
    start_ask_agent_run(), which DOES filter by an `activity_like`
    pattern for an unrelated reason (ignoring this project's own task-
    scoped runs against the same agent name — see that function's
    docstring). Copying that filter here "for consistency" would let a
    Retry-labeled check ignore the still-open original _gather_position()
    run for this exact participant+meeting, silently reopening the
    double-click race this function exists to close. Do not add an
    activity_like parameter to this function.

    Raises LookupError (unknown agent or meeting), ValueError (agent_name
    is not a current participant; a real position already exists for
    this agent in the meeting's shared positions thread — nothing to
    retry; a run for this (agent, meeting) is already in progress; or the
    retry cap is already reached — each a 409 at the HTTP layer), or
    sqlite3.OperationalError (lock contention, caller's responsibility to
    handle, same as start_ask_agent_run())."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        agent_row = conn.execute("SELECT id FROM agents WHERE name = ?", (agent_name,)).fetchone()
        if agent_row is None:
            raise LookupError(f"no such agent '{agent_name}'")
        agent_id = agent_row["id"]

        meeting_row = conn.execute(
            "SELECT participating_agents FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
        if meeting_row is None:
            raise LookupError(f"meeting {meeting_id} does not exist")
        participants = normalized_participants(meeting_row["participating_agents"])
        if not any(p["name"] == agent_name for p in participants):
            raise ValueError(f"'{agent_name}' is not a participant in meeting {meeting_id}")

        has_position = conn.execute(
            "SELECT 1 FROM messages WHERE thread_id = ? AND from_agent = ? LIMIT 1",
            (f"meeting-{meeting_id}", agent_name),
        ).fetchone()
        if has_position is not None:
            raise ValueError(
                f"'{agent_name}' already has a recorded position in meeting {meeting_id} — nothing to retry"
            )

        open_run = conn.execute(
            "SELECT id FROM agent_runs WHERE agent_id = ? AND scope_type = 'meeting' "
            "AND scope_id = ? AND ended_at IS NULL",
            (agent_id, meeting_id),
        ).fetchone()
        if open_run is not None:
            raise ValueError(f"a run for '{agent_name}' in meeting {meeting_id} is already in progress")

        # Every prior attempt for this (agent, meeting) pair — the original
        # _gather_position() invocation plus any retry already made — is a
        # 'failed' agent_runs row here (a 'succeeded' one would have been
        # caught by the has_position check above, since that's exactly what
        # "succeeded" means). MAX_RETRIES_PER_PARTICIPANT retries are
        # allowed on top of the original attempt (the "(1 +
        # MAX_RETRIES_PER_PARTICIPANT) invocations per participant" figure
        # both CTO's and Red Team's Milestone 2B3B round 2 documents use) —
        # so the cap on prior failures before rejecting a NEW attempt is
        # max_retries + 1, not max_retries.
        failed_count = conn.execute(
            "SELECT COUNT(*) FROM agent_runs WHERE agent_id = ? AND scope_type = 'meeting' "
            "AND scope_id = ? AND status = 'failed'",
            (agent_id, meeting_id),
        ).fetchone()[0]
        if failed_count >= max_retries + 1:
            raise ValueError(
                f"retry limit reached for '{agent_name}' in meeting {meeting_id} "
                f"({max_retries} retries already attempted)"
            )

        cur = conn.execute(
            "INSERT INTO agent_runs (agent_id, scope_type, scope_id, status, current_activity) "
            "VALUES (?, 'meeting', ?, 'active', ?)",
            (agent_id, meeting_id, activity_label),
        )
        conn.execute("COMMIT")
        return cur.lastrowid
    except Exception:
        conn.execute("ROLLBACK")
        raise


def finalize_meeting_synthesis(conn: sqlite3.Connection, meeting_id: int,
                                agreements: str | None, disagreements: str | None,
                                unresolved_questions: str | None, recommendation: str | None) -> None:
    """Records CEO's synthesis (Milestone 2B3B) once all participant
    positions are gathered. Any of the four fields may be None — if
    CEO's own synthesis call itself fails, the meeting still keeps every
    real position already persisted in `messages`; these columns simply
    stay NULL, rendered honestly as "not available," never fabricated."""
    with conn:
        conn.execute(
            "UPDATE meetings SET agreements = ?, disagreements = ?, "
            "unresolved_questions = ?, recommendation = ? WHERE id = ?",
            (agreements, disagreements, unresolved_questions, recommendation, meeting_id),
        )


def decide_meeting(conn: sqlite3.Connection, meeting_id: int, decision_text: str, by: str = "founder") -> int:
    """Atomically records the Founder's decision on a meeting: a real
    decisions-table row (via _insert_decision() — the same INSERT every
    other decision in this system goes through, not a parallel one) plus
    meetings.founder_decision/linked_decision_id, guarded by
    WHERE founder_decision IS NULL so a decision, once recorded, cannot
    be silently overwritten by a second submission — same one-time-only
    pattern as decide_approval(). Uses BEGIN IMMEDIATE (not `with conn:`)
    so the decisions INSERT and the meetings UPDATE commit together as
    one real transaction — calling the self-committing record_decision()
    here would let its own commit land between the two writes, breaking
    exactly the atomicity this function exists to provide (a real bug
    caught and fixed during this milestone's own development, before
    Code Review — same category of mistake 2B3A's BEGIN IMMEDIATE
    exception-handling bug was). Raises LookupError if the meeting
    doesn't exist, ValueError if it's already decided. Raises
    sqlite3.OperationalError on genuine lock contention (BEGIN IMMEDIATE
    itself failing) — deliberately NOT inside the try/except below, same
    fix Red Team's Milestone 2B3A review required for
    start_ask_agent_run(): if BEGIN IMMEDIATE never succeeds, there is
    no transaction to roll back, and attempting one would raise a
    second, masking error instead of this real one. Callers must handle
    sqlite3.OperationalError as a distinct "busy, try again" case, same
    as start_ask_agent_run(). Returns the new decisions.id."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT topic, founder_decision FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise LookupError(f"meeting {meeting_id} does not exist")
        if row["founder_decision"] is not None:
            raise ValueError(f"meeting {meeting_id} already has a recorded decision")
        dec_id = _insert_decision(
            conn, title=f"Executive Meeting #{meeting_id}: {row['topic']}", decision=decision_text, by=by,
        )
        cur = conn.execute(
            "UPDATE meetings SET founder_decision = ?, linked_decision_id = ? "
            "WHERE id = ? AND founder_decision IS NULL",
            (decision_text, dec_id, meeting_id),
        )
        if cur.rowcount == 0:
            # Can only happen if founder_decision was NULL in the SELECT above
            # but is no longer NULL here — impossible within a single BEGIN
            # IMMEDIATE transaction (no other writer can interleave), kept as
            # a defensive check, not a reachable path.
            raise ValueError(f"meeting {meeting_id} already has a recorded decision")
        conn.execute("COMMIT")
        return dec_id
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ------------------------------------------------------- other write ops --

def cmd_activity_log(args: argparse.Namespace) -> None:
    conn = connect()
    agent_id = _agent_id(conn, args.agent)
    with conn:
        conn.execute(
            "INSERT INTO agent_activity (agent_id, task_id, summary, detail) VALUES (?, ?, ?, ?)",
            (agent_id, args.task_id, args.summary, args.detail),
        )
    print("activity logged")


_MESSAGE_SCOPE_FIELD = {"task": "task_id", "project": "project_id", "meeting": "meeting_id"}


def send_message(conn: sqlite3.Connection, thread_id: str, scope: str, from_agent: str, body: str,
                  to_agent: str | None = None, task_id: int | None = None,
                  project_id: int | None = None, meeting_id: int | None = None) -> int:
    """Plain, directly-callable form of message-send — the only function
    (besides its thin CLI wrapper) that writes the messages table.
    Mirrors the schema's own scope-consistency CHECK constraint so a bad
    combination raises ValueError with a clear message, not a raw
    IntegrityError."""
    scope_ids = {"task": task_id, "project": project_id, "meeting": meeting_id}
    for s, value in scope_ids.items():
        if s == scope and value is None:
            raise ValueError(f"scope '{scope}' requires {_MESSAGE_SCOPE_FIELD[s]}")
        if s != scope and value is not None:
            raise ValueError(f"{_MESSAGE_SCOPE_FIELD[s]} is only valid with scope '{s}'")
    with conn:
        cur = conn.execute(
            "INSERT INTO messages (thread_id, scope, task_id, project_id, meeting_id, "
            "from_agent, to_agent, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (thread_id, scope, task_id, project_id, meeting_id, from_agent, to_agent, body),
        )
    return cur.lastrowid


def cmd_message_send(args: argparse.Namespace) -> None:
    conn = connect()
    try:
        msg_id = send_message(conn, args.thread_id, args.scope, args.from_agent, args.body,
                               args.to_agent, args.task_id, args.project_id, args.meeting_id)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")
    print(f"message recorded: id={msg_id} thread={args.thread_id}")


def cmd_qa_result(args: argparse.Namespace) -> None:
    if args.result == "fail" and not args.returned_to:
        raise SystemExit("error: a fail result must set --returned-to")
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO qa_results (task_id, tested_by_agent, scenario, result, "
            "defect_summary, reproduction_steps, returned_to_agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (args.task_id, args.by, args.scenario, args.result, args.defect,
             args.steps, args.returned_to),
        )
    print(f"QA result recorded: {args.result}")


def record_review_result(conn: sqlite3.Connection, task_id: int, review_type: str, by: str,
                          result: str, findings: list | None = None,
                          returned_to: str | None = None) -> int:
    """Plain, directly-callable form of review-result — refactored out of
    cmd_review_result (Security's Phase 3A threat-model review, required
    fix C4), same shape as every other write function in this file.
    automation.py (Phase 3A Part B) calls this in-process, never through
    the CLI, for both the automated PASS and REJECT paths (§B.8) — the
    reject-requires-`returned_to` invariant therefore MUST live here, not
    only in cmd_review_result's own --returned-to check below, or an
    in-process caller could bypass it entirely and rely on the schema's
    own CHECK constraint alone (still fail-safe either way, but
    inconsistent with this file's established convention of a clear,
    typed ValueError for a caller-side contract violation — see
    record_task_status()/decide_approval()/end_run() above). Raises
    ValueError for an invalid review_type/result, or a reject with no
    returned_to. Returns the new review_results.id."""
    if review_type not in ("code", "security"):
        raise ValueError(f"review_type must be 'code' or 'security', got {review_type!r}")
    if result not in ("pass", "reject"):
        raise ValueError(f"result must be 'pass' or 'reject', got {result!r}")
    if result == "reject" and not returned_to:
        raise ValueError("a reject result must set returned_to")
    with conn:
        cur = conn.execute(
            "INSERT INTO review_results (task_id, review_type, reviewed_by_agent, result, "
            "findings, returned_to_agent) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, review_type, by, result, json.dumps(findings or []), returned_to),
        )
    return cur.lastrowid


def cmd_review_result(args: argparse.Namespace) -> None:
    conn = connect()
    try:
        record_review_result(conn, args.task_id, args.type, args.by, args.result,
                              args.findings, args.returned_to)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")
    print(f"{args.type} review recorded: {args.result}")


def cmd_handoff(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO handoffs (task_id, from_agent, to_agent, work_completed, "
            "files_changed, tests_added, expected_behavior, known_limitations, "
            "receiving_agent_checklist, base_commit_sha, head_commit_sha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (args.task_id, args.from_agent, args.to_agent, args.work_completed,
             json.dumps(args.files or []), args.tests_added, args.expected_behavior,
             args.known_limitations, args.checklist, args.base_commit_sha, args.head_commit_sha),
        )
    print(f"handoff recorded: {args.from_agent} -> {args.to_agent}")


def cmd_approval_create(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO approvals (task_id, request, requested_by_agent, why, "
            "recommendation, alternatives_considered, expected_cost, risks, "
            "consequence_if_not_approved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (args.task_id, args.request, args.by, args.why, args.recommendation,
             args.alternatives, args.cost, args.risks, args.consequence),
        )
    print(f"approval requested: id={cur.lastrowid} (status: pending)")


DECIDABLE_DECISIONS = ("approve", "reject", "discuss")

# decision -> the states an approval must currently be in for that
# decision to be accepted. approve/reject are terminal (no key here means
# no transition out is ever allowed); discuss is a checkpoint, not a 4th
# terminal outcome, so approve/reject may still follow it. discuss ->
# discuss is intentionally absent: already-flagged is a no-op, not a new
# state. See ops/DATA_MODEL.md, "approvals" / decision transitions.
_APPROVAL_FROM_STATES = {
    "approve": ("pending", "discuss"),
    "reject": ("pending", "discuss"),
    "discuss": ("pending",),
}


def decide_approval(conn: sqlite3.Connection, approval_id: int, decision: str) -> dict:
    """The one function permitted to write approvals.decision — called by
    both the CLI (cmd_approval_decide) and the Control Center's write
    boundary (ops/control-center/server.py). Atomic and conditional: the
    UPDATE only matches a row still in a state that decision is allowed
    to come from, so a second call (double-submit, or deciding an
    already-resolved approval) always affects zero rows instead of
    silently overwriting a prior decision. Raises LookupError if the
    approval doesn't exist, ValueError if it exists but isn't in a
    decidable state for this decision. Commits its own transaction —
    callers (including a long-lived connection held by server.py across
    many requests) must not assume an outer transaction is doing that.
    """
    if decision not in DECIDABLE_DECISIONS:
        raise ValueError(f"decision must be one of {DECIDABLE_DECISIONS}, got {decision!r}")
    from_states = _APPROVAL_FROM_STATES[decision]
    placeholders = ",".join("?" for _ in from_states)
    with conn:
        cur = conn.execute(
            f"UPDATE approvals SET decision = ?, "
            f"decided_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            f"WHERE id = ? AND decision IN ({placeholders})",
            (decision, approval_id, *from_states),
        )
        if cur.rowcount == 0:
            row = conn.execute("SELECT decision FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None:
                raise LookupError(f"approval {approval_id} does not exist")
            raise ValueError(
                f"approval {approval_id} is already '{row['decision']}' — "
                f"cannot record '{decision}' from that state"
            )
    return {"id": approval_id, "decision": decision}


def cmd_approval_decide(args: argparse.Namespace) -> None:
    if args.decision not in DECIDABLE_DECISIONS:
        raise SystemExit(f"error: decision must be one of {DECIDABLE_DECISIONS}")
    if not args.confirm_founder_decision:
        raise SystemExit(
            "error: refusing to record a Founder decision without "
            "--confirm-founder-decision. This CLI has no real identity check "
            "(any caller can pass this flag) — it exists so an agent's normal "
            "workflow can never casually decide its own approval request; a "
            "human deciding through the Control Center (ops/control-center/"
            "server.py, Milestone 2B1) is the primary control for interactive "
            "use, not this flag. See ops/DATA_MODEL.md, Rules."
        )
    conn = connect()
    try:
        decide_approval(conn, args.approval_id, args.decision)
    except LookupError as e:
        raise SystemExit(f"error: {e}")
    except ValueError as e:
        raise SystemExit(f"error: {e}")
    print(f"approval {args.approval_id}: {args.decision}")


def _insert_decision(conn: sqlite3.Connection, title: str, decision: str, by: str,
                      problem: str | None = None, options: list | None = None,
                      reason: str | None = None, tradeoffs: str | None = None,
                      founder_approval: bool = False, approval_id: int | None = None) -> int:
    """The raw INSERT, with no transaction management of its own —
    exists so decide_meeting() can compose it into ONE atomic
    transaction with the meetings UPDATE (see that function). Not
    called directly outside this module; record_decision() below is the
    public, self-committing entry point for standalone use."""
    cur = conn.execute(
        "INSERT INTO decisions (title, date, problem, options_considered, decision, "
        "reason, tradeoffs, recommending_agent, founder_approval_required, "
        "founder_approval_id) VALUES (?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, problem, json.dumps(options or []), decision,
         reason, tradeoffs, by, 1 if founder_approval else 0, approval_id),
    )
    return cur.lastrowid


def record_decision(conn: sqlite3.Connection, title: str, decision: str, by: str,
                     problem: str | None = None, options: list | None = None,
                     reason: str | None = None, tradeoffs: str | None = None,
                     founder_approval: bool = False, approval_id: int | None = None) -> int:
    """Plain, directly-callable, self-committing form of decision-record
    — same pattern as every other opsdb.py write function since
    Milestone 2B1. Standalone use only — decide_meeting() below composes
    _insert_decision() directly instead, so its decisions-row write and
    its meetings-row update share one real transaction rather than this
    function's own commit landing in between them (which would silently
    break the atomicity decide_meeting() depends on)."""
    with conn:
        return _insert_decision(conn, title, decision, by, problem, options,
                                 reason, tradeoffs, founder_approval, approval_id)


def cmd_decision_record(args: argparse.Namespace) -> None:
    conn = connect()
    dec_id = record_decision(conn, args.title, args.decision, args.by, args.problem,
                              args.options, args.reason, args.tradeoffs,
                              args.founder_approval, args.approval_id)
    print(f"decision recorded: id={dec_id} — {args.title}")


def cmd_deployment_record(args: argparse.Namespace) -> None:
    if not args.founder_authorized:
        raise SystemExit(
            "error: refusing to record a deployment without --founder-authorized — "
            "the schema itself rejects founder_authorized=0, this check just fails fast"
        )
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO deployments (task_id, version, environment, release_notes, "
            "rollback_plan, deployed_by_agent, founder_authorized) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (args.task_id, args.version, args.environment, args.release_notes,
             args.rollback_plan, args.by),
        )
    print(f"deployment recorded: id={cur.lastrowid} version={args.version}")


# --------------------------------------------------- Phase 3A Part B ------
# Automation poller support (ops/control-center/automation.py). See
# ops/reviews/cto-phase3a-architecture.md §B.3/§B.4/§B.11. None of these
# have a CLI wrapper — every one is called only in-process, by
# automation.py (create_automation_event/end_automation_event) or
# server.py's write routes (set_automation_enabled) or startup
# reconciliation (reconcile_stuck_automation_events), never through a
# human-typed opsdb.py command.

def set_automation_enabled(conn: sqlite3.Connection, enabled: bool, reason: str | None = None,
                            by: str = "founder") -> None:
    """The only function permitted to write automation_state (§B.4) —
    called only by the two new CSRF+session-gated routes (POST
    /api/automation/stop, /start), never by the poller itself, never by
    any agent invocation. automation_state has exactly one row (id=1,
    CHECK-enforced, seeded by schema.sql's own INSERT OR IGNORE at
    schema-apply time) — this is always an UPDATE, never an INSERT."""
    with conn:
        conn.execute(
            "UPDATE automation_state SET enabled = ?, changed_by = ?, reason = ?, "
            "changed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = 1",
            (1 if enabled else 0, by, reason),
        )


def create_automation_event(conn: sqlite3.Connection, task_id: int,
                             trigger_status_history_id: int) -> int | None:
    """The atomic claim (§B.3/§B.10 scenario 4; Correction, Red Team's
    Phase 3A review, RT3 — this is the VERY FIRST step automation.py takes
    for any eligible-looking trigger row, strictly BEFORE the
    handoff-existence check, the SHA validity checks, and the file-path
    validation, not only before the real invocation — see automation.py's
    own module docstring for why this ordering is load-bearing: without
    it, a task manually moved to CODE_REVIEW with no handoff, a typo'd
    SHA, or any other eligibility failure would be re-evaluated by the
    candidate-finding query on every subsequent poll cycle, forever).

    Two things happen atomically, inside one BEGIN IMMEDIATE transaction:
    (1) re-checks tasks.status is STILL 'CODE_REVIEW' (§B.10 scenario 4 —
    a human may have acted on the task between the poller's candidate-list
    read and this claim attempt); (2) the real claim — an INSERT whose
    trigger_status_history_id UNIQUE constraint (schema.sql) is the
    actual, DB-enforced idempotency guarantee (Founder's control #5), not
    merely this function's own pre-check.

    Returns the new automation_events.id, or None if no NEW claim could be
    made — either this trigger_status_history_id is already claimed (any
    status — the idempotency case, §B.10 scenario 1), or tasks.status no
    longer matches CODE_REVIEW (§B.10 scenario 4). The caller cannot
    distinguish which from the return value alone and, per RT3, must not
    need to: either way there is nothing new to record. Raises
    sqlite3.OperationalError on genuine lock contention (BEGIN IMMEDIATE
    itself, deliberately outside the try/except below — same non-masking
    discipline as start_ask_agent_run()/add_meeting_participant())."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT id FROM automation_events WHERE trigger_status_history_id = ?",
            (trigger_status_history_id,),
        ).fetchone()
        if existing is not None:
            conn.execute("ROLLBACK")
            return None
        task_row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task_row is None or task_row["status"] != "CODE_REVIEW":
            conn.execute("ROLLBACK")
            return None
        try:
            cur = conn.execute(
                "INSERT INTO automation_events (task_id, trigger_status_history_id, status) "
                "VALUES (?, ?, 'running')",
                (task_id, trigger_status_history_id),
            )
        except sqlite3.IntegrityError:
            # A second, truly concurrent claim attempt for the same
            # trigger row (§B.6's R2 disclosure: race-free only under the
            # single-poller-process assumption; the per-event UNIQUE
            # constraint itself is genuinely DB-enforced regardless) —
            # the same "nothing new to record" outcome as the pre-check
            # above, just caught one step later.
            conn.execute("ROLLBACK")
            return None
        conn.execute("COMMIT")
        return cur.lastrowid
    except Exception:
        conn.execute("ROLLBACK")
        raise


_AUTOMATION_EVENT_END_STATUSES = ("completed", "failed", "skipped")


def end_automation_event(conn: sqlite3.Connection, event_id: int, status: str,
                          outcome: str | None = None, review_result_id: int | None = None,
                          cost_usd: float | None = None, truncated: bool = False,
                          skip_reason: str | None = None) -> None:
    """Terminal-state write for one automation_events row — 'completed'
    (outcome pass/reject), 'failed' (outcome error/interrupted), or
    'skipped' (a §B.10 fail-closed scenario, or a §B.7 cap — outcome
    'capped' for the two genuine cap scenarios per Red Team's Phase 3A
    review, NB1). Conditional on status='running' so a row already ended
    cannot be silently re-ended (same one-time-only discipline as
    end_run()/decide_approval()). Raises ValueError if `status` is not one
    of the real terminal values, LookupError if the row doesn't exist or
    is already ended."""
    if status not in _AUTOMATION_EVENT_END_STATUSES:
        raise ValueError(f"status must be one of {_AUTOMATION_EVENT_END_STATUSES}, got {status!r}")
    with conn:
        cur = conn.execute(
            "UPDATE automation_events SET status = ?, outcome = ?, review_result_id = ?, "
            "cost_usd = ?, truncated = ?, skip_reason = ?, "
            "ended_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE id = ? AND status = 'running'",
            (status, outcome, review_result_id, cost_usd, 1 if truncated else 0, skip_reason, event_id),
        )
        if cur.rowcount == 0:
            row = conn.execute("SELECT status FROM automation_events WHERE id = ?", (event_id,)).fetchone()
            if row is None:
                raise LookupError(f"automation_events {event_id} does not exist")
            raise ValueError(f"automation_events {event_id} is already '{row['status']}'")


def reconcile_stuck_automation_events(conn: sqlite3.Connection) -> int:
    """Startup counterpart to reconcile_orphaned_runs() for the new table
    (§B.11) — an automation_events row found status='running' at server
    startup means the prior process crashed mid-cycle. Never silently
    marked complete or resumed: marked 'failed'/'interrupted' once, and
    (per the UNIQUE constraint) its trigger event is never automatically
    retried afterward — the same Founder-visible "needs a look" state as
    any other failure. Returns the number of rows updated."""
    with conn:
        cur = conn.execute(
            "UPDATE automation_events SET status='failed', outcome='interrupted', "
            "ended_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE status='running'"
        )
    return cur.rowcount


PURGE_CHECK_TABLES = [
    "qa_results", "review_results", "deployments", "handoffs",
    "messages", "agent_activity", "task_steps",
    "approvals",  # an approval is auditable Founder-decision history —
                  # never silently deleted, even for a scratch task.
]


def cmd_task_purge_scratch(args: argparse.Namespace) -> None:
    """Remove a task from the live database — ONLY ever usable on
    self-labeled scratch/test data with zero real work AND zero auditable
    history (approvals, decisions) attached. This is not a general
    delete: it exists to undo test contamination like TASK-003 (see
    ops/db/README.md), never to erase real history. Only the task itself
    and its task_status_history are ever removed — every other table is
    a blocker, never a deletion target."""
    conn = connect()
    row = conn.execute("SELECT id, title FROM tasks WHERE id = ?", (args.task_id,)).fetchone()
    if row is None:
        raise SystemExit(f"error: no such task TASK-{args.task_id:03d}")
    if not row["title"].lower().startswith("qa scratch:"):
        raise SystemExit(
            f"error: refusing to purge TASK-{args.task_id:03d} — its title does not "
            "start with 'QA scratch:'. This command only removes tasks explicitly "
            "self-labeled that way, never real work, however small, and never on a "
            "loose substring match (a real task titled 'not scratch work' must not "
            "be purgeable by accident)."
        )
    blockers = []
    for table in PURGE_CHECK_TABLES:
        n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (args.task_id,)).fetchone()[0]
        if n:
            blockers.append(f"{n} row(s) in {table}")
    n_risks = conn.execute(
        "SELECT COUNT(*) FROM risks WHERE scope_type='task' AND scope_id = ?", (args.task_id,)
    ).fetchone()[0]
    if n_risks:
        blockers.append(f"{n_risks} row(s) in risks")
    # Belt-and-suspenders: even though blocking on any approvals row above
    # already makes this unreachable (a decision can only reference an
    # approval that exists), check explicitly that no decision references
    # one of this task's approvals — auditable decision history must
    # never depend on the approvals check alone to stay protected.
    n_decisions = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE founder_approval_id IN "
        "(SELECT id FROM approvals WHERE task_id = ?)", (args.task_id,)
    ).fetchone()[0]
    if n_decisions:
        blockers.append(f"{n_decisions} row(s) in decisions (via an approval)")
    if blockers:
        raise SystemExit(
            f"error: refusing to purge TASK-{args.task_id:03d} — it has real work "
            f"or auditable history attached: {'; '.join(blockers)}. Purge only "
            "removes tasks with zero downstream artifacts; approvals and decisions "
            "are never deleted by this command, only checked as blockers."
        )
    if not args.confirm:
        raise SystemExit("error: pass --confirm to actually remove it")

    with conn:
        n_hist = conn.execute("DELETE FROM task_status_history WHERE task_id = ?", (args.task_id,)).rowcount
        conn.execute("DELETE FROM tasks WHERE id = ?", (args.task_id,))
    print(f"purged TASK-{args.task_id:03d} ({row['title']!r}): "
          f"removed {n_hist} task_status_history row(s) and the task itself "
          "(no approvals existed to protect)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database from schema.sql (idempotent)").set_defaults(func=cmd_init)

    q = sub.add_parser("query", help="run a read-only SELECT against the database")
    q.add_argument("sql", help="a SELECT statement, quoted")
    q.set_defaults(func=cmd_query)

    pc = sub.add_parser("project-create", help="create a project")
    pc.add_argument("--name", required=True)
    pc.add_argument("--description")
    pc.add_argument("--status", default="active", choices=["active", "paused", "done"])
    pc.set_defaults(func=cmd_project_create)

    a = sub.add_parser("agent-upsert", help="create or update an agent row")
    a.add_argument("--name", required=True)
    a.add_argument("--role", required=True)
    a.add_argument("--model", default="configurable")
    a.add_argument("--skills", nargs="*")
    a.add_argument("--frameworks", nargs="*")
    a.add_argument("--tools", nargs="*")
    a.add_argument("--allow", nargs="*")
    a.add_argument("--deny", nargs="*")
    a.set_defaults(func=cmd_agent_upsert)

    t = sub.add_parser("task-create", help="create a task (starts at BACKLOG)")
    t.add_argument("--title", required=True)
    t.add_argument("--project-id", type=int, dest="project_id")
    t.add_argument("--business-goal")
    t.add_argument("--user-story")
    t.add_argument("--priority")
    t.add_argument("--owner")
    t.add_argument("--requirements")
    t.add_argument("--acceptance-criteria")
    t.add_argument("--by", required=True, help="agent recording the creation")
    t.set_defaults(func=cmd_task_create)

    ts = sub.add_parser("task-status", help="move a task to a new status")
    ts.add_argument("--task-id", type=int, required=True, dest="task_id")
    ts.add_argument("--to", required=True, choices=VALID_STATUSES)
    ts.add_argument("--by", required=True)
    ts.add_argument("--owner", help="new current_owner, if changing")
    ts.add_argument("--note")
    ts.set_defaults(func=cmd_task_status)

    tu = sub.add_parser("task-update", help="update one or more of a task's narrative fields")
    tu.add_argument("--task-id", type=int, required=True, dest="task_id")
    for field in TASK_UPDATE_FIELDS:
        tu.add_argument(f"--{field.replace('_', '-')}", dest=field)
    tu.set_defaults(func=cmd_task_update)

    tsa = sub.add_parser("task-step-add", help="add an objective step to a task")
    tsa.add_argument("--task-id", type=int, required=True, dest="task_id")
    tsa.add_argument("--title", required=True)
    tsa.add_argument("--weight", type=float, default=1.0)
    tsa.add_argument("--owner")
    tsa.set_defaults(func=cmd_task_step_add)

    tss = sub.add_parser("task-step-status", help="mark a task step pending/in_progress/done")
    tss.add_argument("--step-id", type=int, required=True, dest="step_id")
    tss.add_argument("--status", required=True, choices=["pending", "in_progress", "done"])
    tss.set_defaults(func=cmd_task_step_status)

    tp = sub.add_parser("task-progress", help="print a task's deterministic progress %")
    tp.add_argument("--task-id", type=int, required=True, dest="task_id")
    tp.set_defaults(func=cmd_task_progress)

    rs = sub.add_parser("run-start", help="start an agent_runs row (Working)")
    rs.add_argument("--agent", required=True)
    rs.add_argument("--scope-type", required=True, choices=["task", "project", "meeting", "company"], dest="scope_type")
    rs.add_argument("--scope-id", type=int, dest="scope_id")
    rs.add_argument("--activity", required=True)
    rs.set_defaults(func=cmd_run_start)

    rh = sub.add_parser("run-heartbeat", help="update an open run's activity/status")
    rh.add_argument("--run-id", type=int, required=True, dest="run_id")
    rh.add_argument("--activity")
    rh.add_argument("--status", choices=["active", "waiting", "blocked"])
    rh.add_argument("--blocked-reason", dest="blocked_reason")
    rh.set_defaults(func=cmd_run_heartbeat)

    re_ = sub.add_parser("run-end", help="end an agent_runs row")
    re_.add_argument("--run-id", type=int, required=True, dest="run_id")
    re_.add_argument("--status", choices=list(RUN_END_STATUSES), default="ended")
    re_.set_defaults(func=cmd_run_end)

    rc = sub.add_parser("run-reconcile", help="bulk-end orphaned open runs matching a current_activity LIKE pattern (startup recovery)")
    rc.add_argument("--activity-like", required=True, dest="activity_like")
    rc.add_argument("--status", choices=list(RUN_END_STATUSES), default="failed")
    rc.set_defaults(func=cmd_run_reconcile)

    sub.add_parser("agent-status", help="print every agent's computed status").set_defaults(func=cmd_agent_status)

    ra = sub.add_parser("risk-add", help="record a risk")
    ra.add_argument("--scope-type", required=True, choices=["task", "project", "company"], dest="scope_type")
    ra.add_argument("--scope-id", type=int, dest="scope_id")
    ra.add_argument("--by", required=True)
    ra.add_argument("--title", required=True)
    ra.add_argument("--description")
    ra.add_argument("--severity", required=True, choices=["low", "medium", "high"])
    ra.add_argument("--owner")
    ra.set_defaults(func=cmd_risk_add)

    rr = sub.add_parser("risk-resolve", help="update a risk's status")
    rr.add_argument("--risk-id", type=int, required=True, dest="risk_id")
    rr.add_argument("--status", required=True, choices=["open", "mitigated", "resolved"])
    rr.add_argument("--mitigation")
    rr.set_defaults(func=cmd_risk_resolve)

    ms = sub.add_parser("message-send", help="record a message (Founder<->agent or agent<->agent) — the only writer of the messages table")
    ms.add_argument("--thread-id", required=True, dest="thread_id")
    ms.add_argument("--scope", required=True, choices=["task", "project", "agent", "meeting"])
    ms.add_argument("--task-id", type=int, dest="task_id")
    ms.add_argument("--project-id", type=int, dest="project_id")
    ms.add_argument("--meeting-id", type=int, dest="meeting_id")
    ms.add_argument("--from-agent", required=True, dest="from_agent")
    ms.add_argument("--to-agent", dest="to_agent")
    ms.add_argument("--body", required=True)
    ms.set_defaults(func=cmd_message_send)

    al = sub.add_parser("activity-log", help="log a free-text activity entry")
    al.add_argument("--agent", required=True)
    al.add_argument("--task-id", type=int, dest="task_id")
    al.add_argument("--summary", required=True)
    al.add_argument("--detail")
    al.set_defaults(func=cmd_activity_log)

    qr = sub.add_parser("qa-result", help="record a QA pass/fail")
    qr.add_argument("--task-id", type=int, required=True, dest="task_id")
    qr.add_argument("--by", required=True)
    qr.add_argument("--scenario", required=True)
    qr.add_argument("--result", required=True, choices=["pass", "fail"])
    qr.add_argument("--defect")
    qr.add_argument("--steps")
    qr.add_argument("--returned-to", dest="returned_to")
    qr.set_defaults(func=cmd_qa_result)

    rv = sub.add_parser("review-result", help="record a code/security review pass/reject")
    rv.add_argument("--task-id", type=int, required=True, dest="task_id")
    rv.add_argument("--type", required=True, choices=["code", "security"])
    rv.add_argument("--by", required=True)
    rv.add_argument("--result", required=True, choices=["pass", "reject"])
    rv.add_argument("--findings", nargs="*")
    rv.add_argument("--returned-to", dest="returned_to")
    rv.set_defaults(func=cmd_review_result)

    ho = sub.add_parser("handoff", help="record a structured handoff")
    ho.add_argument("--task-id", type=int, required=True, dest="task_id")
    ho.add_argument("--from-agent", required=True, dest="from_agent")
    ho.add_argument("--to-agent", required=True, dest="to_agent")
    ho.add_argument("--work-completed", dest="work_completed")
    ho.add_argument("--files", nargs="*")
    ho.add_argument("--tests-added", dest="tests_added")
    ho.add_argument("--expected-behavior", dest="expected_behavior")
    ho.add_argument("--known-limitations", dest="known_limitations")
    ho.add_argument("--checklist")
    ho.add_argument("--base-commit-sha", dest="base_commit_sha",
                     help="Phase 3A Part B (TASK-015): git rev-parse HEAD before this task's work "
                          "began — required for the automated Code Review poller to assemble a real "
                          "diff (§B.13); nullable, non-code handoffs may omit it")
    ho.add_argument("--head-commit-sha", dest="head_commit_sha",
                     help="Phase 3A Part B (TASK-015): git rev-parse HEAD at handoff time")
    ho.set_defaults(func=cmd_handoff)

    ac = sub.add_parser("approval-create", help="raise a Founder approval request")
    ac.add_argument("--task-id", type=int, dest="task_id")
    ac.add_argument("--request", required=True)
    ac.add_argument("--by", required=True)
    ac.add_argument("--why")
    ac.add_argument("--recommendation")
    ac.add_argument("--alternatives")
    ac.add_argument("--cost")
    ac.add_argument("--risks")
    ac.add_argument("--consequence")
    ac.set_defaults(func=cmd_approval_create)

    ad = sub.add_parser("approval-decide", help="record the Founder's decision (Founder-only — see --confirm-founder-decision)")
    ad.add_argument("--approval-id", type=int, required=True, dest="approval_id")
    ad.add_argument("--decision", required=True)
    ad.add_argument("--confirm-founder-decision", action="store_true", dest="confirm_founder_decision",
                     help="required — asserts this call is actually the Founder deciding, not an agent")
    ad.set_defaults(func=cmd_approval_decide)

    dr = sub.add_parser("decision-record", help="record a decision-log entry")
    dr.add_argument("--title", required=True)
    dr.add_argument("--problem")
    dr.add_argument("--options", nargs="*")
    dr.add_argument("--decision", required=True)
    dr.add_argument("--reason")
    dr.add_argument("--tradeoffs")
    dr.add_argument("--by", required=True)
    dr.add_argument("--founder-approval", action="store_true", dest="founder_approval")
    dr.add_argument("--approval-id", type=int, dest="approval_id")
    dr.set_defaults(func=cmd_decision_record)

    tps = sub.add_parser("task-purge-scratch", help="remove a self-labeled scratch task with zero real work attached")
    tps.add_argument("--task-id", type=int, required=True, dest="task_id")
    tps.add_argument("--confirm", action="store_true")
    tps.set_defaults(func=cmd_task_purge_scratch)

    dep = sub.add_parser("deployment-record", help="record a deployment (Founder authorization required)")
    dep.add_argument("--task-id", type=int, required=True, dest="task_id")
    dep.add_argument("--version", required=True)
    dep.add_argument("--environment", required=True)
    dep.add_argument("--release-notes", dest="release_notes")
    dep.add_argument("--rollback-plan", required=True, dest="rollback_plan")
    dep.add_argument("--by", required=True)
    dep.add_argument("--founder-authorized", action="store_true", dest="founder_authorized")
    dep.set_defaults(func=cmd_deployment_record)

    args = p.parse_args()
    if args.command != "init" and not DB_PATH.exists():
        raise SystemExit(f"error: {DB_PATH} does not exist — run `opsdb.py init` first")
    try:
        args.func(args)
    except sqlite3.IntegrityError as exc:
        # Most commonly a bad foreign key (e.g. --task-id for a task that
        # doesn't exist) or a CHECK constraint the schema enforces (e.g. an
        # unauthorized deployment). Surface it as a clean error, not a
        # traceback — the constraint itself is doing its job correctly.
        raise SystemExit(f"error: rejected by the database — {exc}") from None


if __name__ == "__main__":
    main()
