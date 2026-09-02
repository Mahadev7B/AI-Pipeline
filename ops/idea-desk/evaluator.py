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

import json
import os
import re
import subprocess
import sys
import threading
import traceback
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
                                                 "outside the company"]]}


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
    that mean something to them."""


# --------------------------------------------------------------- helpers ---

def _opsdb(*args: str) -> str:
    proc = subprocess.run([sys.executable, str(OPSDB), *args], capture_output=True, text=True,
                          timeout=30)
    if proc.returncode != 0:
        raise EvaluationError((proc.stderr or proc.stdout).strip().removeprefix("error: "))
    return proc.stdout.strip()


def _extract_json(text: str) -> dict:
    """Models wrap JSON in prose or fences more often than not. Take the
    outermost object and parse that; if it will not parse, say so plainly
    rather than storing something half-understood."""
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
                          "Nothing was saved. Trying again usually clears it.")


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


def _invoke(agent: str, transcript: str, idea_id: int | None = None) -> str:
    result = agent_runtime.invoke_agent(
        agent, transcript,
        timeout_s=agent_runtime.IDEA_EVALUATION_TIMEOUT_S,
        wait_for_slot=True)
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
    if idea.get("current_audience"):
        lines += ["", f"WHO IT IS FOR: {idea['current_audience']}"]
    if idea.get("current_trigger"):
        lines += [f"WHAT PROMPTED IT: {idea['current_trigger']}"]
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
  funding figure or a feature. No agent here can browse the web. If current
  information about the outside world would change the answer, SAY that
  research was not performed and label anything you do say as company
  recollection, never as verified fact.
* Never praise an idea because the Founder proposed it. If the merits are
  weak, say they are weak. You are useful here only to the extent that you
  are willing to disagree.
* Do not restate the Founder's own sentence back to them. Saying "you want a
  dashboard" when they asked for a dashboard is a failure, not an answer.
* Say what you do not know, in the answer, rather than working around it.
"""


# ------------------------------------------------------- phase 1: roster ---

def _select_roster(idea: dict, rounds: list[dict], founder_note: str | None,
                   idea_id: int | None = None) -> dict:
    transcript = f"""You are the Chief of Staff of an AI software company. The Founder has brought
in an idea. Your first job is to decide WHO should read it, and HOW DEEPLY the
company should look — before anyone spends time on it.

{_idea_block(idea, rounds, founder_note)}

WHO YOU MAY CHOOSE FROM:
  product   — the problem, the scope, what belongs in a first version. ALWAYS on the roster.
  cto       — what is technically true, what the existing records can support.
  red-team  — how this fails, what breaks, what is being assumed.
  ceo       — positioning and market direction. Only when someone OUTSIDE the company chooses this.
  design    — only when the experience or the shape of the thing materially decides the answer.
  financial — only when money genuinely changes hands or the cost structure decides it.
  security  — only when identity, payments or sensitive data are actually in play.

Choose ONLY the perspectives that could materially change how this idea is
read. Choosing everyone is the failure mode, not the safe option. Product plus
one or two others is a good roster. Four others is the maximum.

HOW DEEP:
  Light    — internal tooling, one user, nothing outside the company changes. No competitor work.
  Standard — real users beyond the Founder, but no market to compete in yet.
  Full     — something people outside would choose between this and an alternative.

Reply with ONLY this JSON and nothing else:

{{
  "depth": "Light" | "Standard" | "Full",
  "depth_reason": "one sentence, in the Founder's terms, why this depth and not another",
  "in":  [["product", "why THIS idea needs them, specifically"], ...],
  "out": [["ceo, financial", "why they would add nothing here"], ...]
}}

"out" is not optional: naming who you left out and why is how the Founder can
tell you chose rather than defaulted.
"""
    raw = _invoke("orchestrator", transcript, idea_id)
    data = _extract_json(raw)

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
    return {
        "depth": depth if depth in ("Light", "Standard", "Full") else "Standard",
        "depth_reason": str(data.get("depth_reason") or ""),
        "in": chosen,
        # Take the first two elements, never unpack — a three-element entry is
        # well-formed JSON and used to raise ValueError here.
        "out": [[str(e[0]), str(e[1])] for e in (data.get("out") or [])
                if isinstance(e, (list, tuple)) and len(e) >= 2],
    }


# -------------------------------------------------- phase 2: perspectives ---

