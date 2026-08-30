#!/usr/bin/env python3
"""ops/control-center/generate_pipeline.py — Phase 2, Milestone 2A.

Six major-stage columns with real substate lanes, per AGENT_STATUS.md and
ops/db/derived_state.py's STAGE_MAP (not invented here — see
ops/reviews/cto-milestone2a-architecture.md). Backlog and Needs Attention
(BLOCKED/FOUNDER_APPROVAL) render separately, matching AGENT_STATUS.md's
"interrupt state, not a pipeline stage" rule.

Usage:
    python3 ops/control-center/generate_pipeline.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
from derived_state import PIPELINE_STAGES, display_name, stage_and_substate, task_progress_fraction  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("pipeline.html", "OPSDB_PIPELINE_PATH")


def render_needs_attention(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, title, status, blockers FROM tasks "
        "WHERE status IN ('BLOCKED','FOUNDER_APPROVAL') ORDER BY id"
    ).fetchall()
    if not rows:
        return ""
    items = []
    for t in rows:
        note = e(t["blockers"]) if t["status"] == "BLOCKED" and t["blockers"] else e(t["status"])
        items.append(f'''
        <div id="task-{t["id"]}" class="card" style="border-color:oklch(66% 0.17 25 / 0.4); background:var(--red-soft);">
          <div style="font-size:12px; font-weight:600;">TASK-{t["id"]:03d} — {e(t["title"])}</div>
          <div style="font-size:11px; color:var(--red); margin-top:2px;">{note}</div>
        </div>''')
    return f'''
    <div class="panel" style="margin-bottom:16px; border-color:oklch(66% 0.17 25 / 0.35);">
      <div class="label" style="margin-bottom:10px; color:var(--red);">Needs Attention</div>
      <div style="display:flex; flex-direction:column; gap:8px;">{"".join(items)}</div>
    </div>'''


def render_backlog(conn: sqlite3.Connection) -> str:
    rows = conn.execute("SELECT id, title FROM tasks WHERE status = 'BACKLOG' ORDER BY id").fetchall()
    if not rows:
        return '<div style="font-size:11.5px; color:var(--text2);">Nothing in backlog.</div>'
    return "".join(
        f'<div id="task-{t["id"]}" class="card" style="margin-bottom:6px;"><div style="font-size:12px; font-weight:600;">TASK-{t["id"]:03d} — {e(t["title"])}</div></div>'
        for t in rows
    )


def render_stage_column(conn: sqlite3.Connection, stage: str, tasks_by_substate: dict) -> str:
    substates = tasks_by_substate.get(stage, {})
    lanes = []
    for substate, tasks in substates.items():
        cards = []
        for t in tasks:
            frac = task_progress_fraction(conn, t["id"])
            progress_html = ""
            if frac is not None:
                done, total = frac
                pct = round(100 * done / total)
                progress_html = f'''<div style="display:flex; align-items:center; gap:6px; margin-top:6px;">
                  <div style="flex:1; height:4px; border-radius:2px; background:var(--border2); overflow:hidden;"><div style="width:{pct}%; height:100%; background:var(--accent);"></div></div>
                  <span class="mono" style="font-size:9.5px; color:var(--text2);">{pct}%</span></div>'''
            cards.append(f'''
            <div id="task-{t["id"]}" class="card">
              <div class="mono" style="font-size:9.5px; color:var(--text3); margin-bottom:4px;">TASK-{t["id"]:03d}</div>
              <div style="font-size:12px; font-weight:600;">{e(t["title"])}</div>
              <div style="font-size:10.5px; color:var(--text3); margin-top:4px;">{e(display_name(t["current_owner"]) if t["current_owner"] else "unassigned")}</div>
              {progress_html}
            </div>''')
        lanes.append(f'''
        <div style="border-radius:10px; border:1px solid var(--border); background:var(--panel); padding:9px; margin-bottom:8px;">
          <div class="label" style="margin-bottom:6px;">{e(substate)}</div>
          {"".join(cards)}
        </div>''')
    count = sum(len(v) for v in substates.values())
    return f'''
    <div style="flex:1; min-width:0;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
        <div style="font-size:12.5px; font-weight:700;">{e(stage)}</div>
        <div class="mono" style="font-size:10px; color:var(--text3);">{count}</div>
      </div>
      {"".join(lanes) if lanes else '<div style="font-size:11px; color:var(--text3);">—</div>'}
    </div>'''


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    all_tasks = conn.execute(
        "SELECT id, title, status, current_owner FROM tasks "
        "WHERE status NOT IN ('BACKLOG','BLOCKED','FOUNDER_APPROVAL') ORDER BY id"
    ).fetchall()

    # Group real tasks into (stage -> substate -> [tasks]) using the shared
    # mapping — no per-screen invention of which stage a status belongs to.
    tasks_by_stage: dict = {stage: {} for stage in PIPELINE_STAGES}
    for t in all_tasks:
        mapped = stage_and_substate(t["status"])
        if mapped is None:
            continue
        stage, substate = mapped
        tasks_by_stage[stage].setdefault(substate, []).append(t)

    columns = "".join(render_stage_column(conn, stage, tasks_by_stage) for stage in PIPELINE_STAGES)

    body = f"""
<h1>Pipeline <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
{render_needs_attention(conn)}
<div class="panel" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:10px;">Backlog</div>
  {render_backlog(conn)}
</div>
<div style="display:flex; gap:12px; align-items:flex-start;">
  {columns}
</div>
<div style="margin-top:16px; font-size:10.5px; color:var(--text3);">
  A major stage is the simple answer; open a lane to see the exact detailed status. Marketing/Launch Prep, when active, runs in parallel inside Release — it does not block the pipeline (AGENT_STATUS.md).
</div>"""
    return page("Pipeline", "pipeline.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
