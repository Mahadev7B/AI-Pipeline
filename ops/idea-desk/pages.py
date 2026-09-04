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

# Kept in step with evaluator.NO_WORKING. When an answer has no working behind
# it the page says so once, quietly, instead of offering an empty expander.
# NOTE the literal em dash: safe_html() escapes &<>"' and leaves it alone, so
# writing &mdash; here would never match what actually arrives.
NO_WORKING_HTML = "No further working \u2014 the concise answer is the whole of it."

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
/* Every grid column below uses minmax(0,1fr), never a bare 1fr: a bare 1fr
   track refuses to shrink below its content, so one long idea pushed the
   status pill and date clean off the list page, and the stored-versions card
   ran off the right edge of a phone. Found by looking at the rendered pages,
   which no amount of HTTP-level testing had caught. */
.row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,290px) auto;gap:22px;align-items:center;
     padding:18px 6px;border-bottom:1px solid var(--border);}
.row:hover{background:var(--panel);}
.row .t{font-size:15.5px;font-weight:600;color:var(--text);}
.row .d{font-size:13px;color:var(--text2);margin-top:4px;overflow:hidden;text-overflow:ellipsis;
        white-space:nowrap;}
.row .when{font-size:12px;color:var(--text3);text-align:right;}
.empty{padding:32px 0;color:var(--text3);font-size:13.5px;}
h2{font-size:16px;font-weight:600;letter-spacing:-0.01em;margin:0;}
.row .tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px;}
.tag{font-size:10.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--text3);
     border:1px solid var(--border);border-radius:5px;padding:2px 7px;}
.row .state{text-align:right;}
.row .state .lastly{font-size:12.5px;color:var(--text2);margin-top:7px;max-width:40ch;
                    margin-left:auto;line-height:1.5;}
.row .state .when{font-size:11.5px;color:var(--dim);margin-top:4px;}
.row .act{display:flex;justify-content:flex-end;}
@media (max-width:760px){
  .row .state{text-align:left;} .row .state .lastly{max-width:none;}
  .row .act{justify-content:flex-start;}
}
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
@media (max-width:900px){
  .cols{grid-template-columns:minmax(0,1fr);gap:24px;}
  .side{position:static !important;}
}
/* A pasted URL or an unbroken run of characters must wrap rather than widen
   its container — everything here renders text the Founder or an agent wrote. */
.you .q,.banner,.hist,.qa .a,.xin,.cvg .val,.h-item,.row .t{overflow-wrap:anywhere;}
@media (max-width:760px){
  .wrap{padding:0 18px 140px;}
  .row{grid-template-columns:minmax(0,1fr);gap:8px;padding:16px 4px;}
  .row .when{text-align:left;}
  .topright{display:none;}          /* the tagline is the first thing to go */
  .brand{white-space:nowrap;}
  .crumb{display:none;}
  .top-in,.bar-in{padding:12px 18px;}
  .head{gap:12px;}
  .voices{gap:10px;}
  h1{font-size:24px;}
}
.side{position:sticky;top:64px;display:flex;flex-direction:column;gap:18px;}
.you{border-left:3px solid var(--gray);padding:2px 0 2px 14px;}
.you .q{white-space:pre-wrap;font-size:14px;line-height:1.6;color:var(--text);}
.you .aud{margin-top:10px;font-size:12.5px;color:var(--text2);}
.hist{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 16px;}
.h-item{display:grid;grid-template-columns:18px minmax(0,1fr);gap:10px;padding:8px 0;border-top:1px solid var(--hair);
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
.q ul,.xin ul{margin:8px 0 0;padding-left:18px;}
.q li,.xin li{margin:4px 0;}
details.x{margin-top:10px;}
.nowork{margin-top:10px;font-size:12.5px;color:var(--gray);font-style:italic;}
/* The Research lane's evidence. Styled so the eye lands on the CLAIM first and
   the source second — a wall of links reads as decoration, and the Founder's
   question is "what is already out there", not "which sites did you open". */
.fbot{font-size:13.5px;line-height:1.65;}
.fcat{margin-bottom:16px;}
.fcat-h{font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
        color:var(--text3);margin-bottom:8px;}
.fnd{padding:9px 0 9px 12px;border-left:2px solid var(--border2);margin-bottom:8px;}
.fnd.moved{border-left-color:var(--green);}
.fc{font-size:13px;line-height:1.55;}
.fd{font-size:12.5px;color:var(--text2);margin-top:4px;}
.fs{font-size:11.5px;color:var(--text3);margin-top:5px;}
.fs a{color:var(--accent);}
.moved-tag{margin-left:8px;color:var(--green);font-size:10.5px;font-weight:700;
           letter-spacing:.04em;text-transform:uppercase;}
.fw{font-size:12.5px;color:var(--text);margin-top:5px;}
.fnote{margin-top:14px;font-size:12.5px;color:var(--text2);}
.fnote b{color:var(--text);}
/* Unverified claims get the same visual weight as a warning, deliberately.
   They are the ones most likely to be read as fact and quoted onwards. */
.fnote.warn{border-left:2px solid var(--accent);padding-left:12px;}
.fsmall{margin-top:16px;font-size:11.5px;color:var(--text3);line-height:1.6;}
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
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;}
@media (max-width:640px){.two{grid-template-columns:minmax(0,1fr);}}
.dec{border:1px solid var(--border);border-radius:9px;padding:12px 14px;margin-top:10px;
     background:var(--panel2);}
