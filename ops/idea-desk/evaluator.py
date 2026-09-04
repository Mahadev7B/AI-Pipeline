"""ops/idea-desk/evaluator.py — the company actually reading a Founder idea.

Three phases, matching DEC-014 and DEC-015:

  1. Chief of Staff picks who should weigh in on THIS idea, and how deep to go.
     Not everyone, by design — only perspectives that could materially change
     the reading.
  2. Each chosen role reads the idea independently. They may disagree; the
     Founder never receives their separate reports.
  3. Chief of Staff synthesises ONE answer: the ten concise questions, their
     expanded sections, and the six-field Company View.

Runs in a background thread because it is several model calls and takes
minutes. Progress is published for the live screen; the finished round is
written through opsdb.py, which stays the sole database writer.

The prompts here carry the parts of the directive that are easy to lose:
never invent a competitor, say plainly when research was not performed, zero
Founder questions is a passing score, one recommendation rather than five, and
— the one this stage exists for — an idea the company does not believe in gets
told so. A gate that always says Proceed is a gate that does nothing.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import subprocess
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
# APPEND, never insert: ops/control-center also contains a server.py, and
# putting that directory ahead of this one on the path makes `import server`
# resolve to the Control Center's. Appending keeps this package's own modules
# winning while still finding agent_runtime.
_CC = str(REPO / "ops" / "control-center")
if _CC not in sys.path:
    sys.path.append(_CC)
import agent_runtime  # noqa: E402

OPSDB = REPO / "ops" / "db" / "opsdb.py"

# Live progress for the in-flight screen, keyed by idea id. In memory on
# purpose: it is a view of something happening right now, not a record. The
# record is the round, and it is in the database.
PROGRESS: dict[int, list[tuple[str, str]]] = {}
_PROGRESS_LOCK = threading.Lock()

ROLE_LABEL = {
    "orchestrator": "Chief of Staff", "product": "Product", "cto": "CTO",
    "red-team": "Red Team", "ceo": "CEO", "design": "Design",
    "financial": "Financial", "security": "Security",
}
SELECTABLE = ("product", "cto", "red-team", "ceo", "design", "financial", "security")
MAX_PERSPECTIVES = 4  # Chief of Staff plus at most four others


def _note(idea_id: int, who: str, what: str) -> None:
    with _PROGRESS_LOCK:
        PROGRESS.setdefault(idea_id, []).append((who, what))


def progress_for(idea_id: int) -> list[tuple[str, str]]:
    with _PROGRESS_LOCK:
        return list(PROGRESS.get(idea_id, []))


def _clear(idea_id: int) -> None:
    with _PROGRESS_LOCK:
        PROGRESS.pop(idea_id, None)


# --------------------------------------------------------------- rehearsal ---
# Set IDEA_DESK_REHEARSAL=1 and no model is called and nothing is spent. The
# whole journey still runs — roster, per-role reading, synthesis, a stored
# round, correct, park, reopen — so the Founder can exercise every screen for
# free while testing. What it will NOT do is pretend: the answers say plainly
# that they are placeholders, the round is marked `rehearsal` in the database
# forever, the page says so, and opsdb refuses to approve a brief built on one.
REHEARSAL = os.environ.get("IDEA_DESK_REHEARSAL", "").strip().lower() in ("1", "true", "yes", "on")

_REHEARSAL_NOTE = ("<b>Rehearsal.</b> No agent read your idea and nothing was spent. This text is a "
                   "placeholder so the screen can be walked for free.")


def _rehearsal_roster() -> dict:
    return {"depth": "Light",
            "depth_reason": "Rehearsal mode — depth was not judged, because nobody read the idea.",
            "in": [["product", "would always be on the roster"],
                   ["cto", "would be asked what the records can support"]],
            "out": [["ceo, financial, security", "would be left out unless the idea reached "
                                                 "outside the company"]],
            # Rehearsal never reaches the outside world. This is not a judgement
            # that the idea needs no research — it is the same promise the rest
            # of rehearsal makes: nothing was asked, nothing was spent, and
            # nobody searched for anything.
            "outside_facts": False,
            "outside_facts_reason": "Rehearsal mode — nobody searched for anything.",
            "research_questions": []}


def _rehearsal_result(idea: dict, rounds: list[dict]) -> dict:
    words = (idea.get("current_raw") or idea["raw_idea"]).split()
    title = " ".join(words[:5])[:60] or "Rehearsal idea"
    answers = {}
    for num, question, _voice, expands in (
            (1, "understood", None, None), (2, "achieve", None, None), (3, "worth", None, None),
            (4, "exists", None, None), (5, "different", None, None), (6, "fail", None, None),
            (7, "recommend", None, None), (8, "assumptions", None, None),
            (9, "decisions", None, None), (10, "success", None, None)):
        answers[str(num)] = [
            f"{_REHEARSAL_NOTE} In a real evaluation, answer {num} would be the company's actual "
            f"reading, a few sentences long.",
            "<div class='sk'>Rehearsal</div>The expanded working would be here. Nothing on this "
            "page came from an agent."]
    return {"title": f"{title} (rehearsal)", "answers": answers,
            "view": {"opp": "Unclear",
                     "why": "Rehearsal mode. Nobody read this idea, so there is no judgement to "
                            "report. This exists to let the screens be walked without spending "
                            "anything.",
                     "merit": "Not assessed — rehearsal.",
                     "threat": "Not assessed — rehearsal.",
                     "diff": "Not assessed — rehearsal.",
                     "rec": "Investigate first"},
            "changed": ("Rehearsal round — your correction was stored, but nobody re-read the idea."
                        if rounds else None)}


class EvaluationError(Exception):
    """Something went wrong that the Founder should be told about, in words
    that mean something to them.

    `stage` names WHERE in the evaluation it happened. Without it every parse
    failure looked identical from the outside, and a roster-selection failure
    was indistinguishable from a final-synthesis one — which is exactly how
    several real evaluations were spent chasing the wrong path."""

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        self.stage = stage


# --------------------------------------------------------------- helpers ---

def _opsdb(*args: str) -> str:
    proc = subprocess.run([sys.executable, str(OPSDB), *args], capture_output=True, text=True,
                          timeout=30)
    if proc.returncode != 0:
        raise EvaluationError((proc.stderr or proc.stdout).strip().removeprefix("error: "))
    return proc.stdout.strip()


def _extract_json(text: str, *, stage: str | None = None) -> dict:
    """Models wrap JSON in prose or fences more often than not. Take the
    outermost object and parse that; if it will not parse, say so plainly
    rather than storing something half-understood."""
    if not (text or "").strip():
        # An empty reply and a misformatted one produced the same sentence,
        # and they are not the same problem: nothing can be reformatted out of
        # nothing, so a repair attempt here would spend a real call for
        # certain failure.
        raise EvaluationError("the company was asked, but answered with nothing at all. Nothing "
                              "was saved. This is usually a timed-out or interrupted agent rather "
                              "than a bad answer.", stage=stage)
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise EvaluationError("the company answered, but not in a shape this page could read. "
                          "Nothing was saved. Trying again usually clears it.", stage=stage)


# Every model call in an evaluation, so the Founder can see what a round cost.
# Previously dropped entirely: the one action the UI headlines as "This one
# spends money" was the only one invisible to the costs page, while the
# constants and the agent_run_id column added for exactly this sat unused.
_SPEND: dict[int, list[dict]] = {}
_SPEND_LOCK = threading.Lock()


def _record_spend(idea_id: int | None, agent: str, result) -> None:
    if idea_id is None:
        return
    with _SPEND_LOCK:
        _SPEND.setdefault(idea_id, []).append({
            "agent": agent,
            "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms,
            "model": result.model_used,
            "ok": result.ok,
        })


def spend_for(idea_id: int) -> tuple[float | None, int]:
    """Total dollars and call count for an in-flight or just-finished run.
    None for the total when no call reported a cost, rather than 0.00 —
    an unknown cost and a free one are different things."""
    with _SPEND_LOCK:
        calls = list(_SPEND.get(idea_id, []))
    known = [c["cost_usd"] for c in calls if c["cost_usd"] is not None]
    return (sum(known) if known else None), len(calls)


def _invoke(agent: str, transcript: str, idea_id: int | None = None,
            budget: str | None = None, timeout_s: float | None = None) -> str:
    result = agent_runtime.invoke_agent(
        agent, transcript,
        timeout_s=timeout_s or agent_runtime.IDEA_EVALUATION_TIMEOUT_S,
        wait_for_slot=True,
        max_budget_usd=budget)
    _record_spend(idea_id, agent, result)
    if not result.ok:
        if result.error_kind == "runtime_unavailable":
            raise EvaluationError(
                "no agent could be asked, because the <b>claude</b> command is not on this "
                "machine's PATH. Everything else in the Idea Desk works without it &mdash; writing "
                "ideas, reading past evaluations, approving, parking. Only evaluation needs it."
                "<br><br>To install it:<br>"
                "<code>npm install -g @anthropic-ai/claude-code</code><br>"
                "then run <code>claude</code> once to sign in, and restart the Idea Desk."
                "<br><br>Already installed? Run <code>python ops\\idea-desk\\doctor.py</code> "
                "&mdash; it reports whether Python can find it, which is a different question from "
                "whether your terminal can. If your terminal finds it and the doctor does not, "
                "point us straight at it: set <code>CLAUDE_BIN</code> to its full path.")
        raise EvaluationError(f"{ROLE_LABEL.get(agent, agent)} could not answer — {result.error}")
    return result.response_text or ""


def _idea_block(idea: dict, rounds: list[dict], founder_note: str | None) -> str:
    lines = [
        "THE FOUNDER'S IDEA, IN THEIR OWN WORDS (never edit or tidy this):",
        f'"""{idea["raw_idea"]}"""',
    ]
    if idea.get("current_raw") and idea["current_raw"] != idea["raw_idea"]:
        lines += ["", "THEY HAVE SINCE REWORDED IT TO:", f'"""{idea["current_raw"]}"""']
    # The old "WHO IT IS FOR" and "WHAT PROMPTED IT" lines are deliberately
    # gone. They were presented to every agent as if they were specification,
    # so a word typed in passing became load-bearing: "the public" in a
    # secondary box produced a roster that declared the idea was for the
    # public, and Product then spent its reading narrowing that word instead of
    # the idea. Working out who it is for is the company's job — Product is
    # asked for exactly that. An answer the Founder gave in one word is not
    # evidence, and treating it as evidence crowded out the actual thinking.
    if idea.get("current_audience") or idea.get("current_trigger"):
        aside = "; ".join(x for x in (idea.get("current_audience"),
                                      idea.get("current_trigger")) if x)
        lines += ["", "The Founder once jotted this alongside the idea, in a box the app no "
                      "longer asks for. It is a hint, NOT a specification, and it does not "
                      f"constrain who this is for or what it must be: {aside}"]
    if rounds:
        last = rounds[-1]
        lines += ["", f"THIS IS ROUND {len(rounds) + 1}. Your previous round recommended "
                      f"'{last['recommendation']}' and said, in one line: "
                      f"{(json.loads(last['view_json'] or '{}')).get('why', '')}"]
    if founder_note:
        lines += ["", "THE FOUNDER HAS TOLD YOU WHAT YOU GOT WRONG. This is the whole reason "
                      "there is another round. Take it seriously and change your reading:",
                  f'"""{founder_note}"""']
    return "\n".join(lines)


COMMON_RULES = """
HOUSE RULES, which matter more than sounding impressive:

* Never invent a competitor, a price, a customer count, a market size, a
  funding figure or a feature. YOU cannot search the web. This company has a
  separate Research lane that can, and if it was sent out you will find its
  findings below, each with a source you may cite. Anything NOT in that
  evidence is your own recollection: say so in those words, and never dress it
  up as a current fact. If no evidence appears below, then nobody searched, and
  the honest answer to any question about the outside world is that it was not
  checked — plus what specifically would need checking.
* Never praise an idea because the Founder proposed it. If the merits are
  weak, say they are weak. You are useful here only to the extent that you
  are willing to disagree.
* Do not restate the Founder's own sentence back to them. Saying "you want a
  dashboard" when they asked for a dashboard is a failure, not an answer.
* Say what you do not know, in the answer, rather than working around it.
* Never collapse what you OBSERVED into what you INFER. "The bottle was opened
  at 8:04" is an observation; "the pill was taken" is a guess built on it.
  Where an idea turns on knowing that something happened, keep the two apart in
  the design and in the words — store and show what was actually seen, and
  label anything derived from it as derived. Systems that quietly promote a
  signal into a fact are how a product ends up making a claim nobody can stand
  behind.

HOW TO WRITE IT. The Founder said the answers were hard to read and hard to
pay attention to. They were right, and it is your problem to fix, not theirs:

* SHORT SENTENCES. One idea each. If a sentence has a semicolon or three
  commas, it is two sentences pretending to be one. Break it.
* Lead with the answer. Then the reason. Never build up to the point across
  three clauses — the Founder may stop reading before you arrive.
* Plain words. Say "we cannot check this" not "no verification capability
  exists". Say "people stop using it" not "retention degrades". If a word
  would not survive being said out loud to a friend, replace it.
* When you are listing things, USE A LIST: <ul><li>one point</li><li>the
  next</li></ul>. Three points buried in a paragraph read as none.
* <b>Bold the few words that carry the decision</b>, not whole sentences.
  Bolding everything is the same as bolding nothing.
* No throat-clearing. "It is worth noting that", "there are several factors",
  "broadly speaking" — cut them and start with the thing itself.

Write for someone smart who is busy and skimming, not for someone grading
your thoroughness. The test is whether they can get the point in one pass.

TWO FAILURES THAT SHORT SENTENCES DO NOT FIX. The Founder hit both:

* ANSWER THE QUESTION YOU WERE ASKED, and nothing else. "Did you understand
  my idea" is answered by saying what you understood. It is NOT the place for
  what you cut, who you narrowed it to, how the code will be structured, or
  what would make you revisit the decision. Those belong to questions 7, 8 and
  9, and putting them here means the Founder reads five decisions crammed into
  one paragraph and takes none of them in. Before you write each answer, check
  every sentence against the question. If a sentence belongs to a different
  question, move it there.
