# Red Team — TASK-024 Idea Desk, slices 1 and 2

Reviewed at `044a4ad`. Scope: `ops/idea-desk/` (README, server, pages,
evaluator, doctor, seed), the TASK-024 sections of `ops/db/opsdb.py` and
`ops/db/schema.sql`, the `IDEA_EVALUATION*` / `cwd=` changes in
`ops/control-center/agent_runtime.py`, and DEC-013 through DEC-019.

Built directly by the orchestrator with no architecture, code or security
gate. This is the first gate it has been through.

**VERDICT: REJECT.**

Not because the feature is wrong — the three-artifact rule, immutability by
omission, read-only DB handle and shelled-out writes are genuinely good, and
better than most of what this repo has shipped. It is rejected because the
one thing the stage exists for (a gate that can say no) is not defended
anywhere in the code, and because there are at least four reachable states
that present to the Founder as "it is broken and I cannot tell why" — the
exact failure class this session has already produced twice.

---

## 1. The gate is structurally biased toward passing, and nothing measures it

The prompts do license disagreement, and better than I expected: `COMMON_RULES`
says "you are useful here only to the extent that you are willing to
disagree"; `_perspective` demands a first-sentence "do not build this" if
that is the honest view; `_synthesise` says "Investigate first" and
"Reconsider" exist to be used. That is real work and it is not nothing.

It is also all of the defence there is, and three structural facts undercut it:

**1a. The model that writes the verdict also decides whether its own critic
is in the room.** `_select_roster` lets the Chief of Staff choose whether
`red-team` participates. `product` is force-added in Python (`evaluator.py`
~line 218) precisely because the roster is otherwise the model's own
judgement — and then the one role whose entire function is "how this fails"
is left to that same judgement. A model disposed to agree with the Founder
does not need to fabricate praise; it only needs to leave Red Team off a
four-slot roster and write an honest-sounding "out" line about it. The roster
prompt even supplies the vocabulary: "Choosing everyone is the failure mode."
Fix: pin `red-team` the same way `product` is pinned, at least whenever depth
is not Light.

**1b. "Proceed with narrowed scope" is a pass, and it is the hedge a
reluctant model reaches for first.** `APPROVABLE` / `cmd_idea_approve` accept
two of the four recommendations. The one that lets a model half-refuse while
still clearing the gate is on the passing side. The predicted steady state is
not "always Proceed" — it is "always Proceed with narrowed scope," which
*looks* discriminating and never blocks anything. Note that both hand-written
seeded rounds in `seed_founder_idea.py` (lines 121, 239, 273, 281) are
"Proceed with narrowed scope." The only worked example the Founder will ever
see, twice, is the hedge that passes.

**1c. Telling the model its verdict blocks the Founder is pressure toward
Proceed, not away from it.** `_synthesise` says: "Your recommendation is the
one thing on this page with consequences: it decides whether the Founder is
even offered the choice to approve. There is no 'approve anyway' button behind
you." That is written as a call to gravity. A sycophancy-prone model reads it
as "if I say Reconsider I take the decision away from my Founder." You have
raised the felt cost of refusing and then asked it to refuse.

**1d. Nothing counts.** There is no query, no screen, no log line that would
ever show "we have evaluated N ideas and recommended a passing verdict N
times." `_validate` checks the recommendation is one of four strings and
nothing else. Without measurement the claim "this gate is load-bearing" is
unfalsifiable, which is the working definition of theatre. The cheapest real
fix in this whole review: show the recommendation distribution on the list
page. If it is 9/9 passing, you will know within a week instead of never.

## 2. The no-override rule is not a no-override rule; it is a paid, unrecorded, unlimited retry

Approve is withheld unless the company says Proceed. The only remaining door
is "Correct us", which re-runs the same model — and `_idea_block` hands that
model the previous recommendation *plus* the Founder's note under the header
"THE FOUNDER HAS TOLD YOU WHAT YOU GOT WRONG. This is the whole reason there
is another round. Take it seriously and **change your reading**."

That is an instruction to change the reading. There is no counter-instruction
anywhere saying "if the correction does not change the underlying facts, keep
your previous recommendation and say why." There is no cap on rounds. So a
determined Founder converges on Proceed in two or three corrections with near
certainty.

The result is worse than an explicit override, on three counts:

- **It is invisible in the record the Founder acts on.** The approved brief
  renders as "the company recommended Proceed." Nothing on the approved view
  says it took four rounds of pushing to get there. `founder_note` is stored
  per round, so it is reconstructible — but the artifact that goes downstream
  as the source of truth carries no marker of the pressure that produced it.
