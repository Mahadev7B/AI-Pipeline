"""ops/idea-desk/pages.py — every screen the Idea Desk renders.

This is the approved mockup (ops/mockups/idea-evaluation/index.html, DEC-018)
ported to server-rendered HTML. The visual language is deliberately identical:
same palette, same five-voice colour grammar, same copy. What changed is that
the content now comes from the operational database instead of a JavaScript
constant, and the actions are real form posts instead of local state flips.

Read-only by construction — nothing in this module writes anything. Writes go
through server.py, which shells out to opsdb.py, the sole database writer.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone

# The five voices of the journey (design review Revision 2). Colour carries
# who is speaking: you, our reading of you, our judgement, our ask, your call.
VOICES = {
    "you":   ("var(--gray)",   "You said"),
    "mean":  ("var(--blue)",   "We think you mean"),
    "think": ("var(--violet)", "What we think of it"),
    "need":  ("var(--accent)", "We recommend / need"),
    "ok":    ("var(--green)",  "You approved"),
}

# The ten concise questions. The fifteen sections sit behind them on demand.
QUESTIONS = [
    (1,  "Did the company understand my idea?",      "mean",  "sections 1 and 2"),
    (2,  "What am I really trying to achieve?",      "mean",  "section 3"),
    (3,  "Why might this be worth building?",        "think", "section 4"),
    (4,  "What already exists?",                     "think", "sections 5 and 6"),
    (5,  "What could make ours different?",          "think", "section 7"),
    (6,  "What could make it fail?",                 "think", "section 8"),
    (7,  "What does the company recommend?",         "need",  "sections 9, 10 and 12"),
    (8,  "What assumptions did the company make?",   "think", "section 11"),
    (9,  "What decisions do you need from me?",      "need",  "section 13"),
    (10, "How will we know we succeeded?",           "need",  "section 14"),
]

APPROVABLE = ("Proceed", "Proceed with narrowed scope")

CSS = """
:root{
  --bg:#0b0d10; --panel:#14171c; --panel2:#1a1e24; --panel3:#20252d;
  --border:#242830; --border2:#323844; --hair:#1c2027;
  --text:#eae8e3; --text2:#9aa0a8; --text3:#666c74; --dim:#4c525a;
  --accent: oklch(78% 0.14 75); --accent-soft: oklch(78% 0.14 75 / 0.13); --accent-ink:#141007;
  --gray:#7d848d;
  --blue: oklch(72% 0.12 250); --blue-soft: oklch(72% 0.12 250 / 0.12);
  --violet: oklch(72% 0.13 300); --violet-soft: oklch(72% 0.13 300 / 0.12);
  --green: oklch(72% 0.15 150); --green-soft: oklch(72% 0.15 150 / 0.13);
  --red: oklch(66% 0.17 25);
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  color-scheme: dark;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:var(--sans);
          font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;}
a{color:var(--accent);text-decoration:none;} a:hover{color:var(--text);}
button{font:inherit;cursor:pointer;}
button:focus-visible,textarea:focus-visible,input:focus-visible,summary:focus-visible{
  outline:2px solid var(--accent);outline-offset:2px;}
textarea,input{font:inherit;color:var(--text);background:var(--panel2);border:1px solid var(--border2);
               border-radius:9px;padding:12px 14px;width:100%;}
textarea{min-height:150px;resize:vertical;line-height:1.6;}
textarea::placeholder,input::placeholder{color:var(--text3);}
.wrap{max-width:1180px;margin:0 auto;padding:0 28px 130px;}
.top{position:sticky;top:0;z-index:20;background:color-mix(in oklab, var(--bg) 88%, transparent);
     backdrop-filter:blur(10px);border-bottom:1px solid var(--hair);}
.top-in{max-width:1180px;margin:0 auto;padding:12px 28px;display:flex;align-items:center;gap:18px;}
.brand{font-weight:700;letter-spacing:-0.01em;font-size:15px;display:flex;align-items:center;gap:10px;
       color:var(--text);}
.brand .sq{width:12px;height:12px;border-radius:3px;background:var(--accent);}
.crumb{color:var(--text3);font-size:13px;}
.crumb b{color:var(--text2);font-weight:500;}
.topright{margin-left:auto;display:flex;align-items:center;gap:14px;font-size:12px;color:var(--text3);}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 16px;border-radius:9px;font-size:13.5px;
     font-weight:600;border:1px solid var(--border2);background:var(--panel);color:var(--text);
     transition:background .12s,border-color .12s;}
