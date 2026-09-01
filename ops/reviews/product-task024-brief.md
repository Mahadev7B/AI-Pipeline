# Product Brief — TASK-024: Raw Idea → Deciphered Brief → Founder Approval → Work

**Revision 3 — the DEC-014 revision. Clean rewrite.** Product agent · 2026-09-01 ·
for Design (revise the mockup), then CTO.

**Supersedes a damaged intermediate state.** This file's prior contents were a
partial rewrite — an earlier agent was stopped mid-write — leaving it part
Revision 1 (pre-DEC-013) and part Revision 2 (DEC-013), internally inconsistent and
not a specification. It was rewritten, not patched; §1 preserves what remains true.
The damaged text survives in git history.

**Authoritative input:** `ops/reviews/founder-directive-task024-deciphering.md`
(verbatim). Where this brief and that directive differ, **the directive governs.**
DEC-014 records it; DEC-013 is what it extends. This brief does not restate the
directive — it settles the five things the directive leaves open.

---

## 1. Carried forward from Revision 1 (still binding)

**Intake fields.** `title` **required**. `business_goal` **required** — this *is* the
idea, free text, paragraph-shaped. `priority` **optional**, from a fixed
`high`/`medium`/`low` allowlist, rejected rather than coerced if it is anything else.
`user_story`, `requirements`, `acceptance_criteria` are **not asked for** — requiring
them asks a non-technical Founder to do Product's and QA's jobs at the moment they
know least. Two required fields, one optional selector.

**Submitting is not starting.** Save writes one `tasks` row at `BACKLOG` plus one
history row, dispatches nothing, spends nothing. The directive's `[ Save Idea ]`
confirms this.

**Security weight.** This remains the first write route that *creates* work rather
than acting on an existing row: unbounded object creation with no rate limit anywhere
in the product; Founder free text becoming model prompt input; a new stored-text
render surface (`business_goal` renders on no Founder-facing page today) that must go
through `layout.py`'s `e()` with no Markdown or rich-text path; and per-field caps,
because `MAX_BODY_BYTES` (64 KiB) is a transport bound, not a field bound.

**Still-open CTO items from Revision 1:** `is_stuck()` and `BACKLOG` (TASK-025 sits in
`BACKLOG` today and crosses `STUCK_THRESHOLD_DAYS = 3` on 2026-09-04 — the docstring's
"currently latent" excuse has expired); `project_id` on intake; `cmd_task_create()`'s
refactor shape; per-field caps (Design recommends 160 / 4,000 / allowlist).

**Design's surviving work.** The Save half of `Main.dc.html` stands. So does
`StartFlow.dc.html`'s **arm-then-confirm** treatment of a consequential action —
outlined control arms, filled control commits, on a screen whose body is the
consequence; control removed once fired; "started" never rendered unless a transition
was written. That now applies to **Approve Brief & Start Work** (§5), not a generic
Start. **The label `Start work on TASK-025…` is now wrong** — the first click starts
understanding, not building.

---

## 2. Chief of Staff's selection judgement

The directive: pick only perspectives that materially improve understanding, and
**"Do NOT automatically use every agent."** Nothing reviews that judgement. This
makes it reviewable.

### 2.1 What makes a perspective material — the only-you test

> A perspective is material for **this** idea if that role can name a specific
> question about **this** idea that would change the recommended direction, the scope,
> or the assumption list — **and no other role already on the roster would raise it.**

Two failure checks on that sentence:

- **Generic-sentence check.** If it would be equally true pasted onto an arbitrary
  other idea, the role is not material — it is being invited because it exists.
  ("CTO should check feasibility" fails. "This asks for real-time sync between two
  machines that have never talked, which changes what the smallest useful version is"
  passes.)
- **Duplicate check.** If a role already on the roster would have said the same thing,
  the second role adds cost, not understanding.

**Product is always on the roster** — the directive's word, not an inference.

**Red Team is a rebuttable presumption, not an automatic.** Its questions — *what
might we be misunderstanding, why might this fail, is there a simpler alternative* —
are the ones this stage exists to force, so **omitting it requires a stated reason**
while including it does not. That is deliberately different from automatic, given the
directive's blanket instruction.

**CEO, CTO, Design, Security/Privacy, Financial** join only on a passing only-you
sentence, and the directive's own narrowings stand verbatim: Design when UX is
important; Security/Privacy only when genuinely relevant; Financial only when cost,
pricing, budget or viability *materially affects the idea* — not merely "this will
cost something to build," which is true of everything.