.cv{margin-top:22px;border-radius:14px;border:1px solid oklch(72% 0.13 300 / .55);background:var(--panel);
    padding:20px 22px;}
.cv .cvh{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px;
         align-items:baseline;}
.cv .cvh .k{color:var(--violet);}
.cvg{display:grid;grid-template-columns:150px minmax(0,1fr);gap:13px 20px;align-items:baseline;}
.cvg .k{text-align:right;}
.cvg .val{font-size:13.5px;line-height:1.65;color:var(--text);}
.cvg .opp{font-size:15px;font-weight:700;}
.rec{display:inline-block;padding:6px 14px;border-radius:8px;border:1px solid var(--accent);
     background:var(--accent-soft);color:var(--accent);font-weight:700;font-size:13px;}
@media (max-width:640px){.cvg{grid-template-columns:minmax(0,1fr);} .cvg .k{text-align:left;}}
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
.art{display:grid;grid-template-columns:minmax(0,130px) minmax(0,1fr) auto;gap:12px;align-items:baseline;padding:9px 12px;
     border-radius:8px;background:var(--panel2);font-size:13px;}
.art .m{font-family:var(--mono);font-size:11.5px;color:var(--text3);}
.foot{margin-top:60px;padding-top:18px;border-top:1px dashed var(--border2);font-size:12px;
      color:var(--text3);line-height:1.7;max-width:72ch;}
