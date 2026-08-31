#!/usr/bin/env python3
"""ops/control-center/generate_task.py — Milestone A (TASK-019).

Generates /tasks/<id>.html — one Task Detail page per task, following the
same build_*_detail(conn, row, token=...) pattern generate_agents.py /
generate_meetings.py already establish (ops/reviews/cto-milestone-a-
architecture.md §4.1). Layout follows Design's review (§2): a compact
summary strip of scalar facts promoted above the section list, a vertical
(not kanban) gate timeline, an anchor-pill nav row, and — per Red Team's
required, non-blocking fix (ops/reviews/red-team-milestone-a-review.md
§2/§5 item 4) — review_results/qa_results are fetched ONCE per page and
rendered three ways (Gate timeline inline notes, the Bounces summary
stat, and the full Findings section), never queried three times.

Every field has a real source or an honest "—"/"not available" — no
fabricated data anywhere (cost/usage in particular: see
ops/db/derived_state.py's task_cost_usd()).

Read-only: dbutil.connect() (mode=ro), zero writes, zero new routes.

Usage:
    python3 ops/control-center/generate_task.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import derived_state as ds  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

# Anchors where the per-task detail files go — same pattern
# generate_agents.py uses for AGENTS_SUBDIR (a sibling "tasks.html" name
# purely to resolve the right directory via dbutil.out_path()'s existing
# OPSDB_PATH-scratch-testing convention; there is no top-level
# /tasks.html list page — Active Work is that list, see §3/§6.1).
OUT_PATH = out_path("tasks.html", "OPSDB_TASKS_PATH")
TASKS_SUBDIR = OUT_PATH.parent / "tasks"

_INTERRUPT_STATUSES = ("BLOCKED", "FOUNDER_APPROVAL")

# Overrides for reviewed_by_agent labels that don't read well as
# "<display_name> review" — matches ops/reviews/cto-milestone-a-
# architecture.md §0/§1.6's labeling convention (label by
# reviewed_by_agent, not review_type, since Red Team/CTO Conformance
# rows both carry review_type='code' today).
_REVIEW_LABEL_OVERRIDE = {
    "cto": "CTO Conformance",
    "red-team": "Red Team review",
    "security": "Security review",
    "design": "Design review",
    "code-review": "Code review",
}


def _review_label(reviewed_by_agent: str, review_type: str) -> str:
    if reviewed_by_agent in _REVIEW_LABEL_OVERRIDE:
        return _REVIEW_LABEL_OVERRIDE[reviewed_by_agent]
    kind = "security" if review_type == "security" else "code"
    return f"{e(ds.display_name(reviewed_by_agent))} {kind} review"


def _fetch_findings(conn: sqlite3.Connection, task_id: int) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    """The one fetch, reused by the gate timeline, the Bounces summary
    stat, and the Findings section — see Red Team's required fix."""
    reviews = conn.execute(
        "SELECT id, review_type, reviewed_by_agent, result, findings, returned_to_agent, created_at "
        "FROM review_results WHERE task_id = ? ORDER BY created_at, id",
        (task_id,),
    ).fetchall()
    qa = conn.execute(
        "SELECT id, tested_by_agent, scenario, result, defect_summary, reproduction_steps, "
        "returned_to_agent, created_at FROM qa_results WHERE task_id = ? ORDER BY created_at, id",
        (task_id,),
    ).fetchall()
    return reviews, qa


def _gate_bucket_for_timestamp(history_asc: list[sqlite3.Row], at: str) -> str | None:
    """The most recent GATE_STATUS_ORDER position that was active at or
    before `at`, walking backward through non-ladder statuses
    (BLOCKED/FOUNDER_APPROVAL) exactly like effective_gate_status() does
    for 'now' — same algorithm, time-bounded instead of live-bounded, so
    a finding recorded while the task was mid-interrupt is still
    attributed to the real gate it interrupted, not silently dropped."""
    candidate = None
    for h in history_asc:
        if h["changed_at"] > at:
            break
        if h["to_status"] in ds.GATE_STATUS_ORDER:
            candidate = h["to_status"]
    return candidate


