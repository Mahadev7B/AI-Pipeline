# Product Brief — TASK-024: Founder Idea Intake

**Revision 2 — re-briefed under DEC-013.** Author: Product agent · Date: 2026-09-01
Status: for Design (revise Start flow), then CTO
Task: TASK-024 · Prior state: PLANNING → MOCKUP on delivery of this revision

Revision 1 (same file, sections 1–10) was written before DEC-013 and before the
Founder's mid-design scope correction recorded in `ops/reviews/design-review-task024.md`
§0. It is **not withdrawn** — most of it still holds and is still the requirement.
Where DEC-013 supersedes it, the passage is left in place and marked
`[SUPERSEDED — see §N]` rather than deleted, so the record shows what the company
believed before the Founder corrected it. New sections §11–§19 carry everything
DEC-013 adds.

---

## 0. What changed under DEC-013, and what it supersedes

DEC-013 (2026-09-01, the Founder's own written directive) replaces the journey
this brief was written against.

Revision 1 assumed: **Founder types an idea → it lands in `BACKLOG` → something
later starts the pipeline.** Design's §0 correction then added a Founder-pressable
Start. DEC-013 changes what Start *does*.

The journey is now:

> **Raw Idea → Save → Refine/Brainstorm → Interpreted Brief → Founder Approval →
> Start Execution → Design / CTO / Red Team / Development**

"Start work on this" must **not** launch Design, CTO or Development. It launches an
idea-understanding stage. Only a Founder-approved interpretation starts real building.

| Revision 1 section | Status under DEC-013 |
|---|---|
| §1 The problem | **Holds.** Still the reason this milestone exists. |
| §2 Who this is for | **Holds**, and matters more — a non-technical Founder is exactly who needs an interpretation checkpoint. |
| §3 BACKLOG, not auto-start | **Holds.** Auto-start on submit is still out. DEC-013 strengthens the argument rather than weakening it. |
| §4 What the Founder types | **Holds for intake**, but `business_goal` acquires a new obligation: it is now the *raw idea artifact* and is **write-once**. See §13. |
| §5 Acceptance criteria | **Extended**, not replaced. AC-1..11 stand; AC-12..24 added in §19. |
| §6 Scope — what this is NOT | **Holds in full**, extended by §17. |
| §7 Constraints | **Holds in full.** Unchanged. |
| §8 Security weight | **Holds**, and grows: the refinement stage makes Founder free text a *model prompt* on a new path. See §18. |
| §9 Assumptions | One superseded — see marker in §9. |
| §10 Open questions for CTO | **Superseded by §20**, which carries all four forward plus what DEC-013 adds. |

**The single most important new requirement, stated once, plainly:** the Founder
must always be able to see **what they originally typed**, next to **what the
company decided it meant**. Nothing in this milestone may destroy, overwrite, or
silently improve the raw idea.

---

## 1. The problem

The Founder tried to enter an app idea into the Control Center and could not.
There is no route in this product that creates work. Every write route the
server accepts — `/api/login`, `/api/logout`, `/api/approvals/<id>/decide`,
`/api/agents/<name>/ask`, `/api/meetings` (+ decide / request-perspective /
followup / retry), `/api/chief-of-staff/ask`, `/api/automation/stop|start`,
`/api/tasks/<id>/review/{code,security,red-team}` — acts on an object that
already exists. All 24 tasks in this company's history were created by running
`python3 ops/db/opsdb.py task-create` in a terminal, by the orchestrator on the
Founder's behalf.

**The completeness audit missed this, and it is worth naming why.** DEC-009 set
the bar as: "if the Founder has to open GitHub, SQLite, Markdown, terminal
output, or an outside AI to understand what the company is doing, the UI is not
feature-complete." The audit that followed (30 capabilities, Milestones A–D)
tested that bar faithfully — for *observation*. It asked whether the Founder
could see everything. It never asked whether the Founder could *start* anything.
"Complete" was defined as complete visibility, and the definition was never
challenged. The product is a cockpit with every instrument and no ignition.

The Founder chose to build this front door before bringing a real idea through
it (Path B), rather than starting the idea through the existing CLI (Path A).

## 2. Who this is for

One non-technical Founder, signed in on their own machine, with an idea in their
head and no interest in writing a spec. That is the entire user population. Every
decision below is made against that user and no other.

## 3. Recommendation on the core question: BACKLOG, not auto-start

**Question:** when the Founder submits an idea, does it (a) immediately start the
pipeline — auto-advance to PLANNING and dispatch Product, (b) land in `BACKLOG`
awaiting a deliberate "start", or (c) something else?

**Recommendation: (b) — the idea lands in `BACKLOG`. Submitting is not starting.**

This is a real recommendation, not a hedge. Three reasons, in order of weight:

1. **Auto-start is not a small addition — it is unauthorized Phase 3 automation.**
   Nothing in this system dispatches Product, ever. `AUTOMATED_REVIEW_ALLOWLIST`
   in `ops/control-center/agent_runtime.py` contains exactly one entry,
   `("code-review",)`, and the automation poller's single authorized handoff is
   Developer-complete → Code Review (DEC-007). Auto-start would be the first
   automatic dispatch of a new agent type, on the exact path DEC-012 froze:
   Phase 3 automation is explicitly not started, gated behind TASK-023's security
   lock, which most recently *failed QA with four blocking defects*. Choosing (a)
   silently reopens a sequencing decision the Founder made three times (DEC-008,
   DEC-010, DEC-012). That alone settles it.
2. **A submit button that spends money is the wrong first version of a text box.**
   Auto-start makes an unbounded-cardinality button — one that can be clicked
   repeatedly, from a page the Founder can leave open — into a trigger for real
   model invocations at real cost. Today the only Founder actions that spend
   money (Ask-Agent, Meetings, Chief of Staff) are ones where the Founder is
   obviously asking for model work. "Save my idea" does not read that way.
3. **The second click costs the Founder about two seconds and buys them the
   ability to change their mind.** Ideas get typed half-formed. Land-then-start
   lets the Founder write three ideas Sunday night and start one Monday. Auto-start
   turns every draft into committed company work.

**What "the second click" is, and is not:** [SUPERSEDED — see §11 and §15. Design's
§0 correction established that a Start control *is* required; DEC-013 then established
that what it starts is refinement, not the pipeline. The paragraph below is left intact
because its reasoning — that submitting must not equal starting — survives both
corrections and is still load-bearing.] this brief does *not* require building
a start-the-pipeline button. Advancing a task out of `BACKLOG` already happens the
way every other status transition in this company happens — the Founder asks the
Chief of Staff, or `task-status` is run on their behalf. Intake's job is to get the
idea into the system as a real, visible, well-formed task. What starts it is
unchanged by this milestone and is out of scope (§6).

**One consequence CTO must handle, found while researching this brief:** a
`BACKLOG` task will be flagged **"stuck"** on the Active Work dashboard after 3
days. `ops/db/derived_state.py` `STUCK_THRESHOLD_DAYS = 3`, and `is_stuck()`
excludes only `BLOCKED`, `FOUNDER_APPROVAL`, `DONE` — its own docstring (lines
~341–349) records this as a *known, deliberately-unresolved ambiguity* flagged for
CTO, "currently latent (no active BACKLOG task exists)". This milestone makes it
non-latent on day one: the recommended design produces exactly the row type that
docstring says nobody resolved. Either `BACKLOG` is excluded from `is_stuck()`, or
a parked idea starts nagging the Founder as a failure. CTO's call which; it must
not ship undecided.

## 4. What the Founder actually types

The `tasks` table has six substantive fields (`title`, `business_goal`,
`user_story`, `requirements`, `acceptance_criteria`, `priority`). Requiring all six
turns "I have an idea" into a form-filling chore and — more to the point — asks the
Founder to do the Product agent's job. Requiring only a title lets a task reach
Design and CTO with nothing in it.

| Field | Intake | Why |
|---|---|---|
| `title` | **Required** | Short name. It is what every existing page renders — Active Work cards, Pipeline, Task Detail, Progress. A task with a bad title is unusable everywhere. |
| `business_goal` | **Required** | This is *the idea*. Free text, paragraph-shaped, prompted as "what do you want, and why does it matter?" It is also the field that already flows into agent transcripts (`ops/control-center/review_transcripts.py` lines 203–206, 261–264) and the Developer session context — so it is the field that actually reaches the agents who will build it. |
| `priority` | **Optional**, from a fixed list (high / medium / low), default medium | One click, no typing. Must be a constrained value, not free text — see the finding below. |
| `user_story` | **Not at intake.** Derived by Product. | Writing a user story is a skill. Asking the Founder for one gets a worse story than Product would write from the same idea. |
| `requirements` | **Not at intake.** Derived by Product. | Same. This is the Product brief's own output. |
| `acceptance_criteria` | **Not at intake.** Derived by Product. | Asking a non-technical Founder to write testable acceptance criteria before the work is understood is asking them to do QA's and Product's jobs at the moment they know least. |

**Two required fields, one optional selector. Nothing else.**

The garbage-input worry is real but is answered by the pipeline, not by the form.
An idea in `BACKLOG` with a title and a paragraph is exactly the input this company
already handles well: Product turns it into a brief, Design and CTO build from the
brief. Intake's job is to capture intent faithfully, not to pre-validate it. What
protects Design and CTO is the `BACKLOG` gate and the Product stage — not a longer
form.

**Finding, for CTO:** `priority` today is uncontrolled free text — the live database
holds `NULL` (15 rows), `high` (3), and four one-off strings like
`"P0 - Phase 1 Foundation"`. Intake must write one of a fixed set. Retro-fixing the
existing rows is **out of scope** (§6).

**Open question for CTO (not mine to decide):** `project_id`. 18 tasks have `NULL`,
4 have `1` ("AI-Pipeline Ops Bootstrap"). Intake must set it consistently. My
preference is `1`, so the task carries a project label on the pages that render one;
CTO decides.

## 5. Acceptance criteria

Written in the shape QA verifies.

1. A signed-in Founder can reach an idea-submission surface from the Control Center's
   own navigation, without typing a URL by hand. (Design chooses the placement.)
2. Submitting title + idea creates exactly one row in `tasks` with status `BACKLOG`,
   and exactly one corresponding `task_status_history` row (`from_status` NULL →
   `to_status` `BACKLOG`), attributed to the Founder.
3. The created row is written through `opsdb.py`. QA verifies no SQL statement
   against `tasks` exists in the web layer for this feature.
4. The new task appears on the Active Work dashboard and has a working Task Detail
   page at `/tasks/<id>.html` on the next page load, with no manual regeneration step.
5. **The text the Founder typed is visible back to them in the product** — at minimum
   `business_goal` on Task Detail. Today none of `business_goal`, `user_story`,
   `requirements`, `acceptance_criteria` is rendered on any Founder-facing page
   (verified: those column names appear in `review_transcripts.py` and
   `launch_developer_session.py` only). Write-only intake would fail DEC-009's own bar
   the moment it shipped — the Founder would have to open SQLite to re-read their own
   idea. This is the one place I am adding a requirement beyond "make a task," and it
   is the Founder's existing standard, not a new one.
6. Submitting with an empty title, or an empty idea, is rejected with a plain-English
   message and creates no row.
7. Submitting text longer than the documented per-field cap is rejected with a message
   naming the limit — same shape as the existing `MAX_ASK_MESSAGE_CHARS` /
   `MAX_TOPIC_CHARS` rejections.
8. A submission containing HTML or script markup (`<script>alert(1)</script>`, `"><img
   src=x onerror=...>`) is stored verbatim and rendered escaped everywhere it appears —
   Active Work card, Task Detail, Pipeline, Progress. Nothing executes.
9. The route is unreachable without an authenticated Founder session, and unreachable
   without a valid CSRF token. QA verifies both by direct request, exactly as the
   existing write routes are verified.
10. Nothing about the Founder's other work changes: no existing task's status, owner,
    or fields are modified by an intake submission.
11. A `BACKLOG` task's Active Work presentation is correct per CTO's resolution of the
    `is_stuck()` question in §3 — specifically, a freshly parked idea is not presented
    as a failure state.

## 6. Scope — what this is NOT

This project's history is full of scope creep caught late. Ruled out explicitly:

- **Editing a task from the UI.** No edit form, no field updates. `task-update` stays a
  CLI operation. A typo in a title is fixed the way it is fixed today.
- **Deleting or archiving a task from the UI.** Nothing in this product deletes anything
  today; intake is the wrong milestone to introduce the first destructive route.
- **A task-management CRUD surface** — no list-and-manage screen, no bulk actions, no
  reordering, no assignment. Active Work and Pipeline already show tasks; a second
  task-management system is exactly what DEC-008 forbade.
- **Attachments, images, file upload.** Text only. Uploads are a materially different
  security and storage problem and were not asked for.
- **Multi-project support.** One project (`projects` has one row). No project picker,
  no project creation.
- **Changing an existing task's status from the UI beyond what already exists.** No
  start button, no cancel, no advance, no reject. Status transitions stay exactly as
  they are today.
- **Auto-starting the pipeline** — per §3. Not deferred quietly; deliberately excluded,
  and it stays excluded until the Founder decides otherwise with DEC-012's sequencing
  in view.
- **Retro-fixing existing rows** — the uncontrolled `priority` values and the
  inconsistent `project_id` in the 24 existing tasks are disclosed above, not cleaned up
  here.
- **Rendering `user_story` / `requirements` / `acceptance_criteria` on Task Detail.**
  Only `business_goal` is required to be readable back (AC-5), because it is the only one
  intake writes. If Design wants the others rendered too, that is a separate, larger
  question about Task Detail, not intake's to answer.

## 7. Constraints (established architecture — not mine to change)

1. `opsdb.py` remains the **sole database writer**. No direct SQL against `tasks` from the
   web layer. The existing pattern is a plain, directly-callable function in `opsdb.py`
   (`record_task_status()`, `decide_approval()`, `record_review_result()`) that raises typed
   errors, with the CLI as one wrapper — `cmd_task_create()` does not have that shape today,
   which is CTO's problem to solve, not Product's to specify.
2. The new route reuses the **existing session + CSRF gate exactly as-is**. No new auth code.
   `do_POST()`'s centralized order — credential gate → body/size limit → CSRF token →
   authenticated-session check → dispatch — is not modified beyond adding one dispatch branch.
3. Static pages are produced by the existing `generate_*.py` builders. No new generation
   mechanism.
4. The refined-dark Command Center visual direction (DEC-002) stands.

## 8. Security weight — flagged up front for Security and Red Team

**This is the first write route in this product that creates work rather than acting on an
existing object.** Every prior write route takes an id that already exists and was created by
a trusted process; its blast radius is bounded by the set of rows already in the database.
This one has no such bound. What that changes:

1. **Unbounded object creation.** Every previous route can be replayed and the worst case is a
   duplicate decision or a wasted invocation on a known row. This route, replayed, grows the
   `tasks` table without limit — and `tasks` is read by Active Work, Pipeline, Progress, the
   Chief of Staff's state digest, and `CURRENT_STATUS.md`. Denial-of-usefulness (a dashboard
   with 5,000 junk cards) is a realistic outcome and there is no rate limit on any write route
   today.
