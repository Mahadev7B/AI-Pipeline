#!/usr/bin/env python3
"""ops/db/report.py — generates CURRENT_STATUS.md from the operational
database. Read-only. Zero third-party dependencies.

Company Health, agent status, and task progress are computed here using
exactly the formulas documented in DATA_MODEL.md, "Deterministic derived
state" — never invented text. See ops/ARCHITECTURE.md, "Derived UI state
must be deterministic."

Usage:
    python3 ops/db/report.py             # regenerate CURRENT_STATUS.md
    python3 ops/db/report.py --check     # exit 1 if the committed file is
                                          # stale vs. the live database —
                                          # no write. See "Release checklist"
                                          # in ops/AGENT_STATUS.md: a task
                                          # does not move to DONE until this
                                          # passes.

Respects OPSDB_PATH (see ops/db/README.md) — when testing this script
against a scratch database, the report is written next to that scratch
database instead of overwriting the real ops/reports/CURRENT_STATUS.md,
unless OPSDB_REPORT_PATH is set explicitly.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derived_state import (  # noqa: E402 — see sys.path.insert above
    agent_status_rows,
    company_health,
    scope_label,
    task_progress_pct,
)

DB_DIR = Path(__file__).resolve().parent
_default_db = DB_DIR / "operations.sqlite3"
_using_scratch_db = bool(os.environ.get("OPSDB_PATH"))
DB_PATH = Path(os.environ["OPSDB_PATH"]) if _using_scratch_db else _default_db

if os.environ.get("OPSDB_REPORT_PATH"):
    REPORT_PATH = Path(os.environ["OPSDB_REPORT_PATH"])
elif _using_scratch_db:
    REPORT_PATH = DB_PATH.with_name(DB_PATH.stem + ".CURRENT_STATUS.md")
else:
    REPORT_PATH = DB_DIR.parent / "reports" / "CURRENT_STATUS.md"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_report() -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    health_label, health_detail = company_health(conn)

    lines: list[str] = []
    lines.append("# CURRENT_STATUS.md")
    lines.append("")
    lines.append(f"Generated {now} by `ops/db/report.py` from the live database — "
                  "do not hand-edit; re-run the script instead.")
    lines.append("")
    lines.append(f"## Company Health: {health_label}")
    lines.append(f"{health_detail}")
    lines.append("")

    lines.append("## Completed")
    done = conn.execute("SELECT id, title FROM tasks WHERE status = 'DONE' ORDER BY id").fetchall()
    if done:
        for t in done:
            lines.append(f"- TASK-{t['id']:03d} — {t['title']}")
    else:
        lines.append("- none yet")
    lines.append("")

    lines.append("## In progress")
    in_progress = conn.execute(
        "SELECT id, title, status, current_owner FROM tasks "
        "WHERE status NOT IN ('DONE','BACKLOG','BLOCKED') ORDER BY id"
    ).fetchall()
    if in_progress:
        for t in in_progress:
            pct = task_progress_pct(conn, t["id"])
            lines.append(f"- TASK-{t['id']:03d} — {t['title']} ({t['status']}, "
                          f"owner: {t['current_owner'] or '—'}, progress: {pct})")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Blocked")
    blocked = conn.execute("SELECT id, title, blockers FROM tasks WHERE status = 'BLOCKED'").fetchall()
    if blocked:
        for t in blocked:
            lines.append(f"- TASK-{t['id']:03d} — {t['title']}: {t['blockers'] or 'no reason recorded'}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Waiting (Backlog)")
    backlog = conn.execute("SELECT id, title FROM tasks WHERE status = 'BACKLOG'").fetchall()
    if backlog:
        for t in backlog:
            lines.append(f"- TASK-{t['id']:03d} — {t['title']}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## QA failures (unresolved)")
    qa_fails = conn.execute(
        "SELECT q.task_id, q.scenario, q.defect_summary, q.returned_to_agent "
        "FROM qa_results q "
        "JOIN tasks t ON t.id = q.task_id "
        "WHERE q.result = 'fail' AND t.status != 'DONE' "
        "AND q.id = (SELECT MAX(id) FROM qa_results WHERE task_id = q.task_id)"
    ).fetchall()
    if qa_fails:
        for r in qa_fails:
            lines.append(f"- TASK-{r['task_id']:03d} — {r['scenario']}: {r['defect_summary']} "
                          f"(returned to {r['returned_to_agent']})")
    else:
        lines.append("- none open")
    lines.append("")

    lines.append("## Current risks (open)")
    risks = conn.execute(
        "SELECT id, scope_type, scope_id, title, severity, owner_agent "
        "FROM risks WHERE status = 'open' ORDER BY "
        "CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"
    ).fetchall()
    if risks:
        for r in risks:
            lines.append(f"- [{r['severity']}] {r['title']} ({scope_label(r['scope_type'], r['scope_id'])}, "
                          f"owner: {r['owner_agent'] or '—'})")
    else:
        lines.append("- none open")
    lines.append("")

    lines.append("## Founder decisions required")
    pending = conn.execute("SELECT id, request, requested_by_agent FROM approvals WHERE decision = 'pending'").fetchall()
    founder_status = conn.execute("SELECT id, title FROM tasks WHERE status = 'FOUNDER_APPROVAL'").fetchall()
    if pending or founder_status:
        for a in pending:
            lines.append(f"- Approval #{a['id']} — {a['request']} (requested by {a['requested_by_agent']})")
        for t in founder_status:
            lines.append(f"- TASK-{t['id']:03d} — {t['title']} is waiting at FOUNDER_APPROVAL")
    else:
        lines.append("- none pending")
    lines.append("")

    lines.append("## Agents")
    for row in agent_status_rows(conn):
        if row["status"] is None:
            lines.append(f"- {row['name']}: available")
        else:
            lines.append(f"- {row['name']}: {row['status']} "
                          f"({scope_label(row['scope_type'], row['scope_id'])}) — {row['current_activity'] or ''}")
    lines.append("")

    return "\n".join(lines) + "\n"


def _content_ignoring_generated_line(text: str) -> str:
    """Strip the one line that legitimately changes on every run (the
    'Generated <timestamp>...' line) so a --check comparison only flags
    real drift in the DB-derived content, not the mere passage of time."""
    return "\n".join(line for line in text.splitlines() if not line.startswith("Generated "))


def check() -> bool:
    """Returns True if REPORT_PATH already matches what build_report()
    would produce right now (content-wise, ignoring the timestamp line).
    Never writes."""
    fresh = build_report()
    if not REPORT_PATH.exists():
        print(f"STALE: {REPORT_PATH} does not exist yet — run `python3 ops/db/report.py` to create it.")
        return False
    committed = REPORT_PATH.read_text()
    if _content_ignoring_generated_line(committed) != _content_ignoring_generated_line(fresh):
        print(f"STALE: {REPORT_PATH} does not match the live database — "
              f"run `python3 ops/db/report.py` and commit the result.")
        return False
    print(f"OK: {REPORT_PATH} matches the live database.")
    return True


def main() -> None:
    if "--check" in sys.argv[1:]:
        sys.exit(0 if check() else 1)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report())
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
