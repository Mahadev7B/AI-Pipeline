#!/usr/bin/env python3
"""ops/control-center/generate_agents.py — Phase 2, Milestone 2A.

Generates the Agents roster (agents.html) and one Agent Detail page per
agent (agents/<name>.html) — 15 files total.

Grouping/sorting is by REAL state (Working/Blocked/Waiting/Available,
from agent_runs), not an invented functional-group taxonomy — the
`agents` table has no group column, and inventing one in code would be
exactly the "structure the schema doesn't back" the Founder's data rules
forbid. See ops/reviews/cto-milestone2a-architecture.md, "Agents: the
functional-grouping gap, resolved" for the reasoning. Founder vs. CEO
Agent stay visually distinct (violet solid vs. dashed hexagon), same as
every prior screen.

Usage:
    python3 ops/control-center/generate_agents.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
from derived_state import agent_status_rows, scope_label  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("agents.html", "OPSDB_AGENTS_PATH")
AGENTS_SUBDIR = OUT_PATH.parent / "agents"

STATE_ORDER = ["active", "blocked", "waiting", None]  # None = available, sorted last
STATE_LABEL = {"active": "Working", "blocked": "Blocked", "waiting": "Waiting", None: "Available"}
STATE_COLOR = {
    "active": "var(--accent)", "blocked": "var(--red)",
    "waiting": "var(--blue)", None: "var(--gray)",
}


def is_ceo(name: str) -> bool:
    return name == "ceo"


def agent_avatar(name: str) -> str:
    """Founder vs. CEO Agent vs. every other agent stay visually distinct
    — same treatment as every prior screen (Milestone 0/1 rule, unchanged)."""
    if is_ceo(name):
        return ('<div style="width:26px; height:26px; border-radius:7px; background:var(--violet-soft); '
                'border:1px dashed var(--violet); display:flex; align-items:center; justify-content:center;">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z" '
                'stroke="var(--violet)" stroke-width="1.6"/></svg></div>')
    return ('<div style="width:26px; height:26px; border-radius:7px; background:var(--panel2); '
            'display:flex; align-items:center; justify-content:center; font-size:11px; color:var(--text3);">•</div>')


def render_roster(rows: list[sqlite3.Row]) -> str:
    by_state: dict = {s: [] for s in STATE_ORDER}
    for r in rows:
        by_state.get(r["status"], by_state[None]).append(r)

    counts = " ".join(
        f'<span class="pill" style="background:{STATE_COLOR[s]}22; color:{STATE_COLOR[s]};">'
        f'{e(STATE_LABEL[s])} · {len(by_state[s])}</span>'
        for s in STATE_ORDER
    )

    sections = []
    for s in STATE_ORDER:
        agents_in_state = by_state[s]
        if not agents_in_state:
            continue
        cards = []
        for r in agents_in_state:
            label_extra = ' <span style="font-size:9px; color:var(--violet); font-weight:700;">· AI ADVISOR</span>' if is_ceo(r["name"]) else ""
            activity = f'<div style="font-size:10.5px; color:var(--text3); margin-top:2px;">{e(r["current_activity"])}</div>' if r["current_activity"] else ""
            cards.append(f'''
            <a href="agents/{e(r["name"])}.html" class="card" style="display:flex; align-items:center; gap:10px;">
              {agent_avatar(r["name"])}
              <div style="flex:1; min-width:0;">
                <div style="font-size:12.5px; font-weight:600;">{e(r["name"])}{label_extra}</div>
                {activity}
              </div>
            </a>''')
        sections.append(f'''
        <div style="margin-bottom:16px;">
          <div class="label" style="margin-bottom:8px;">{e(STATE_LABEL[s])}</div>
          <div style="display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px;">{"".join(cards)}</div>
        </div>''')

    return f'''
    <div style="margin-bottom:16px;">{counts}</div>
    {"".join(sections)}'''


def json_list(raw: str) -> list:
    try:
        val = json.loads(raw or "[]")
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def render_field(label: str, value: str) -> str:
    return f'''
    <div style="margin-bottom:12px;">
      <div class="label" style="margin-bottom:3px;">{e(label)}</div>
      <div style="font-size:12.5px; color:var(--text);">{value}</div>
    </div>'''


def render_list_field(label: str, items: list) -> str:
    if not items:
        return render_field(label, '<span style="color:var(--text3);">none recorded</span>')
    return render_field(label, ", ".join(e(i) for i in items))


def build_agent_detail(conn: sqlite3.Connection, agent_row: sqlite3.Row) -> str:
    name = agent_row["name"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    run = conn.execute(
        "SELECT status, scope_type, scope_id, current_activity, blocked_reason, started_at "
        "FROM agent_runs WHERE agent_id = ? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
        (agent_row["id"],),
    ).fetchone()
    status = run["status"] if run else None
    status_color = STATE_COLOR.get(status, "var(--gray)")

    activity_rows = conn.execute(
        "SELECT summary, task_id, created_at FROM agent_activity "
        "WHERE agent_id = ? ORDER BY id DESC LIMIT 10",
        (agent_row["id"],),
    ).fetchall()

    qa_perf = conn.execute(
        "SELECT task_id, scenario, result FROM qa_results WHERE tested_by_agent = ? ORDER BY id DESC LIMIT 5",
        (name,),
    ).fetchall()
    reviews_perf = conn.execute(
        "SELECT task_id, review_type, result FROM review_results WHERE reviewed_by_agent = ? ORDER BY id DESC LIMIT 5",
        (name,),
    ).fetchall()
    decisions_made = conn.execute(
        "SELECT id, title, decision FROM decisions WHERE recommending_agent = ? ORDER BY id DESC LIMIT 5",
        (name,),
    ).fetchall()
    risks_owned = conn.execute(
        "SELECT id, title, severity FROM risks WHERE owner_agent = ? AND status = 'open' ORDER BY id",
        (name,),
    ).fetchall()
    risks_raised = conn.execute(
        "SELECT id, title, severity FROM risks WHERE raised_by_agent = ? ORDER BY id DESC LIMIT 5",
        (name,),
    ).fetchall()

    eval_items = []
    for r in qa_perf:
        eval_items.append(f'<div style="font-size:11.5px; color:var(--text2);">QA performed by this agent · TASK-{r["task_id"]:03d} — {e(r["scenario"])}: <b style="color:var(--text);">{e(r["result"])}</b></div>')
    for r in reviews_perf:
        eval_items.append(f'<div style="font-size:11.5px; color:var(--text2);">{e(r["review_type"])} review performed by this agent · TASK-{r["task_id"]:03d}: <b style="color:var(--text);">{e(r["result"])}</b></div>')
    for r in decisions_made:
        eval_items.append(f'<div style="font-size:11.5px; color:var(--text2);">Decision recommended by this agent — #{r["id"]} {e(r["title"])}: {e(r["decision"])}</div>')
    for r in risks_raised:
        eval_items.append(f'<div style="font-size:11.5px; color:var(--text2);">Risk raised by this agent — [{e(r["severity"])}] {e(r["title"])}</div>')
    eval_html = "".join(eval_items) if eval_items else '<div style="font-size:12px; color:var(--text2);">No evaluation or decision history recorded for this agent yet.</div>'

    activity_html = "".join(
        f'<div style="font-size:11.5px; color:var(--text2);">{e(a["summary"])}</div>'
        for a in activity_rows
    ) or '<div style="font-size:12px; color:var(--text2);">No activity recorded yet.</div>'

    blockers_parts = []
    if run and run["blocked_reason"]:
        blockers_parts.append(e(run["blocked_reason"]))
    for r in risks_owned:
        blockers_parts.append(f'[{e(r["severity"])}] {e(r["title"])}')
    blockers_html = "<br>".join(blockers_parts) if blockers_parts else '<span style="color:var(--text3);">none</span>'

    header_badge = ('<span style="font-size:9px; color:var(--violet); font-weight:700; letter-spacing:0.04em;">AI ADVISOR — NOT THE FOUNDER</span>'
                     if is_ceo(name) else "")

    body = f'''
<h1>{e(name)} {header_badge}</h1>
<div style="display:flex; align-items:center; gap:8px; margin-bottom:20px;">
  <div style="width:8px; height:8px; border-radius:50%; background:{status_color};"></div>
  <span style="font-size:12.5px;">{e(STATE_LABEL.get(status, "Available"))}</span>
  {f'<span style="font-size:11px; color:var(--text3);">· {e(scope_label(run["scope_type"], run["scope_id"]))}</span>' if run else ""}
</div>
<div style="display:grid; grid-template-columns:1fr 1fr; gap:24px;">
  <div>
    {render_field("Role", e(agent_row["role"]))}
    {render_field("Model", e(agent_row["model"]) + f' <span style="color:var(--text3);">({e(agent_row["model_status"])})</span>')}
    {render_list_field("Skills", json_list(agent_row["skills"]))}
    {render_list_field("Frameworks", json_list(agent_row["frameworks"]))}
    {render_list_field("Tools", json_list(agent_row["tools"]))}
    {render_field("Permissions — allowed", ", ".join(e(i) for i in json_list(agent_row["permissions_allow"])) or '<span style="color:var(--text3);">none recorded</span>')}
    {render_field("Permissions — not permitted", ", ".join(e(i) for i in json_list(agent_row["permissions_deny"])) or '<span style="color:var(--text3);">none recorded</span>')}
  </div>
  <div>
    {render_field("Current activity", e(run["current_activity"]) if run and run["current_activity"] else '<span style="color:var(--text3);">none</span>')}
    {render_field("Blockers", blockers_html)}
    <div style="margin-bottom:12px;">
      <div class="label" style="margin-bottom:6px;">Recent activity</div>
      <div style="display:flex; flex-direction:column; gap:6px;">{activity_html}</div>
    </div>
    <div>
      <div class="label" style="margin-bottom:6px;">Evaluation / decision history</div>
      <div style="display:flex; flex-direction:column; gap:6px;">{eval_html}</div>
    </div>
  </div>
</div>'''
    return page(f"{name} — Agent Detail", "agents.html", body, depth=1,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run generate_agents.py to refresh.")


def build_roster_html(conn: sqlite3.Connection) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = agent_status_rows(conn)
    body = f'''
<h1>Agents <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
<div class="sub" style="margin-top:-14px;">Grouped and sorted by real state (agent_runs), not an invented org chart — see ops/reviews/cto-milestone2a-architecture.md.</div>
{render_roster(rows)}'''
    return page("Agents", "agents.html", body,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    conn = connect()
    write_output(OUT_PATH, build_roster_html(conn))
    print(f"wrote {OUT_PATH}")

    agents = conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
    AGENTS_SUBDIR.mkdir(parents=True, exist_ok=True)
    for a in agents:
        detail_path = AGENTS_SUBDIR / f"{a['name']}.html"
        write_output(detail_path, build_agent_detail(conn, a))
    print(f"wrote {len(agents)} agent detail pages under {AGENTS_SUBDIR}")


if __name__ == "__main__":
    main()