2. **Founder-authored free text becomes agent prompt input.** `business_goal` already flows
   verbatim into reviewer transcripts (`review_transcripts.py`) and Developer session context
   (`launch_developer_session.py`). Text the Founder types now reaches model invocations. The
   Founder injecting themselves is not the threat — the threat is the same-OS-user actor
   `risks.id=3` describes, who can already write `tasks` rows via `opsdb.py` and now has one
   more path whose content is *designed* to be read by an agent. Security should state plainly
   whether this widens that surface or merely renames a door already open.
3. **New render surface for stored text.** `business_goal` is not rendered on any
   Founder-facing page today (verified). AC-5 makes it rendered. That is a new stored-XSS
   surface — mitigated by `layout.py`'s `e()` helper, which every existing render site uses,
   but only if the new render sites use it too, and only if Design does not introduce a
   rich-text or Markdown rendering path (which would be scope creep *and* a security
   regression; see §6).
4. **Unbounded input.** `MAX_BODY_BYTES` (64 KiB) applies at the transport layer, but each new
   field needs its own documented per-field cap in the shape `MAX_ASK_MESSAGE_CHARS` (8,000)
   and `MAX_TOPIC_CHARS` (2,000) already set. Absent that, one submission can put 64 KiB of
   text into a field that later renders on a dashboard card and gets concatenated into an
   agent transcript.
