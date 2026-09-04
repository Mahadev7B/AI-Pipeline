# Product Brief — TASK-024: Raw Idea → Interpreted & Evaluated Brief → Founder Approval → Work

**Revision 4 — the DEC-015 revision.** Product · 2026-09-01 · for Design, then CTO.

**Authoritative input:** `ops/reviews/founder-directive-task024-deciphering-v2.md`
(verbatim, **now complete — Parts 1, 2 and 3**). Where this brief differs from it, **the
file governs.**

**Changes from Revision 3 (DEC-014), which this supersedes:** brainstorming removed, not
renamed — no feature, no skill dependency, no *Brainstorm More*; the gate becomes
**Edit/Correct · Reconsider · Approve Brief** plus the separate **Approve Brief & Start
Work**; objective is **correct understanding, not endless ideation**. Evaluation is added,
with Part 2's **fifteen-section output contract** closing in a fixed-shape **Company View**
(§3). Competitor claims are labelled **VERIFIED / CURRENT · COMPANY INFERENCE · UNKNOWN**,
reconciled in §4 against the fact that **no agent here can research anything today**. Depth
scales with the idea (§2.3). Ten questions are the concise layer, the fifteen sections sit
behind them (§5). Downstream source of truth is a **release blocker with a named test**
(§7). Carried forward: both materiality tests, the three artifacts, the machinery-reuse
assessment, the `--tools ""` finding, most acceptance criteria. §12 lists what was cut.

---

## 1. Carried forward and still binding

**Intake.** `title` **required**; `business_goal` **required** — this *is* the raw idea,
free text; `priority` **optional**, fixed `high`/`medium`/`low` allowlist, rejected not
coerced. `user_story`, `requirements`, `acceptance_criteria` are **not asked for** —
requiring them asks a non-technical Founder to do Product's and QA's jobs at the moment they
know least. **The Founder never has to write a PRD.**

**Submitting is not starting.** Save writes one `tasks` row at `BACKLOG` plus one history
row; dispatches nothing, spends nothing. **Never auto-start from a saved raw idea.**

**Security weight.** The first write route that *creates* work rather than acting on an
existing row: unbounded object creation with no rate limit anywhere in the product; Founder
free text becoming model prompt input; a new stored-text render surface (`business_goal`
renders on no Founder-facing page today) that must go through `layout.py`'s `e()` with no
Markdown path; per-field caps, because `MAX_BODY_BYTES` (64 KiB) is a transport bound, not a
field bound.

**Open CTO items:** `is_stuck()` and `BACKLOG` (TASK-025 crosses `STUCK_THRESHOLD_DAYS = 3`
on 2026-09-04 — "currently latent" has expired); `project_id` on intake;
`cmd_task_create()`'s refactor shape; per-field caps (160 / 4,000 / allowlist).

**Design's surviving work.** The Save half of `Main.dc.html` stands, as does
`StartFlow.dc.html`'s **arm-then-confirm** pattern — outlined control arms, filled control
commits, control removed once fired, "started" never rendered unless a transition was
written. It now applies to **Approve Brief & Start Work** only. The label
`Start work on TASK-025…` is wrong: the first click starts understanding, not building.

---

## 2. Chief of Staff's two judgements

CoS decides **who is consulted** and **how deep the evaluation goes**. Nothing reviews either
today; §2.1–§2.4 make both reviewable.

### 2.1 Which perspectives — the only-you test

> A perspective is material for **this** idea if that role can name a specific question about
> **this** idea that would change the recommendation, the scope, the evaluation or the
> assumptions — **and no other role on the roster would raise it.**