### 2.2 The test applied afterwards — the contribution test

Selection is a judgement call and cannot be pre-verified. It can be audited:

> **Every selected role must have produced at least one thing that survived into the
> Founder-facing synthesis** — an assumption, alternative, risk or question traceable
> to it. A role that contributed nothing was, in hindsight, not material.

One such role in one round is noise; a role that repeatedly contributes nothing is the
observable signal that selection is bad — observable without anyone second-guessing
the judgement in the abstract.

**Requirement:** the selection is recorded as a one-line reason per role, persisted,
and shown to the Founder as the "which perspectives participated" element. Not raw
agent output — the roster and why. Nothing captures this today (§6.2).

### 2.3 When Chief of Staff picks nobody beyond Product

**Legitimate, expected, and allowed** — a clear idea does not need six leaders. Never
silent, though:

1. The synthesis says so in plain language, with the reason — *"clear enough that I
   handled it with Product alone."*
2. The screen shows a roster of one, not a blank. A blank reads as breakage.
3. The round still produces the full six-section synthesis, the full interpreted
   brief, and the same approval gate. Only other agents' opinions are skipped.
4. It costs materially less and the Founder should see that.

**Self-consistency check:** a Product-only round that comes back leaning on a long
assumption list, or asking questions, is *prima facie* evidence the roster was too
narrow. Not a failure — that is what **Brainstorm More** is for, and the synthesis
should say so rather than making the Founder work it out.

---

## 3. "Only questions that can materially change direction"

**An agent that returns eight questions has failed as completely as one that asks
none** — eight questions is the company handing its job back to the Founder.

### 3.1 The divergence test — primary filter

> **A question is material if and only if two different honest answers to it would
> produce two different briefs.**

Per question: write the two most likely answers; ask whether the **recommended
direction**, the **scope**, or the **success criteria** would differ. If no — delete
it, take the likelier answer, state it as a visible assumption. If yes — keep it and
state in one line *what changes*. **A material question can always explain its own
stakes; one that cannot is decoration.**

**Reviewer's one-liner:** *if the brief would have been identical whichever way the
Founder answered, the question should not have been asked.*

### 3.2 Four supporting filters

- **Assumption-first.** Anything statable as an explicit, visible, correctable
  assumption **must** be, rather than asked — the directive's *"do not ask questions
  agents can reasonably decide themselves"*, made operational.
- **Founder-can-answer-it.** "Should state live server-side or client-side?" is a CTO
  question wearing a question mark. Material questions are about **what they want and
  why**, never **how to build it**.
- **Already-answered.** If the raw idea, `ops/DECISIONS.md`, or the product as it
  stands already answers it, it is not a question — it is the stage not having read.
- **Internal-disagreement (new under DEC-014).** An internal disagreement about **what
  the Founder wants** is material by construction — the company genuinely cannot
  resolve it without them. A disagreement about **how to build it** is not; the agents
  decide and say so in the assumptions. This is the most reliable question-generator
  the multi-agent stage produces and CoS should reach for it first.

### 3.3 Cap: three, and it is a cap

