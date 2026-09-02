#!/usr/bin/env python3
"""ops/idea-desk/render_all_screens.py — render all 22 screens and check each.

Exists because HTTP-level testing passed 39 checks while the list page was
visibly broken: one long idea pushed its status pill and date off the screen.
Nothing that inspects response bodies catches that. This renders every screen
to HTML for a human to look at, and checks what a machine CAN judge — balanced
tags, no unescaped payloads, no visible "None", no unsubstituted placeholders.

    OUT=/tmp/screens OPSDB_PATH=/tmp/screens.sqlite3 python3 ops/idea-desk/render_all_screens.py

Scratch database only, auth stubbed in memory, no agents and no cost.

Screenshotting note, learned the hard way: chromium's --window-size does NOT
set the viewport (it clamps at about 485px and adds scrollbar width), and
--screenshot then captures only the window width. That crops the right edge and
looks exactly like a layout overflow. Measure with document.documentElement
.scrollWidth before believing a screenshot.
"""
import http.cookiejar
import importlib.util as iu
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

REPO = "/home/user/AI-Pipeline"
OUT = pathlib.Path(os.environ["OUT"])
OUT.mkdir(exist_ok=True)
PASS = "not-a-real-passphrase-0000"
PORT = 8493

sys.path.append(f"{REPO}/ops/control-center")
sys.path.insert(0, f"{REPO}/ops/idea-desk")
import founder_auth
founder_auth.credential_exists = lambda *a, **k: True
_real_verify = founder_auth.verify_passphrase
founder_auth.verify_passphrase = lambda p, *a, **k: p == PASS
sp = iu.spec_from_file_location("desk", f"{REPO}/ops/idea-desk/server.py")
server = iu.module_from_spec(sp); sp.loader.exec_module(server)
import evaluator

OPS = f"{REPO}/ops/db/opsdb.py"
def ops(*a):
    return subprocess.run([sys.executable, OPS, *a], capture_output=True, text=True)

# --- seed content that exercises the layout, including awkward text ---------
ops("init")
ops("idea-create", "--raw=a quiet place to write down half-thoughts before they escape",
    "--audience=me", "--trigger=I keep losing them in notes apps")
ops("idea-create", "--raw=--dark-mode but for calendars <script>alert(1)</script> & \"quotes\" 😀 "
                   "and a very long run of words that should wrap rather than blow out the column "
                   "width on the list page where it is truncated with an ellipsis")
ops("idea-create", "--raw=something the company likes")

ANSWERS = {str(n): [f"<b>Short answer {n}.</b> A couple of sentences that carry the actual point, "
                    f"long enough to wrap onto a second line in the card.",
                    f"<div class='sk'>Section {n}</div>The working behind it, with "
                    f"<span class='lab unk'>UNKNOWN</span> labels and a "
                    f"<div class='two'><div>left column</div><div>right column</div></div> split."]
           for n in range(1, 11)}
ROSTER = {"in": [["Product", "always on the roster"], ["CTO", "only CTO can say what the records hold"]],
          "out": [["CEO, Financial", "no market and no money in play"]]}
def view(rec, opp="Medium"):
    return {"opp": opp, "why": "Two to four sentences of closing judgement that should wrap "
                               "cleanly in the right-hand column of the company view grid.",
            "merit": "The single biggest merit.", "threat": "The single biggest threat.",
            "diff": "none we can see yet", "rec": rec}

ops("idea-round-add", "--idea-id", "2", "--title=Calendar dark mode",
    "--recommendation=Investigate first", "--depth=Full", "--depth-reason=Outside audience.",
    f"--roster={json.dumps(ROSTER)}", f"--answers={json.dumps(ANSWERS)}",
    f"--view={json.dumps(view('Investigate first', 'Unclear'))}")
ops("idea-round-add", "--idea-id", "3", "--title=A liked idea",
    "--recommendation=Proceed with narrowed scope", "--depth=Light", "--depth-reason=Internal.",
    f"--roster={json.dumps(ROSTER)}", f"--answers={json.dumps(ANSWERS)}",
    f"--view={json.dumps(view('Proceed with narrowed scope', 'High'))}")
