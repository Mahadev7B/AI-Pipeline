#!/usr/bin/env python3
"""ops/control-center/generate_automation.py — Phase 3A Part B (TASK-015).

Renders /automation.html: the kill-switch state with a STOP/START form
(styled like the existing Approve/Reject buttons — no new visual
pattern), currently-running automation_events, recent terminal ones with
links to their tasks, and today's spend against the ceiling. Same shape
as generate_reviews.py/generate_releases.py — read-only dbutil.connect(),
build_html(token=...). The write itself always goes through
opsdb.set_automation_enabled(), never through this file; server.py's
POST /api/automation/stop|start routes call that directly, same
separation generate_inbox.py already keeps from opsdb.decide_approval().

Reads derived_state.automation_status_digest() — the SAME shared query
the Chief of Staff's own "what is running right now" answers read (§B.12)
— never a second, hand-typed copy of this fact.

Usage:
    python3 ops/control-center/generate_automation.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import derived_state  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("automation.html", "OPSDB_AUTOMATION_PATH")

# Same order-of-magnitude ceiling automation.py itself enforces
# (MAX_AUTOMATION_SPEND_USD_PER_DAY) — restated here as a plain literal
# (not imported) for the same reason derived_state.automation_status_digest()'s
# own docstring gives: this module is ops/db-adjacent read-only rendering,
# not a control-center -> db -> control-center import cycle. Development
# must keep this in sync with automation.MAX_AUTOMATION_SPEND_USD_PER_DAY
# if that constant is ever revised.
SPEND_CEILING_USD = 10.00

_STATUS_STYLE = {
    "completed": ("var(--green)", "var(--green-soft)"),
    "failed": ("var(--red)", "var(--red-soft)"),
    "skipped": ("var(--gray)", "var(--gray-soft)"),
    "running": ("var(--blue)", "var(--blue-soft)"),
}
_OUTCOME_STYLE = {
    "pass": ("var(--green)", "var(--green-soft)"),
    "reject": ("var(--red)", "var(--red-soft)"),
    "error": ("var(--red)", "var(--red-soft)"),
    "interrupted": ("var(--red)", "var(--red-soft)"),
    "capped": ("var(--violet)", "var(--violet-soft)"),
}


def _pill(text: str, color: str, soft: str) -> str:
    return f'<span class="pill" style="background:{soft}; color:{color};">{e(text)}</span>'


def _status_pill(row) -> str:
    if row["outcome"]:
        color, soft = _OUTCOME_STYLE.get(row["outcome"], ("var(--text2)", "var(--gray-soft)"))
        return _pill(f"{row['status']}/{row['outcome']}", color, soft)
    color, soft = _STATUS_STYLE.get(row["status"], ("var(--text2)", "var(--gray-soft)"))
    return _pill(row["status"], color, soft)


def render_kill_switch(automation: dict, token: str | None) -> str:
    tok = e(token or "")
    on = automation["enabled"]
    status_pill = _pill("AUTOMATION ON", "var(--green)", "var(--green-soft)") if on \
        else _pill("AUTOMATION OFF", "var(--text2)", "var(--gray-soft)")
    changed_note = (
        f'<div style="font-size:10.5px; color:var(--text3); margin-top:6px;">Last changed by '
        f'{e(automation["changed_by"])} at {e(automation["changed_at"])}'
        f'{": " + e(automation["reason"]) if automation["reason"] else ""}</div>'
        if automation["changed_at"] else ""
    )

    def form(action: str, label: str, color: str) -> str:
        return f'''
        <form method="POST" action="/api/automation/{action}" style="display:inline;">
          <input type="hidden" name="token" value="{tok}">
          <button type="submit" style="padding:9px 20px; border-radius:8px; border:1px solid {color};
            background:{color}22; color:{color}; font-size:13px; font-weight:700; cursor:pointer;">{e(label)}</button>
        </form>'''

    buttons = form("start", "START automation", "var(--green)") if not on else form("stop", "STOP automation", "var(--red)")

    return f'''
    <div class="panel" style="margin-bottom:16px;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
        <div class="label">Kill switch</div>
        {status_pill}
      </div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.5; margin-bottom:10px;">
        Stopping prevents any <b>new</b> automatic action from starting on the poller's next check
        (at most ~20 seconds later). It does <b>not</b> forcibly kill an already-in-flight
        Code Review invocation — bounded at $0.50 and 120 seconds, the same honest limitation Ctrl+C has
        always had for Ask-Agent. See <span class="mono">ops/SECURITY.md</span>.
      </div>
      {buttons}
      {changed_note}
    </div>'''


def render_spend(automation: dict) -> str:
    spent = automation["spend_today_usd"]
    pct = min(100, round(100 * spent / SPEND_CEILING_USD)) if SPEND_CEILING_USD else 0
    color = "var(--red)" if pct >= 90 else ("var(--accent)" if pct >= 60 else "var(--green)")
    return f'''
    <div class="panel" style="margin-bottom:16px;">
      <div class="label" style="margin-bottom:8px;">Today's automation spend</div>
      <div style="font-size:20px; font-weight:700; margin-bottom:6px;">${spent:.2f} <span style="font-size:12px; font-weight:400; color:var(--text3);">/ ${SPEND_CEILING_USD:.2f} daily ceiling</span></div>
      <div style="height:6px; border-radius:3px; background:var(--panel2); overflow:hidden;">
        <div style="height:100%; width:{pct}%; background:{color};"></div>
      </div>
    </div>'''


def render_running(automation: dict) -> str:
    rows = automation["running"]
    if not rows:
        return '<div class="panel" style="margin-bottom:16px;"><div class="label" style="margin-bottom:6px;">Running now</div><div style="font-size:12px; color:var(--text2);">Nothing running right now.</div></div>'
    cards = []
    for r in rows:
        cards.append(f'''
        <div class="card" style="margin-bottom:8px;">
          <a href="tasks/{r["task_id"]}.html" style="font-size:12.5px; font-weight:600;">TASK-{r["task_id"]:03d} — {e(r["task_title"])}</a>
          <div style="font-size:10.5px; color:var(--text3); margin-top:4px;">started {e(r["started_at"])} — still reviewing, ends automatically either way (120s timeout, $0.50 cap)</div>
        </div>''')
    return f'<div class="panel" style="margin-bottom:16px;"><div class="label" style="margin-bottom:8px;">Running now</div>{"".join(cards)}</div>'


def render_recent(automation: dict) -> str:
    rows = automation["recent_terminal"]
    if not rows:
        return '<div class="panel"><div class="label" style="margin-bottom:6px;">Recent</div><div style="font-size:12px; color:var(--text2);">No automated events recorded yet.</div></div>'
    cards = []
    for r in rows:
        # R6 (Security's Phase 3A threat-model review): an invalid-file-path
        # skip is a stronger signal of a real, possibly-adversarial data
        # problem than a routine skip — visually distinguished here (a
        # distinct border/label), without a new Founder-visible-flag
        # mechanism.
        is_invalid_path = bool(r["skip_reason"] and "invalid file path" in r["skip_reason"])
        border = "var(--violet)" if is_invalid_path else "var(--border2)"
        flag = _pill("NEEDS ATTENTION — invalid path", "var(--violet)", "var(--violet-soft)") if is_invalid_path else ""
        detail = f'<div style="font-size:11px; color:var(--text2); margin-top:4px;">{e(r["skip_reason"])}</div>' if r["skip_reason"] else ""
        cost = f' — ${r["cost_usd"]:.2f}' if r["cost_usd"] else ""
        truncated_note = ' <span style="color:var(--violet);">(transcript truncated)</span>' if r["truncated"] else ""
        review_link = (
            f' — <a href="reviews.html" style="color:var(--accent);">see review</a>'
            if r["review_result_id"] else ""
        )
        cards.append(f'''
        <div class="card" style="margin-bottom:8px; border-color:{border};">
          <div style="display:flex; align-items:baseline; justify-content:space-between; gap:8px;">
            <a href="tasks/{r["task_id"]}.html" style="font-size:12.5px; font-weight:600;">TASK-{r["task_id"]:03d} — {e(r["task_title"])}</a>
            <div style="display:flex; gap:6px; align-items:center;">{flag}{_status_pill(r)}</div>
          </div>
          <div style="font-size:10.5px; color:var(--text3); margin-top:4px;">{e(r["ended_at"] or r["started_at"])}{cost}{truncated_note}{review_link}</div>
          {detail}
        </div>''')
    return f'<div class="panel"><div class="label" style="margin-bottom:8px;">Recent ({len(rows)})</div>{"".join(cards)}</div>'


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    automation = derived_state.automation_status_digest(conn)

    body = f'''
<h1>Automation <span style="font-size:11px; color:var(--text3); font-weight:400;">— Phase 3A Part B</span></h1>
<div class="sub" style="margin-top:-14px;">
  Limited automated Code Review: when turned on, a background poller reviews a completed Developer
  handoff at most once per real Code Review entry. A PASS never advances the task past Code Review
  automatically; a REJECT is routed back to Development mechanically — never a new Developer invocation.
  See <span class="mono">ops/reviews/cto-phase3a-architecture.md</span> and
  <span class="mono">ops/SECURITY.md</span>.
</div>
{render_kill_switch(automation, token)}
{render_spend(automation)}
{render_running(automation)}
{render_recent(automation)}'''
    return page("Automation", "automation.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