If more than three survive, rank by how much the brief changes, ask the top three, and
the rest become stated assumptions. Three is not invented here — it is the limit
already documented by `prompt-master` (*"Do not ask more than 3 clarifying
questions"*), so the company stays consistent with a bar it already wrote down.

### 3.4 Zero is a passing score

A round with no questions, a clear recommendation and a good assumption list is a
**success**. The stage must never manufacture a question to look thorough. QA treats a
zero-question brief with good assumptions as a **pass**, and a three-question brief
where any question fails §3.1 as a **fail**.

---

## 4. The three artifacts

*Never overwrite one with another*; the company must always be able to answer **what
did the Founder originally say / what did the AI company interpret / what did the
Founder actually approve.** `tasks` has flat columns and no versioning, so today it
cannot answer those. Requirements below; **schema is CTO's.**

### 4.1 The non-negotiable

> **The Founder must always be able to open the product and see the words they
> originally typed, next to what the company decided those words meant — forever, on
> the same screen, not in an archive.**

Preserving the Founder's raw words unaltered is the principle this feature encodes.
Any design that satisfies everything else and fails this, fails.

### 4.2 The three

| Artifact | Author | Mutable? | Role |
|---|---|---|---|
| **Raw idea** | Founder, at intake | **Never.** Write-once. | What was actually asked for. |
| **Interpreted brief** | The deciphering round, synthesised by CoS | Append-only — a new round makes a **new version**, never an edit | What the company thinks the Founder meant, at round N. |
| **Approved brief** | Founder, by approving a specific version | Terminal for that task | **The authoritative input to every downstream agent.** |

`business_goal` is written once, at intake, by the Founder, and **never overwritten by
any agent, ever.** It *is* the raw-idea artifact. Nothing stops that today —
`task-update` exists and Product is its natural caller. Under DEC-014 that is a
defect, not a convenience.

### 4.3 Requirements on persistence

1. **Distinguishable by kind**, not by convention or by which column someone
   remembers. "Which of these is the raw idea?" is answerable from the data.
2. **Every round retained.** Brainstorm More / Refine make this inherently
   multi-round; a design where round 3 overwrites round 2 loses the exact thing the
   directive asked to preserve. This rules out flat `interpreted_brief` /
   `approved_brief` columns — a flat column holds only the latest.
3. **The approved brief is identifiable as a specific version** — ideally a pointer to
   the version approved, not a re-typed copy. A copy can drift; a pointer cannot. If a
   copy is taken it must be provably identical at the moment of approval.
4. **Downstream agents read the approved brief.** Not the raw idea, not the latest
   interpretation. Concrete consequence: `review_transcripts.py` (~lines 203–206,
   261–264) and `launch_developer_session.py` feed **`business_goal`** — the raw idea —
   into agent transcripts today. For a task with an approved brief that is now the
   **wrong field**. **This is the single most likely place for DEC-014 to be quietly
   violated**, because those call sites work today and nothing about them looks wrong.
5. **Nothing is deleted.** Superseded is not removed.

**Requirements-level preference (CTO decides the shape):** a versioned, append-only
brief record — `task_id`, `version`, `kind`, `content`, `author`, `created_at`, link
to the round that decided it. It matches a pattern this project already understands:
`task_status_history` is exactly "an append-only record of how this changed over
time." Reusing `requirements`/`acceptance_criteria` is rejected — those are Product's
normal downstream outputs; overloading them conflates "what we think you meant" with
"the spec we built from it."

### 4.4 A fourth thing, nearly free

The internal debate. "Not dumped on the Founder" is not "thrown away." The existing
meeting machinery already persists every position and synthesis as a `meetings` row
plus `messages` (§6.2). **Requirement:** the round links to that record; the
Founder-facing screen shows only the roster and the synthesis; the full debate is one
click away. Plus §2.2's selection reasons, which nothing captures today.

---

## 5. The review gate: four actions, and what each costs

| Action | What it means | New version? | Model spend? |
|---|---|---|---|
| **Brainstorm More** | *Diverge.* "More, or different, options." New round instructed to widen; CoS may pick a **broader or different** roster. | Yes → vN+1 | **Yes — a full round, several agents** |
| **Refine** | *Converge.* "Right direction, go deeper," or "I meant X, not Y." Founder supplies words; new round instructed to narrow, roster same or narrower. | Yes → vN+1 | **Yes — a full round** |
| **Edit** | *The Founder writes.* Founder edits the interpreted brief's text directly. | Yes → vN+1, authored by **the Founder** | **No — no model invocation at all** |
| **Approve Brief** | Accepts a version as the approved brief. **Starts no work.** | No | **No** |
| **Approve Brief & Start Work** | Approves *and* dispatches. The action that begins execution. | No | **Yes — downstream, the expensive one** |

- **Edit is why the directive lists four buttons, not three.** Refine asks the company
  to try again; Edit is the Founder saying it themselves. It must cost nothing — that
  is most of its value — and its version must be **attributed to the Founder**, so the
  record keeps "what the company interpreted" distinct from "what the Founder
  changed." Attributing an edited version to the company would corrupt the exact
  question §4 exists to answer.
- **Edit never reaches the raw idea.** The Founder corrects the *interpretation*,
  never their own original words. That immutability is what makes the side-by-side
  comparison worth anything.
- **Brainstorm More and Refine spend again, and the control says so on itself** — not
  in a paragraph above it. A Founder who clicked four times has paid four times.
  Rounds are numbered and visible ("Round 3"), and from round 4 the product should say
  something honest: *"You've refined this three times; the next round costs again — it
  may be cheaper to approve and correct downstream."* **Not a hard block.** It is the
  Founder's money and the Founder's idea.
- **Leaving the gate is free and lossless.** No new Park button required; the
  requirement is that navigating away decides nothing, spends nothing, loses no round,
  and leaves the idea findable. Without that the gate is a trap whose only exits are
  "approve something I disagree with" or "keep paying."

**Approve Brief alone must be a complete, useful outcome** — brief approved, nothing
dispatched, nothing spent, Start Work still available later from the task's own page.
If approving always started work the directive would not have named two actions.

Design's arm-then-confirm pattern applies to **Approve Brief & Start Work** only.
Before that click the screen states, in the directive's terms: agents will begin
working; real AI cost may be incurred; the approved brief becomes the authoritative
project instruction. Plus two things the product knows and the Founder does not:
**there is no stop button**, and **the approved brief — never the raw idea — is what
those agents receive.**

---

## 6. Approval machinery, and reuse vs new

### 6.1 Approvals: reuse, unchanged

**Reuse the existing `approvals` table and `/api/approvals/<id>/decide` as-is, with
one approval row per interpretation round.** No new approval machinery, no new
decision states, no new auth. Checked against the real schema and function:

- The columns already describe an interpretation — `request`, `why`,
  `recommendation`, `alternatives_considered`, `expected_cost`, `risks`,
  `consequence_if_not_approved`.
- `tasks.status` already has **`FOUNDER_APPROVAL`**, and `task_is_stuck()` already
  **excludes** it — an idea awaiting review is not flagged stuck. Correct behaviour,
  free. (`BACKLOG` is *not* excluded; still the open defect from §1.)
- `decide_approval()` is already atomic and double-submit-safe: its conditional
  `UPDATE ... WHERE decision IN (...)` makes a second click affect **zero rows**
  rather than overwrite — exactly what you want on a gate where each decision leads to
  spending.

**The one mismatch.** `decide_approval()` is deliberately single-shot — `approve`/
`reject` terminal, `discuss → discuss` intentionally absent. The directive needs a
gate the Founder can send back repeatedly. Resolved by not asking that function to do
what it was built to refuse: round N produces version vN **and one new `approvals`
row**, decided exactly once; a send-back closes it forever and round N+1 creates a new
one. Zero changes to the function, the CHECK constraint, the route or the auth — and
`approvals` becomes the round-by-round record for free.

**The one genuine gap.** There is nowhere to put the Founder's words.
`decide_approval(conn, approval_id, decision)` takes a decision and nothing else, and
the route accepts nothing else — but Brainstorm More and Refine are worthless without
them; a send-back with no explanation produces round N+1 identical to round N at full
cost. **Requirement (mechanism is CTO's):** the Founder's text is captured at the
moment of decision, persisted verbatim, attributed to the Founder, and supplied to the
next round — **without** creating a second, unreviewed way to decide an approval.

### 6.2 The deciphering engine already exists

Stated plainly, because specifying a parallel system would be the wrong call:
**`chief_of_staff.py` + `meeting_orchestrator.py` already implement most of the
directive.** What the directive calls deciphering is mechanically the
consult-then-narrate flow that shipped in Phase 3A.

**Reusable essentially as-is:**

- **`_parse_consult()`** — CoS names roles on a `CONSULT:` line; deterministic Python
  matches them against a fixed allowlist and drops anything else. That **is** §2's
  per-idea selection mechanism. No new selection mechanism is needed.
- **`run_consult_meeting()` → `_gather_and_synthesize()`** — real `meetings` row,
  positions gathered concurrently under the global `MAX_CONCURRENT_INVOCATIONS`
  semaphore, each persisted, then synthesised. That **is** "agents debate internally,"
  and it already persists the debate where §4.4 wants it.
- **`_build_narration_transcript()` + the second CoS invocation** — already reads the
  real positions and synthesis and returns **one** Founder-addressed answer in a fixed
  shape (WHAT HAPPENED / WHY IT MATTERS / MY RECOMMENDATION / WHAT I NEED FROM YOU).
  That **is** "decipher broadly, communicate narrowly." The directive's six sections
  are a **prompt change, not a new system.** The first reply, with its raw `CONSULT:`
  line, is already discarded and never shown to the Founder.
- **Bounds already exist:** `MAX_MEETING_PARTICIPANTS = 6`, `cap_participants()`,
  `MAX_CONCURRENT_INVOCATIONS`, `MAX_BUDGET_USD = "0.50"` per invocation.

**Genuinely new — a short list:**

1. **A task-scoped caller.** The only entry today is a Founder chat message on the
   `agent-orchestrator-company` thread. Deciphering must be triggered *by a task* with
   its output attached *to that task*. A new caller, not a new engine.
2. **The roster rule, which conflicts with the code in two places.**
   `run_consult_meeting()` **always adds CEO** and never guarantees **Product**. The
   directive requires Product always and CEO only when materially strategic. Fixable
   by passing an explicit roster, but "CEO is always a participant — never optional" is
   a stated rule in two functions, so this is **CTO's decision, not mine to change
   quietly.**
3. **`design` is not in `MEETING_PARTICIPANT_ALLOWLIST`** — the live tuple is
   `("ceo","product","cto","financial","marketing","qa","security","red-team")`, and
   the directive names Design when UX matters. Adding it is a security-relevant
   allowlist change Security has previously reviewed. **Flagged, not decided.**
4. **Selection reasons are captured nowhere.** `meetings.participating_agents` records
   *who*, never *why*. §2.2's audit needs the why. Small, new, and the thing that makes
   CoS's judgement reviewable at all.
5. **The persisted brief (§4), the approval gate (§6.1), and the Founder-facing
   screens.** Genuinely new work.

So nobody gets it backwards: in the existing flow **CEO synthesises the meeting and
CoS narrates to the Founder.** Under the directive CoS owns the Founder-facing answer,
so CEO's synthesis is an **internal** artifact feeding CoS's narration and must never
be shown to the Founder as the answer. The code already works this way; the
requirement is that it stays that way.

### 6.3 What a round can cost — an honest ceiling

Design's finding stands: 0 of 13 `agent_runs` rows carry `cost_usd`, so any *estimate*
would be fabricated. The *maximum* is knowable. Every invocation runs with
`--max-budget-usd 0.50`, and one round on the existing path is at most 1 CoS selection
turn + up to 6 participant positions + 1 CEO synthesis + 1 CoS narration =
**≤ 9 invocations ≤ $4.50 per round.** Honest, useful, verifiable — and it turns an
unbounded-feeling spend into a bounded one, the most reassuring true thing available on
that screen. **Two conditions, or it must not be shown:** recompute it from the
mechanism CTO actually builds (never copy the figure from this brief), and it is a
**per-round** ceiling, so the Founder must see how many rounds they have paid for.

---

## 7. Two things flagged honestly, not designed around

### 7.1 The brainstorming skill — I invoked it; here is what happened

**It fires in a session like this one.** Invoking `prompt-master` **succeeded**,
loading from
`/root/.claude/skills/synced/b656f309-…_19c0a3da-…/prompt-master/SKILL.md`. So the
concern is half wrong and precision matters about which half: the repo genuinely ships
**no `.claude/skills/` directory at all** — correct — but the skill is not
repo-provided. It is **user-account-synced**: it travels with the Founder's Claude
account, not the codebase. A fresh clone, a different account, or CI has no
`prompt-master`. It is an **undeclared external dependency** of a documented role
behaviour.

**It cannot fire on the path that actually runs agents.** `agent_runtime.py`,
`_run_claude()`, line 304: `"--tools", ""`. Every agent dispatched through the Control
Center runtime launches with **zero built-in tools** — no `Skill` tool. **No skill can
be invoked by a dispatched agent**, whatever its definition grants. Eight agent
definitions carry a `Skill` grant (`code-review`, `cto`, `design`, `developer`,
`devops`, `product`, `qa`, `security` — `.claude/agents/*.md` line 4). On the runtime
path **all eight are inert.** That is a third "documented but inert" mechanism, after
TASK-017's hook that never fired and the defence-in-depth layer that could not fire
inside the sandbox. It was already here, and it is found before build rather than in
QA. **`--tools ""` is a deliberate security control and I am not recommending it be
relaxed** (§8.7).

**Even where it fires, it is the wrong tool — and there is no brainstorming skill at
all.** `prompt-master` is a prompt engineer: *"output a single production-ready prompt
optimized for that specific tool,"* output *"a single copyable prompt block."* The
repo's own registry already records it verbatim
(`ops/skills/product/prompt-master.md`): *"Produces a prompt for someone/something
else to run — it does not execute the task itself."* The registry was honest;
`.claude/agents/product.md` line 10 overstated it. And **no brainstorming skill exists
anywhere reachable** — not in the synced set, not among `ops/skills/`'s twelve
entries, not in the session roster.

**Restated so it can be built:** the deciphering stage has **no skill dependency.**
Its divergent thinking is a **behavioural** requirement met by the instruction
transcript and by the multi-agent roster — which is what DEC-014 replaced the
single-agent reading with — and enforced by what QA checks it produced. That mechanism
demonstrably works in this codebase; a skill demonstrably does not. **This is a
substantive amendment to the directive's wording and I flag it rather than quietly
satisfying it:** the intent (real divergent thinking before requirements lock) is fully
preserved and fully buildable; only the named mechanism is unavailable. It also
**answers** TASK-025's verification question rather than deferring it.

### 7.2 Money is spent before anything is built

The deciphering stage spends real model money across several agents **before any
building begins**, on a screen that already has to disclose that no cost estimate is
available and there is no stop button. That is not an argument against the stage — a
Start button that reliably begins building the wrong thing is worse — but it fixes what
the Founder must be told **before the first click**: (1) this starts *understanding*,
not building — no design, architecture or code results from it; (2) it spends real
money across **several agents**, not one; (3) there is no per-round estimate — 0 of 13
recorded runs carry a cost figure; (4) there **is** an enforced ceiling (§6.3);
(5) there is **no stop button** — a dispatched round runs to completion; (6) this is
the first spend of possibly several — **the Founder learns that before round 1**, not
by being charged.

---

## 8. Scope exclusions

Revision 1's exclusions **all stand**: no editing a task from the UI, no delete or
archive, no CRUD surface, no attachments or upload, no multi-project, no auto-start on
submit, no retro-fixing existing rows' `priority`/`project_id`, no rendering of
`user_story`/`requirements`/`acceptance_criteria` on Task Detail. Design's Concept B
receipt and Concept C inline capture remain **documented and rejected**. Added:

1. **No unattended automatic pipeline execution.** The directive is explicit that it
   does **not** authorize it and the Founder remains the authority who deliberately
   starts work. This exclusion governs all the others.
2. **No cascade on Start Work.** Starting dispatches the pipeline the Founder
   approved; it is not a licence for the automation poller to acquire new agent types.
   DEC-012's freeze is untouched.
3. **No auto-approval, in any form** — never by timeout, never because nobody looked
   for N days. **Silence is not consent.** The most dangerous available shortcut,
   closed explicitly.
4. **No editing the raw idea**, by anyone, ever.
5. **The deciphering stage is not Design** (no screens, layout, wireframes), **not
   architecture** (no schema, routes or technology choice — if an interpreted brief
   names a technology, QA fails it), **not a feasibility study**, **not an estimate**
   (no dollars, hours or t-shirt sizes — this company has zero cost data and a
   documented record of estimates wrong by an order of magnitude), and **not the
   decision-maker** (it recommends one direction; the Founder decides by approving).
6. **No skill dependency** (§7.1) — nothing here may require `prompt-master`, a
   brainstorming skill, or any skill to function.
7. **No relaxing `--tools ""`** to make a skill reachable. That is a security control;
   trading it for convenience needs Security and Red Team, not a Product brief.
8. **No hard cap on rounds** — numbered, visible and warned (§5), not blocked.
9. **No retro-interpretation** of the 24 existing tasks.
10. **No multi-Founder review, comments, threads or @-mentions.** The gate is a
    decision, not a discussion forum.
11. **No showing raw agent reports to the Founder.** The debate is preserved and
    reachable (§4.4); it is not the Founder-facing answer.

---

## 9. Acceptance criteria

AC-1 – AC-11 from Revision 1 stand (intake creates one `BACKLOG` row plus one history
row through `opsdb.py`; the task appears on Active Work and Task Detail; the Founder's
text reads back; empty and over-cap submissions are rejected with the typed text
preserved; markup is stored verbatim and rendered escaped; the route requires session
+ CSRF; nothing else changes; a parked idea is not presented as a failure). Added:

**Deciphering**

12. A deciphering round runs **only** deciphering. QA verifies **no Design, CTO, Red
    Team or Developer implementation invocation** occurs — participating in the round
    is not dispatch.
13. The Founder-facing output is **one** synthesis with all six named sections.
    Separate per-agent reports shown to the Founder are a **FAIL**.
14. The roster is visible with a one-line reason per selected role, and the full
    internal debate is reachable in at most one click.
15. **Every selected role's contribution is traceable** into the synthesis — QA names
    the assumption, alternative, risk or question each produced (§2.2).
16. A **Product-only** round passes provided it says so and gives the reason (§2.3). A
    round selecting every available agent is a **FAIL** absent a per-role only-you
    reason.
17. At most **3** clarifying questions; zero is a pass. Each question present passes
    §3.1 — QA applies it by writing two plausible answers and checking whether the
    brief would differ.
18. The interpreted brief is **approvable with no questions answered** — QA approves
    one without answering anything and gets a brief usable downstream.
19. The interpreted brief contains **no** screens, schema, routes, technology names,
    dollar figures or time estimates (§8.5).

**The three artifacts**

20. After any number of rounds the Founder sees the **exact original text** they typed,
    unmodified, alongside the current interpretation — verified byte-for-byte against
    what was submitted.
21. `business_goal` is **never** modified after intake — verified across a full
    multi-round cycle including an **Edit**.
22. Round 1 is still readable after round 3 exists.
23. **The raw idea is never sent downstream as the implementation prompt.** QA
    inspects a real downstream transcript for a task with an approved brief and
    confirms it is built from the **approved brief** — specifically that
    `review_transcripts.py` and `launch_developer_session.py` no longer feed
    `business_goal` for such a task (§4.3.4).
24. A Founder **Edit** produces a new version attributed to the **Founder** and
    triggers **no** model invocation (zero new `agent_runs` rows).

**The gate**

25. An interpretation is **never** approved without an explicit Founder action — no
    timeout, no default, no auto-approve path exists.
26. A send-back carrying the Founder's correction text produces a new round that
    **demonstrably reflects that text**, and the prior round is retained.
27. Deciding the same approval row twice affects **zero rows** the second time and
    triggers **no** second paid round.
28. **Approve Brief** approves and dispatches nothing — QA verifies zero dispatch and
    that Start Work remains available afterwards.
29. **Approve Brief & Start Work** does not render "started" unless a status transition
    was actually written; a failed dispatch leaves the task where it was and says so.
30. §7.2's disclosures are present before the first click, and the round-cost warning
    is **on** the Brainstorm More / Refine controls, not only in surrounding prose.

---

## 10. Open questions for CTO

1. **`is_stuck()` and `BACKLOG`** — no longer latent (§1). Must not ship undecided.
2. **`project_id` on intake** — `1` or `NULL`.
3. **`cmd_task_create()`'s refactor shape.**
4. **Per-field caps** — Design recommends 160 / 4,000 / allowlist.
5. **Brief-storage shape** — §4.3's requirements are not negotiable; the shape is
   CTO's.
6. **Where the Founder's correction text is captured** (§6.1) — the one real gap in
   reusing the approvals machinery.
7. **Which decision value means "send it back"** — `discuss` or `reject`; both work
   under one-row-per-round, `discuss` reads more accurately.
8. **The roster rule vs. `run_consult_meeting()`'s CEO-always rule** (§6.2.2).
9. **Whether `design` joins `MEETING_PARTICIPANT_ALLOWLIST`** (§6.2.3) — needs
   Security's view, not only CTO's.
10. **Switching downstream transcripts to the approved brief** (§4.3.4) — the most
    likely place for DEC-014 to be silently violated.
11. **The real per-round cost ceiling** (§6.3) — recomputed from the built mechanism,
    or not shown.

**Flagged, outside this milestone, needing an owner:** eight agents carry an inert
`Skill` grant on the runtime path (§7.1) — either the grants are meaningless there and
the definitions should say so, or the runtime is stricter than intended;
`.claude/agents/product.md` line 10 is wrong on three counts; and `ops/db/ops.db` is an
empty stray file (0 tables) beside the real `ops/db/operations.sqlite3` — harmless
today, an obvious footgun for whoever opens the plausibly-named one.

---

## 11. Handover

The directive's 15 mockup elements and the walkable journey are **Design's**, and this
brief deliberately does not draw them. Two things handed over rather than decided: the
**wording** of every disclosure above (the requirement is what must be true, not the
sentence), and **how** the raw idea sits beside the interpretation on screen (the
requirement is only that it always does). One thing not up for relitigation: per the
directive, Design is **not** complete because individual screens look attractive.