.btn:hover{background:var(--panel2);border-color:var(--text3);}
.btn.primary{background:var(--accent);color:var(--accent-ink);border-color:transparent;}
.btn.primary:hover{filter:brightness(1.06);}
.btn.ok{background:var(--green);color:#06140c;border-color:transparent;}
.btn.ghost{border-color:transparent;color:var(--text2);background:none;}
.btn.ghost:hover{color:var(--text);background:var(--panel);}
.btn.sm{padding:6px 11px;font-size:12.5px;border-radius:7px;}
.st{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;letter-spacing:0.06em;
    text-transform:uppercase;padding:3px 9px;border-radius:6px;border:1px solid;}
.st::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;}
.st.draft{color:var(--text2);border-color:var(--border2);}
.st.evaluated{color:var(--violet);border-color:oklch(72% 0.13 300 / .5);background:var(--violet-soft);}
.st.approved{color:var(--green);border-color:oklch(72% 0.15 150 / .5);background:var(--green-soft);}
.st.parked{color:var(--text2);border-color:var(--border2);background:var(--panel2);}
.st.dropped{color:var(--text3);border-color:var(--border);}
h1{font-size:28px;font-weight:600;letter-spacing:-0.02em;line-height:1.2;margin:0;text-wrap:balance;}
.k{font-size:10.5px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:var(--text3);}
.sub{color:var(--text2);font-size:14px;max-width:62ch;}
.list{display:flex;flex-direction:column;border-top:1px solid var(--border);margin-top:22px;}
.row{display:grid;grid-template-columns:1fr auto 210px;gap:22px;align-items:center;padding:18px 6px;
     border-bottom:1px solid var(--border);}
.row:hover{background:var(--panel);}
.row .t{font-size:15.5px;font-weight:600;color:var(--text);}
.row .d{font-size:13px;color:var(--text2);margin-top:4px;overflow:hidden;text-overflow:ellipsis;
        white-space:nowrap;}
.row .when{font-size:12px;color:var(--text3);text-align:right;}
.empty{padding:48px 0;color:var(--text3);font-size:14px;}
.form{max-width:720px;display:flex;flex-direction:column;gap:22px;margin-top:28px;}
.field label{display:block;font-size:13px;font-weight:600;margin-bottom:8px;}
.field .hint{font-size:12px;color:var(--text3);margin-top:7px;line-height:1.55;}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
.note{font-size:12.5px;color:var(--text3);line-height:1.6;max-width:64ch;}
.head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-top:26px;
      flex-wrap:wrap;}
.meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:12.5px;color:var(--text3);}
.meta .chip{padding:3px 9px;border-radius:6px;background:var(--panel);border:1px solid var(--border);
            color:var(--text2);font-size:11.5px;}
.voices{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--text3);}
.voices span::before{content:"";display:inline-block;width:9px;height:9px;border-radius:2px;
                     margin-right:6px;vertical-align:-1px;background:var(--c);}
.cols{display:grid;grid-template-columns:330px minmax(0,1fr);gap:34px;margin-top:26px;align-items:start;}
@media (max-width:900px){.cols{grid-template-columns:1fr;} .side{position:static !important;}}
.side{position:sticky;top:64px;display:flex;flex-direction:column;gap:18px;}
.you{border-left:3px solid var(--gray);padding:2px 0 2px 14px;}
.you .q{white-space:pre-wrap;font-size:14px;line-height:1.6;color:var(--text);}
.you .aud{margin-top:10px;font-size:12.5px;color:var(--text2);}
.hist{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 16px;}
.h-item{display:grid;grid-template-columns:18px 1fr;gap:10px;padding:8px 0;border-top:1px solid var(--hair);
        font-size:12.5px;color:var(--text2);align-items:start;}
.h-item:first-of-type{border-top:0;}
.h-item .dot{width:8px;height:8px;border-radius:50%;margin-top:6px;background:var(--border2);}
.h-item.cur .dot{background:var(--violet);} .h-item.ok .dot{background:var(--green);}
.h-item.raw .dot{background:var(--gray);}
.h-item b{color:var(--text);font-weight:600;}
.h-item .fb{margin-top:5px;padding:7px 9px;border-left:2px solid var(--gray);background:var(--panel2);
            border-radius:0 6px 6px 0;font-size:12px;white-space:pre-wrap;}
.banner{margin-top:14px;padding:12px 16px;border-radius:10px;font-size:13px;line-height:1.55;
        border:1px solid;}
.banner.blue{border-color:oklch(72% 0.12 250 / .4);background:var(--blue-soft);color:var(--text);}
.banner.green{border-color:oklch(72% 0.15 150 / .5);background:var(--green-soft);color:var(--text);}
.banner.gray{border-color:var(--border2);background:var(--panel);color:var(--text2);}
.banner.red{border-color:oklch(66% 0.17 25 / .5);background:oklch(66% 0.17 25 / .1);color:var(--text);}
.qs{display:flex;flex-direction:column;gap:14px;margin-top:18px;}
.qa{border:1px solid var(--border);border-radius:12px;padding:16px 18px 14px;background:var(--panel);
    border-left:3px solid var(--v);}
.qa.need{background:oklch(78% 0.14 75 / 0.05);border-color:oklch(78% 0.14 75 / .35);
         border-left-color:var(--accent);}
.qa .qh{display:flex;align-items:baseline;gap:10px;margin-bottom:8px;}
.qa .n{font-family:var(--mono);font-size:11px;color:var(--text3);}
.qa .qt{font-size:14.5px;font-weight:600;}
.qa .v{margin-left:auto;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
       color:var(--v);}
.qa .a{font-size:14px;line-height:1.65;color:var(--text2);}
.qa .a b{color:var(--text);font-weight:600;}
.qa .a.big{font-size:16px;color:var(--text);line-height:1.55;}
details.x{margin-top:10px;}
details.x > summary{font-size:12.5px;color:var(--accent);cursor:pointer;list-style:none;
                    display:inline-flex;align-items:center;gap:6px;}