5. **Model spend** — if and only if auto-start is chosen against my recommendation, this
   becomes a Founder-clickable, repeatable trigger for real cost, and Security's review must
   cover the accidental-double-submit and held-enter-key cases. Under the recommended BACKLOG
   design, **this route triggers no model invocation at all**, which is the single largest
   reason to prefer it.

## 9. Assumptions

- Single Founder, single machine, loopback-only, authenticated session — unchanged from every
  prior milestone.
- The Founder wants to capture ideas in their own words, not fill in a spec template.
- Ideas arrive occasionally, not in bulk. No import, no bulk entry.
- ~~The pipeline that runs after an idea is started is unchanged by this milestone.~~
  **[SUPERSEDED by DEC-013 — §11.]** The pipeline gains a stage in front of it. What
  runs *after Founder approval* is unchanged; what runs *on Start* is new.

## 10. Open questions for CTO  [SUPERSEDED — carried forward and extended in §20]

1. `is_stuck()` and `BACKLOG` — resolve the ambiguity `derived_state.py` already documents
   (§3). Must not ship undecided.
2. `project_id` on intake — `1` or `NULL`? (§4)
3. What shape `cmd_task_create()` refactors into so the web layer can call it without SQL and
   without the CLI (§7.1).
4. Per-field character caps and their values (§8.4).


---
---

# Part II — Added under DEC-013

Sections §11–§20. Everything above this line is Revision 1, retained.

---

## 11. The refinement stage — its contract

### 11.1 What it is

One pipeline stage, owned by Product, that runs **between the Founder pressing
Start and any other agent doing anything.** Its single job: turn a raw idea into a
statement of understanding the Founder can check.

It is the answer to the failure DEC-013 names — that the company "begins
implementing an idea without ever confirming it understood the idea correctly."

### 11.2 What it must produce (the deliverable)

One document, the **interpreted brief**, containing exactly these six parts. Not
five, not ten. A reviewer checks for all six by name:

1. **The problem, restated** — what the Founder is actually trying to solve, in the
   stage's own words, not a paraphrase of their sentence. If restating it adds
   nothing beyond what the Founder typed, say so rather than padding.
2. **The intended outcome** — what is true for the Founder after this ships that is
   not true now. Observable, not aspirational.
