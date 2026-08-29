"""ops/control-center/layout.py — shared CSS tokens, nav shell, and the
HTML-escape helper for every Control Center screen. Same DRY reasoning as
ops/db/derived_state.py: one copy of the chrome, not six.

Visual tokens are copied verbatim from the Founder-approved dark mockup
(ops/mockups/control-center-phase-0/Main.dc.html, Style A / DEC-002) —
this is that same visual system, not a reinterpretation.
"""
from __future__ import annotations

import html

CSS_TOKENS = """
:root{
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
}
body{ margin:0; background:var(--bg); color:var(--text); font-family:var(--sans); }
.mono{ font-family:var(--mono); letter-spacing:0.01em; }
.label{ font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; }
.pill{ display:inline-flex; align-items:center; gap:5px; padding:2px 8px; border-radius:100px; font-size:10px; font-weight:600; }
.panel{ border-radius:14px; border:1px solid var(--border); background:var(--panel); padding:16px; }
.card{ border-radius:10px; border:1px solid var(--border2); background:var(--panel2); padding:12px; }
a{ color:inherit; text-decoration:none; }
h1{ font-family:var(--disp); font-size:19px; font-weight:600; margin:0 0 4px; }
.sub{ font-size:11.5px; color:var(--text3); margin:0 0 20px; }
"""

# (href, label) for every top-level screen — same five links everywhere.
NAV_LINKS = [
    ("overview.html", "Overview"),
    ("pipeline.html", "Pipeline"),
    ("agents.html", "Agents"),
    ("decisions.html", "Decisions"),
    ("meetings.html", "Meetings"),
]


def e(value) -> str:
    """Escape every piece of database text before it reaches HTML — the
    Milestone-1 rule (ops/reviews/red-team-phase2-architecture.md, item 2)
    applies unchanged to every screen, Founder-authored content included."""
    return html.escape(str(value) if value is not None else "")


def nav_html(active: str, depth: int = 0) -> str:
    """active = the filename (e.g. 'pipeline.html') of the current page.
    depth = 0 for top-level pages, 1 for pages one directory down
    (ops/control-center/agents/<name>.html) so relative links still work."""
    prefix = "../" * depth
    items = []
    for href, label in NAV_LINKS:
        is_active = href == active
        style = (
            "padding:6px 13px; border-radius:7px; background:var(--panel2); font-size:12.5px; font-weight:600;"
            if is_active else
            "padding:6px 13px; border-radius:7px; color:var(--text2); font-size:12.5px;"
        )
        items.append(f'<a href="{prefix}{href}" style="{style}">{e(label)}</a>')
    return f'''
    <div style="display:flex; align-items:center; justify-content:space-between; padding:13px 26px; border-bottom:1px solid var(--border);">
      <div style="display:flex; align-items:center; gap:26px;">
        <div style="display:flex; align-items:center; gap:9px;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z" stroke="var(--accent)" stroke-width="1.6"/><circle cx="12" cy="12" r="3" fill="var(--accent)"/></svg>
          <div style="font-family:var(--disp); font-weight:600; font-size:15px;">Command</div>
        </div>
        <div style="display:flex; gap:2px;">{"".join(items)}</div>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <div style="width:28px; height:28px; border-radius:50%; background:var(--violet-soft); border:1.5px solid var(--violet); display:flex; align-items:center; justify-content:center;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="4" stroke="var(--violet)" stroke-width="1.8"/><path d="M4 20c0-4.4 3.6-7 8-7s8 2.6 8 7" stroke="var(--violet)" stroke-width="1.8" stroke-linecap="round"/></svg>
        </div>
        <div style="line-height:1.15;">
          <div style="font-size:11.5px; font-weight:600;">Alex</div>
          <div style="font-size:9px; color:var(--violet); font-weight:700; letter-spacing:0.04em;">FOUNDER · HUMAN</div>
        </div>
      </div>
    </div>'''


def page(title: str, active_nav: str, body_html: str, depth: int = 0, generated_note: str = "") -> str:
    """Full HTML document: head + nav + body. Every screen calls this so
    the chrome (tokens, nav, escaping convention) never drifts between
    screens — see the module docstring."""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{e(title)} — Command Center</title>
<style>{CSS_TOKENS}</style>
</head>
<body>
{nav_html(active_nav, depth)}
<div style="padding:26px;">
{f'<div class="sub">{e(generated_note)}</div>' if generated_note else ''}
{body_html}
</div>
</body>
</html>
"""