.login{max-width:420px;margin:14vh auto;padding:0 24px;}
"""


REHEARSAL_BANNER = (
    '<div class="banner" style="border-color:oklch(78% 0.14 75 / .5);background:var(--accent-soft)">'
    '<b>This was a rehearsal.</b> No agent read your idea and nothing was spent &mdash; the answers '
    'below are placeholders so the screens can be walked for free. Evaluate again with rehearsal '
    'mode off for the company&rsquo;s real reading. A brief cannot be approved from a rehearsal.'
    '</div>')

COST_DISCLOSURE = (
    '<div class="banner" style="margin:0 0 14px;border-color:oklch(78% 0.14 75 / .4);'
    'background:var(--accent-soft);color:var(--text)"><b>This one spends money.</b> Several agents '
    'run, each a real model call, and it takes a few minutes. Everything else in the Idea Desk is '
    'free; this is the step that is not. Whether that is an actual charge or a draw on a '
    'subscription depends on how the account behind your <code>claude</code> command is '
    'billed &mdash; either way it is real usage, and there is no estimate available '
    'beforehand.</div>')

REHEARSAL_DISCLOSURE = (
    '<div class="banner" style="margin:0 0 14px;border-color:oklch(72% 0.15 150 / .5);'
    'background:var(--green-soft);color:var(--text)"><b>Rehearsal mode is on, so this costs '
    'nothing.</b> No agent will be asked and no model call will be made. You get placeholder '
    'answers so every screen can be walked for free. The round is marked as a rehearsal and cannot '
    'be approved.</div>')


def e(s) -> str:
    return html.escape("" if s is None else str(s))


# The ten answers are written by agents, and agent output is not trusted input
# just because it came from our own company. Everything is escaped first, then
# the small set of tags the answer format actually needs is put back. Nothing
# else survives — no links, no scripts, no attributes but the class names below.
# <code> is here because failure messages give the Founder a command to run
# and a diagnostics file to look at. Escaped, those arrived with the literal
# tags showing, which is the one moment the message most needs to be clear.
# <ul>/<li> so a list of three things can BE a list. Without them the
# answers ran everything together into one block, and the Founder said
# plainly that the writing was hard to pay attention to.
_SIMPLE_TAGS = "b|i|em|strong|br|code|ul|li"
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
    # Balance every container we allow, so a stray tag can never escape the card
    # it was written into. Divs AND the inline formatting tags: b/i/em/strong
    # are active-formatting elements, which the HTML parser reconstructs past a
    # closing </div>, so an unclosed <b> really does leak out (Code Review,
    # catch-up — the earlier version balanced divs only while claiming
    # otherwise).
    open_stack: list[str] = []
    balanced: list[str] = []
    for piece in re.split(r"(</?(?:div|b|i|em|strong|code|ul|li)(?:\s[^>]*)?>)", out):
        m = re.fullmatch(r"</?([a-z]+)(?:\s[^>]*)?>", piece)
        if not m:
            balanced.append(piece)
            continue
        tag = m.group(1)
        if piece.startswith("</"):
            if tag not in open_stack:
                continue  # a closer with no opener — drop it
            while open_stack and open_stack[-1] != tag:
                balanced.append(f"</{open_stack.pop()}>")
            open_stack.pop()
            balanced.append(piece)
        else:
            open_stack.append(tag)
            balanced.append(piece)
    balanced.extend(f"</{tag}>" for tag in reversed(open_stack))
    return "".join(balanced)


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

def _lifecycle(i: dict) -> tuple[str, str, str, str]:
    """Where this idea is, what happened last, and the one thing to do next.

    Every state here is one the data can actually prove. There is deliberately
    no "Building" or "Shipped" — Start Work is not built yet, and inventing a
    stage the factory cannot reach would be exactly the fake progress this
    company keeps promising not to show."""
    if i["evaluating_since"]:
        return ("working", "Being read",
                "The company is reading it now. This takes a few minutes.",
                "")
    if i["last_error"]:
        return ("working", "Didn't finish",
                "The last reading failed. Nothing was saved, and your idea and its history are "
                "untouched.",
                "Ask the company to read it again")
    if i["status"] == "approved":
        return ("working", "Approved",
                "You approved this brief. Nothing is being built yet.",
                "Start work")
    if i["status"] == "parked":
        return ("backlog", "Parked",
                i["close_reason"] or "Saved for later.", "Reopen")
    if i["status"] == "dropped":
        return ("archive", "Dropped",
                i["close_reason"] or "Decided against.", "Reopen")
    if i.get("investigation_round_id"):
        # NOT a status: no brief is frozen and artifact 3 does not exist. But
        # the Founder authorised real work, and a screen that looks identical
        # afterwards is exactly the dead end this was built to remove.
        return ("working", "Investigating",
                f"Round {i['rounds']}: you authorised the investigation the company asked for. "
                "No brief is approved and nothing is in production.",
                "Start the investigation")
    if i["rounds"]:
        # The pill stays short so it scans; the verdict goes in the line below,
        # where it has room. "READ — PROCEED WITH NARROWED SCOPE" as an
        # uppercase letter-spaced pill wraps to two lines and reads worse.
        rec = i["recommendation"] or "Read"
        approvable = rec in APPROVABLE
        return ("working", "Read",
                f"Round {i['rounds']}: {rec}."
                + ("" if approvable else " Not recommending you build it yet."),
                "Approve the brief" if approvable
                else ("Authorise the investigation" if rec == "Investigate first" else "Correct us"))
    return ("working", "Saved",
            "Nobody has read it yet. Saving costs nothing.",
            "Ask the company to read it")


NEXT_HREF = {
    "Ask the company to read it again": "/evaluate/{id}",
    "Ask the company to read it": "/evaluate/{id}",
    "Correct us": "/correct/{id}", "Approve the brief": "/approve/{id}",
    "Reopen": "/idea/{id}", "Start work": "/idea/{id}",
    "Authorise the investigation": "/investigate/{id}",
    # Start Work is still a wall, and so is this. It leads to the same honest
    # 501 rather than to a page pretending work began.
    "Start the investigation": "/api/start/{id}",
}

BUCKETS = (
    ("working", "Working on",
     "Ideas the company is reading, has read, or you have approved."),
    ("backlog", "Idea backlog", "Parked on purpose. Reopen any of them."),
    ("archive", "Archive", "Dropped, and kept. Nothing here is deleted."),
)


def list_page(ideas: list, build: str = "") -> bytes:
    grouped: dict[str, list] = {"working": [], "backlog": [], "archive": []}
    for i in ideas:
        bucket, state, last, nxt = _lifecycle(i)
        grouped[bucket].append((i, state, last, nxt))

    sections = []
    for key, heading, blurb in BUCKETS:
        items = grouped[key]
        if not items and key != "working":
            continue          # empty backlog and archive are noise, not information
        rows = []
        for i, state, last, nxt in items:
            href = NEXT_HREF.get(nxt, "/idea/{id}").format(id=i["id"])
            action = (f'<a class="btn sm" href="{href}">{e(nxt)}</a>' if nxt else
                      '<span style="font-size:12px;color:var(--text3)">nothing to do</span>')
            tags = []
            if i.get("only_rehearsals"):
                tags.append('<span class="tag">rehearsal only</span>')
            if i.get("edits"):
                tags.append(f'<span class="tag">edited {i["edits"]}&times;</span>')
            if i["rounds"] > 1:
                tags.append(f'<span class="tag">{i["rounds"]} rounds</span>')
            rows.append(f"""<div class="row">
              <div><a class="t" href="/idea/{i['id']}">{e(i['title'] or 'Untitled idea')}</a>
                <div class="d">{e(i['current_raw'])}</div>
                <div class="tags">{''.join(tags)}</div></div>
              <div class="state"><span class="st {e(i['status'])}">{e(state)}</span>
                <div class="lastly">{e(last)}</div>
                <div class="when">{e(_ago(i['updated_at']))}</div></div>
              <div class="act">{action}</div></div>""")
        sections.append(f"""<section style="margin-top:34px">
          <div style="display:flex;align-items:baseline;gap:12px">
            <h2>{heading}</h2>
            <span style="font-size:12.5px;color:var(--text3)">{len(items)}</span></div>
          <p class="sub" style="margin:6px 0 0;font-size:13px;color:var(--text3)">{blurb}</p>
          <div class="list">{''.join(rows) or
            '<div class="empty">Nothing here yet. Every idea you save starts in this group.</div>'}</div>
        </section>""")

    body = f"""
    <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-top:40px;
                flex-wrap:wrap">
      <div><h1>Your ideas</h1>
        <p class="sub" style="margin:10px 0 0">Each one stays here for good &mdash; your original
        words, every reading the company gave it, every correction you made, and what you decided.
        Editing or re-evaluating continues the same idea rather than starting another.</p></div>
      <a class="btn primary" href="/new">+ New idea</a>
    </div>
    {''.join(sections)}
    <div class="foot">Stored in the factory's own database, so they survive closing this window.
    Saving an idea and reading past evaluations are free; asking the company to read one is the
    only step that uses anything.
    {f'<div style="margin-top:10px;color:var(--dim)">Running: {e(build)}</div>' if build else ''}</div>"""
    return shell("Idea Desk", body)


# ----------------------------------------------------------- the new form ---

def new_page(token: str, idea=None) -> bytes:
    editing = idea is not None
    raw = e(idea["current_raw"]) if editing else ""
    # "Who is it for" and "what made you think of it" used to be asked here and
    # sent to every agent as specification. A one-word answer typed in passing
    # became load-bearing: "the public" in that box produced a roster note
    # saying the idea was for the public, and then Product spent its reading
    # narrowing that word rather than the idea. Working out who it is for is
    # the company's job, not a form field. The columns stay for ideas that
    # already have them; nothing new is collected.
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


def evaluate_panel(idea, token: str, *, correcting: bool = False,
                   rehearsal: bool = False) -> str:
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
      {REHEARSAL_DISCLOSURE if rehearsal else COST_DISCLOSURE}
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
        # An answer with no working behind it says so in a plain line. It used
        # to get an expander like every other, which opened onto a stub — the
        # screen promising depth that was never written.
        if expanded == NO_WORKING_HTML:
            exp = f'<div class="nowork">{NO_WORKING_HTML}</div>'
        elif expanded:
            exp = (f"""<details class="x"><summary>Expanded &middot; {e(expands)}</summary>
                <div class="xin">{expanded}</div></details>""")
        else:
            exp = ""
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
    if "rehearsal" in shown.keys() and shown["rehearsal"]:
        banners += REHEARSAL_BANNER
    if idea.get("last_error"):
        # safe_html, not e(). A failure message is written by our own evaluator
        # and carries deliberate markup — the failing stage in <b>, the
        # diagnostics path in <code>, line breaks between an explanation and
        # the command that fixes it. e() escaped all of it, so every one of
        # those arrived with the literal tags showing, in the message that most
        # needs to be readable. safe_html still escapes everything first and
        # restores only the allowlist, so nothing gains privileges here.
        banners += (f'<div class="banner red"><b>The last evaluation did not finish.</b> '
                    f'{safe_html(idea["last_error"])}{_share_link(idea)}</div>')
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
        <div class="qs">{roster_block}{_evidence_block(shown)}{''.join(qs)}</div>
        {_company_view(view)}
        {panel}
      </main>
    </div>"""
    return shell("Idea Desk", body,
                 crumb=f"/ <b>{e(idea['title'] or 'Idea')}</b>",
                 bar=_action_bar(idea, shown, token))


