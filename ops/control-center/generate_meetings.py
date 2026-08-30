#!/usr/bin/env python3
"""ops/control-center/generate_meetings.py — Phase 2, Milestones 2A + 2B3B
(+ round 2, TASK-011).

Executive Meetings / Discussions history (2A, read-only list) plus real
meeting creation and per-meeting detail (2B3B) — see
ops/EXECUTIVE_MEETINGS.md for the design and
ops/reviews/cto-milestone2b3b-architecture.md for how it's actually
wired. This module only ever READS the database — the real work
(participant selection, gathering positions, synthesis) lives in
meeting_orchestrator.py; the write itself always goes through
server.py's POST /api/meetings, POST /api/meetings/<id>/decide, and (2B3B
round 2) POST /api/meetings/<id>/{request-perspective,followup,retry},
gated by the same session token every other write route uses.

Milestone 2B3B round 2 additions: the Orchestrator validation note (item
1), a "requested by" marker + the request-perspective affordance (item
2), the per-participant follow-up thread + reply form (item 3), and a
Retry affordance on a no-position card (item 5). See
ops/reviews/cto-milestone2b3b-round2-architecture.md and
ops/reviews/red-team-milestone2b3b-round2.md.

Usage:
    python3 ops/control-center/generate_meetings.py
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
from agent_runtime import (  # noqa: E402 — Milestone 2B3B(+round 2)
    MEETING_PARTICIPANT_ALLOWLIST, MAX_MEETING_PARTICIPANTS, MAX_RETRIES_PER_PARTICIPANT,
)
import opsdb  # noqa: E402 — Milestone 2B3B round 2: normalized_participants() is the only correct way to read
              # meetings.participating_agents now that it may hold either the old flat-string shape or the new
              # {"name","source","requested_by"} object shape (see opsdb._normalize_participant()'s docstring).
              # generate_meetings.py's own former json_list() helper read this column raw — that's exactly the
              # crash Red Team's Milestone 2B3B round 2 review (finding 5b) found and required fixed.

OUT_PATH = out_path("meetings.html", "OPSDB_MEETINGS_PATH")
MAX_TOPIC_CHARS = 2_000  # kept in sync with meeting_orchestrator.MAX_TOPIC_CHARS — see that module


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
        participants = ", ".join(e(p["name"]) for p in opsdb.normalized_participants(m["participating_agents"])) or "—"
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

def render_position_card(agent_name: str, body_text: str, requested_by: str | None = None) -> str:
    """requested_by (Milestone 2B3B round 2, item 2): set only for a
    manually-requested participant's card. Per ExecutiveMeeting.dc.html
    lines 72-79 — a distinct accent-border style, deliberately never the
    dashed/violet (CEO) or red (Red Team) treatment those two already
    use, carrying an explicit "— requested by <name>" marker next to the
    participant label."""
    if is_ceo(agent_name):
        style = "border-style:dashed; border-color:var(--violet); background:var(--violet-soft);"
        label_color = "var(--violet)"
        label_suffix = " · AI ADVISOR"
    elif agent_name == "red-team":
        style = "border-color:oklch(66% 0.17 25 / 0.35); background:var(--red-soft);"
        label_color = "var(--red)"
        label_suffix = ""
    elif requested_by:
        style = "border-color:var(--accent); background:var(--accent-soft);"
        label_color = "var(--accent)"
        requested_by_display = "Founder" if requested_by == "founder" else requested_by
        label_suffix = f" — requested by {e(requested_by_display)}"
    else:
        style = ""
        label_color = "var(--text2)"
        label_suffix = ""
    return f'''
    <div class="card" style="{style}">
      <div style="font-size:10.5px; font-weight:700; color:{label_color}; margin-bottom:5px; text-transform:uppercase;">{e(display_name(agent_name))}{label_suffix}</div>
      <div style="font-size:12px; color:var(--text2); line-height:1.5;">{e(body_text)}</div>
    </div>'''


def _retry_exhausted(conn: sqlite3.Connection, meeting_id: int, agent_name: str) -> bool:
    """TASK-011 QA round 2, defect 3: mirrors opsdb.start_meeting_retry_run()'s
    own `failed_count >= max_retries + 1` threshold exactly (see that
    function's docstring for why it's `+ 1`, not `max_retries` alone),
    so the Retry button is never offered for a slot that would just get
    a guaranteed 409. Read-only — the real enforcement stays entirely in
    start_meeting_retry_run()'s atomic check; a stale read here (a retry
    landing between this render and a click) is not a correctness gap,
    only a rarer still-safe 409 the atomic function still catches."""
    row = conn.execute(
        "SELECT COUNT(*) FROM agent_runs WHERE agent_id = (SELECT id FROM agents WHERE name = ?) "
        "AND scope_type = 'meeting' AND scope_id = ? AND status = 'failed'",
        (agent_name, meeting_id),
    ).fetchone()
    failed_count = row[0] if row else 0
    return failed_count >= MAX_RETRIES_PER_PARTICIPANT + 1


def render_orchestrator_note(conn: sqlite3.Connection, meeting_id: int) -> str:
    """Item 1: Orchestrator's validation note, rendered distinctly from a
    position card — Orchestrator doesn't have a position on the topic, it
    validated who gets one. Lives on its own thread
    (`meeting-{id}-orchestrator`), never mixed into the shared positions
    thread. Absent for a meeting created before this round shipped (no
    such thread exists) — rendered as nothing, not an error."""
    row = conn.execute(
        "SELECT body FROM messages WHERE thread_id = ? AND from_agent = 'orchestrator' ORDER BY id LIMIT 1",
        (f"meeting-{meeting_id}-orchestrator",),
    ).fetchone()
    if row is None:
        return ""
    return f'''
    <div class="panel" style="margin-bottom:14px; border-color:var(--border2);">
      <div class="label" style="margin-bottom:6px;">{e(display_name("orchestrator"))} — participant selection validated</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.5;">{e(row["body"])}</div>
    </div>'''


def render_request_perspective_form(meeting_id: int, participants: list[dict], token: str | None) -> str:
    """Item 2's dashed affordance row (ExecutiveMeeting.dc.html lines
    81-84). Only offered when a token is present (the same "static file
    has no active session" gate every other write affordance on this
    page already uses) and only when there's an eligible candidate role
    left AND the meeting isn't already at the (unrevised)
    MAX_MEETING_PARTICIPANTS cap — Red Team's Milestone 2B3B round 2
    review, finding 1 / condition 1: a manually-requested participant
    counts against the SAME cap as everyone else, no separate allowance."""
    if token is None:
        return ""
    current_names = {p["name"] for p in participants}
    candidates = [r for r in MEETING_PARTICIPANT_ALLOWLIST if r not in current_names]
    if not candidates or len(participants) >= MAX_MEETING_PARTICIPANTS:
        return ""
    options = "".join(f'<option value="{e(c)}">{e(c)}</option>' for c in candidates)
    return f'''
    <form method="POST" action="/api/meetings/{meeting_id}/request-perspective" style="margin-bottom:16px;">
      <input type="hidden" name="token" value="{e(token)}">
      <div class="card" style="border-style:dashed; display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
        <span style="font-size:15px; color:var(--accent); font-weight:700;">+</span>
        <span style="font-size:11.5px; color:var(--text2);">Request another agent's perspective</span>
        <select name="agent_name" required
                style="padding:7px 10px; border-radius:7px; background:var(--panel2); border:1px solid var(--border2); color:var(--text); font-size:11.5px;">{options}</select>
        <button type="submit" style="margin-left:auto; padding:7px 16px; border-radius:7px; background:var(--accent); border:none; font-size:11px; font-weight:700; color:#1a1206; cursor:pointer;">Request</button>
      </div>
    </form>'''


def render_followup_section(conn: sqlite3.Connection, meeting_id: int, participants: list[dict],
                             positions_by_agent: dict, token: str | None) -> str:
    """Item 3 (ExecutiveMeeting.dc.html lines 86-93): a per-(meeting,
    participant) follow-up thread, styled like the existing Ask-Agent
    chat bubbles (violet Founder / neutral agent), rendered only for a
    participant who has a real recorded position — per Red Team's
    Milestone 2B3B round 2 review, finding 7, this must match the same
    eligibility server.py's /followup route itself enforces, not a
    looser one. A participant with an existing thread is shown even on a
    static (token=None) page (read-only history); the reply form itself
    only appears with a live session token."""
    sections = []
    for p in participants:
        name = p["name"]
        if name not in positions_by_agent:
            continue
        thread_id = f"meeting-{meeting_id}-{name}"
        rows = conn.execute(
            "SELECT from_agent, body FROM messages WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
        if not rows and token is None:
            continue
        bubbles = "".join(
            f'''<div style="margin-bottom:8px; display:flex; justify-content:{"flex-end" if r["from_agent"] == "founder" else "flex-start"};">
              <div style="max-width:80%; padding:9px 13px; border-radius:11px; font-size:12px; line-height:1.5;
                          {"background:var(--violet-soft); color:var(--text);" if r["from_agent"] == "founder" else "background:var(--panel2); color:var(--text2);"}">
                <b style="font-size:10px; text-transform:uppercase; opacity:0.7;">{"Founder" if r["from_agent"] == "founder" else e(name)}</b><br>{e(r["body"])}
              </div>
            </div>''' for r in rows
        )
        form = ""
        if token is not None:
            form = f'''
            <form method="POST" action="/api/meetings/{meeting_id}/followup" style="display:flex; gap:8px; margin-top:6px;">
              <input type="hidden" name="token" value="{e(token)}">
              <input type="hidden" name="agent_name" value="{e(name)}">
              <input type="text" name="message" required maxlength="8000" placeholder="Follow up with {e(name)}..."
                     style="flex:1; padding:8px 12px; border-radius:8px; background:var(--panel2); border:1px solid var(--border2); color:var(--text); font-size:11.5px;">
              <button type="submit" style="padding:8px 16px; border-radius:8px; background:var(--accent); border:none; font-size:11px; font-weight:700; color:#1a1206; cursor:pointer;">Send</button>
            </form>'''
        sections.append(f'''
        <div class="panel" style="margin-bottom:12px;">
          <div class="label" style="margin-bottom:8px;">Follow-up with {e(name)}</div>
          {bubbles or '<div style="font-size:11px; color:var(--text3);">No follow-up yet.</div>'}
          {form}
        </div>''')
    if not sections:
        return ""
    return f'<div style="margin-top:6px; margin-bottom:20px;"><div class="label" style="margin-bottom:10px;">Follow-up</div>{"".join(sections)}</div>'


def build_meeting_detail(conn: sqlite3.Connection, meeting: sqlite3.Row, token: str | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    participants = opsdb.normalized_participants(meeting["participating_agents"])

    # Milestone 2B3B round 2: filtered by thread_id, NOT just meeting_id.
    # Every message tied to this meeting — the shared positions thread,
    # Orchestrator's own note, and now every per-participant follow-up
    # reply — shares the same meeting_id. A plain "WHERE meeting_id = ?"
    # (the original Milestone 2B3B query) would let a later follow-up
    # reply from the same agent silently overwrite that agent's real
    # original position here, since both share from_agent too. The
    # shared positions thread's own thread_id is the only reliable filter.
    positions = conn.execute(
        "SELECT from_agent, body FROM messages WHERE thread_id = ? ORDER BY id",
        (f"meeting-{meeting['id']}",),
    ).fetchall()
    positions_by_agent = {p["from_agent"]: p["body"] for p in positions}

    orchestrator_html = render_orchestrator_note(conn, meeting["id"])

    cards = []
    for p in participants:
        name = p["name"]
        if name in positions_by_agent:
            requested_by = p["requested_by"] if p["source"] == "requested" else None
            cards.append(render_position_card(name, positions_by_agent[name], requested_by=requested_by))
        else:
            # Selected/requested but no real position was gathered — an
            # honest absence (invocation failed), never a fabricated
            # position. Red Team's Milestone 2B3B condition 6. A "Retry"
            # affordance (item 5) replaces the old unconditional
            # no-affordance text when a live session token is present —
            # same "static page has no active session" gate every other
            # write form on this page already uses.
            #
            # TASK-011 QA round 2, defect 3: the button used to render
            # unconditionally whenever a token was present, with no
            # awareness of opsdb.start_meeting_retry_run()'s own
            # MAX_RETRIES_PER_PARTICIPANT cap — a Founder could click
            # Retry on an already-exhausted slot and get a guaranteed 409
            # with no warning. _retry_exhausted() mirrors that function's
            # exact failed_count >= max_retries + 1 threshold (read-only;
            # the real enforcement still lives in the atomic function —
            # this only avoids OFFERING a button guaranteed to fail).
            retry_html = ""
            if token is not None:
                if _retry_exhausted(conn, meeting["id"], name):
                    retry_html = (
                        '<div style="margin-top:8px; font-size:10.5px; color:var(--text3); font-style:italic;">'
                        f'Retry limit reached ({MAX_RETRIES_PER_PARTICIPANT} attempts).</div>'
                    )
                else:
                    retry_html = f'''
                <form method="POST" action="/api/meetings/{meeting["id"]}/retry" style="margin-top:8px;">
                  <input type="hidden" name="token" value="{e(token)}">
                  <input type="hidden" name="agent_name" value="{e(name)}">
                  <button type="submit" style="padding:5px 12px; border-radius:7px; background:var(--panel2); border:1px solid var(--border2); font-size:10.5px; font-weight:600; color:var(--text2); cursor:pointer;">Retry</button>
                </form>'''
            cards.append(f'''
            <div class="card" style="border-color:var(--border2); opacity:0.6;">
              <div style="font-size:10.5px; font-weight:700; color:var(--text3); margin-bottom:5px; text-transform:uppercase;">{e(name)}</div>
              <div style="font-size:12px; color:var(--text3); font-style:italic;">Selected, but no response was recorded (the real invocation did not succeed).</div>
              {retry_html}
            </div>''')

    grid = f'<div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:11px; margin-bottom:16px;">{"".join(cards)}</div>'
    request_perspective_html = render_request_perspective_form(meeting["id"], participants, token)
    followup_html = render_followup_section(conn, meeting["id"], participants, positions_by_agent, token)

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
{orchestrator_html}
{grid}
{request_perspective_html}
{followup_html}
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
