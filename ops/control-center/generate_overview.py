#!/usr/bin/env python3
"""ops/control-center/generate_overview.py — Phase 2, Milestone 1.

Generates a static, read-only Overview page from the real operational
database. Zero third-party dependencies. Visual tokens are copied
verbatim from the Founder-approved dark mockup
(ops/mockups/control-center-phase-0/Main.dc.html, Style A) — this is
that same visual system, not a reinterpretation of it.

Every number and status on this page is computed by ops/db/derived_state.py
— the same module ops/db/report.py uses — never hand-written or invented.
See ops/ARCHITECTURE.md, "Derived UI state must be deterministic", and
ops/reviews/red-team-phase2-architecture.md for the conditions this file
was built to satisfy (universal HTML-escaping; no element styled as
clickable unless it actually does something — this page has no write
actions yet, so nothing here is button-shaped).

Read-only: opens the database read-only and never calls any opsdb.py
write path. Respects OPSDB_PATH the same way report.py does (see
ops/db/README.md) — testing this script must use a scratch database,
never operations.sqlite3.

Usage:
    python3 ops/control-center/generate_overview.py
"""
from __future__ import annotations

import html
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

_DB_DIR = Path(__file__).resolve().parent.parent / "db"
sys.path.insert(0, str(_DB_DIR))
from derived_state import agent_status_rows, company_health, scope_label, task_progress_fraction  # noqa: E402

_using_scratch_db = bool(os.environ.get("OPSDB_PATH"))
DB_PATH = Path(os.environ["OPSDB_PATH"]) if _using_scratch_db else _DB_DIR / "operations.sqlite3"

if os.environ.get("OPSDB_OVERVIEW_PATH"):
    OUT_PATH = Path(os.environ["OPSDB_OVERVIEW_PATH"])
elif _using_scratch_db:
    OUT_PATH = DB_PATH.with_name(DB_PATH.stem + ".overview.html")
