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