- **Generic-sentence check.** If the sentence would be equally true of an arbitrary other
  idea, the role is not material. ("CTO should check feasibility" fails. "This needs
  real-time sync between two machines that have never talked, which changes the smallest
  useful version" passes.)
- **Duplicate check.** If a role already on the roster would say it, the second adds cost,
  not understanding.

**Product is always on the roster.** **Red Team is a rebuttable presumption** — **omitting it
requires a stated reason**, including it does not. **CEO, CTO, Design, Financial,
Security/Privacy** join only on a passing only-you sentence, with the directive's narrowings:
Design when UX materially affects the idea; Financial when relevant; Security/Privacy only
when genuinely relevant.

### 2.2 The audit — the contribution test

> **Every selected role must have produced something that survived into the Founder-facing
> result** — an assumption, alternative, risk, competitor, threat or question traceable to it.
> A role that contributed nothing was not material.

One such role once is noise; a role that repeatedly contributes nothing is the observable
signal that selection is bad. **Requirement:** the roster is persisted with a one-line reason
per role and shown as the "perspectives consulted" element. Nothing captures this today.

### 2.3 How deep — the exposure test

> **Does this idea have to win against an alternative that someone outside this company could
> choose instead?** If nobody outside chooses, competitor and market analysis cannot change
> the recommendation and **must not be produced**. If someone outside chooses, what else they
> could choose is material.

**Light is the default. Full requires a stated reason naming who chooses and what else they
could choose.**

| | **Light** (default) | **Full** |
|---|---|---|
| Typical case | internal utility, tooling, changes to what we already run | commercial product, external users, anything monetised |
| Sections (§3) | all fifteen except 5–7, marked not applicable with the reason; threats technical and execution only | all fifteen; threats across competitive, market, technical, business, regulatory where material |
| Typical roster | Product, Red Team, often CTO | usually adds CEO and Financial |

**A competitor section at Light depth is a defect, not diligence.**

### 2.4 The depth audit

> **Every section produced only because depth was Full must have changed something.** If
> sections 5–7 and the market threats were deleted and the recommendation, scope and
> definition of success were identical, Full was not warranted — that is research theatre.

**Requirement:** depth and its one-line reason are persisted and shown beside the roster.

### 2.5 A roster of one

Product-only is **legitimate and expected**, never silent: the result says so with the reason;
the screen shows a roster of one, not a blank; the full contract and the same gate still
apply. **Self-consistency check:** a Product-only round returning a long assumption list or
questions is evidence the roster was too narrow, and the result should say so.

---

## 3. The output contract — Part 2's fifteen sections

Every round produces **one** Founder-facing result with these sections **where relevant**.

| # | Section | Requirement |
|---|---|---|
| 1 | **Original Idea** | The Founder's exact words, preserved, never edited (§6). |
| 2 | **What We Think You Mean** | Concise interpretation answering *did the factory understand me?* **Sentence-by-sentence paraphrase is a FAIL.** |
| 3 | **What You Are Really Trying to Achieve** | The deeper outcome, not the requested features. **The directive's example is the standard:** not *"you want a progress dashboard"* but *"you want to open the AI Factory and understand within seconds how each child product is progressing without reading internal task records."* Restating features is a **FAIL**. |
| 4 | **Why This May Be Valuable** | Genuine merits — user problem, convenience, speed, simplicity, automation, cost, underserved users, experience, strategic value, new capability. **Never praise an idea because the Founder proposed it. If the merits are weak, say so.** |
| 5 | **Known Competitors / Alternatives** | Full depth only. **3–5 genuinely relevant examples, not a giant list.** Each: what they offer · overlap · where stronger · where we could differentiate. **Substitutes count.** Governed by §4. |
| 6 | **Competitor Data Freshness** | Every §5 claim labelled **VERIFIED / CURRENT · COMPANY INFERENCE · UNKNOWN**. **If research was not performed, say so** — today that is always (§4). |
| 7 | **Competitive Advantages / Merits** | What could make this stronger — UX, cost, speed, automation, integration, audience, personalisation, privacy, distribution, simplicity, technical or business-model advantage. **Do not claim differentiation unless it is real.** *"We do not yet see a strong differentiation"* is a **pass**. |
| 8 | **Threats / Weaknesses** | Only threats that could **materially affect whether or how we build it**. **Not a giant risk register.** |
| 9 | **Our Recommended Direction** | **ONE recommendation**, never five options: what · why · what we build first · what we intentionally postpone. If the idea should change significantly, or a simpler version has a better chance, say so. **If the idea is weak, say so.** |
| 10 | **Initial Scope** | **IN SCOPE NOW** and **NOT IN THE FIRST VERSION**, both populated — what stops a small idea becoming a massive project. |
| 11 | **Important Assumptions** | Only assumptions that could **materially change the result**. No trivia. |
| 12 | **Alternatives Worth Considering** | **Usually 0–3**, genuinely meaningful only. **Inventing alternatives to appear thorough is a FAIL**; zero is a pass. |
| 13 | **What We Need From You** | Genuine Founder decisions only. **Zero is allowed and is a pass** (§3.1). |
| 14 | **Definition of Success** | **Concrete enough for Product, Design, Development, Code Review and QA to know what "done" means** — downstream-facing as well as Founder-facing (§7). |
| 15 | **Company View** | The closing executive judgment, fixed shape (§3.2). |

Sections 1–4 and 8–15 are produced at **every** depth. Only 5–7 are depth-gated, and when
omitted are **marked not applicable with the reason**, never silently absent.

### 3.1 Founder questions (section 13) — the divergence test

> **A question is material if and only if two different honest answers would produce two
> different briefs.**

Write the two likeliest answers; ask whether the recommendation, the scope or the definition
of success would differ. If no — delete it and state the likelier answer as a visible
assumption. If yes — keep it and state in one line *what changes*. **A material question can
always explain its own stakes; one that cannot is decoration.** Anything statable as a
correctable assumption **must** be; *how to build it* is never a Founder question; anything
already answered by the raw idea or `ops/DECISIONS.md` is a failure to read. **Cap three; one
or two beats eight; zero is a passing score.** The stage must never manufacture a question to
look thorough.

### 3.2 Company View (section 15) — fixed shape, no false precision

```
OPPORTUNITY:           High / Medium / Low / Unclear
WHY:                   2–4 sentences
BIGGEST MERIT:         …
BIGGEST THREAT:        …
BEST DIFFERENTIATION:  …
RECOMMENDATION:        Proceed | Proceed with narrowed scope | Investigate first | Reconsider
```

**Executive judgments, not mathematical scores.** No numeric score, percentage, confidence
figure, star rating, meter or weighted rubric. A seventh field, or OPPORTUNITY rendered as a
number or meter, is a **FAIL**.

**Unclear** and **Investigate first** are load-bearing, not filler: they exist so the company
is never forced to manufacture confidence it lacks. **Requirement:** when competitor
information is UNKNOWN *and* materially affects the decision, the honest RECOMMENDATION is
**Investigate first**, not Proceed — the directive's own answer to §4's problem, and it must
be a reachable outcome rather than a value nobody selects. **BEST DIFFERENTIATION** may read
*"none we can see yet"*; asserting differentiation the body does not support is a **FAIL**.

---

## 4. Competitor claims: the labels, and the research gap

Part 2 §6: where current competitor information materially affects the decision — **use
available public research capabilities, do not rely only on stale model memory, distinguish
verified current information from inference, preserve evidence and sources where possible,
and never invent pricing, customer counts, revenue, funding, market share or features.**
Every claim is labelled **VERIFIED / CURRENT**, **COMPANY INFERENCE** or **UNKNOWN**, and
**if research has not been performed, say so.**

### 4.1 What that means here

**No agent in this factory has any research capability.** `agent_runtime.py`'s
`_run_claude()` launches every dispatched agent with `"--tools", ""` (line 304) — zero
built-in tools: no web search, no fetch, no file read, no shell. **The public research
capability the directive refers to is not wired into the deciphering path.**

> **Every competitor claim the factory can make today is COMPANY INFERENCE or UNKNOWN.
> VERIFIED / CURRENT is unreachable, and every evaluation discussing competitors must state
> that research was not performed.**

That is the directive's own instruction (*if research has not been performed, say so*)
applied to this factory's real capability, and it pairs with §3.2: an UNKNOWN that matters
produces **Investigate first**.

**Future work the directive anticipates and this brief does not design:** wiring a research
capability into the deciphering path so VERIFIED / CURRENT becomes reachable. It would relax
`--tools ""`, a security control — **a separate Founder decision with Security and Red Team**
(§10.7), named so it is neither forgotten nor silently assumed.

### 4.2 The labelling requirement

- **Every claim about a third party carries exactly one label.** Unlabelled is a **defect**.
- **VERIFIED / CURRENT requires a preserved source.** The label without a source is a
  **defect** — and since nothing can produce a source today, a VERIFIED label appearing at
  all is itself the signal that something fabricated it.
- **COMPANY INFERENCE** is the default for model recollection, carrying the caveat that it is
  unverified and may be out of date. **UNKNOWN** is a first-class answer; *"we do not know,
  and cannot check"* is a **pass**.
- **Standing disclosure on the section itself**, not a page footer: *"No agent in this company
  can browse the web. Nothing below was researched — it is what the company recollects, and it
  may be out of date or wrong."*
- **Never invented, at any depth, with or without a hedge:** pricing, customer counts, revenue,
  funding, market share, features. A fabricated number with "roughly" in front is still
  fabricated. Extends to rankings and superlatives (*leading, biggest, most popular*) and to
  present- or recent-tense claims about a third party's current state (*currently offers,
  recently launched*).
