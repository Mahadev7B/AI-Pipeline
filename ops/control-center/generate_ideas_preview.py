#!/usr/bin/env python3
"""ops/control-center/generate_ideas_preview.py — TASK-024 Founder-review UI shell.

**This is a preview shell, not the feature.** It exists for one reason: the
Founder asked to click through Design's approved ten-stage "idea deciphering"
journey as real pages in the real Control Center rather than as screenshots
("I don't want screenshots, I need UI so I can see clearly"). DEC-015 /
Part 3 §11's Founder approval gate is still in force — nothing downstream of
TASK-024 proceeds until the Founder approves what they walk here.

Spec: the fourteen artboards at ops/mockups/task024/*.dc.html (Main, the ten
stages, Distinctions, FullDepth, HonestStates) and
ops/reviews/design-review-task024.md Revision 2. Every panel, kicker,
attribution line and sentence below is translated from those artboards — not
rewritten. The sample idea is the Founder's own raw text for TASK-026,
verbatim, and the Reconsider feedback is their real later correction.

WHAT THIS MODULE DOES NOT DO, deliberately and checkably:

- **No database access at all.** It does not import dbutil.connect(); there
  is no read path and therefore no write path. Every figure quoted on these
  pages (0 of 13 agent_runs with a cost, task_steps on 1 of 24 tasks,
  project_id NULL on 20 of 24, one row in projects, `design` absent from the
  meeting participant allowlist) is quoted from Design's artboards, which
  recorded them when the canvas was built.
- **No agent invocation, no model call, no cost.** Nothing here imports
  agent_runtime or opsdb.
- **No write route.** Every control on every page is either a plain GET link
  to another shell page or a pure-CSS <details> disclosure. There is not one
  form, not one POST, not one byte of JavaScript.
- **No schema change, no new table, no new column.**

Interaction model. The artboards carry per-screen client state (the compose /
saved / armed states of stage 1, the arm-then-confirm of stage 9, the tabs of
stage 6, the version ladder of stage 8). Here that state lives in the URL
query string — `stage-9.html?step=confirm` — so the whole journey is plain
GET navigation with no script and no server state. Expanders ("+ Show the
working · sections 5 and 6") are <details>/<summary>, so they open with no
script either. An unrecognised query value silently falls back to the
default state; a query string can never produce an error page.

Routes are registered in server.py behind the same _authenticated_session()
gate as every other page — no new auth code, no new authorization boundary.
main() writes the same twelve pages as static snapshots under
ops/control-center/ideas-preview/ (the generate_task.py / generate_agents.py
subdirectory precedent) so they can also be opened as files; those snapshots
render each page's default state only, since a file:// URL has no server to
read the query string.

Usage:
    python3 ops/control-center/generate_ideas_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dbutil import out_path, write_output  # noqa: E402
from layout import e, page  # noqa: E402

# Same out_path()/subdirectory resolution generate_task.py and
# generate_agents.py use: a sibling name purely to resolve the right
# directory (and to honour the OPSDB_PATH scratch-DB testing convention),
# then the real pages one level down.
OUT_PATH = out_path("ideas-preview.html", "OPSDB_IDEAS_PREVIEW_PATH")
IDEAS_SUBDIR = OUT_PATH.parent / "ideas-preview"

# The one nav entry (layout.NAV_LINKS) every page in this shell marks active,
# exactly as generate_task.py's detail pages all mark "active-work.html".
NAV_HREF = "ideas-preview/stage-1.html"

# The persistent, unmissable label the brief requires on every shell page.
PREVIEW_NOTE = "Preview — nothing on these pages runs an agent or spends money."

# ---------------------------------------------------------------------------
# Content constants — the Founder's own words, quoted byte-for-byte.
# ---------------------------------------------------------------------------

# TASK-026's raw idea, exactly as the Founder typed it. Rendered through e()
# everywhere it appears, like every other string on every other screen.
RAW_IDEA = ("the current UI so much verbose, it should be as simple as a dashboard, "
            "I'M THINKING like an ellipse where we can track flow")

# The Founder's real later correction, used verbatim as the Reconsider round's
# feedback (design review Revision 2, §0).
FEEDBACK = ("almost there, UI i'm talking about is UI of my factory to track the app progress, "
            "once done the app( which is a child of my factory will hve another UI which is "
            "unrelated to ours) you got it?")

# (slug, number, rail name, stage kicker, page title)
STAGES = [
    ("stage-1", 1, "Raw idea", "Raw idea", "Bring an idea to the company"),
    ("stage-2", 2, "Interpreting", "Factory interpreting", "The company is considering your idea"),
    ("stage-3", 3, "Understanding", "Factory understanding", "What we think you asked for"),
    ("stage-4", 4, "Evaluation", "Idea evaluation", "What we think of the idea, and what we recommend"),
    ("stage-5", 5, "Founder review", "Founder review", "Your call"),
    ("stage-6", 6, "Correction", "Correction / reconsideration", "Two ways to put it right"),
    ("stage-7", 7, "Approval", "Founder approval", "Approve this understanding"),
    ("stage-8", 8, "Approved brief", "Approved brief", "What you approved"),
    ("stage-9", 9, "Start work", "Start work", "The expensive decision, on its own screen"),
    ("stage-10", 10, "Executing", "Factory begins execution", "It is running"),
]

SHEETS = [
    ("distinctions", "The five voices"),
    ("full-depth", "The Full-depth layer"),
]

PAGE_SLUGS = [s[0] for s in STAGES] + [s[0] for s in SHEETS]

# ---------------------------------------------------------------------------
# Page-local colour vars.
#
# layout.CSS_TOKENS is NOT forked or extended — these are the handful of
# shades Design used on the TASK-024 artboards that the shared token set has
# no name for (a recessed ground, an inset ground, a hairline, a dimmest
# text, a dashed-placeholder border, the two prose weights, and the two
# on-filled-button inks). They are scoped to .idj on this shell's pages only,
# copied from the artboards, and deliberately not promoted into the shared
# token set by a Founder-review shell.
# ---------------------------------------------------------------------------

SHELL_CSS = """
.idj{
  --recess:#101317; --inset:#0f1216; --hair:#1e2229; --dim:#4e545c;
  --dash:#3d434d; --prose:#c8ccd2; --prose2:#d8dce2;
  --ink-accent:#1a1206; --ink-green:#06180d;
}
.idj a{ color:inherit; text-decoration:none; }
.idj .dcx{ margin-top:11px; }
.idj .dcx > summary{ list-style:none; cursor:pointer; font-size:11px; color:var(--accent); }
.idj .dcx > summary::-webkit-details-marker{ display:none; }
.idj .dcx > summary:hover{ color:oklch(84% 0.14 75); }
.idj .dcx .dcx-hide{ display:none; }
.idj .dcx[open] .dcx-show{ display:none; }
.idj .dcx[open] .dcx-hide{ display:inline; }
.idj .inset{ margin-top:12px; border-radius:10px; background:var(--inset); border:1px solid var(--hair);
             border-left:2px solid var(--border2); padding:14px 16px; }
.idj .inset-k{ font-size:9.5px; font-weight:700; letter-spacing:0.06em; color:var(--dim);
               text-transform:uppercase; margin-bottom:10px; }
.idj .ph{ font-family:var(--mono); font-size:10.5px; color:var(--dim); border:1px dashed var(--dash);
          border-radius:5px; padding:2px 7px; }
