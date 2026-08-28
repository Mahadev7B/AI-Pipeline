#!/usr/bin/env python3
"""ops/db/opsdb.py — the only supported way to read or write the Phase 1
operational database (ops/db/operations.sqlite3).

Zero third-party dependencies (Python 3 standard library only). Every
write goes through a parameterized query — never string-built SQL — and
every connection enables foreign-key enforcement, per the Red Team
review (ops/reviews/red-team-schema.md).

Usage:
    python3 ops/db/opsdb.py init
    python3 ops/db/opsdb.py <command> [--flag value ...]

Run `python3 ops/db/opsdb.py --help` for the full command list, or
`python3 ops/db/opsdb.py <command> --help` for one command's flags.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent
DB_PATH = DB_DIR / "operations.sqlite3"
SCHEMA_PATH = DB_DIR / "schema.sql"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def cmd_project_create(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO projects (name, description, status) VALUES (?, ?, ?)",
            (args.name, args.description, args.status),
        )
    print(f"project created: id={cur.lastrowid} — {args.name}")


def cmd_init(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.executescript(SCHEMA_PATH.read_text())
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


def cmd_task_status(args: argparse.Namespace) -> None:
    if args.to not in VALID_STATUSES:
        raise SystemExit(f"error: invalid status '{args.to}' — must be one of {VALID_STATUSES}")
    conn = connect()
    with conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (args.task_id,)).fetchone()
        if row is None:
            raise SystemExit(f"error: no such task TASK-{args.task_id:03d}")
        conn.execute(
            "UPDATE tasks SET status = ?, current_owner = COALESCE(?, current_owner), "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (args.to, args.owner, args.task_id),
        )
        conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, "
            "changed_by_agent, note) VALUES (?, ?, ?, ?, ?)",
            (args.task_id, row["status"], args.to, args.by, args.note),
        )
    print(f"TASK-{args.task_id:03d}: {row['status']} -> {args.to}")


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

def cmd_run_start(args: argparse.Namespace) -> None:
    conn = connect()
    agent_id = _agent_id(conn, args.agent)
    if args.scope_type == "company" and args.scope_id is not None:
        raise SystemExit("error: company-scoped runs must not set --scope-id")
    if args.scope_type != "company" and args.scope_id is None:
        raise SystemExit("error: non-company scope requires --scope-id")
    with conn:
        cur = conn.execute(
            "INSERT INTO agent_runs (agent_id, scope_type, scope_id, status, current_activity) "
            "VALUES (?, ?, ?, 'active', ?)",
            (agent_id, args.scope_type, args.scope_id, args.activity),
        )
    print(f"run started: id={cur.lastrowid} agent={args.agent} scope={args.scope_type}:{args.scope_id}")


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


def cmd_run_end(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE agent_runs SET status = 'ended', "
            "ended_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (args.run_id,),
        )
    print(f"run {args.run_id}: ended")


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


def cmd_review_result(args: argparse.Namespace) -> None:
    if args.result == "reject" and not args.returned_to:
        raise SystemExit("error: a reject result must set --returned-to")
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO review_results (task_id, review_type, reviewed_by_agent, result, "
            "findings, returned_to_agent) VALUES (?, ?, ?, ?, ?, ?)",
            (args.task_id, args.type, args.by, args.result,
             json.dumps(args.findings or []), args.returned_to),
        )
    print(f"{args.type} review recorded: {args.result}")


def cmd_handoff(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO handoffs (task_id, from_agent, to_agent, work_completed, "
            "files_changed, tests_added, expected_behavior, known_limitations, "
            "receiving_agent_checklist) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (args.task_id, args.from_agent, args.to_agent, args.work_completed,
             json.dumps(args.files or []), args.tests_added, args.expected_behavior,
             args.known_limitations, args.checklist),
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


def cmd_approval_decide(args: argparse.Namespace) -> None:
    if args.decision not in ("approve", "reject", "discuss"):
        raise SystemExit("error: decision must be approve, reject, or discuss")
    if not args.confirm_founder_decision:
        raise SystemExit(
            "error: refusing to record a Founder decision without "
            "--confirm-founder-decision. This CLI has no real identity check "
            "(any caller can pass this flag) — it exists so an agent's normal "
            "workflow can never casually decide its own approval request; a "
            "human deciding through the Control Center is the real control, "
            "not this flag. See ops/DATA_MODEL.md, Rules."
        )
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE approvals SET decision = ?, "
            "decided_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (args.decision, args.approval_id),
        )
    print(f"approval {args.approval_id}: {args.decision}")


def cmd_decision_record(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO decisions (title, date, problem, options_considered, decision, "
            "reason, tradeoffs, recommending_agent, founder_approval_required, "
            "founder_approval_id) VALUES (?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?)",
            (args.title, args.problem, json.dumps(args.options or []), args.decision,
             args.reason, args.tradeoffs, args.by, 1 if args.founder_approval else 0,
             args.approval_id),
        )
    print(f"decision recorded: id={cur.lastrowid} — {args.title}")


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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database from schema.sql (idempotent)").set_defaults(func=cmd_init)

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
    re_.set_defaults(func=cmd_run_end)

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