ops("idea-round-add", "--idea-id", "3", "--title=A liked idea",
    "--recommendation=Proceed with narrowed scope", "--depth=Light", "--depth-reason=Internal.",
    "--founder-note=you missed that this is only for me",
    "--changed-note=Dropped the market framing entirely after your note.",
    f"--roster={json.dumps(ROSTER)}", f"--answers={json.dumps(ANSWERS)}",
    f"--view={json.dumps(view('Proceed with narrowed scope', 'High'))}")

httpd = server.ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{PORT}"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def fetch(path, post=None, expect=200):
    try:
        if post is None:
            r = op.open(B + path, timeout=30)
        else:
            body = urllib.parse.urlencode({**post, "token": server.SESSION_TOKEN}).encode()
            r = op.open(urllib.request.Request(B + path, data=body), timeout=30)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode()

PROBLEMS = []
def capture(name, path, post=None, expect=200):
    status, html = fetch(path, post)
    (OUT / f"{name}.html").write_text(html)
    issues = []
    if status != expect:
        issues.append(f"HTTP {status}, expected {expect}")
    # structural checks that catch a broken render without a human looking
    if "<body>" not in html:
        issues.append("no <body>")
    for tag in ("div", "main", "aside", "form"):
        if html.count(f"<{tag}") - html.count(f"</{tag}") not in (0,):
            issues.append(f"unbalanced <{tag}>: {html.count(f'<{tag}')} open, {html.count(f'</{tag}>')} close")
    if "None" in re.sub(r"<[^>]*>", "", html):
        issues.append("the literal text 'None' is visible on the page")
    if "{" in re.sub(r"<style>.*?</style>", "", html, flags=re.S).replace("&#", ""):
        stray = re.findall(r"\{[a-z_]+\}", html)
        if stray:
            issues.append(f"unsubstituted placeholder: {stray[:3]}")
    if "alert(1)" in html and "&lt;script&gt;" not in html:
        issues.append("unescaped script payload")
    if issues:
        PROBLEMS.append((name, issues))
    print(f"  {'ok  ' if not issues else 'BAD '} {name:<26} HTTP {status}"
          + ("" if not issues else "  <-- " + "; ".join(issues)))

print("\nSCREENS\n" + "-" * 70)
capture("01-login-signed-out", "/", expect=200)
capture("02-login-wrong-pass", "/api/login", {"passphrase": "wrong"}, expect=401)
fetch("/api/login", {"passphrase": PASS})
capture("03-list", "/")
capture("04-new-idea-form", "/new")
capture("05-draft-idea", "/idea/1")
capture("06-evaluate-disclosure", "/evaluate/1")
capture("07-evaluated-blocked", "/idea/2")
capture("08-evaluated-approvable", "/idea/3")
capture("09-correct-panel", "/correct/3")
capture("10-close-panel", "/close/3")
capture("11-approve-panel", "/approve/3")
capture("12-approve-refused-on-blocked", "/approve/2", expect=409)
capture("13-edit-form", "/edit/3")
capture("14-not-found", "/idea/9999", expect=404)
capture("15-bad-id", "/idea/notanumber", expect=404)

# states that need a write first
fetch("/api/close/1", {"how": "parked", "reason": "not now"})
capture("16-parked", "/idea/1")
capture("17-evaluate-refused-on-parked", "/evaluate/1", expect=409)
fetch("/api/reopen/1", {})
fetch("/api/approve/3", {"round_id": "3"})
capture("18-approved", "/idea/3")
capture("19-start-work-wall", "/api/start/3", {}, expect=200)

# the in-progress screen, without running anything
ops("idea-evaluation-start", "--idea-id", "1", "--note=a correction of mine")
evaluator._note(1, "Chief of Staff", "Choosing who should weigh in on this idea.")
evaluator._note(1, "Product", "Reading it.")
capture("20-evaluating", "/idea/1")
capture("21-approve-refused-mid-eval", "/approve/1", expect=409)
ops("idea-evaluation-end", "--idea-id", "1", "--error=Something went wrong reading this one.")
capture("22-after-a-failed-evaluation", "/idea/1")

print("\n" + "=" * 70)
if PROBLEMS:
    print(f"{len(PROBLEMS)} SCREEN(S) WITH PROBLEMS:")
    for name, issues in PROBLEMS:
        print(f"   {name}: {'; '.join(issues)}")
    sys.exit(1)
print(f"All {len(list(OUT.glob('*.html')))} screens rendered cleanly")
print("=" * 70)