.idj .qrow{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
@media (max-width:900px){ .idj .qrow{ grid-template-columns:minmax(0,1fr); } }
"""


def _expander(label: str, inner_html: str, accent_rule: bool = False) -> str:
    """One concise-layer row's "+ Show the working · sections N and M"
    control, opening the visually recessed inset the design review §2
    specifies. Pure <details>/<summary> — no script. `label` is the part
    after "Show the working · " and is also what "Hide ..." names, so a
    control never says only "more" (design review §2, rule 2)."""
    rule = "border-left:2px solid oklch(78% 0.14 75 / 0.45);" if accent_rule else ""
    return f'''<details class="dcx">
  <summary><span class="dcx-show">+&nbsp; Show the working &middot; {e(label)}</span><span class="dcx-hide">&minus;&nbsp; Hide {e(label)}</span></summary>
  <div class="inset" style="{rule}">{inner_html}</div>
</details>'''


# ---------------------------------------------------------------------------
# Shared chrome: the preview strip, the ten-stage rail, the five-voice legend,
# the raw-idea panel in its three shapes, and the footer.
# ---------------------------------------------------------------------------


def _preview_strip() -> str:
    return f'''
<div style="border-radius:10px; border:1px dashed oklch(78% 0.14 75 / 0.55); background:oklch(78% 0.14 75 / 0.06); padding:9px 14px; margin-bottom:16px; display:flex; align-items:center; gap:11px; flex-wrap:wrap;">
  <span style="padding:2px 8px; border-radius:100px; background:var(--accent-soft); color:var(--accent); font-size:9.5px; font-weight:700; letter-spacing:0.06em;">PREVIEW</span>
  <div style="font-size:11.5px; color:var(--text2); line-height:1.55;">{e(PREVIEW_NOTE)}</div>
  <div style="font-size:10.5px; color:var(--dim); margin-left:auto;">A drawn shell of the TASK-024 journey for Founder review &mdash; no backend behind any control.</div>
</div>'''


def _legend() -> str:
    """The five-voice legend, in the page chrome on every screen of the
    journey — design review §1: "The Founder learns the grammar once." """
    voices = [
        ("var(--gray)", "you said"),
        ("var(--blue)", "we think you mean"),
        ("var(--violet)", "what we think of it"),
        ("var(--accent)", "what we recommend"),
        ("var(--green)", "you approved"),
    ]
    items = "".join(
        f'<div style="display:flex; align-items:center; gap:6px;">'
        f'<div style="width:3px; height:12px; background:{c}; border-radius:2px;"></div>'
        f'<div style="font-size:10.5px; color:var(--text2);">{e(t)}</div></div>'
        for c, t in voices)
    sheet_links = "".join(
        f'<a href="{e(slug)}.html" style="font-size:10.5px; color:var(--accent);">{e(title)} &rarr;</a>'
        for slug, title in SHEETS)
    return f'''
<div style="display:flex; align-items:center; gap:16px; flex-wrap:wrap; padding:11px 0 2px;">
  <div style="font-size:9.5px; font-weight:700; letter-spacing:0.06em; color:var(--dim); text-transform:uppercase;">Who is speaking</div>
  {items}
  <div style="display:flex; gap:14px; margin-left:auto;">{sheet_links}</div>
</div>'''


def _rail(active_slug: str) -> str:
    """The persistent ten-stage rail (Main.dc.html) — every stage clickable
    from every page, the current one highlighted, plus Back/Next. On the two
    reference sheets no tile is current and Back/Next collapse to one link
    back into the journey."""
    active_n = next((n for s, n, _, _, _ in STAGES if s == active_slug), 0)
    tiles = []
    for slug, n, name, _, _ in STAGES:
        cur, past = n == active_n, n < active_n
        bg = "var(--accent-soft)" if cur else ("var(--panel)" if past else "var(--recess)")
        bd = "var(--accent)" if cur else ("var(--border2)" if past else "var(--border)")
        fg = "var(--accent)" if cur else ("var(--text2)" if past else "var(--dim)")
        bar = "var(--accent)" if cur else ("var(--dim)" if past else "var(--border)")
        tiles.append(f'''<a href="{e(slug)}.html" style="flex:1; min-width:74px; border-radius:8px; padding:8px 7px 9px; box-sizing:border-box; background:{bg}; border:1px solid {bd}; color:{fg};">
      <div style="height:2px; border-radius:2px; margin-bottom:6px; background:{bar};"></div>
      <div class="mono" style="font-size:9px; opacity:0.75; margin-bottom:2px;">{n:02d}</div>
      <div style="font-size:10px; font-weight:600; line-height:1.3;">{e(name)}</div>
    </a>''')

    if active_n:
        prev_slug = STAGES[active_n - 2][0] if active_n > 1 else None
        next_slug = STAGES[active_n][0] if active_n < len(STAGES) else None
        back = (f'<a href="{e(prev_slug)}.html" style="padding:5px 12px; border-radius:7px; border:1px solid var(--border); background:var(--panel); color:var(--text2); font-size:11px;">&larr; Back</a>'
                if prev_slug else
                '<span style="padding:5px 12px; border-radius:7px; border:1px solid var(--border); background:var(--recess); color:var(--dim); font-size:11px;">&larr; Back</span>')
        fwd = (f'<a href="{e(next_slug)}.html" style="padding:5px 12px; border-radius:7px; border:1px solid oklch(78% 0.14 75 / 0.55); background:var(--panel); color:var(--accent); font-size:11px; font-weight:600;">Next &rarr;</a>'
               if next_slug else
               '<span style="padding:5px 12px; border-radius:7px; border:1px solid var(--border); background:var(--recess); color:var(--dim); font-size:11px;">Next &rarr;</span>')
        controls = back + fwd
    else:
        controls = '<a href="stage-1.html" style="padding:5px 12px; border-radius:7px; border:1px solid oklch(78% 0.14 75 / 0.55); background:var(--panel); color:var(--accent); font-size:11px; font-weight:600;">&larr; Back to the journey</a>'

    return f'''
<div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:14px 16px 12px; margin-bottom:18px;">
  <div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:10px;">
    <div style="display:flex; align-items:baseline; gap:11px; flex-wrap:wrap;">
      <div style="font-size:13px; font-weight:600;">TASK-026</div>
      <div style="font-size:11px; color:var(--text3);">from a sentence you typed to agents at work &mdash; ten stages, all clickable</div>
    </div>
    <div style="display:flex; gap:7px;">{controls}</div>
  </div>
  <div style="display:flex; gap:3px; align-items:stretch; flex-wrap:wrap;">{"".join(tiles)}</div>
  {_legend()}
</div>'''


def _stage_head(n: int, kicker: str, title: str, sub_html: str) -> str:
    return f'''
<div style="display:flex; align-items:baseline; gap:10px; margin-bottom:3px;">
  <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--gray); text-transform:uppercase;">Stage {n} of 10</div>
  <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase;">{e(kicker)}</div>
</div>
<div style="font-family:var(--disp); font-size:19px; font-weight:600; margin:0 0 4px;">{e(title)}</div>
<div style="font-size:11.5px; color:var(--text3); margin:0 0 20px; line-height:1.55; max-width:860px;">{sub_html}</div>'''


def _sheet_head(kicker: str, title: str, sub_html: str) -> str:
    return f'''
<div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; margin-bottom:3px;">{e(kicker)}</div>
<div style="font-family:var(--disp); font-size:19px; font-weight:600; margin:0 0 4px;">{e(title)}</div>
<div style="font-size:11.5px; color:var(--text3); margin:0 0 20px; line-height:1.6; max-width:900px;">{sub_html}</div>'''


def _said_strip(note: str = "unedited &middot; on every screen") -> str:
    """The compact one-line raw-idea strip carried on stages 4-7 — Product
    §6 / design review §1.1: the Founder's own words are on ALL ten stages,
    in the same place, in the same treatment, never in an archive."""
    return f'''
<div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:11px 16px; margin-bottom:18px; display:flex; align-items:center; gap:14px; flex-wrap:wrap;">
  <div style="width:3px; align-self:stretch; min-height:16px; background:var(--gray); border-radius:2px; flex-shrink:0;"></div>
  <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--gray); text-transform:uppercase; flex-shrink:0;">You said</div>
  <div style="font-size:11.5px; color:var(--text2); line-height:1.55; white-space:pre-wrap;">&ldquo;{e(RAW_IDEA)}&rdquo;</div>
  <div style="font-size:10px; color:var(--dim); flex-shrink:0; margin-left:auto;">{note}</div>
</div>'''


def _said_panel(footer_html: str) -> str:
    """The full "You said" panel: recessed ground, 3px gray rule, quotation
    marks, pre-wrap, no company colour anywhere on it (design review §1)."""
    return f'''
<div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:17px 18px;">
  <div style="display:flex; align-items:center; gap:8px; margin-bottom:10px;">
    <div style="width:3px; height:12px; background:var(--gray); border-radius:2px;"></div>
    <div style="font-size:10px; font-weight:700; letter-spacing:0.07em; color:var(--gray); text-transform:uppercase;">You said</div>
  </div>
  <div style="font-size:13px; line-height:1.7; color:var(--text); white-space:pre-wrap;">&ldquo;{e(RAW_IDEA)}&rdquo;</div>
  <div style="font-size:10.5px; color:var(--dim); margin-top:13px; padding-top:11px; border-top:1px solid var(--hair); line-height:1.6;">{footer_html}</div>
</div>'''


def _footer() -> str:
    """Main.dc.html's "About this prototype" block, on every page — it is the
    honest disclosure about what these pages are, so it does not get dropped
    from any of them."""
    sheets = " &middot; ".join(
        f'<a href="{e(slug)}.html" style="color:var(--accent);">{e(title)}</a>' for slug, title in SHEETS)
    return f'''
<div style="margin-top:26px; border-radius:12px; border:1px dashed var(--border); background:var(--recess); padding:14px 18px;">
  <div class="label" style="margin-bottom:7px;">About this preview</div>
  <div style="font-size:11px; color:var(--text3); line-height:1.65; max-width:920px;">
    Working navigation, no backend. Every control here moves you between drawn states; nothing is dispatched, no model is invoked and no money is spent by clicking anything.
    The idea it walks is real &mdash; the Founder&rsquo;s own words for TASK-026, together with the real feedback given later.
    The database facts quoted throughout (0 of 13 agent runs carrying a cost, <span class="mono">task_steps</span> on 1 of 24 tasks, <span class="mono">project_id</span> NULL on 20 of 24, one row in <span class="mono">projects</span>) are quoted from Design&rsquo;s artboards. Anything the product could not know honestly is drawn as a bracketed placeholder rather than filled in.
  </div>
  <div style="font-size:11px; color:var(--text3); margin-top:10px;">Reference sheets: {sheets}</div>
</div>'''


def _next_link(slug: str, label: str, note_html: str = "", filled: bool = False) -> str:
    """A stage's own forward control — the artboards' per-screen "advance",
    rendered as a plain GET link. Outlined by default: in this product an
    unfilled control has never been the thing that spends."""
    style = ("padding:9px 18px; border-radius:8px; background:var(--accent); color:var(--ink-accent); font-weight:700; font-size:12.5px; display:inline-block;"
             if filled else
             "padding:9px 18px; border-radius:8px; background:transparent; border:1px solid var(--border2); color:var(--text2); font-weight:600; font-size:12.5px; display:inline-block;")
    note = f'<div style="font-size:11px; color:var(--dim);">{note_html}</div>' if note_html else ""
    return f'''
<div style="margin-top:18px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
  <a href="{e(slug)}.html" style="{style}">{label}</a>{note}
</div>'''


# ---------------------------------------------------------------------------
# Stage 1 — RAW IDEA (S1RawIdea.dc.html)
# ---------------------------------------------------------------------------


def _stage1(params: dict) -> str:
    mode = params.get("mode", "compose")
    if mode not in ("compose", "saved", "arm"):
        mode = "compose"

    head = _stage_head(1, "Raw idea", "Bring an idea to the company",
                       "Short, messy, half-formed is fine. You are not writing a specification &mdash; that is the company&rsquo;s job. "
                       "Your words are stored exactly as you type them and are never edited by anyone, including us.")

    if mode == "compose":
        body = f'''
<div style="display:grid; grid-template-columns:minmax(0,1.55fr) minmax(0,1fr); gap:18px; align-items:start;">
  <div class="panel" style="padding:18px;">
    <div class="label" style="margin-bottom:9px;">Name it</div>
    <div style="border-radius:8px; border:1px solid var(--border2); background:var(--inset); padding:10px 12px; font-size:12.5px; color:var(--dim); margin-bottom:16px;">A short name &mdash; a few words is all it needs</div>

    <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:9px;">
      <div class="label">The idea, in your own words</div>
      <div style="font-size:10.5px; color:var(--dim);">stored exactly as typed</div>
    </div>
    <div style="border-radius:8px; border:1px solid oklch(58% 0.015 250 / 0.55); background:var(--inset); padding:13px 14px; min-height:104px;">
      <div style="font-size:13px; line-height:1.65; color:var(--text); white-space:pre-wrap;">{e(RAW_IDEA)}</div>
      <div style="height:15px; width:1.5px; background:var(--accent); margin-top:2px;"></div>
    </div>
    <div style="font-size:10.5px; color:var(--dim); margin-top:7px;">123 of 4,000 characters</div>

    <div style="display:flex; align-items:center; gap:16px; margin-top:16px; margin-bottom:14px; flex-wrap:wrap;">
      <div class="label">Priority</div>
      <div style="display:flex; gap:7px; flex-wrap:wrap;">
        <div class="pill" style="border:1px solid var(--border2); color:var(--text2); font-weight:400;">High</div>
        <div class="pill" style="border:1px solid var(--accent); background:var(--accent-soft); color:var(--accent);">Medium</div>
        <div class="pill" style="border:1px solid var(--border2); color:var(--text2); font-weight:400;">Low</div>
        <div class="pill" style="border:1px dashed var(--border2); color:var(--dim); font-weight:400;">Skip</div>
      </div>
    </div>

    <div style="display:flex; align-items:center; gap:11px; padding-top:15px; border-top:1px solid var(--border); flex-wrap:wrap;">
      <a href="stage-1.html?mode=saved" style="padding:9px 20px; border-radius:8px; background:var(--accent); color:var(--ink-accent); font-weight:600; font-size:13px;">Save Idea</a>
      <a href="stage-1.html?mode=arm" style="padding:9px 18px; border-radius:8px; background:transparent; border:1px solid var(--border2); color:var(--text2); font-weight:600; font-size:12.5px;">Refine / Interpret&hellip;</a>
    </div>
    <div style="display:grid; grid-template-columns:auto 1fr; gap:5px 10px; margin-top:12px; font-size:11px; color:var(--text3); line-height:1.55;">
      <div style="color:var(--accent); font-weight:600;">Save</div>
      <div>writes one row and stops. No agent runs, nothing is spent, nothing starts.</div>
      <div style="color:var(--text2); font-weight:600;">Refine</div>
      <div>opens the disclosure for asking the company to interpret it. It does not spend on this click &mdash; nothing on this page does.</div>
    </div>
  </div>

  <div class="panel" style="padding:18px;">
    <div class="label" style="margin-bottom:4px;">In Backlog &mdash; saved, not started</div>
    <div style="font-size:11px; color:var(--text3); line-height:1.5; margin-bottom:13px;">A standing list, not a notification. Anything you save stays here until you deliberately start it.</div>
    <div class="card">
      <div style="display:flex; gap:9px; align-items:flex-start;">
        <div style="width:8px; height:8px; border-radius:50%; border:1.5px solid var(--gray); box-sizing:border-box; margin-top:4px; flex-shrink:0;"></div>
        <div>
          <div style="font-size:12px; font-weight:600; line-height:1.4;">TASK-025 &mdash; Divergent-thinking stage: real brainstorming before requirements lock</div>
          <div style="font-size:10.5px; color:var(--text3); margin-top:5px;">In Backlog 4d &middot; not started &middot; waiting for you</div>
        </div>
      </div>
    </div>
    <div style="font-size:10.5px; color:var(--dim); margin-top:11px; line-height:1.5;">One real row today. When this list is empty it says so &mdash; &ldquo;No ideas saved yet&rdquo; &mdash; rather than rendering an empty box.</div>
  </div>
</div>'''
    elif mode == "saved":
        body = f'''
<div style="display:grid; grid-template-columns:minmax(0,1.55fr) minmax(0,1fr); gap:18px; align-items:start;">
  <div>
    <div style="border-radius:14px; border:1px solid oklch(72% 0.15 150 / 0.5); background:var(--green-soft); padding:16px 18px; margin-bottom:16px;">
      <div style="font-size:13.5px; font-weight:600; margin-bottom:6px;">Saved. TASK-026 is in the Backlog.</div>
      <div style="font-size:12px; color:var(--text2); line-height:1.6;">
        One task row and one history entry were written. <b style="color:var(--text);">0 agents dispatched &middot; 0 model calls &middot; nothing spent &middot; 0 other tasks changed.</b>
        Your words are stored exactly as you typed them and will not be edited by anyone.
      </div>
    </div>
    <div class="panel" style="padding:18px;">
      <div class="label" style="margin-bottom:8px;">What happens next is your call</div>
      <div style="font-size:12px; color:var(--text2); line-height:1.65; margin-bottom:14px;">
        Nothing happens on its own. The idea can sit here indefinitely. When you want the company&rsquo;s reading of it, you ask &mdash; and that costs money, so you are told what it costs before you agree, not after.
      </div>
      <a href="stage-1.html?mode=arm" style="padding:9px 18px; border-radius:8px; background:transparent; border:1px solid var(--accent); color:var(--accent); font-weight:600; font-size:12.5px; display:inline-block;">Refine / Interpret&hellip;</a>
    </div>
  </div>
  <div class="panel" style="padding:18px;">
    <div class="label" style="margin-bottom:13px;">In Backlog &mdash; saved, not started</div>
    <div class="card" style="border-color:oklch(78% 0.14 75 / 0.4); margin-bottom:9px;">
      <div style="display:flex; gap:9px; align-items:flex-start;">
        <div style="width:8px; height:8px; border-radius:50%; border:1.5px solid var(--gray); box-sizing:border-box; margin-top:4px; flex-shrink:0;"></div>
        <div>
          <div style="font-size:12px; font-weight:600; line-height:1.4;">TASK-026 &mdash; the idea you just saved</div>
          <div style="font-size:10.5px; color:var(--text3); margin-top:5px;">In Backlog 0m &middot; not started &middot; not interpreted</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div style="display:flex; gap:9px; align-items:flex-start;">
        <div style="width:8px; height:8px; border-radius:50%; border:1.5px solid var(--gray); box-sizing:border-box; margin-top:4px; flex-shrink:0;"></div>
        <div>
          <div style="font-size:12px; font-weight:600; line-height:1.4;">TASK-025 &mdash; Divergent-thinking stage</div>
          <div style="font-size:10.5px; color:var(--text3); margin-top:5px;">In Backlog 4d &middot; not started</div>
        </div>
      </div>
    </div>
  </div>
</div>'''
    else:  # arm
        body = f'''
<div class="panel" style="border-color:var(--accent); padding:20px; max-width:880px;">
  <div style="display:flex; align-items:center; gap:9px; margin-bottom:14px; flex-wrap:wrap;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--accent); text-transform:uppercase;">Before the company reads this</div>
    <span class="pill" style="background:var(--accent-soft); color:var(--accent); letter-spacing:0.04em;">SPENDS MONEY</span>
  </div>

  <div class="card" style="margin-bottom:16px;">
    <div class="label" style="margin-bottom:6px;">You are about to ask about</div>
    <div style="border-left:3px solid var(--gray); padding-left:11px; font-size:12.5px; line-height:1.6; color:var(--text); white-space:pre-wrap;">&ldquo;{e(RAW_IDEA)}&rdquo;</div>
  </div>

  <div style="display:grid; grid-template-columns:auto 1fr; gap:9px 14px; align-items:baseline; font-size:12px; color:var(--text2); line-height:1.6;">
    <div class="mono" style="text-align:right; font-weight:700; color:var(--accent); font-size:11.5px;">what</div>
    <div>This starts <b style="color:var(--text);">understanding and evaluation</b> &mdash; not building. Nothing gets designed and no code is written.</div>
    <div class="mono" style="text-align:right; font-weight:700; color:var(--text3); font-size:11.5px;">who</div>
    <div>Several agents, not one. Which ones is the company&rsquo;s call, and you will see the list.</div>
    <div class="mono" style="text-align:right; font-weight:700; color:var(--text3); font-size:11.5px;">cost</div>
    <div>No estimate exists. <b style="color:var(--text);">0 of the 13 agent runs on record carries a cost figure</b>, so any number here would be invented.</div>
    <div class="mono" style="text-align:right; font-weight:700; color:var(--text3); font-size:11.5px;">ceiling</div>
    <div><span class="ph">[ per-round maximum &mdash; computed from the real dispatch path, not yet wired ]</span> <span style="color:var(--text3);">A ceiling is enforced per invocation. The round total must be computed from the mechanism that actually runs it; until that exists this shows no number rather than a copied one.</span></div>
    <div class="mono" style="text-align:right; font-weight:700; color:var(--red); font-size:11.5px;">stop</div>
    <div><b style="color:var(--text);">There is no stop button.</b> A round runs to completion.</div>
    <div class="mono" style="text-align:right; font-weight:700; color:var(--text3); font-size:11.5px;">again</div>
    <div>This may be the first of several. If you send it back with feedback, that round costs again.</div>
  </div>

  <div style="display:flex; align-items:center; gap:10px; padding-top:16px; margin-top:16px; border-top:1px solid var(--border); flex-wrap:wrap;">
    <a href="stage-2.html" style="padding:9px 18px; border-radius:8px; background:var(--accent); color:var(--ink-accent); font-weight:700; font-size:12.5px;">Yes &mdash; have the company interpret this and spend</a>
    <a href="stage-1.html?mode=saved" style="padding:9px 18px; border-radius:8px; background:var(--panel2); border:1px solid var(--border2); color:var(--text2); font-size:12.5px;">Not now &mdash; leave it in the Backlog</a>
  </div>
  <div style="font-size:11px; color:var(--text3); margin-top:12px; line-height:1.55;">
    In this preview both controls are links to other drawn screens. Nothing is dispatched by either.
  </div>
</div>'''

    modes = ('<div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px;">'
             + "".join(
                 f'<a href="stage-1.html?mode={k}" style="padding:6px 13px; border-radius:8px; border:1px solid {"var(--accent)" if mode == k else "var(--border)"}; '
                 f'background:{"var(--accent-soft)" if mode == k else "var(--panel)"}; color:{"var(--accent)" if mode == k else "var(--text2)"}; font-size:11.5px; font-weight:600;">{e(label)}</a>'
                 for k, label in (("compose", "Compose"), ("saved", "Saved"), ("arm", "Refine / Interpret disclosure")))
             + '<div style="font-size:10.5px; color:var(--dim); align-self:center;">Three drawn states of one screen. In the product you reach them by using the controls; here they are also directly reachable.</div></div>')

    return head + modes + body + _next_link(
        "stage-2", "The company is reading it &rarr;",
        "Next: <b style=\"color:var(--text2);\">FACTORY INTERPRETING</b>.")


def _disclosure(show_label: str, hide_label: str, inner_html: str, boxed: bool = True) -> str:
    """A disclosure whose label is not the concise layer's "show the
    working" phrasing — the roster expanders on stages 2 and 3. Same
    pure-CSS <details> mechanics as _expander()."""
    inner = f'<div class="inset">{inner_html}</div>' if boxed else inner_html
    return f'''<details class="dcx">
  <summary><span class="dcx-show">+&nbsp; {e(show_label)}</span><span class="dcx-hide">&minus;&nbsp; {e(hide_label)}</span></summary>
  {inner}
</details>'''


# ---------------------------------------------------------------------------
# Stage 2 — FACTORY INTERPRETING (S2Interpreting.dc.html)
# ---------------------------------------------------------------------------


def _stage2(params: dict) -> str:
    roster = _disclosure(
        "Why each of these, and who was left out", "Hide why each was chosen", '''
    <div style="display:flex; flex-direction:column; gap:11px;">
      <div>
        <div style="font-size:11.5px; font-weight:600; color:var(--text);">Product</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55;">Always on the roster. Owns the problem, the target user, the scope and what belongs in a first version.</div>
      </div>
      <div>
        <div style="font-size:11.5px; font-weight:600; color:var(--text);">CTO</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55;">Only CTO can say what the database actually holds &mdash; and that decides whether a percentage or a live indicator can honestly exist on this screen at all.</div>
      </div>
      <div>
        <div style="font-size:11.5px; font-weight:600; color:var(--text);">Red Team</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55;">The idea names a shape before naming what goes on it. Red Team is the role whose job is to say that building the shape first is the risk.</div>
      </div>
      <div style="padding-top:10px; border-top:1px solid var(--border);">
        <div class="label" style="margin-bottom:7px;">Not consulted, and why</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55; margin-bottom:7px;"><b style="color:var(--text);">CEO</b> &mdash; nobody outside this company chooses this screen, so there is no market direction or positioning question to answer.</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55; margin-bottom:7px;"><b style="color:var(--text);">Financial, Security</b> &mdash; no cost structure, no identity, payments or sensitive data in play.</div>
        <div style="font-size:11px; color:var(--red); line-height:1.55;"><b>Design</b> &mdash; would have been material here; this is a user-experience idea. It could not be consulted: <span class="mono" style="font-size:10.5px;">design</span> is not on the meeting participant allowlist today. Recorded rather than silently left out.</div>
      </div>
    </div>''')

    pills = "".join(
        f'<div class="pill" style="border:1px solid oklch(70% 0.12 300 / 0.55); background:var(--violet-soft); color:var(--violet); font-size:11px;">{e(n)}</div>'
        for n in ("Product", "CTO", "Red Team"))

    body = f'''
<div class="panel" style="padding:16px 18px; margin-bottom:16px;">
  <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:8px; gap:12px; flex-wrap:wrap;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--gray); text-transform:uppercase;">You said</div>
    <div style="font-size:10.5px; color:var(--dim);">TASK-026 &middot; your words, unedited</div>
  </div>
  <div style="border-left:3px solid var(--gray); padding-left:13px; font-size:13px; line-height:1.65; color:var(--text); white-space:pre-wrap;">&ldquo;{e(RAW_IDEA)}&rdquo;</div>
</div>

<div style="display:grid; grid-template-columns:minmax(0,1.4fr) minmax(0,1fr); gap:18px; align-items:start;">
  <div class="panel" style="border-color:oklch(72% 0.12 250 / 0.45); padding:20px;">
    <div style="display:flex; align-items:center; gap:9px; margin-bottom:14px;">
      <div style="width:9px; height:9px; border-radius:50%; background:var(--blue);"></div>
      <div style="font-size:14px; font-weight:600;">Reading it now</div>
    </div>
    <div style="display:flex; flex-direction:column; gap:11px; margin-bottom:18px;">
      <div style="display:flex; gap:11px; align-items:flex-start;">
        <div style="width:7px; height:7px; border-radius:50%; background:var(--green); margin-top:5px; flex-shrink:0;"></div>
        <div style="font-size:12px; color:var(--text2); line-height:1.55;"><b style="color:var(--text);">Perspectives chosen.</b> Chief of Staff picked who could materially improve the reading of <i>this</i> idea &mdash; not everyone.</div>
      </div>
      <div style="display:flex; gap:11px; align-items:flex-start;">
        <div style="width:7px; height:7px; border-radius:50%; background:var(--blue); margin-top:5px; flex-shrink:0;"></div>
        <div style="font-size:12px; color:var(--text2); line-height:1.55;"><b style="color:var(--text);">They are considering it, separately.</b> They may disagree with each other. You will not be handed that argument.</div>
      </div>
      <div style="display:flex; gap:11px; align-items:flex-start;">
        <div style="width:7px; height:7px; border-radius:50%; border:1.5px solid var(--dash); box-sizing:border-box; margin-top:5px; flex-shrink:0;"></div>
        <div style="font-size:12px; color:var(--text3); line-height:1.55;">Chief of Staff writes <b style="color:var(--text2);">one</b> answer and brings it to you.</div>
      </div>
    </div>
    <div style="border-radius:10px; border:1px dashed var(--border2); background:var(--inset); padding:13px 14px;">
      <div class="label" style="margin-bottom:6px;">Why there is no progress bar here</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">
        There is no honest number to put in one. Positions are gathered at the same time, not in sequence, and this product records nothing while a run is in flight &mdash;
        <b style="color:var(--text);">0 of 13 recorded agent runs carries a duration or a cost.</b>
        A bar here would be an animation, not a measurement. There is no estimated finish time for the same reason.
      </div>
    </div>
    <div style="font-size:11px; color:var(--text3); line-height:1.6; margin-top:14px;">
      You will not be shown three reports. One answer comes back, and it will say who was consulted.
    </div>
  </div>

  <div class="panel" style="padding:18px;">
    <div class="label" style="margin-bottom:9px;">Company perspectives consulted</div>
    <div style="display:flex; gap:7px; flex-wrap:wrap; margin-bottom:6px;">{pills}</div>
    {roster}
    <div style="margin-top:16px; padding-top:14px; border-top:1px solid var(--border);">
      <div class="label" style="margin-bottom:8px;">Depth</div>
      <div style="display:flex; align-items:flex-start; gap:10px; flex-wrap:wrap;">
        <div class="pill" style="border:1px solid var(--dash); background:var(--panel2); color:var(--text); font-size:11px; font-weight:700; flex-shrink:0;">Light</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55; flex:1; min-width:200px;">Nobody outside this company chooses between this screen and an alternative &mdash; it is our own console. Competitor and market analysis could not change the recommendation, so it will not be produced.</div>
      </div>
      <div style="font-size:10.5px; color:var(--dim); margin-top:9px; line-height:1.5;">The other setting is <b style="color:var(--text3);">Full</b>, and it has to name who chooses and what else they could choose. It costs more, which is part of why you are shown which one is running. <a href="full-depth.html" style="color:var(--accent);">See the Full-depth layer &rarr;</a></div>
    </div>
  </div>
</div>'''

    head = _stage_head(2, "Factory interpreting", "The company is considering your idea",
                       "You can leave this page. The round keeps running and the result waits for you here.")
    return head + body + _next_link(
        "stage-3", "Leave this page &mdash; the round keeps running",
        "Next: <b style=\"color:var(--text2);\">FACTORY UNDERSTANDING</b>.")


# ---------------------------------------------------------------------------
# The concise question row — one per Founder question, carrying its full
# answer in prose on the panel ground, with the expanded material behind one
# labelled disclosure (design review §2). Shared by stages 3 and 4.
# ---------------------------------------------------------------------------

# The four company voices a question row can speak in. Gray ("you said") is
# never a question row — it is only ever the Founder's own words.
VOICE = {
    "mean": ("WE THINK YOU MEAN", "var(--blue)", "var(--blue-soft)"),
    "think": ("WHAT WE THINK OF IT", "var(--violet)", "var(--violet-soft)"),
    "recommend": ("WE RECOMMEND", "var(--accent)", "oklch(78% 0.14 75 / 0.16)"),
    "need": ("WE NEED FROM YOU", "var(--accent)", "oklch(78% 0.14 75 / 0.16)"),
}


def _q(num: int, title: str, voice: str, answer_html: str, *,
       rule: str | None = None, border: str = "var(--border)", bg: str = "var(--panel)",
       extra_html: str = "", expander: tuple[str, str] | None = None,
       accent_inset: bool = False, big_answer: bool = False) -> str:
    kicker, kcolor, kbg = VOICE[voice]
    rule_css = f" border-left:3px solid {rule};" if rule else ""
    answer_style = ("font-size:13.5px; color:var(--text); line-height:1.65; font-weight:500;"
                    if big_answer else "font-size:12.5px; color:var(--prose); line-height:1.7;")
    exp = _expander(expander[0], expander[1], accent_rule=accent_inset) if expander else ""
    return f'''
<div style="border-radius:12px; border:1px solid {border}; background:{bg}; padding:16px 18px;{rule_css}">
  <div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; margin-bottom:8px; flex-wrap:wrap;">
    <div style="display:flex; align-items:baseline; gap:10px;">
      <div class="mono" style="font-size:11px; color:var(--dim);">{num:02d}</div>
      <div style="font-size:13.5px; font-weight:600; color:var(--text);">{e(title)}</div>
    </div>
    <div class="pill" style="background:{kbg}; color:{kcolor}; font-size:9.5px; letter-spacing:0.05em; white-space:nowrap;">{e(kicker)}</div>
  </div>
  <div style="{answer_style}">{answer_html}</div>
  {extra_html}
  {exp}
</div>'''


def _roster_depth_strip() -> str:
    """The roster/depth strip carried on the result screens (stage 3), with
    the depth chip and its one-line reason beside it — design review §3:
    depth is a visible chip with a reason, never a setting buried in a
    panel."""
    pills = "".join(
        f'<div class="pill" style="border:1px solid oklch(70% 0.12 300 / 0.5); color:var(--violet); font-size:10.5px;">{e(n)}</div>'
        for n in ("Product", "CTO", "Red Team"))
    inner = '''
    <div class="qrow" style="gap:12px 22px; margin-top:13px; padding-top:13px; border-top:1px solid var(--border);">
      <div style="font-size:11px; color:var(--text2); line-height:1.55;"><b style="color:var(--text);">Product</b> &mdash; always on the roster; owns problem, scope and first version.</div>
      <div style="font-size:11px; color:var(--text2); line-height:1.55;"><b style="color:var(--text);">CTO</b> &mdash; only CTO can say what the records actually hold, which decides what this screen can honestly show.</div>
      <div style="font-size:11px; color:var(--text2); line-height:1.55;"><b style="color:var(--text);">Red Team</b> &mdash; the idea names a shape before naming its contents; that is the risk worth stating.</div>
      <div style="font-size:11px; color:var(--text2); line-height:1.55;"><b style="color:var(--text);">CEO, Financial, Security</b> &mdash; left out: no market, no cost structure, no sensitive data in play.</div>
      <div style="font-size:11px; color:var(--red); line-height:1.55; grid-column:1 / -1;"><b>Design was material and could not be consulted</b> &mdash; <span class="mono" style="font-size:10.5px;">design</span> is not on the meeting participant allowlist today. Said out loud rather than left out quietly.</div>
      <div style="font-size:11px; color:var(--text3); line-height:1.55; grid-column:1 / -1;">The internal discussion is kept and is one click away. It is not shown here because three reports are not an answer.</div>
    </div>'''
    return f'''
<div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:12px 16px; margin-bottom:20px;">
  <div style="display:flex; align-items:center; gap:16px; flex-wrap:wrap;">
    <div style="font-size:11px; color:var(--text3);">Perspectives consulted</div>
    <div style="display:flex; gap:6px; flex-wrap:wrap;">{pills}</div>
    <div style="width:1px; height:16px; background:var(--border);"></div>
    <div style="font-size:11px; color:var(--text3);">Depth</div>
    <div class="pill" style="border:1px solid var(--dash); color:var(--text); font-size:10.5px; font-weight:700;">Light</div>
    <div style="font-size:11px; color:var(--text2); flex:1; min-width:280px;">&mdash; nobody outside this company chooses this screen, so competitor and market work could not change the answer.</div>
  </div>
  {_disclosure("Why these, and who was left out", "Hide", inner, boxed=False)}
</div>'''


# ---------------------------------------------------------------------------
# Stage 3 — FACTORY UNDERSTANDING (S3Understanding.dc.html)
# ---------------------------------------------------------------------------


def _stage3(params: dict) -> str:
    head = _stage_head(
        3, "Factory understanding", "What we think you asked for",
        'Ten answers, about two minutes. <b style="color:var(--text2);">You can approve from this page without opening anything.</b> '
        'Everything behind a &ldquo;show the working&rdquo; is evidence for a decision you can already make &mdash; not part of the decision.')

    two_voices = f'''
<div style="display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.35fr); gap:16px; align-items:stretch; margin-bottom:18px;">
  {_said_panel("Your words, 1 Sep 2026 20:03 UTC. Never edited, by anyone, ever &mdash; not by you, not by us. They stay on this screen for the life of the idea.")}
  <div class="panel" style="border-color:oklch(72% 0.12 250 / 0.45); padding:17px 18px; border-left:3px solid var(--blue);">
    <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.07em; color:var(--blue); text-transform:uppercase;">We think you mean</div>
      <div style="font-size:10px; color:var(--dim);">the company &middot; round 1 &middot; v1</div>
    </div>
    <div style="font-size:13px; line-height:1.7; color:var(--text);">
      Today&rsquo;s Control Center makes you <i>read</i> to find out what is happening &mdash; thirteen tabs of dense text panels, lists and paragraphs. You want the opposite: one screen where the state of the company is visible at a glance.
      The <b>ellipse</b> we read as your sketch of the form &mdash; the pipeline drawn as a loop with work visible as it moves round it &mdash; rather than a requirement that the shape be an ellipse.
    </div>
    <div style="font-size:10.5px; color:var(--dim); margin-top:13px; padding-top:11px; border-top:1px solid var(--border); line-height:1.55;">
      This is our reading, not your words. If it is wrong, correcting it costs nothing and takes one click &mdash; and correcting it here is far cheaper than correcting it after we have built something.
    </div>
  </div>
</div>'''

    q1 = _q(1, "Did the factory understand my idea?", "mean", rule="var(--blue)", answer_html='''
        We think so. You are not asking for a chart &mdash; you are saying the Control Center makes you read to learn what is happening, and you want to see it instead. The ellipse we read as your sketch of the form, not as a requirement that the shape be an ellipse. If that second half is wrong it changes what we build first, so we are asking about it rather than guessing &mdash; question 9.''',
            expander=("sections 1 and 2", f'''
        <div class="inset-k">Expanded &middot; sections 1 and 2 of the company&rsquo;s output contract</div>
        <div class="qrow">
          <div>
            <div style="font-size:10px; font-weight:700; color:var(--gray); letter-spacing:0.05em; margin-bottom:6px;">1 &middot; ORIGINAL IDEA</div>
            <div style="font-size:11.5px; color:var(--text2); line-height:1.6; white-space:pre-wrap;">&ldquo;{e(RAW_IDEA)}&rdquo;</div>
            <div style="font-size:10.5px; color:var(--dim); margin-top:8px;">Stored verbatim. 123 characters. Byte-identical to what you typed.</div>
          </div>
          <div>
            <div style="font-size:10px; font-weight:700; color:var(--blue); letter-spacing:0.05em; margin-bottom:6px;">2 &middot; WHAT WE THINK YOU MEAN</div>
            <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">
              Three claims, so you can reject them one at a time: <b style="color:var(--prose);">(a)</b> the problem is reading, not missing information; <b style="color:var(--prose);">(b)</b> the fix is one screen, not a better-organised thirteen; <b style="color:var(--prose);">(c)</b> &ldquo;ellipse&rdquo; describes a way of seeing flow, and is a candidate form rather than the requirement.
            </div>
          </div>
        </div>'''))

    q2 = _q(2, "What am I really trying to achieve?", "mean", rule="var(--blue)", big_answer=True, answer_html='''
        You want to open the AI Factory and understand within seconds how each child product is progressing without reading internal task records.''',
            expander=("section 3", '''
        <div class="inset-k">Expanded &middot; section 3 &middot; what you are really trying to achieve</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
          The requested feature was &ldquo;a dashboard, like an ellipse.&rdquo; The outcome behind it is not a shape and not a page &mdash; it is <b style="color:var(--prose);">time to knowing</b>. Today that time is measured in pages read; you want it measured in seconds looked.
          Two consequences follow, and they are why this distinction is worth making:
          a design that draws a beautiful ring but still requires you to click into a task to learn what is stuck has <b style="color:var(--prose);">not</b> met this;
          a design that is an ugly list you can read in three seconds <b style="color:var(--prose);">has</b>.
        </div>'''))

    q3 = _q(3, "Why might this be worth building?", "think", rule="var(--violet)", answer_html='''
        Because the problem is observed rather than assumed: you went looking for the Meetings page and could not find it, and it is the eighth item in a thirteen-item nav bar. And because the factory is the product &mdash; its own console is the demonstration, not a side view of it.
        The merit is in the legibility, though, not in the ellipse. <b style="color:var(--text);">If the loop gets drawn and the records behind it stay thin, the screen is prettier and no more informative.</b>''',
            expander=("section 4", '''
        <div class="inset-k">Expanded &middot; section 4 &middot; why this may be valuable</div>
        <div style="display:flex; flex-direction:column; gap:9px;">
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">A real, witnessed user problem.</b> Not a persona and not a survey &mdash; the one user of this product could not find a page that exists. That is the strongest evidence a small company ever gets.</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">Speed.</b> The picture you presently assemble by reading nine pages arrives in one look.</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">Strategic.</b> If the factory is the product, watching the factory work is the product working. Nothing else in the roadmap demonstrates that.</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">Simplicity, with a caveat.</b> Fewer things on screen is a genuine merit. Fewer things <i>reachable</i> would reproduce the exact failure that prompted this &mdash; a page that exists and cannot be found.</div>
          <div style="font-size:11.5px; color:var(--red); line-height:1.6; padding-top:8px; border-top:1px solid var(--hair);"><b>Where the merits are weak:</b> nothing here makes the factory build faster or better. It makes the building legible. That is worth doing and it is not a capability gain, and we are not going to call it one because you proposed it.</div>
        </div>'''))

    body = (two_voices + _roster_depth_strip()
            + '<div style="display:flex; flex-direction:column; gap:12px;">' + q1 + q2 + q3 + '</div>')
    return head + body + _next_link(
        "stage-4", "Keep reading &mdash; what we think of the idea",
        "Same page, continued. The rail splits it in two only so you can jump.")


# ---------------------------------------------------------------------------
# Stage 4 — IDEA EVALUATION (S4Evaluation.dc.html)
# ---------------------------------------------------------------------------


def _company_view() -> str:
    """The Company View — six fields, the same six every time, never behind a
    disclosure, and with no score, meter or percentage anywhere on it
    (design review §2 rule 3 and §1's "must never" for the violet voice)."""
    rows = [
        ("Opportunity", "var(--text3)",
         '<div style="font-size:14px; font-weight:700; color:var(--green);">High</div>'),
        ("Why", "var(--text3)",
         '<div style="font-size:12.5px; color:var(--prose); line-height:1.7;">The problem is observed rather than assumed &mdash; you could not find a page that exists, and today&rsquo;s screens make you read to learn what happened. The factory is the product, so its own console is the demonstration rather than a report about it. What is uncertain is not whether to build it but what it can honestly show: the records behind it are thin in specific, checkable ways.</div>'),
        ("Biggest merit", "var(--text3)",
         '<div style="font-size:12.5px; color:var(--prose); line-height:1.7;">It replaces reading with looking, for the one person it is for, on the product that is the point.</div>'),
        ("Biggest threat", "var(--red)",
         '<div style="font-size:12.5px; color:var(--prose); line-height:1.7;">There may not be enough truthful data to fill it. A loop with nothing moving on it is worse than the list it replaced.</div>'),
        ("Best differentiation", "var(--text3)",
         '<div style="font-size:12.5px; color:var(--prose); line-height:1.7;">None we can see, and we did not look &mdash; there is no market here. The one difference that matters internally: today&rsquo;s screens report status, this one would show movement.</div>'),
        ("Recommendation", "var(--accent)",
         '<div><span style="display:inline-block; padding:6px 16px; border-radius:8px; background:oklch(78% 0.14 75 / 0.16); border:1px solid var(--accent); color:var(--accent); font-size:13px; font-weight:700;">Proceed with narrowed scope</span></div>'),
    ]
    grid = "".join(
        f'<div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:{c}; text-transform:uppercase; text-align:right;">{e(label)}</div>{val}'
        for label, c, val in rows)
    return f'''
<div style="margin-top:22px; border-radius:14px; border:1px solid oklch(70% 0.12 300 / 0.55); background:var(--panel); padding:20px 22px;">
  <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; gap:12px; flex-wrap:wrap;">
    <div style="font-size:11px; font-weight:700; letter-spacing:0.08em; color:var(--violet); text-transform:uppercase;">Company view</div>
    <div style="font-size:10.5px; color:var(--dim);">Executive judgment &middot; not a score &middot; always visible, never behind a disclosure</div>
  </div>
  <div style="display:grid; grid-template-columns:150px 1fr; gap:13px 20px; align-items:baseline;">{grid}</div>
  <div style="margin-top:16px; padding-top:13px; border-top:1px solid var(--border); font-size:10.5px; color:var(--dim); line-height:1.6;">
    Six fields, the same six every time. The other three recommendations this company can give are <b style="color:var(--text3);">Proceed</b>, <b style="color:var(--text3);">Investigate first</b> and <b style="color:var(--text3);">Reconsider</b> &mdash; and Reconsider means we think the idea is weak. There is no number here on purpose: a score would be false precision dressed as rigour.
  </div>
</div>'''


def _stage4(params: dict) -> str:
    head = _stage_head(4, "Idea evaluation", "What we think of the idea, and what we recommend",
                       "The second half of the same page. Questions 4 to 10, then the company&rsquo;s closing judgment.")

    q4 = _q(4, "What already exists?", "think", rule="var(--violet)", answer_html='''
        <b style="color:var(--text);">We don&rsquo;t know, and here is why.</b> This is our own operating console; nobody outside this company chooses between it and something else, so what else exists cannot change what we recommend &mdash; that is why the depth is Light and we did not look.
        Two honest cautions rather than a comfortable answer: that is <b style="color:var(--text);">not</b> evidence that nothing comparable exists, and no agent in this company can browse the web, so we could not have checked even if it mattered.''',
            expander=("sections 5 and 6", '''
        <div class="inset-k">Expanded &middot; sections 5 and 6</div>
        <div style="border:1px dashed var(--border2); border-radius:9px; padding:13px 14px; margin-bottom:11px;">
          <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:8px; gap:10px; flex-wrap:wrap;">
            <div style="font-size:10px; font-weight:700; color:var(--text2); letter-spacing:0.05em;">5 &middot; KNOWN COMPETITORS / ALTERNATIVES</div>
            <div style="padding:2px 8px; border-radius:5px; background:var(--panel2); border:1px solid var(--dash); color:var(--text2); font-size:9.5px; font-weight:700; letter-spacing:0.04em;">NOT PRODUCED</div>
          </div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">
            <b style="color:var(--prose);">Why this section is empty:</b> depth for this idea is Light. Nobody outside this company chooses between this screen and an alternative &mdash; it is our own console &mdash; so competitor and substitute analysis could not change the recommendation, the scope or the definition of success. Producing it anyway would be research theatre.
          </div>
          <div style="font-size:11.5px; color:var(--accent); line-height:1.6; margin-top:9px; padding-top:9px; border-top:1px solid var(--hair);">
            This is not the claim that there are no competitors. We have not looked, and we cannot look.
          </div>
        </div>
        <div style="border:1px dashed var(--border2); border-radius:9px; padding:13px 14px;">
          <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:8px; gap:10px; flex-wrap:wrap;">
            <div style="font-size:10px; font-weight:700; color:var(--text2); letter-spacing:0.05em;">6 &middot; COMPETITOR DATA FRESHNESS</div>
            <div style="padding:2px 8px; border-radius:5px; background:var(--panel2); border:1px solid var(--dash); color:var(--text2); font-size:9.5px; font-weight:700; letter-spacing:0.04em;">NOTHING TO LABEL</div>
          </div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">
            No claim about any third party appears above, so there is nothing to mark <span class="mono" style="font-size:10.5px; color:var(--prose);">VERIFIED / CURRENT</span>, <span class="mono" style="font-size:10.5px; color:var(--prose);">COMPANY INFERENCE</span> or <span class="mono" style="font-size:10.5px; color:var(--prose);">UNKNOWN</span>.
          </div>
          <div style="font-size:11.5px; color:var(--prose); line-height:1.6; margin-top:9px; padding:9px 11px; background:var(--panel); border-radius:7px;">
            <b>Standing disclosure:</b> research has not been performed. No agent in this company can browse the web. Wherever this section does have content, everything in it is company recollection &mdash; it may be out of date or wrong.
          </div>
        </div>'''))

    q5 = _q(5, "What could make ours different?", "think", rule="var(--violet)", answer_html='''
        <b style="color:var(--text);">We do not yet see a strong differentiation</b> &mdash; and at this depth we did not look for one, because there is no market to be different in. Inside the company there is one real difference worth naming: today&rsquo;s screens report status, and this one would show movement.''',
            expander=("section 7", '''
        <div class="inset-k">Expanded &middot; section 7 &middot; competitive advantages</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
          At Light depth this section is <b style="color:var(--prose);">not produced as a market claim</b>, for the same reason section 5 is not: differentiation is a comparison, and there is nothing to compare against that anyone chooses between.
          What we will say, because it is checkable inside this company: the advantage over what we run today is that a status is a claim and a movement is evidence. That is a real improvement and it is not a competitive advantage, and we are not going to dress it up as one.
        </div>'''))

    q6 = _q(6, "What could make it fail?", "think", rule="var(--violet)", border="oklch(66% 0.17 25 / 0.35)", answer_html='''
        <b style="color:var(--text);">The data.</b> <span class="mono" style="font-size:11.5px;">task_steps</span> exists on 1 of 24 tasks, so there is no honest percentage;
        <span class="mono" style="font-size:11.5px;">project_id</span> is NULL on 20 of 24, so &ldquo;which app is this build for&rdquo; is unanswerable for most work; and no pipeline agent writes an
        <span class="mono" style="font-size:11.5px;">agent_runs</span> row, so there is no live signal to animate.
        <b style="color:var(--text);">A loop with nothing moving on it is worse than the list it replaced.</b>
        Second: committing to the ellipse now fixes the least certain part of the design before we know what there is to put on it.''',
            expander=("section 8", '''
        <div class="inset-k">Expanded &middot; section 8 &middot; threats, by category</div>
        <div style="display:flex; flex-direction:column; gap:11px;">
          <div>
            <div style="font-size:10px; font-weight:700; color:var(--red); letter-spacing:0.05em; margin-bottom:5px;">TECHNICAL</div>
            <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">The records cannot support the picture. <i style="color:var(--prose);">Changes how we build it:</i> the first version has to render absent data as absent, not animate a placeholder over it.</div>
          </div>
          <div>
            <div style="font-size:10px; font-weight:700; color:var(--red); letter-spacing:0.05em; margin-bottom:5px;">EXECUTION</div>
            <div style="font-size:11.5px; color:var(--text2); line-height:1.6; margin-bottom:7px;">Form fixed before content is known. <i style="color:var(--prose);">Changes what we build first:</i> build the one-glance screen and decide the geometry once a real build has run through it.</div>
            <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">Simplifying by deletion. The thing that started this was a page you could not find; replacing thirteen destinations with one can reproduce that failure in a new shape. <i style="color:var(--prose);">Changes scope:</i> the registers move, they do not go.</div>
          </div>
          <div style="padding-top:9px; border-top:1px solid var(--hair);">
            <div style="font-size:10px; font-weight:700; color:var(--dim); letter-spacing:0.05em; margin-bottom:5px;">COMPETITIVE, MARKET, BUSINESS, REGULATORY &mdash; NOT PRODUCED</div>
            <div style="font-size:11px; color:var(--text3); line-height:1.6;">Depth is Light. None of these could change whether or how we build an internal console, and a threat that would not change the decision does not belong on this list. This section is deliberately short: it is not a risk register.</div>
          </div>
        </div>'''))

    q7 = _q(7, "What does the company recommend?", "recommend", accent_inset=True,
            border="oklch(78% 0.14 75 / 0.5)", bg="oklch(78% 0.14 75 / 0.05)", answer_html='''
        <b style="color:var(--text);">Proceed with narrowed scope: build the one-glance screen, and do not commit to the ellipse yet.</b>
        First, one screen whose subject is the build &mdash; what the factory is making, which of the six gates it has passed, whose turn it is, what is stopping it &mdash; honest about what the records cannot support.
        Postponed on purpose: motion, percentages, and the ring geometry itself, until one real build has run through and we know what actually moves.''',
            expander=("sections 9, 10 and 12", '''
        <div class="inset-k">Expanded &middot; sections 9, 10 and 12</div>
        <div style="font-size:10px; font-weight:700; color:var(--accent); letter-spacing:0.05em; margin-bottom:6px;">9 &middot; WHY THIS AND NOT SOMETHING ELSE</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.6; margin-bottom:14px;">
          The outcome you named is &ldquo;understand within seconds&rdquo;. That is a legibility requirement, not a geometry requirement. Committing the shape in the brief would freeze the least certain decision at the moment we know least. One recommendation, not five options: build the screen, test the ring against alternatives during design, pick on evidence.
        </div>
        <div class="qrow" style="margin-bottom:14px;">
          <div>
            <div style="font-size:10px; font-weight:700; color:var(--green); letter-spacing:0.05em; margin-bottom:7px;">10 &middot; IN SCOPE NOW</div>
            <div style="font-size:11.5px; color:var(--text2); line-height:1.75;">One Build screen &middot; the six-stage gate ladder instead of a percentage &middot; last event and how long ago &middot; whose turn it is &middot; what is stuck and why &middot; the never-run state as a designed state &middot; a Team page &middot; every existing register still reachable, Meetings in at most two clicks</div>
          </div>
          <div>
            <div style="font-size:10px; font-weight:700; color:var(--text3); letter-spacing:0.05em; margin-bottom:7px;">10 &middot; NOT IN THE FIRST VERSION</div>
            <div style="font-size:11.5px; color:var(--text2); line-height:1.75;">The ellipse geometry as a commitment &middot; motion and live indicators (nothing writes them today) &middot; any percentage &middot; any dollar figure &middot; deleting any existing destination &middot; anything about the built app&rsquo;s own content, users or quality</div>
          </div>
        </div>
        <div style="padding-top:12px; border-top:1px solid var(--hair);">
          <div style="font-size:10px; font-weight:700; color:var(--text2); letter-spacing:0.05em; margin-bottom:7px;">12 &middot; ALTERNATIVES WORTH CONSIDERING &mdash; TWO</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6; margin-bottom:8px;"><b style="color:var(--prose);">Fix the navigation instead of the screen.</b> What triggered this was not finding Meetings in a thirteen-item bar. A shorter bar and one grouped menu is a fraction of the work. We do not recommend it as the whole answer &mdash; it does not turn reading into looking &mdash; but it is worth doing either way, and it is cheap.</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">Wait for one real end-to-end build first.</b> The screen designs itself once something has actually run through it. Cost: delay. Benefit: no screen built around imagined activity.</div>
          <div style="font-size:10.5px; color:var(--dim); line-height:1.5; margin-top:9px;">Two, not three. We are not adding a third to look thorough.</div>
        </div>'''))

    q8 = _q(8, "What assumptions did the company make?", "think", rule="var(--violet)", answer_html='''
        Two that could change the answer. That <b style="color:var(--text);">&ldquo;as simple as a dashboard&rdquo; means fewer things on one screen, not fewer capabilities behind it</b> &mdash; so today&rsquo;s registers move behind one menu rather than being deleted. And that <b style="color:var(--text);">&ldquo;track flow&rdquo; means work moving through our own gates</b>, with a build as the unit on the screen, not an agent. Both are correctable in one click if we have them wrong.''',
            expander=("section 11", '''
        <div class="inset-k">Expanded &middot; section 11 &middot; important assumptions</div>
        <div style="display:flex; flex-direction:column; gap:10px;">
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">Simplify means consolidate, not delete.</b> If you meant delete, the scope shrinks and several records stop being reachable &mdash; a materially different brief.</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">The unit on the screen is a build, not an agent.</b> If you want to watch agents rather than work, this is a different screen with different data behind it.</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">You will keep using this yourself.</b> One user, one machine. No multi-user, no permissions, no sharing was designed for. If that is wrong, say so before we build.</div>
          <div style="font-size:10.5px; color:var(--dim); line-height:1.5; padding-top:8px; border-top:1px solid var(--hair);">Three, and no more. Assumptions that could not change the result &mdash; font choice, page title, where the menu sits &mdash; are ours to make and are not listed here.</div>
        </div>'''))

    q9_extra = '''
      <div style="display:flex; flex-direction:column; gap:10px; margin-top:12px;">
        <div class="card">
          <div style="font-size:12.5px; font-weight:600; color:var(--text); margin-bottom:5px;">1 &mdash; Is the subject of this screen the factory, or the app the factory builds?</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">What changes:</b> the factory, and the screen shows stages, owners and stalls, and we can build it now. The app being built, and the screen has almost nothing to show &mdash; <span class="mono" style="font-size:11px;">projects</span> holds one row, this ops system itself, so the factory has never built an app.</div>
        </div>
        <div class="card">
          <div style="font-size:12.5px; font-weight:600; color:var(--text); margin-bottom:5px;">2 &mdash; Is the ellipse a requirement, or your sketch of one?</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">What changes:</b> a sketch, and Design tests the ring against two or three other forms and picks on evidence. A requirement, and we build the ring first and accept that there may be very little to put on it.</div>
        </div>
      </div>'''
    q9 = _q(9, "What decisions do you need from me?", "need", border="oklch(78% 0.14 75 / 0.5)",
            extra_html=q9_extra, answer_html='''
        Two. Both would produce a different brief depending on how you answer, which is the only reason either is here.
        <b style="color:var(--text);">You can approve without answering them</b> &mdash; if you do, we proceed on the assumptions above and the brief will say so.''',
            expander=("section 13", '''
        <div class="inset-k">Expanded &middot; section 13 &middot; what we did not ask you</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
          Five candidate questions were written and three were deleted, because two honest answers to them produce the same brief: which colours to use, whether the menu sits left or top, and whether the Team page ships in the same release. Those are ours to decide, and asking you would have been decoration.
          A sixth &mdash; &ldquo;do you want the existing pages kept?&rdquo; &mdash; became assumption 1 instead, because we can state the likelier answer and let you correct it in one click. The cap is three questions; we are asking two.
        </div>'''))

    q10 = _q(10, "How will we know we succeeded?", "recommend", rule="var(--accent)", answer_html='''
        You open one screen and, without clicking, can say what the factory is making, which of the six gates it has passed, whose turn it is, and what is stopping it. Nothing on the screen is a number the records cannot support. A factory that has never run renders as a designed state, not an empty grid. And Meetings &mdash; the page you could not find &mdash; is reachable in at most two clicks.''',
             expander=("section 14", '''
        <div class="inset-k">Expanded &middot; section 14 &middot; concrete enough for the people who build it</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.75;">
          Each of these can be checked by looking at the screen against today&rsquo;s database, with no outside knowledge:
          the four facts above are legible without a click &middot;
          no percentage appears anywhere while <span class="mono" style="font-size:11px;">task_steps</span> covers 1 of 24 tasks &middot;
          no dollar figure appears while <span class="mono" style="font-size:11px;">agent_runs</span> carries 0 costs &middot;
          no live-agent indicator appears while nothing writes one &middot;
          a passed gate with no handoff, review or QA record renders &ldquo;no record kept&rdquo; rather than a tick &middot;
          the zero-apps-built state is a drawn state, not an empty container &middot;
          Meetings is reachable in two clicks and renders &ldquo;no meetings have been held&rdquo; against 0 rows.
        </div>'''))

    body = (_said_strip() + '<div style="display:flex; flex-direction:column; gap:12px;">'
            + q4 + q5 + q6 + q7 + q8 + q9 + q10 + "</div>" + _company_view())
    return head + body + _next_link("stage-5", "Now decide &mdash; your three options")


# ---------------------------------------------------------------------------
# Stage 5 — FOUNDER REVIEW (S5Review.dc.html)
# ---------------------------------------------------------------------------

_PICK_DETAIL = {
    "none": ("Pick one above to see exactly what it does, what it costs and what it leaves behind.", None, ""),
    "edit": ("Edit / Correct &mdash; the brief opens for editing. You change any line of our reading. No model is invoked, "
             "no <span class=\"mono\">agent_runs</span> row is written, nothing is spent. The result is version 2, authored by you, and every later screen says "
             "&ldquo;edited by you&rdquo; on the lines you touched. Your original idea is untouched: it is not editable by anyone, ever.",
             "stage-6.html?view=edit", "Open the edit screen &rarr;"),
    "recon": ("Reconsider &mdash; a text box opens and asks what we got wrong. Your words are stored verbatim, attributed to you, "
              "and handed to round 2 as the thing to answer. This runs the full company round again and spends real money, which is why "
              "the cost warning sits on the control itself and not in a paragraph somewhere above it. Round 1 is kept and stays readable forever.",
              "stage-6.html?view=recon", "Open the reconsider screen &rarr;"),
    "approve": ("Approve Brief &mdash; this version becomes the approved brief. Nothing is dispatched, nothing is spent, no status moves beyond "
                "the approval itself. Approving is a complete outcome: you can stop here and start work next week. What approval does mean is that "
                "from the moment work starts, every agent downstream reads this and not your original sentence.",
                "stage-7.html", "Open the approval screen &rarr;"),
}


def _stage5(params: dict) -> str:
    pick = params.get("pick", "none")
    if pick not in _PICK_DETAIL:
        pick = "none"

    def card(key: str, title: str, badge: str, badge_color: str, body: str, foot: str, sel_color: str) -> str:
        selected = pick == key
        bd = sel_color if selected else "var(--border)"
        bg = "#171b21" if selected else "var(--panel)"
        return f'''
    <a href="stage-5.html?pick={key}" style="display:block; border-radius:12px; border:1px solid {bd}; background:{bg}; padding:16px 18px;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:9px; gap:10px;">
        <div style="font-size:13.5px; font-weight:600; color:var(--text);">{e(title)}</div>
        <div class="pill" style="background:{badge_color}; color:{sel_color}; font-size:9.5px; letter-spacing:0.04em;">{e(badge)}</div>
      </div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">{body}</div>
      <div style="font-size:10.5px; color:var(--dim); margin-top:9px; line-height:1.5;">{foot}</div>
    </a>'''

    cards = (
        card("edit", "Edit / Correct", "FREE", "var(--green-soft)",
             "You change the words yourself. No agent runs, nothing is spent. The result is a new version <b style=\"color:var(--prose);\">authored by you</b>, and the record says so.",
             "Your original idea is not editable, by you or anyone. Only our reading of it is.", "var(--green)")
        + card("recon", "Reconsider", "COSTS AGAIN", "oklch(78% 0.14 75 / 0.16)",
               "You tell us what we got wrong and the company re-evaluates &mdash; interpretation, assumptions, evaluation, recommendation or scope. <b style=\"color:var(--prose);\">This runs a full new round and spends real money.</b>",
               "It needs your feedback to be worth anything. Sending it back empty buys you round 2 saying round 1 again, at full price.", "var(--accent)")
        + card("approve", "Approve Brief", "FREE", "var(--green-soft)",
               "You accept this version as the brief. <b style=\"color:var(--prose);\">It starts no work</b> and spends nothing. Starting work is a separate decision you can make now, later, or never.",
               "Approving is a complete outcome on its own. Nothing times out and nothing auto-approves &mdash; silence is not consent.", "var(--green)"))

    detail_text, detail_href, detail_label = _PICK_DETAIL[pick]
    detail_link = (f'<div style="margin-top:10px;"><a href="{e(detail_href)}" style="color:var(--accent); font-size:11.5px; font-weight:600;">{detail_label}</a></div>'
                   if detail_href else "")

    head = _stage_head(5, "Founder review", "Your call",
                       "Round 1 &middot; version 1. Nothing is approved and nothing has started. "
                       "<b style=\"color:var(--text2);\">Walking away decides nothing, spends nothing and loses nothing</b> &mdash; "
                       "the idea and this reading both stay where they are.")

    body = f'''
{_said_strip()}
<div style="display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-bottom:20px;">{cards}</div>

<div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:14px 18px; margin-bottom:22px;">
  <div style="font-size:12px; color:var(--text2); line-height:1.65;"><b style="color:var(--text);">{detail_text}</b></div>
  {detail_link}
</div>

<div class="label" style="margin-bottom:4px;">Design states &middot; the questions block</div>
<div style="font-size:11.5px; color:var(--text3); margin-bottom:13px; line-height:1.55; max-width:860px;">Zero questions is a legitimate and common outcome, so it is a drawn state rather than an empty container. Both renderings are shown here; only one appears in the product at a time.</div>

<div class="qrow" style="gap:14px;">
  <div class="panel" style="border-color:oklch(78% 0.14 75 / 0.45); padding:16px 18px;">
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:11px; gap:10px;">
      <div style="font-size:12.5px; font-weight:600;">When there are questions</div>
      <div class="pill" style="background:oklch(78% 0.14 75 / 0.16); color:var(--accent); font-size:9.5px; letter-spacing:0.05em;">WE NEED FROM YOU</div>
    </div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.6; margin-bottom:11px;">Two here. Each one states, in a line, what changes depending on your answer &mdash; a question that cannot say that is decoration and gets deleted before you see it. Cap of three.</div>
    <div class="card" style="border-radius:9px; margin-bottom:8px;">
      <div style="font-size:11.5px; font-weight:600; color:var(--text);">Is the subject the factory, or the app it builds?</div>
      <div style="font-size:10.5px; color:var(--text2); margin-top:4px; line-height:1.5;">Changes what we build first, and whether there is anything to show at all.</div>
    </div>
    <div class="card" style="border-radius:9px;">
      <div style="font-size:11.5px; font-weight:600; color:var(--text);">Is the ellipse a requirement, or a sketch?</div>
      <div style="font-size:10.5px; color:var(--text2); margin-top:4px; line-height:1.5;">Changes whether Design tests forms, or builds the one you drew.</div>
    </div>
    <div style="font-size:10.5px; color:var(--dim); margin-top:10px; line-height:1.5;">You can approve without answering either. The brief then records the assumption we proceeded on.</div>
  </div>

  <div class="panel" style="padding:16px 18px;">
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:11px; gap:10px;">
      <div style="font-size:12.5px; font-weight:600;">When there are none &mdash; the honest zero</div>
      <div class="pill" style="background:var(--green-soft); color:var(--green); font-size:9.5px; letter-spacing:0.05em;">NOTHING NEEDED</div>
    </div>
    <div style="border-radius:9px; border:1px dashed var(--border2); background:var(--inset); padding:16px 14px;">
      <div style="font-size:12.5px; color:var(--text); line-height:1.6; margin-bottom:8px;">We have nothing to ask you.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">Everything we were unsure about, we could state as an assumption you can correct in one click &mdash; so we did that instead of making you answer questions. The assumptions are in answer 8.</div>
    </div>
    <div style="font-size:10.5px; color:var(--dim); margin-top:11px; line-height:1.55;">
      This is a pass, not a gap. A round that manufactures a question to look thorough has failed. If we ever ask you eight things, the right response is to distrust the round.
    </div>
  </div>
</div>'''
    return head + body + _next_link(
        "stage-6", "Send it back with feedback &mdash; see what that does",
        "Next: correction and reconsideration.")


# ---------------------------------------------------------------------------
# Stage 6 — CORRECTION / RECONSIDERATION (S6Reconsider.dc.html)
# ---------------------------------------------------------------------------


def _stage6(params: dict) -> str:
    view = params.get("view", "recon")
    if view not in ("recon", "round2", "edit", "edited"):
        view = "recon"
    on_recon = view in ("recon", "round2")

    def tab(key: str, label: str) -> str:
        active = (key == "recon") == on_recon
        bd = "var(--accent)" if active else "var(--border)"
        bg = "var(--accent-soft)" if active else "var(--panel)"
        fg = "var(--accent)" if active else "var(--text2)"
        return (f'<a href="stage-6.html?view={key}" style="padding:8px 15px; border-radius:8px; border:1px solid {bd}; '
                f'background:{bg}; color:{fg}; font-size:12px; font-weight:600;">{label}</a>')

    tabs = ('<div style="display:flex; gap:8px; margin-bottom:18px; flex-wrap:wrap;">'
            + tab("recon", "Reconsider &mdash; the company re-evaluates")
            + tab("edit", "Edit / Correct &mdash; you change the words") + "</div>")

    if view == "recon":
        content = f'''
<div style="display:grid; grid-template-columns:minmax(0,1.45fr) minmax(0,1fr); gap:16px; align-items:start;">
  <div class="panel" style="border-color:oklch(78% 0.14 75 / 0.5); padding:18px 20px;">
    <div class="label" style="margin-bottom:8px;">Tell us what we got wrong</div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.6; margin-bottom:12px;">
      This is the only thing round 2 has that round 1 did not. Without it we would re-run the same reasoning on the same input and hand you the same answer, at the same price.
    </div>
    <div style="border-radius:8px; border:1px solid oklch(78% 0.14 75 / 0.45); background:var(--inset); padding:13px 14px; min-height:92px;">
      <div style="font-size:12.5px; line-height:1.7; color:var(--text); white-space:pre-wrap;">{e(FEEDBACK)}</div>
      <div style="height:15px; width:1.5px; background:var(--accent); margin-top:2px;"></div>
    </div>
    <div style="font-size:10.5px; color:var(--dim); margin-top:7px;">Stored exactly as typed, attributed to you, and kept beside round 2 forever &mdash; so &ldquo;why did the answer change?&rdquo; always has an answer.</div>
    <div style="margin-top:16px; padding-top:15px; border-top:1px solid var(--border);">
      <a href="stage-6.html?view=round2" style="padding:10px 18px; border-radius:8px; background:var(--accent); color:var(--ink-accent); font-weight:700; font-size:12.5px; display:inline-block;">Send back for round 2 &mdash; this spends again</a>
      <div style="font-size:11px; color:var(--text3); margin-top:9px; line-height:1.55;">The cost warning is on the button, not in a paragraph above it. Round 1 is not replaced &mdash; it stays readable, with its evaluation intact.</div>
    </div>
  </div>
  <div class="panel" style="padding:18px;">
    <div class="label" style="margin-bottom:10px;">Rounds so far</div>
    <div style="display:flex; flex-direction:column; gap:9px;">
      <div style="display:flex; gap:10px; align-items:flex-start;">
        <div class="mono" style="font-size:11px; color:var(--violet); font-weight:700; flex-shrink:0;">v1</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.55;">Round 1 &middot; the company &middot; 1 Sep 20:0x &mdash; still readable, always.</div>
      </div>
      <div style="display:flex; gap:10px; align-items:flex-start;">
        <div class="mono" style="font-size:11px; color:var(--dim); font-weight:700; flex-shrink:0;">v2</div>
        <div style="font-size:11.5px; color:var(--dim); line-height:1.55;">Round 2 &mdash; not run yet. It will cost what round 1 cost.</div>
      </div>
    </div>
    <div style="margin-top:14px; padding-top:13px; border-top:1px solid var(--border); font-size:11px; color:var(--text2); line-height:1.6;">
      Rounds are numbered and visible. There is no cap on them, and from round 3 this panel will say the honest thing: <i style="color:var(--prose);">another round costs again &mdash; it may be cheaper to approve and correct downstream.</i> It will not stop you.
    </div>
    <div style="margin-top:12px; font-size:10.5px; color:var(--dim); line-height:1.55;">
      Still no cost estimate: 0 of 13 recorded runs carries a figure.
      <span class="ph" style="display:inline-block; margin-top:5px;">[ per-round maximum &mdash; not yet computable ]</span>
    </div>
  </div>
</div>'''
    elif view == "round2":
        deltas = [
            ("CLOSED", "var(--green)", "var(--green-soft)",
             '<b style="color:var(--text);">Question 1 is answered.</b> The subject is the factory, not the app it builds. Recorded as <b style="color:var(--text);">your answer</b>, not as our assumption &mdash; the difference matters when someone asks later why we built it this way.'),
            ("SHARPER", "var(--blue)", "var(--blue-soft)",
             '<b style="color:var(--text);">The interpretation now names the boundary.</b> The subject is <i>the build</i>. The app the factory produces is a child with its own unrelated interface, and this screen never renders anything about that app&rsquo;s content, users or quality &mdash; only that it exists and how far along it is.'),
            ("NEW", "var(--red)", "var(--red-soft)",
             '<b style="color:var(--text);">A threat we missed in round 1.</b> Once the subject is fixed as the factory, the empty case becomes the normal case: <span class="mono" style="font-size:11.5px;">projects</span> holds one row &mdash; this ops system building itself. The factory has never built an app. The never-run state stops being an edge case and becomes a designed state.'),
            ("SAME", "var(--text2)", "var(--panel2)",
             '<b style="color:var(--prose);">The recommendation did not change direction</b> &mdash; still <i>proceed with narrowed scope</i>, and the scope narrowed again. We are telling you what did <i>not</i> move as well as what did; a round that reports only changes is easy to misread as agreement.'),
            ("OPEN", "var(--accent)", "oklch(78% 0.14 75 / 0.16)",
             '<b style="color:var(--text);">One question is still open</b> &mdash; whether the ellipse is a requirement or a sketch. You did not answer it and we did not quietly decide it for you.'),
        ]
        delta_html = "".join(f'''
        <div style="display:flex; gap:11px; align-items:flex-start;">
          <div style="padding:1px 7px; border-radius:5px; background:{bg}; color:{fg}; font-size:9.5px; font-weight:700; flex-shrink:0; margin-top:2px;">{e(tag)}</div>
          <div style="font-size:12px; color:var(--prose); line-height:1.6;">{text}</div>
        </div>''' for tag, fg, bg, text in deltas)
        content = f'''
<div class="panel" style="border-color:oklch(72% 0.12 250 / 0.45); padding:18px 20px; margin-bottom:16px; border-left:3px solid var(--blue);">
  <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:11px; gap:12px; flex-wrap:wrap;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.07em; color:var(--blue); text-transform:uppercase;">Round 2 &middot; what your feedback changed</div>
    <div style="font-size:10.5px; color:var(--dim);">the company &middot; v2 &middot; round 1 kept</div>
  </div>
  <div style="display:flex; flex-direction:column; gap:11px;">{delta_html}</div>
</div>
<div class="qrow" style="gap:14px;">
  <div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:15px 17px;">
    <div class="label" style="margin-bottom:9px;">The record, after two rounds</div>
    <div style="display:flex; flex-direction:column; gap:8px;">
      <div style="font-size:11.5px; color:var(--text2); line-height:1.55;"><b style="color:var(--gray);">Your idea</b> &mdash; unchanged, byte for byte, since 20:03 UTC.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.55;"><b style="color:var(--violet);">v1</b> &mdash; round 1, the company. Readable, with its evaluation and its two questions intact.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.55;"><b style="color:var(--dim);">Your feedback</b> &mdash; stored verbatim between them, so the change has a cause.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.55;"><b style="color:var(--blue);">v2</b> &mdash; round 2, the company. Nothing was overwritten to make it.</div>
    </div>
  </div>
  <div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:15px 17px;">
    <div class="label" style="margin-bottom:9px;">What this round cost</div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">
      Two rounds have now been paid for. This product still cannot tell you the amount &mdash; 0 of 13 recorded agent runs carries a cost figure &mdash; and it is not going to invent one to fill the space.
    </div>
    <div style="font-size:11px; color:var(--text3); line-height:1.55; margin-top:10px;">What it can tell you honestly: the count of rounds, that each one spent, and that a Light round costs less than a Full one.</div>
  </div>
</div>'''
    else:  # edit / edited
        saved = view == "edited"
        saved_html = '''
<div style="margin-top:14px; border-radius:12px; border:1px solid oklch(72% 0.15 150 / 0.5); background:var(--green-soft); padding:15px 18px;">
  <div style="font-size:12.5px; font-weight:600; margin-bottom:5px;">Version 3 saved &mdash; authored by you.</div>
  <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">v1 and v2 are unchanged and still readable. Nothing was spent. The line you added is marked as yours wherever it appears from here on, including in what downstream agents receive.</div>
  <div style="margin-top:12px;"><a href="stage-7.html" style="padding:8px 16px; border-radius:8px; border:1px solid var(--accent); color:var(--accent); font-weight:600; font-size:12px; display:inline-block;">Go to approval</a></div>
</div>''' if saved else ""
        save_control = ("" if saved else '''
      <div style="display:flex; align-items:center; gap:11px; margin-top:16px; padding-top:15px; border-top:1px solid var(--border); flex-wrap:wrap;">
        <a href="stage-6.html?view=edited" style="padding:9px 18px; border-radius:8px; background:var(--green); color:var(--ink-green); font-weight:700; font-size:12.5px;">Save as version 3 &mdash; authored by you</a>
        <div style="font-size:11px; color:var(--text3);">No model is invoked. Zero <span class="mono">agent_runs</span> rows are written.</div>
      </div>''')
        content = f'''
<div class="panel" style="border-color:oklch(72% 0.15 150 / 0.45); padding:18px 20px; margin-bottom:14px;">
  <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:12px; gap:12px; flex-wrap:wrap;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.07em; color:var(--green); text-transform:uppercase;">You are editing the company&rsquo;s words</div>
    <div style="font-size:10.5px; color:var(--dim);">no agent runs &middot; nothing spent</div>
  </div>
  <div style="font-size:10px; font-weight:700; color:var(--text3); letter-spacing:0.05em; margin-bottom:7px;">SECTION 14 &middot; DEFINITION OF SUCCESS</div>
  <div style="border-radius:9px; border:1px solid var(--border2); background:var(--inset); padding:13px 14px;">
    <div style="font-size:11.5px; color:var(--text3); line-height:1.7; margin-bottom:9px;">You open one screen and, without clicking, can say what the factory is making, which of the six gates it has passed, whose turn it is, and what is stopping it. Nothing on the screen is a number the records cannot support&hellip;</div>
    <div style="border-left:2px solid var(--green); padding-left:11px; font-size:12px; color:var(--text); line-height:1.7;">
      The meeting room is still there and I can find it &mdash; it exists today and I could not find it, which is what started this.
      <span style="height:14px; width:1.5px; background:var(--green); display:inline-block; vertical-align:middle; margin-left:2px;"></span>
    </div>
    <div style="font-size:10px; font-weight:700; color:var(--green); letter-spacing:0.05em; margin-top:8px;">ADDED BY YOU</div>
  </div>
  {save_control}
</div>
<div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:15px 18px;">
  <div style="font-size:12px; color:var(--text2); line-height:1.65;">
    <b style="color:var(--text);">Why an edit gets your name on it.</b> A version the company wrote and a version you rewrote are different things, and the whole point of keeping three artifacts is being able to tell them apart later.
    Crediting your edit to the company would corrupt the one question this record exists to answer.
    <b style="color:var(--text);">And an edit never reaches your original idea</b> &mdash; that text has no edit path anywhere in the product, for anyone.
  </div>
</div>{saved_html}'''

    head = _stage_head(6, "Correction / reconsideration", "Two ways to put it right",
                       "One costs nothing and is your words. The other costs a full round and is the company thinking again. "
                       "The objective is correct understanding, not more ideas.")
    # The artboard gives the round-2 result its own forward control ("Read v2
    # and decide"); the other views share the generic one.
    fwd_label = "Read v2 and decide" if view == "round2" else "Continue to Founder approval"
    return head + _said_strip() + tabs + content + _next_link(
        "stage-7", fwd_label, "Next: Founder approval.")


# ---------------------------------------------------------------------------
# Stage 7 — FOUNDER APPROVAL (S7Approval.dc.html)
# ---------------------------------------------------------------------------


def _stage7(params: dict) -> str:
    done = params.get("done") == "1"
    approved_html = '''
      <div style="margin-top:16px; border-radius:10px; border:1px solid oklch(72% 0.15 150 / 0.55); background:var(--green-soft); padding:14px 16px;">
        <div style="font-size:13px; font-weight:600; margin-bottom:5px;">Approved. v3 is the brief.</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">No agent was dispatched, nothing was spent, and no work has begun. <b style="color:var(--text);">Start Work is now available and is a separate decision.</b></div>
        <div style="margin-top:11px;"><a href="stage-8.html" style="padding:8px 16px; border-radius:8px; border:1px solid var(--accent); color:var(--accent); font-weight:600; font-size:12px; display:inline-block;">See the approved brief</a></div>
      </div>''' if done else ""
    controls = ("" if done else '''
      <div style="display:flex; align-items:center; gap:11px; margin-top:18px; padding-top:16px; border-top:1px solid var(--border); flex-wrap:wrap;">
        <a href="stage-7.html?done=1" style="padding:10px 20px; border-radius:8px; background:var(--green); color:var(--ink-green); font-weight:700; font-size:13px;">Approve v3 as the brief</a>
        <a href="stage-6.html" style="padding:10px 18px; border-radius:8px; background:var(--panel2); border:1px solid var(--border2); color:var(--text2); font-size:12.5px;">Not yet &mdash; go back</a>
      </div>''')

    head = _stage_head(7, "Founder approval", "Approve this understanding",
                       "You are approving <b style=\"color:var(--text2);\">a specific version</b>, not an idea in general. "
                       "Which version is on the record, and it is the one every agent downstream will read.")

    body = f'''
{_said_strip()}
<div style="display:grid; grid-template-columns:minmax(0,1.35fr) minmax(0,1fr); gap:16px; align-items:start;">
  <div class="panel" style="border-color:oklch(72% 0.15 150 / 0.5); padding:20px;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--green); text-transform:uppercase; margin-bottom:12px;">You are about to approve</div>
    <div class="card" style="margin-bottom:16px;">
      <div style="display:flex; align-items:baseline; gap:9px; margin-bottom:7px; flex-wrap:wrap;">
        <div class="mono" style="font-size:12px; color:var(--green); font-weight:700;">v3</div>
        <div style="font-size:12.5px; font-weight:600;">TASK-026 &mdash; round 2, with your edit</div>
      </div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">The company&rsquo;s round-2 reading, plus the one line you added to the definition of success. v1, v2 and your feedback all stay readable.</div>
    </div>
    <div style="display:grid; grid-template-columns:auto 1fr; gap:11px 14px; align-items:baseline; font-size:12px; line-height:1.65;">
      <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--green);">does</div>
      <div style="color:var(--prose);">Marks v3 as the approved brief. From this moment there is an answer to &ldquo;what did the Founder actually agree to?&rdquo;</div>
      <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--text3);">does not</div>
      <div style="color:var(--prose);"><b style="color:var(--text);">Start any work. Spend any money. Dispatch any agent.</b> Approving is a complete outcome on its own &mdash; you can stop here and start next week.</div>
      <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--text3);">later</div>
      <div style="color:var(--prose);">When work does start, every agent &mdash; Product, Design, CTO, Red Team, Developer, Code Review, QA, Security &mdash; is given <i>this</i>, not your original sentence. Your sentence travels with it, labelled as context.</div>
      <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--accent);">open</div>
      <div style="color:var(--prose);">One question is unanswered &mdash; whether the ellipse is a requirement. <b style="color:var(--text);">Approving with it open is allowed</b>; the brief will record that we proceeded on our stated assumption, in your name.</div>
    </div>
    {controls}{approved_html}
  </div>

  <div style="display:flex; flex-direction:column; gap:14px;">
    <div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:17px;">
      <div class="label" style="margin-bottom:10px;">Nothing here approves itself</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
        There is no timeout, no default and no path by which a brief becomes approved because nobody looked at it. If you never click, it is never approved. <b style="color:var(--prose);">Silence is not consent</b>, and there is no code path in this product that treats it as consent.
      </div>
    </div>
    <div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:17px;">
      <div class="label" style="margin-bottom:10px;">What you are not being asked to do</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
        Approving is not agreeing that every sentence is perfect. It is saying <i style="color:var(--prose);">this is close enough to what I meant that building from it is not a waste.</i> Anything still wrong is cheaper to fix now than after &mdash; but not everything has to be right for this to be worth approving.
      </div>
    </div>
    <div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:17px;">
      <div class="label" style="margin-bottom:10px;">Reversibility, honestly</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
        Approval itself is a record, not an action, so it costs nothing to have made. What is <b style="color:var(--prose);">not</b> reversible is what comes after it &mdash; and that is the next screen, behind its own deliberate decision.
      </div>
    </div>
  </div>
</div>'''
    return head + body + _next_link("stage-8", "See the approved brief &rarr;")


# ---------------------------------------------------------------------------
# Stage 8 — APPROVED BRIEF (S8ApprovedBrief.dc.html)
# ---------------------------------------------------------------------------

_LADDER = [
    ("v1", "v1 &middot; round 1 &middot; company", "var(--accent)", "oklch(78% 0.14 75 / 0.14)",
     "Round 1, written by the company. Two open questions, Light depth, Product &middot; CTO &middot; Red Team. Still readable in full, with its evaluation and its labels intact &mdash; nothing about it was changed when v2 was made."),
    ("fb", "your feedback", "var(--accent)", "oklch(78% 0.14 75 / 0.14)",
     "Your feedback, stored verbatim between the two rounds and attributed to you &mdash; the words that answered question 1 and settled the subject as the factory rather than the app. This is why v2 differs from v1, and it is kept so that question always has an answer."),
    ("v2", "v2 &middot; round 2 &middot; company", "var(--accent)", "oklch(78% 0.14 75 / 0.14)",
     "Round 2, written by the company after your feedback. One question closed by your answer, one threat added, the scope narrowed. v1 was not touched to make it."),
    ("v3", "v3 &middot; your edit &middot; APPROVED", "var(--green)", "var(--green-soft)",
     "Your edit of v2 &mdash; one line added to the definition of success. Authored by you, zero agent runs, nothing spent. This is the version the approval points at."),
]


def _stage8(params: dict) -> str:
    sel = params.get("sel", "v3")
    if sel not in {k for k, _, _, _, _ in _LADDER}:
        sel = "v3"
    pills = "".join(
        f'<a href="stage-8.html?sel={k}" class="mono" style="padding:5px 12px; border-radius:100px; '
        f'border:1px solid {c if sel == k else "var(--border2)"}; background:{bgc if sel == k else "var(--panel)"}; '
        f'color:{c if sel == k else "var(--text2)"}; font-size:10.5px; font-weight:700;">{label}</a>'
        for k, label, c, bgc, _ in _LADDER)
    note = next(n for k, _, _, _, n in _LADDER if k == sel)

    head = _stage_head(8, "Approved brief", "What you approved",
                       "A different kind of thing from the reading it came from &mdash; and it looks different on purpose. "
                       "This is the company&rsquo;s instruction now.")

    body = f'''
<div style="display:grid; grid-template-columns:minmax(0,0.72fr) minmax(0,1.5fr); gap:16px; align-items:start; margin-bottom:18px;">
  {_said_panel("1 Sep 2026 20:03 UTC. Unchanged through two company rounds, one piece of your feedback, one edit of yours and one approval. It will still be here, in these words, when the work is finished.")}

  <div style="border-radius:14px; border:2px solid oklch(72% 0.15 150 / 0.7); background:var(--panel); padding:0; overflow:hidden;">
    <div style="background:oklch(72% 0.15 150 / 0.1); border-bottom:1px solid oklch(72% 0.15 150 / 0.35); padding:13px 18px; display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
      <div style="display:flex; align-items:center; gap:9px;">
        <div style="width:8px; height:8px; border-radius:50%; background:var(--green);"></div>
        <div style="font-size:10.5px; font-weight:700; letter-spacing:0.08em; color:var(--green); text-transform:uppercase;">You approved</div>
      </div>
      <div class="mono" style="font-size:10.5px; color:var(--text2);">v3 &middot; approved by you &middot; 1 Sep 2026 20:41 UTC</div>
    </div>
    <div style="padding:17px 18px;">
      <div style="font-size:10px; font-weight:700; color:var(--text3); letter-spacing:0.05em; margin-bottom:6px;">THE OUTCOME</div>
      <div style="font-size:12.5px; color:var(--text); line-height:1.7; margin-bottom:14px;">Open the AI Factory and understand within seconds how each child product is progressing, without reading internal task records. The subject is the build, not the thing being built.</div>
      <div style="font-size:10px; font-weight:700; color:var(--accent); letter-spacing:0.05em; margin-bottom:6px;">THE DIRECTION</div>
      <div style="font-size:12.5px; color:var(--prose); line-height:1.7; margin-bottom:14px;">Proceed with narrowed scope. One Build screen plus a Team page; the six-stage gate ladder rather than a percentage; last event, whose turn, what is stuck. The ellipse geometry is not committed &mdash; Design tests forms and picks on evidence.</div>
      <div class="qrow" style="gap:14px; margin-bottom:14px;">
        <div>
          <div style="font-size:10px; font-weight:700; color:var(--green); letter-spacing:0.05em; margin-bottom:5px;">IN SCOPE NOW</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.7;">The Build screen &middot; gate ladder &middot; last event and elapsed &middot; owner &middot; stuck reason &middot; the never-run state as a designed state &middot; Team page &middot; every record still reachable, Meetings in two clicks</div>
        </div>
        <div>
          <div style="font-size:10px; font-weight:700; color:var(--text3); letter-spacing:0.05em; margin-bottom:5px;">NOT IN THE FIRST VERSION</div>
          <div style="font-size:11.5px; color:var(--text2); line-height:1.7;">Ellipse geometry as a commitment &middot; motion &middot; percentages &middot; dollar figures &middot; live-agent indicators &middot; deleting any destination &middot; anything about the child app&rsquo;s own content</div>
        </div>
      </div>
      <div class="card" style="border-radius:9px; margin-bottom:12px;">
        <div style="font-size:10px; font-weight:700; color:var(--green); letter-spacing:0.05em; margin-bottom:6px;">YOUR OWN WORDS IN THIS BRIEF</div>
        <div style="font-size:11.5px; color:var(--prose); line-height:1.6;">Two things here came from you, not from us: the subject is the factory and not the app it builds (<i>your answer to question 1</i>), and the meeting room stays findable (<i>your edit to the definition of success</i>). Both are marked as yours everywhere they appear.</div>
      </div>
      <div style="border-radius:9px; border:1px dashed oklch(78% 0.14 75 / 0.45); background:var(--inset); padding:12px 14px;">
        <div style="font-size:10px; font-weight:700; color:var(--accent); letter-spacing:0.05em; margin-bottom:6px;">APPROVED WITH ONE QUESTION STILL OPEN</div>
        <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">Whether the ellipse is a requirement. We proceed on the stated assumption that it is a sketch. Recorded here so nobody later reads this as your decision when it was ours.</div>
      </div>
    </div>
  </div>
</div>

<div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:18px 20px; margin-bottom:16px;">
  <div class="label" style="margin-bottom:4px;">Three things, kept apart on purpose</div>
  <div style="font-size:11.5px; color:var(--text2); line-height:1.6; margin-bottom:15px; max-width:820px;">Nothing here was ever overwritten to produce the next thing. Every row below can still be opened.</div>
  <div style="display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px;">
    <div style="border-radius:10px; border:1px solid var(--border); background:var(--panel); padding:13px 15px; border-top:3px solid var(--gray);">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--gray); text-transform:uppercase; margin-bottom:7px;">Raw founder idea</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">Written once, at intake, by you. <b style="color:var(--prose);">Write-once</b> &mdash; no edit path exists for it anywhere in this product. Historical context downstream, never the instruction.</div>
    </div>
    <div style="border-radius:10px; border:1px solid var(--border); background:var(--panel); padding:13px 15px; border-top:3px solid var(--blue);">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--blue); text-transform:uppercase; margin-bottom:7px;">Interpreted &amp; evaluated</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">Append-only. A new round makes a <b style="color:var(--prose);">new version</b>, never an edit. Three exist: v1 (company), v2 (company, after your feedback), v3 (you).</div>
    </div>
    <div style="border-radius:10px; border:1px solid oklch(72% 0.15 150 / 0.4); background:var(--panel); padding:13px 15px; border-top:3px solid var(--green);">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--green); text-transform:uppercase; margin-bottom:7px;">Approved brief</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">A pointer to <b style="color:var(--prose);">one specific version</b> &mdash; v3 &mdash; not a copy of it. A copy could drift from what you actually read when you clicked.</div>
    </div>
  </div>
  <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:15px; padding-top:14px; border-top:1px solid var(--border);">
    {pills}
    <div style="flex:1; min-width:260px; font-size:11px; color:var(--text2); line-height:1.55; align-self:center;">{note}</div>
  </div>
</div>

<div class="panel" style="border-color:oklch(78% 0.14 75 / 0.45); padding:18px 20px;">
  <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--accent); text-transform:uppercase; margin-bottom:11px;">What every agent will be given</div>
  <div class="qrow">
    <div style="border-radius:9px; border:1px solid oklch(72% 0.15 150 / 0.4); background:var(--panel2); padding:12px 14px;">
      <div style="font-size:10px; font-weight:700; color:var(--green); letter-spacing:0.05em; margin-bottom:6px;">THE INSTRUCTION</div>
      <div style="font-size:11.5px; color:var(--prose); line-height:1.6;">The approved brief, v3, in full. Product, Design, CTO, Red Team, Developer, Code Review, QA and Security all get the same one. None of them re-reads your sentence and decides for itself what it meant.</div>
    </div>
    <div style="border-radius:9px; border:1px solid var(--border2); background:var(--panel2); padding:12px 14px;">
      <div style="font-size:10px; font-weight:700; color:var(--gray); letter-spacing:0.05em; margin-bottom:6px;">BENEATH IT, LABELLED</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><i style="color:var(--prose);">&ldquo;Original idea as typed &mdash; context, not the specification.&rdquo;</i> Your words travel with the brief so the company never loses them, and are never handed over as the thing to build.</div>
    </div>
  </div>
  <div style="font-size:10.5px; color:var(--dim); line-height:1.6; margin-top:13px;">
    This is the rule most likely to be broken quietly, because the code that breaks it works. Two places feed your raw sentence into agent transcripts today.
  </div>
</div>'''
    return head + body + _next_link("stage-9", "Start work on this brief&hellip;")


# ---------------------------------------------------------------------------
# Stage 9 — START WORK (S9StartWork.dc.html)
#
# Arm -> confirm -> started, as two real steps: the first control is outlined
# and dispatches nothing (it only opens the second), the filled control
# appears exactly once, and after firing the control is REMOVED rather than
# disabled. Design review §6.
# ---------------------------------------------------------------------------


def _stage9(params: dict) -> str:
    step = params.get("step", "rest")
    if step not in ("rest", "confirm", "started"):
        step = "rest"

    if step == "rest":
        where = "Step 1 of 2 &mdash; armed nothing yet."
        panel = '''
<div class="panel" style="border-color:oklch(78% 0.14 75 / 0.5); padding:20px; max-width:880px;">
  <div style="display:flex; align-items:center; gap:9px; margin-bottom:12px; flex-wrap:wrap;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--accent); text-transform:uppercase;">Start work on TASK-026</div>
    <span class="pill" style="background:var(--accent-soft); color:var(--accent); letter-spacing:0.04em;">SPENDS MONEY</span>
  </div>
  <div style="font-size:12.5px; color:var(--prose); line-height:1.7; margin-bottom:16px;">
    The brief is approved and nothing is running. This control begins execution: agents pick the work up and carry it through the pipeline. It is the only control in this product that starts a multi-stage run on a click, so it does not do that on the first click.
  </div>
  <a href="stage-9.html?step=confirm" style="padding:10px 20px; border-radius:8px; background:transparent; border:1px solid var(--accent); color:var(--accent); font-weight:600; font-size:13px; display:inline-block;">Approve Brief &amp; Start Work&hellip;</a>
  <div style="font-size:11px; color:var(--text3); margin-top:11px; line-height:1.55;">Unfilled, and it ends in an ellipsis. In this product an unfilled button has never been the &ldquo;go&rdquo;. It arms; it dispatches nothing.</div>
</div>'''
    elif step == "confirm":
        where = "Step 2 of 2 &mdash; this is the only screen in the product with a filled button that spends."
        panel = f'''
<div class="panel" style="border-color:var(--accent); padding:22px; max-width:880px;">
  <div style="display:flex; align-items:center; gap:9px; margin-bottom:14px; flex-wrap:wrap;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--accent); text-transform:uppercase;">Confirm &mdash; start the company on TASK-026</div>
    <span class="pill" style="background:var(--accent-soft); color:var(--accent); letter-spacing:0.04em;">SPENDS MONEY</span>
  </div>
  <div class="card" style="margin-bottom:16px;">
    <div class="label" style="margin-bottom:7px;">What they will be told to build</div>
    <div style="font-size:12px; color:var(--text); line-height:1.6; margin-bottom:8px;"><b style="color:var(--green);">The approved brief, v3</b> &mdash; open the AI Factory and understand within seconds how each child product is progressing. Proceed with narrowed scope: one Build screen, gate ladder not percentage, no committed geometry.</div>
    <div style="border-left:2px solid var(--gray); padding-left:10px; font-size:11px; color:var(--text2); line-height:1.55; white-space:pre-wrap;">Beneath it, labelled as context, not the specification: &ldquo;{e(RAW_IDEA)}&rdquo;</div>
  </div>
  <div style="display:grid; grid-template-columns:auto 1fr; gap:10px 15px; align-items:baseline; margin-bottom:18px; font-size:12px; line-height:1.65;">
    <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--accent);">now</div>
    <div style="color:var(--prose);"><b style="color:var(--text);">Agents begin working.</b> Real model invocations start from this click.</div>
    <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--text3);">cost</div>
    <div style="color:var(--prose);"><b style="color:var(--text);">Real AI cost may be incurred, and there is no estimate.</b> 0 of the 13 agent runs on record carries a cost figure, so this product has no honest number to show you. It will appear on Costs as it accrues.
      <div style="margin-top:6px;"><span class="ph">[ enforced ceiling &mdash; computed from the real dispatch path; not yet wired ]</span></div>
    </div>
    <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--text3);">reads</div>
    <div style="color:var(--prose);">Every agent is given <b style="color:var(--text);">the approved brief</b> as the authoritative instruction. Your original sentence goes with it as labelled context and is not the specification.</div>
    <div class="mono" style="text-align:right; font-size:11px; font-weight:700; color:var(--red);">stop</div>
    <div style="color:var(--prose);"><b style="color:var(--text);">There is no stop button.</b> A dispatched stage runs to completion. Nothing in this product can interrupt it once it is away.</div>
  </div>
  <div style="display:flex; align-items:center; gap:10px; padding-top:16px; border-top:1px solid var(--border); flex-wrap:wrap;">
    <a href="stage-9.html?step=started" style="padding:10px 20px; border-radius:8px; background:var(--accent); color:var(--ink-accent); font-weight:700; font-size:12.5px;">Yes &mdash; start work on TASK-026 and spend</a>
    <a href="stage-9.html?step=rest" style="padding:10px 18px; border-radius:8px; background:var(--panel2); border:1px solid var(--border2); color:var(--text2); font-size:12.5px;">Cancel &mdash; the brief stays approved and nothing runs</a>
  </div>
  <div style="font-size:11px; color:var(--text3); margin-top:11px; line-height:1.55;">The filled button appears exactly once in this flow, on this screen, wearing a label that names the task and the spend. Cancelling loses nothing: the approval stands and this control is still here tomorrow. In this preview neither control dispatches anything &mdash; both are links to drawn screens.</div>
</div>'''
    else:
        where = "After-state &mdash; the control has been removed, not disabled."
        panel = '''
<div style="border-radius:14px; border:1px solid var(--accent); background:oklch(78% 0.14 75 / 0.07); padding:20px; max-width:880px;">
  <div style="display:flex; gap:12px; align-items:flex-start;">
    <div style="width:9px; height:9px; border-radius:50%; background:var(--accent); flex-shrink:0; margin-top:6px;"></div>
    <div>
      <div style="font-size:14px; font-weight:600; margin-bottom:6px;">Started. Product is working on TASK-026 now.</div>
      <div style="font-size:12px; color:var(--prose); line-height:1.7;">
        Dispatched at 20:47 UTC. Status moved <span class="mono" style="color:var(--text);">BACKLOG &rarr; PLANNING</span>, owner is now <b style="color:var(--text);">Product</b>, and the instruction it received is the approved brief v3. This is real work and it is spending money from this moment.
      </div>
    </div>
  </div>
  <div style="margin-top:15px; padding-top:13px; border-top:1px solid oklch(78% 0.14 75 / 0.28); font-size:11.5px; color:var(--text2); line-height:1.6;">
    <b style="color:var(--text);">The Start control is gone from this page.</b> There is nothing left here to click twice, so a second dispatch is impossible rather than merely discouraged. It returns only if this work is ever put back in the Backlog.
  </div>
  <div style="margin-top:14px;"><a href="stage-10.html" style="padding:9px 18px; border-radius:8px; border:1px solid var(--accent); color:var(--accent); font-weight:600; font-size:12.5px; display:inline-block;">Watch it &rarr;</a></div>
</div>'''

    failure = '''
<div style="margin-top:26px;">
  <div class="label" style="margin-bottom:4px;">Design state &middot; when the dispatch fails</div>
  <div style="font-size:11.5px; color:var(--text3); margin-bottom:13px; line-height:1.55; max-width:880px;">
    This project has already shipped one thing that reported success over a no-op, and QA caught it. Start is the same shape of risk and does not get to repeat it.
  </div>
  <div class="qrow" style="gap:14px;">
    <div class="panel" style="border-color:var(--red); padding:16px 18px;">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--red); text-transform:uppercase; margin-bottom:8px;">Start failed</div>
      <div style="font-size:13px; font-weight:600; margin-bottom:6px;">Not started. TASK-026 is still in the Backlog.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
        The dispatch did not go through. No agent was started, nothing was spent, the status is unchanged and the approved brief is untouched. You can try again, and trying again starts one pipeline, not two.
      </div>
      <div style="font-size:10.5px; color:var(--dim); margin-top:10px; line-height:1.55;">The word &ldquo;started&rdquo; never appears on this screen unless a status transition was actually written to the database. Not &ldquo;probably started&rdquo;, not &ldquo;starting&rdquo;.</div>
      <div style="margin-top:13px;"><a href="stage-9.html?step=confirm" style="padding:8px 16px; border-radius:8px; border:1px solid var(--accent); color:var(--accent); font-weight:600; font-size:12px; display:inline-block;">Try starting it again&hellip;</a></div>
    </div>
    <div class="panel" style="border-color:var(--border2); padding:16px 18px;">
      <div class="label" style="margin-bottom:8px;">Already running &mdash; the double-click lock</div>
      <div style="font-size:13px; font-weight:600; margin-bottom:6px; color:var(--text2);">Product is already working on this.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
        Reached by a refresh, a back button or a second tab. No Start control is rendered here and the route refuses a second dispatch. Approving is cheap and forgiving; starting is neither, so it gets the stricter guard.
      </div>
      <div style="font-size:10.5px; color:var(--dim); margin-top:10px; line-height:1.55;">Same in-progress lock the Ask-Agent panel already uses, applied to a far more expensive action.</div>
    </div>
  </div>
</div>'''

    head = _stage_head(9, "Start work", "The expensive decision, on its own screen",
                       "Approving cost nothing. This does not. It is two steps, and the first one dispatches nothing &mdash; it only opens the second.")
    reset = f'''
<div style="display:flex; gap:10px; margin-top:18px; align-items:center; flex-wrap:wrap;">
  <a href="stage-9.html?step=rest" style="padding:7px 14px; border-radius:7px; border:1px solid var(--border); background:var(--recess); color:var(--text3); font-size:11px;">Reset this flow</a>
  <div style="font-size:11px; color:var(--dim);">{where}</div>
</div>'''
    return head + _said_strip() + panel + reset + failure + _next_link(
        "stage-10", "What you see once it is running &rarr;")


# ---------------------------------------------------------------------------
# Stage 10 — FACTORY BEGINS EXECUTION (S10Running.dc.html)
# ---------------------------------------------------------------------------


def _stage10(params: dict) -> str:
    head = _stage_head(10, "Factory begins execution", "It is running",
                       "The first minute after starting is where a product is most tempted to invent activity. "
                       "This one shows what was written and nothing else.")
    body = f'''
<div style="border-radius:14px; border:1px solid oklch(78% 0.14 75 / 0.55); background:oklch(78% 0.14 75 / 0.06); padding:18px 20px; margin-bottom:16px;">
  <div style="display:flex; align-items:center; gap:11px; margin-bottom:10px; flex-wrap:wrap;">
    <div style="width:9px; height:9px; border-radius:50%; background:var(--accent);"></div>
    <div style="font-size:14.5px; font-weight:600;">TASK-026 is with Product</div>
    <div class="mono" style="font-size:11px; color:var(--text2);">since 20:47 UTC &middot; 40 seconds ago</div>
  </div>
  <div style="display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px;">
    <div class="card" style="border-radius:9px; padding:11px 13px;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; margin-bottom:5px;">What was written</div>
      <div style="font-size:11.5px; color:var(--prose); line-height:1.6;">One status transition, <span class="mono">BACKLOG &rarr; PLANNING</span>, and one history row naming you as the person who started it.</div>
    </div>
    <div class="card" style="border-radius:9px; padding:11px 13px;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; margin-bottom:5px;">Who has it</div>
      <div style="font-size:11.5px; color:var(--prose); line-height:1.6;">Product. One agent, not eight &mdash; the rest of the pipeline is not dispatched and will not start on its own.</div>
    </div>
    <div class="card" style="border-radius:9px; padding:11px 13px; border-color:oklch(72% 0.15 150 / 0.4);">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.06em; color:var(--green); text-transform:uppercase; margin-bottom:5px;">What it was told</div>
      <div style="font-size:11.5px; color:var(--prose); line-height:1.6;">The approved brief, v3. Your original sentence went with it, labelled as context.</div>
    </div>
  </div>
</div>

<div style="display:grid; grid-template-columns:minmax(0,1.15fr) minmax(0,1fr); gap:16px; align-items:start; margin-bottom:16px;">
  <div class="panel" style="padding:18px 20px;">
    <div class="label" style="margin-bottom:11px;">What this screen will not show you, and why</div>
    <div style="display:flex; flex-direction:column; gap:10px;">
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">No live-agent light.</b> Nothing in the pipeline writes an <span class="mono" style="font-size:11px;">agent_runs</span> row, so a pulsing dot would be a decoration reporting a fact this product does not have.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">No percentage complete.</b> <span class="mono" style="font-size:11px;">task_steps</span> exists on 1 of 24 tasks. A number here would be arithmetic on nothing.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">No spend so far.</b> 0 of 13 recorded runs carries a cost figure. When cost attribution exists, this is where it belongs; until then the space stays empty rather than showing $0.00, which would read as &ldquo;free&rdquo;.</div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;"><b style="color:var(--prose);">No estimated finish.</b> Nothing here has run enough times to have a history to estimate from.</div>
    </div>
    <div style="margin-top:14px; padding-top:12px; border-top:1px solid var(--border); font-size:11px; color:var(--text3); line-height:1.6;">
      Four absences, each with its cause. An empty space with a reason is information; an empty space without one is a bug, and a filled space without evidence is a lie.
    </div>
  </div>
  <div class="panel" style="padding:18px 20px;">
    <div class="label" style="margin-bottom:11px;">Where you watch it from here</div>
    <div style="display:flex; flex-direction:column; gap:11px;">
      <div>
        <div style="font-size:12px; color:var(--accent); font-weight:600;">This task&rsquo;s own page &rarr;</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55;">Status, owner, the gate ladder, and &mdash; permanently &mdash; your words beside what you approved. That pairing never goes away.</div>
      </div>
      <div>
        <div style="font-size:12px; color:var(--accent); font-weight:600;">Active Work &rarr;</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55;">Everything the company has in hand right now, TASK-026 among it.</div>
      </div>
      <div>
        <div style="font-size:12px; color:var(--accent); font-weight:600;">Costs &rarr;</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55;">Where spend appears as it accrues. Honestly: it will be sparse until runs record their cost.</div>
      </div>
      <div style="padding-top:10px; border-top:1px solid var(--border);">
        <div style="font-size:12px; color:var(--text2); font-weight:600;">The internal discussion</div>
        <div style="font-size:11px; color:var(--text3); line-height:1.55;">Kept, and one click away if you ever want it. Not shown by default &mdash; you asked the company a question, not for its minutes.</div>
      </div>
      <div style="padding-top:10px; border-top:1px solid var(--border); font-size:10.5px; color:var(--dim); line-height:1.55;">
        These three are drawn as the destinations they will be. In this preview they are labels, not links &mdash; the real Control Center pages they name are in the nav bar above.
      </div>
    </div>
  </div>
</div>

<div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:16px 18px;">
  <div class="label" style="margin-bottom:12px;">Still on the same screen, and always will be</div>
  <div class="qrow">
    <div style="border-left:3px solid var(--gray); padding-left:13px;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--gray); text-transform:uppercase; margin-bottom:6px;">You said</div>
      <div style="font-size:12px; color:var(--prose); line-height:1.65; white-space:pre-wrap;">&ldquo;{e(RAW_IDEA)}&rdquo;</div>
    </div>
    <div style="border-left:3px solid var(--green); padding-left:13px;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--green); text-transform:uppercase; margin-bottom:6px;">You approved &middot; v3</div>
      <div style="font-size:12px; color:var(--prose); line-height:1.65;">Open the AI Factory and understand within seconds how each child product is progressing. Proceed with narrowed scope: one Build screen, gate ladder not percentage, geometry not committed.</div>
    </div>
  </div>
  <div style="font-size:10.5px; color:var(--dim); margin-top:13px; line-height:1.6;">
    Not an archive, not a history tab &mdash; this pair stays on the working screen for the life of the idea, so &ldquo;is the company still building what I asked for?&rdquo; is answerable by looking, at any moment, without hunting.
  </div>
</div>'''
    return head + body


# ---------------------------------------------------------------------------
# Reference sheet — DISTINCTIONS (Distinctions.dc.html)
# ---------------------------------------------------------------------------

_VOICE_ROWS = [
    ("You said", "var(--gray)",
     "Recessed ground, gray rule, quotation marks, <span class=\"mono\" style=\"font-size:10.5px;\">pre-wrap</span>. The one voice with no company colour at all &mdash; it is not the company&rsquo;s claim.",
     "<b style=\"color:var(--prose);\">Appears on every screen of the journey</b>, in the same place, from intake to execution. Never collapsed, never behind a tab, never summarised.",
     "<b>Must never:</b> be edited, by anyone, including the Founder. Be paraphrased or tidied. Be sent downstream as the specification.",
     "border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:16px 18px; border-left:3px solid var(--gray);"),
    ("We think you mean", "var(--blue)",
     "Blue rule &mdash; already the colour of &ldquo;an agent produced this and it is waiting on you.&rdquo; Sits directly beside the gray, always, so the comparison is free.",
     "<b style=\"color:var(--prose);\">Concise questions 1 and 2.</b> Carries an attribution line naming the round and the version, because the reading changes between rounds and the Founder&rsquo;s words do not.",
     "<b>Must never:</b> occupy the same panel as the raw idea, or be rendered in a way that could be mistaken for a quotation.",
     "border-radius:12px; border:1px solid var(--border); background:var(--panel); padding:16px 18px; border-left:3px solid var(--blue);"),
    ("What we think of it", "var(--violet)",
     "Violet rule. Judgment about the idea &mdash; merits, what exists, differentiation, threats &mdash; and the closing Company View.",
     "<b style=\"color:var(--prose);\">Concise questions 3, 4, 5, 6, 8.</b> This is opinion, and its panels say so. Threats inside it use red for the risk itself, never for the panel.",
     "<b>Must never:</b> carry a score, a meter, a percentage or a star rating. Judgment stated as a number is false precision.",
     "border-radius:12px; border:1px solid var(--border); background:var(--panel); padding:16px 18px; border-left:3px solid var(--violet);"),
    ("We recommend", "var(--accent)",
     "The only voice with a filled ground and a full border rather than a left rule. It is the one thing the Founder is being asked to accept or reject.",
     "<b style=\"color:var(--prose);\">Concise questions 7, 9 and 10</b> &mdash; the recommendation, what we need from you, and what &ldquo;done&rdquo; means. One recommendation, never five options.",
     "<b>Must never:</b> appear more than once per version, or be softened into a menu of choices for the Founder to arbitrate.",
     "border-radius:12px; border:1px solid oklch(78% 0.14 75 / 0.5); background:oklch(78% 0.14 75 / 0.05); padding:16px 18px;"),
    ("You approved", "var(--green)",
     "A double border and a header bar &mdash; the only panel in the product built like a document rather than a card. It is an artifact, not a view.",
     "<b style=\"color:var(--prose);\">Stamped with the version, your name and the time.</b> Lines that came from you rather than the company are marked inside it, individually.",
     "<b>Must never:</b> appear before an explicit click. There is no timeout and no default &mdash; silence is not consent, and no code path treats it as consent.",
     "border-radius:12px; border:2px solid oklch(72% 0.15 150 / 0.7); background:var(--panel); padding:16px 18px;"),
]


def _distinctions(params: dict) -> str:
    rows = "".join(f'''
  <div style="{style}">
    <div style="display:grid; grid-template-columns:200px 1fr 1fr; gap:18px; align-items:start;">
      <div>
        <div style="font-size:10px; font-weight:700; letter-spacing:0.07em; color:{color}; text-transform:uppercase; margin-bottom:6px;">{e(name)}</div>
        <div style="font-size:11px; color:var(--text2); line-height:1.55;">{shape}</div>
      </div>
      <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">{where}</div>
      <div style="font-size:11.5px; color:var(--red); line-height:1.6;">{never}</div>
    </div>
  </div>''' for name, color, shape, where, never, style in _VOICE_ROWS)

    head = _sheet_head(
        "The central design problem", "Five voices, never confusable",
        "The whole feature exists so the Founder never loses track of which of these they are reading. Every panel in the journey "
        "carries exactly one voice, and carries it the same way every time &mdash; a colour, a rule in a fixed position, a kicker that "
        "names the speaker, and an attribution line. Four signals, so no single one is load-bearing.")

    return head + f'''
<div style="display:flex; flex-direction:column; gap:12px; margin-bottom:24px;">{rows}</div>

<div style="border-radius:14px; border:1px solid var(--border); background:var(--recess); padding:18px 20px; margin-bottom:20px;">
  <div class="label" style="margin-bottom:4px;">The same subject, in all five voices</div>
  <div style="font-size:11.5px; color:var(--text3); line-height:1.55; margin-bottom:15px; max-width:840px;">This is the test the design has to pass: five statements about one idea, and it should be impossible to read any of them as one of the others &mdash; even out of context, even in grayscale, even for someone who has not read the legend.</div>
  <div style="display:flex; flex-direction:column; gap:9px;">
    <div style="border-left:3px solid var(--gray); background:var(--recess); padding:11px 14px; border-radius:0 8px 8px 0;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--gray); text-transform:uppercase; margin-bottom:4px;">You said &middot; 20:03 UTC &middot; unedited</div>
      <div style="font-size:12px; color:var(--text); line-height:1.6; white-space:pre-wrap;">&ldquo;&hellip;I'M THINKING like an ellipse where we can track flow&rdquo;</div>
    </div>
    <div style="border-left:3px solid var(--blue); background:var(--panel); padding:11px 14px; border-radius:0 8px 8px 0;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--blue); text-transform:uppercase; margin-bottom:4px;">We think you mean &middot; the company &middot; round 1</div>
      <div style="font-size:12px; color:var(--prose); line-height:1.6;">The ellipse is your sketch of a form &mdash; the pipeline drawn as a loop with work moving round it &mdash; not a requirement that the shape be an ellipse.</div>
    </div>
    <div style="border-left:3px solid var(--violet); background:var(--panel); padding:11px 14px; border-radius:0 8px 8px 0;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--violet); text-transform:uppercase; margin-bottom:4px;">What we think of it &middot; the company &middot; round 1</div>
      <div style="font-size:12px; color:var(--prose); line-height:1.6;">Drawing the loop before we know what moves on it is the main risk here. Nothing in the pipeline writes a run record today, so the ring could arrive empty.</div>
    </div>
    <div style="border:1px solid oklch(78% 0.14 75 / 0.5); background:oklch(78% 0.14 75 / 0.05); padding:11px 14px; border-radius:8px;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--accent); text-transform:uppercase; margin-bottom:4px;">We recommend &middot; one recommendation</div>
      <div style="font-size:12px; color:var(--prose2); line-height:1.6;">Build the one-glance screen; do not commit to the ellipse yet. Test forms during design and pick on evidence.</div>
    </div>
    <div style="border:2px solid oklch(72% 0.15 150 / 0.7); background:var(--panel); padding:11px 14px; border-radius:8px;">
      <div style="font-size:9.5px; font-weight:700; letter-spacing:0.07em; color:var(--green); text-transform:uppercase; margin-bottom:4px;">You approved &middot; v3 &middot; by you &middot; 20:41 UTC</div>
      <div style="font-size:12px; color:var(--prose); line-height:1.6;">The ellipse geometry is not committed. Design tests forms and picks on evidence. <span style="color:var(--text3);">(approved with the ellipse question still open &mdash; recorded)</span></div>
    </div>
  </div>
</div>

<div class="qrow" style="gap:14px;">
  <div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:16px 18px;">
    <div class="label" style="margin-bottom:9px;">Why colour is not enough on its own</div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
      The palette here was closed before this feature existed &mdash; amber active, green passed, red risk, blue waiting, violet identity, gray neutral &mdash; and this design spends all five hues at once. So each voice carries three more signals that survive a screenshot, a grayscale print and colour-blindness: <b style="color:var(--prose);">the shape of the container</b> (left rule, filled panel, or bordered document), <b style="color:var(--prose);">a kicker naming the speaker in words</b>, and <b style="color:var(--prose);">an attribution line</b> saying who and when.
    </div>
    <div style="font-size:11px; color:var(--text3); line-height:1.6; margin-top:10px;">
      One honest note: violet already means <i>actor identity</i> elsewhere in this product and is asked here to also mean <i>the company&rsquo;s judgment</i>. That is a second meaning for one hue, and it is the weakest link in this system. It is written down rather than hidden.
    </div>
  </div>
  <div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:16px 18px;">
    <div class="label" style="margin-bottom:9px;">The rule that generates all of this</div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
      A Founder should be able to point at any sentence in the product and answer, without scrolling and without remembering, <b style="color:var(--prose);">&ldquo;did I say that, or did the company?&rdquo;</b> and if the company, <b style="color:var(--prose);">&ldquo;is that a reading, an opinion, or an instruction?&rdquo;</b>
    </div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.65; margin-top:10px;">
      Everything above is downstream of that one requirement. If a future screen makes it hard to answer, the screen is wrong &mdash; not the rule.
    </div>
  </div>
</div>'''


# ---------------------------------------------------------------------------
# Reference sheet — FULL DEPTH (FullDepth.dc.html)
#
# Every value here is a bracketed structural placeholder. No competitor,
# substitute, price, feature or market fact is named anywhere: the directive
# bans invented competitor information and a preview is not exempt from that
# (design review §3 and §8.2).
# ---------------------------------------------------------------------------


def _entry_rows(rows: list[tuple[str, str]]) -> str:
    return "".join(
        f'<div style="text-align:right; color:var(--text3); font-weight:600;">{e(label)}</div>'
        f'<div style="color:var(--text2);">{value}</div>'
        for label, value in rows)


def _full_depth(params: dict) -> str:
    ph = '<span class="ph">[ %s ]</span>'
    common = [
        ("what they offer", ph % "what they offer"),
        ("how it overlaps", ph % "overlap with our idea"),
        ("where it is stronger", ph % "where they appear stronger"),
        ("where we could differ", ph % "where our idea could differentiate"),
    ]
    competitor_rows = [
        ("what they offer", ph % "what they offer"),
        ("how they overlap", ph % "overlap with our idea"),
        ("where stronger", ph % "where they appear stronger"),
        ("where we differ", ph % "where our idea could differentiate"),
        ("source", '<span style="color:var(--text3);">None. This is unverified model recollection and may be out of date.</span>'),
    ]

    head = _sheet_head(
        "Depth scaling &middot; the other setting", "The Full-depth expanded layer",
        "The walkable journey uses a real idea, and that idea is internal tooling, so its depth is Light and sections 5&ndash;7 are "
        "honestly empty. This sheet shows the <b style=\"color:var(--text2);\">shape</b> of those sections when depth is Full &mdash; "
        "every label slot, the standing disclosure, and the Founder check. "
        "<b style=\"color:var(--text);\">Every value below is a structural placeholder in brackets.</b> Inventing a competitor to make "
        "a preview look finished is the same offence as inventing one in production, and a preview is not exempt.")

    return head + f'''
<div style="border-radius:12px; border:1px solid var(--border); background:var(--recess); padding:13px 16px; margin-bottom:18px; display:flex; align-items:flex-start; gap:14px; flex-wrap:wrap;">
  <div style="font-size:11px; color:var(--text3); padding-top:3px;">Depth</div>
  <div class="pill" style="border:1px solid var(--accent); background:var(--accent-soft); color:var(--accent); font-size:11px; font-weight:700;">Full</div>
  <div style="flex:1; min-width:320px; font-size:11.5px; color:var(--text2); line-height:1.6;">
    {ph % "who outside chooses"} could choose {ph % "what else they could choose"} instead.
    &mdash; Full is never the default and never automatic: it has to name both, or the depth stays Light.
  </div>
</div>

<div style="border-radius:12px; border:1px solid oklch(66% 0.17 25 / 0.55); background:var(--red-soft); padding:15px 18px; margin-bottom:18px;">
  <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--red); text-transform:uppercase; margin-bottom:7px;">Standing disclosure &mdash; on the section, not in a page footer</div>
  <div style="font-size:13px; color:var(--text); line-height:1.65; font-weight:500;">
    Research has not been performed; all entries below are company inference or unknown.
  </div>
  <div style="font-size:11.5px; color:var(--text2); line-height:1.6; margin-top:9px;">
    No agent in this company can browse the web. Nothing below was researched &mdash; it is what the company recollects, and it may be out of date or wrong. This line is rendered exactly as it would appear today, on every Full-depth evaluation this product could currently produce.
  </div>
</div>

<div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text2); text-transform:uppercase; margin-bottom:4px;">5 &middot; Known competitors and alternatives &mdash; substitutes first</div>
<div style="font-size:11.5px; color:var(--text3); margin-bottom:13px; line-height:1.55; max-width:900px;">
  How people solve the problem today &mdash; a spreadsheet, a manual process, a group chat &mdash; comes before any vendor. It is more decision-relevant and it needs no verification, so it is the only part of this section the company can state with confidence.
</div>

<div class="panel" style="padding:15px 17px; margin-bottom:12px; border-left:3px solid var(--violet);">
  <div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; margin-bottom:10px; flex-wrap:wrap;">
    <div style="font-size:13px; font-weight:600; color:var(--text);"><span class="mono" style="font-size:12px; color:var(--text2); border:1px dashed var(--dim); border-radius:5px; padding:2px 8px;">[ substitute &mdash; how people do this today without any product ]</span></div>
    <div style="padding:2px 9px; border-radius:5px; background:var(--panel2); border:1px solid var(--dash); color:var(--text2); font-size:9.5px; font-weight:700; letter-spacing:0.04em; white-space:nowrap;">COMPANY INFERENCE</div>
  </div>
  <div style="display:grid; grid-template-columns:150px 1fr; gap:8px 16px; font-size:11.5px; line-height:1.6;">{_entry_rows(common)}</div>
  <div style="font-size:10.5px; color:var(--dim); margin-top:10px; line-height:1.5;">A substitute is not a vendor, so nothing here needs a source. This is the entry the company is most confident about and it goes first for that reason.</div>
</div>

<div class="panel" style="padding:15px 17px; margin-bottom:12px; border-left:3px solid var(--violet);">
  <div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; margin-bottom:10px; flex-wrap:wrap;">
    <div style="font-size:13px; font-weight:600;"><span class="mono" style="font-size:12px; color:var(--text2); border:1px dashed var(--dim); border-radius:5px; padding:2px 8px;">[ competitor ]</span></div>
    <div style="padding:2px 9px; border-radius:5px; background:var(--panel2); border:1px solid var(--dash); color:var(--text2); font-size:9.5px; font-weight:700; letter-spacing:0.04em; white-space:nowrap;">COMPANY INFERENCE</div>
  </div>
  <div style="display:grid; grid-template-columns:150px 1fr; gap:8px 16px; font-size:11.5px; line-height:1.6;">{_entry_rows(competitor_rows)}</div>
  <div style="border-radius:8px; background:oklch(78% 0.14 75 / 0.08); border:1px solid oklch(78% 0.14 75 / 0.35); padding:9px 12px; margin-top:11px;">
    <div style="font-size:9.5px; font-weight:700; letter-spacing:0.06em; color:var(--accent); text-transform:uppercase; margin-bottom:4px;">Before you commit</div>
    <div style="font-size:11.5px; color:var(--prose); line-height:1.55;">Check whether <span class="mono" style="font-size:10.5px; color:var(--text2);">[ competitor ]</span> already does this &mdash; we cannot. Every named third party carries this line, or it is a bare assertion the company cannot stand behind.</div>
  </div>
</div>

<div class="qrow" style="gap:12px; margin-bottom:20px;">
  <div class="panel" style="padding:15px 17px;">
    <div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:9px; flex-wrap:wrap;">
      <div style="font-size:12.5px; font-weight:600;"><span class="mono" style="font-size:11.5px; color:var(--text2); border:1px dashed var(--dim); border-radius:5px; padding:2px 7px;">[ area we know nothing about ]</span></div>
      <div style="padding:2px 9px; border-radius:5px; background:var(--panel2); border:1px solid var(--dash); color:var(--text2); font-size:9.5px; font-weight:700; letter-spacing:0.04em;">UNKNOWN</div>
    </div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">
      We are not aware of an established competitor here, and cannot check. <b style="color:var(--prose);">That is not evidence there are none.</b>
    </div>
    <div style="font-size:11px; color:var(--text3); line-height:1.55; margin-top:9px;">UNKNOWN is a first-class answer. &ldquo;We do not know, and cannot check&rdquo; is a complete, passing entry &mdash; and it is the entry most likely to be quietly replaced by something more flattering.</div>
  </div>
  <div style="border-radius:12px; border:1px dashed oklch(66% 0.17 25 / 0.6); background:var(--recess); padding:15px 17px;">
    <div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:9px; flex-wrap:wrap;">
      <div style="font-size:12.5px; font-weight:600; color:var(--text3);">The third label</div>
      <div style="padding:2px 9px; border-radius:5px; background:var(--panel2); border:1px solid var(--dim); color:var(--text3); font-size:9.5px; font-weight:700; letter-spacing:0.04em; text-decoration:line-through;">VERIFIED / CURRENT</div>
    </div>
    <div style="font-size:11.5px; color:var(--text2); line-height:1.6;">
      <b style="color:var(--red);">Unreachable today.</b> This label requires a preserved source, and no agent in this company can produce one &mdash; every dispatched agent runs with its tools disabled.
    </div>
    <div style="font-size:11px; color:var(--red); line-height:1.6; margin-top:9px;">
      The slot is drawn anyway, because it is the tell: <b>if this label ever appears on a real evaluation, treat it as evidence that something fabricated it.</b>
    </div>
  </div>
</div>

<div class="panel" style="padding:15px 17px; margin-bottom:20px; border-left:3px solid var(--violet);">
  <div style="font-size:10px; font-weight:700; letter-spacing:0.05em; color:var(--text2); margin-bottom:9px;">7 &middot; COMPETITIVE ADVANTAGES / MERITS</div>
  <div style="font-size:11.5px; color:var(--text2); line-height:1.65;">
    Populated from real advantages only &mdash; UX, cost, speed, automation, integration, audience, personalisation, privacy, distribution, simplicity, technical or business-model advantage. <b style="color:var(--prose);">Differentiation is not claimed unless it is real.</b>
    When it is not, the section says so in these words, and that is a complete answer rather than a gap: <i style="color:var(--text);">&ldquo;We do not yet see a strong differentiation.&rdquo;</i>
  </div>
</div>

<div style="border-radius:14px; border:1px solid oklch(70% 0.12 300 / 0.55); background:var(--panel); padding:19px 21px;">
  <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; gap:12px; flex-wrap:wrap;">
    <div style="font-size:11px; font-weight:700; letter-spacing:0.08em; color:var(--violet); text-transform:uppercase;">Company view &mdash; at Full depth, with unknown competitor data</div>
    <div style="font-size:10.5px; color:var(--dim);">same six fields, same vocabulary, at both depths</div>
  </div>
  <div style="display:grid; grid-template-columns:160px 1fr; gap:12px 20px; align-items:baseline;">
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; text-align:right;">Opportunity</div>
    <div style="font-size:14px; font-weight:700; color:var(--text2);">Unclear</div>
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; text-align:right;">Why</div>
    <div style="font-size:12.5px; color:var(--prose); line-height:1.7;">The merits are legible, but whether this wins depends on what already exists, and we do not know what already exists. We could not look, and the model&rsquo;s recollection is not evidence. <b style="color:var(--text);">Unclear is the honest word here</b>, and it exists precisely so the company is never forced to manufacture confidence it does not have.</div>
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; text-align:right;">Biggest merit</div>
    <div style="font-size:12.5px; color:var(--text2); line-height:1.7;">{ph % "the strongest real merit"}</div>
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--red); text-transform:uppercase; text-align:right;">Biggest threat</div>
    <div style="font-size:12.5px; color:var(--prose); line-height:1.7;">That an established alternative already does this and we would not know until after building. Unverifiable from inside this company.</div>
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--text3); text-transform:uppercase; text-align:right;">Best differentiation</div>
    <div style="font-size:12.5px; color:var(--prose); line-height:1.7;">None we can see yet.</div>
    <div style="font-size:10px; font-weight:700; letter-spacing:0.06em; color:var(--accent); text-transform:uppercase; text-align:right;">Recommendation</div>
    <div><span style="display:inline-block; padding:6px 16px; border-radius:8px; background:oklch(78% 0.14 75 / 0.16); border:1px solid var(--accent); color:var(--accent); font-size:13px; font-weight:700;">Investigate first</span></div>
  </div>
  <div style="margin-top:15px; padding-top:13px; border-top:1px solid var(--border); font-size:11px; color:var(--text2); line-height:1.65;">
    <b style="color:var(--prose);">This is the whole point of the four-value vocabulary.</b> When competitor information is unknown and it materially affects the decision, the honest recommendation is <i>Investigate first</i> &mdash; not <i>Proceed</i> with a hedge in the small print. A recommendation nobody ever selects is not a recommendation, and this is the case that reaches it.
  </div>
</div>'''


# ---------------------------------------------------------------------------
# Page assembly, routing table, and the static-snapshot entry point.
# ---------------------------------------------------------------------------

BUILDERS = {
    "stage-1": _stage1, "stage-2": _stage2, "stage-3": _stage3, "stage-4": _stage4,
    "stage-5": _stage5, "stage-6": _stage6, "stage-7": _stage7, "stage-8": _stage8,
    "stage-9": _stage9, "stage-10": _stage10,
    "distinctions": _distinctions, "full-depth": _full_depth,
}

PAGE_TITLES = {slug: f"Ideas (preview) — {kicker}" for slug, _, _, kicker, _ in STAGES}
PAGE_TITLES.update({slug: f"Ideas (preview) — {title}" for slug, title in SHEETS})


def build_page(slug: str, params: dict | None = None, token: str | None = None) -> str:
    """Render one shell page. `params` is a flat {name: first value} view of
    the query string; an unknown key or an unrecognised value always falls
    back to that page's default state, so no query string can produce an
    error. Raises KeyError for an unknown slug — the caller (server.py)
    validates the slug against BUILDERS first and 404s instead."""
    builder = BUILDERS[slug]
    body = f'''<style>{SHELL_CSS}</style>
<div class="idj">
{_preview_strip()}
{_rail(slug)}
{builder(params or {})}
{_footer()}
</div>'''
    return page(PAGE_TITLES[slug], NAV_HREF, body, depth=1, token=token)


def main() -> None:
    IDEAS_SUBDIR.mkdir(parents=True, exist_ok=True)
    for slug in PAGE_SLUGS:
        write_output(IDEAS_SUBDIR / f"{slug}.html", build_page(slug))
    print(f"wrote {len(PAGE_SLUGS)} Ideas (preview) pages under {IDEAS_SUBDIR}")


if __name__ == "__main__":
    main()