details.x > summary::-webkit-details-marker{display:none;}
details.x > summary::before{content:"\\25B8";font-size:10px;display:inline-block;transition:transform .15s;}
details.x[open] > summary::before{transform:rotate(90deg);}
details.x .xin{margin-top:12px;padding:14px 16px;background:var(--panel2);border-radius:9px;
               font-size:13px;line-height:1.65;color:var(--text2);}
.xin .sk{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);
         margin:12px 0 6px;}
.xin .sk:first-child{margin-top:0;}
.xin b{color:var(--text);font-weight:600;}
.na{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.05em;padding:2px 7px;
    border-radius:5px;border:1px dashed var(--border2);color:var(--text3);margin-left:8px;}
.lab{display:inline-block;font-family:var(--mono);font-size:10.5px;padding:1px 6px;border-radius:4px;
     border:1px solid var(--border2);color:var(--text2);}
.lab.unk{color:var(--red);border-color:oklch(66% 0.17 25 / .5);}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
@media (max-width:640px){.two{grid-template-columns:1fr;}}
.dec{border:1px solid var(--border);border-radius:9px;padding:12px 14px;margin-top:10px;
     background:var(--panel2);}
.cv{margin-top:22px;border-radius:14px;border:1px solid oklch(72% 0.13 300 / .55);background:var(--panel);
    padding:20px 22px;}
.cv .cvh{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px;
         align-items:baseline;}
.cv .cvh .k{color:var(--violet);}
.cvg{display:grid;grid-template-columns:150px 1fr;gap:13px 20px;align-items:baseline;}
.cvg .k{text-align:right;}
.cvg .val{font-size:13.5px;line-height:1.65;color:var(--text);}
.cvg .opp{font-size:15px;font-weight:700;}
.rec{display:inline-block;padding:6px 14px;border-radius:8px;border:1px solid var(--accent);
     background:var(--accent-soft);color:var(--accent);font-weight:700;font-size:13px;}
@media (max-width:640px){.cvg{grid-template-columns:1fr;} .cvg .k{text-align:left;}}
.bar{position:fixed;left:0;right:0;bottom:0;z-index:30;
     background:color-mix(in oklab, var(--bg) 92%, transparent);backdrop-filter:blur(10px);
     border-top:1px solid var(--border);}
.bar-in{max-width:1180px;margin:0 auto;padding:12px 28px;display:flex;align-items:center;gap:10px;
        flex-wrap:wrap;}
.bar .why{font-size:12.5px;color:var(--text3);margin-right:auto;max-width:56ch;}
.panel{margin-top:18px;border:1px solid var(--border2);border-radius:12px;background:var(--panel);
       padding:18px 20px;}
.panel h3{margin:0 0 6px;font-size:15px;}
.panel p{margin:0 0 12px;color:var(--text2);font-size:13.5px;line-height:1.6;}
.panel.g{border-color:oklch(72% 0.15 150 / .5);}
.arts{display:flex;flex-direction:column;gap:8px;margin:12px 0 16px;}
.art{display:grid;grid-template-columns:130px 1fr auto;gap:12px;align-items:baseline;padding:9px 12px;
     border-radius:8px;background:var(--panel2);font-size:13px;}
.art .m{font-family:var(--mono);font-size:11.5px;color:var(--text3);}
.foot{margin-top:60px;padding-top:18px;border-top:1px dashed var(--border2);font-size:12px;
      color:var(--text3);line-height:1.7;max-width:72ch;}
.login{max-width:420px;margin:14vh auto;padding:0 24px;}
"""


def e(s) -> str:
    return html.escape("" if s is None else str(s))


# The ten answers are written by agents, and agent output is not trusted input
# just because it came from our own company. Everything is escaped first, then
# the small set of tags the answer format actually needs is put back. Nothing
# else survives — no links, no scripts, no attributes but the class names below.
_SIMPLE_TAGS = "b|i|em|strong|br"
_DIV_CLASSES = "sk|two|dec"
_SPAN_CLASSES = r"lab unk|lab|na"


def safe_html(raw: str | None) -> str:
    out = html.escape("" if raw is None else str(raw))
    out = re.sub(rf"&lt;(/?)({_SIMPLE_TAGS})\s*/?&gt;", r"<\1\2>", out)
    out = re.sub(rf"&lt;div class=(?:&quot;|&#x27;)({_DIV_CLASSES})(?:&quot;|&#x27;)&gt;",
                 r'<div class="\1">', out)
    out = re.sub(rf"&lt;span class=(?:&quot;|&#x27;)({_SPAN_CLASSES})(?:&quot;|&#x27;)&gt;",
                 r'<span class="\1">', out)
    out = out.replace("&lt;div&gt;", "<div>")
    out = out.replace("&lt;/div&gt;", "</div>").replace("&lt;/span&gt;", "</span>")
    # Balance the containers, so a stray closing tag can never escape the card
    # it was written into and start eating the page.
    depth = 0
    balanced = []
    for piece in re.split(r"(<div[^>]*>|</div>)", out):
        if piece.startswith("<div"):
            depth += 1
        elif piece == "</div>":
            if depth == 0:
                continue
            depth -= 1
        balanced.append(piece)
    return "".join(balanced) + "</div>" * depth


def _ago(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 172800:
        return f"{int(secs // 3600)} h ago"
    return f"{int(secs // 86400)} d ago"


def shell(title: str, body: str, *, crumb: str = "", bar: str = "") -> bytes:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><style>{CSS}</style></head><body>
<div class="top"><div class="top-in">
  <a class="brand" href="/"><span class="sq"></span>Idea Desk</a>
  <div class="crumb">{crumb}</div>
  <div class="topright"><span>Your ideas, before they become work</span></div>
</div></div>
<div class="wrap">{body}</div>{bar}
</body></html>""".encode("utf-8")


