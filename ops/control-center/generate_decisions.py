#!/usr/bin/env python3
"""ops/control-center/generate_decisions.py — Phase 2, Milestone 2A.

Lists the real rows in the `decisions` table. DECISIONS.md remains the
durable narrative record (see ops/DATA_MODEL.md's clarification on the
two independent numbering schemes) — this screen shows what's actually
structured, queryable state, not a copy of the markdown file.

Usage:
    python3 ops/control-center/generate_decisions.py
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

OUT_PATH = out_path("decisions.html", "OPSDB_DECISIONS_PATH")


def render_decisions(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, title, date, problem, decision, reason, tradeoffs, "
        "recommending_agent, founder_approval_required, founder_approval_id "
        "FROM decisions ORDER BY id DESC"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No decisions recorded yet.</div>'
    items = []
    for d in rows:
        approval_note = ""
        if d["founder_approval_required"]:
            if d["founder_approval_id"] is not None:
                approval_note = f'<span class="pill" style="background:var(--green-soft); color:var(--green);">Founder approval linked — #{e(d["founder_approval_id"])}</span>'
            else:
                approval_note = '<span class="pill" style="background:var(--gray-soft); color:var(--text2);">Founder approval required — recorded outside the approvals table</span>'
        items.append(f'''
        <div class="card" id="decision-{d["id"]}" style="margin-bottom:10px;">
          <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px;">
            <div style="font-size:13px; font-weight:600;">#{d["id"]} — {e(d["title"])}</div>
            <div class="mono" style="font-size:10px; color:var(--text3);">{e(d["date"])}</div>
          </div>
          {f'<div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;"><b style="color:var(--text);">Problem:</b> {e(d["problem"])}</div>' if d["problem"] else ""}
          <div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;"><b style="color:var(--text);">Decision:</b> {e(d["decision"])}</div>
          {f'<div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;"><b style="color:var(--text);">Reason:</b> {e(d["reason"])}</div>' if d["reason"] else ""}
          {f'<div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;"><b style="color:var(--text);">Tradeoffs:</b> {e(d["tradeoffs"])}</div>' if d["tradeoffs"] else ""}
          <div style="display:flex; align-items:center; justify-content:space-between; margin-top:8px;">
            <div style="font-size:10.5px; color:var(--text3);">Recommended by {e(display_name(d["recommending_agent"]))}</div>
            {approval_note}
          </div>
        </div>''')
    return "".join(items)


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    body = f'''
<h1>Decisions <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
<div class="sub" style="margin-top:-14px;">
  This is the operational decision log ({count} record{"s" if count != 1 else ""}) — structured, queryable state from the
  <span class="mono">decisions</span> table. <code class="mono">DECISIONS.md</code> is the durable narrative record and may
  include additional historical context; the two use independent numbering (see DATA_MODEL.md).
</div>
{render_decisions(conn)}'''
    return page("Decisions", "decisions.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
