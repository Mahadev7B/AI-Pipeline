#!/usr/bin/env python3
"""ops/control-center/generate_reviews.py — Phase 2, Milestone 2B5 (TASK-014).

The full `review_results` (Code Review + Security, pass/reject) and
`qa_results` (pass/fail) history, grouped by task. This is the
full-history screen — every row, pass and fail, resolved and
unresolved — as distinct from ops/db/report.py's CURRENT_STATUS.md
"QA failures (unresolved)" section, which is deliberately narrower
(latest qa_results row per task, only fail rows on non-DONE tasks).
See ops/reviews/cto-milestone2b5-architecture.md, Decision 2 and
Decision 7, and ops/reviews/red-team-milestone2b5-architecture.md's
Decision 7 note (the two screens must read as complementary, not
contradictory).

Task groups are ordered by the most-recently-active task first (MAX of
that task's own review/QA row created_at, descending); rows within a
task group are interleaved reverse-chronologically by created_at. A
task group with more than ~10 combined rows renders inside a native
<details> element, collapsed by default (Red Team's Milestone 2B5
review, condition 2 — verified against the real worst case, TASK-007's
21 combined rows).

Usage:
    python3 ops/control-center/generate_reviews.py
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

OUT_PATH = out_path("reviews.html", "OPSDB_REVIEWS_PATH")

# A task-group with more than this many combined review+QA rows renders
# collapsed inside a <details> element (Decision 2 correction).
COLLAPSE_THRESHOLD = 10

_RESULT_STYLE = {
    "pass": ("var(--green)", "var(--green-soft)"),
    "reject": ("var(--red)", "var(--red-soft)"),
    "fail": ("var(--red)", "var(--red-soft)"),
}


def _result_pill(result: str) -> str:
    color, soft = _RESULT_STYLE.get(result, ("var(--text2)", "var(--gray-soft)"))
    return f'<span class="pill" style="background:{soft}; color:{color};">{e(result)}</span>'


def _task_groups(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Distinct task_ids with review/QA rows, ordered by that task's own
    most-recent review/QA row (most-recently-active task first), joined
    to the task's current title/status for the group header."""
    return conn.execute(
        """
        SELECT t.id, t.title, t.status, g.max_created
        FROM (
            SELECT task_id, MAX(created_at) AS max_created
            FROM (
                SELECT task_id, created_at FROM review_results
                UNION ALL
                SELECT task_id, created_at FROM qa_results
            )
            GROUP BY task_id
        ) g
        JOIN tasks t ON t.id = g.task_id
        ORDER BY g.max_created DESC
        """
    ).fetchall()


def _task_rows(conn: sqlite3.Connection, task_id: int) -> list[sqlite3.Row]:
    """Review and QA rows for one task, interleaved reverse-chronologically."""
    return conn.execute(
        """
        SELECT 'review' AS kind, id, review_type, reviewed_by_agent AS agent,
               result, findings, returned_to_agent, created_at,
               NULL AS scenario, NULL AS defect_summary, NULL AS reproduction_steps
        FROM review_results WHERE task_id = ?
        UNION ALL
        SELECT 'qa' AS kind, id, NULL AS review_type, tested_by_agent AS agent,
               result, NULL AS findings, returned_to_agent, created_at,
               scenario, defect_summary, reproduction_steps
        FROM qa_results WHERE task_id = ?
        ORDER BY created_at DESC
        """,
        (task_id, task_id),
    ).fetchall()


def _render_row(row: sqlite3.Row) -> str:
    if row["kind"] == "review":
        label = f'Code review ({e(row["review_type"])})' if row["review_type"] == "code" else "Security review"
        detail = f'Findings: {e(row["findings"])}' if row["findings"] and row["findings"] != "[]" else ""
    else:
        label = "QA"
        parts = []
        if row["scenario"]:
            parts.append(f'Scenario: {e(row["scenario"])}')
        if row["defect_summary"]:
            parts.append(f'Defect: {e(row["defect_summary"])}')
        detail = " — ".join(parts)
    returned_note = (
        f'<div style="font-size:10.5px; color:var(--text3); margin-top:4px;">Returned to {e(display_name(row["returned_to_agent"]))}</div>'
        if row["returned_to_agent"] else ""
    )
    return f'''
    <div class="card" style="margin-bottom:8px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:4px;">
        <div style="font-size:12px; font-weight:600;">{label}</div>
        <div style="display:flex; align-items:center; gap:8px;">
          {_result_pill(row["result"])}
          <div class="mono" style="font-size:10px; color:var(--text3);">{e(row["created_at"])}</div>
        </div>
      </div>
      <div style="font-size:11px; color:var(--text2);">by {e(display_name(row["agent"]))}</div>
      {f'<div style="font-size:11px; color:var(--text2); margin-top:4px;">{detail}</div>' if detail else ""}
      {returned_note}
    </div>'''


def render_reviews(conn: sqlite3.Connection) -> str:
    groups = _task_groups(conn)
    if not groups:
        return '<div style="font-size:12px; color:var(--text2);">No review or QA history recorded yet.</div>'

    sections = []
    for g in groups:
        rows = _task_rows(conn, g["id"])
        rows_html = "".join(_render_row(r) for r in rows)
        header = f'''
        <a href="pipeline.html#task-{g["id"]}" style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:8px;">
          <div style="font-size:13px; font-weight:600; color:var(--text);">TASK-{g["id"]:03d} — {e(g["title"])}</div>
          <div style="font-size:10.5px; color:var(--text3);">{e(g["status"])}</div>
        </a>'''
        if len(rows) > COLLAPSE_THRESHOLD:
            body = f'''
            <details>
              <summary style="cursor:pointer; font-size:11px; color:var(--text2); margin-bottom:8px;">show all {len(rows)}</summary>
              {rows_html}
            </details>'''
        else:
            body = rows_html
        sections.append(f'<div class="panel" style="margin-bottom:14px;">{header}{body}</div>')
    return "".join(sections)


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    review_count = conn.execute("SELECT COUNT(*) FROM review_results").fetchone()[0]
    qa_count = conn.execute("SELECT COUNT(*) FROM qa_results").fetchone()[0]

    body = f'''
<h1>Reviews <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
<div class="sub" style="margin-top:-14px;">
  Full historical record — {review_count} code/security review result(s) and {qa_count} QA result(s), grouped by
  task, most-recently-active task first — including resolved failures on now-DONE tasks. For what needs attention
  right now, see the Founder Inbox or <code class="mono">CURRENT_STATUS.md</code>.
</div>
{render_reviews(conn)}'''
    return page("Reviews", "reviews.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