- **Substitutes before vendors.** How users solve the problem today — a spreadsheet, a manual
  process, a group chat — is more decision-relevant *and* needs no verification.
- **The flattering fabrication.** If the company knows of no competitors, the honest output is
  *"We are not aware of established competitors, and cannot check. That is not evidence there
  are none."* Rendering absence of knowledge as **"there are no competitors"** is a **FAIL**,
  always — it is the claim the Founder most wants to hear.
- **Every named third party is paired with a Founder-checkable prompt**: *"Before committing,
  check whether X already does this — we cannot."* One without is a bare assertion the company
  cannot stand behind.

### 4.3 What QA checks — and what QA cannot

**QA also runs with no tools. QA cannot verify that a named competitor exists and must never
certify that it does.** QA certifies that claims are honestly labelled and structurally
permitted. Every check is mechanical and needs no outside knowledge:

1. Every third-party claim carries one of the three labels → else **FAIL**.
2. **VERIFIED without a source** → **FAIL**.
3. **"Research not performed" stated** whenever section 5 has content → else **FAIL**.
4. **Never-invent scan** — no pricing, customer count, revenue, funding, market share or
   feature claim about a named third party; no ranking superlative; no present/recent-tense
   claim about their current state.
5. **Substitutes stated before vendors** → else **FAIL**.
6. **Founder-checkable prompt** on every named third party → else **FAIL**.
7. **Depth conformance** — sections 5–7 present at Light depth → **FAIL**.
8. **No-knowledge rendering** — "there are no competitors" → **FAIL**.
9. **Standing disclosure present** on the section → else **FAIL**.

