#!/usr/bin/env python3
"""ops/control-center/generate_meetings.py — Phase 2, Milestone 2A.

Executive Meetings / Discussions history. First-class nav destination
per the Founder's explicit instruction — ships even though `meetings`
currently has zero rows, rendering a real empty state rather than
inventing a sample meeting to make the screen "look right." See
ops/reviews/cto-milestone2a-architecture.md, "Decisions and Meetings:
honest about what's really in the database."

Usage:
    python3 ops/control-center/generate_meetings.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("meetings.html", "OPSDB_MEETINGS_PATH")


def json_list(raw: str) -> list:
    try:
        val = json.loads(raw or "[]")
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def render_meetings(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, topic, initiated_by, participating_agents, agreements, "
        "disagreements, recommendation, founder_decision, created_at "
        "FROM meetings ORDER BY id DESC"
    ).fetchall()
    if not rows:
        return '''
        <div class="panel" style="text-align:center; padding:40px 20px;">
          <div style="font-size:13px; font-weight:600; margin-bottom:6px;">No executive meetings recorded yet.</div>
          <div style="font-size:11.5px; color:var(--text2);">
            When the Founder or an agent raises a cross-cutting question, it will appear here with each
            participant's position, agreements/disagreements, and the Founder's decision — see
            ops/EXECUTIVE_MEETINGS.md for the design. Meeting creation is not part of this milestone.
          </div>
        </div>'''
    items = []
    for m in rows:
        participants = ", ".join(e(a) for a in json_list(m["participating_agents"])) or "—"
        decided = (f'<span class="pill" style="background:var(--green-soft); color:var(--green);">Decided</span>'
                   if m["founder_decision"] else
                   '<span class="pill" style="background:var(--accent-soft); color:var(--accent);">Open</span>')
        items.append(f'''
        <div class="card" style="margin-bottom:10px;">
          <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px;">
            <div style="font-size:13px; font-weight:600;">#{m["id"]} — {e(m["topic"])}</div>
            {decided}
          </div>
          <div style="font-size:11px; color:var(--text3); margin-bottom:8px;">Initiated by {e(m["initiated_by"])} · participants: {participants}</div>
          {f'<div style="font-size:11.5px; color:var(--green); margin-bottom:4px;"><b>Agreement:</b> {e(m["agreements"])}</div>' if m["agreements"] else ""}
          {f'<div style="font-size:11.5px; color:var(--red); margin-bottom:4px;"><b>Disagreement:</b> {e(m["disagreements"])}</div>' if m["disagreements"] else ""}
          {f'<div style="font-size:11.5px; color:var(--text2); margin-bottom:4px;"><b style="color:var(--text);">Recommendation:</b> {e(m["recommendation"])}</div>' if m["recommendation"] else ""}
          {f'<div style="font-size:11.5px; color:var(--text2);"><b style="color:var(--text);">Founder decision:</b> {e(m["founder_decision"])}</div>' if m["founder_decision"] else ""}
        </div>''')
    return "".join(items)


def build_html() -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = f'''
<h1>Meetings <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
<div class="sub" style="margin-top:-14px;">Executive discussion history, from the <span class="mono">meetings</span> table. Meeting creation is not part of this milestone.</div>
{render_meetings(conn)}'''
    return page("Meetings", "meetings.html", body,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
