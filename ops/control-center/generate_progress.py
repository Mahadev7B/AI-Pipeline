#!/usr/bin/env python3
"""ops/control-center/generate_progress.py — Milestone D (TASK-022).

Project / Phase Progress: `/progress.html`, the fourth and final milestone
of DEC-009's Founder UI Completeness plan. Follows the exact
`generate_decisions.py`/`generate_risks.py` precedent (`build_html(token=
None)` self-connecting via `dbutil.connect()` mode=ro, rendered through
`layout.page()`, one new `NAV_LINKS` entry). Backed by the shared computed
functions `derived_state.phase_progress_rows()` and
`derived_state.founder_readiness_summary()` — see
ops/reviews/cto-milestone-d-architecture.md (Parts 3.4, 4) and
ops/reviews/design-review-milestone-d.md (the "Right now" panel addition,
folded in below — no new query, reuses `founder_readiness_summary()` /
the same `phases` row already computed for the tree, plus
`derived_state.active_tasks_digest()` unchanged, Milestone A's own base
query).

Read-only page: `phases` itself has exactly one write path — the CLI
commands `opsdb.py phase-add`/`phase-set-status` — no HTTP write route
here, ever (per the architecture's own stated constraint). Zero
client-side JS — same anchor-based, single-page rendering model as
`/risks.html`/`/decisions.html`.

Usage:
    python3 ops/control-center/generate_progress.py
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

OUT_PATH = out_path("progress.html", "OPSDB_PROGRESS_PATH")

# Design review's Part 3 confirmation: complete=green, in_progress=accent,
# not_started=gray all already matched the established convention exactly.
# `paused` — the one genuinely new value — recommended blue, reusing the
# existing agent "waiting" semantic one level up (a phase, not an agent
# run, but the same idea: temporarily halted, not urgent, not active).
# Red rejected (already means "open risk"/danger elsewhere); violet
# rejected (already spoken for — actor identity, alert strips). See
# ops/reviews/design-review-milestone-d.md §3.
_STATUS_COLOR = {
    "complete": "var(--green)",
    "in_progress": "var(--accent)",
    "not_started": "var(--text2)",
    "paused": "var(--blue)",
}
_STATUS_LABEL = {
    "complete": "Complete",
    "in_progress": "In Progress",
    "not_started": "Not Started",
    "paused": "Paused",
}

# Design review's Part 5: task statuses signaling Founder action needed
# render with the same red pill this project already uses elsewhere
# (generate_active_work.py's founder_action_required convention) — a
# lighter-weight, page-local echo, not a second copy of that function's
# full logic (this page never needs gates/bounce/cost, only the status
# string itself).
_FOUNDER_NEEDED_TASK_STATUSES = ("FOUNDER_APPROVAL", "BLOCKED")


def _status_pill_html(status: str) -> str:
    color = _STATUS_COLOR.get(status, "var(--text2)")
    label = _STATUS_LABEL.get(status, e(status))
    return f'<span class="pill" style="background:{color}22; color:{color};">{label}</span>'


def _task_status_pill_html(status: str) -> str:
    if status in _FOUNDER_NEEDED_TASK_STATUSES:
        return f'<span class="pill" style="background:var(--red-soft); color:var(--red);">{e(status.replace("_", " ").title())}</span>'
    return f'<span class="pill" style="background:var(--gray-soft); color:var(--text2);">{e(status.replace("_", " ").title())}</span>'


def _decision_link_html(decision_id: int | None, decision_date: str | None) -> str:
    if decision_id is None:
        return ""
    label = f"#{decision_id}" + (f" · {e(decision_date)}" if decision_date else "")
    return (f'<a href="decisions.html#decision-{decision_id}" class="mono" '
            f'style="font-size:10.5px; color:var(--text3);">{label}</a>')


def _task_link_html(task_id: int | None) -> str:
    if task_id is None:
        return ""
    return (f'<a href="tasks/{task_id}.html" class="mono accentlink" '
            f'style="font-size:10.5px;">TASK-{task_id:03d} &rarr;</a>')


def _milestones_fraction_html(row: dict) -> str:
    if row["milestones_total"] is None or row["milestones_complete"] is None:
        return ""
    return (f'<span style="font-size:11px; color:var(--text3);">'
            f'{row["milestones_complete"]} of {row["milestones_total"]} milestones</span>')


def _build_tree(rows: list[dict]) -> tuple[list[dict], dict[int, list[dict]]]:
    """Split phase_progress_rows() into top-level rows (parent_phase_id is
    NULL) and a {parent_id: [children]} map — both already sort_order-
    ordered by the query itself. At most two levels of real nesting exist
    in the data (architecture doc Part 2) — this is a plain grouping, not
    a recursive-tree builder."""
    top_level = [r for r in rows if r["parent_phase_id"] is None]
    children: dict[int, list[dict]] = {}
    for r in rows:
        if r["parent_phase_id"] is not None:
            children.setdefault(r["parent_phase_id"], []).append(r)
    return top_level, children


def _phase_row_html(row: dict, depth: int) -> str:
    """One phase row. `depth` 0/1/2 controls indent + the accent-tinted,
    left-border-connector treatment Design specified (§4) for the
    in-progress branch (Phase 3 itself, and Founder UI Completeness
    nested under it) — a styling-only distinction, same rows/order/data
    as CTO's Part 4.3 tree."""
    is_active_branch = row["status"] == "in_progress" and depth < 2
    row_style = (
        "display:flex; align-items:center; justify-content:space-between; gap:14px; "
        "padding:9px 12px; border-radius:8px; margin:2px 0;"
    )
    if is_active_branch:
        row_style += " border-left:2px solid var(--accent); background:var(--accent-soft); font-weight:600;"
    elif row["status"] == "complete":
        row_style += " opacity:0.72;"
    elif row["status"] == "not_started":
        row_style += " opacity:0.6;"

    title_size = "13px" if is_active_branch else "12.5px"
    anchor = f' id="tree-{e(row["name"].lower().replace(" ", "-"))}"' if row["name"] == "Founder UI Completeness" else ""
    left = (
        f'<div style="display:flex; align-items:center; gap:10px;">'
        f'{_status_pill_html(row["status"])}'
        f'<span style="font-size:{title_size};">{e(row["name"])}</span>'
        f'{_milestones_fraction_html(row)}'
        f'</div>'
    )
    links = []
    opened = _decision_link_html(row["opened_decision_id"], row["opened_decision_date"])
    closed = _decision_link_html(row["closed_decision_id"], row["closed_decision_date"])
    if opened and closed and row["opened_decision_id"] != row["closed_decision_id"]:
        links.append(f'{opened} &rarr; {closed}')
    else:
        links.append(closed or opened)
    task_link = _task_link_html(row["task_id"])
    if task_link:
        links.append(task_link)
    right = f'<div style="display:flex; gap:10px; align-items:center;">{"".join(links)}</div>'

    note_html = (
        f'<div style="font-size:11px; color:var(--text2); padding:0 12px 8px {14 + depth * 26}px; '
        f'line-height:1.5; max-width:760px;">{e(row["note"])}</div>'
        if row["note"] else ""
    )
    return f'<div{anchor} style="{row_style}">{left}{right}</div>{note_html}'