def render_anchor_nav() -> str:
    sections = [
        ("gates", "Gate timeline"), ("history", "Status history"),
        ("handoffs", "Handoffs"), ("findings", "Review / QA findings"),
        ("decisions", "Founder decisions"), ("risks", "Associated risks"),
        ("activity", "Activity"),
    ]
    pills = "".join(
        f'<a href="#{sec_id}" class="pill" style="background:var(--panel2); color:var(--text2); '
        f'border:1px solid var(--border2);">{e(label)}</a>'
        for sec_id, label in sections
    )
    return f'<div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:20px;">{pills}</div>'


def render_interrupt_banner(conn: sqlite3.Connection, row: dict) -> str:
    if row["status"] not in _INTERRUPT_STATUSES:
        return ""
    is_blocked = row["status"] == "BLOCKED"
    title = "Blocked · paused, not stuck" if is_blocked else "Founder approval needed"
    reason = ds.interrupt_reason(conn, row["id"], row["status"])
    detail = e(reason) if reason else "No note recorded for this transition."
    return f'''
<div style="border-radius:10px; border:1px solid oklch(66% 0.17 25 / 0.4); background:var(--red-soft); padding:12px 14px; margin-bottom:16px;">
  <div style="font-size:11px; font-weight:700; color:var(--red); letter-spacing:0.03em; text-transform:uppercase; margin-bottom:4px;">{e(title)}</div>
  <div style="font-size:12px; color:var(--text2); line-height:1.5;">{detail}</div>
</div>'''


def render_summary_panel(conn: sqlite3.Connection, row: dict) -> str:
    owner = e(ds.display_name(row["current_owner"])) if row["current_owner"] else "unassigned"
    elapsed_created = ds.elapsed_since(conn, row["created_at"])
    elapsed_gate = ds.elapsed_since(conn, row["gate_entered_at"]) if row["gate_entered_at"] else None
    elapsed_html = f"{elapsed_created} since created"
    if row["status"] in _INTERRUPT_STATUSES:
        last_at = (row["last_event"] or {}).get("at")
        if last_at:
            since_label = "paused" if row["status"] == "BLOCKED" else "flagged"
            elapsed_html += f'<br><span style="color:var(--text3); font-size:10.5px;">{ds.elapsed_since(conn, last_at)} since {since_label}</span>'
    elif elapsed_gate:
        elapsed_html += f'<br><span style="color:var(--text3); font-size:10.5px;">{elapsed_gate} in this gate</span>'

    next_action = e(row["next_action"]) if row["next_action"] else '&mdash; <span style="font-size:10.5px;">(not populated)</span>'
    if row["founder_action_required"]:
        founder_html = '<span style="color:var(--red); font-weight:600;">Yes</span>'
    else:
        founder_html = '<span style="color:var(--text2);">No</span>'
    cost = row["cost"]
    cost_html = f'${cost["usd"]:.2f}' if cost["available"] else '<span style="color:var(--text3);">not available</span>'

    return f'''
<div class="panel" style="margin-bottom:20px;">
  <div style="display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:18px;">
    <div><div class="label" style="margin-bottom:4px;">Owner</div><div style="font-size:12.5px;">{owner}</div></div>
    <div><div class="label" style="margin-bottom:4px;">Elapsed</div><div style="font-size:12.5px;">{elapsed_html}</div></div>
    <div><div class="label" style="margin-bottom:4px;">Bounces</div><div style="font-size:12.5px; {"color:var(--red); font-weight:600;" if row["bounce_count"] else ""}">{row["bounce_count"]} <a href="#findings" class="accentlink" style="font-size:10.5px; font-weight:400;">&rarr; findings</a></div></div>
    <div><div class="label" style="margin-bottom:4px;">Next action</div><div style="font-size:12.5px; color:var(--text3);">{next_action}</div></div>
    <div><div class="label" style="margin-bottom:4px;">Founder action needed</div><div style="font-size:12.5px;">{founder_html}</div></div>
    <div><div class="label" style="margin-bottom:4px;">Cost</div><div style="font-size:12.5px;">{cost_html}</div></div>
  </div>
</div>'''