def _evidence_block(shown) -> str:
    """What the Research lane found, shown so the Founder can check it.

    The point is not to dump sources. It is that every claim the company makes
    about the outside world can be traced to something the Founder can open —
    and that "we did not check" is stated in the same place, just as plainly,
    instead of being an absence they have to notice.
    """
    keys = shown.keys()
    status = (shown["research_status"] if "research_status" in keys else None) or "not-needed"

    if status == "not-needed":
        # Deliberately quiet. This is the normal case for an internal tool, and
        # a loud panel announcing that nothing was researched would make every
        # small idea look under-examined.
        return ("""<div class="qa" style="--v:var(--border2)">
          <div class="qh"><span class="qt" style="font-size:13.5px;color:var(--text2)">Outside
            research</span><span class="v" style="color:var(--text3)">not needed</span></div>
          <div class="a" style="font-size:13px;color:var(--text2)">Nobody searched the web for this
            one, because the answer did not depend on what is true outside the company. Anything
            said above about the wider world is the company's own recollection, not a checked
            fact.</div></div>""")

    if status == "unavailable":
        # The honest failure, and the reason the third status exists. Silence
        # here would read exactly like "we checked and there was nothing".
        return ("""<div class="qa need" style="--v:var(--accent)">
          <div class="qh"><span class="qt" style="font-size:13.5px">Outside research</span>
            <span class="v" style="color:var(--accent)">needed, but not done</span></div>
          <div class="a" style="font-size:13px">This idea's answer <b>does</b> depend on what is
            already out there &mdash; and the search could not be run this time. Nothing above has
            been checked against the real world. Treat every statement about existing products,
            prices or rules as unverified, and evaluate again when you want it checked
            properly.</div></div>""")

    packet = {}
    if "research_json" in keys and shown["research_json"]:
        try:
            packet = json.loads(shown["research_json"])
        except (json.JSONDecodeError, TypeError):
            packet = {}
        # Valid JSON that is not an OBJECT is still unusable here, and `.get`
        # on a list is an AttributeError that takes down the entire idea page
        # — not just this panel. Stored evidence is data this page did not
        # write, so its shape is checked rather than assumed.
        if not isinstance(packet, dict):
            packet = {}
    raw_findings = packet.get("findings")
    findings = ([f for f in raw_findings if isinstance(f, dict)]
                if isinstance(raw_findings, list) else [])

    def _moved(f) -> bool:
        """Did this finding change the company's ranking?

        Normalised rather than trusted. The evaluator's own _clean_packet
        stores a real bool, but this page also renders rounds it did not
        write — older ones, hand-seeded ones — and the raw contract value is
        the STRING "yes" or "no". A bare truthiness check marks every finding
        as decisive, including the ones that explicitly said "no", which is
        precisely the false confidence this lane exists to remove.
        """
        v = f.get("changes_ranking")
        if isinstance(v, str):
            return v.strip().lower() in ("yes", "true")
        return bool(v)
    n = (shown["research_searches"] if "research_searches" in keys else None) or 0
    searched = f"{n} search{'es' if n != 1 else ''}" if n else "a search"

    if not findings:
        return (f"""<div class="qa" style="--v:var(--border2)">
          <div class="qh"><span class="qt" style="font-size:13.5px;color:var(--text2)">Outside
            research</span><span class="v" style="color:var(--text3)">nothing found</span></div>
          <div class="a" style="font-size:13px">The company ran {e(searched)} and came back with
            nothing it could stand behind with a source. That is itself worth knowing: as far as
            this search could tell, nobody is doing this.</div></div>""")

    # Grouped by solution category, because the Founder's question is "what
    # else already does this", not "list some links". Ordering puts the
    # findings that CHANGED the company's ranking first — those are the ones
    # that did work, and the rest is background.
    by_cat: dict[str, list] = {}
    for f in findings:
        by_cat.setdefault(str(f.get("category") or "Other"), []).append(f)
    ordered = sorted(by_cat.items(),
                     key=lambda kv: (not any(_moved(x) for x in kv[1]), kv[0]))

    cats = []
    for cat, items in ordered:
        rows = []
        for f in items:
            url = str(f.get("url") or "")
            src = str(f.get("source") or "source")
            when = str(f.get("dated") or "")
            detail = str(f.get("detail") or "")
            mattered = _moved(f)
            link = (f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer nofollow">'
                    f'{e(src)}</a>' if url.startswith(("http://", "https://")) else e(src))
            rows.append(f"""<div class="fnd{' moved' if mattered else ''}">
              <div class="fc">{e(str(f.get('claim') or ''))}</div>
              {f'<div class="fd">{e(detail)}</div>' if detail else ''}
              <div class="fs">{link}{f' &middot; {e(when)}' if when else ''}
                {'<b class="moved-tag">changed our ranking</b>' if mattered else ''}</div>
              {f'<div class="fw">{e(str(f.get("why_it_matters") or ""))}</div>'
               if mattered and f.get('why_it_matters') else ''}</div>""")
        cats.append(f"""<div class="fcat"><div class="fcat-h">{e(cat)}</div>{''.join(rows)}</div>""")

    def _list(key, label, tone=""):
        raw = packet.get(key)
        vals = [str(x) for x in raw if str(x).strip()] if isinstance(raw, list) else []
        if not vals:
            return ""
        return (f'<div class="fnote {tone}"><b>{label}</b><ul>'
                + "".join(f"<li>{e(v)}</li>" for v in vals) + "</ul></div>")

    extras = (_list("contradictions", "Sources that disagree")
              + _list("unverified", "Believed, but NOT checked &mdash; treat as hearsay", "warn")
              + _list("unknown", "Still unknown after searching"))
    bottom = str(packet.get("bottom_line") or "")

    return f"""<div class="qa" style="--v:var(--green)">
      <div class="qh"><span class="qt" style="font-size:13.5px">What we actually found out there</span>
        <span class="v" style="color:var(--text3)">{len(findings)} source-backed
          &middot; {e(searched)}</span></div>
      <div class="a" style="font-size:13px">
        {f'<div class="fbot">{e(bottom)}</div>' if bottom else ''}
        <details class="x"><summary>The evidence, with its sources</summary>
          <div class="xin">{''.join(cats)}{extras}
            <div class="fsmall">Every line above was retrieved from the web during this
              evaluation. Anything the company said that is NOT here is its own recollection, not a
              checked fact. Prices and availability go stale &mdash; open a source before betting on
              it.</div></div></details></div></div>"""


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
        # Saying "nothing has been evaluated yet" directly beneath a banner
        # describing a failed evaluation is true of the STORED rounds and false
        # to the Founder, who just watched one run.
        state = ("""<div class="banner blue">No completed evaluation has been saved yet &mdash; the
          last attempt failed before it could be. Your idea and its history are untouched.</div>"""
                 if idea.get("last_error") else
                 """<div class="banner blue">Nothing has been evaluated yet. When you are ready, the
          company reads it and comes back with one answer.</div>""")
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
    {f'<div class="banner red"><b>The last evaluation did not finish.</b> '
      f'{safe_html(idea["last_error"])}{_share_link(idea)}</div>'
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
    elif rec == "Investigate first" and not idea.get("investigation_round_id"):
        # "Investigate first" is a recommendation to DO something — build a
        # throwaway prototype, put it in front of five people. Offering no
        # action at all made the company's most honest recommendation the one
        # dead end on the screen, where agreeing with it meant doing nothing.
        # This authorises that work and NOT a brief; the brief gate is
        # unchanged and still refuses anything but Proceed.
        approve = f"""<a class="btn ok" href="/investigate/{idea['id']}">Authorise investigation</a>"""
        why = ('The company wants to <b>find something out first</b>, and says what in answer 7. '
               'You can authorise that work &mdash; it is not a brief, and nothing goes into '
               'production.')
    elif idea.get("investigation_round_id"):
        approve = ""
        why = ('<b style="color:var(--text2)">Investigation authorised.</b> No brief is approved '
               'and nothing is in production. When it comes back with evidence, correct us and the '
               'company reads the idea again knowing something it does not know now.')
    else:
        # No Approve, and the reason takes the explanatory slot rather than
        # trailing after the buttons — otherwise it wraps under them and reads
        # like a footnote to a decision the Founder cannot make yet.
        approve = ""
        why = (f'<b style="color:var(--text2)">No Approve on this round.</b> The company\'s own '
               f'recommendation is <b style="color:var(--text2)">{e(rec)}</b>, so there is nothing '
               f'to approve yet. Correct us, or narrow the idea, and let it read again.')
    # "Read it again" was missing entirely. Once an idea had been read, the
    # only route to another reading was "Correct us", which requires writing
    # what the company got wrong. Sometimes there is nothing to correct and you
    # simply want it looked at again — after the company itself changed, or
    # because the first read was thin. The capability already existed at
    # /evaluate/<id>; nothing offered it.
    return f"""<div class="bar"><div class="bar-in">
      <span class="why">{why}</span>
      <a class="btn ghost" href="/close/{idea['id']}">Not building this</a>
      <a class="btn" href="/edit/{idea['id']}">Edit my idea</a>
      <a class="btn" href="/evaluate/{idea['id']}">Read it again</a>
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


def _share_link(idea) -> str:
    """Offered only when there is actually a file to send. A button that leads
    to "there is nothing here" is worse than no button."""
    if not idea.get("has_diagnostic"):
        return ""
    return (f'<div style="margin-top:12px"><a class="btn" href="/share/{idea["id"]}">'
            'Send this to the build side</a></div>')


def share_panel(idea, token: str, text: str, truncated: bool, name: str,
                already: bool) -> str:
    """Show the Founder EXACTLY what would be published, before publishing it.

    This file holds their idea in their own words and every agent's full
    reading. Git history does not forget, so a summary of what is in it would
    not be good enough — they read the thing itself, then decide."""
    warn = ("<b>This was already sent.</b> Sending it again changes nothing." if already else
            "Once this is on GitHub it is in the repository's history <b>permanently</b>. "
            "There is no unsend.")
    return f"""<div class="panel"><h3>Send this evidence to the build side</h3>
      <p>This commits one file &mdash; <code>ops/incidents/{e(name)}</code> &mdash; and pushes it,
      so whoever fixes the defect can read what actually happened without you having to find it,
      describe it, or carry it anywhere.</p>
      <p><b>It contains your idea in your own words and every role's full reading.</b> {warn}</p>
      <p style="color:var(--gray)">Nothing else is committed. Whatever else is in your working
      folder stays where it is.</p>
      <details open><summary>Everything that would be published, in full</summary>
        <pre style="white-space:pre-wrap;word-break:break-word;max-height:340px;overflow:auto;
             font-family:var(--mono);font-size:12px;line-height:1.5;background:var(--bg2);
             padding:12px;border-radius:8px">{e(text)}</pre>
        {'<p style="color:var(--gray)">Shown up to 20,000 characters; the whole file is sent.</p>'
         if truncated else ''}</details>
      <form method="post" action="/api/share/{idea['id']}" style="margin-top:14px">
        <input type="hidden" name="token" value="{e(token)}">
        <textarea name="note" style="min-height:70px"
          placeholder="Anything you noticed when it failed. Optional, and appended to the file."></textarea>
        <div class="actions" style="margin-top:12px">
          <button class="btn primary" type="submit">Send it</button>
          <a class="btn ghost" href="/idea/{idea['id']}">Cancel</a></div></form></div>"""


def investigate_panel(idea, rounds, token: str) -> str:
    """Authorising the work the company asked for — not a production brief.

    "Investigate first" is a recommendation to DO something: build a throwaway
    prototype, put it in front of five people. Treating it as "nothing to
    approve" made the company's most honest recommendation the one dead end on
    the screen, and left the Founder able to agree with it only by doing
    nothing."""
    r = rounds[-1]
    return f"""<div class="panel"><h3>Authorise the investigation</h3>
      <p>The company recommends <b>Investigate first</b> &mdash; it wants to find something out
      before anyone builds the real thing. This authorises <b>that work and nothing else</b>.</p>
      <div class="art" style="margin:14px 0"><span class="k">What it does not do</span>
        <span>It does not approve a brief, and nothing goes into production. The idea stays where
        it is; approving a brief still needs the company to recommend Proceed.</span>
        <span class="m">unchanged</span></div>
      <p style="color:var(--gray)">What the company wants to investigate is answer 7 on this
      round. When the investigation comes back with evidence, the company reads the idea again
      knowing something it does not know now.</p>
      <form method="post" action="/api/investigate/{idea['id']}">
        <input type="hidden" name="token" value="{e(token)}">
        <input type="hidden" name="round_id" value="{e(r['id'])}">
        <div class="actions" style="margin-top:12px">
          <button class="btn primary" type="submit">Authorise this investigation</button>
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