**Red Team makes the check QA structurally cannot:** *which of these did we actually know, and
which did we infer from the shape of the idea?* An inferred competitor presented as a known one
is the exact failure this section prevents.

---

## 5. The Founder-facing shape

**The ten questions are the concise layer; the fifteen sections sit behind them on demand.**

> **Concise layer = everything needed to decide whether to approve.**
> **Expanded layer = everything needed to check that decision.**
>
> If the Founder must expand something to know whether to approve, it is in the wrong layer. If
> a Founder who approves **without expanding anything** has been misled, the concise layer is
> wrong.

**Hard consequence:** nothing that would change the decision may live only in an expanded
section. The fatal risk does not get buried under *Threats ▸*. Progressive disclosure is for
depth, never for hiding.

Concise layer = **the Original Idea, always visible beside the interpretation** · **the ten
answers** · **the Company View**, never behind a disclosure.

| Concise question | Answered by | Expands to |
|---|---|---|
| 1. Did the factory understand my idea? | §2 | sections 1 + 2 side by side |
| 2. What am I really trying to achieve? | §3 | §3 in full |
| 3. Why might this be worth building? | §4 | merits in full |
| 4. What already exists? | §5 + §6 | competitor/substitute detail with labels, disclosure, Founder checks (§4) |
| 5. What could make ours different? | §7 | §7 in full |
| 6. What could make it fail? | §8 | threats by category |
| 7. What does the company recommend? | §9 + §10 | recommendation, IN SCOPE NOW / NOT IN THE FIRST VERSION, §12's alternatives |
| 8. What assumptions did the company make? | §11 | the full assumption list |
| 9. What decisions do you need from me? | §13 | the stakes line per question |
| 10. How will we know we succeeded? | §14 | criteria concrete enough for downstream |
| *(closing judgment)* | §15 | — always visible, never expanded |

Also expanded, behind one click: the roster with per-role reasons, the depth reason, and the
full internal debate (§6). **Never shown by default:** raw per-agent reports.

