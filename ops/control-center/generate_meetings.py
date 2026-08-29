#!/usr/bin/env python3
"""ops/control-center/generate_meetings.py — Phase 2, Milestones 2A + 2B3B.

Executive Meetings / Discussions history (2A, read-only list) plus real
meeting creation and per-meeting detail (2B3B) — see
ops/EXECUTIVE_MEETINGS.md for the design and
ops/reviews/cto-milestone2b3b-architecture.md for how it's actually
wired. This module only ever READS the database — the real work
(participant selection, gathering positions, synthesis) lives in
meeting_orchestrator.py; the write itself always goes through
server.py's POST /api/meetings and POST /api/meetings/<id>/decide,
gated by the same session token every other write route uses.

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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402
from agent_runtime import MEETING_PARTICIPANT_ALLOWLIST  # noqa: E402 — Milestone 2B3B

OUT_PATH = out_path("meetings.html", "OPSDB_MEETINGS_PATH")
MAX_TOPIC_CHARS = 2_000  # kept in sync with meeting_orchestrator.MAX_TOPIC_CHARS — see that module


def json_list(raw: str) -> list:
    try:
        val = json.loads(raw or "[]")
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def is_ceo(name: str) -> bool:
    return name == "ceo"


def render_raise_question_form(token: str | None) -> str:
    if token is None:
        return ('<div class="panel" style="margin-bottom:16px; border-color:var(--accent);">'
                 '<div style="font-size:11.5px; color:var(--text2);">'
                 'Raising a question requires <span class="mono">python3 ops/control-center/server.py</span> '
                 'running locally — this static file has no active session token.</div></div>')
    return f'''
    <form method="POST" action="/api/meetings" style="margin-bottom:16px;">
      <input type="hidden" name="token" value="{e(token)}">
      <div class="panel">
        <div class="label" style="margin-bottom:8px;">Raise a question for an Executive Meeting</div>
        <div style="display:flex; gap:10px; align-items:center;">
          <input type="text" name="topic" placeholder="e.g. Should we add rate limiting before launch?" maxlength="{MAX_TOPIC_CHARS}" required
                 style="flex:1; padding:10px 14px; border-radius:9px; background:var(--panel2); border:1px solid var(--border2); color:var(--text); font-size:12.5px;">
          <button type="submit" style="padding:10px 18px; border-radius:9px; background:var(--accent); border:none; font-size:12px; font-weight:700; color:#1a1206; cursor:pointer;">Raise</button>
        </div>
        <div style="font-size:10.5px; color:var(--text3); margin-top:8px;">
          CEO Agent selects who else should weigh in from {len(MEETING_PARTICIPANT_ALLOWLIST) - 1} candidate roles, gathers real
          positions, and synthesizes a recommendation — this runs for real and can take up to ~2 minutes.
        </div>
      </div>
    </form>'''


def render_meetings(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, topic, initiated_by, participating_agents, recommendation, "
        "founder_decision, created_at FROM meetings ORDER BY id DESC"
    ).fetchall()
    if not rows:
        return '''
        <div class="panel" style="text-align:center; padding:40px 20px;">
          <div style="font-size:13px; font-weight:600; margin-bottom:6px;">No executive meetings recorded yet.</div>
          <div style="font-size:11.5px; color:var(--text2);">
            Raise a question above and it will appear here with each participant's real position,
            agreements/disagreements, and the Founder's decision.</div>
        </div>'''
    items = []
    for m in rows:
        participants = ", ".join(e(a) for a in json_list(m["participating_agents"])) or "—"
        decided = ('<span class="pill" style="background:var(--green-soft); color:var(--green);">Decided</span>'
                   if m["founder_decision"] else
                   '<span class="pill" style="background:var(--accent-soft); color:var(--accent);">Open</span>')
        items.append(f'''
        <a href="meetings/{m["id"]}.html" class="card" style="display:block; margin-bottom:10px;">
          <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px;">
            <div style="font-size:13px; font-weight:600;">#{m["id"]} — {e(m["topic"])}</div>
            {decided}
          </div>
          <div style="font-size:11px; color:var(--text3); margin-bottom:8px;">Raised by {e("Founder" if m["initiated_by"] == "founder" else m["initiated_by"])} · participants: {participants} · {e(m["created_at"])}</div>
          {f'<div style="font-size:11.5px; color:var(--text2);"><b style="color:var(--text);">Recommendation:</b> {e(m["recommendation"])}</div>' if m["recommendation"] else '<div style="font-size:11px; color:var(--text3);">No recommendation yet.</div>'}
        </a>''')
    return "".join(items)


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = f'''
<h1>Meetings</h1>
<div class="sub" style="margin-top:-14px;">Executive discussion history, from the <span class="mono">meetings</span> table.</div>
{render_raise_question_form(token)}
{render_meetings(conn)}'''
    return page("Meetings", "meetings.html", body,
                generated_note=f"Generated {now} from the live operational database. Re-run this script (or load via server.py) to refresh.")


# ---------------------------------------------------------- meeting detail --

def render_position_card(agent_name: str, body_text: str) -> str:
    if is_ceo(agent_name):
        style = "border-style:dashed; border-color:var(--violet); background:var(--violet-soft);"
        label_color = "var(--violet)"
        label_suffix = " · AI ADVISOR"
    elif agent_name == "red-team":
        style = "border-color:oklch(66% 0.17 25 / 0.35); background:var(--red-soft);"
        label_color = "var(--red)"
        label_suffix = ""
    else:
        style = ""
        label_color = "var(--text2)"
        label_suffix = ""
    return f'''
    <div class="card" style="{style}">
      <div style="font-size:10.5px; font-weight:700; color:{label_color}; margin-bottom:5px; text-transform:uppercase;">{e(agent_name)}{label_suffix}</div>
      <div style="font-size:12px; color:var(--text2); line-height:1.5;">{e(body_text)}</div>
    </div>'''


def build_meeting_detail(conn: sqlite3.Connection, meeting: sqlite3.Row, token: str | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    participants = json_list(meeting["participating_agents"])

    positions = conn.execute(
        "SELECT from_agent, body FROM messages WHERE meeting_id = ? ORDER BY id",
        (meeting["id"],),
    ).fetchall()
    positions_by_agent = {p["from_agent"]: p["body"] for p in positions}

    cards = []
    for name in participants:
        if name in positions_by_agent:
            cards.append(render_position_card(name, positions_by_agent[name]))
        else:
            # Selected but no real position was gathered — an honest absence
            # (invocation failed), never a fabricated position. Red Team's
            # Milestone 2B3B condition 6.
            cards.append(f'''
            <div class="card" style="border-color:var(--border2); opacity:0.6;">
              <div style="font-size:10.5px; font-weight:700; color:var(--text3); margin-bottom:5px; text-transform:uppercase;">{e(name)}</div>
              <div style="font-size:12px; color:var(--text3); font-style:italic;">Selected, but no response was recorded (the real invocation did not succeed).</div>
            </div>''')

    grid = f'<div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:11px; margin-bottom:16px;">{"".join(cards)}</div>'

    synthesis_html = ""
    if any(meeting[f] for f in ("agreements", "disagreements", "unresolved_questions", "recommendation")):
        synthesis_html = f'''
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px; padding-top:14px; border-top:1px solid var(--border);">
          <div>
            <div class="label" style="margin-bottom:6px; color:var(--green);">Areas of agreement</div>
            <div style="font-size:12px; color:var(--text2); line-height:1.55;">{e(meeting["agreements"]) if meeting["agreements"] else '<span style="color:var(--text3);">Not available.</span>'}</div>
          </div>
          <div>
            <div class="label" style="margin-bottom:6px; color:var(--red);">Areas of disagreement</div>
            <div style="font-size:12px; color:var(--text2); line-height:1.55;">{e(meeting["disagreements"]) if meeting["disagreements"] else '<span style="color:var(--text3);">Not available.</span>'}</div>
          </div>
          <div>
            <div class="label" style="margin-bottom:6px;">Unresolved questions</div>
            <div style="font-size:12px; color:var(--text2); line-height:1.55;">{e(meeting["unresolved_questions"]) if meeting["unresolved_questions"] else '<span style="color:var(--text3);">Not available.</span>'}</div>
          </div>
          <div>
            <div class="label" style="margin-bottom:6px; color:var(--accent);">CEO recommendation</div>
            <div style="font-size:12px; color:var(--text2); line-height:1.55;">{e(meeting["recommendation"]) if meeting["recommendation"] else '<span style="color:var(--text3);">Not available.</span>'}</div>
          </div>
        </div>'''
    else:
        synthesis_html = '<div class="panel" style="margin-bottom:20px;"><div style="font-size:12px; color:var(--text2);">No synthesis available — the synthesis step did not complete.</div></div>'

    if meeting["founder_decision"]:
        decision_html = f'''
        <div style="border-radius:13px; border:1px solid var(--green); background:var(--green-soft); padding:18px;">
          <div class="label" style="margin-bottom:8px; color:var(--green);">Founder decision</div>
          <div style="font-size:12.5px; color:var(--text);">{e(meeting["founder_decision"])}</div>
          {f'<div style="font-size:10.5px; color:var(--text3); margin-top:8px;">Logged as decision #{meeting["linked_decision_id"]} in the operational record.</div>' if meeting["linked_decision_id"] else ""}
        </div>'''
    elif token is not None:
        decision_html = f'''
        <form method="POST" action="/api/meetings/{meeting["id"]}/decide">
          <input type="hidden" name="token" value="{e(token)}">
          <div style="border-radius:13px; border:1px solid var(--accent); background:var(--accent-soft); padding:18px;">
            <div class="label" style="margin-bottom:10px; color:var(--accent);">Founder decision</div>
            <textarea name="decision" required maxlength="4000" rows="3" placeholder="What did you decide, and why?"
                      style="width:100%; box-sizing:border-box; padding:10px 14px; border-radius:9px; background:var(--panel2); border:1px solid var(--border2); color:var(--text); font-size:12.5px; margin-bottom:10px; resize:vertical;"></textarea>
            <div style="display:flex; align-items:center; justify-content:space-between;">
              <div style="font-size:11px; color:var(--text2);">Confirming logs this decision to the operational record — an ID is assigned automatically.</div>
              <button type="submit" style="padding:9px 20px; border-radius:9px; background:var(--accent); border:none; font-size:12.5px; font-weight:700; color:#1a1206; cursor:pointer;">Confirm decision</button>
            </div>
          </div>
        </form>'''
    else:
        decision_html = ('<div class="panel" style="border-color:var(--accent);"><div style="font-size:11.5px; color:var(--text2);">'
                          'Deciding requires python3 ops/control-center/server.py running locally.</div></div>')

    body = f'''
<div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
  <a href="../meetings.html" style="font-size:12px; color:var(--text3);">&larr; Meetings</a>
</div>
<div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:16px;">
  <h1 style="margin:0;">{e(meeting["topic"])}</h1>
  <div style="font-size:11px; color:var(--text3);">Raised by {e("Founder" if meeting["initiated_by"] == "founder" else meeting["initiated_by"])} &middot; {e(meeting["created_at"])}</div>
</div>
{grid}
{synthesis_html}
{decision_html}'''
    return page(f"Meeting #{meeting['id']}", "meetings.html", body, depth=1,
                generated_note=f"Generated {now} from the live operational database. Re-run generate_meetings.py (or load via server.py) to refresh.")


def main() -> None:
    conn = connect()
    write_output(OUT_PATH, build_html(token=None))
    print(f"wrote {OUT_PATH}")

    meetings_subdir = OUT_PATH.parent / "meetings"
    meetings_subdir.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("SELECT * FROM meetings ORDER BY id").fetchall()
    for m in rows:
        write_output(meetings_subdir / f"{m['id']}.html", build_meeting_detail(conn, m, token=None))
    print(f"wrote {len(rows)} meeting detail pages under {meetings_subdir}")


if __name__ == "__main__":
    main()