def render_phase_tree(rows: list[dict]) -> str:
    if not rows:
        return ('<div style="font-size:12px; color:var(--text2);">No phase data recorded yet — run '
                '<span class="mono">opsdb.py phase-add</span> to backfill.</div>')
    top_level, children = _build_tree(rows)
    parts = []
    for phase in top_level:
        parts.append(_phase_row_html(phase, depth=0))
        kids = children.get(phase["id"], [])
        if kids:
            inner = []
            for child in kids:
                inner.append(_phase_row_html(child, depth=1))
                grandkids = children.get(child["id"], [])
                if grandkids:
                    inner_inner = "".join(_phase_row_html(g, depth=2) for g in grandkids)
                    inner.append(
                        f'<div style="padding-left:26px; border-left:2px solid var(--border2); margin-left:16px;">{inner_inner}</div>'
                    )
            parts.append(
                f'<div style="padding-left:26px; border-left:2px solid var(--border2); margin-left:16px;">{"".join(inner)}</div>'
            )
    return f'<div class="panel" style="padding:4px 16px;">{"".join(parts)}</div>'


def render_readiness_header(summary: dict) -> str:
    """CTO's Part 4.2 spec, confirmed unchanged by Design review §2: a
    pill (YES/NOT YET) plus one honest qualifying clause, in its own
    labeled card, larger pill sizing than an in-tree status pill so it
    reads as the page's headline the instant it loads."""
    ui_pill = ('YES' if summary["ui_100pct_complete"] else 'NOT YET')
    ui_color = 'var(--green)' if summary["ui_100pct_complete"] else 'var(--text2)'
    ui_bg = 'var(--green-soft)' if summary["ui_100pct_complete"] else 'var(--gray-soft)'
    ui_clause = f'{summary["milestones_done"]} of {summary["milestones_total"]} UI Completeness milestones done'

    testing_pill = ('YES' if summary["exploratory_testing_ready"] else 'NOT YET')
    testing_color = 'var(--green)' if summary["exploratory_testing_ready"] else 'var(--text2)'
    testing_bg = 'var(--green-soft)' if summary["exploratory_testing_ready"] else 'var(--gray-soft)'
    testing_clause = 'Milestones A + B + C complete' if summary["exploratory_testing_ready"] else 'Milestones A + B + C not yet all complete'

    return f'''
<div class="panel" style="margin-bottom:16px; border-color:var(--border2);">
  <div class="label" style="margin-bottom:10px;">Founder readiness &mdash; computed, not narrated</div>
  <div style="display:flex; flex-direction:column; gap:10px;">
    <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
      <span class="pill" style="background:{ui_bg}; color:{ui_color}; font-weight:700; padding:4px 11px; font-size:11px;">{ui_pill}</span>
      <div style="font-size:13px;"><b>Founder UI 100% feature-complete</b> <span style="color:var(--text2);">&mdash; {e(ui_clause)}</span></div>
    </div>
    <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
      <span class="pill" style="background:{testing_bg}; color:{testing_color}; font-weight:700; padding:4px 11px; font-size:11px;">{testing_pill}</span>
      <div style="font-size:13px;"><b>Exploratory Founder Testing ready</b> <span style="color:var(--text2);">&mdash; {e(testing_clause)}</span></div>
    </div>
  </div>
</div>'''