3. **Assumptions** — everything the interpretation rests on that the Founder did not
   say. Each one individually correctable. This is the load-bearing part: it is
   where a misread surfaces cheaply.
4. **Approaches considered — at least 2, at most 4.** Genuinely distinct *product*
   directions, not the same idea at three sizes. Each with what it gets you and what
   it costs you. Fewer than 2 is not "exploring approaches"; more than 4 is a
   catalogue, and the Founder will skim it.
5. **The recommended direction, with its reasoning** — one named choice, and why it
   beats the others it was compared against. A recommendation without a comparison
   is a preference.
6. **Material clarifying questions — zero to three.** Governed by §12. **Each carries
   the stage's own best answer already applied as an assumption**, so the brief is
   complete and approvable even if the Founder answers none of them.

### 11.3 Its obligations

- **It must be approvable as-is.** A Founder who reads it, agrees, and clicks approve
  must get a brief good enough for Design and CTO to build from. It may not depend on
  the Founder answering anything. Questions are an *offer*, never a *gate*.
- **It must be readable by a non-technical Founder** (§2). No architecture vocabulary,
  no library names, no schema talk. If a sentence needs the Founder to know what a
  route is, it is written wrong.
- **It must quote the raw idea back**, verbatim and visibly, alongside the
  interpretation. Not summarised. The comparison *is* the feature (§13).
- **It must be honest about thin input.** If the Founder typed one vague line, the
  correct interpreted brief says so and leans on assumptions and questions — it does
  not invent detail and present it with confidence. A confident brief built on nothing
  is the exact failure mode DEC-013 exists to prevent, one stage earlier.
- **It must never claim to have done work it did not do.** This company has shipped a
  sandbox that reported success over a no-op, docs claiming a protection that could not
  fire, and a forged review row. The interpretation stage does not get to add a fourth.

### 11.4 Its limits — what it is *not*

Stated as hard boundaries because this stage sits upstream of four agents whose jobs
it could easily start doing. See §17 for these as enforceable scope exclusions.

It is **not Design** (no layout, no screens, no visual concepts), **not architecture**
(no schema, no routes, no technology choice), **not a feasibility study** (it does not
rule on whether a thing can be built), **not an estimate** (no dollars, no hours), and
**not the decision-maker** (it recommends; the Founder decides by approving).

### 11.5 Termination

The stage ends by producing the interpreted brief and parking the task at the approval
gate. It **never** advances itself, never approves its own interpretation, and never
dispatches another agent. One invocation in, one brief out, stop.

---

## 12. What makes a clarifying question "material" — the test

The Founder said **only material** questions. An agent that returns twelve questions
has failed that instruction as completely as one that asks none — twelve questions is
the stage handing its job back to the Founder, which is the thing this milestone exists
to stop.

Here is the test. It is written so a reviewer (or QA) can apply it to a real brief and
get the same answer I would.

### 12.1 The divergence test — the primary filter

> **A question is material if and only if two different honest answers to it would
> produce two different briefs.**

Applied concretely, for each question:

1. Write down the two most likely answers the Founder could give.
2. Ask: under answer A versus answer B, would the **recommended direction**, the
   **scope**, or the **acceptance criteria** actually differ?
3. If **no** — the question is not material. Delete it. Pick the more likely answer,
   state it as an assumption, and move on.
4. If **yes** — keep it, and say in one line *what changes* depending on the answer.
   A material question can always explain its own stakes. One that cannot is decoration.

**The one-line failure test, for a reviewer:** *if the brief would have been identical
whichever way the Founder answered, the question should not have been asked.*

### 12.2 Three supporting filters

- **The assumption-first rule.** Anything that can be stated as an explicit, visible,
  correctable assumption **must** be, rather than asked. DEC-013 asks for assumptions
  *and* questions; assumptions are the default and questions are the narrow exception.
  An assumption the Founder can see and strike out costs them three seconds. A question
  costs them a decision they may not be ready to make.
- **The Founder-can-answer-it rule.** The question must be answerable by *this* user —
  one non-technical Founder (§2). "Should this store state server-side or client-side?"
  is not a material question; it is a CTO question wearing a question mark, and it is
  out of this stage's scope entirely (§17). Material questions are about **what they
  want and why**. Never about **how to build it**.
- **The already-answered rule.** If the raw idea, an existing decision in
  `ops/DECISIONS.md`, or the existing product already answers it, it is not a question —
  it is the stage not having read. DEC-013 is itself the standing example: nobody should
  be asked "should the Founder review this before building?"

### 12.3 The cap: three, and it is a cap not a guideline

**At most three questions.** If more than three survive §12.1–12.2, the stage ranks them
by how much the brief changes and asks the **top three only**; the remainder become
stated assumptions.

Three is not a number I invented. It is the number enforced by the one skill this
role's own definition tells it to use — `prompt-master`'s hard rules include *"Do not
ask more than 3 clarifying questions before producing a prompt."* Adopting that here
keeps the company consistent with a bar it already documented, and — given §16 — it is
the most useful thing that skill contributes to this milestone.

### 12.4 Zero is a passing score

A round with **no questions**, a clear recommendation and a well-stated assumption list
is a **success**, not a shortcut. The stage must never manufacture a question to appear
thorough. QA should treat a zero-question brief with good assumptions as a pass, and a
three-question brief where any question fails §12.1 as a **fail**.

---

## 13. The three artifacts — raw, interpreted, approved

DEC-013: *"All three artifacts must be preserved and distinguishable."* This section
states what must be true. **The data shape is CTO's decision** (§7.1); the requirements
below are not.

### 13.1 What must never be lost — the non-negotiable

> **The Founder must always be able to open the product and see the words they
> originally typed, next to what the company decided those words meant.**

Every requirement in this section serves that one sentence. If a proposed design
satisfies everything else here and fails this, it fails.

Concretely: **`business_goal` is written once, at intake, by the Founder, and is never
overwritten by any agent, ever.** It *is* the raw-idea artifact. Today nothing stops an
agent updating it — `task-update` exists and Product would be its natural caller. Under
DEC-013 that becomes a defect, not a convenience. The raw idea is immutable
(§17: the Founder corrects the *interpretation*, never their own original words).

### 13.2 The three, defined

