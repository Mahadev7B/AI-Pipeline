#!/usr/bin/env python3
"""ops/idea-desk/seed_founder_idea.py — put the Founder's own first idea into
the real database, with the two rounds it actually went through.

This is the idea that started TASK-026, in the Founder's own words, and the
correction they actually sent when round 1 read it wrong. It is seeded rather
than generated because slice 2 — the part that runs real agents — is not built
yet, and an Idea Desk with nothing in it teaches the Founder nothing about
whether the journey works.

Every word of both rounds was written by the company during this project; none
of it is invented for the demo. When slice 2 lands, new rounds come from real
agent runs and these stay as the historical first two.

Safe to run more than once: it refuses if the idea is already there.
"""
from __future__ import annotations

import json
import subprocess
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
OPSDB = REPO / "ops" / "db" / "opsdb.py"
DB = REPO / "ops" / "db" / "operations.sqlite3"

RAW = ("the current UI so much verbose, it should be as simple as a dashboard, "
       "I'M THINKING like an ellipse where we can track flow")
CORRECTION = ("almost there, UI i'm talking about is UI of my factory to track the app progress, "
              "once done the app( which is a child of my factory will hve another UI which is "
              "unrelated to ours) you got it?")

R1_ROSTER = {
    "in": [
        ["Product", "always on the roster; owns the problem, the scope and the first version."],
        ["Design", "the idea names a shape (an ellipse) before it names what goes on it; Design has "
                   "to say whether the shape earns its place."],
        ["Red Team", "the fastest way to find out if a screen can be filled honestly is to ask who "
                     "will try to break it."],
    ],
    "out": [
        ["CEO, Financial, Security", "no market, no cost structure, no sensitive data in play."],
        ["CTO", "not consulted this round; nothing about the records was asked. This turned out to "
                "be the mistake."],
    ],
}

R1 = {
    "1": ["<b>We read this as a request for a progress screen for the app the factory is building</b> "
          "&mdash; one page where you see how far along your product is, instead of reading task records.",
          "<div class='sk'>1 &middot; Original idea</div>Preserved verbatim on the left."
          "<div class='sk'>2 &middot; What we think you mean</div>A single progress view, replacing the "
          "thirteen text-heavy tabs, whose subject is the product under construction."],
    "2": ["You want to open the app and know, within seconds and without reading, how close it is to done.",
          "<div class='sk'>3 &middot; What you are really trying to achieve</div>The outcome is "
          "legibility, not a chart. &ldquo;Verbose&rdquo; is the complaint; &ldquo;dashboard&rdquo; and "
          "&ldquo;ellipse&rdquo; are your sketch of the remedy."],
    "3": ["<b>The merit is real and it is in the legibility, not the ellipse.</b> Today every screen "
          "makes you read to learn what state something is in. A view that shows state instead of "
          "describing it is a genuine improvement for the one person it is for.",
          "<div class='sk'>4 &middot; Why this may be valuable</div>Speed to understanding &middot; "
          "removes reading &middot; one place instead of thirteen. Weak merit we will not inflate: it "
          "does not make the factory build anything faster."],
    "4": ["<b>We don't know, and here is why.</b> Product-progress dashboards exist in every project "
          "tool. We did not compare them because no agent in this company can browse the web, and for "
          "an internal screen the comparison would not change the recommendation.",
          "<div class='sk'>5 &middot; Known competitors <span class='na'>NOT PRODUCED</span></div>Depth "
          "is Light.<div class='sk'>6 &middot; Competitor data freshness</div><b>Standing "
          "disclosure:</b> research has not been performed. Anything we say about third parties would "
          "be labelled <span class='lab'>COMPANY INFERENCE</span> or <span class='lab unk'>UNKNOWN</span>, "
          "never <span class='lab'>VERIFIED / CURRENT</span>."],
    "5": ["<b>We do not yet see a strong differentiation</b>, and at this depth we did not look for one. "
          "There is no market to be different in.",
          "<div class='sk'>7 &middot; Competitive advantages</div>Not produced as a market claim. "
          "Internally, the advantage over today is that a status is a claim and a movement is evidence."],
    "6": ["<b>Building a screen about the wrong subject.</b> If the thing you want to watch is not the "
          "app but something else, everything below is aimed at the wrong target. Second: the ellipse is "
          "the least certain part of the design and the idea commits to it first.",
          "<div class='sk'>8 &middot; Threats</div><b>Execution:</b> shape fixed before content is "
          "known. <b>Technical:</b> a screen is only as honest as the records behind it; we did not "
          "check them this round."],
    "7": ["<b>Proceed with narrowed scope: build one progress screen for the app, and do not commit to "
          "the ellipse yet.</b> One page, one subject, honest about what it cannot show. Postponed: "
          "motion, percentages and the ring itself.",
          "<div class='sk'>9 &middot; Recommended direction</div>Legibility is the requirement; geometry "
          "is a guess.<div class='two' style='margin-top:8px'><div><div class='sk'>10 &middot; In scope "
          "now</div>One screen &middot; stage of the app &middot; what is stopping it &middot; whose "
          "turn</div><div><div class='sk'>10 &middot; Not in the first version</div>Ellipse geometry "
          "&middot; animation &middot; percentages</div></div><div class='sk'>12 &middot; "
          "Alternatives</div>One: fix the navigation instead of the screen."],
    "8": ["One that could change everything: <b>that the subject of the screen is the app the factory "
          "builds.</b> If the subject is the factory itself, this is a different brief.",
          "<div class='sk'>11 &middot; Important assumptions</div>Subject = the child app &middot; one "
          "user, one machine &middot; &ldquo;simple&rdquo; means fewer things on screen, not fewer "
          "capabilities."],
    "9": ["One. <b>Is the subject of this screen the app, or the factory?</b> Two honest answers give "
          "two different briefs, which is the only reason it is here. You can approve without answering; "
          "we proceed on the assumption above.",
          "<div class='dec'><div style='font-weight:600;color:var(--text);margin-bottom:4px'>Is the "
          "subject the app, or the factory that builds it?</div><div style='font-size:12.5px'>"
          "<i style='color:var(--text);font-style:normal;font-weight:600'>What changes:</i> the app, and "
          "the screen shows the product's progress toward release. The factory, and it shows gates, "
          "owners and stalls across every product it is building.</div></div>"],
    "10": ["You open it, and in under ten seconds you can say what stage the app is at and what is "
           "stopping it, without opening anything else.",
           "<div class='sk'>14 &middot; Definition of success</div>QA test: a person who has never seen "
           "the records answers &ldquo;where is it and what is it waiting on&rdquo; correctly from this "
           "screen alone."],
}