else:
    OUT_PATH = Path(__file__).resolve().parent / "overview.html"


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SystemExit(f"error: {DB_PATH} does not exist — run `opsdb.py init` first")
    # Read-only connection (mode=ro) — this generator has no write path at all.
    # The path MUST be percent-encoded: an unescaped '#' or '?' in a file: URI
    # is a fragment/query separator, not a literal character — without quote(),
    # a path containing one silently opens the wrong (or no) database instead
    # of raising an error, which is worse than a crash (found in Code Review —
    # confirmed with a real path containing '#' before this fix).
    conn = sqlite3.connect(f"file:{quote(str(DB_PATH))}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def e(value) -> str:
    """Escape every piece of database text before it reaches HTML — required
    by ops/reviews/red-team-phase2-architecture.md, item 2. Applies to
    Founder-authored content too, not only untrusted input."""
    return html.escape(str(value) if value is not None else "")


HEALTH_COLOR = {"Good": "var(--green)", "Fair": "var(--accent)", "Poor": "var(--red)"}
STATUS_COLOR = {
    "active": "var(--accent)", "waiting": "var(--blue)",
    "blocked": "var(--red)", None: "var(--gray)",
}


def render_active_now(conn: sqlite3.Connection) -> str:
    rows = [r for r in agent_status_rows(conn) if r["status"] is not None]
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No agent currently has an open run.</div>'
    items = []
    for r in rows:
        color = STATUS_COLOR.get(r["status"], "var(--gray)")
        items.append(f'''
        <div style="display:flex; align-items:center; gap:11px; padding:9px 11px; border-radius:10px; background:var(--panel2);">
          <div style="width:8px; height:8px; border-radius:50%; background:{color}; flex-shrink:0;"></div>
          <div style="flex:1; min-width:0;">
            <div style="font-size:12.5px; font-weight:600;">{e(r["name"])}</div>
            <div style="font-size:11.5px; color:var(--text2);">{e(r["current_activity"] or "")}</div>
          </div>
          <div style="font-size:10px; color:var(--text3); flex-shrink:0;">{e(r["status"])} · {e(scope_label(r["scope_type"], r["scope_id"]))}</div>
        </div>''')
    return "".join(items)


def render_pipeline(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, title, status, current_owner FROM tasks "
        "WHERE status != 'DONE' ORDER BY id"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No open tasks.</div>'
    items = []
    for t in rows:
        frac = task_progress_fraction(conn, t["id"])
        if frac is None:
            pct, label = 0, "not broken into steps"
        else:
            done, total = frac
            pct = round(100 * done / total)
            label = f"{pct}%"
        items.append(f'''
        <div style="display:flex; align-items:center; gap:10px;">
          <div style="width:170px; font-size:12px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">TASK-{t["id"]:03d} — {e(t["title"])}</div>
          <div style="flex:1; height:6px; border-radius:3px; background:var(--border2); overflow:hidden;"><div style="width:{pct}%; height:100%; background:var(--accent);"></div></div>
          <div style="width:70px; font-size:11px; color:var(--text2); text-align:right;">{e(label)}</div>
          <div style="width:110px; font-size:11px; color:var(--text3);">{e(t["status"])}</div>
        </div>''')
    return "".join(items)


def render_activity(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT a.name AS agent, x.summary, x.created_at FROM agent_activity x "
        "JOIN agents a ON a.id = x.agent_id ORDER BY x.id DESC LIMIT 8"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">No activity recorded yet.</div>'
    items = []
    for r in rows:
        items.append(f'''
        <div style="display:flex; gap:8px;">
          <div style="font-size:11.5px; color:var(--text2);"><b style="color:var(--text);">{e(r["agent"])}</b> — {e(r["summary"])}</div>
        </div>''')
    return "".join(items)


def render_inbox(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, request, requested_by_agent, decision FROM approvals "
        "WHERE decision = 'pending' ORDER BY id"
    ).fetchall()
    if not rows:
        return '<div style="font-size:12px; color:var(--text2);">Nothing pending.</div>'
    # No Approve/Reject controls here on purpose — this milestone is read-only
    # and a button that does not call opsdb.py must not be rendered as one
    # (ops/reviews/red-team-phase2-architecture.md, item 3).
    items = []
    for r in rows:
        items.append(f'''
        <div style="border-radius:9px; border:1px solid var(--border2); background:var(--panel2); padding:10px 12px;">
          <div style="font-size:12px; font-weight:600; margin-bottom:3px;">{e(r["request"])}</div>
          <div style="font-size:11px; color:var(--text2);">Requested by {e(r["requested_by_agent"])} · not yet decided</div>
        </div>''')
    return "".join(items)


def build_html() -> str:
    conn = connect()
    health_label, health_detail = company_health(conn)
    health_color = HEALTH_COLOR.get(health_label, "var(--text)")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Overview — Command Center</title>
<style>
:root{{
  --bg:#0b0d10; --panel:#14171c; --panel2:#1a1e24; --border:#242830; --border2:#323844;
  --text:#eae8e3; --text2:#9aa0a8; --text3:#666c74;
  --accent: oklch(78% 0.14 75); --accent-soft: oklch(78% 0.14 75 / 0.13);
  --green: oklch(72% 0.15 150); --green-soft: oklch(72% 0.15 150 / 0.14);
  --red: oklch(66% 0.17 25); --red-soft: oklch(66% 0.17 25 / 0.14);
  --blue: oklch(72% 0.12 250); --blue-soft: oklch(72% 0.12 250 / 0.14);
  --violet: oklch(70% 0.12 300); --violet-soft: oklch(70% 0.12 300 / 0.14);
  --gray: oklch(58% 0.015 250); --gray-soft: oklch(58% 0.015 250 / 0.12);
  --mono: ui-monospace, "SF Mono", Menlo, monospace;
  --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
  --disp: system-ui, sans-serif;
}}
body{{ margin:0; background:var(--bg); color:var(--text); font-family:var(--sans); padding:26px; }}
.label{{ font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; }}
.panel{{ border-radius:14px; border:1px solid var(--border); background:var(--panel); padding:16px; }}
h1{{ font-family:var(--disp); font-size:19px; font-weight:600; margin:0 0 4px; }}
.sub{{ font-size:11.5px; color:var(--text3); margin:0 0 20px; }}
.grid{{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
.stack{{ display:flex; flex-direction:column; gap:10px; }}
</style>
</head>
<body>
<h1>Overview <span style="font-size:11px; color:var(--text3); font-weight:400;">— read-only, Phase 2 Milestone 1</span></h1>
<div class="sub">Generated {e(now)} from the live operational database. Not hand-edited; re-run generate_overview.py to refresh.</div>

<div class="panel" style="margin-bottom:14px;">
  <div class="label" style="margin-bottom:6px;">Company Health</div>
  <div style="font-size:20px; font-weight:600; color:{health_color};">{e(health_label)}</div>
  <div style="font-size:11.5px; color:var(--text2); margin-top:2px;">{e(health_detail)}</div>
</div>

<div class="grid">
  <div class="panel">
    <div class="label" style="margin-bottom:10px;">Active Now</div>
    <div class="stack">{render_active_now(conn)}</div>
  </div>
  <div class="panel">
    <div class="label" style="margin-bottom:10px;">Founder Inbox</div>
    <div class="stack">{render_inbox(conn)}</div>
  </div>
  <div class="panel" style="grid-column:1 / -1;">
    <div class="label" style="margin-bottom:10px;">Pipeline Snapshot</div>
    <div class="stack">{render_pipeline(conn)}</div>
  </div>
  <div class="panel" style="grid-column:1 / -1;">
    <div class="label" style="margin-bottom:10px;">Just Happened</div>
    <div class="stack">{render_activity(conn)}</div>
  </div>
</div>
</body>
</html>
"""


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(build_html())
    OUT_PATH.chmod(0o600)  # same reasoning as operations.sqlite3 (see ops/db/opsdb.py cmd_init) —
                           # this file carries the same class of internal company data
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
