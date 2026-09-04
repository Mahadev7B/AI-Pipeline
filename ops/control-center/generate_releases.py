#!/usr/bin/env python3
"""ops/control-center/generate_releases.py — Phase 2, Milestone 2B5 (TASK-014).

Two sections, both real:
1. The `deployments` table's actual rows, in a normal chronological list.
2. The computed release-readiness gap (derived_state.release_readiness_gap()) —
   DONE/READY_TO_RELEASE/DEPLOYED tasks with no matching `deployments` row.

The gap-list section is presented as a neutral data observation, never as
an assertion of a process-discipline failure — required per Red Team's
Milestone 2B5 review, blocking finding on Decision 3 (see
ops/reviews/cto-milestone2b5-architecture.md, Decision 3's "Correction").

Usage:
    python3 ops/control-center/generate_releases.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
from derived_state import display_name, release_readiness_gap  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("releases.html", "OPSDB_RELEASES_PATH")


def render_deployments(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT d.id, d.task_id, t.title, d.version, d.environment, d.release_notes, "
        "d.rollback_plan, d.deployed_by_agent, d.founder_authorized, d.deployed_at "
        "FROM deployments d JOIN tasks t ON t.id = d.task_id "
        "ORDER BY d.deployed_at ASC"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No deployments recorded yet.</div>'
    items = []
    for d in rows:
        authorized_note = (
            '<span class="pill" style="background:var(--green-soft); color:var(--green);">Founder authorized</span>'
            if d["founder_authorized"] else
            '<span class="pill" style="background:var(--red-soft); color:var(--red);">Not Founder authorized</span>'
        )
        items.append(f'''
        <div class="card" style="margin-bottom:10px;">
          <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px;">
            <a href="tasks/{d["task_id"]}.html" style="font-size:13px; font-weight:600; color:var(--text);">TASK-{d["task_id"]:03d} — {e(d["title"])}</a>
            <div class="mono" style="font-size:10px; color:var(--text3);">{e(d["deployed_at"])}</div>
          </div>
          <div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;">
            <b style="color:var(--text);">{e(d["version"])}</b> &middot; {e(d["environment"])}
          </div>
          {f'<div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;"><b style="color:var(--text);">Release notes:</b> {e(d["release_notes"])}</div>' if d["release_notes"] else ""}
          <div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;"><b style="color:var(--text);">Rollback plan:</b> {e(d["rollback_plan"])}</div>
          <div style="display:flex; align-items:center; justify-content:space-between; margin-top:8px;">
            <div style="font-size:10.5px; color:var(--text3);">Deployed by {e(display_name(d["deployed_by_agent"]))}</div>
            {authorized_note}
          </div>
        </div>''')
    return "".join(items)


def render_gap(conn: sqlite3.Connection) -> str:
    gap_rows = release_readiness_gap(conn)
    done_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'DONE'").fetchone()[0]
    if not gap_rows:
        return '<div style="font-size:12px; color:var(--text2);">Every READY_TO_RELEASE/DEPLOYED/DONE task has a matching deployments row.</div>'
    items = "".join(
        f'''<div class="card" style="margin-bottom:6px;">
          <a href="tasks/{t["id"]}.html" style="display:flex; align-items:baseline; justify-content:space-between;">
            <div style="font-size:12px; font-weight:600; color:var(--text);">TASK-{t["id"]:03d} — {e(t["title"])}</div>
            <div style="font-size:10.5px; color:var(--text3);">{e(t["status"])}</div>
          </a>
        </div>'''
        for t in gap_rows
    )
    return f'''
    <div class="sub" style="margin:0 0 10px;">
      {len(gap_rows)} of {done_count} DONE tasks have no <code class="mono">deployments</code> row — this may reflect
      internal/tooling work with no discrete production release step, not necessarily a process gap.
    </div>
    {items}'''


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    deployment_count = conn.execute("SELECT COUNT(*) FROM deployments").fetchone()[0]

    body = f'''
<h1>Releases <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
<div class="sub" style="margin-top:-14px;">
  The real deployment log ({deployment_count} record{"s" if deployment_count != 1 else ""}) from the
  <span class="mono">deployments</span> table, plus a computed release-readiness gap list below.
</div>
<div class="panel" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:10px;">Deployments</div>
  {render_deployments(conn)}
</div>
<div class="panel">
  <div class="label" style="margin-bottom:10px;">Release-readiness gap</div>
  {render_gap(conn)}
</div>'''
    return page("Releases", "releases.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