**Requirements on the concise layer.** **All ten answered, including the uncomfortable ones** —
one the company cannot answer well is answered *"we don't know, and here is why"* **in the
concise layer**, never dropped behind a disclosure; the ten are a completeness contract.
**Bounded** — a few sentences each, the whole layer readable in about two minutes without
expanding anything. **Depth does not change its shape** — at Light depth questions 4 and 5 are
still answered (*"nothing directly comparable that we know of; this is internal tooling, so what
exists does not change the recommendation"*). Depth changes the expanded layer's size.

---

## 6. The three artifacts

The company must always be able to answer: what did the Founder originally say · what did the
company interpret · **what merits, competitors and threats did it identify** · what did it
recommend · what did it assume · what did the Founder approve. `tasks` has flat columns and no
versioning, so today it answers none of these. **Schema is CTO's.**

> **The Founder must always be able to open the product and see the words they originally typed,
> next to what the company decided those words meant — forever, on the same screen, not in an
> archive.** Any design that satisfies everything else and fails this, fails.

| Artifact | Author | Mutable? | Role |
|---|---|---|---|
| **Raw idea** | Founder, at intake | **Never.** Write-once. | What was asked for. Historical context downstream — never the instruction. |
| **Interpreted & evaluated brief** | The round, synthesised by CoS | Append-only — a new round makes a **new version**, never an edit | The fifteen-section contract at round N. |
| **Approved brief** | Founder, approving a specific version | Terminal for that task | **The authoritative instruction to every downstream agent** (§7). |

`business_goal` is written once, at intake, and **never overwritten by any agent, ever.** It *is*
the raw-idea artifact and section 1 of the contract. Nothing stops that today — `task-update`
exists and Product is its natural caller.

**Persistence requirements.** (1) **Distinguishable by kind** from the data, not by convention.
(2) **Every round retained** — *Reconsider* makes this multi-round; this rules out flat
`interpreted_brief` / `approved_brief` columns, which hold only the latest. (3) **The approved
brief is identifiable as a specific version** — ideally a pointer, not a re-typed copy; a copy can
drift, and if copied it must be provably identical at the moment of approval. (4) **§4's labels
survive storage** — they are part of the claim, not render-time presentation; an evaluation that
loses its labels has become unsourced assertion. (5) **Nothing is deleted.**

**Preference (shape is CTO's):** a versioned, append-only brief record — `task_id`, `version`,
`kind`, `content`, `author`, `created_at`, link to the round, roster reasons, depth reason,
matching `task_status_history`, a pattern this project already understands. Reusing
`requirements` / `acceptance_criteria` is rejected — those are Product's normal downstream
outputs, and overloading them conflates "what we think you meant" with "the spec we built from
it."

**Nearly free:** the meeting machinery already persists every position and synthesis as a
`meetings` row plus `messages`. **Requirement:** the round links to that record; the screen shows
only roster, depth and synthesis; the debate is one click away.

---

## 7. Downstream source of truth — a release blocker

Once a Founder-approved brief exists, Product, Design, CTO, Red Team, Developer, Code Review, QA,
Security and every other downstream agent **receive the approved brief as the authoritative
product instruction.** The raw idea is historical context only. **No agent independently
reinterprets the one-line idea.**

**This is the single most likely place for DEC-015 to be quietly violated**, because the code that
violates it works today and nothing about it looks wrong. Two confirmed sites feed the **raw
idea** into agent transcripts now:

- `ops/control-center/review_transcripts.py` lines 203–204 and 261–262 — both
  `parts.append(f"Business goal: {task_row['business_goal']}")`.
- `ops/control-center/launch_developer_session.py` line 129 — `"business_goal"` inside the
  `_TASK_FIELDS_FOR_TRANSCRIPT` tuple.

**Requirement.** For any task with an approved brief, the approved brief is the product
instruction in every dispatched transcript; `business_goal` appears — if at all — only beneath a
label marking it historical (*"Original idea as typed — context, not the specification"*). For a
task with no approved brief, behaviour is unchanged. Section 14 is written for these same
downstream agents. **Completeness:** those two are what I found by grep, not provably all. **CTO
enumerates every code path that builds an agent transcript from a task row**; the test covers
each. An unenumerated site is an untested leak.

### 7.1 The named test — SOT-1

> Create a task whose raw idea contains a distinctive marker absent from the brief. Run one round
> and approve a brief containing a second marker absent from the raw idea. Dispatch through
> **each enumerated call site**. Assert per site: **(a)** the approved-brief marker appears in
> the built transcript; **(b)** the raw-idea marker is absent, or appears only beneath the
> historical-context label; **(c)** no code path builds a downstream transcript with
> `business_goal` as the primary instruction.

Two markers, because it catches both failure directions — the brief not arriving, and the raw idea
still being read as the spec. **SOT-1 is a release blocker.** TASK-024 does not ship with an
approved-brief concept that downstream agents do not read.

---

## 8. The review gate, and reuse vs new

### 8.1 Three actions, plus the consequential one

| Action | Meaning | New version? | Model spend? |
|---|---|---|---|
| **Edit / Correct** | The Founder edits the brief's text directly. | Yes → vN+1, authored by **the Founder** | **No — no model invocation** |
| **Reconsider** | Founder gives feedback; the company re-evaluates interpretation, assumptions, evaluation, recommendation or scope. | Yes → vN+1 | **Yes — a full round** |
| **Approve Brief** | Accepts a version as the approved brief. **Starts no work.** | No | **No** |
| **Approve Brief & Start Work** | Approves *and* dispatches. | No | **Yes — the expensive one** |

- **Reconsider requires the Founder's feedback.** It is the only send-back; with nothing
  attached it produces round N+1 substantially identical to round N at full cost. Capturing that
  text is what makes the action work at all (§8.3).
- **Edit costs nothing and is attributed to the Founder** — crediting an edited version to the
  company would corrupt the exact question §6 answers. **Edit never reaches the raw idea.**
- **Reconsider spends again, and the control says so on itself**, not in a paragraph above it.
  Rounds are numbered and visible; from round 3 the product should say something honest (*"the
  next round costs again — it may be cheaper to approve and correct downstream"*). **Not a hard
  block.**
- **Leaving the gate is free and lossless** — navigating away decides nothing, spends nothing,
  loses no round, leaves the idea findable.
- **Approve Brief alone is a complete outcome** — approved, nothing dispatched, nothing spent,
  Start Work available later.

Arm-then-confirm applies to **Approve Brief & Start Work** only. Before that click the screen
states: agents will begin working; real AI cost may be incurred; the approved brief becomes the
authoritative instruction. Plus two things the product knows and the Founder does not — **there
is no stop button**, and **the approved brief, never the raw idea, is what those agents receive.**

### 8.2 The engine already exists

**`chief_of_staff.py` + `meeting_orchestrator.py` already implement most of this** — deciphering
is mechanically the consult-then-narrate flow from Phase 3A, so specifying a parallel system
would be the wrong call. `_parse_consult()` (CoS names roles on a `CONSULT:` line; deterministic
Python matches them against a fixed allowlist and drops the rest) **is** §2.1's selection
mechanism. `run_consult_meeting()` → `_gather_and_synthesize()` (a real `meetings` row, positions
gathered concurrently under `MAX_CONCURRENT_INVOCATIONS`, each persisted, then synthesised) **is**
internal debate, already persisted where §6 wants it. `_build_narration_transcript()` plus the
second CoS invocation already returns **one** Founder-addressed answer in a fixed shape — so §3's
fifteen sections and §5's ten questions are a **prompt and render change, not a new system**.
Bounds exist: `MAX_MEETING_PARTICIPANTS = 6`, `cap_participants()`, `MAX_CONCURRENT_INVOCATIONS`,
`MAX_BUDGET_USD = "0.50"`.

**Genuinely new:**

1. **A task-scoped caller.** The only entry today is a Founder chat message on the
   `agent-orchestrator-company` thread; this must be triggered *by a task* with output attached
   *to that task*. A new caller, not a new engine.
2. **The roster rule conflicts with the code in two places.** `run_consult_meeting()` **always
   adds CEO** (`meeting_orchestrator.py` lines 390 and 445) and never guarantees **Product**; the
   directive requires the reverse, and under §2.3 CEO on a Light-depth internal utility is exactly
   the waste the directive names. "CEO is always a participant — never optional" is a stated rule
   in two functions, so this is **CTO's decision, not mine to change quietly.**
3. **`design` is not in `MEETING_PARTICIPANT_ALLOWLIST`** — the live tuple (`agent_runtime.py`
   line 79) is `("ceo","product","cto","financial","marketing","qa","security","red-team")`, and
   the directive names Design when UX materially affects the idea. A security-relevant allowlist
   change. **Flagged, not decided.**
4. **Roster reasons, depth and depth reason are captured nowhere** —
   `meetings.participating_agents` records *who*, never *why*; nothing records depth.
5. **§4's labelling** — the part most likely to be dropped as presentation polish. It is the
   difference between an evaluation and a fabrication.
6. **The persisted briefs (§6), the gate (§8.3), SOT-1 (§7) and the Founder-facing screens.**

In the existing flow **CEO synthesises the meeting and CoS narrates to the Founder.** CEO's
synthesis is an **internal** artifact feeding CoS's narration and must never be shown to the
Founder as the answer. The code already works this way; the requirement is that it stays that way.

### 8.3 Approvals: reuse, with one real gap

**Reuse the existing `approvals` table and `/api/approvals/<id>/decide` as-is, one approval row
per round.** No new approval machinery, decision states or auth. The columns already describe an
interpretation (`request`, `why`, `recommendation`, `alternatives_considered`, `expected_cost`,
`risks`, `consequence_if_not_approved`); `tasks.status` already has **`FOUNDER_APPROVAL`** and
`task_is_stuck()` already **excludes** it (`BACKLOG` is *not* excluded — still the §1 defect); and
`decide_approval()` is atomic and double-submit-safe, its conditional
`UPDATE ... WHERE decision IN (...)` making a second click affect **zero rows**.

**The mismatch.** `decide_approval()` is deliberately single-shot; the gate needs repeated
send-backs. Resolved by not asking it to do what it was built to refuse: round N produces version
vN **and one new `approvals` row**, decided exactly once; a Reconsider closes it forever and round
N+1 creates a new one. Zero changes to the function, CHECK constraint, route or auth.

**The genuine gap.** There is nowhere to put the Founder's words —
`decide_approval(conn, approval_id, decision)` takes a decision and nothing else, and the route
accepts nothing else, but **Reconsider is worthless without them.** **Requirement (mechanism is
CTO's):** the Founder's text is captured at the moment of decision, persisted verbatim, attributed
to the Founder, and supplied to the next round — **without** creating a second, unreviewed way to
decide an approval.

### 8.4 An honest cost ceiling

0 of 13 `agent_runs` rows carry `cost_usd`, so any *estimate* would be fabricated — the same
offence as a fabricated market number. The *maximum* is knowable: every invocation runs with
`--max-budget-usd 0.50`, and one round is at most 1 CoS selection + up to 6 positions + 1 CEO
synthesis + 1 CoS narration = **≤ 9 invocations ≤ $4.50 per round.** **Three conditions or it must
not be shown:** recompute from the mechanism CTO builds (never copy this figure); it is **per
round**, so the Founder must see how many rounds they have paid for; and a Light round costs less
than a Full one, part of why depth is shown.

---

## 9. Two things flagged honestly

**9.1 No skill dependency.** `prompt-master` fires in an interactive session but is
**user-account-synced, not repo-provided** — a fresh clone, another account or CI has none. More
decisively, **no dispatched agent can invoke any skill at all**: `agent_runtime.py` line 304
passes `"--tools", ""`, so the `Skill` grant carried by eight agent definitions
(`.claude/agents/*.md` line 4) is **inert on the runtime path**. No brainstorming skill exists
anywhere reachable. **Consequence:** the stage has no skill dependency; its quality is
**behavioural**, met by the instruction transcript, the roster and the depth setting, and enforced
by what QA checks it produced. This **answers** TASK-025's verification question. The same
`--tools ""` line is why §4 exists; it is a deliberate security control and I am **not**
recommending it be relaxed.

**9.2 Money is spent before anything is built.** What the Founder must be told **before the first
click**: (1) this starts *understanding and evaluation*, not building; (2) it spends real money
across **several agents**, not one; (3) there is no per-round estimate — 0 of 13 recorded runs
carry a cost figure; (4) there **is** an enforced ceiling (§8.4); (5) there is **no stop button**;
(6) this is the first spend of possibly several, learned before round 1 rather than by being
charged.

---

## 10. Scope exclusions

Revision 1's exclusions **all stand**: no editing a task from the UI, no delete or archive, no CRUD
surface, no attachments, no multi-project, no auto-start on submit, no retro-fixing existing rows,
no rendering of `user_story`/`requirements`/`acceptance_criteria` on Task Detail. Design's Concept
B receipt and Concept C inline capture remain **rejected**. Added:

1. **No unattended automatic pipeline execution.** This governs all the others.
2. **No cascade on Start Work.** DEC-012's freeze is untouched.
3. **No auto-approval in any form** — never by timeout, never because nobody looked. **Silence is
   not consent.**
4. **No editing the raw idea**, by anyone, ever.
5. **No brainstorming subsystem and no skill dependency of any kind** (§9.1).
6. **No invented competitor information and no fabricated market numbers** (§4) — nor fabricated
   cost estimates, the same offence.
7. **This milestone does not add a research capability.** "Evaluate competitors" is not
   authorisation to wire web access into the agent runtime; that would relax `--tools ""`. Making
   VERIFIED / CURRENT reachable is **future work requiring a separate Founder decision with
   Security and Red Team** (§4.1).
8. **No automatic depth escalation.** Full requires a stated reason (§2.3).
9. **No scores, meters or rubrics on the Company View** (§3.2).
10. **The stage is not Design** (no screens or wireframes), **not architecture** (no schema, routes
    or technology choice — if a brief names a technology, QA fails it), **not a feasibility
    study**, **not an estimate** (no dollars, hours or t-shirt sizes), and **not the
    decision-maker**.
11. **No hard cap on rounds** — numbered, visible and warned, not blocked.
12. **No retro-interpretation** of existing tasks.
13. **No multi-Founder review, comments, threads or @-mentions.**
14. **No showing raw agent reports to the Founder.**

---

## 11. Acceptance criteria

AC-1 – AC-11 from Revision 1 stand (intake creates one `BACKLOG` row plus one history row via
`opsdb.py`; the task appears on Active Work and Task Detail; the Founder's text reads back; empty
and over-cap submissions are rejected with the typed text preserved; markup stored verbatim and
rendered escaped; the route requires session + CSRF; nothing else changes; a parked idea is not
presented as a failure). Added:

**The round and the contract**

12. A round runs **only** interpretation and evaluation — no Design, CTO, Red Team or Developer
    implementation invocation; participating is not dispatch. The output is **one** synthesis;
    per-agent reports shown to the Founder are a **FAIL**.
13. **All fifteen sections present**, with 5–7 either produced or **marked not applicable with the
    reason**. Silently absent is a **FAIL**.
14. Section 2 is not sentence-by-sentence paraphrase; section 3 states a deeper outcome rather than
    restating features, at the standard of the directive's dashboard example.
15. Section 9 gives **one** recommendation with what to build first and what to postpone (five
    options is a **FAIL**); section 10 has both scope lists populated; section 12 has 0–3
    alternatives, zero passing; section 14 is concrete enough that QA can state what "done" means
    from it alone.
16. QA treats *"the merits are weak"* and *"we do not yet see a strong differentiation"* as
    **passes**, and checks section 4 does not praise merely because the Founder proposed it.
17. **Section 8 is not a risk register** — every threat is tied to how it would change whether or
    how to build; threats that would not are a **FAIL**.
18. **Company View has exactly §3.2's six fields**, with the fixed OPPORTUNITY and RECOMMENDATION
    vocabularies. **Any numeric score, percentage, confidence figure or meter is a FAIL**, as is
    asserting differentiation the body does not support.
19. **Roster, depth and depth reason visible**, one-line reason per role, debate reachable in at
    most one click, and **every selected role's contribution traceable** into the result.
20. A **Product-only** round passes if it says so with the reason; a round selecting every
    available agent is a **FAIL** absent a per-role only-you reason.
21. **Depth conformance:** Light produces no sections 5–7. A Full round whose sections 5–7 and
    market threats could be deleted without changing the recommendation, scope or definition of
    success is a **FAIL**.
22. At most **3** Founder questions, one or two preferred, **zero passing**. Each passes the
    divergence test — QA writes two plausible answers and checks whether the brief would differ. A
    question that cannot state its own stakes in one line is a **FAIL**.
23. The brief is **approvable with no questions answered**, usable downstream, and contains no
    screens, schema, routes, technology names, dollar figures or time estimates.

**Evaluation honesty**

24. **§4.3's nine checks all pass** on any round with competitor content.
25. **A VERIFIED / CURRENT label appearing at all, while no research capability is wired in, is a
    FAIL**, treated as evidence of fabrication (§4.1).
26. QA's report **states it verified labelling, not existence** — a pass must never read as
    confirmation that a named competitor is real.
27. *"We are not aware of competitors and cannot check"* is a **PASS**, and **Investigate first**
    is reachable and is produced when UNKNOWN competitor data materially affects the decision.

**The Founder-facing shape**

28. The concise layer answers **all ten questions** — including *"we don't know"* where true —
    shows the Company View, and is readable without expanding anything. All ten plus the Company
    View are present at **both** depths.
29. **No content that would change the approve/reconsider decision exists only in an expanded
    section.** QA reads the concise layer alone, decides, expands everything, and checks whether
    the decision would have changed. If it would, **FAIL**.

**The three artifacts**

30. After any number of rounds the Founder sees the **exact original text** they typed, unmodified,
    beside the current interpretation — verified byte-for-byte — and `business_goal` is **never**
    modified after intake, verified across a multi-round cycle including an **Edit**.
31. Round 1 is still readable after round 3 exists, with its evaluation and §4 labels intact.
32. A Founder **Edit / Correct** produces a version attributed to the **Founder** with **zero** new
    `agent_runs` rows.

**Downstream source of truth**

33. **SOT-1 passes at every enumerated call site** (§7.1). **Release blocker.**
34. CTO's enumeration of transcript-building call sites is recorded and each is covered by SOT-1.
    An unenumerated site is a **FAIL**.

**The gate**

35. A brief is **never** approved without an explicit Founder action — no timeout, no default, no
    auto-approve path exists.
36. A **Reconsider** carrying feedback produces a round that **demonstrably reflects it**, with the
    prior round retained; one with no feedback does not silently spend a round.
37. Deciding the same approval row twice affects **zero rows** the second time and triggers no
    second paid round.
38. **Approve Brief** dispatches nothing, and Start Work remains available afterwards.
39. **Approve Brief & Start Work** does not render "started" unless a transition was written; a
    failed dispatch leaves the task where it was and says so.
40. §9.2's disclosures precede the first click, and the round-cost warning is **on** the Reconsider
    control, not only in surrounding prose.

---

## 12. What Revision 4 cut

*Brainstorm More* and *Refine* and every rule about them (one **Reconsider** replaces both);
DEC-014's six-section synthesis shape and Revision 3's field list (both superseded by Part 2's
contract); a provenance-labelling scheme drafted before Part 2 arrived (**superseded by the
Founder's VERIFIED / COMPANY INFERENCE / UNKNOWN**); Revision 3's long `prompt-master`
investigation (compressed to §9.1 — the finding survives, the narrative does not); the header's
account of a damaged intermediate file state (historical, in git); and justification prose
throughout. **Nothing that constrains what gets built was removed.**

---

## 13. Open questions for CTO

1. **`is_stuck()` and `BACKLOG`** — no longer latent (§1); must not ship undecided.
2. **`project_id` on intake** — `1` or `NULL`.
3. **`cmd_task_create()`'s refactor shape.**
4. **Per-field caps** — 160 / 4,000 / allowlist.
5. **Brief-storage shape** (§6), including how §4's labels are stored so they cannot be lost.
6. **Where Reconsider feedback is captured** (§8.3) — the one real gap in reusing approvals.
7. **Which decision value means "send it back"** — `discuss` or `reject`; `discuss` reads more
   accurately.
8. **The roster rule vs. `run_consult_meeting()`'s CEO-always rule** (§8.2.2).
9. **Whether `design` joins `MEETING_PARTICIPANT_ALLOWLIST`** (§8.2.3) — needs Security's view.
10. **The full enumeration of transcript-building call sites** (§7) — SOT-1 depends on it.
11. **Where depth is recorded** (§2.3) — persisted and shown, not implied by who participated.
12. **The real per-round cost ceiling** (§8.4) — recomputed, or not shown.

**Outside this milestone, needing an owner:** wiring a research capability into the deciphering
path so VERIFIED / CURRENT becomes reachable (§4.1) — Founder decision, with Security and Red
Team; eight agents carry an inert `Skill` grant on the runtime path (§9.1);
`.claude/agents/product.md` line 10 overstates `prompt-master`; and `ops/db/ops.db` is an empty
stray file (0 tables) beside the real `ops/db/operations.sqlite3`.

---

## 14. Handover

Design must make the directive's full journey walkable — raw idea → interpreting → understanding →
**evaluation** → review → correction/reconsideration → approval → approved brief → start work →
execution — with the five states visually distinguishable (*what I said · what the factory thinks I
meant · what the factory thinks about the idea · what the factory recommends · what I approved*).
The artboards are **Design's**. Handed over rather than decided: the **wording** of every
disclosure; **how** the raw idea sits beside the interpretation on screen (only that it always
does); and **how the concise/expanded split is rendered** (the requirement is §5's rule and
mapping, not a particular control). Not up for relitigation: Design is **not** complete because
individual screens look attractive, and Development does not begin until the Founder has seen the
revised clickable mockup.