| Artifact | Author | Mutable? | Role |
|---|---|---|---|
| **Raw idea** | Founder, at intake | **Never.** Write-once. | The record of what was actually asked for. |
| **Interpreted brief** | Product's refinement stage | Append-only — a new round makes a **new version**, it does not edit the old one | What the company thinks the Founder meant, at round N. |
| **Approved brief** | Founder, by approving a specific interpretation | Terminal for that task | **The authoritative input to every downstream agent.** |

### 13.3 Requirements on persistence

1. **All three must be distinguishable by kind**, not by convention or by which column
   someone remembers. A reader (human or agent) must be able to ask "which of these is
   the raw idea?" and get an unambiguous answer from the data.
2. **Every interpretation round is retained**, not just the latest. The refine loop
   (§14) is inherently multi-round, and "we interpreted it three times and the Founder
   corrected us twice" is exactly the honest record DEC-013 asks for. A design where
   round 3 overwrites round 2 loses the thing the Founder asked to preserve.
3. **The approved brief must be identifiable as a specific interpretation version** —
   ideally a *pointer to* the version approved, not a re-typed copy of it. A copy can
   drift from what was actually approved; a pointer cannot. If a copy is taken for
   performance or simplicity, it must be provably identical at the moment of approval.
4. **Downstream agents read the approved brief.** Not the raw idea, not the latest
   interpretation. DEC-013 is explicit: *"The Founder-approved brief — not the raw idea —
   is the authoritative input to every downstream agent."* This has a concrete
   consequence CTO must handle: `review_transcripts.py` (lines ~203–206, 261–264) and
   `launch_developer_session.py` currently feed **`business_goal`** — the raw idea — into
   agent transcripts. Under DEC-013 that is now the *wrong field* for any task that has
   an approved brief. **This is the single most likely place for DEC-013 to be quietly
   violated in implementation**, because those call sites work today and nothing about
   them looks wrong.
5. **Nothing is deleted.** A superseded interpretation is superseded, not removed —
   the same discipline this file itself is following.

### 13.4 Recommended shape (requirements-level preference; CTO decides)

**A versioned brief record — a new table, not new flat columns.** Roughly:
`task_id`, `version`, `kind` (raw / interpreted / approved), `content`, `author`,
`created_at`, and a link to the approval round that decided it.

Reasoning, and the honest alternative:

- **Flat columns on `tasks`** (`interpreted_brief`, `approved_brief`) are simpler and I
  considered them seriously. They fail requirement 13.3.2: a flat column holds only the
  latest, so round 3 destroys round 2. The refine loop makes that a certainty, not an
  edge case.
- **A versioned table** matches a pattern this project already has and already
  understands: `task_status_history` is exactly "an append-only record of how this task
  changed over time." The refine loop *is* that shape. Reusing a known pattern over
  inventing one is this project's consistent preference.
- **Reusing `requirements` / `acceptance_criteria`** is rejected outright: those are
  Product's normal downstream outputs, and overloading them would conflate "what we
  think you meant" with "the spec we built from it."

**What I am not deciding:** table name, column types, whether it is one table or two,
migration mechanics, and whether `business_goal` stays the raw-idea home or is copied
into the new record at intake. All CTO's.

---

## 14. What the Founder can do to an interpretation

DEC-013: the Founder must be able to *"review, correct, refine, or brainstorm further."*
Four verbs. The important finding is that they need **two mechanisms, not four**.

### 14.1 The four actions, concretely

| Founder action | What it means | Produces a new round? | Spends money? |
|---|---|---|---|
| **Accept** | "Yes, that's what I meant." Interpretation vN becomes the approved brief. | No | **No** — approving is free |
| **Correct** | "No — I meant X, not Y." Founder supplies the correction in their own words. | **Yes** → vN+1 | **Yes** |
| **Refine** | "Right direction, go deeper on the second approach." No contradiction, more depth. | **Yes** → vN+1 | **Yes** |
| **Brainstorm further** | "Give me some different options." | **Yes** → vN+1 | **Yes** |
| **Park** | "This isn't right at all — leave it." Task returns to `BACKLOG`, nothing downstream starts. | No | **No** |

### 14.2 Correct, refine and brainstorm are one mechanism — build one

They differ only in the Founder's **intent**, expressed in their own free text. All
three do the identical thing: take interpretation vN plus the Founder's words, produce
interpretation vN+1, spend one model invocation.

**Requirement: one send-back code path, not three.** Design may present them as
distinctly-labelled affordances if that helps the Founder say what they mean — three
labels over one mechanism is fine and probably good. Three implementations is scope
creep, three times the test surface, and three places for the round counter to be wrong.

### 14.3 Park must exist

The Founder must be able to **walk away at the gate** — approve nothing, spend nothing
more, and leave the idea where it was. Without it the approval gate is a trap: the only
exits are "approve something I don't agree with" or "keep paying for rounds." Park
returns the task to `BACKLOG` with every interpretation round retained (§13.3.5).

### 14.4 Every send-back spends money again — say so on the control

Stated plainly because the Founder asked for it plainly: **a correction is not free.**
Each round is a fresh model invocation at fresh cost. The control that triggers a new
round must say so **on the control itself**, not in a paragraph above it. A Founder who
has clicked "refine" four times has spent four times.

### 14.5 Rounds are numbered, visible, and warned — not capped

- Every interpretation carries its **round number**, visible to the Founder ("Round 3").
- The Founder can always see **how many rounds this idea has already cost**.
- At **round 4 and beyond**, the product should say something honest: *"You've refined
  this three times. The next round costs again — it may be cheaper to approve this and
  correct it downstream, or park it."*

**Not a hard block.** It is the Founder's money and the Founder's idea; a product that
refuses to let them think again is worse than one that lets them spend. But an unbounded
loop that never mentions its own cost, on a screen that already has no estimate and no
stop button (§18), is exactly the kind of silent mechanism this project keeps catching
late. Numbered and warned, not forbidden.

---

## 15. Where approval lives — reuse `approvals`, one row per round

**Recommendation: reuse the existing `approvals` table and the existing
`/api/approvals/<id>/decide` route, unchanged — with one approval row per
interpretation round.** No new approval machinery, no new decision states, no new
auth code.

### 15.1 Why the existing machinery fits

I checked the real schema and the real function rather than assuming. The fit is
better than I expected:

- **The `approvals` columns already describe an interpretation.** `request`, `why`,
  `recommendation`, `alternatives_considered`, `expected_cost`, `risks`,
  `consequence_if_not_approved` — that is close to a field-by-field match for §11.2's
  six-part brief. `recommendation` holds the recommended direction;
  `alternatives_considered` holds the approaches explored. This table was built for
  precisely this shape of decision.