- **It costs money each attempt** (see §5).
- **It corrupts the evaluation instead of recording a disagreement.** An
  explicit "I am proceeding against the company's recommendation, and here is
  why" would be cheaper, more honest, and auditable — and it would preserve
  the "Reconsider" verdict as a permanent, visible fact about the idea. The
  current design deletes the company's real opinion by talking it out of it.

I am not asking for an approve-anyway button on the Founder's authority. I am
saying the current design already *is* one, with a $3 fee and no audit trail,
and the honest version is the cheaper one.

## 3. Failure modes that will reach the Founder as "it is broken and I cannot tell why"

**3a. A stuck `evaluating_since` bricks an idea permanently, with no UI escape
and no documented recovery.** This is the most likely next incident.

`ideas.evaluating_since` is set before a **daemon** thread starts. Nothing
anywhere clears a stale marker:

    $ grep -rn "evaluating_since" --include=*.py .
    ops/idea-desk/pages.py:496   (read)
    ops/idea-desk/server.py:425  (a comment)

There is no startup reconciliation in `server.py` (`_ensure_schema` only runs
`init`), and no staleness threshold — despite `evaluating_since` being a
timestamp, which makes the check a one-liner. So:

- Ctrl-C during an evaluation kills the daemon thread instantly; the `finally`
  block never runs. **This happens every single time**, and the README's "It
  takes a few minutes — you can close this and come back" actively invites it.
- If the `finally` block's own `_opsdb("idea-evaluation-end")` fails (SQLite
  busy past the 5s timeout, disk full), the exception is caught, printed to
  stderr the Founder is not reading, and the marker stays set.

Once set, `idea_page` short-circuits to `evaluating_page` before the action bar
is ever built. The Founder gets a page that refreshes itself every 6 seconds,
forever, with an empty step list (`PROGRESS` is in memory and died with the
process), and **no reachable Correct / Approve / Park / Drop**. Re-evaluating
is refused by `cmd_idea_evaluation_start` ("already running"). The only
recovery is `python3 ops/db/opsdb.py idea-evaluation-end --idea-id N`, which
appears in neither the README nor `doctor.py`. This is precisely the tracked-
database failure again in a new costume: a silent state that makes the tool
inert while every restart looks like it worked.

**3b. `/evaluate/<id>` and `/approve/<id>` render their panels without
checking whether the action is legal — and one of them destroys a record.**
`server.py` GET only validates `rest.isdigit()` and idea existence. On a
**parked** idea, `/evaluate/<id>` renders the full money-spending panel; the
button posts; `cmd_idea_evaluation_start` permits it (it refuses only
`approved`/`dropped`); `cmd_idea_round_add` then sets `status='evaluated'`
while leaving `close_reason` and `closed_at` populated. The idea is now
silently un-parked, the "You parked it" entry **disappears from "What is
stored"** (`_history` gates on status, not on `closed_at`), and `idea-reopen`
now refuses because the status is no longer parked. A Founder-visible record
was deleted by a route that should not have offered the button.
Similarly `/approve/<id>` renders the whole approve panel and green Approve
button on a `Reconsider` round; only the POST is refused, with a 409. The
"there is no approve-anyway path" promise is kept by `opsdb.py` — good — but
the UI offers the button anyway, which is how a Founder learns that the rules
here are discovered by hitting walls.

**3c. Any single failure discards the entire run and everything already paid
for.** Six sequential calls, no retry, no partial persistence. One timeout at
`IDEA_EVALUATION_TIMEOUT_S = 180`, one `$0.50` budget trip, one JSON parse
miss, and every completed perspective is thrown away. The error text says
"Trying again usually clears it" — i.e. pay again, from zero. 180s is also
optimistic for the synthesis call specifically: it must emit ten concise
answers, ten expanded sections and a six-field view as one JSON object, off a
prompt containing up to four 400-word perspectives. It is benchmarked against
`REVIEW_TIMEOUT_S = 120`, which is a far smaller output. The most expensive
call in the chain is the one most likely to blow both the timeout and the
`MAX_BUDGET_USD = "0.50"` cap, and it is the last one, after everything else
has been paid for.

**3d. `doctor.py` will start lying.** It hard-codes
`claude/orchestrator-chief-of-staff-f35grl` (lines 55–60) and prints `!!` plus
"check out this branch" instructions on any other branch. The moment that
branch merges, the diagnostic tool tells a correctly-configured Founder they
are wrong and instructs them to check out a stale ref. Worse, the one question
`doctor.py` exists to answer — "is the *running* server the code I just
pulled?" — it does not answer: it reads `BUILD` from the file **on disk**, then
separately probes the port and only checks that the response contains the
string "Idea Desk". Old code answers to that string too. `BUILD` is already
printed on startup and rendered in the footer; put it on `/login` or a
`/version` endpoint and compare, or the tool is guessing about the exact thing
it was written for.