ROLE_BRIEF = {
    "product": "the problem behind the request, who it is for, what belongs in a first useful "
               "version and what should wait. Name the scope you would cut.",
    "cto": "what is technically true here. What would this actually require, what in our existing "
           "system supports or contradicts it, and what would make it dishonest to build as asked.",
    "red-team": "how this fails. The assumption that would sink it, the thing being decided too "
                "early, the version of this that quietly becomes a huge project.",
    "ceo": "whether this should exist, and for whom. Positioning, and whether anyone outside would "
           "choose it. Say plainly if there is no outside audience.",
    "design": "whether the experience the Founder is imagining is the right one, and whether the "
              "shape they named is a requirement or a sketch.",
    "financial": "the money. What it costs to build and run, what it could return, and whether the "
                 "economics change the recommendation.",
    "security": "identity, secrets, personal data, and what could go wrong with them. Only raise "
                "what genuinely applies.",
}


def _perspective(role: str, idea: dict, rounds: list[dict], founder_note: str | None,
                 depth: str, idea_id: int | None = None) -> str:
    transcript = f"""You are the {ROLE_LABEL[role]} of an AI software company. The Founder has brought
in an idea and the Chief of Staff has asked specifically for your reading of it.

{_idea_block(idea, rounds, founder_note)}

HOW DEEP THE COMPANY IS GOING: {depth}.
{"At Light depth there is no market to research and no competitor work to do — do not invent any."
 if depth == "Light" else ""}

YOUR ANGLE — answer from it and not from everyone else's: {ROLE_BRIEF[role]}
{COMMON_RULES}
Write at most 400 words of plain prose. No headings, no JSON, no bullet
theatre. The Chief of Staff reads this and writes the single answer the Founder
sees, so write for a colleague who will disagree with you, not for the Founder.

If your honest view is that this idea should not be built, or should be built
much smaller, say so in your first sentence.
"""
    return _invoke(role, transcript, idea_id)


# ---------------------------------------------------- phase 3: synthesis ---

SYNTH_CONTRACT = """
Reply with ONLY this JSON object and nothing else. Every value is a string.
The "concise" strings may use <b>...</b> for the few words that matter most.
The "expanded" strings may additionally use <div class="sk">Section heading</div>
to label which of the fifteen sections you are answering from, and
<div class="two"><div>...</div><div>...</div></div> for a two-column split.
No other HTML, no links, no scripts.

{
  "title": "a short name for this idea, 3-7 words, how the company would refer to it",
  "answers": {
    "1":  ["Did the company understand my idea? — a few sentences",  "expanded: sections 1 and 2"],
    "2":  ["What am I really trying to achieve? — the outcome, not the feature", "expanded: section 3"],
    "3":  ["Why might this be worth building?",  "expanded: section 4"],
    "4":  ["What already exists?",               "expanded: sections 5 and 6"],
    "5":  ["What could make ours different?",    "expanded: section 7"],
    "6":  ["What could make it fail?",           "expanded: section 8"],
    "7":  ["What does the company recommend?",   "expanded: sections 9, 10 and 12"],
    "8":  ["What assumptions did the company make?", "expanded: section 11"],
    "9":  ["What decisions do you need from me?",    "expanded: section 13"],
    "10": ["How will we know we succeeded?",         "expanded: section 14"]
  },
  "view": {
    "opp":    "High" | "Medium" | "Low" | "Unclear",
    "why":    "two to four sentences",
    "merit":  "the single biggest merit",
    "threat": "the single biggest threat",
    "diff":   "the best differentiation, or 'none we can see yet'",
    "rec":    "Proceed" | "Proceed with narrowed scope" | "Investigate first" | "Reconsider"
  },
  "changed": "what changed since the previous round — omit entirely if this is round 1"
}
"""


