#!/usr/bin/env python3
"""ops/control-center/generate_risks.py — Milestone C (TASK-021).

Company-wide Risks register: `/risks.html`, a new top-level, read-only
page following the exact `generate_decisions.py` precedent
(`build_html(token=None)` self-connecting via `dbutil.connect()`,
rendered through `layout.page()`, one `NAV_LINKS` entry). Backed by the
one shared computed function `derived_state.risk_register_rows()` —
see ops/reviews/cto-milestone-c-architecture.md and
ops/reviews/design-review-milestone-c.md (three required refinements,
folded in below: the "Needs attention" strip, page-level — not
per-card — mitigation-history disclosure, and a capped mitigation-text
width).

Zero write route. Zero client-side JS — three sections (Open/Mitigated/
Resolved) with anchor-pill jump links, the same no-JS interaction model
every other multi-section Control Center page already uses.

Usage:
    python3 ops/control-center/generate_risks.py
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

OUT_PATH = out_path("risks.html", "OPSDB_RISKS_PATH")

# Same severity/status color mapping generate_task.py's render_risks()
# already established — visual consistency between the two places a risk
# can be seen (architecture doc §3.3).
_SEV_COLOR = {"high": "var(--red)", "medium": "var(--accent)", "low": "var(--text2)"}
_STATUS_COLOR = {"open": "var(--red)", "mitigated": "var(--accent)", "resolved": "var(--green)"}

# Design review's page-level "prior mitigation not preserved" disclosure
# (recommendation 2) — CTO's own wording (Part 1.1), unchanged, moved from
# per-card to once, page-level.
_HISTORY_DISCLOSURE = (
    "Only the current mitigation text is stored — prior versions are not "
    "preserved in the database. See ops/DECISIONS.md and linked decisions/"
    "reviews below for a risk's documented history."
)

_SECTIONS = [
    ("open", "Open", "var(--red)"),
    ("mitigated", "Mitigated", "var(--accent)"),
    ("resolved", "Resolved", "var(--green)"),
]


def _scope_html(r: dict) -> str:
    """Scope: task-scoped risks link to the real Task Detail page
    (Milestone A), company-scoped risks show a plain pill, project-scoped
    risks show plain text (no per-project detail page exists yet —
    architecture doc §4.3, honest non-link, not a gap)."""
    if r["scope_type"] == "task":
        title = r["scope_task_title"] or "(task no longer exists)"
        return (f'<a href="tasks/{r["scope_id"]}.html" class="pill" '
                f'style="background:var(--blue-soft); color:var(--blue); border:1px solid oklch(72% 0.12 250 / 0.35);">'
                f'TASK-{r["scope_id"]:03d} — {e(title)}</a>')
    if r["scope_type"] == "project":
        name = r["scope_project_name"] or "(unknown project)"
        return f'Project — {e(name)}'
    return '<span class="pill" style="background:var(--gray-soft); color:var(--text2);">Company-wide</span>'


def _related_decisions_html(conn: sqlite3.Connection, risk_id: int) -> str:
    """Compact, wrapped chip row (Design review item 4) — not a full
    vertical list. Each chip: '#{id} — {title}' (title-truncated with
    text-overflow:ellipsis, full title in a title="" tooltip), linking to
    decisions.html#decision-{id}."""
    decisions = ds.related_decisions_for_risk(conn, risk_id)
    if not decisions:
        return ""
    chips = "".join(
        f'<a href="decisions.html#decision-{d["id"]}" class="mono" title="{e(d["title"])}" '
        f'style="display:inline-block; max-width:230px; white-space:nowrap; overflow:hidden; '
        f'text-overflow:ellipsis; font-size:10.5px; padding:3px 9px; border-radius:100px; '
        f'background:var(--panel); border:1px solid var(--border2); color:var(--text2);">'
        f'#{d["id"]} — {e(d["title"])}</a>'
        for d in decisions
    )
    return (f'<div style="margin-top:10px;"><div class="label" style="margin-bottom:6px;">'
            f'Related decisions ({len(decisions)})</div>'
            f'<div style="display:flex; flex-wrap:wrap; gap:6px;">{chips}</div></div>')


def _risk_card_html(conn: sqlite3.Connection, r: dict) -> str:
    sev_color = _SEV_COLOR.get(r["severity"], "var(--text2)")
    status_color = _STATUS_COLOR.get(r["status"], "var(--text2)")
    owner = ds.display_name(r["owner_agent"]) if r["owner_agent"] else "unassigned"
    raised_by = ds.display_name(r["raised_by_agent"]) if r["raised_by_agent"] else "—"
    mitigation_html = (
        f'<div style="margin-top:10px;"><div class="label" style="margin-bottom:5px;">Mitigation</div>'
        f'<div style="font-size:11.5px; color:var(--text2); line-height:1.6; white-space:pre-wrap; max-width:760px;">'
        f'{e(r["mitigation"])}</div></div>'
        if r["mitigation"] else
        '<div style="margin-top:10px; font-size:11.5px; color:var(--text3);">No mitigation recorded yet.</div>'
    )
    resolved_html = (
        f'<div style="margin-top:8px; font-size:11px; color:var(--text3);">Resolved '
        f'<span class="mono">{e(r["resolved_at"])}</span></div>'
        if r["status"] == "resolved" and r["resolved_at"] else ""
    )
    return f'''
    <div class="card" id="risk-{r["id"]}" style="margin-bottom:10px;">
      <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap;">
        <div style="font-size:13px; font-weight:600;">Risk #{r["id"]} — {e(r["title"])}</div>
        <div style="display:flex; gap:6px; flex-shrink:0;">
          <span class="pill" style="background:{sev_color}22; color:{sev_color};">{e(r["severity"])}</span>
          <span class="pill" style="background:{status_color}22; color:{status_color};">{e(r["status"])}</span>
        </div>
      </div>
      <div style="font-size:11.5px; color:var(--text2); margin-top:6px; line-height:1.5;">{e(r["description"]) if r["description"] else "—"}</div>
      <div style="display:flex; gap:16px; flex-wrap:wrap; margin-top:8px; font-size:10.5px; color:var(--text3);">
        <div>Scope: {_scope_html(r)}</div>
        <div>Owner: <span class="mono" style="color:var(--text2);">{e(owner)}</span></div>
        <div>Raised by: <span class="mono" style="color:var(--text2);">{e(raised_by)}</span></div>
        <div class="mono">{e(r["created_at"])}</div>
      </div>
      {mitigation_html}
      {_related_decisions_html(conn, r["id"])}
      {resolved_html}
    </div>'''


