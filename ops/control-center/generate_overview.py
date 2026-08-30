#!/usr/bin/env python3
"""ops/control-center/generate_overview.py — Phase 2, Milestone 1
(refactored onto the shared layout/dbutil modules in Milestone 2A —
disclosed in ops/reviews/cto-milestone2a-architecture.md; no content or
behavior change, only where the chrome/connection boilerplate lives).

Generates a static, read-only Overview page from the real operational
database. Every number and status is computed by ops/db/derived_state.py
— never hand-written or invented. See ops/ARCHITECTURE.md, "Derived UI
state must be deterministic."

Usage:
    python3 ops/control-center/generate_overview.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
from derived_state import agent_status_rows, company_health, display_name, scope_label, task_progress_fraction  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("overview.html", "OPSDB_OVERVIEW_PATH")

HEALTH_COLOR = {"Good": "var(--green)", "Fair": "var(--accent)", "Poor": "var(--red)"}
STATUS_COLOR = {
    "active": "var(--accent)", "waiting": "var(--blue)",
    "blocked": "var(--red)", None: "var(--gray)",
}


def render_active_now(conn: sqlite3.Connection) -> str:
    rows = [r for r in agent_status_rows(conn) if r["status"] is not None]
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No agent currently has an open run.</div>'
    items = []
    for r in rows:
        color = STATUS_COLOR.get(r["status"], "var(--gray)")
        items.append(f'''
        <a href="agents/{e(r["name"])}.html" style="display:flex; align-items:center; gap:11px; padding:9px 11px; border-radius:10px; background:var(--panel2);">
          <div style="width:8px; height:8px; border-radius:50%; background:{color}; flex-shrink:0;"></div>
          <div style="flex:1; min-width:0;">
            <div style="font-size:12.5px; font-weight:600;">{e(display_name(r["name"]))}</div>
            <div style="font-size:11.5px; color:var(--text2);">{e(r["current_activity"] or "")}</div>
          </div>
          <div style="font-size:10px; color:var(--text3); flex-shrink:0;">{e(r["status"])} · {e(scope_label(r["scope_type"], r["scope_id"]))}</div>
        </a>''')
    return "".join(items)


def render_pipeline(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, title, status, current_owner FROM tasks "
        "WHERE status != 'DONE' ORDER BY id"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No open tasks.</div>'
    items = []
    for t in rows:
        frac = task_progress_fraction(conn, t["id"])
        if frac is None:
            pct, label = 0, "not broken into steps"
        else:
            done, total = frac
            pct = round(100 * done / total)
            label = f"{pct}%"
        items.append(f'''
        <div style="display:flex; align-items:center; gap:10px;">
          <div style="width:170px; font-size:12px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">TASK-{t["id"]:03d} — {e(t["title"])}</div>
          <div style="flex:1; height:6px; border-radius:3px; background:var(--border2); overflow:hidden;"><div style="width:{pct}%; height:100%; background:var(--accent);"></div></div>
          <div style="width:70px; font-size:11px; color:var(--text2); text-align:right;">{e(label)}</div>
          <div style="width:110px; font-size:11px; color:var(--text3);">{e(t["status"])}</div>
        </div>''')
    return "".join(items)


def render_activity(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT a.name AS agent, x.summary, x.created_at FROM agent_activity x "
        "JOIN agents a ON a.id = x.agent_id ORDER BY x.id DESC LIMIT 8"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No activity recorded yet.</div>'
    items = []
    for r in rows:
        items.append(f'''
        <div style="display:flex; gap:8px;">
          <div style="font-size:11.5px; color:var(--text2);"><b style="color:var(--text);">{e(display_name(r["agent"]))}</b> — {e(r["summary"])}</div>
        </div>''')
    return "".join(items)


def render_inbox(conn: sqlite3.Connection) -> str:
    # Milestone 2B1: the real Approve/Reject/Discuss actions live on their
    # own screen (inbox.html) — see ops/reviews/cto-milestone2b1-architecture.md,
    # "Where the Inbox lives." This panel is a summary-plus-link, the same
    # pattern Active Now uses for Agent Detail — no write forms duplicated
    # here, so there is exactly one place a decision can be made.
    rows = conn.execute(
        "SELECT id, request, requested_by_agent, decision FROM approvals "
        "WHERE decision IN ('pending','discuss') ORDER BY id"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">Nothing pending.</div>'
    items = []
    for r in rows[:4]:
        note = "flagged for discussion" if r["decision"] == "discuss" else "not yet decided"
        items.append(f'''
        <a href="inbox.html" class="card" style="display:block;">
          <div style="font-size:12px; font-weight:600; margin-bottom:3px;">{e(r["request"])}</div>
          <div style="font-size:11px; color:var(--text2);">Requested by {e(display_name(r["requested_by_agent"]))} · {e(note)}</div>
        </a>''')
    more = ""
    if len(rows) > 4:
        more = f'<a href="inbox.html" style="font-size:11px; color:var(--accent);">+{len(rows) - 4} more in Inbox</a>'
    return "".join(items) + more


def build_html() -> str:
    conn = connect()
    health_label, health_detail = company_health(conn)
    health_color = HEALTH_COLOR.get(health_label, "var(--text)")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = f"""
<h1>Overview <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
<div class="panel" style="margin-bottom:14px;">
  <div class="label" style="margin-bottom:6px;">Company Health</div>
  <div style="font-size:20px; font-weight:600; color:{health_color};">{e(health_label)}</div>
  <div style="font-size:11.5px; color:var(--text2); margin-top:2px;">{e(health_detail)}</div>
</div>
<div style="display:grid; grid-template-columns:1fr 1fr; gap:14px;">
  <div class="panel">
    <div class="label" style="margin-bottom:10px;">Active Now</div>
    <div style="display:flex; flex-direction:column; gap:10px;">{render_active_now(conn)}</div>
  </div>
  <div class="panel">
    <div class="label" style="margin-bottom:10px;">Founder Inbox</div>
    <div style="display:flex; flex-direction:column; gap:10px;">{render_inbox(conn)}</div>
  </div>
  <div class="panel" style="grid-column:1 / -1;">
    <div class="label" style="margin-bottom:10px;">Pipeline Snapshot</div>
    <div style="display:flex; flex-direction:column; gap:10px;">{render_pipeline(conn)}</div>
  </div>
  <div class="panel" style="grid-column:1 / -1;">
    <div class="label" style="margin-bottom:10px;">Just Happened</div>
    <div style="display:flex; flex-direction:column; gap:10px;">{render_activity(conn)}</div>
  </div>
</div>"""
    return page("Overview", "overview.html", body,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
