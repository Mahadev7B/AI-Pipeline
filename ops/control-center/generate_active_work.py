#!/usr/bin/env python3
"""ops/control-center/generate_active_work.py — Milestone A (TASK-019).

Renders /active-work.html: every non-DONE task, one row each, sorted
Founder-decision-needed first, then stuck, then most-recently-active
(ops/reviews/cto-milestone-a-architecture.md §3.5, confirmed unchanged by
Design review). Each row is built from the one shared computed function,
ops/db/derived_state.py's task_progress_row() — never a second, hand-typed
copy of the gate/bounce/stuck/cost logic.

Layout follows ops/reviews/design-review-milestone-a.md exactly: a status
dot + bold primary line (title + Founder-needed pill) with everything
else demoted to small muted secondary text — real typographic hierarchy,
not four equal-weight lines. No progress bar for the two gate-count
numbers (Design §1.2 — plain text chips only, since no fixed total exists
for most tasks). Matches ops/mockups/milestone-a/Main.dc.html.

Read-only: dbutil.connect() (mode=ro), zero writes, zero new routes.

Usage:
    python3 ops/control-center/generate_active_work.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import derived_state as ds  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("active-work.html", "OPSDB_ACTIVE_WORK_PATH")

_INTERRUPT_STATUSES = ("BLOCKED", "FOUNDER_APPROVAL")


def _sort_key(row: dict) -> tuple:
    """Founder-action-required first, then stuck, then most-recently-active
    (ops/reviews/cto-milestone-a-architecture.md §3.5, confirmed as-is by
    Design review §1.4). last_event['at'] descending needs a DESC-friendly
    key; using a tuple of negated-orderable booleans plus the raw
    (ISO, sortable) timestamp string reversed via a wrapper class would be
    overkill — reverse=True on the final sort call handles the recency
    ordering, so this key returns ascending-sortable fields for the first
    two criteria and the raw timestamp for the third, sorted together with
    a single reverse=True (all three criteria want "more urgent first").
    """
    founder_needed = 1 if row["founder_action_required"] else 0
    stuck = 1 if row["is_stuck"] else 0
    last_at = (row["last_event"] or {}).get("at") or row["created_at"] or ""
    return (founder_needed, stuck, last_at)


def _founder_pill(founder_needed: bool) -> str:
    if founder_needed:
        return '<span class="pill" style="background:var(--red-soft); color:var(--red); font-weight:700;">Founder needed &middot; Yes</span>'
    return '<span class="pill" style="background:var(--gray-soft); color:var(--text2);">Founder needed &middot; No</span>'


def _project_label(row: dict) -> str:
    """CTO architecture doc §3.2's first table field ('Project / Phase /
    Milestone'): tasks.project_id -> projects.name via task_progress_row()'s
    LEFT JOIN, or an honest '—' when project_id is NULL — this project has
    one implicit single project today, never a fabricated name."""
    return e(row["project_name"]) if row["project_name"] else "&mdash;"


def _gate_line(conn: sqlite3.Connection, row: dict) -> str:
    owner = e(ds.display_name(row["current_owner"])) if row["current_owner"] else "unassigned"
    project = _project_label(row)
    if row["effective_gate_status"] is None:
        return (
            f'<span style="color:var(--text3);">Project: {project}</span> &middot; '
            f'<b style="color:var(--text);">Gate: &mdash;</b> &middot; '
            f'<span style="color:var(--text3);">&mdash; not yet on the gate ladder</span> &middot; Owner: {owner}'
        )
    label = e(ds.gate_display_label(row["effective_gate_status"]))
    if row["status"] in ("BLOCKED", "FOUNDER_APPROVAL"):
        label += " (paused)"
    n_done = len(row["gates_completed"])
    n_remaining = len(row["gates_remaining"])
    return (
        f'<span style="color:var(--text3);">Project: {project}</span> &middot; '
        f'<b style="color:var(--text);">{label}</b> &middot; '
        f'<b style="color:var(--text2); font-weight:600;">{n_done} done</b> &middot; '
        f'<b style="color:var(--text2); font-weight:600;">{n_remaining} to go</b> &middot; Owner: {owner}'
    )


def _detail_line(conn: sqlite3.Connection, row: dict) -> str:
    last_event = row["last_event"]
    if last_event:
        kind_label = {"status_change": "status change", "review": "review", "qa": "QA"}.get(last_event["kind"], last_event["kind"])
        last_event_html = f'{e(last_event["at"])} ({e(kind_label)})'
    else:
        last_event_html = "&mdash;"
    next_action = e(row["next_action"]) if row["next_action"] else "&mdash;"
    elapsed_created = ds.elapsed_since(conn, row["created_at"])
    extra_elapsed = ""
    if row["status"] in _INTERRUPT_STATUSES:
        since_label = "paused" if row["status"] == "BLOCKED" else "flagged"
        last_at = (last_event or {}).get("at")
        if last_at:
            extra_elapsed = f' &middot; {ds.elapsed_since(conn, last_at)} since {since_label}'
    elif row["gate_entered_at"]:
        extra_elapsed = f' &middot; {ds.elapsed_since(conn, row["gate_entered_at"])} in this gate'
    cost = row["cost"]
    cost_html = f'${cost["usd"]:.2f}' if cost["available"] else "not available"
    return (
        f'Bounces: {row["bounce_count"]} &middot; Last event: {last_event_html} &middot; '
        f'Next: {next_action} &middot; Elapsed: {elapsed_created} since created{extra_elapsed} &middot; Cost: {cost_html}'
    )


def _stuck_badge(conn: sqlite3.Connection, row: dict) -> str:
    """Design-approved exact text ('No activity in 4d · threshold 3d',
    ops/mockups/milestone-a/milestone-a-design-review.html) — the real
    elapsed-days figure, not a hardcoded placeholder. Computed from
    row['stuck_last_event_at'] (task_progress_row()'s own
    task_is_stuck() result); falls back to created_at only for the
    "zero activity ever" case where stuck_last_event_at is None."""
    if not row["is_stuck"]:
        return ""
    since = row["stuck_last_event_at"] or row["created_at"]
    days = ds.elapsed_days_int(conn, since)
    days_label = f"{days}d" if days is not None else "an unknown duration"
    return (
        f'<span class="pill" style="background:var(--gray-soft); color:var(--text2); margin-left:6px;">'
        f'No activity in {days_label} &middot; threshold {ds.STUCK_THRESHOLD_DAYS}d</span>'
    )


def render_card(conn: sqlite3.Connection, row: dict) -> str:
    is_interrupt = row["status"] in _INTERRUPT_STATUSES
    dot_color = "var(--red)" if is_interrupt else "var(--accent)"
    card_style = (
        "display:block; border-color:oklch(66% 0.17 25 / 0.4); background:var(--red-soft); margin-bottom:10px;"
        if is_interrupt else
        "display:block; border-color:var(--border2); background:var(--panel2); margin-bottom:10px;"
    )

    interrupt_note_html = ""
    if is_interrupt:
        reason = ds.interrupt_reason(conn, row["id"], row["status"])
        prefix = "BLOCKED" if row["status"] == "BLOCKED" else "Awaiting Founder decision"
        text = e(reason) if reason else "No note recorded for this transition."
        interrupt_note_html = (
            f'<div style="font-size:11px; color:var(--red); background:var(--red-soft); border-radius:6px; '
            f'padding:5px 9px; margin:6px 0 8px; line-height:1.4;">{e(prefix)} &mdash; {text}</div>'
        )

    return f'''
    <a href="tasks/{row["id"]}.html" class="card" style="{card_style}">
      <div style="display:flex; align-items:flex-start; gap:12px;">
        <div style="width:8px; height:8px; border-radius:50%; background:{dot_color}; margin-top:5px; flex-shrink:0;"></div>
        <div style="flex:1; min-width:0;">
          <div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px; flex-wrap:wrap;">
            <div style="font-size:13px; font-weight:600;">
              <span class="mono" style="color:var(--text3); font-weight:400; font-size:11px;">TASK-{row["id"]:03d}</span>
              &nbsp;&mdash;&nbsp;{e(row["title"])}
            </div>
            <div>{_founder_pill(row["founder_action_required"])}{_stuck_badge(conn, row)}</div>
          </div>
          {interrupt_note_html}
          <div style="font-size:11.5px; color:var(--text2); margin-top:2px;">{_gate_line(conn, row)}</div>
          <div style="font-size:10.5px; color:var(--text3); margin-top:5px; line-height:1.6;">{_detail_line(conn, row)}</div>
        </div>
      </div>
    </a>'''


def render_summary_strip(rows: list[dict]) -> str:
    """Optional addition Design recommended (§1.6) — four counts over the
    exact same active_work_rows() list already being rendered, zero new
    query. Cheap and explicitly flagged non-required; included here since
    it costs nothing new to compute."""
    active = len(rows)
    founder_needed = sum(1 for r in rows if r["founder_action_required"])
    blocked_or_paused = sum(1 for r in rows if r["status"] in _INTERRUPT_STATUSES)
    stuck = sum(1 for r in rows if r["is_stuck"])
    return f'''
    <div class="panel" style="margin-bottom:16px;">
      <div style="display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:20px;">
        <div><div class="label" style="margin-bottom:4px;">Active tasks</div><div style="font-size:20px; font-weight:600;">{active}</div></div>
        <div><div class="label" style="margin-bottom:4px; color:var(--red);">Founder decision needed</div><div style="font-size:20px; font-weight:600; color:var(--red);">{founder_needed}</div></div>
        <div><div class="label" style="margin-bottom:4px;">Blocked / paused</div><div style="font-size:20px; font-weight:600;">{blocked_or_paused}</div></div>
        <div><div class="label" style="margin-bottom:4px;">Stuck (no activity &gt;{ds.STUCK_THRESHOLD_DAYS}d)</div><div style="font-size:20px; font-weight:600; color:var(--text2);">{stuck}</div></div>
      </div>
    </div>'''


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = ds.active_work_rows(conn)
    rows.sort(key=_sort_key, reverse=True)

    cards_html = "".join(render_card(conn, r) for r in rows) if rows else (
        '<div class="card" style="text-align:center; color:var(--text2);">Nothing active — every task is DONE.</div>'
    )

    body = f'''
<h1>Active Work <span style="font-size:11px; color:var(--text3); font-weight:400;">&mdash; read-only</span></h1>
<div class="sub" style="margin-top:-14px; max-width:820px;">
  Every non-DONE task, one row each, sorted Founder-decision-needed first, then stuck, then most-recently-active.
  &ldquo;N done &middot; M to go&rdquo; are two independently real counts, not a fraction &mdash; most tasks in this
  database skip ladder positions, so a fixed &ldquo;of 8&rdquo; total would misrepresent most rows.
</div>
{render_summary_strip(rows)}
{cards_html}'''
    return page("Active Work", "active-work.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