## 4. Overengineering — what is not earning its keep

Most of it is. Three tables are three artifacts the Founder directed; six
subcommands are six verbs; the background thread is unavoidable for
minutes-long work. These are fine. Three things are not:

**4a. A second HTTP application.** DEC-016 explicitly considered and
**rejected** "a second, separate application (rejected — a second app means a
second login and a second path to the database, quietly undoing the security
posture)." Slice 1 built exactly that, on port 8421, and `server.py`'s
docstring cites **DEC-018** as the authority for it. DEC-018's own commit
message (`0c766ee`) says the opposite: *"It gets ported into the Control
Center as its own section... Not a second app and not a second auth path."*
No decision record reverses DEC-016. The result: a second session store, a
second idle/absolute timeout implementation, a second CSRF scheme, a second
cookie on the shared `127.0.0.1` cookie origin, and signing out of the
Control Center does not sign you out of the Idea Desk. `founder_auth` is
shared; none of the session machinery is. The Founder's "I want it separate"
is satisfied by a separate URL and separate chrome — it never required a
separate process, and being a separate process is what caused 4b.

**4b. The concurrency cap is now silently doubled.**
`MAX_CONCURRENT_INVOCATIONS = 3` is a module-level `BoundedSemaphore`, whose
stated purpose (agent_runtime.py ~line 255) is bounding "real resource/cost
exposure on a single local machine," affirmed by two prior reviews. It is
per-process. The Idea Desk is a second process with its own copy. A Founder
running both apps can now have six concurrent `claude` invocations on that
single local machine. Nobody noticed. This is the concrete cost of 4a.

**4c. The model is asked to emit HTML, so a bespoke sanitiser had to be
written to defend against it.** `SYNTH_CONTRACT` asks for `<b>`,
`<div class="sk">` and a two-column `<div class="two">` layout, and `pages.py`
answers with `safe_html()` — escape everything, selectively unescape an
allowlist by regex, then hand-roll `<div>` depth balancing. The sanitiser
itself looks correct as far as I can push it, and treating agent output as
untrusted is the right instinct. But the simpler thing that would have done is
obvious: **do not ask a language model for a two-column layout.** Plain
paragraphs, or one narrow markdown subset rendered by a real parser, removes
this file's most security-sensitive function entirely. You wrote a sanitiser
to protect yourself from a requirement you chose.

`doctor.py` I would keep, once 3d is fixed — but note what it is: a tool for
managing the symptoms of two self-inflicted bugs, both of which have since
been fixed at the root (`a2ed57d`, `3f50a3b`). Its remaining half-life is
short.

## 5. Cost — no ceiling, no estimate, no record, and no reason for any of that

