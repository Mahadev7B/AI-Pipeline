#!/usr/bin/env python3
"""ops/control-center/generate_costs.py — TASK-020 (DEC-009 Milestone B).

Renders /costs.html: company-wide AI invocation cost visibility across
all five real invocation paths (Ask-Agent, Executive Meetings, Chief of
Staff, Automated Code Review, and — shown honestly, per Design's review
item 6 / Red Team's §1 — Synchronous review, currently unused while
TASK-017 stays paused per DEC-008). Read-only: no spend ceiling, no
write-side control, no denominator on the headline figures — see
ops/reviews/cto-milestone-b-architecture.md §3.5. Same shape as every
other top-level generate_*.py — read-only dbutil.connect(),
build_html(token=...).

Layout follows Design's approved Concept A (`ops/mockups/milestone-b/Main.dc.html`,
recommended in ops/reviews/design-review-milestone-b.md): a single-column
stacked digest — header note, two headline stat cards (today/all-time),
then three stacked panels (by invocation path, by agent, recent
meetings) — not a two-column dashboard. Every SUM(...cost_usd) figure
here goes through derived_state.cost_coverage()/format_cost_coverage(),
the shared "count, not just sum, decides what's shown" discipline that
also implements Red Team's required fix (never a bare "$0.00" when zero
of N invocations have a recorded cost, not just when N itself is zero).

Usage:
    python3 ops/control-center/generate_costs.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import derived_state as ds  # noqa: E402
from dbutil import connect, out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

OUT_PATH = out_path("costs.html", "OPSDB_COSTS_PATH")


def _stat_card(label: str, cov: dict, accent: bool = False) -> str:
    """Today's/all-time's headline figure. Design's review §1.1: when
    nothing has ever been recorded (cov["n"] == 0), this deliberately
    renders NO dollar sign at all — "0 invocations" is a real, different
    fact from "$0.00 spent," and conflating them would misread as "AI use
    is free here" rather than "AI use hasn't happened yet." """
    color = "var(--accent)" if accent else "var(--text)"
    if cov["n"] == 0:
        big = '<div style="font-size:26px; font-weight:700; color:var(--text3); margin-bottom:4px;">&mdash;</div>'
        detail = "0 invocations recorded, across every invocation path (see breakdown below)."
    elif cov["covered"] == 0:
        big = '<div style="font-size:26px; font-weight:700; color:var(--text3); margin-bottom:4px;">not available</div>'
        detail = f'0 of {cov["n"]} invocations have a recorded cost (recorded before cost tracking).'
    else:
        big = f'<div style="font-size:26px; font-weight:700; color:{color}; margin-bottom:4px;">${cov["usd"]:.2f}</div>'
        missing = cov["n"] - cov["covered"]
        detail = f'{cov["covered"]} of {cov["n"]} invocations tracked' + (
            f' ({missing} recorded before cost tracking).' if missing else '.')
    return f'''
    <div class="panel" style="flex:1;">
      <div class="label" style="margin-bottom:8px;">{e(label)}</div>
      {big}
      <div style="font-size:11px; color:var(--text3); line-height:1.5;">{e(detail)}</div>
    </div>'''


def render_advisory(digest: dict) -> str:
    """Design's review §1.1: this specific, literal-state banner only
    holds while nothing has ever been recorded — the moment real spend
    exists, each row's own format_cost_coverage() text already carries
    the same "recorded before cost tracking" distinction, so a permanent
    banner claiming "no invocation has been recorded" would go stale and
    false. Rendered only when digest["all_time"]["n"] == 0."""
    if digest["all_time"]["n"] != 0:
        return ""
    return '''
    <div style="border-radius:10px; border:1px dashed var(--border2); background:var(--panel2); padding:12px 14px; margin-bottom:20px;">
      <div style="font-size:11px; color:var(--text2); line-height:1.6;">
        <b style="color:var(--text);">Cost tracking begins today.</b> No Ask-Agent, Meeting, Chief-of-Staff, or Code Review
        invocation has been recorded with a real cost yet &mdash; this is the actual current state of the operational
        database, not a placeholder. Figures below will populate as the four paths are used. A separate, distinct case
        &mdash; a real invocation whose cost was never captured, because it happened before this page shipped &mdash; is
        labeled <i>&ldquo;recorded before cost tracking&rdquo;</i> everywhere it appears, never merged with
        &ldquo;hasn&rsquo;t happened yet.&rdquo;
      </div>
    </div>'''