def _needs_attention_html(open_high_medium: list[dict]) -> str:
    """Design review recommendation 1 — a page-level strip surfacing open
    + medium/high-severity risks as quick-jump links, reusing the
    existing "Needs You" alert-strip pattern (Founder-approved in phase
    0's own mockup). An index into the sections, not a replacement for
    them — every risk still appears in its own status section too."""
    if not open_high_medium:
        return ""
    items = "".join(
        f'<a href="#risk-{r["id"]}" style="display:flex; align-items:center; gap:10px; padding:8px 10px; '
        f'border-radius:8px; background:var(--panel2); margin-top:6px;">'
        f'<span class="pill" style="background:{_SEV_COLOR.get(r["severity"], "var(--text2)")}22; '
        f'color:{_SEV_COLOR.get(r["severity"], "var(--text2)")}; flex-shrink:0;">{e(r["severity"])}</span>'
        f'<span style="flex:1; font-size:12px;"><b>Risk #{r["id"]}</b> — {e(r["title"])}</span>'
        f'<span style="font-size:10.5px; color:var(--accent); font-weight:600; flex-shrink:0;">Jump to card &rarr;</span></a>'
        for r in open_high_medium
    )
    return f'''
<div style="display:flex; align-items:flex-start; gap:12px; padding:11px 14px; border-radius:11px;
     background:var(--accent-soft); border:1px solid oklch(78% 0.14 75 / 0.35); margin-bottom:16px;">
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" style="flex-shrink:0; margin-top:2px;">
    <path d="M12 9v4M12 17h.01M10.3 3.9 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"
     stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
  <div style="flex:1;">
    <div class="label" style="color:var(--accent);">Needs attention — {len(open_high_medium)} open, medium/high severity</div>
    {items}
  </div>
</div>'''


def render_risks(conn: sqlite3.Connection) -> str:
    rows = ds.risk_register_rows(conn)
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No risks recorded yet.</div>'

    groups: dict[str, list[dict]] = {"open": [], "mitigated": [], "resolved": []}
    for r in rows:
        groups.setdefault(r["status"], []).append(r)

    open_n, mitigated_n, resolved_n = len(groups["open"]), len(groups["mitigated"]), len(groups["resolved"])
    high_n = sum(1 for r in groups["open"] if r["severity"] == "high")

    open_high_medium = [r for r in groups["open"] if r["severity"] in ("high", "medium")]

    pills = "".join(
        f'<a href="#{anchor}" class="pill" style="background:var(--panel2); color:{color}; border:1px solid var(--border2);">'
        f'{label} ({len(groups.get(anchor, []))})</a>'
        for anchor, label, color in _SECTIONS
    )

    summary = f"{open_n} open ({high_n} high-severity) · {mitigated_n} mitigated · {resolved_n} resolved"

    sections_html = []
    for anchor, label, color in _SECTIONS:
        section_rows = groups.get(anchor, [])
        cards = "".join(_risk_card_html(conn, r) for r in section_rows)
        if not cards:
            cards = f'<div style="font-size:12px; color:var(--text2);">None.</div>'
        sections_html.append(f'''
<div id="{anchor}" style="margin-bottom:22px;">
  <div class="label" style="margin-bottom:8px; color:{color};">{label} ({len(section_rows)})</div>
  {cards}
</div>''')

    return f'''
<div class="sub" style="margin-top:-14px; max-width:820px;">{e(summary)}</div>
{_needs_attention_html(open_high_medium)}
<div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:18px;">{pills}</div>
<div class="panel" style="margin-bottom:18px; border-color:var(--border2);">
  <div style="display:flex; gap:10px; align-items:flex-start;">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" style="flex-shrink:0; margin-top:1px;">
      <circle cx="12" cy="12" r="9" stroke="var(--text3)" stroke-width="1.6"/>
      <path d="M12 8v5M12 16h.01" stroke="var(--text3)" stroke-width="1.6" stroke-linecap="round"/>
    </svg>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.55;">{e(_HISTORY_DISCLOSURE)}</div>
  </div>
</div>
{"".join(sections_html)}'''


def build_html(token: str | None = None) -> str:
    conn = connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f'''
<h1>Risks <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only</span></h1>
{render_risks(conn)}'''
    return page("Risks", "risks.html", body, token=token,
                generated_note=f"Generated {now} from the live operational database. Not hand-edited; re-run this script to refresh.")


def main() -> None:
    write_output(OUT_PATH, build_html())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