def render_gate_timeline(row: dict, history_asc: list[sqlite3.Row],
                          reviews: list[sqlite3.Row], qa: list[sqlite3.Row]) -> str:
    completed_set = set(row["gates_completed"])
    effective_status = row["effective_gate_status"]

    # Bucket every review/QA row by the gate it happened during (§ above).
    buckets: dict[str, list[dict]] = {s: [] for s in ds.GATE_STATUS_ORDER}
    for r in reviews:
        bucket = _gate_bucket_for_timestamp(history_asc, r["created_at"])
        if bucket:
            buckets[bucket].append({
                "label": _review_label(r["reviewed_by_agent"], r["review_type"]),
                "result": r["result"], "created_at": r["created_at"],
            })
    for r in qa:
        bucket = _gate_bucket_for_timestamp(history_asc, r["created_at"])
        if bucket:
            buckets[bucket].append({"label": "QA", "result": r["result"], "created_at": r["created_at"]})

    entries = []
    for status in ds.GATE_STATUS_ORDER:
        if status == "DONE":
            continue
        findings = buckets.get(status, [])
        if status in completed_set:
            state = "DONE"
            dot = ('<div style="width:16px; height:16px; border-radius:50%; background:var(--green); '
                   'display:flex; align-items:center; justify-content:center; flex-shrink:0;">'
                   '<svg width="9" height="9" viewBox="0 0 24 24" fill="none"><path d="M4 12l6 6L20 6" '
                   'stroke="var(--bg)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></div>')
            pill = '<span class="pill" style="background:var(--green-soft); color:var(--green);">DONE</span>'
            title_color = "var(--text)"
        elif status == effective_status:
            state = "CURRENT"
            dot = '<div style="width:16px; height:16px; border-radius:50%; border:2px solid var(--accent); background:var(--bg); flex-shrink:0;"></div>'
            pill = '<span class="pill" style="background:var(--accent-soft); color:var(--accent);">CURRENT</span>'
            title_color = "var(--text)"
        else:
            state = "WAITING"
            dot = '<div style="width:16px; height:16px; border-radius:50%; border:2px solid var(--border2); background:transparent; flex-shrink:0;"></div>'
            pill = '<span class="pill" style="background:var(--gray-soft); color:var(--text3);">WAITING</span>'
            title_color = "var(--text3)"

        note_html = ""
        if findings:
            n_pass = sum(1 for f in findings if f["result"] == "pass")
            n_other = len(findings) - n_pass
            parts = []
            if n_pass:
                parts.append(f'{n_pass} pass')
            if n_other:
                labels = ", ".join(e(f["label"]) + " " + e(f["result"]) for f in findings if f["result"] != "pass")
                parts.append(f'{n_other} reject/fail ({labels})')
            note_html = (
                f'<div style="font-size:11.5px; color:var(--text2); margin-top:5px; line-height:1.6;">'
                f'{" &middot; ".join(parts)} '
                f'<a href="#findings" class="accentlink" style="font-size:10.5px;">&rarr; findings</a></div>'
            )
        elif state == "CURRENT" and row["status"] in _INTERRUPT_STATUSES:
            note_html = (
                f'<div style="font-size:11.5px; color:var(--text2); margin-top:5px; line-height:1.6;">'
                f'Waiting &mdash; task is currently {e(row["status"])}, has not exited this gate.</div>'
            )

        entries.append(f'''
    <div style="display:flex; gap:12px;">
      <div style="display:flex; flex-direction:column; align-items:center;">
        {dot}
        <div style="width:1px; flex:1; background:var(--border2); margin-top:2px;"></div>
      </div>
      <div style="flex:1; padding-bottom:20px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <div style="font-size:13px; font-weight:600; color:{title_color};">{e(ds.gate_display_label(status))}</div>
          {pill}
        </div>
        {note_html}
      </div>
    </div>''')

    finish_note = "reached" if "DONE" in completed_set or row["status"] == "DONE" else "not reached"
    return f'''
<div class="panel" id="gates" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:14px;">Gate timeline</div>
  {"".join(entries)}
  <div style="display:flex; gap:12px; align-items:center;">
    <div style="width:16px; height:16px; flex-shrink:0; display:flex; align-items:center; justify-content:center; color:var(--text3); font-size:11px;">&hellip;</div>
    <div style="font-size:11.5px; color:var(--text3);">Deployed / Done &mdash; {finish_note}</div>
  </div>
</div>'''