Per evaluation: 1 roster + up to `MAX_PERSPECTIVES = 4` + 1 synthesis = **6
invocations, each capped at `MAX_BUDGET_USD = "0.50"` — a hard $3.00
worst case.** That number is trivially derivable and appears nowhere. The
disclosure panel says "There is no cost estimate available before the fact —
the company cannot tell you in advance what a given idea will cost to read."
The per-idea *ceiling* is not an estimate and the company absolutely can tell
them: `agent_runtime.py` lines 205–230 already carry exactly this disclosure
convention for meetings ("= 20 real, MAX_BUDGET_USD-capped `claude`
invocations per meeting, worst case — roughly $10.00"), written at this
reviewer's own prior insistence. Slice 2 did not follow the convention the
file it imports from established.

Worse, **nothing records what was actually spent.** `RuntimeResult.cost_usd`
is returned by `invoke_agent` and dropped on the floor. `evaluator.py` never
writes an `agent_runs` row — grep confirms it touches nothing but
`agent_runtime.invoke_agent`. `idea_rounds.agent_run_id` exists, is documented
as "NULL for a seeded round," and is **never passed by `_opsdb(...)` in
`run_evaluation`** — so it is NULL for every real round too. Consequences:

- The only action in the entire system that spends the Founder's money is the
  only one with no spend record anywhere.
- `IDEA_EVALUATION_ACTIVITY_LABEL` and `IDEA_EVALUATION_ACTIVITY_LIKE` are
  defined in `agent_runtime.py` and **used by nothing**. They exist for the
  Control Center's orphan reconciliation, which will never see an Idea Desk
  run, because no row is ever written.
- A real round and a hand-seeded round are indistinguishable in the database,
  because the one column that would tell them apart is NULL in both.

There is no per-idea round cap, so per-idea spend is unbounded by design (see
§2). There should be a ceiling: a round cap, or at minimum a "this idea has
had 4 rounds and cost roughly $X" line above the fifth Correct-us button.

## 6. Honesty of the output is enforced by prompt only; nothing would catch a fabrication

Asked directly: **nothing in the code would catch an invented competitor.**
`_validate` checks that ten answer keys exist, that six view fields exist,
that `rec` is one of four strings and that `opp` is one of four strings. It
does not look at a single word of content.

Three specific gaps:

**6a. The "research not performed" disclosure is required by prompt and by
nothing else.** DEC-015's addendum requires every outside-world claim to be
labelled **VERIFIED/CURRENT**, **COMPANY INFERENCE** or **UNKNOWN**. The
prompts never ask for those labels — `COMMON_RULES` asks for "company
recollection" phrasing instead. Meanwhile `pages.py` line 223 carries
`_SPAN_CLASSES = "lab unk|lab|na"` in the sanitiser allowlist and the CSS
supports rendering them. **The label mechanism is built into the renderer and
requested by no prompt anywhere.** One prompt tweak away from a confident
competitor list is exactly right — it is currently zero mechanisms away.

The fix is cheap and does not depend on model compliance at all: the server
*knows* no agent can browse. Have the code append a fixed, non-model-generated
sentence to Q4 — "No external research was performed; no agent in this company
can browse the web" — and, at Light depth, refuse to save a round whose Q4
contains a competitor-shaped claim without it. A truth the code knows should
not be delegated to the thing most likely to forget it.

**6b. `_select_roster` does not receive `COMMON_RULES`.** It is the only
prompt that omits them, and its `depth_reason` and per-role "why" strings are
rendered to the Founder verbatim in the roster block. Small, and free to fix.

**6c. The Founder's first and only worked example is a fabricated agent
deliberation, unlabelled.** `seed_founder_idea.py` is honest in its own
docstring ("Every word of both rounds was written by the company during this
project"). The UI is not. The Founder opens the Idea Desk and sees "Who
weighed in, and why: Product — ... · Design — ... · Red Team — ...", a Depth
label, and two rounds of company reasoning. **Design and Red Team never ran on
that idea.** No agent invocation occurred; `agent_run_id` is NULL, and per §5
that tells you nothing because it is NULL for real rounds too. A product whose
entire value proposition is "this is what the company actually said" ships
with a hand-written record of a deliberation that did not happen, presented
identically to one that did. One line in the roster block — "seeded from the
project record; no agent run" — fixes it, and it must be there before the
Founder sees this again.

---

## What would move this to PASS

Blocking:

1. Pin `red-team` onto the roster the way `product` is pinned (§1a).
2. Stale-`evaluating_since` recovery: a staleness threshold, startup
   reconciliation, and a Founder-visible "this evaluation stopped; try again"
   escape on the evaluating page (§3a).
3. Legality checks on the GET routes that render `evaluate_panel` and
   `approve_panel`; stop `idea-round-add` from silently erasing a park (§3b).
4. Label seeded rounds in the UI, and populate `agent_run_id` for real ones
   (§5, §6c).
5. Code-side "no external research was performed" on Q4, not prompt-side
   (§6a).
6. Disclose the $3.00 worst case per evaluation, and record `cost_usd`
   somewhere the Founder can see it (§5).
7. A written decision reversing DEC-016's "not a second app," or fold the
   Idea Desk back into the Control Center as the section DEC-016 and DEC-018
   both specify. Either is acceptable; citing a decision that says the
   opposite of what was built is not (§4a).

Also required before this is called a working record: **DEC-018 does not exist
in `ops/DECISIONS.md`.** It was written only into `ops/db/operations.sqlite3`
(`0c766ee` changes that file and nothing else), which DEC-019 then removed
from git. Four source files cite DEC-018 as their governing authority and no
clone of this repository can read it. Write it into `ops/DECISIONS.md`, and
treat this as the first concrete instance of the audit DEC-019 admits it owes
("this decision does not audit what currently qualifies").

Non-blocking but should be scheduled: the counter-instruction on Correct-us
(§2), the recommendation distribution on the list page (§1d), partial
persistence or retry so one timeout does not discard a paid run (§3c), the
`doctor.py` branch hard-code and the running-vs-on-disk build check (§3d), and
retiring the model-generated HTML in favour of something that does not need a
bespoke sanitiser (§4c).

The Founder should not read this as "the Idea Desk is bad." The storage model
is the best-designed thing in this repository. But it was built through no
gates, and the two things it was built to guarantee — that the company can
refuse, and that it never invents — are the two things nothing in the code
currently enforces.