def _in_flight_rows(conn: sqlite3.Connection, phase_rows: list[dict]) -> list[sqlite3.Row]:
    """Every task from `active_tasks_digest()` (Milestone A's existing
    base query, unchanged) not already reachable via a `task_id` on a
    `phases` row above — i.e. TASK-016/017/018 today, whatever the real
    set is at render time (architecture doc Part 4.4). Computed once and
    shared by both the "Right now" panel (Design review §1, summary form)
    and the fuller in-flight-work register below it (§5's intentional,
    small duplication) — one query, not two."""
    covered_task_ids = {r["task_id"] for r in phase_rows if r["task_id"] is not None}
    return [t for t in ds.active_tasks_digest(conn) if t["id"] not in covered_task_ids]


def render_right_now_panel(conn: sqlite3.Connection, summary: dict, phase_rows: list[dict], in_flight: list[sqlite3.Row]) -> str:
    """Design review's required addition (§1): the one genuinely live,
    actionable fact — the Founder UI Completeness sub-plan's real
    fraction and the tasks currently needing Founder attention — surfaced
    above the historical phase tree instead of buried two indent levels
    deep. No new query: reuses `founder_readiness_summary()`, the same
    "Founder UI Completeness" `phases` row already computed for the tree,
    and the same `_in_flight_rows()` list Part 4.4's section renders
    below (TASK-016/017/018, not Milestone D's own TASK-022 — that task
    is already covered by its own `phases` row, so it's correctly
    excluded from this "needs attention elsewhere" list, matching the
    Design mockup)."""
    ui_row = next((r for r in phase_rows if r["name"] == "Founder UI Completeness"), None)
    fraction_text = (
        f'{summary["milestones_done"]} of {summary["milestones_total"]}'
        if ui_row is None else
        f'{ui_row["milestones_complete"]} of {ui_row["milestones_total"]}'
    )

    chips = "".join(
        f'<a href="tasks/{t["id"]}.html" class="taskchip" '
        f'style="display:inline-flex; align-items:center; gap:8px; padding:6px 10px; '
        f'border-radius:8px; background:var(--panel2); font-size:11.5px;">'
        f'<span class="mono" style="color:var(--text3); font-size:10.5px;">TASK-{t["id"]:03d}</span>'
        f'<span>{e(t["title"])}</span>{_task_status_pill_html(t["status"])}</a>'
        for t in in_flight
    )
    chips_html = chips or '<span style="font-size:11.5px; color:var(--text3);">No in-flight tasks.</span>'

    return f'''
<div style="display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:11px;
     background:var(--accent-soft); border:1px solid oklch(78% 0.14 75 / 0.35); margin-bottom:22px;">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style="flex-shrink:0; margin-top:1px;"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" stroke="var(--accent)" stroke-width="1.6" stroke-linejoin="round"/></svg>
  <div style="flex:1; display:flex; flex-direction:column; gap:8px;">
    <div class="label" style="color:var(--accent);">Right now &mdash; the one thing actually moving</div>
    <div style="font-size:13px;"><b>Founder UI Completeness &mdash; {e(fraction_text)}</b></div>
    <div style="display:flex; gap:8px; flex-wrap:wrap;">{chips_html}</div>
    <a href="#tree-founder-ui-completeness" style="font-size:10.5px; color:var(--accent); font-weight:600;">Jump to the phase tree &rarr;</a>
  </div>
</div>'''