def render_status_history(conn: sqlite3.Connection, task_id: int) -> str:
    rows = conn.execute(
        "SELECT from_status, to_status, changed_by_agent, changed_at, note "
        "FROM task_status_history WHERE task_id = ? ORDER BY id DESC",
        (task_id,),
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No status history recorded (should not happen post-creation).</div>'
    cards = []
    for r in rows:
        frm = ds.gate_display_label(r["from_status"]) if r["from_status"] in ds.GATE_STATUS_ORDER else (
            "(created)" if r["from_status"] is None else e(r["from_status"]))
        to = ds.gate_display_label(r["to_status"]) if r["to_status"] in ds.GATE_STATUS_ORDER else e(r["to_status"])
        cards.append(f'''
    <div class="card" style="margin-bottom:8px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px;">
        <div style="font-size:12px; font-weight:600;">{frm} &rarr; {to}</div>
        <div class="mono" style="font-size:10px; color:var(--text3);">{e(r["changed_at"])}</div>
      </div>
      <div style="font-size:11px; color:var(--text2); margin-top:3px;">by {e(ds.display_name(r["changed_by_agent"]))}</div>
      {f'<div style="font-size:11px; color:var(--text2); margin-top:5px; line-height:1.5;">{e(r["note"])}</div>' if r["note"] else ""}
    </div>''')
    return "".join(cards)


def render_handoffs(conn: sqlite3.Connection, task_id: int) -> str:
    rows = conn.execute(
        "SELECT from_agent, to_agent, work_completed, files_changed, tests_added, "
        "expected_behavior, known_limitations, created_at FROM handoffs WHERE task_id = ? ORDER BY id DESC",
        (task_id,),
    ).fetchall()
    if not rows:
        return ('<div style="font-size:12px; color:var(--text2); line-height:1.5;">'
                'None recorded for this task &mdash; not necessarily an error; work at earlier gates '
                '(e.g. a Development pass not yet handed to Code Review) legitimately has none yet.</div>')
    cards = []
    for r in rows:
        files = r["files_changed"]
        cards.append(f'''
    <div class="card" style="margin-bottom:8px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px;">
        <div style="font-size:12px; font-weight:600;">{e(ds.display_name(r["from_agent"]))} &rarr; {e(ds.display_name(r["to_agent"]))}</div>
        <div class="mono" style="font-size:10px; color:var(--text3);">{e(r["created_at"])}</div>
      </div>
      {f'<div style="font-size:11px; color:var(--text2); margin-top:5px;">{e(r["work_completed"])}</div>' if r["work_completed"] else ""}
      {f'<div style="font-size:10.5px; color:var(--text3); margin-top:5px;">Files: {e(files)}</div>' if files and files != "[]" else ""}
      {f'<div style="font-size:10.5px; color:var(--text3); margin-top:3px;">Known limitations: {e(r["known_limitations"])}</div>' if r["known_limitations"] else ""}
    </div>''')
    return "".join(cards)


def render_findings(reviews: list[sqlite3.Row], qa: list[sqlite3.Row]) -> str:
    if not reviews and not qa:
        return '<div style="font-size:12px; color:var(--text2);">No Code Review, QA, or Security findings recorded for this task yet.</div>'

    combined = []
    for r in reviews:
        combined.append(("review", r["created_at"], r))
    for r in qa:
        combined.append(("qa", r["created_at"], r))
    combined.sort(key=lambda t: t[1], reverse=True)

    cards = []
    for kind, _at, r in combined:
        result_color = "var(--green)" if r["result"] == "pass" else "var(--red)"
        result_soft = "var(--green-soft)" if r["result"] == "pass" else "var(--red-soft)"
        if kind == "review":
            label = _review_label(r["reviewed_by_agent"], r["review_type"])
            id_note = f"review_results #{r['id']}"
            by = e(ds.display_name(r["reviewed_by_agent"]))
            try:
                items = json.loads(r["findings"] or "[]")
                if not isinstance(items, list):
                    items = [str(items)]
            except (ValueError, TypeError):
                items = [r["findings"]] if r["findings"] else []
            body = "".join(f'<div style="margin-bottom:6px;">&bull; {e(i)}</div>' for i in items) or '<div style="color:var(--text3);">No findings text recorded.</div>'
        else:
            label = "QA"
            id_note = f"qa_results #{r['id']}"
            by = e(ds.display_name(r["tested_by_agent"]))
            parts = []
            if r["scenario"]:
                parts.append(f'Scenario: {e(r["scenario"])}')
            if r["defect_summary"]:
                parts.append(f'Defect: {e(r["defect_summary"])}')
            if r["reproduction_steps"]:
                parts.append(f'Repro: {e(r["reproduction_steps"])}')
            body = "".join(f'<div style="margin-bottom:6px;">{p}</div>' for p in parts) or '<div style="color:var(--text3);">No detail recorded.</div>'
        returned_note = (
            f'<div style="font-size:10.5px; color:var(--text3); margin-top:6px;">Returned to {e(ds.display_name(r["returned_to_agent"]))}</div>'
            if r["returned_to_agent"] else ""
        )
        cards.append(f'''
    <div class="card" style="margin-bottom:8px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin-bottom:4px;">
        <div style="font-size:12px; font-weight:600;">{e(label)} <span class="mono" style="font-size:10px; color:var(--text3); font-weight:400;">&middot; {e(id_note)}</span></div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="pill" style="background:{result_soft}; color:{result_color};">{e(r["result"])}</span>
          <div class="mono" style="font-size:10px; color:var(--text3);">{e(r["created_at"])}</div>
        </div>
      </div>
      <div style="font-size:11px; color:var(--text2); margin-bottom:4px;">by {by}</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">{body}</div>
      {returned_note}
    </div>''')
    return f'''
    <div style="font-size:11px; color:var(--text3); margin-bottom:12px; line-height:1.5;">
      All Code Review / QA / Security rows for this task, most recent first — the same rows summarized inline in the
      Gate timeline above and counted in the Bounces stat, shown here once, in full.
    </div>
    {"".join(cards)}'''


def render_decisions(conn: sqlite3.Connection, task_id: int) -> str:
    approvals = conn.execute(
        "SELECT id, request, requested_by_agent, decision, decided_at, created_at "
        "FROM approvals WHERE task_id = ? ORDER BY id DESC",
        (task_id,),
    ).fetchall()
    decisions = conn.execute(
        "SELECT d.id, d.title, d.decision, d.recommending_agent, d.created_at "
        "FROM decisions d JOIN approvals a ON a.id = d.founder_approval_id "
        "WHERE a.task_id = ? ORDER BY d.id DESC",
        (task_id,),
    ).fetchall()
    if not approvals and not decisions:
        return ('<div style="font-size:12px; color:var(--text2); line-height:1.5;">'
                'None recorded against this task directly &mdash; no <span class="mono">approvals</span> row, '
                'no linked <span class="mono">decisions</span> row. If a pause/interrupt affecting this task was '
                'still Founder-directed, see the Status history section above for how it was actually recorded.</div>')
    cards = []
    for a in approvals:
        pill_color = {"approve": "var(--green)", "reject": "var(--red)"}.get(a["decision"], "var(--text2)")
        pill_soft = {"approve": "var(--green-soft)", "reject": "var(--red-soft)"}.get(a["decision"], "var(--gray-soft)")
        cards.append(f'''
    <div class="card" style="margin-bottom:8px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px;">
        <div style="font-size:12px; font-weight:600;">Approval #{a["id"]} &mdash; {e(a["request"])}</div>
        <span class="pill" style="background:{pill_soft}; color:{pill_color};">{e(a["decision"])}</span>
      </div>
      <div style="font-size:11px; color:var(--text2); margin-top:3px;">requested by {e(ds.display_name(a["requested_by_agent"]))} &middot; {e(a["decided_at"] or a["created_at"])}</div>
    </div>''')
    for d in decisions:
        cards.append(f'''
    <div class="card" style="margin-bottom:8px;">
      <div style="font-size:12px; font-weight:600;">Decision #{d["id"]} &mdash; {e(d["title"])}</div>
      <div style="font-size:11px; color:var(--text2); margin-top:3px;">{e(d["decision"])} &middot; recommended by {e(ds.display_name(d["recommending_agent"]))} &middot; {e(d["created_at"])}</div>
    </div>''')
    return "".join(cards)


def render_risks(conn: sqlite3.Connection, task_id: int) -> str:
    rows = conn.execute(
        "SELECT id, title, severity, status, mitigation, owner_agent FROM risks "
        "WHERE scope_type = 'task' AND scope_id = ? ORDER BY id DESC",
        (task_id,),
    ).fetchall()
    if not rows:
        return ('<div style="font-size:12px; color:var(--text2); line-height:1.5;">'
                'None task-scoped to this task. A company-scoped risk this task may exist to reduce (scope_type='
                '<span class="mono">company</span>) intentionally does not appear here &mdash; that scope is '
                'company-wide, not this task\'s own, and stays visible only via Agent Detail pages until a future '
                'company-wide Risks register (Milestone C) ships. This is correct, disclosed behavior, not a gap.</div>')
    sev_color = {"high": "var(--red)", "medium": "var(--accent)", "low": "var(--text2)"}
    cards = []
    for r in rows:
        color = sev_color.get(r["severity"], "var(--text2)")
        cards.append(f'''
    <div class="card" style="margin-bottom:8px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px;">
        <div style="font-size:12px; font-weight:600;">Risk #{r["id"]} &mdash; {e(r["title"])}</div>
        <span class="pill" style="background:{color}22; color:{color};">{e(r["severity"])} &middot; {e(r["status"])}</span>
      </div>
      {f'<div style="font-size:11px; color:var(--text2); margin-top:4px;">{e(r["mitigation"])}</div>' if r["mitigation"] else ""}
    </div>''')
    return "".join(cards)


def render_activity(conn: sqlite3.Connection, task_id: int) -> str:
    rows = conn.execute(
        "SELECT summary, detail, created_at FROM agent_activity WHERE task_id = ? ORDER BY id DESC",
        (task_id,),
    ).fetchall()
    if not rows:
        return ('<div style="font-size:12px; color:var(--text2); line-height:1.5;">'
                'No <span class="mono">agent_activity</span> rows recorded for this task. Real, not an error &mdash; '
                'some tasks\' work is captured entirely via status history and review/QA results instead.</div>')
    items = []
    for r in rows:
        items.append(
            f'<div style="font-size:11.5px; color:var(--text2); margin-bottom:6px;">'
            f'<span class="mono" style="font-size:10px; color:var(--text3);">{e(r["created_at"])}</span> &middot; {e(r["summary"])}</div>'
        )
    return "".join(items)


def build_task_detail(conn: sqlite3.Connection, task_row: sqlite3.Row, token: str | None = None) -> str:
    task_id = task_row["id"]
    row = ds.task_progress_row(conn, task_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    history_asc = conn.execute(
        "SELECT to_status, changed_at FROM task_status_history WHERE task_id = ? ORDER BY id",
        (task_id,),
    ).fetchall()
    reviews, qa = _fetch_findings(conn, task_id)

    body = f'''
<h1>TASK-{task_id:03d} <span style="font-weight:400; color:var(--text2); font-size:16px;">&mdash; {e(row["title"])}</span></h1>
<div class="sub" style="margin-top:-14px; margin-bottom:16px;">Read-only</div>
{render_interrupt_banner(conn, row)}
{render_anchor_nav()}
{render_summary_panel(conn, row)}
{render_gate_timeline(row, history_asc, reviews, qa)}
<div class="panel" id="history" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:10px;">Status history <span style="font-weight:400; text-transform:none; color:var(--text3);">&mdash; most recent first</span></div>
  {render_status_history(conn, task_id)}
</div>
<div class="panel" id="handoffs" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:8px;">Handoffs</div>
  {render_handoffs(conn, task_id)}
</div>
<div class="panel" id="findings" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:4px;">Code Review / QA / Security findings</div>
  {render_findings(reviews, qa)}
</div>
<div class="panel" id="decisions" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:8px;">Founder decisions / approvals</div>
  {render_decisions(conn, task_id)}
</div>
<div class="panel" id="risks" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:8px;">Associated risks</div>
  {render_risks(conn, task_id)}
</div>
<div class="panel" id="activity" style="margin-bottom:16px;">
  <div class="label" style="margin-bottom:8px;">Activity timeline</div>
  {render_activity(conn, task_id)}
</div>'''
    return page(f"TASK-{task_id:03d} — Task Detail", "active-work.html", body, depth=1, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run generate_task.py to refresh.")


def main() -> None:
    conn = connect()
    tasks = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    TASKS_SUBDIR.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        detail_path = TASKS_SUBDIR / f"{t['id']}.html"
        write_output(detail_path, build_task_detail(conn, t))
    print(f"wrote {len(tasks)} task detail pages under {TASKS_SUBDIR}")


if __name__ == "__main__":
    main()