def login_page(token: str, error: str = "") -> bytes:
    err = f'<div class="banner red" style="margin-bottom:18px">{e(error)}</div>' if error else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Idea Desk</title><style>{CSS}</style></head><body>
<div class="login">
  <div class="brand" style="margin-bottom:26px"><span class="sq"></span>Idea Desk</div>
  <h1>Sign in</h1>
  <p class="sub" style="margin:10px 0 22px">Same passphrase as your Control Center. This is the
     Founder's desk, so nothing here opens without it.</p>
  {err}
  <form method="post" action="/api/login">
    <input type="hidden" name="token" value="{e(token)}">
    <input type="password" name="passphrase" placeholder="Passphrase" autofocus
           autocomplete="current-password">
    <div class="actions" style="margin-top:14px"><button class="btn primary" type="submit">Sign in</button></div>
  </form>
</div></body></html>""".encode("utf-8")


def setup_required_page() -> bytes:
    return shell("Idea Desk", """
      <div style="margin-top:60px"><h1>Set a passphrase first</h1>
      <p class="sub" style="margin-top:12px">No Founder credential exists yet, so there is nothing to
      sign in against. Create one, then start this again:</p>
      <div class="panel" style="max-width:640px"><code style="font-family:var(--mono);font-size:13px">
      python3 ops/control-center/founder_auth.py setup</code></div></div>""")


def error_page(status: int, title: str, detail: str) -> bytes:
    return shell(title, f"""<div style="margin-top:60px"><h1>{e(title)}</h1>
      <p class="sub" style="margin-top:12px">{detail}</p>
      <div class="actions" style="margin-top:20px"><a class="btn" href="/">Back to your ideas</a></div></div>""")


# --------------------------------------------------------------- the list ---

def list_page(ideas: list, build: str = "") -> bytes:
    rows = []
    for i in ideas:
        st = i["status"]
        if st == "draft":
            line = "Saved. Not evaluated yet."
        elif st == "approved":
            line = "Approved brief"
        elif st in ("parked", "dropped"):
            line = f"{st.capitalize()}"
        else:
            line = e(i["recommendation"] or "Evaluated")
        rows.append(f"""<div class="row">
          <div><a class="t" href="/idea/{i['id']}">{e(i['title'] or 'Untitled idea')}</a>
            <div class="d">{e(i['current_raw'])}</div></div>
          <span class="st {e(st)}">{e(st)}</span>
          <div class="when">{e(_ago(i['updated_at']))}<br>
            <span style="color:var(--text3)">{line}</span></div></div>""")
    body = f"""
    <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-top:40px;
                flex-wrap:wrap">
      <div><h1>Bring an idea to the company</h1>
        <p class="sub" style="margin:10px 0 0">You write it in your own words. The company works out what
        you mean, tells you what it thinks of it, and asks only what it genuinely needs. Nothing gets
        built until you approve the brief.</p></div>
      <a class="btn primary" href="/new">+ New idea</a>
    </div>
    <div class="list">{''.join(rows) or '<div class="empty">No ideas saved yet.</div>'}</div>
    <div class="foot">Your ideas are stored in the factory's own database, so they survive closing this
    window. Saving an idea starts nothing and costs nothing. Evaluation is the step that asks the company
    to actually read it &mdash; the only part that spends money.
    {f'<div style="margin-top:10px;color:var(--dim)">Running: {e(build)}</div>' if build else ''}</div>"""
    return shell("Idea Desk", body)


# ----------------------------------------------------------- the new form ---

def new_page(token: str, idea=None) -> bytes:
    editing = idea is not None
    raw = e(idea["current_raw"]) if editing else ""
    aud = e(idea["current_audience"]) if editing else ""
    trg = e(idea["current_trigger"]) if editing else ""
    action = f"/api/edit/{idea['id']}" if editing else "/api/create"
    cancel = f"/idea/{idea['id']}" if editing else "/"
    lead = ("Your original words from before stay on record. This edit is stored beside them, "
            "not over them." if editing else
            "Write it the way you would say it out loud. Do not tidy it. The company's first job is "
            "to work out what you mean, and it does that better from your real words.")
    body = f"""
    <div style="margin-top:40px"><h1>{'Edit your idea' if editing else 'What do you want to build?'}</h1>
      <p class="sub" style="margin:10px 0 0">{lead}</p></div>
    <form class="form" method="post" action="{action}">
      <input type="hidden" name="token" value="{e(token)}">
      <div class="field"><label for="raw">In your own words</label>
        <textarea id="raw" name="raw" required
          placeholder="the current UI so much verbose, it should be as simple as a dashboard&hellip;"
          >{raw}</textarea>
        <div class="hint">Stored exactly as typed, and never edited by the company.</div></div>
      <div class="two">
        <div class="field"><label for="aud">Who is it for?
          <span style="color:var(--text3);font-weight:400">optional</span></label>
          <input id="aud" name="audience" value="{aud}" placeholder="me &middot; my team &middot; the public"></div>
        <div class="field"><label for="trg">What made you think of it?
          <span style="color:var(--text3);font-weight:400">optional</span></label>
          <input id="trg" name="trigger" value="{trg}" placeholder="a moment, a complaint, something you could not find"></div>
      </div>
      <div class="actions">
        <button class="btn primary" type="submit">{'Save the edit' if editing else 'Save idea'}</button>
        <a class="btn ghost" href="{cancel}">Cancel</a>
      </div>
      <div class="note">Saving stores it and nothing else. No agent reads it, nothing is dispatched and
      nothing is spent until you ask for an evaluation.</div>
    </form>"""
    return shell("Idea Desk", body, crumb=f"/ <b>{'Edit idea' if editing else 'New idea'}</b>")


# ------------------------------------------------------------ one idea ------

def _history(idea, rounds) -> str:
    items = [f"""<div class="h-item raw"><span class="dot"></span><div><b>Original idea</b> &middot;
      {e(_ago(idea['created_at']))}<br>Your words, verbatim. Artifact 1.</div></div>"""]
    for ed in idea["edits"]:
        items.append(f"""<div class="h-item"><span class="dot"></span><div><b>You edited it</b> &middot;
          {e(_ago(ed['created_at']))}<div class="fb">{e(ed['raw_idea'])}</div></div></div>""")
    last_id = rounds[-1]["id"] if rounds else None
    for r in rounds:
        # The correction that produced a round belongs BEFORE it — that is the
        # order it actually happened in, and the history is read top to bottom.
        if r["founder_note"]:
            items.append(f"""<div class="h-item"><span class="dot"></span><div><b>You corrected us</b>
              <div class="fb">{e(r['founder_note'])}</div></div></div>""")
        approved = idea["approved_round_id"] == r["id"]
        cls = "ok" if approved else ("cur" if r["id"] == last_id and idea["status"] == "evaluated" else "")
        tag = ' &middot; <span style="color:var(--green)">approved</span>' if approved else ""
        items.append(f"""<div class="h-item {cls}"><span class="dot"></span><div>
          <b>Round {r['round_no']}</b> &middot; company reading &middot; {e(_ago(r['created_at']))}{tag}<br>
          {e(r['recommendation'] or '')}</div></div>""")
    if idea["status"] in ("parked", "dropped"):
        items.append(f"""<div class="h-item"><span class="dot"></span><div>
          <b>You {e(idea['status'])} it</b> &middot; {e(_ago(idea['closed_at']))}<br>
          {e(idea['close_reason'] or 'No reason given.')}</div></div>""")
    if idea["approved_round_id"]:
        items.append(f"""<div class="h-item ok"><span class="dot"></span><div><b>Approved brief</b>
          &middot; {e(_ago(idea['approved_at']))}<br>Artifact 3. Downstream reads only this.</div></div>""")
    return f'<div class="hist"><div class="k" style="margin-bottom:10px">What is stored</div>{"".join(items)}</div>'


def _company_view(view: dict) -> str:
    opp = view.get("opp", "Unclear")
    colour = ("var(--green)" if opp == "High" else "var(--red)" if opp == "Low" else "var(--text)")
    return f"""<div class="cv"><div class="cvh"><span class="k">Company view</span>
      <small style="font-size:11px;color:var(--dim)">Executive judgment &middot; not a score &middot;
      always visible</small></div>
      <div class="cvg">
        <div class="k">Opportunity</div><div class="val opp" style="color:{colour}">{e(opp)}</div>
        <div class="k">Why</div><div class="val">{e(view.get('why'))}</div>
        <div class="k">Biggest merit</div><div class="val">{e(view.get('merit'))}</div>
        <div class="k" style="color:var(--red)">Biggest threat</div><div class="val">{e(view.get('threat'))}</div>
        <div class="k">Best differentiation</div><div class="val">{e(view.get('diff'))}</div>
        <div class="k" style="color:var(--accent)">Recommendation</div>
        <div class="val"><span class="rec">{e(view.get('rec'))}</span></div>
      </div>
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);font-size:11.5px;
                  color:var(--dim)">Six fields, the same six every time. The four recommendations this
      company can give: Proceed &middot; Proceed with narrowed scope &middot; Investigate first &middot;
      Reconsider.</div></div>"""


def evaluating_page(idea, steps) -> bytes:
    """Shown while the company is actually reading the idea. Refreshes itself,
    because the work is happening in another thread and takes minutes."""
    lines = "".join(f"""<div class="h-item"><span class="dot" style="background:var(--accent)"></span>
      <div><b>{e(who)}</b><br>{e(what)}</div></div>""" for who, what in steps) or (
        '<div class="h-item"><span class="dot"></span><div>Starting&hellip;</div></div>')
    body = f"""
    <div style="max-width:660px;margin-top:40px">
      <div class="k">Round {len(idea.get('rounds_so_far') or []) + 1}</div>
      <h1 style="margin-top:8px">The company is considering your idea</h1>
      <p class="sub" style="margin:12px 0 0">They read it separately. They may disagree. You will not
      be handed the argument &mdash; the Chief of Staff brings you one answer.</p>
      <div class="you" style="margin-top:24px"><div class="k" style="color:var(--gray);
        margin-bottom:8px">You said</div><div class="q">&ldquo;{e(idea['current_raw'])}&rdquo;</div></div>
      <div class="hist" style="margin-top:22px">{lines}</div>
      <p class="note" style="margin-top:18px">This page refreshes itself. It takes a few minutes &mdash;
      several people are reading it, one after another. You can close this and come back.</p>
      <div class="actions" style="margin-top:14px"><a class="btn ghost" href="/">Back to your ideas</a></div>
    </div>"""
    page = shell("Idea Desk", body, crumb=f"/ <b>{e(idea.get('title') or 'Evaluating')}</b>")
    return page.replace(b"<title>", b'<meta http-equiv="refresh" content="6"><title>', 1)


def evaluate_panel(idea, token: str, *, correcting: bool = False) -> str:
    """The disclosure that has to sit in front of the one expensive button."""
    note_field = ("""<textarea name="note" style="min-height:90px" required
        placeholder="What did we get wrong? One or two lines is enough."></textarea>""" if correcting
        else "")
    heading = ("Correct us, and evaluate again" if correcting
               else "Ask the company to evaluate this idea")
    lead = ("Your idea does not change. Your note is stored beside it, and the company re-reads both."
            if correcting else
            "The Chief of Staff picks who should read it, those people read it separately, and you "
            "get back one answer.")
    return f"""<div class="panel"><h3>{heading}</h3><p>{lead}</p>
      <div class="banner" style="margin:0 0 14px;border-color:oklch(78% 0.14 75 / .4);
           background:var(--accent-soft);color:var(--text)">
        <b>This one spends money.</b> Several agents run, each a real model call, and it takes a few
        minutes. Everything else in the Idea Desk is free; this is the step that is not. There is no
        cost estimate available before the fact &mdash; the company cannot tell you in advance what a
        given idea will cost to read.</div>
      <form method="post" action="/api/{'correct' if correcting else 'evaluate'}/{idea['id']}">
        <input type="hidden" name="token" value="{e(token)}">{note_field}
        <div class="actions" style="margin-top:{'12' if correcting else '0'}px">
          <button class="btn primary" type="submit">{'Send and re-evaluate' if correcting
            else 'Yes, evaluate it'}</button>
          <a class="btn ghost" href="/idea/{idea['id']}">Not now</a></div></form></div>"""


def idea_page(idea, rounds, token: str, *, panel: str = "", flash: str = "",
              steps=None) -> bytes:
    if idea.get("evaluating_since"):
        return evaluating_page({**idea, "rounds_so_far": rounds}, steps or [])
    if not rounds:
        return _draft_page(idea, token, flash, panel)

    r = rounds[-1]
    answers = json.loads(r["answers_json"] or "{}")
    view = json.loads(r["view_json"] or "{}")
    roster = json.loads(r["roster_json"] or "{}")
    approved = idea["status"] == "approved"
    closed = idea["status"] in ("parked", "dropped")
    shown = next((x for x in rounds if x["id"] == idea["approved_round_id"]), r) if approved else r
    if shown["id"] != r["id"]:
        answers = json.loads(shown["answers_json"] or "{}")
        view = json.loads(shown["view_json"] or "{}")
        roster = json.loads(shown["roster_json"] or "{}")

    qs = []
    for num, title, voice, expands in QUESTIONS:
        colour, vname = VOICES[voice]
        pair = answers.get(str(num)) or ["Not answered in this round.", ""]
        concise, expanded = (safe_html(pair[0]), safe_html(pair[1] if len(pair) > 1 else ""))
        big = ' big' if num == 2 else ''
        exp = (f"""<details class="x"><summary>Expanded &middot; {e(expands)}</summary>
                <div class="xin">{expanded}</div></details>""" if expanded else "")
        qs.append(f"""<div class="qa {'need' if voice == 'need' else ''}" style="--v:{colour}">
          <div class="qh"><span class="n">Q{num}</span><span class="qt">{e(title)}</span>
            <span class="v">{e(vname)}</span></div>
          <div class="a{big}">{concise}</div>{exp}</div>""")

    inn = "<br>".join(f"<b>{e(w)}</b> &mdash; {e(why)}" for w, why in roster.get("in", []))
    out = "<br>".join(f'<b style="color:var(--text3)">Left out: {e(w)}</b> &mdash; {e(why)}'
                      for w, why in roster.get("out", []))
    roster_block = f"""<div class="qa" style="--v:var(--border2)">
      <div class="qh"><span class="qt" style="font-size:13.5px;color:var(--text2)">Who weighed in, and
        why</span><span class="v" style="color:var(--text3)">Depth {e(shown['depth'] or '')}</span></div>
      <div class="a" style="font-size:13px">{inn}
        <div style="margin-top:8px;color:var(--text3)">{out}</div>
        <div style="margin-top:8px;color:var(--text3)">Depth reason:
          {e(shown['depth_reason'] or '')}</div></div></div>"""

    banners = ""
    if flash:
        banners += f'<div class="banner green">{flash}</div>'
    if idea.get("last_error"):
        banners += (f'<div class="banner red"><b>The last evaluation did not finish.</b> '
                    f'{e(idea["last_error"])}</div>')
    if closed:
        word = "Parked." if idea["status"] == "parked" else "Dropped."
        tail = ("Not being built now; you can come back to it." if idea["status"] == "parked"
                else "Not being built. Kept as a record, together with what the company said.")
        why = (f' Your reason: &ldquo;{e(idea["close_reason"])}&rdquo;' if idea["close_reason"] else "")
        banners += f'<div class="banner gray"><b style="color:var(--text)">{word}</b> {tail}{why}</div>'
    if approved:
        banners += f"""<div class="banner green"><b>This is the approved brief.</b> Round
          {shown['round_no']} is now the single source of truth for anything built from this idea. Your
          original words and every earlier round stay stored underneath it, unchanged.</div>"""
    if shown["changed_note"] and not approved:
        banners += (f'<div class="banner blue"><b>What changed since round {shown["round_no"] - 1}:</b> '
                    f'{e(shown["changed_note"])}</div>')

    voices_legend = "".join(f'<span style="--c:{c}">{e(n)}</span>' for c, n in VOICES.values())
    aud = (f'<div class="aud"><b style="color:var(--text3)">For:</b> {e(idea["current_audience"])}</div>'
           if idea["current_audience"] else "")
    trg = (f'<div class="aud"><b style="color:var(--text3)">Because:</b> {e(idea["current_trigger"])}</div>'
           if idea["current_trigger"] else "")
    edited = ('<div class="aud" style="color:var(--text3)">You have since edited the wording — the '
              'current version is in "What is stored".</div>' if idea["edits"] else "")

    body = f"""
    <div class="head">
      <div><div class="k">Idea &middot; round {shown['round_no']} of {len(rounds)}</div>
        <h1 style="margin-top:6px">{e(idea['title'] or 'Untitled idea')}</h1>
        <div class="meta" style="margin-top:10px"><span class="st {e(idea['status'])}">{e(idea['status'])}</span>
          <span class="chip">Depth: {e(shown['depth'] or 'n/a')}</span>
          <span>{e(_ago(shown['created_at']))}</span></div></div>
      <div class="voices">{voices_legend}</div>
    </div>
    {banners}
    <div class="cols">
      <aside class="side">
        <div class="you"><div class="k" style="color:var(--gray);margin-bottom:8px">You said &middot;
          never edited</div>
          <div class="q">&ldquo;{e(idea['raw_idea'])}&rdquo;</div>{aud}{trg}{edited}</div>
        {_history(idea, rounds)}
      </aside>
      <main>
        <div style="display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;
                    padding-bottom:12px;border-bottom:1px solid var(--border)">
          <div style="font-size:12.5px;color:var(--text2)">The ten answers, then the company's closing
            view. Everything needed to decide is here.</div>
          <div style="font-size:12px;color:var(--text3)">Open any &ldquo;Expanded&rdquo; for the working
            behind an answer.</div>
        </div>
        <div class="qs">{roster_block}{''.join(qs)}</div>
        {_company_view(view)}
        {panel}
      </main>
    </div>"""
    return shell("Idea Desk", body,
                 crumb=f"/ <b>{e(idea['title'] or 'Idea')}</b>",
                 bar=_action_bar(idea, shown, token))


def _draft_page(idea, token: str, flash: str = "", panel: str = "") -> bytes:
    closed = idea["status"] in ("parked", "dropped")
    flash_html = f'<div class="banner green">{flash}</div>' if flash else ""
    if closed:
        state = f"""<div class="banner gray"><b style="color:var(--text)">
          {'Parked.' if idea['status'] == 'parked' else 'Dropped.'}</b> Nothing was evaluated.
          {e(idea['close_reason'] or '')}</div>"""
        acts = f"""<form method="post" action="/api/reopen/{idea['id']}" style="margin-top:18px">
          <input type="hidden" name="token" value="{e(token)}">
          <button class="btn" type="submit">Reopen</button></form>"""
    else:
        state = """<div class="banner blue">Nothing has been evaluated yet. When you are ready, the
          company reads it and comes back with one answer.</div>"""
        acts = f"""<div class="actions" style="margin-top:18px">
          <a class="btn primary" href="/evaluate/{idea['id']}">Ask the company to evaluate it</a>
          <a class="btn" href="/edit/{idea['id']}">Edit</a>
          <a class="btn ghost" href="/close/{idea['id']}">Not building this</a></div>"""
    body = f"""
    <div class="head"><div><div class="k">Idea &middot; saved, not evaluated</div>
      <h1 style="margin-top:6px">{e(idea['title'] or 'Untitled idea')}</h1>
      <div class="meta" style="margin-top:10px"><span class="st {e(idea['status'])}">{e(idea['status'])}</span>
        <span>{e(_ago(idea['created_at']))}</span></div></div></div>
    {flash_html}
    {f'<div class="banner red"><b>The last evaluation did not finish.</b> {e(idea["last_error"])}</div>'
      if idea.get("last_error") else ""}
    <div class="cols"><aside class="side">
      <div class="you"><div class="k" style="color:var(--gray);margin-bottom:8px">You said &middot;
        never edited</div><div class="q">&ldquo;{e(idea['raw_idea'])}&rdquo;</div></div>
      </aside><main>{state}{acts}{panel}</main></div>"""
    return shell("Idea Desk", body, crumb=f"/ <b>{e(idea['title'] or 'Idea')}</b>")


def _action_bar(idea, shown, token: str) -> str:
    if idea["status"] == "approved":
        return f"""<div class="bar"><div class="bar-in">
          <span class="why">Approved. Starting work is the next step, and it is deliberately not
          connected yet.</span>
          <a class="btn" href="/">Back to ideas</a>
          <form method="post" action="/api/start/{idea['id']}"><input type="hidden" name="token"
            value="{e(token)}"><button class="btn primary" type="submit">Start work</button></form>
        </div></div>"""
    if idea["status"] in ("parked", "dropped"):
        return f"""<div class="bar"><div class="bar-in">
          <span class="why">{'Parked. Reopening puts it back exactly where it was.'
                             if idea['status'] == 'parked'
                             else 'Dropped. It stays on record; reopening is allowed.'}</span>
          <a class="btn" href="/">Back to ideas</a>
          <form method="post" action="/api/reopen/{idea['id']}"><input type="hidden" name="token"
            value="{e(token)}"><button class="btn" type="submit">Reopen</button></form>
        </div></div>"""

    rec = shown["recommendation"]
    can = rec in APPROVABLE
    if can:
        approve = f"""<a class="btn ok" href="/approve/{idea['id']}">Approve brief</a>"""
        why = (f"Four things you can do with round {shown['round_no']}. "
               f"Nothing is built by any of them.")
    else:
        # No Approve, and the reason takes the explanatory slot rather than
        # trailing after the buttons — otherwise it wraps under them and reads
        # like a footnote to a decision the Founder cannot make yet.
        approve = ""
        why = (f'<b style="color:var(--text2)">No Approve on this round.</b> The company\'s own '
               f'recommendation is <b style="color:var(--text2)">{e(rec)}</b>, so there is nothing '
               f'to approve yet. Correct us, or narrow the idea, and let it read again.')
    return f"""<div class="bar"><div class="bar-in">
      <span class="why">{why}</span>
      <a class="btn ghost" href="/close/{idea['id']}">Not building this</a>
      <a class="btn" href="/edit/{idea['id']}">Edit my idea</a>
      <a class="btn" href="/correct/{idea['id']}">Correct us</a>
      {approve}</div></div>"""


# ------------------------------------------------------------- sub-panels ---

def correct_panel(idea, token: str) -> str:
    return f"""<div class="panel"><h3>Correct us: what did the company get wrong?</h3>
      <p>One or two lines is enough. This does not change your idea; the note is stored beside it, and
      the company re-reads both and comes back with a new round. If it is your idea you want to change,
      use Edit my idea instead.</p>
      <form method="post" action="/api/correct/{idea['id']}">
        <input type="hidden" name="token" value="{e(token)}">
        <textarea name="note" style="min-height:90px" required
          placeholder="almost there, but&hellip;"></textarea>
        <div class="actions" style="margin-top:12px">
          <button class="btn primary" type="submit">Send and re-evaluate</button>
          <a class="btn ghost" href="/idea/{idea['id']}">Cancel</a></div></form></div>"""


def close_panel(idea, token: str) -> str:
    return f"""<div class="panel"><h3>Not building this</h3>
      <p>Nothing is deleted. Your idea and everything the company said about it stay on record.
      <b>Park</b> means you may come back to it; <b>Drop</b> means you have decided against it. Either
      can be reopened.</p>
      <form method="post" action="/api/close/{idea['id']}">
        <input type="hidden" name="token" value="{e(token)}">
        <textarea name="reason" style="min-height:70px"
          placeholder="Why, in a line. Optional, but the record is better with it."></textarea>
        <div class="actions" style="margin-top:12px">
          <button class="btn" type="submit" name="how" value="parked">Park it</button>
          <button class="btn" type="submit" name="how" value="dropped">Drop it</button>
          <a class="btn ghost" href="/idea/{idea['id']}">Cancel</a></div></form></div>"""


def approve_panel(idea, rounds, token: str) -> str:
    r = rounds[-1]
    arts = [f"""<div class="art"><span class="k">Artifact 1</span>
             <span>Original idea, your words, verbatim</span><span class="m">kept</span></div>"""]
    for rr in rounds:
        note = " + your note" if rr["founder_note"] else ""
        arts.append(f"""<div class="art"><span class="k">Artifact 2 &middot; r{rr['round_no']}</span>
          <span>Company reading, round {rr['round_no']}{note}</span><span class="m">kept</span></div>""")
    arts.append(f"""<div class="art" style="border:1px solid oklch(72% 0.15 150 / .5)">
      <span class="k" style="color:var(--green)">Artifact 3</span>
      <span>Approved brief = round {r['round_no']}, frozen</span>
      <span class="m">created now</span></div>""")
    return f"""<div class="panel g"><h3>Approve round {r['round_no']} as the brief</h3>
      <p>From this point on, anyone working on this idea reads the approved brief, never your raw words
      and never an earlier round. Both stay stored underneath it, unchanged. Approving does not start
      any work.</p>
      <div class="arts">{''.join(arts)}</div>
      <form method="post" action="/api/approve/{idea['id']}">
        <input type="hidden" name="token" value="{e(token)}">
        <input type="hidden" name="round_id" value="{r['id']}">
        <div class="actions"><button class="btn ok" type="submit">Approve brief</button>
          <a class="btn ghost" href="/idea/{idea['id']}">Not yet</a></div></form></div>"""