def _synthesise(idea: dict, rounds: list[dict], founder_note: str | None, roster: dict,
                perspectives: list[tuple[str, str]], idea_id: int | None = None) -> dict:
    voices = "\n\n".join(f"--- {ROLE_LABEL[role]} said ---\n{text}" for role, text in perspectives)
    round_no = len(rounds) + 1
    transcript = f"""You are the Chief of Staff of an AI software company. Your colleagues have each
read the Founder's idea. They may disagree with each other. The Founder never
sees their separate reports — they see ONE answer, and you write it.

{_idea_block(idea, rounds, founder_note)}

DEPTH: {roster['depth']} — {roster['depth_reason']}

WHAT YOUR COLLEAGUES SAID:

{voices}

YOUR JOB: answer these ten questions, and close with the company's view.

The ten answers are the layer the Founder decides on. Everything they need to
decide is there, in a couple of sentences each, readable in two minutes without
opening anything. The expanded string behind each is where someone CHECKS that
decision. Nothing that would change the decision may live only in the expanded
part.

Rules that are easy to get wrong, and matter:

* Question 2 is the one that proves you understood. Not "you want a
  dashboard" — that is their own word handed back. Say what they are actually
  trying to end up with.
* Question 7 is ONE recommendation, not a menu. What we build first, and what
  we deliberately postpone. If a smaller version has a better chance, say that
  instead.
* Question 9: only decisions where two honest answers would produce two
  DIFFERENT briefs, and say what changes for each. ZERO questions is a passing
  score. One or two beats eight. Never invent one to look thorough. Cap: three.
* Question 4: if research was not performed — and it was not — say so.
* Answer all ten. One you cannot answer well is answered "we don't know, and
  here is why", in the concise layer, never dropped.
{COMMON_RULES}
THE COMPANY VIEW is a judgement, not a score. No numbers, no percentages, no
confidence figures, no meters. Six fields, exactly the six.

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
    return _extract_json(_invoke("orchestrator", transcript, idea_id))


# ------------------------------------------------------------ the whole ---

REQUIRED_KEYS = ("opp", "why", "merit", "threat", "diff", "rec")
VALID_RECS = ("Proceed", "Proceed with narrowed scope", "Investigate first", "Reconsider")


def _validate(result: dict) -> tuple[dict, dict, str]:
    answers = result.get("answers")
    if not isinstance(answers, dict):
        raise EvaluationError("the company's answer arrived without its ten answers. Nothing was "
                              "saved.")
    clean: dict[str, list[str]] = {}
    for n in range(1, 11):
        entry = answers.get(str(n)) or answers.get(n)
        if isinstance(entry, str):
            entry = [entry, ""]
        if not isinstance(entry, (list, tuple)) or not entry:
            raise EvaluationError(f"the company did not answer question {n}. All ten are required, "
                                  "so nothing was saved.")
        clean[str(n)] = [str(entry[0]), str(entry[1]) if len(entry) > 1 else ""]

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
    try:
        if REHEARSAL:
            _note(idea_id, "Rehearsal mode", "No agent will be asked and nothing will be spent.")
            roster = _rehearsal_roster()
            result = _rehearsal_result(idea, rounds)
        else:
            _note(idea_id, "Chief of Staff", "Choosing who should weigh in on this idea.")
            roster = _select_roster(idea, rounds, founder_note, idea_id)
            names = ", ".join(ROLE_LABEL[r] for r, _ in roster["in"])
            _note(idea_id, "Chief of Staff", f"Asked {names}. Depth: {roster['depth']}.")

            perspectives = []
            for role, _why in roster["in"]:
                _note(idea_id, ROLE_LABEL[role], "Reading it.")
                perspectives.append((role, _perspective(role, idea, rounds, founder_note,
                                                        roster["depth"], idea_id)))

            _note(idea_id, "Chief of Staff", "Writing one answer.")
            result = _synthesise(idea, rounds, founder_note, roster, perspectives, idea_id)
        answers, view, title = _validate(result)

        args = ["idea-round-add", "--idea-id", str(idea_id),
                "--recommendation", view["rec"],
                "--depth", roster["depth"],
                "--depth-reason", roster["depth_reason"],
                "--roster", json.dumps({"in": [[ROLE_LABEL[r], w] for r, w in roster["in"]],
                                        "out": roster["out"]}),
                "--answers", json.dumps(answers),
                "--view", json.dumps(view)]
        if REHEARSAL:
            args.append("--rehearsal")
        if title:
            args += ["--title", title]
        if founder_note:
            args += ["--founder-note", founder_note]
        if rounds and result.get("changed"):
            args += ["--changed-note", str(result["changed"])]
        _opsdb(*args)
        _note(idea_id, "Chief of Staff", "Done.")

    except EvaluationError as exc:
        error = str(exc)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        error = ("something broke inside the evaluation. That is a bug on our side, not something "
                 "you did. Nothing was saved.")
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