* NEVER USE A TERM THE FOUNDER HAS NOT USED unless you explain it in the same
  breath, in ordinary words. "An evidence field on every dose record", "the
  tap", "a one-way door", "the escalation clock" — each is clear to the
  colleague who wrote it and opaque to the person reading it once. Either say
  it plainly ("every time a dose is recorded we also store HOW we know — a
  tapped button now, a sensor later") or leave it out. A short sentence made
  of unfamiliar terms is harder to read than a long plain one, not easier.
"""


# ------------------------------------------------------- phase 1: roster ---

# The shape asked for, kept OUT of the prompt string so that the prompt and the
# reformatting request cannot drift apart. Asking for a repair against the
# wrong contract is how a repair makes things worse.
ROSTER_CONTRACT = """Reply with ONLY this JSON and nothing else:

{
  "depth": "Light" | "Standard" | "Full",
  "depth_reason": "one sentence, in the Founder's terms, why this depth and not another",
  "in":  [["product", "why THIS idea needs them, specifically"], ...],
  "out": [["ceo, financial", "why they would add nothing here"], ...],
  "outside_facts": "yes" | "no",
  "outside_facts_reason": "one sentence: which judgement here depends on what is true out there",
  "research_questions": ["a specific thing that must be found out", ...]
}

"out" is not optional: naming who you left out and why is how the Founder can
tell you chose rather than defaulted."""

ROSTER_STAGE = "choosing who should read it"


def _select_roster(idea: dict, rounds: list[dict], founder_note: str | None,
                   idea_id: int | None = None,
                   evidence: dict[str, str] | None = None) -> tuple[dict, bool]:
    transcript = f"""You are the Chief of Staff of an AI software company. The Founder has brought
in an idea. Your first job is to decide WHO should read it, and HOW DEEPLY the
company should look — before anyone spends time on it.

{_idea_block(idea, rounds, founder_note)}

HOW THIS COMPANY WORKS: invent first, attack second, improve third. Product,
Design and CTO BUILD a direction — in that order, each seeing the last. Red Team
then attacks THAT direction, not the Founder's rough sentence. Then it gets
repaired. You are choosing who builds, not who comments.

WHO YOU MAY CHOOSE FROM:
  product   — the outcome the Founder actually wants, stated so another implementation could serve
              it. ALWAYS on the roster.
  cto       — invents the way to build it with the least human effort: 3-5 workable architectures,
              compared, one recommended. Include whenever automation, hardware, sensors, AI, APIs,
              integrations or data flow could materially improve the answer. Do NOT leave the CTO
              out just because the Founder's sentence sounds technically simple — the fridge idea
              said nothing about cameras, and system design turned out to be the whole question.
  red-team  — attacks the direction the others designed. Include whenever there is a real direction
              to attack, which is nearly always.
  ceo       — positioning and market direction. Only when someone OUTSIDE the company chooses this.
  design    — the lowest-friction experience that delivers the outcome. Include when what the
              person has to DO decides whether this is worth using.
  financial — only when money genuinely changes hands or the cost structure decides it.
  security  — only when identity, payments or sensitive data are actually in play.

Choose ONLY the perspectives that could materially change the SOLUTION. Choosing
everyone is the failure mode, not the safe option. Product plus one or two
others is a good roster. Four others is the maximum.

The question is never "is this idea any good as written" — it is rough on
purpose. The question is "who do we need in the room to turn this into the
strongest thing we could actually build".

HOW DEEP:
  Light    — internal tooling, one user, nothing outside the company changes. No competitor work.
  Standard — real users beyond the Founder, but no market to compete in yet.
  Full     — something people outside would choose between this and an alternative.

DOES THIS NEED THE OUTSIDE WORLD? This company now has a Research lane that can
actually search the web. It is not free and it is not always worth using, so you
decide. Answer "yes" to outside_facts only when the company's RECOMMENDATION
would genuinely change depending on what is true out there right now — what
already exists and how well it works, what things cost, what a platform does or
does not allow, what the law currently requires, or why previous attempts at
this outcome failed.

Answer "no" when the answer lives inside this company: internal tooling, a
workflow only the Founder has, a question of taste, or anything where knowing
the market changes nothing about what to build.

Do NOT say "yes" because research sounds diligent. A Light-depth idea almost
never needs it, and sending the lane out to confirm the obvious spends the
Founder's money to tell them what they already know.

If yes: research_questions must be the SPECIFIC things that would change the
answer — "which existing products already make this effortless, and why has none
of them won" beats "market research". Three to six of them. If no: leave
research_questions empty.

{ROSTER_CONTRACT}
"""
    raw = _invoke("orchestrator", transcript, idea_id)
    # Recorded BEFORE parsing. This is the fix for the failure that kept
    # costing real evaluations: roster selection needs machine-readable JSON
    # exactly as much as the final answer does, but it had neither the repair
    # attempt nor any preservation of what came back — so a malformed roster
    # threw away the raw response, wrote no diagnostics file at all, and
    # surfaced the same sentence a synthesis failure would.
    if evidence is not None:
        evidence["who should read it — the Chief of Staff's answer"] = raw
    data, _raw_repair, repaired = _parse_with_one_repair(
        raw, idea_id, ROSTER_CONTRACT, ROSTER_STAGE, evidence,
        "who should read it — the reformatting attempt")

    # Everything below treats the model's JSON as hostile: an explicit null, a
    # three-element entry, a string where a list belongs. Two of these shapes
    # crashed the whole evaluation and discarded a completed, paid-for run
    # (Code Review, catch-up).
    chosen, seen = [], set()
    for entry in (data.get("in") or []):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        role = str(entry[0]).strip().lower()
        if role in SELECTABLE and role not in seen:
            seen.add(role)
            chosen.append([role, str(entry[1])])
    if "product" not in seen:
        # DEC-015 puts Product on every roster. Enforced here rather than hoped
        # for, because the roster is otherwise the model's own judgement.
        chosen.insert(0, ["product", "always on the roster; owns the problem, the scope and the "
                                     "first version."])
    chosen = chosen[:MAX_PERSPECTIVES]

    depth = data.get("depth")
    # Anything but a clear "yes" means no. A missing or unparseable field must
    # not be able to send the research lane out on its own initiative — an
    # opt-in capability that fires on ambiguity is not opt-in.
    wants_facts = str(data.get("outside_facts") or "").strip().lower() in ("yes", "true")
    questions = [str(q).strip() for q in (data.get("research_questions") or [])
                 if isinstance(q, (str, int, float)) and str(q).strip()][:8]
    return {
        "depth": depth if depth in ("Light", "Standard", "Full") else "Standard",
        "depth_reason": str(data.get("depth_reason") or ""),
        "outside_facts": wants_facts,
        "outside_facts_reason": str(data.get("outside_facts_reason") or ""),
        "research_questions": questions,
        "in": chosen,
        # Take the first two elements, never unpack — a three-element entry is
        # well-formed JSON and used to raise ValueError here.
        "out": [[str(e[0]), str(e[1])] for e in (data.get("out") or [])
                if isinstance(e, (list, tuple)) and len(e) >= 2],
    }, repaired


# -------------------------------------------------- phase 2: perspectives ---

ROLE_BRIEF = {
    "product": "the OUTCOME the Founder is actually after, stated so plainly that a different "
               "implementation could serve it. Who it is for, what belongs in a first useful "
               "version, what should wait. Name the scope you would cut. Do not treat the "
               "Founder's wording as the specification — it is the signal, not the design.\n"
               "  FIRST, in one sentence: what is the DISTINCTIVE part of this idea — the thing "
               "that makes it different from the obvious version anyone could build? Say it before "
               "you cut anything, because it is the one part that must not be cut for convenience. "
               "If your recommended first version does not contain it, say so out loud and say "
               "what would have to be true to bring it back.\n"
               "  Then ask whether the idea solves MORE THAN ONE problem. The Founder usually "
               "names the obvious one. A second, quieter problem in the same idea is often the "
               "better wedge, and nobody finds it by restating the first.",
    # The Founder's correction: the CTO's job during idea formation is to
    # INVENT the way around the hard part, not to certify that the hard part is
    # hard. "Manual entry is the weakness, so investigate first" was the failure
    # this rewrites — nobody had asked whether the manual entry could be
    # engineered away.
    "cto": "how to actually BUILD this with the least human effort. Generate three to five "
           "genuinely different workable architectures — software, AI, hardware, sensors, cameras, "
           "APIs, integrations, edge or cloud, hybrids. They must differ in KIND, not in detail: "
           "'ours, but tuned' is not a second option. Compare them explicitly and in one place, on "
           "fidelity to what the Founder actually asked for, time to the first moment that works, "
           "performance on modest hardware and slow networks, quality of the failure experience, "
           "engineering time, maintenance burden, and reversibility. Then say which ONE you would "
           "build and why it beats each of the others.\n"
           "  Mark any ONE-WAY DOOR explicitly: a choice that would take a rewrite rather than a "
           "week to undo. Building our own version of something that already exists — a language, "
           "a runtime, a parser, an engine — is nearly always a one-way door, and choosing one "
           "needs more justification than 'it gives a better first experience'.\n"
           "  Attack the constraint rather than accepting it: if a step is tedious for the user, "
           "your job is to design it away or make it degrade gracefully, not to report that it is "
           "tedious.\n"
           "  THE DISTINCTIVE PART IS NOT YOURS TO DROP. If Product named something as what makes "
           "this idea different — a physical sensor, a particular moment, an unusual input — at "
           "least one of your architectures MUST attempt it, and you must try hard to make it "
           "cheap, simple and reversible before you conclude it is impractical. Look for the "
           "off-the-shelf, retrofit or borrowed-hardware version before assuming custom "
           "manufacturing; a thing that clips onto what people already own is a different project "
           "from a thing you have to make. Only after that may you recommend a version without "
           "it, and then you must say plainly that the differentiator was dropped, what it would "
           "cost to keep, and what would bring it back. Replacing the distinctive idea with the "
           "conventional one because the conventional one is easier is the failure this company "
           "exists to avoid.\n"
           "  Compare on the axes that actually separate these options: user effort (automatic vs "
           "manual), quality of the evidence or result, how it fails and how badly, cost, setup "
           "burden, battery or upkeep, whether it works when the phone or network does not, time "
           "to a working prototype, what it takes to manufacture or certify, privacy exposure, "
           "reversibility, and whether it leaves a path open to something better later.",
    "red-team": "how this fails. The assumption that would sink it, the thing being decided too "
                "early, the version of this that quietly becomes a huge project.",
    "ceo": "whether this should exist, and for whom. Positioning, and whether anyone outside would "
           "choose it. Say plainly if there is no outside audience.",
    "design": "the LOWEST-FRICTION experience that would deliver the outcome. Not whether the "
              "Founder's shape is right — what shape would ask least of the person using it. Name "
              "the interaction that has to disappear for this to be worth using at all.",
    "financial": "the money. What it costs to build and run, what it could return, and whether the "
                 "economics change the recommendation.",
    "security": "identity, secrets, personal data, and what could go wrong with them. Only raise "
                "what genuinely applies.",
}


# The order the Founder set: invent first, attack second, improve third. These
# roles BUILD the direction, in this sequence, each seeing what came before.
INVENTORS = ("product", "design", "cto")
ATTACKER = "red-team"


# ------------------------------------------------------ the Research lane ---
# TASK-027 (DEC-032). Until now the company could say what ought to be looked
# up and then not look it up, because no agent could reach the outside world.
# Every evaluation therefore ended with a sentence like "no research was
# performed" sitting next to a market judgement that depended on research. The
# Founder called that what it is: a capability gap wearing a prompt's clothes.
#
# The lane runs BETWEEN inventing and attacking, deliberately. Earlier and it
# has no solution categories to search across; later and the evidence arrives
# after the direction is already fixed, which is the "write 'research needed'
# and synthesise anyway" pattern the Founder rejected.

# Two sweeps at most, ever. The first searches what the roster asked for across
# the categories the company invented; the second exists only for a category
# the first sweep DISCOVERED and nobody had thought to look at. There is no
# third, and no loop: a research step that decides for itself when to stop is
# an unbounded spend on the Founder's account.
MAX_SWEEPS = 2

RESEARCH_CONTRACT = """Reply with ONLY this JSON and nothing else:

{
  "findings": [
    {
      "category": "which solution category this belongs to",
      "claim": "the specific factual thing you established, in one sentence",
      "source": "who published it — the organisation or site name",
      "url": "the link",
      "dated": "publication or access date, or \\"\\" if you cannot tell",
      "detail": "prices, capabilities, limits, complaints — the specifics, or \\"\\"",
      "changes_ranking": "yes" | "no",
      "why_it_matters": "one sentence: what this does or does not change for the company"
    }, ...
  ],
  "contradictions": ["two sources disagree about X: A says ..., B says ...", ...],
  "unknown": ["what you could not establish, and why it stayed unknown", ...],
  "unverified": ["anything you believe but did NOT confirm by searching this session", ...],
  "new_categories": ["a solution category you DISCOVERED that nobody had listed", ...],
  "bottom_line": "2-4 sentences: what the evidence says about which approach is strongest"
}

Every finding needs a real url you actually retrieved. If you cannot cite it,
it does not go in "findings" — put it in "unverified" instead. An empty
"findings" list is an acceptable and honest answer; an invented citation is not."""

RESEARCH_STAGE = "researching the outside world"


def _research(questions: list[str], direction: str, idea: dict, rounds: list[dict],
              founder_note: str | None, idea_id: int | None = None,
              sweep: int = 1, chasing: str = "") -> tuple[dict, bool, int | None]:
    """One bounded sweep. Returns (packet, repaired, searches_actually_performed).

    Raises EvaluationError like any other stage — but every caller catches it,
    because research failing is not the same as the evaluation failing. The
    company can still answer without evidence; it just has to say so.
    """
    asked = "\n".join(f"  {i}. {q}" for i, q in enumerate(questions, 1)) or \
        "  (none were listed — work them out from the direction below)"
    chase = (f"""
THIS IS A SECOND, NARROWER SWEEP. Your first sweep turned up a solution category
nobody in this company had thought of, and it could change the answer, so you are
being sent back out for exactly this and nothing else:

{chasing}

Do not re-cover ground you already covered. Spend the whole sweep here.
""" if chasing else "")
    transcript = f"""You are the Research lane of an AI software company. The Founder brought in an
idea, and the company has designed a direction it thinks is best. Before anyone
attacks or defends that direction, somebody has to go and find out what is
actually TRUE out there right now. That is you.

{_idea_block(idea, rounds, founder_note)}

WHAT THE COMPANY HAS DESIGNED SO FAR — use it to work out which categories to
search across, NOT as a thing to confirm. Evidence that this direction is wrong
is more valuable to them than evidence that it is right:

{direction or "(nothing designed yet)"}

WHAT THEY NEED YOU TO FIND OUT:
{asked}
{chase}
YOUR SEARCH CEILING FOR THIS SWEEP: about {SWEEP_SEARCH_HINT} searches. Spend
them where they buy the most. Stop early if more searching stops changing the
picture.

Start from the OUTCOME, not the product name. The most useful thing you can
bring back is a way of achieving this outcome that works completely differently
from anything above — that is the comparison nobody here can make for
themselves.

{RESEARCH_CONTRACT}
"""
    result = agent_runtime.invoke_agent(
        "research", transcript,
        timeout_s=agent_runtime.RESEARCH_TIMEOUT_S,
        wait_for_slot=True,
        max_budget_usd=agent_runtime.RESEARCH_BUDGET_USD,
        web_research=True)
    _record_spend(idea_id, "research", result)
    if not result.ok:
        raise EvaluationError(
            f"the Research lane could not search &mdash; {result.error}", stage=RESEARCH_STAGE)
    raw = result.response_text or ""
    packet, _raw_repair, repaired = _parse_with_one_repair(
        raw, idea_id, RESEARCH_CONTRACT, RESEARCH_STAGE, None,
        f"the research sweep {sweep} reformatting attempt")
    return _clean_packet(packet), repaired, result.searches


# How many searches to ASK for. Not a limit — the real limits are the dollar
# ceiling and the timeout in agent_runtime, both of which the CLI enforces
# whatever the prompt says. This number exists so the lane spends its effort
# deliberately instead of stopping at three results or grinding through forty.
SWEEP_SEARCH_HINT = 12


def _clean_packet(packet: dict) -> dict:
    """Treat the packet as hostile, exactly as the roster and the final answer
    are treated. A finding with no url is not a finding — it is a sentence, and
    the entire point of this lane is that the company stopped being able to
    tell those apart."""
    findings = []
    for f in (packet.get("findings") or []):
        if not isinstance(f, dict):
            continue
        url = str(f.get("url") or "").strip()
        claim = str(f.get("claim") or "").strip()
        # Demoted, not dropped: an uncited claim still gets shown to the
        # company, just never as verified fact. Dropping it silently would hide
        # that the lane produced something it could not stand behind.
        if not claim:
            continue
        if not _CITED.match(url):
            packet.setdefault("unverified", []).append(
                f"{claim} (the lane could not cite this)")
            continue
        findings.append({
            "category": str(f.get("category") or "uncategorised").strip(),
            "claim": claim,
            "source": str(f.get("source") or "").strip(),
            "url": url,
            "dated": str(f.get("dated") or "").strip(),
            "detail": str(f.get("detail") or "").strip(),
            "changes_ranking": str(f.get("changes_ranking") or "").strip().lower() in ("yes", "true"),
            "why_it_matters": str(f.get("why_it_matters") or "").strip(),
        })

    def _strings(key):
        return [str(x).strip() for x in (packet.get(key) or [])
                if isinstance(x, (str, int, float)) and str(x).strip()]

    return {
        "findings": findings,
        "contradictions": _strings("contradictions"),
        "unknown": _strings("unknown"),
        "unverified": _strings("unverified"),
        "new_categories": _strings("new_categories"),
        "bottom_line": str(packet.get("bottom_line") or "").strip(),
    }


# A citation has to be a real http(s) link. "see their website" and
# "example.com" are how an unsourced claim gets to wear a source's clothes.
_CITED = re.compile(r"^https?://[^\s/]+\.[^\s/]", re.I)


def _empty_packet() -> dict:
    """The shape every consumer can rely on, whether or not anyone searched.
    Callers must never have to ask "did research run" before they can read a
    key — that question is answered by the status, in one place."""
    return {"findings": [], "contradictions": [], "unknown": [], "unverified": [],
            "new_categories": [], "bottom_line": ""}


def _merge_packets(a: dict, b: dict) -> dict:
    """Two sweeps, one packet. Findings are de-duplicated by url+claim so a
    second sweep that re-cites the same page does not make the evidence look
    twice as strong as it is."""
    seen = {(f["url"], f["claim"]) for f in a["findings"]}
    merged = dict(a)
    merged["findings"] = a["findings"] + [f for f in b["findings"]
                                          if (f["url"], f["claim"]) not in seen]
    for key in ("contradictions", "unknown", "unverified", "new_categories"):
        merged[key] = a[key] + [x for x in b[key] if x not in a[key]]
    merged["bottom_line"] = (b["bottom_line"] or a["bottom_line"])
    return merged


def evidence_for_agents(packet: dict, status: str) -> str:
    """The packet as the rest of the company reads it.

    Written so that a role CANNOT accidentally present recollection as
    research: verified findings carry their source inline, and everything the
    lane could not stand behind is in a section that says so.
    """
    if status != "done":
        return _NO_EVIDENCE[status]
    if not packet["findings"] and not packet["unknown"] and not packet["unverified"]:
        return ("THE RESEARCH LANE SEARCHED AND FOUND NOTHING IT COULD CITE. That is a real "
                "finding, not a formality: treat this outcome as unstudied, and do not fill the "
                "gap with what you think you remember.")
    out = ["WHAT THE RESEARCH LANE ACTUALLY FOUND. Every line below was retrieved from the web "
           "during this evaluation. You may state these as current fact and cite them. You may "
           "NOT state anything else as current fact.", ""]
    if packet["findings"]:
        out.append("VERIFIED FINDINGS:")
        for f in packet["findings"]:
            bits = [f"  [{f['category']}] {f['claim']}"]
            if f["detail"]:
                bits.append(f"      detail: {f['detail']}")
            bits.append(f"      source: {f['source'] or 'unnamed'} — {f['url']}"
                        + (f" ({f['dated']})" if f["dated"] else ""))
            if f["changes_ranking"]:
                bits.append(f"      CHANGES THE RANKING: {f['why_it_matters']}")
            out.append("\n".join(bits))
        out.append("")
    if packet["contradictions"]:
        out += ["SOURCES THAT DISAGREE — do not quietly pick one:",
                *(f"  - {c}" for c in packet["contradictions"]), ""]
    if packet["unverified"]:
        out += ["NOT VERIFIED — the lane believes these but did not confirm them. Treat as "
                "hearsay. If one of these decides your answer, say that it is unconfirmed:",
                *(f"  - {u}" for u in packet["unverified"]), ""]
    if packet["unknown"]:
        out += ["STILL UNKNOWN after searching — an honest gap, not an invitation to guess:",
                *(f"  - {u}" for u in packet["unknown"]), ""]
    if packet["bottom_line"]:
        out += ["THE LANE'S READING OF ITS OWN EVIDENCE (it does not decide anything):",
                f"  {packet['bottom_line']}", ""]
    return "\n".join(out)


_NO_EVIDENCE = {
    "not-needed": ("NO RESEARCH WAS DONE, because the Chief of Staff judged that this idea's "
                   "answer does not depend on what is true outside this company. If you find "
                   "yourself needing an outside fact to answer, say so plainly and say what fact "
                   "— do not supply it from memory."),
    "unavailable": ("RESEARCH WAS NEEDED HERE AND COULD NOT BE DONE — the lane was asked and "
                    "could not search. This is a known gap in THIS evaluation. Do not paper over "
                    "it: where your answer depends on a current outside fact, say that the fact "
                    "was not checked. Never write anything that implies a market scan happened."),
}


def _perspective(role: str, idea: dict, rounds: list[dict], founder_note: str | None,
                 depth: str, idea_id: int | None = None, earlier: str = "") -> str:
    prior = (f"""
WHAT YOUR COLLEAGUES HAVE ALREADY WORKED OUT — build on it, do not repeat it:

{earlier}
""" if earlier else "")
    transcript = f"""You are the {ROLE_LABEL[role]} of an AI software company. The Founder has brought
in a rough idea. Your job is NOT to judge whether their wording is a good
specification — it is not one, and it was never meant to be. Your job is to help
turn it into the strongest workable thing the company could actually build.
{prior}

{_idea_block(idea, rounds, founder_note)}

HOW DEEP THE COMPANY IS GOING: {depth}.
{"At Light depth there is no market to research and no competitor work to do — do not invent any."
 if depth == "Light" else ""}

YOUR ANGLE — answer from it and not from everyone else's: {ROLE_BRIEF[role]}
{COMMON_RULES}
Write at most 450 words of plain prose. No headings, no JSON, no bullet
theatre. The Chief of Staff reads this and writes the single answer the Founder
sees, so write for a colleague who will disagree with you, not for the Founder.

Saying "this has a weakness, so it is risky" is not your job and is not useful
on its own. If you name a weakness, name what you would DO about it. If after
genuinely trying you believe the outcome cannot be reached workably, say that
plainly and say what would have to be true for it to become reachable.
"""
    return _invoke(role, transcript, idea_id)


def _reconsider(role: str, direction: str, evidence_text: str, idea: dict,
                rounds: list[dict], founder_note: str | None,
                idea_id: int | None = None) -> str:
    """One role reads the evidence and revises what it said.

    This is the step that decides whether the Research lane is real. Without
    it, evidence arrives after the direction is settled and becomes decoration
    — the company searches the web and then recommends whatever it was already
    going to recommend. The prompt therefore makes CHANGING the answer the
    normal, expected outcome of learning something, and makes "nothing changed"
    a claim that has to be defended.
    """
    transcript = f"""You are the {ROLE_LABEL[role]} of an AI software company. You already gave your
reading of the Founder's idea. Since then the company's Research lane went out
and searched the real world, and it found things you did not know when you
answered.

{_idea_block(idea, rounds, founder_note)}

WHAT THE COMPANY DESIGNED, INCLUDING YOUR OWN PART OF IT:

{direction}

{evidence_text}

YOUR JOB NOW: read that evidence and say what it changes.

Changing your mind here is not a loss of face — it is the single most valuable
thing you can do in this evaluation, and it is why the searching was paid for.
If a product already does this well, say so and rank it above what you invented.
If the real failure of this category turns out to be something other than what
you assumed, say that plainly and re-rank on the real failure. If the evidence
kills your preferred option, kill it yourself rather than defending it.

Be equally honest the other way: if the evidence genuinely does not change your
ranking, say so and say WHY it does not. "Nothing changed" is an acceptable
answer only with a reason attached.

RULES:
* Only state as current fact what appears in the evidence above, with its
  source. For anything else say plainly that it is not confirmed.
* Do not repeat your earlier answer back. Say only what is DIFFERENT and why.
* If nothing in the evidence touches your part, say that in one line and stop.

{COMMON_RULES}

WRITE IT AS:
WHAT THE EVIDENCE CHANGED: <the re-ranking, the dropped option, the new
    front-runner — or "nothing, because ..." with the reason>
WHY: <which specific finding did it, named and cited>
WHAT I STILL DO NOT KNOW: <the fact that would change this again, if it exists>
"""
    return _invoke(role, transcript, idea_id)


def _attack(direction: str, idea: dict, rounds: list[dict], founder_note: str | None,
            idea_id: int | None = None, evidence_text: str = "") -> str:
    """Red Team attacks the DIRECTION the company designed, not the Founder's
    rough sentence. Attacking a one-line pitch only ever produces "it is
    underspecified", which is true of every one-line pitch and helps nobody."""
    transcript = f"""You are the Red Team of an AI software company. Your colleagues have taken the
Founder's rough idea and designed a specific direction they want to build. That
DIRECTION is what you attack — not the Founder's original wording, which was
only a starting signal.

{_idea_block(idea, rounds, founder_note)}

THE DIRECTION THE COMPANY IS PROPOSING:

{direction}

{evidence_text}

Go after THIS proposal. What is the assumption that sinks it? Where does it
quietly become a much larger project? What breaks when it meets a real person?
What did they design around that cannot actually be designed around?

THE EVIDENCE IS ALSO YOURS TO ATTACK. Does a finding actually support the
weight being put on it? Is a claim about the market resting on one source, an
old page, or a vendor describing its own product? Did they search for what
would confirm the direction rather than what would kill it? A company that
searched the web and then believed whatever it found first is not more rigorous
than one that did not search at all &mdash; it is more confident, which is worse.
Say plainly if the evidence is thinner than the conclusion drawn from it.
{COMMON_RULES}
Be specific enough that someone could act on each objection. "It is
underspecified" is not an objection to a proposal — it is an observation about
a sentence, and the proposal above is not a sentence.

Rank your objections, hardest first. At most 400 words.
"""
    return _invoke(ATTACKER, transcript, idea_id)


def _repair(role: str, direction: str, attack: str, idea: dict, rounds: list[dict],
            founder_note: str | None, idea_id: int | None = None,
            evidence_text: str = "") -> str:
    """One pass to answer the attack. This is where a weakness gets engineered
    away rather than merely recorded — the specific thing the Founder said was
    missing."""
    transcript = f"""You are the {ROLE_LABEL[role]} of an AI software company. The company designed a
direction for the Founder's idea, and the Red Team has attacked it. Your job now
is to REPAIR it where repair is honest.

{_idea_block(idea, rounds, founder_note)}

THE DIRECTION:

{direction}

WHAT THE RED TEAM SAID:

{attack}

{evidence_text}

For each objection, in order: can it be designed away, reduced, or made to fail
gracefully? If yes, say exactly how, and what the direction becomes. If no, say
so plainly — an objection you cannot answer is the most useful thing on this
page, and pretending otherwise is worse than losing the argument.
{COMMON_RULES}
End with the direction as it now stands after your repairs, in a few sentences,
so the Chief of Staff can quote it. If the attack was fatal and no repair
survives, say that instead and say what the company should do about it.

Then, on its own final line, exactly one of:

  NEEDS: none
  NEEDS: <one role> — <why, in a few words>

...naming a role NOT already in this evaluation whose absence would now be a
real gap, because the direction has moved into their territory. Choose from:
product, design, cto, red-team, ceo, financial, security. A direction that
started as a simple tool and now handles children's data, payments, or someone
else's platform has changed domain, and the roster was chosen before that was
known. Name at most one, and only if their absence would genuinely weaken the
answer — this costs a real call.

At most 450 words.
"""
    return _invoke(role, transcript, idea_id)


_NEEDS = re.compile(r"^NEEDS:\s*([a-z-]+)", re.I | re.M)


def _late_addition(repair_text: str, already: list[str]) -> str | None:
    """A role the direction turned out to need, that the roster could not have
    known to include.

    The roster is chosen from the Founder's raw sentence. By the time the
    company has designed something, the domain may have moved — a kids' coding
    toy that acquires share links, resume identifiers and telemetry is handling
    children's data, and Security was left out when none of that existed. This
    reopens the roster once, for one role, rather than freezing a decision made
    before the facts."""
    for match in _NEEDS.finditer(repair_text or ""):
        role = match.group(1).strip().lower()
        if role in SELECTABLE and role not in already:
            return role
    return None


# ---------------------------------------------------- phase 3: synthesis ---

SYNTH_CONTRACT = """
Reply with ONLY this JSON object and nothing else. Every value is a string.
The "concise" strings may use <b>...</b> for the few words that matter most.
The "expanded" strings may additionally use <div class="sk">Section heading</div>
to label which of the fifteen sections you are answering from, and
<div class="two"><div>...</div><div>...</div></div> for a two-column split.
No other HTML, no links, no scripts.

EVERY answer is a PAIR: [concise, expanded]. The second string is the WORKING
behind the first — the part someone opens to check your reasoning. It is not a
label, not a cross-reference, and never a copy of anything below. Write it, or,
if an idea genuinely has no further working behind an answer, put exactly this
sentence and nothing else:

  No further working — the concise answer is the whole of it.

Saying that honestly is fine. Echoing the &lt;&lt;...&gt;&gt; slots below is not: they
describe what to write, they are not text to reuse.

{
  "title": "a short name for this idea, 3-7 words, how the company would refer to it",
  "answers": {
    "1":  ["Did the company understand my idea? — a few sentences",
           "<<your working for answer 1, drawing on sections 1 and 2 of the fifteen>>"],
    "2":  ["What am I really trying to achieve? — the outcome, not the feature",
           "<<your working, from section 3>>"],
    "3":  ["Why might this be worth building?",       "<<your working, from section 4>>"],
    "4":  ["What already exists?",                    "<<your working, sections 5 and 6>>"],
    "5":  ["What could make ours different?",         "<<your working, section 7>>"],
    "6":  ["What could make it fail?",                "<<your working, section 8>>"],
    "7":  ["What does the company recommend?",        "<<your working, sections 9, 10 and 12>>"],
    "8":  ["What assumptions did the company make?",  "<<your working, section 11>>"],
    "9":  ["What decisions do you need from me?",     "<<your working, section 13>>"],
    "10": ["How will we know we succeeded?",          "<<your working, section 14>>"]
  },
  "view": {
    "opp":    "High" | "Medium" | "Low" | "Unclear"  — this rates THE PROBLEM, never the
              architecture the company happened to choose. See the rule below,

    "why":    "two to four sentences",
    "merit":  "the single biggest merit",
    "threat": "the single biggest threat, and WHAT IT THREATENS: write 'to the opportunity:' if it "
              "would sink any version of this idea, or 'to this approach:' if it would only sink "
              "the one we chose",
    "diff":   "what makes the DESIGNED solution better than the obvious version of this idea — the "
              "approach the company chose and what it beats. SAY WHOSE IT IS: if this is the "
              "Founder's own distinctive idea, say so; if the company replaced it, say that "
              "plainly and in the same breath say what the Founder's was and why ours is being "
              "recommended instead. 'none we can see yet' only if the company genuinely found no "
              "better approach than the obvious one",
    "rec":    "Proceed" | "Proceed with narrowed scope" | "Investigate first" | "Reconsider"
  },
  "changed": "what changed since the previous round — omit entirely if this is round 1"
}
"""


def _voice_label(role: str) -> str:
    """Who is speaking, for the synthesis transcript.

    The repair pass arrives as "cto-repair" — a stage, not a role, with no
    entry in ROLE_LABEL. Naming it properly matters: the Chief of Staff has to
    be able to tell the CTO's first architecture from the same CTO's answer
    after the Red Team attacked it, or it will synthesise the superseded one."""
    if role.endswith("-repair"):
        base = role[: -len("-repair")]
        return f"{ROLE_LABEL.get(base, base)}, after repairing the direction"
    return ROLE_LABEL.get(role, role)


def _synthesise(idea: dict, rounds: list[dict], founder_note: str | None, roster: dict,
                perspectives: list[tuple[str, str]], idea_id: int | None = None,
                evidence_text: str = "") -> dict:
    voices = "\n\n".join(f"--- {_voice_label(role)} ---\n{text}" for role, text in perspectives)
    round_no = len(rounds) + 1
    transcript = f"""You are the Chief of Staff of an AI software company. Your colleagues have each
read the Founder's idea. They may disagree with each other. The Founder never
sees their separate reports — they see ONE answer, and you write it.

{_idea_block(idea, rounds, founder_note)}

DEPTH: {roster['depth']} — {roster['depth_reason']}

WHAT YOUR COLLEAGUES SAID:

{voices}

{evidence_text}

YOUR JOB: answer these ten questions, and close with the company's view.

The ten answers are the layer the Founder decides on. Everything they need to
decide is there, in a couple of sentences each, readable in two minutes without
opening anything. The expanded string behind each is where someone CHECKS that
decision. Nothing that would change the decision may live only in the expanded
part.

Rules that are easy to get wrong, and matter:

* Question 1 says WHAT WE UNDERSTOOD, in the Founder's own frame, and nothing
  else. If the company changed or narrowed the idea, name the change in ONE
  short sentence and say the reasoning is in answer 7 — do not argue it here.
  Two or three sentences is the whole budget.
* Question 2 is the one that proves you understood. Not "you want a
  dashboard" — that is their own word handed back. Say what they are actually
  trying to end up with.
* IF THE COMPANY DROPPED THE DISTINCTIVE PART of the Founder's idea — the thing
  that made it different from the obvious version — that is the single most
  important fact on this page and it goes in Question 1, in one plain sentence,
  with the reasoning in Question 7. Never let it surface only inside expanded
  working. A Founder who reads the concise layer and does not learn that their
  differentiator is gone has been quietly overruled.
* Question 5 is where the company's DESIGN goes. Not "we would execute well" —
  the specific approach the CTO landed on and why it beats the alternatives
  they compared it against. Name the approaches that were considered and
  dropped, and why. If the company found a way to remove the hardest manual
  step, that IS the answer to this question.
* Question 7 is ONE recommendation, not a menu, and it is a recommendation of
  the SOLUTION THE COMPANY DESIGNED — not a verdict on the Founder's sentence.
  Say what we build first, what we deliberately postpone, and what the
  direction survived. If a smaller version has a better chance, say that
  instead.
* If the distinctive part was dropped, Question 7 says what it would cost to
  keep it, what the cheapest version that preserves it would look like, and
  what result would bring it back. "We postponed the hardware" is not an
  answer; "an off-the-shelf sensor clipped to an existing bottle, two weeks,
  and we revisit if people fake the tap" is.
* "Investigate first" is still a legitimate answer, but ONLY after the company
  has formed the best workable concept it can — and then it must say WHAT
  PROPOSED SOLUTION the investigation is validating, and what result would kill
  it. "This has a weakness, therefore investigate" is not an answer; the
  company's job was to try to engineer the weakness away first.
* Question 9: the company DECIDES FIRST, then escalates only what it genuinely
  cannot. For every fork, state the answer WE recommend and the consequence of
  it, then say what would make the Founder overrule us. A fork the company
  could have settled from the Founder's own stated goal is not a Founder
  decision — it is work we did not do. Only decisions where two honest answers
  produce two DIFFERENT briefs, and say what changes for each. ZERO questions
  is a passing score. One or two beats eight. Never invent one to look
  thorough. Cap: three.
* If the company NARROWED what the Founder asked for — read "learn X" as
  "feel successful at something X-like", or an audience as a slice of it — say
  so in Question 1 and say how and when the full thing is reached. Quietly
  redefining the Founder's words into something easier to deliver is the most
  expensive mistake on this page, because it is the one they cannot see.
* Where an unknown could change the ARCHITECTURE — what exists today, what a
  law requires, what a platform allows — do not leave it as a disclaimer.
  Question 7 names it as a bounded piece of work: what would be looked up, by
  whom, and what answer would change the recommendation. "Unknown because
  nobody looked" must never be the permanent operating model of a Full-depth
  reading — and where the Research lane DID look, an unknown it has already
  settled must not be listed as an open question. Reporting a fact as unknown
  when the evidence below answers it wastes the Founder's attention on work
  that is already done.
* QUESTION 4 AND EVERY MARKET CLAIM: there are exactly two kinds of statement
  you may make about the outside world, and they must never be blended.
  VERIFIED — it appears in the evidence below, and you name its source when you
  use it. UNVERIFIED — everything else, including anything you happen to
  believe, which you must label as not checked. If research was not performed,
  say that plainly and do not describe the market as though it had been. If it
  WAS performed, say what was actually found, cite it, and say what the search
  did not settle. Never write a sentence that leaves the Founder unable to tell
  which of the two they are reading — that ambiguity is the exact failure this
  company built a Research lane to end.
* Answer all ten. One you cannot answer well is answered "we don't know, and
  here is why", in the concise layer, never dropped.
{COMMON_RULES}
THE COMPANY VIEW is a judgement, not a score. No numbers, no percentages, no
confidence figures, no meters. Six fields, exactly the six.

FOUR JUDGEMENTS THAT MUST NOT BE COLLAPSED INTO ONE. The Company View grades
THE FOUNDER'S IDEA, not the architecture the company happened to pick:

  1. Is the problem worth solving?          -> this is what "opp" rates.
  2. Are there several credible ways at it?  -> solution space.
  3. Which one do we recommend?              -> answers 5 and 7.
  4. What could kill THAT ONE?               -> "threat", labelled as such.

A risk to the architecture WE chose is not a verdict on the Founder's idea. The
failure to avoid, seen in a real round: the company invented a tactic, called
that tactic "the entire differentiator", found a legal risk in it, and lowered
the opportunity to Medium — grading its own invention while appearing to grade
the Founder's idea. If a blocker only threatens the approach we picked, and
other credible approaches were not explored, "opp" does not move. Say instead
that this approach is at risk and name what else remains open.

AND IF WE REPLACED THE FOUNDER'S THESIS, SAY SO IN ONE PLAIN SENTENCE, in
"diff", with the bridge: what theirs was, that we took it seriously, and why
ours is recommended instead. Improving or replacing their implementation is
your job. Doing it silently, so the Company View describes a different product
than the one they brought in, is not.

CHECK THE VIEW AGAINST ITSELF before you finish. If "merit" says a signal is
weak evidence and the recommended approach relies on that same signal, you have
contradicted yourself — say the trade out loud rather than presenting the
replacement as though it solved the problem you just named.

Your recommendation is the one thing on this page with consequences: it decides
whether the Founder is even offered the choice to approve. There is no
"approve anyway" button behind you.

  Proceed                      — build it as understood.
  Proceed with narrowed scope  — build it, smaller, and you have said which part.
  Investigate first            — something you do not know would change what gets built.
  Reconsider                   — as it stands, this should not be built.

"Investigate first" and "Reconsider" exist to be used. If the honest answer is
that this idea is not ready, saying "Proceed" to be agreeable is the single
worst thing you can do here — it makes every evaluation the company ever does
worthless. Where information you lack materially affects the decision, the
honest recommendation is "Investigate first", not "Proceed".

This is round {round_no}.{" Say what changed since the last round — the Founder should see the "
 "difference, not reread everything." if rounds else ""}
{SYNTH_CONTRACT}"""
    # Returns RAW text, deliberately. Parsing happens in run_evaluation, where
    # the raw is still in scope if it needs preserving — the old shape parsed
    # here and threw the evidence away on failure, taking a completed
    # multi-agent evaluation with it.
    #
    # The one call that gets its own budget: it reads every role's reading, the
    # attack and the repair, and writes the largest output in the system.
    return _invoke("orchestrator", transcript, idea_id,
                   budget=agent_runtime.IDEA_SYNTHESIS_BUDGET_USD,
                   timeout_s=agent_runtime.IDEA_SYNTHESIS_TIMEOUT_S)


DIAGNOSTICS = HERE / "diagnostics"

REPAIR_INSTRUCTION = """You wrote the answer below, and it could not be parsed as JSON.

THIS IS A FORMAT REPAIR ONLY. It is not a chance to think again.

  * Do NOT reconsider the idea.
  * Do NOT change the recommendation, the opportunity, or any judgement.
  * Do NOT add, remove, soften or improve any answer.
  * Keep every word of substance exactly as you wrote it.

Your ONLY job is to return the same content as valid JSON in the required
shape. If your original was truncated mid-sentence, close that sentence
minimally and keep everything else; do not invent content that is not there.

If some required field is genuinely absent from your original — not merely
malformed, but never written — say so in plain text instead of inventing it.
Fabricating an answer the company never gave is worse than failing.

Reply with ONLY the JSON object. No preface, no explanation, no code fence.

--- YOUR ORIGINAL ANSWER, VERBATIM ---
"""


def _preserve_diagnostics(idea_id: int, blobs: dict[str, str]) -> Path | None:
    """Keep what the company actually returned when it could not be used.

    A failed evaluation used to vanish entirely — several real model calls, and
    nothing left to look at afterwards. Written next to the code but gitignored:
    it contains the Founder's idea and the agents' words, which are theirs."""
    try:
        DIAGNOSTICS.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = DIAGNOSTICS / f"idea-{idea_id}-{stamp}.txt"
        parts = [f"Idea {idea_id} — evaluation failed at {stamp}", "=" * 70, ""]
        for name, text in blobs.items():
            parts += [f"----- {name} -----", (text or "(empty)"), ""]
        path.write_text("\n".join(parts), encoding="utf-8")
        path.chmod(0o600)
        return path
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return None


def _parse_with_one_repair(raw: str, idea_id: int | None, contract: str, stage: str,
                           evidence: dict[str, str] | None = None,
                           label: str = "the reformatting attempt") -> tuple[dict, str | None, bool]:
    """Parse a Chief of Staff answer, with exactly ONE repair attempt.

    `contract` is the shape that answer was asked for, so the repair asks for
    the SAME shape rather than assuming the final-synthesis one. `stage` names
    the step for the error and the diagnostics file.

    Returns (parsed, raw_repair_or_None, was_repaired). Raises EvaluationError
    carrying nothing to save if both attempts fail.

    Repair fires on a PARSE failure only — never on a valid JSON that is missing
    a required answer. That distinction is the whole point: malformed text with
    the content present can be honestly reformatted, whereas a genuinely absent
    answer could only be "repaired" by inventing one, and this company does not
    invent. A missing answer stays a hard failure.

    One attempt, no loop. A model that cannot produce the shape twice will not
    produce it on the fifth try, and each try is real usage."""
    try:
        return _extract_json(raw, stage=stage), None, False
    except EvaluationError:
        if not (raw or "").strip():
            # Nothing came back. There is nothing to reformat, and asking would
            # spend a real call to fail again.
            raise

    _note(idea_id, "Chief of Staff", "That answer came back misformatted — asking for it again in "
                                     "the right shape. No rethinking, no extra reading.")
    raw_repair = _invoke("orchestrator", REPAIR_INSTRUCTION + raw + "\n\n" + contract, idea_id,
                         budget=agent_runtime.IDEA_SYNTHESIS_BUDGET_USD,
                         timeout_s=agent_runtime.IDEA_SYNTHESIS_TIMEOUT_S)
    # Recorded BEFORE parsing it. Recording it only on success would throw away
    # the evidence in the one case anyone needs it — the repair that failed.
    if evidence is not None:
        evidence[label] = raw_repair
    return _extract_json(raw_repair, stage=stage), raw_repair, True


# ------------------------------------------------------------ the whole ---

REQUIRED_KEYS = ("opp", "why", "merit", "threat", "diff", "rec")
VALID_RECS = ("Proceed", "Proceed with narrowed scope", "Investigate first", "Reconsider")


_QNUM = re.compile(r"^\s*(?:q(?:uestion)?\s*)?(\d{1,2})\s*[.):]?\s*$", re.I)


def _unwrap(result: dict) -> dict:
    """Find the object that holds the answers when it arrived one level down.

    Models wrap a correct payload in a container of their own naming —
    {"evaluation": {...}}, {"result": {...}} — often enough that rejecting it
    discards a COMPLETE evaluation over where it was put. Descends at most one
    level, and only when there is exactly one candidate, so this can never pick
    between two competing answers. Nothing is added or altered."""
    if "answers" in result or "view" in result:
        return result
    nested = [v for v in result.values() if isinstance(v, dict) and ("answers" in v or "view" in v)]
    return nested[0] if len(nested) == 1 else result


def _locate_answers(answers):
    """Return the ten answers keyed "1".."10", or None if they are not all here.

    This is SHAPE normalisation and nothing else. Every one of the ten must be
    present; a missing answer stays a hard failure, because the only way to fix
    an absent answer is to invent one and this company does not invent. What it
    does tolerate is the same ten answers arriving in a list, or under keys like
    "Q1" or "question 3" — a complete evaluation in a different container is
    still a complete evaluation, and rejecting it was throwing away a paid-for
    run over punctuation."""
    if isinstance(answers, (list, tuple)):
        # Only an exact ten can be mapped to the ten questions without guessing
        # which one is missing.
        if len(answers) != 10:
            return None
        return {str(n): answers[n - 1] for n in range(1, 11)}
    if not isinstance(answers, dict):
        return None
    out = {}
    for key, value in answers.items():
        m = _QNUM.match(str(key))
        if m and 1 <= int(m.group(1)) <= 10:
            out.setdefault(str(int(m.group(1))), value)
    return out or None


# What an answer's expanded half must clear to count as working rather than a
# label. The failures seen in a real run were 19-31 characters — "expanded:
# section 7", the contract's own placeholder pasted back.
MIN_EXPANDED_CHARS = 90
NO_WORKING = "No further working — the concise answer is the whole of it."
_PLACEHOLDER = re.compile(r"^\s*(?:<<.*>>|expanded\s*[:\-].{0,60}|section[s]?\s+[\d,\sand]+)\s*$",
                          re.I | re.S)


def _expanded_or_note(expanded: str, concise: str) -> str:
    """The expanded half, or an honest sentence saying there isn't one.

    A real run stored ten expanded sections of ~20 characters each: the model
    had echoed the contract's own placeholder text. Nothing caught it, so the
    page offered ten expanders that opened onto a fragment. This is NOT a hard
    failure — the concise layer is intact and the evaluation was paid for, and
    discarding it would cost more than it saves. It is relabelling an absence
    as an absence, which is the one thing the company must always do rather
    than let a stub pass for working."""
    text = re.sub(r"<[^>]+>", "", expanded or "").strip()
    if not text or _PLACEHOLDER.match(text) or len(text) < MIN_EXPANDED_CHARS:
        return NO_WORKING
    if text == re.sub(r"<[^>]+>", "", concise or "").strip():
        # Restating the concise answer is not working either.
        return NO_WORKING
    return expanded


def _validate(result: dict) -> tuple[dict, dict, str]:
    result = _unwrap(result)
    answers = _locate_answers(result.get("answers"))
    if answers is None:
        raise EvaluationError("the company's answer arrived without its ten answers. Nothing was "
                              "saved.")
    clean: dict[str, list[str]] = {}
    for n in range(1, 11):
        entry = answers.get(str(n))
        if isinstance(entry, str):
            entry = [entry, ""]
        if not isinstance(entry, (list, tuple)) or not entry:
            raise EvaluationError(f"the company did not answer question {n}. All ten are required, "
                                  "so nothing was saved.")
        concise = str(entry[0])
        clean[str(n)] = [concise,
                         _expanded_or_note(str(entry[1]) if len(entry) > 1 else "", concise)]

    view = result.get("view")
    if not isinstance(view, dict) or any(k not in view for k in REQUIRED_KEYS):
        raise EvaluationError("the company's closing view came back incomplete. Nothing was saved.")
    view = {k: str(view[k]) for k in REQUIRED_KEYS}
    if view["rec"] not in VALID_RECS:
        raise EvaluationError(f"the company's recommendation, '{view['rec']}', is not one of the "
                              "four it is allowed to give. Nothing was saved.")
    if view["opp"] not in ("High", "Medium", "Low", "Unclear"):
        view["opp"] = "Unclear"
    return clean, view, str(result.get("title") or "").strip()


def run_evaluation(idea_id: int, idea: dict, rounds: list[dict],
                   founder_note: str | None = None) -> None:
    """The whole thing, start to finish. Called on a background thread; every
    exit path clears the running marker, so a failure never leaves an idea
    stuck saying it is being evaluated."""
    error: str | None = None
    repaired = False
    perspectives: list[tuple[str, str]] = []
    # Everything any agent actually said, recorded as it arrives rather than at
    # the end. A failure at ANY stage can now write a diagnostics file, because
    # the raw text is already in here by the time the exception is raised.
    # Previously only the final synthesis was preserved, so the most common
    # real failure — roster selection — left nothing behind at all.
    evidence: dict[str, str] = {}
    stage = "starting"
    # Declared here, not inside the live branch, so rehearsal and every failure
    # path have the same shape to report. Rehearsal never searches, and saying
    # "not-needed" for it is the truthful answer: nobody was asked anything.
    packet = _empty_packet()
    research_status = "not-needed"
    searches_done = 0
    try:
        if REHEARSAL:
            _note(idea_id, "Rehearsal mode", "No agent will be asked and nothing will be spent.")
            roster = _rehearsal_roster()
            result = _rehearsal_result(idea, rounds)
        else:
            stage = ROSTER_STAGE
            _note(idea_id, "Chief of Staff", "Choosing who should weigh in on this idea.")
            roster, roster_repaired = _select_roster(idea, rounds, founder_note, idea_id, evidence)
            if roster_repaired:
                _note(idea_id, "Chief of Staff", "That came back misformatted; reformatted and "
                                                 "readable. Who was chosen is unchanged.")
            names = ", ".join(ROLE_LABEL[r] for r, _ in roster["in"])
            _note(idea_id, "Chief of Staff", f"Asked {names}. Depth: {roster['depth']}.")

            # The roles read AT THE SAME TIME. Each one reads the same idea
            # from its own angle and none of them sees another's answer, so
            # running them one after another only ever made the Founder wait
            # N times longer for the same result. Bounded by the runtime's own
            # MAX_CONCURRENT_INVOCATIONS, so this asks for concurrency rather
            # than assuming it.
            # INVENT, then ATTACK, then IMPROVE — the Founder's order. The
            # roles that BUILD the direction run in sequence, each reading what
            # the previous one worked out, because a technical architecture that
            # has not seen the product outcome or the intended experience is
            # just a guess. Everyone else still runs alongside them.
            chosen = [role for role, _why in roster["in"]]
            builders = [r for r in INVENTORS if r in chosen]
            others = [r for r in chosen if r not in builders and r != ATTACKER]
            said_by: dict[str, str] = {}
            failed: list[EvaluationError] = []

            def _run(role, earlier=""):
                _note(idea_id, ROLE_LABEL[role], "Working on it.")
                try:
                    said_by[role] = _perspective(role, idea, rounds, founder_note,
                                                 roster["depth"], idea_id, earlier)
                    evidence[f"{ROLE_LABEL[role]} said"] = said_by[role]
                    _note(idea_id, ROLE_LABEL[role], "Done.")
                except EvaluationError as exc:
                    failed.append(EvaluationError(f"{ROLE_LABEL[role]} could not answer. "
                                                  + str(exc),
                                                  stage=f"{ROLE_LABEL[role]} working on the idea"))
                    _note(idea_id, ROLE_LABEL[role], "Could not answer.")

            stage = "designing a direction"
            # Product and Design have no dependency on each other: one states
            # the outcome, the other the lowest-friction experience, and both
            # read the same raw idea. Running them one after the other cost the
            # Founder a whole model call of waiting for nothing. The CTO still
            # runs LAST and sees both, which is the dependency that actually
            # matters — an architecture that has not seen the outcome or the
            # intended experience is a guess.
            first = [r for r in builders if r != "cto"]
            last = [r for r in builders if r == "cto"]
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=(len(others) + len(first)) or 1) as pool:
                running = [pool.submit(_run, r) for r in others + first]
                for f in running:
                    f.result()
            for role in last:
                _run(role, "\n\n".join(
                    f"--- {ROLE_LABEL[r]} said ---\n{said_by[r]}"
                    for r in builders if r in said_by))
            if failed:
                raise failed[0]
            for role in chosen:
                if role in said_by:
                    perspectives.append((role, said_by[role]))

            # The direction the company now proposes — what Red Team attacks.
            direction = "\n\n".join(f"--- {ROLE_LABEL[r]} ---\n{said_by[r]}"
                                     for r in builders if r in said_by)

            # ---------------------------------------------- the Research lane
            # The company has now invented a direction, so it knows which
            # solution categories are worth searching across — and nobody has
            # attacked or defended anything yet, so the evidence can still
            # change the answer instead of merely decorating it.
            #
            # Runs only when the Chief of Staff said the recommendation depends
            # on outside facts, and never at Light depth: an internal tool for
            # one person does not need a market scan, and buying one would
            # spend the Founder's money to confirm what they already know.
            wants = bool(roster.get("outside_facts")) and roster["depth"] != "Light"
            research_status = "not-needed" if not wants else "unavailable"
            if wants:
                stage = RESEARCH_STAGE
                _note(idea_id, "Research", "Searching the web for what is already out there.")
                try:
                    packet, _rep, n = _research(roster.get("research_questions") or [],
                                                direction, idea, rounds, founder_note, idea_id)
                    searches_done += n or 0
                    research_status = "done"

                    # A second sweep ONLY for a category the first sweep
                    # discovered — the case the Founder named: research turns up
                    # a whole class of solution nobody listed, and stopping here
                    # would mean knowing about it and not looking at it. Bounded
                    # at MAX_SWEEPS with no loop, so this can never become an
                    # open-ended spend.
                    if packet["new_categories"] and MAX_SWEEPS > 1:
                        chasing = "; ".join(packet["new_categories"][:3])
                        _note(idea_id, "Research",
                              f"Found something nobody listed — going back out for: {chasing}")
                        try:
                            more, _rep2, n2 = _research(
                                roster.get("research_questions") or [], direction, idea, rounds,
                                founder_note, idea_id, sweep=2, chasing=chasing)
                            packet = _merge_packets(packet, more)
                            searches_done += n2 or 0
                        except EvaluationError:
                            # The first sweep's evidence is already good. A
                            # failed follow-up narrows what was learned; it does
                            # not invalidate it.
                            _note(idea_id, "Research",
                                  "The second sweep failed — keeping what the first one found.")
                    evidence["what the Research lane found"] = json.dumps(packet, indent=2)
                    _note(idea_id, "Research",
                          f"Done — {len(packet['findings'])} cited finding(s) "
                          f"from {searches_done or 'an unreported number of'} search(es).")
                except EvaluationError as exc:
                    # RESEARCH FAILING IS NOT THE EVALUATION FAILING. The
                    # company can still answer; it just may not pretend it
                    # checked. The status carries that honestly all the way to
                    # the Founder's page.
                    research_status = "unavailable"
                    evidence["the Research lane could not search"] = str(exc)
                    _note(idea_id, "Research",
                          "Could not search — the company will answer without evidence and say so.")

            evidence_text = evidence_for_agents(packet, research_status)

            # ------------------------------------------ reconsider on evidence
            # Research is not a box to tick after the answer is written. The
            # roles whose ranking the evidence could overturn get to revise it
            # BEFORE the attack, which is what makes a finding able to replace
            # the provisional architecture rather than sit beside it.
            if research_status == "done" and packet["findings"]:
                rethinkers = [r for r in ("product", "cto") if r in said_by]
                if rethinkers:
                    stage = "reconsidering the direction against the evidence"
                    revisions: dict[str, str] = {}

                    def _rethink(role):
                        _note(idea_id, ROLE_LABEL[role], "Reading the evidence again.")
                        try:
                            revisions[role] = _reconsider(role, direction, evidence_text, idea,
                                                          rounds, founder_note, idea_id)
                            _note(idea_id, ROLE_LABEL[role], "Done.")
                        except EvaluationError:
                            # Same rule as the late addition: a revision is a
                            # bonus. The original reading still stands.
                            _note(idea_id, ROLE_LABEL[role],
                                  "Could not revise — their first reading stands.")

                    with concurrent.futures.ThreadPoolExecutor(
                            max_workers=len(rethinkers)) as pool:
                        for f in [pool.submit(_rethink, r) for r in rethinkers]:
                            f.result()
                    for role in rethinkers:
                        if role in revisions:
                            evidence[f"{ROLE_LABEL[role]} after the evidence"] = revisions[role]
                            perspectives.append((f"{role}-evidence", revisions[role]))
                            direction += (f"\n\n--- {ROLE_LABEL[role]}, after reading the "
                                          f"research ---\n{revisions[role]}")

            if direction and ATTACKER in chosen:
                stage = "the Red Team attacking that direction"
                _note(idea_id, ROLE_LABEL[ATTACKER],
                      "Attacking the direction the company designed.")
                attack = _attack(direction, idea, rounds, founder_note, idea_id, evidence_text)
                evidence["Red Team attacked the direction"] = attack
                perspectives.append((ATTACKER, attack))
                said_by[ATTACKER] = attack

                # IMPROVE. One repair pass, by whichever builder owns the
                # objections most directly. This is the step the Founder said
                # was missing: a weakness gets engineered away here, or is
                # honestly declared unfixable — not merely recorded and used as
                # a reason to stop.
                mender = "cto" if "cto" in builders else (builders[-1] if builders else None)
                if mender:
                    stage = f"{ROLE_LABEL[mender]} repairing the direction"
                    _note(idea_id, ROLE_LABEL[mender], "Repairing what survived the attack.")
                    fixed = _repair(mender, direction, attack, idea, rounds, founder_note,
                                    idea_id, evidence_text)
                    evidence[f"{ROLE_LABEL[mender]} repaired the direction"] = fixed
                    perspectives.append((f"{mender}-repair", fixed))

                    # The roster was chosen from the Founder's raw sentence,
                    # before anyone knew what the company would design. If the
                    # direction has since moved into somebody else's territory
                    # — children's data, payments, another platform's rules —
                    # bring them in now. ONCE, for ONE role: reopening a
                    # decision beats freezing it, but an evaluation that keeps
                    # discovering new roles never finishes.
                    late = _late_addition(fixed, chosen)
                    if late:
                        stage = f"{ROLE_LABEL[late]} joining late"
                        _note(idea_id, ROLE_LABEL[late],
                              "Brought in — the direction moved into their territory.")
                        try:
                            said = _perspective(late, idea, rounds, founder_note,
                                                roster["depth"], idea_id,
                                                direction + "\n\n--- what it became after the "
                                                "Red Team attacked it ---\n" + fixed)
                            evidence[f"{ROLE_LABEL[late]} said (joined late)"] = said
                            perspectives.append((late, said))
                            roster["in"].append([late, "brought in after the direction moved into "
                                                       "their territory"])
                            _note(idea_id, ROLE_LABEL[late], "Done.")
                        except EvaluationError:
                            # A late addition is a bonus, not a dependency. The
                            # evaluation already has everything it needs.
                            _note(idea_id, ROLE_LABEL[late],
                                  "Could not answer — continuing without them.")

            stage = "writing the final answer"
            _note(idea_id, "Chief of Staff", "Writing one answer.")
            raw_final = _synthesise(idea, rounds, founder_note, roster, perspectives, idea_id,
                                    evidence_text)
            evidence["the Chief of Staff's final answer"] = raw_final
            try:
                result, _raw_repair, repaired = _parse_with_one_repair(
                    raw_final, idea_id, SYNTH_CONTRACT, stage, evidence)
            except EvaluationError as exc:
                # Both attempts failed. Everything the company said is kept —
                # several real model calls produced it, and it is the only
                # evidence of what went wrong.
                raise EvaluationError(
                    "the company answered, but it could not be read as a result even after being "
                    "asked to reformat it. Nothing was saved, because a half-understood brief is "
                    "worse than none.<br><br>Evaluating again re-reads the idea from scratch.",
                    stage=exc.stage or stage) from exc
        answers, view, title = _validate(result)
        if repaired:
            _note(idea_id, "Chief of Staff", "Reformatted and readable. Substance unchanged.")

        args = ["idea-round-add", "--idea-id", str(idea_id),
                "--recommendation", view["rec"],
                "--depth", roster["depth"],
                "--depth-reason", roster["depth_reason"],
                "--roster", json.dumps({"in": [[ROLE_LABEL[r], w] for r, w in roster["in"]],
                                        "out": roster["out"]}),
                "--answers", json.dumps(answers),
                "--view", json.dumps(view)]
        args += ["--research-status", research_status]
        if research_status == "done":
            args += ["--research", json.dumps(packet)]
            if searches_done:
                args += ["--research-searches", str(searches_done)]
        if REHEARSAL:
            args.append("--rehearsal")
        if repaired:
            args.append("--repaired")
        if title:
            args += ["--title", title]
        if founder_note:
            args += ["--founder-note", founder_note]
        if rounds and result.get("changed"):
            args += ["--changed-note", str(result["changed"])]
        _opsdb(*args)
        _note(idea_id, "Chief of Staff", "Done.")

    except EvaluationError as exc:
        # ONE place that turns any evaluation failure into what the Founder
        # reads and what a developer can debug from. A semantic failure — valid
        # JSON, but an answer genuinely missing — is NOT repaired, because the
        # only way to "fix" a missing answer is to invent one. Its evidence is
        # still kept, exactly like every other stage's.
        failed_at = exc.stage or stage
        error = f"it failed while <b>{failed_at}</b>. " + str(exc)
        if evidence:
            saved = _preserve_diagnostics(idea_id, {"the stage that failed": failed_at, **evidence})
            if saved:
                error += (f"<br><br>What the company actually said is kept in <code>{saved}</code>"
                          + (", including each role's reading" if perspectives else "")
                          + ".")
    except Exception:
        traceback.print_exc(file=sys.stderr)
        error = (f"something broke inside the evaluation while <b>{stage}</b>. That is a bug on "
                 "our side, not something you did. Nothing was saved.")
        # A crash used to leave nothing behind either, even when several agents
        # had already answered.
        saved = _preserve_diagnostics(idea_id, {
            "the stage that failed": stage,
            "the crash": traceback.format_exc(),
            **evidence}) if evidence else None
        if saved:
            error += f"<br><br>What had been said so far is kept in <code>{saved}</code>."
    finally:
        try:
            if error:
                _opsdb("idea-evaluation-end", "--idea-id", str(idea_id), "--error", error)
            else:
                _opsdb("idea-evaluation-end", "--idea-id", str(idea_id))
        except Exception:
            traceback.print_exc(file=sys.stderr)
        _clear(idea_id)


def start(idea_id: int, idea: dict, rounds: list[dict], founder_note: str | None = None) -> None:
    """Mark it running, then hand off to a thread. The marker is written BEFORE
    the thread starts, so a double-clicked button is refused by the database
    rather than racing."""
    args = ["idea-evaluation-start", "--idea-id", str(idea_id)]
    if founder_note:
        args += ["--note", founder_note]
    _opsdb(*args)
    _clear(idea_id)
    _note(idea_id, "Chief of Staff", "Reading your idea.")
    threading.Thread(target=run_evaluation, args=(idea_id, idea, rounds, founder_note),
                     daemon=True).start()