R1_VIEW = {
    "opp": "High",
    "why": "The complaint is observed, not assumed: the current screens make you read to learn state. "
           "The fix is cheap relative to what it removes. The one thing that could sink it is the "
           "subject question, and that is one answer away.",
    "merit": "It replaces reading with looking.",
    "threat": "We may have understood the subject wrong.",
    "diff": "None we can see, and we did not look — there is no market here.",
    "rec": "Proceed with narrowed scope",
}

R2_ROSTER = {
    "in": [
        ["Product", "always on the roster; owns the problem, the scope and the first version."],
        ["CTO", "added this round. Only CTO can say what the records actually hold, which decides what "
                "this screen can honestly show."],
        ["Red Team", "the idea names a shape before naming its contents; that is the risk worth stating."],
    ],
    "out": [
        ["Design", "dropped this round; the question is no longer what the shape should be but what the "
                   "records can support."],
        ["CEO, Financial, Security", "no market, no cost structure, no sensitive data in play."],
    ],
}

R2 = {
    "1": ["<b>Yes, now.</b> The screen is the factory's own: it tracks how each child product is "
          "progressing through the company. The child product gets its own, unrelated UI later. Round 1 "
          "had the subject backwards; your note fixed it.",
          "<div class='sk'>1 &middot; Original idea</div>Preserved verbatim on the left, together with "
          "your round-1 correction.<div class='sk'>2 &middot; What we think you mean</div>A factory "
          "console whose unit is a build: what is being made, which gate it is at, whose turn it is, "
          "what is stopping it."],
    "2": ["You want to open the AI Factory and understand within seconds how each child product is "
          "progressing, without reading internal task records.",
          "<div class='sk'>3 &middot; What you are really trying to achieve</div>Not &ldquo;a "
          "dashboard&rdquo;. Legibility of the factory's work, for its owner, at a glance."],
    "3": ["<b>The merit is in the legibility, not the ellipse.</b> Today's screens report state as text "
          "you have to read. A screen that shows movement lets you look instead. <b>If the loop gets "
          "drawn and the records behind it stay thin, the screen is prettier and no more informative.</b>",
          "<div class='sk'>4 &middot; Why this may be valuable</div>Speed to understanding &middot; one "
          "place instead of thirteen &middot; built for the person who looks at it daily &middot; it "
          "also exposes, usefully, where the factory records nothing."],
    "4": ["<b>We don't know, and here is why.</b> This is our own operating console; nobody outside the "
          "company chooses between it and something else, so what exists cannot change the "
          "recommendation. That is not evidence nothing comparable exists, and no agent here can browse "
          "the web, so we could not have checked.",
          "<div class='sk'>5 &middot; Known competitors <span class='na'>NOT PRODUCED</span></div>Depth "
          "is Light and there is no external chooser.<div class='sk'>6 &middot; Competitor data "
          "freshness</div><b>Standing disclosure:</b> research has not been performed. Wherever this "
          "section has content it is company recollection, labelled <span class='lab'>COMPANY "
          "INFERENCE</span> or <span class='lab unk'>UNKNOWN</span>. <span class='lab'>VERIFIED / "
          "CURRENT</span> cannot honestly appear today."],
    "5": ["<b>We do not yet see a strong differentiation</b>, and at this depth we did not look for one. "
          "Inside the company there is one real difference: today a status is a claim, on this screen a "
          "movement is evidence.",
          "<div class='sk'>7 &middot; Competitive advantages</div>Not produced as a market claim. The "
          "internal advantage is checkable and it is not competitive."],
    "6": ["<b>The data.</b> Step records exist on 1 of 24 tasks, so there is no honest percentage. "
          "Twenty of 24 tasks are not linked to a product, so &ldquo;which app is this for&rdquo; is "
          "unanswerable for most work. No agent writes a live-run row, so there is nothing to animate. "
          "<b>A loop with nothing moving on it is worse than the list it replaced.</b>",
          "<div class='sk'>8 &middot; Threats, by category</div><b>Technical:</b> the records cannot "
          "support the picture. Changes how we build it: the first version renders absent data as "
          "absent, not as zero.<br><b>Execution:</b> form fixed before content is known. Changes what we "
          "build first: the one-glance screen, then decide the shape.<br><span "
          "style='color:var(--text3)'>Competitive, market, business, regulatory: not produced. None "
          "could change whether or how we build an internal console.</span>"],
    "7": ["<b>Proceed with narrowed scope: build the one-glance screen, and do not commit to the ellipse "
          "yet.</b> One screen whose subject is the build: what the factory is making, which of the six "
          "gates it has passed, whose turn it is, what is stopping it. Honest about what the records "
          "cannot support. Postponed on purpose: motion, percentages, and the ring geometry, until one "
          "real build has run through.",
          "<div class='sk'>9 &middot; Why this and not something else</div>&ldquo;Understand within "
          "seconds&rdquo; is a legibility requirement, not a geometry requirement. Committing the shape "
          "now freezes the least certain decision first.<div class='two' style='margin-top:8px'><div>"
          "<div class='sk'>10 &middot; In scope now</div>One Build screen &middot; six-stage gate ladder "
          "instead of a percentage &middot; last event and how long ago &middot; whose turn it is "
          "&middot; what is stopping it</div><div><div class='sk'>10 &middot; Not in the first version"
          "</div>The ellipse as a commitment &middot; motion (nothing writes it today) &middot; any "
          "percentage &middot; anything per-agent &middot; multi-user</div></div><div class='sk'>12 "
          "&middot; Alternatives worth considering &mdash; two</div><b>Fix the navigation instead of the "
          "screen.</b> What triggered this was not finding a page; thirteen destinations may be the "
          "problem, not the text.<br><b>Wait for one real end-to-end build first.</b> The screen designs "
          "itself once something has actually run through.<br><span style='color:var(--text3)'>Two, not "
          "three. We are not adding a third to look thorough.</span>"],
    "8": ["Two that could change the answer. <b>That &ldquo;as simple as a dashboard&rdquo; means fewer "
          "things on one screen, not fewer capabilities behind it.</b> And <b>that the unit on the "
          "screen is a build, not an agent.</b> If either is wrong, say so and we redo the brief.",
          "<div class='sk'>11 &middot; Important assumptions</div><b>Simplify means consolidate, not "
          "delete.</b> If you meant delete, scope shrinks and several records stop being shown "
          "anywhere.<br><b>The unit is a build, not an agent.</b> If you want to watch agents rather "
          "than work, this is a different screen.<br><b>One user, one machine.</b> No sharing, "
          "permissions or multi-user designed in.<br><span style='color:var(--text3)'>Three, and no "
          "more.</span>"],
    "9": ["One. <b>Is the ellipse a requirement, or your sketch of one?</b> You can approve without "
          "answering; if you do, we treat it as a sketch and Design tests it against two other forms.",
          "<div class='dec'><div style='font-weight:600;color:var(--text);margin-bottom:4px'>Is the "
          "ellipse a requirement, or a sketch?</div><div style='font-size:12.5px'><i style='color:"
          "var(--text);font-style:normal;font-weight:600'>What changes:</i> a sketch, and Design tests "
          "the ring against two or three other forms and picks on evidence. A requirement, and we build "
          "the ring and accept the data risk in question 6.</div></div><div style='margin-top:10px;"
          "color:var(--text3);font-size:12.5px'>Round 1's question (app or factory?) is answered by your "
          "note and no longer appears.</div>"],
    "10": ["You open the factory, and in under ten seconds you can say, for each product it is building, "
           "which gate it is at and what is stopping it, without opening a task record. Where the "
           "records are silent, the screen says so instead of guessing.",
           "<div class='sk'>14 &middot; Definition of success</div>For Design: the screen answers "
           "&ldquo;where is it, whose turn, what is it waiting on&rdquo; for every build without a "
           "click. For Development: absent data renders as absent. For QA: a first-time viewer answers "
           "those three questions correctly from the screen alone, and no number on the screen is "
           "invented."],
}