def render_by_path(digest: dict) -> str:
    rows = []
    for entry in digest["by_path"]:
        rows.append(f'''
    <div class="card" style="margin-bottom:8px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
      <div style="font-size:12.5px; font-weight:600;">{e(entry["label"])}</div>
      <div style="font-size:11px; color:var(--text3); text-align:right;">{e(ds.format_cost_coverage(entry["cov"]))}</div>
    </div>''')
    return f'''
    <div class="panel" style="margin-bottom:16px;">
      <div class="label" style="margin-bottom:10px;">By invocation path</div>
      {"".join(rows)}
      <div style="font-size:10px; color:var(--text3); margin-top:6px; line-height:1.5;">&ldquo;Synchronous review&rdquo;
        is a fifth real invocation path (<span class="mono" style="font-size:9.5px;">reviewer_sync.py</span>, TASK-017)
        distinct from the automation poller &mdash; shown as its own row rather than folded silently into Automated Code
        Review. Its cost stays &ldquo;not available&rdquo; by construction while TASK-017 stays paused (DEC-008) —
        <span class="mono" style="font-size:9.5px;">reviewer_sync.py</span>'s own end_run() calls do not yet pass
        cost_usd, a disclosed, out-of-scope consequence for this milestone, not a bug in the figures above.</div>
    </div>'''


def render_by_agent(digest: dict) -> str:
    rows = digest["by_agent"]
    if not rows:
        return '''
    <div class="panel" style="margin-bottom:16px;">
      <div class="label" style="margin-bottom:8px;">By agent <span style="font-weight:400; text-transform:none; color:var(--text3);">&mdash; Ask-Agent + Chief of Staff conversations</span></div>
      <div style="font-size:11.5px; color:var(--text2);">No Ask-Agent or Chief-of-Staff activity recorded yet.</div>
    </div>'''
    cards = []
    for entry in rows:
        cards.append(f'''
        <div class="card" style="margin-bottom:8px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
          <div style="font-size:12.5px; font-weight:600;">{e(ds.display_name(entry["name"]))}</div>
          <div style="font-size:11px; color:var(--text3); text-align:right;">{e(ds.format_cost_coverage(entry["cov"]))}</div>
        </div>''')
    return f'''
    <div class="panel" style="margin-bottom:16px;">
      <div class="label" style="margin-bottom:8px;">By agent <span style="font-weight:400; text-transform:none; color:var(--text3);">&mdash; Ask-Agent + Chief of Staff conversations</span></div>
      {"".join(cards)}
    </div>'''


def render_recent_meetings(digest: dict) -> str:
    rows = digest["recent_meetings"]
    if not rows:
        return '''
    <div class="panel">
      <div class="label" style="margin-bottom:8px;">Recent meetings, with cost</div>
      <div style="font-size:11.5px; color:var(--text2);">No executive meetings recorded yet. Meetings will appear here,
        most recent first, with each meeting&rsquo;s real total once one is raised.</div>
    </div>'''
    cards = []
    for m in rows:
        cards.append(f'''
        <a href="meetings/{m["id"]}.html" class="card" style="margin-bottom:8px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
          <div style="font-size:12.5px; font-weight:600;">#{m["id"]} &mdash; {e(m["topic"])}</div>
          <div style="font-size:11px; color:var(--text3); text-align:right;">{e(ds.format_cost_coverage(m["cov"]))}</div>
        </a>''')
    return f'''
    <div class="panel">
      <div class="label" style="margin-bottom:8px;">Recent meetings, with cost</div>
      {"".join(cards)}
    </div>'''


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    digest = ds.company_cost_digest(conn)

    body = f'''
<h1>Costs</h1>
<div class="sub" style="margin-top:-2px;">Company-wide AI invocation cost across every AI invocation path &mdash; see
  &ldquo;By invocation path&rdquo; below for the current full list. Read-only: no spend ceiling or write-side control
  lives here &mdash; see <a class="accentlink" href="automation.html">Automation</a> for the poller's own $10.00/day cap,
  unchanged and unduplicated.</div>
{render_advisory(digest)}
<div style="display:flex; gap:14px; margin-bottom:16px;">
{_stat_card("Today's AI spend", digest["today"])}
{_stat_card("All-time AI spend", digest["all_time"], accent=True)}
</div>
{render_by_path(digest)}
{render_by_agent(digest)}
{render_recent_meetings(digest)}'''
    return page("Costs", "costs.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
