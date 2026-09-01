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
a.accentlink{ color:var(--accent); }
a.accentlink:hover{ color:oklch(84% 0.14 75); }
h1{ font-family:var(--disp); font-size:19px; font-weight:600; margin:0 0 4px; }
.sub{ font-size:11.5px; color:var(--text3); margin:0 0 20px; }
"""

# (href, label) for every top-level screen — same six links everywhere.
NAV_LINKS = [
    ("overview.html", "Overview"),
    ("active-work.html", "Active Work"),  # Milestone A (TASK-019) — placed right after
                                           # Overview: the natural next click from the
                                           # broad company-health snapshot to "what needs
                                           # me, per task." /tasks/<id>.html is NOT a
                                           # nav-bar item, matching /agents/<name>.html and
                                           # /meetings/<id>.html precedent.
    ("pipeline.html", "Pipeline"),
    ("agents.html", "Agents"),
    ("decisions.html", "Decisions"),
    ("risks.html", "Risks"),  # Milestone C (TASK-021) — placed right after Decisions: both
                              # are company-governance, read-only registers of durable
                              # record-keeping, a natural adjacent pair.
    ("meetings.html", "Meetings"),
    ("inbox.html", "Inbox"),
    ("reviews.html", "Reviews"),
    ("releases.html", "Releases"),
    ("automation.html", "Automation"),
    ("costs.html", "Costs"),  # Milestone B (TASK-020) — placed after Automation: spend
                              # visibility is a company-health concern adjacent to, but not
                              # part of, the automation kill-switch page it sits next to.
]


def e(value) -> str:
    """Escape every piece of database text before it reaches HTML — the
    Milestone-1 rule (ops/reviews/red-team-phase2-architecture.md, item 2)
    applies unchanged to every screen, Founder-authored content included."""
    return html.escape(str(value) if value is not None else "")


def _logout_form_html(token: str) -> str:
    """Milestone 2B4 (TASK-013): the "Log out" affordance in the Founder
    badge area — a tiny inline form posting to /api/logout with the same
    CSRF `token` hidden field every other write route already carries
    (architecture doc §4/§12). Rendered only when a token is supplied
    (i.e. only by the live server, never by the static
    `generate_*.py main()` snapshots, which have no live SESSION_TOKEN or
    session to log out of — see the module docstring's static-snapshot
    note)."""
    return f'''<form method="post" action="/api/logout" style="margin:0;">
          <input type="hidden" name="token" value="{e(token)}">
          <button type="submit" style="background:none; border:none; color:var(--text3); font-size:10.5px; cursor:pointer; padding:2px 0; font-family:var(--sans);">Log out</button>
        </form>'''


def nav_html(active: str, depth: int = 0, token: str | None = None) -> str:
    """active = the filename (e.g. 'pipeline.html') of the current page.
    depth = 0 for top-level pages, 1 for pages one directory down
    (ops/control-center/agents/<name>.html) so relative links still work.
    token = the current SESSION_TOKEN, passed only by server.py's live
    routes (Milestone 2B4) — when present, renders a "Log out" affordance
    next to the Founder badge; omitted entirely for the static
    generator snapshots, which have no live session to log out of."""
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
    logout_html = _logout_form_html(token) if token else ""
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
          <div style="font-size:11.5px; font-weight:600;">Founder</div>
          <div style="font-size:9px; color:var(--violet); font-weight:700; letter-spacing:0.04em;">HUMAN</div>
          {logout_html}
        </div>
      </div>
    </div>'''


def page(title: str, active_nav: str, body_html: str, depth: int = 0, generated_note: str = "", token: str | None = None) -> str:
    """Full HTML document: head + nav + body. Every screen calls this so
    the chrome (tokens, nav, escaping convention) never drifts between
    screens — see the module docstring. `token`: see nav_html()."""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{e(title)} — Command Center</title>
<style>{CSS_TOKENS}</style>
</head>
<body>
{nav_html(active_nav, depth, token=token)}
<div style="padding:26px;">
{f'<div class="sub">{e(generated_note)}</div>' if generated_note else ''}
{body_html}
</div>
</body>
</html>
"""


def _bare_page(title: str, body_html: str) -> str:
    """Milestone 2B4: shared skeleton for the unauthenticated pages below
    (login, setup-required) — NO nav_html() at all, deliberately: these
    pages must carry no link to any gated content (architecture doc §7 —
    the whole app requires a session except /login and the fixed
    setup-required page)."""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{e(title)} — Command Center</title>
<style>{CSS_TOKENS}</style>
</head>
<body>
<div style="max-width:360px; margin:14vh auto 0; padding:0 20px;">
  <div style="display:flex; align-items:center; gap:9px; margin-bottom:22px;">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z" stroke="var(--accent)" stroke-width="1.6"/><circle cx="12" cy="12" r="3" fill="var(--accent)"/></svg>
    <div style="font-family:var(--disp); font-weight:600; font-size:17px;">Command</div>
  </div>
{body_html}
</div>
</body>
</html>
"""


def login_page(token: str, error: str | None = None) -> str:
    """Milestone 2B4 (TASK-013): the /login form. Embeds the current
    SESSION_TOKEN as a hidden CSRF field, exactly like every other write
    form this server renders (Security's Milestone 2B4 threat-model
    review, condition C2) — /api/login checks it via
    secrets.compare_digest() before ever touching the passphrase, same as
    every other route. No nav — see _bare_page()."""
    error_html = (
        f'<div class="panel" style="border-color:var(--red); margin-bottom:14px;">'
        f'<div style="font-size:12.5px; color:var(--text2);">{e(error)}</div></div>'
        if error else ""
    )
    body = f'''{error_html}
  <form method="post" action="/api/login" class="panel">
    <input type="hidden" name="token" value="{e(token)}">
    <div class="label" style="margin-bottom:8px;">Founder Passphrase</div>
    <input type="password" name="passphrase" autofocus autocomplete="current-password"
           style="width:100%; box-sizing:border-box; padding:9px 10px; border-radius:8px; border:1px solid var(--border2); background:var(--panel2); color:var(--text); font-size:13px; margin-bottom:12px;">
    <button type="submit" style="width:100%; padding:9px 10px; border-radius:8px; border:none; background:var(--accent); color:var(--bg); font-weight:600; font-size:13px; cursor:pointer;">Sign in</button>
  </form>
  <div class="sub" style="margin-top:14px;">This session unlocks the Control Center for this browser only — up to 12 hours, or 30 minutes idle.</div>'''
    return _bare_page("Sign in", body)


def setup_required_page() -> str:
    """Milestone 2B4 (TASK-013): the fixed 503 page every route (GET and
    POST alike, including /login itself) returns while no Founder
    credential file exists yet — architecture doc §3. Fixed message, no
    dynamic content, so there's nothing here for a request to influence."""
    body = '''<div class="panel" style="border-color:var(--red);">
    <div class="label" style="margin-bottom:8px; color:var(--red);">Founder setup required</div>
    <div style="font-size:12.5px; color:var(--text2); line-height:1.5;">
      No Founder credential exists yet. From a terminal on this machine, run:
      <div class="mono" style="margin-top:8px; padding:8px 10px; border-radius:6px; background:var(--panel2); font-size:12px;">python3 ops/control-center/founder_auth.py setup</div>
    </div>
  </div>'''
    return _bare_page("Setup required", body)
