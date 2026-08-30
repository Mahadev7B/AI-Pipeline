#!/usr/bin/env python3
"""ops/control-center/generate_inbox.py — Phase 2, Milestone 2B1.

Founder Inbox: the first screen with real write actions
(Approve/Reject/Discuss). This module only ever READS the database —
build_html() renders forms that POST to /api/approvals/<id>/decide, which
only ops/control-center/server.py can serve; the write itself always goes
through opsdb.decide_approval(), never through this file. See
ops/reviews/cto-milestone2b1-architecture.md.

Two ways to use this module:
  - Live: server.py imports build_html(conn, token) and returns the
    string directly, with the current session token embedded in every
    form so a submission is provably a request the server itself served.
  - Static: `python3 generate_inbox.py` writes inbox.html with no token
    (forms are present but always fail closed — see the banner in the
    rendered page) — same as every other Control Center snapshot.

Usage:
    python3 ops/control-center/generate_inbox.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
from derived_state import display_name  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("inbox.html", "OPSDB_INBOX_PATH")

DECIDABLE = ("pending", "discuss")


def render_field(label: str, value: str | None) -> str:
    if not value:
        return ""
    return f'''
    <div style="margin-bottom:8px;">
      <div class="label" style="margin-bottom:2px;">{e(label)}</div>
      <div style="font-size:12px; color:var(--text);">{e(value)}</div>
    </div>'''


def render_actions(approval_id: int, decision: str, token: str | None) -> str:
    if decision not in DECIDABLE:
        return ""
    tok = e(token or "")

    def form(action: str, label: str, color: str) -> str:
        return f'''
        <form method="POST" action="/api/approvals/{approval_id}/decide" style="display:inline;">
          <input type="hidden" name="decision" value="{action}">
          <input type="hidden" name="token" value="{tok}">
          <button type="submit" style="padding:7px 16px; border-radius:7px; border:1px solid {color};
            background:{color}22; color:{color}; font-size:12px; font-weight:600; cursor:pointer;">{e(label)}</button>
        </form>'''

    buttons = [form("approve", "Approve", "var(--green)"), form("reject", "Reject", "var(--red)")]
    if decision == "pending":
        buttons.append(form("discuss", "Discuss", "var(--blue)"))
    return f'<div style="display:flex; gap:8px; margin-top:10px;">{"".join(buttons)}</div>'


def render_approval_card(a: sqlite3.Row, token: str | None) -> str:
    is_discuss = a["decision"] == "discuss"
    is_resolved = a["decision"] in ("approve", "reject")
    border = "var(--blue)" if is_discuss else ("var(--border2)")
    status_pill = ""
    if is_discuss:
        status_pill = '<span class="pill" style="background:var(--blue-soft); color:var(--blue);">Needs follow-up — Founder flagged for discussion</span>'
    elif is_resolved:
        color = "var(--green)" if a["decision"] == "approve" else "var(--red)"
        status_pill = f'<span class="pill" style="background:{color}22; color:{color};">{e(a["decision"].upper())} · {e(a["decided_at"] or "")}</span>'
    else:
        status_pill = '<span class="pill" style="background:var(--gray-soft); color:var(--text2);">Awaiting decision</span>'

    note = ""
    if is_discuss:
        note = ('<div style="font-size:11px; color:var(--text3); margin-top:8px;">'
                'Flagged for discussion — not an agent conversation yet (that\'s a later milestone). '
                'Still awaiting Approve or Reject.</div>')

    return f'''
    <div class="card" style="margin-bottom:12px; border-color:{border};">
      <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin-bottom:8px;">
        <div style="font-size:13px; font-weight:600;">{e(a["request"])}</div>
        {status_pill}
      </div>
      <div style="font-size:10.5px; color:var(--text3); margin-bottom:10px;">
        Requested by {e(display_name(a["requested_by_agent"]))}{f' · TASK-{a["task_id"]:03d}' if a["task_id"] else ""} · {e(a["created_at"])}
      </div>
      {render_field("Why", a["why"])}
      {render_field("Recommendation", a["recommendation"])}
      {render_field("Alternatives considered", a["alternatives_considered"])}
      {render_field("Expected cost", a["expected_cost"])}
      {render_field("Risks", a["risks"])}
      {render_field("Consequence if not approved", a["consequence_if_not_approved"])}
      {note}
      {render_actions(a["id"], a["decision"], token)}
    </div>'''


def build_html(conn: sqlite3.Connection, token: str | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = conn.execute(
        "SELECT id, task_id, request, requested_by_agent, why, recommendation, "
        "alternatives_considered, expected_cost, risks, consequence_if_not_approved, "
        "decision, decided_at, created_at FROM approvals ORDER BY id DESC"
    ).fetchall()

    pending = [a for a in rows if a["decision"] == "pending"]
    discuss = [a for a in rows if a["decision"] == "discuss"]
    resolved = [a for a in rows if a["decision"] in ("approve", "reject")]

    banner = ""
    if token is None:
        banner = ('<div class="panel" style="margin-bottom:14px; border-color:var(--accent);">'
                   '<div style="font-size:11.5px; color:var(--text2);">'
                   'This is a static, point-in-time snapshot. Approve/Reject/Discuss only work when '
                   '<span class="mono">python3 ops/control-center/server.py</span> is running locally — '
                   'this file has no active session token, so any submission from it fails closed.</div></div>')

    def section(title: str, items: list, empty_text: str) -> str:
        body = "".join(render_approval_card(a, token) for a in items) or f'<div style="font-size:12px; color:var(--text2);">{e(empty_text)}</div>'
        return f'''
        <div style="margin-bottom:20px;">
          <div class="label" style="margin-bottom:10px;">{e(title)} <span class="mono" style="color:var(--text3);">· {len(items)}</span></div>
          {body}
        </div>'''

    body = f'''
<h1>Founder Inbox</h1>
<div class="sub" style="margin-top:-14px;">Real pending approvals from the <span class="mono">approvals</span> table. Approve/Reject are final; Discuss leaves the item visibly open for follow-up.</div>
{banner}
{section("Awaiting decision", pending, "Nothing pending.")}
{section("Needs follow-up", discuss, "Nothing flagged for discussion.")}
{section("Resolved", resolved, "No approvals decided yet.")}'''
    return page("Inbox", "inbox.html", body,
                generated_note=f"Generated {now} from the live operational database. Re-run this script (or load via server.py) to refresh.")


def main() -> None:
    conn = connect()
    write_output(OUT_PATH, build_html(conn, token=None))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