R2_VIEW = {
    "opp": "High",
    "why": "The problem is observed rather than assumed: you could not find a page that exists, and "
           "today's screens make you read to learn state. The fix is small relative to what it removes. "
           "The one real risk is that the records are too thin to fill it, and the narrowed scope is "
           "designed around exactly that.",
    "merit": "It replaces reading with looking, for the one person it is for, on the product that is "
             "the point.",
    "threat": "There may not be enough truthful data to fill it. A loop with nothing moving on it is "
              "worse than the list it replaced.",
    "diff": "None we can see, and we did not look. Internally: a status is a claim, a movement is "
            "evidence.",
    "rec": "Proceed with narrowed scope",
}

R2_CHANGED = ("Subject corrected from the child app to the factory itself. CTO joined the roster to "
              "check the records; Design dropped. Question 6 is new (the data). Round 1's Founder "
              "question is answered and removed; one new question replaces it.")


def run(*args: str) -> str:
    proc = subprocess.run([sys.executable, str(OPSDB), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit((proc.stderr or proc.stdout).strip())
    out = proc.stdout.strip()
    print("  " + out)
    return out


def main() -> None:
    # A fresh clone has no database — it is deliberately not in git (DEC-019).
    # Opening it read-only first died with a traceback (QA).
    if not DB.exists():
        print("No database yet — creating it.")
        subprocess.run([sys.executable, str(OPSDB), "init"], check=True,
                       capture_output=True, text=True)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        existing = conn.execute("SELECT id FROM ideas WHERE raw_idea = ?", (RAW,)).fetchone()
    except sqlite3.OperationalError:
        # Database exists but predates the ideas tables.
        subprocess.run([sys.executable, str(OPSDB), "init"], check=True,
                       capture_output=True, text=True)
        existing = None
    finally:
        conn.close()
    if existing:
        raise SystemExit(f"Already seeded as idea id={existing[0]} — nothing to do.")

    print("Seeding the Founder's first idea:")
    out = run("idea-create", f"--raw={RAW}",
              "--audience", "Me. The founder, on my own machine.",
              "--trigger", "I could not find the meetings page; thirteen tabs of text.")
    idea_id = out.rsplit("id=", 1)[-1].strip()

    run("idea-round-add", "--idea-id", idea_id,
        "--title", "Progress dashboard for the app",
        "--recommendation", "Proceed with narrowed scope",
        "--depth", "Light",
        "--depth-reason", "An internal screen for one user. Nothing outside the company changes because "
                          "of it, so the market sections are not worth their cost.",
        "--roster", json.dumps(R1_ROSTER), "--answers", json.dumps(R1), "--view", json.dumps(R1_VIEW))

    run("idea-round-add", "--idea-id", idea_id,
        "--title", "Factory tracking screen for child products",
        "--recommendation", "Proceed with narrowed scope",
        "--depth", "Light",
        "--depth-reason", "Still an internal screen for one user. The correction changed the subject, "
                          "not the depth.",
        "--roster", json.dumps(R2_ROSTER), "--answers", json.dumps(R2), "--view", json.dumps(R2_VIEW),
        "--changed-note", R2_CHANGED, "--founder-note", CORRECTION)

    print(f"\nDone. Open http://127.0.0.1:8421/idea/{idea_id}")


if __name__ == "__main__":
    main()