- **`tasks.status` already has `FOUNDER_APPROVAL`**, and — usefully — `is_stuck()`
  already **excludes** it (`ops/db/derived_state.py`). A task parked awaiting the
  Founder's review of an interpretation will therefore **not** be flagged as stuck.
  That is the correct behaviour and it costs nothing to get. (Contrast `BACKLOG`, which
  is *not* excluded — the unresolved defect from §3, still unresolved, still CTO's.)
- **`decide_approval()` is already atomic and double-submit-safe.** Its conditional
  `UPDATE ... WHERE decision IN (...)` means a second click affects zero rows instead
  of overwriting a decision. That is exactly the property you want on a gate where each
  decision leads to spending.
- **`discuss` already exists** as a non-terminal decision (`approve`/`reject` may still
  follow it) — a natural fit for "send it back for another round."

### 15.2 The one real mismatch, and how one row per round resolves it

`decide_approval()` is deliberately **single-shot**: `approve` and `reject` are terminal,
and `discuss → discuss` is *intentionally absent* — the code comments it as "already-flagged
is a no-op, not a new state."

DEC-013 needs the opposite: a gate the Founder can send back **repeatedly**.

Resolved not by changing that function but by **not asking it to do something it was
built to refuse**: each interpretation round gets its **own approval row**, decided
exactly once.

- Round N produces interpretation vN **and one new `approvals` row**.
- The Founder decides that row once: `approve` → proceed; send-back (`discuss` or
  `reject`, CTO's call which) → that row is closed **forever**.
- A send-back triggers round N+1, which creates interpretation vN+1 and a **new**
  approval row.

This costs zero changes to `decide_approval()`, zero changes to the `CHECK` constraint,
zero changes to the route, zero new auth — and it delivers §13.3.2's round history for
free, because the `approvals` table becomes the round-by-round record of what was
proposed and what the Founder said each time. Reusing existing machinery has been this
project's consistent preference; here it is also simply the better design.

### 15.3 The one genuine gap CTO must close

**There is nowhere to put the Founder's correction text.** `decide_approval(conn,
approval_id, decision)` takes a decision and nothing else, and the route accepts nothing
else. But §14's correct / refine / brainstorm are *worthless without the Founder's
words* — "send this back" with no explanation produces round N+1 identical to round N,
at full cost.

**Product requirement** (mechanism is CTO's): the Founder's correction text must be
(a) captured at the moment of decision, (b) persisted verbatim and attributed to the
Founder, and (c) supplied as an input to the next round. It must **not** be routed
around the existing decide path in a way that creates a second, unreviewed way to
decide an approval.

### 15.4 What approval must and must not trigger

- Approving writes the approved brief (§13) and moves the task out of `FOUNDER_APPROVAL`.
- **Approval dispatches at most the next single stage.** It must not start a chain that
  runs Design → CTO → Red Team → Development unattended.

  This resolves a real tension I am naming rather than papering over: DEC-013 says
  *"only after the Founder approves the interpreted brief does the downstream company
  workflow begin,"* which reads as approve-then-dispatch. DEC-012 freezes automatic
  dispatch of new agent types behind TASK-023's security lock. My reading, and the one
  I recommend: **a Founder clicking approve is attended human action** — the same
  argument Design §0 made for Start, and the same category as Ask-Agent and Meetings,
  which already spend on a click. One dispatch, of one stage, on one deliberate click,
  is not automation. **A cascade would be**, and it stays frozen. If CTO reads DEC-012
  more strictly than I do, that disagreement goes to the Founder — it is not something
  either of us should resolve quietly.

---

## 16. `prompt-master` and the "brainstorming skill" — tested, not assumed

I was asked to invoke it rather than reason about it. I did. **The answer has three
layers and the last one is the one that matters.**

### 16.1 It exists and it fires — in a session like this one

Invoking `prompt-master` **succeeded**. It loaded from:

`/root/.claude/skills/synced/b656f309-9315-4bd1-bd01-0465317d0b42_19c0a3da-256e-4147-be5c-88c54c8638db/prompt-master`

So the premise behind the concern is half wrong, and it is worth being precise about
which half. The repo genuinely ships **no `.claude/skills/` directory at all** — that
part is correct. But the skill is not repo-provided; it is a **user-account-synced**
skill. It travels with the Founder's Claude account, **not with the codebase**. A fresh
clone, a different account, or CI has no `prompt-master`. It is an **undeclared external
dependency** of a documented role behaviour.

### 16.2 It cannot fire on the path that actually runs agents — the finding

`ops/control-center/agent_runtime.py` line 304, in `_run_claude()`:

```python
"--tools", "",                 # zero built-in tools — see module docstring
```

**Every agent dispatched through the Control Center runtime is launched with zero
built-in tools.** No `Skill` tool. Therefore **no skill — `prompt-master` or any
other — can be invoked by a dispatched agent**, regardless of what its definition
grants.

Eight agent definitions carry a `Skill` grant in their frontmatter
(`code-review`, `cto`, `design`, `developer`, `devops`, `product`, `qa`, `security` —
`.claude/agents/*.md` line 4). On the runtime path, **all eight are inert.**

This is the third "documented but inert" mechanism in this project's history — after
TASK-017's hook that never fired and the defence-in-depth layer that could not fire
inside the sandbox. I was asked not to add a fourth. **It was already here**, and
DEC-013 would have shipped a refinement stage specified to use a skill it structurally
cannot reach. Found before build rather than in QA.

**To be explicit: `--tools ""` is a deliberate security control, not a bug, and I am
not recommending it be relaxed.** Making a skill reachable by widening the tool grant
on the dispatch path would trade a real security property for a convenience. The
requirement can be met without it (§16.4).

### 16.3 Even where it fires, it is the wrong tool for this job

Read in full, `prompt-master` is a **prompt engineer**, not a brief writer:

- Its identity: *"Take the rough idea, identify the target AI tool… output a single
  production-ready prompt optimized for that specific tool."*
- A hard rule: *"Do not output a prompt without first confirming the target tool — ask
  if ambiguous."*
- Its output format: *"A single copyable prompt block ready to paste into the target
  tool."*

DEC-013's refinement stage must produce a **brief for a human Founder to review** —
problem, outcome, assumptions, approaches, recommendation. `prompt-master` produces a
**prompt for a machine to consume**. Different artifact, different audience.

This is not a discovery so much as a confirmation: the repo's own registry entry,
`ops/skills/product/prompt-master.md`, already records the limitation verbatim —
*"Produces a prompt for someone/something else to run — it does not execute the task
itself."* The registry was honest; `product.md` line 10 overstated it.

**So `.claude/agents/product.md` line 10 — *"You use the `prompt-master` skill when
turning a rough idea into a precise brief"* — is wrong on three independent counts:**
it is not repo-provided, it cannot be invoked on the runtime path, and it does not
produce briefs. Correcting that line is a small documentation fix, outside this
milestone's scope, and I am flagging it rather than doing it.

### 16.4 There is no brainstorming skill — so DEC-013's wording needs restating

DEC-013 requires the stage to *"use the brainstorming skill where useful."* **No such
skill exists anywhere reachable.** The complete synced set is: `docx`, `import-memory`,
`morning`, `pdf`, `pptx`, `prompt-master`, `skill-creator`, `xlsx`. The repo's own
registry (`ops/skills/`) lists thirteen skills, none of them brainstorming. Nothing in
the session roster is one either.

**Requirement — the mechanism DEC-013 needs, restated so it can actually be built:**

> The refinement stage has **no skill dependency**. Its divergent thinking is a
> **behavioural** requirement met by the instruction transcript, not a tooling one.

Which is to say: §11.2's obligations (2–4 genuinely distinct approaches, a reasoned
recommendation, ≤3 material questions, explicit assumptions) are enforced by **what the
stage is told to produce and what QA checks it produced** — using the same
transcript-driven mechanism (`review_transcripts.py`) that every other agent stage in
this company already uses successfully. That mechanism demonstrably works here. A skill
demonstrably does not.

**This is a substantive amendment to DEC-013's wording** and I am flagging it as one
rather than quietly satisfying it: the intent ("real divergent thinking before
requirements lock") is fully preserved and fully buildable; only the named mechanism is
unavailable. The Founder should see that correction. It also **answers**, rather than
defers, the verification question DEC-013 assigned to what remains of TASK-025.

---

## 17. New scope exclusions — this milestone just grew, so guard it

§6's exclusions **all still stand** (no UI edit, no delete, no CRUD surface, no
attachments, no multi-project, no auto-start on submit, no retro-fix of existing rows).
DEC-013 adds these:

**The refinement stage is not:**

1. **Not Design.** No screens, no layout, no visual concepts, no wireframes. Design runs
   after approval, as it always has.
2. **Not architecture.** No schema, no routes, no data model, no technology or library
   choice. If an interpreted brief names a technology, that is a scope violation and QA
   should fail it.
3. **Not a feasibility study.** It does not rule on whether the thing can be built, or
   how hard it would be. "Explore a few reasonable approaches" means **product**
   approaches — *what to build* — never implementation strategies.
4. **Not a cost or effort estimate.** No dollar figures, no hour figures, no
   t-shirt sizes. This company has **zero** cost data (0 of 13 `agent_runs` carry
   `cost_usd`) and a documented record of estimates being wrong by an order of
   magnitude — DEC-012's own "45–70 minutes" for remaining gates was immediately
   followed by a QA FAIL with four blocking defects, revised to 3–8 hours. Any estimate
   from this stage would be fabricated.
5. **Not the decision-maker.** It recommends exactly one direction and never chooses.
   The Founder chooses, by approving.

**And the milestone as a whole excludes:**

6. **No auto-approval, in any form.** An interpretation never approves itself, never
   approves by timeout, never approves because nobody looked at it for N days. **Silence
   is not consent.** This is the most dangerous shortcut available in this design and it
   is closed explicitly.
7. **No cascade on approval.** Approving dispatches at most the next single stage
   (§15.4). No chain, no unattended run through Design → CTO → Red Team → Development.
8. **No editing the raw idea.** The Founder corrects the *interpretation*, never what
   they originally typed. The raw idea is immutable — that immutability is precisely
   what makes the three-artifact comparison worth anything (§13.1).
9. **No skill dependency** (§16.4). Nothing in this milestone may be specified as
   requiring `prompt-master`, a brainstorming skill, or any other skill to function.
10. **No relaxing `--tools ""`** in `agent_runtime.py` to make a skill reachable. That
    is a security control; trading it for convenience is out of scope and would need
    Security and Red Team, not a Product brief.
11. **No retro-interpretation.** The 24 existing tasks do not get interpreted briefs.
12. **No hard cap on refine rounds** — numbered, visible and warned (§14.5), not blocked.
13. **No multi-Founder review, no comments, no threads, no @-mentions.** One Founder
    (§2). The approval gate is a decision, not a discussion forum.
14. Design's Concept B receipt block and Concept C inline capture remain **documented and
    rejected**, unchanged by DEC-013.

---

## 18. Honest disclosure — what the Founder must be told, and when

The refinement stage **spends real model money before any building begins**, on a screen
that (per Design §4) already has to admit it cannot estimate cost and has no stop button.
DEC-013 names this explicitly as something that "must be disclosed honestly."

### 18.1 Before the first click — on the Start control

All six, before the Founder can trigger round 1:

1. **What this actually starts.** It starts *understanding*, not building. No design, no
   architecture, no code results from this click. **Design's mockup label
   `Start work on TASK-025…` is now wrong** and must change — it promises building. The
   wording is Design's; the requirement is that the label **must not promise work that
   this click does not start.**
2. **It spends real money, before anything is built.** Unchanged in force by anything
   below.
3. **There is no cost estimate** — Design's finding stands: 0 of 13 `agent_runs` carry a
   `cost_usd` value, so any figure would be fabricated.
4. **But there is an honest ceiling — and it should be shown.** See §18.2. This is new,
   and it materially improves Design's disclosure.
5. **There is no stop button.** A dispatched stage runs to completion.
6. **This is the first spend of possibly several.** Each correction, refine or
   brainstorm round spends again (§14.4). **The Founder must learn this before round 1**,
   not when they click "refine" for the first time — otherwise the product has taught
   them that starting costs once, and they discover otherwise by being charged.

### 18.2 A finding that improves the disclosure: the ceiling is knowable

Design concluded the product can say nothing honest about cost. That is true of the
*expected* cost. It is **not** true of the *maximum*.

`ops/control-center/agent_runtime.py` sets `MAX_BUDGET_USD = "0.50"` and passes it as
`--max-budget-usd` on **every** invocation. That is a hard, enforced, verifiable per-
invocation ceiling.

So the disclosure can be materially better than "we can't tell you anything":

> *"We can't tell you what this will cost — no run recorded so far carries a cost
> figure. We can tell you it cannot exceed **$0.50** for this round, because the runtime
> enforces that limit. Each further round you ask for costs again, under the same limit."*

That is honest, useful, and verifiable — and it turns an unbounded-feeling spend into a
bounded one, which is the single most reassuring true thing available on that screen.

**Two conditions on using the number, which must hold or the number must not be shown:**
(a) it is only valid if the refinement stage runs as **one** invocation on the
`agent_runtime._run_claude()` path — if CTO implements it as several invocations, or on
a different path, the disclosed ceiling must be recomputed from the real mechanism;
(b) it is a **per-round** ceiling, so with rounds the running total grows and the
Founder must be able to see how many rounds they have paid for (§14.5). **The disclosed
figure must be derived from the mechanism CTO actually builds, never hard-coded from
this brief.** A stale $0.50 on screen after the mechanism changed would be exactly the
kind of confidently-wrong statement this project keeps catching.

### 18.3 At the approval gate — every round

- **Which round this is** ("Round 2 of your refinements").
- **Approving spends nothing further at this gate.**
- **Sending it back spends again**, said on the control that does it (§14.4).
- **Parking spends nothing** and keeps everything (§14.3).

### 18.4 The standing argument

Every round of this makes the case for finishing task-scoped cost attribution
(`agent_runs.cost_usd`) more concrete. Not this milestone's job. Worth CTO seeing stated
plainly, again.

---

## 19. Additional acceptance criteria (AC-12 – AC-24)

AC-1 – AC-11 in §5 stand unchanged. Written in the shape QA verifies.

**The refinement stage**

12. Pressing Start on a `BACKLOG` idea runs the refinement stage and **dispatches no
    other agent**. QA verifies no Design, CTO, Red Team or Developer invocation occurs.
13. The stage produces an interpreted brief containing **all six** parts of §11.2. A
    brief missing any one is a FAIL.
14. The interpreted brief contains **between 2 and 4** distinct approaches, and exactly
    **one** named recommendation with reasoning that references the alternatives.
15. The interpreted brief contains **at most 3** clarifying questions. Zero is a pass.
    Each question present must pass the §12.1 divergence test — QA applies it by writing
    two plausible answers and checking whether the brief would differ.
16. The interpreted brief is **approvable with no questions answered** — QA approves one
    without answering anything and gets a usable brief downstream.
17. The interpreted brief contains **no** screens, schema, routes, technology names,
    dollar figures or time estimates (§17.1–17.4).

**The three artifacts**

18. After any number of refinement rounds, the Founder can see the **exact original
    text** they typed, unmodified, in the product, alongside the current interpretation.
    QA verifies byte-for-byte against what was submitted.
19. `business_goal` is **never** modified after intake. QA verifies across a full
    multi-round refine-and-approve cycle.
20. Every interpretation round is retrievable after later rounds exist — round 1 is
    still readable after round 3 (§13.3.2).
21. After approval, downstream agent transcripts are built from the **approved brief**,
    not the raw idea (§13.3.4) — QA inspects a real transcript.

**The approval gate**

22. An interpretation is **never** approved without an explicit Founder action. QA
    verifies no timeout, no default, no auto-approve path exists.
23. A send-back with correction text produces a **new** interpretation round that
    demonstrably reflects that text, and the prior round is retained.
24. Deciding the same approval row twice affects **zero rows** the second time (the
    existing `decide_approval()` guarantee) and does not trigger a second paid round.

---

## 20. Open questions for CTO  (supersedes §10)

Carried forward from §10, all still open:

1. **`is_stuck()` and `BACKLOG`** — still unresolved, still must not ship undecided.
   (Note: `FOUNDER_APPROVAL` is already excluded, so the new approval gate is fine;
   `BACKLOG` is the one that bites.)
2. **`project_id` on intake** — `1` or `NULL`. TASK-024 and TASK-025 both currently have
   `NULL`, so the inconsistency is still live.
3. **`cmd_task_create()`'s refactor shape** — it is still the only write path in
   `opsdb.py` not in the plain-callable-function form (`record_task_status()`,
   `decide_approval()`, `record_review_result()` all are).
4. **Per-field caps** — Design §6 recommends 160 / 4,000 / allowlist with real data
   behind them; CTO confirms or overrides.

Added by DEC-013:

5. **The brief-storage shape** — §13.4 recommends a versioned record over flat columns,
   with reasoning. CTO decides. The requirements in §13.1–13.3 are not negotiable; the
   shape is.
6. **Where the Founder's correction text is captured and persisted** — §15.3. The one
   real gap in reusing the approvals machinery.
7. **Which decision value means "send it back"** — `discuss` or `reject`. Both are
   available; `discuss` reads more accurately, `reject` is more clearly terminal for
   that row. Either satisfies §15.2.
8. **Switching downstream transcripts to the approved brief** — `review_transcripts.py`
   and `launch_developer_session.py` currently read `business_goal`. §13.3.4. **The most
   likely place for DEC-013 to be silently violated.**
9. **Whether approval dispatches the next stage directly or via the automation poller** —
   with §15.4's constraint that it is one stage, not a cascade, and Design's constraint
   that it stays human-triggered and attended.
10. **The real cost ceiling for one refinement round** — §18.2. If it is not one
    `agent_runtime` invocation, the $0.50 figure must not be shown.

Flagged, outside this milestone, needing an owner:

11. **Eight agents carry an inert `Skill` grant** (§16.2). Either the grants are
    meaningless on the runtime path and the definitions should say so, or the runtime is
    stricter than intended. Not this milestone's to fix; it should not stay undocumented.
12. **`.claude/agents/product.md` line 10 is wrong** (§16.3) — a documentation fix.
13. **`ops/db/ops.db` is an empty stray file** (0 tables) sitting next to the real
    `ops/db/operations.sqlite3`. Harmless today, an obvious footgun for anyone — human or
    agent — who opens the plausibly-named one. Noticed while querying; not mine to delete.