def render_in_flight_work(rows: list[sqlite3.Row]) -> str:
    """CTO's Part 4.4 — every non-DONE task not already reachable via a
    `task_id` on a `phases` row above (`_in_flight_rows()`, shared with
    the "Right now" panel above). Kept as the authoritative, complete,
    never-stale register even though the "Right now" panel above already
    shows the same tasks in summary form (Design review §5 — an
    intentional small duplication, same pattern as Milestone C's Risks
    page)."""
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No in-flight work outside the phase tree above.</div>'
    items = "".join(
        f'<div class="phaserow" style="display:flex; align-items:center; justify-content:space-between; '
        f'gap:14px; padding:9px 12px; border-bottom:1px solid var(--border);">'
        f'<div style="display:flex; align-items:center; gap:10px;">'
        f'<a href="tasks/{t["id"]}.html" class="mono accentlink" style="font-size:10.5px;">TASK-{t["id"]:03d}</a>'
        f'<span style="font-size:12px;">{e(t["title"])}</span></div>'
        f'{_task_status_pill_html(t["status"])}</div>'
        for t in rows
    )
    return f'<div class="panel" style="padding:6px 16px;">{items}</div>'


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    phase_rows = ds.phase_progress_rows(conn)
    summary = ds.founder_readiness_summary(conn)
    in_flight = _in_flight_rows(conn, phase_rows)

    body = f'''
<h1>Project / Phase Progress <span style="font-size:11px; color:var(--text3); font-weight:400;">&mdash; read-only</span></h1>
<div class="sub" style="margin-top:-14px; max-width:820px;">
  How far along the company is, at the roadmap level &mdash; not a substitute for Active Work's per-task view.
</div>
{render_readiness_header(summary)}
{render_right_now_panel(conn, summary, phase_rows, in_flight)}
<div class="label" style="margin-bottom:8px;">Phase tree</div>
<div style="margin-bottom:18px;">{render_phase_tree(phase_rows)}</div>
<div class="label" style="margin-bottom:8px;">Currently in-flight work <span style="font-weight:400; text-transform:none; color:var(--text3);">&mdash; every non-DONE task not already covered by a phase row above (reused from Active Work's own digest)</span></div>
{render_in_flight_work(in_flight)}'''
    return page("Progress", "progress.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
