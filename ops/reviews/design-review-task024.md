# Design Review — TASK-024: Founder Idea Intake

Author: Design agent · Date: 2026-09-01 · Status: for CTO
Input: `ops/reviews/product-task024-brief.md` (approved), plus a **Founder scope
correction issued mid-design** (§0).

Mockups: `ops/mockups/task024/` — `Main.dc.html` (Concept A, recommended),
`StartFlow.dc.html` (the Start action, every state), `Receipt.dc.html`
(Concept B), `Inline.dc.html` (Concept C), `Closeups.dc.html`.
Published as one canvas: https://claude.ai/code/artifact/6eb8e58e-4ef8-4201-8f7c-e92aad45c612

All content is real, queried from the live database this session: TASK-025
(the one genuine `BACKLOG` row, with its actual title, `business_goal` and
19:42 UTC creation), TASK-023/024 on Active Work, the real `priority`
distribution, and the real title/`business_goal` length statistics behind
the caps in §6. Nothing here is invented data.

---

## 0. Scope correction — where the change came from

Product's brief scoped out any start-the-pipeline control (§6: "No start
button… Status transitions stay exactly as they are today"), on the reasoning
that a task leaves `BACKLOG` the way every other transition happens — on the
command line, by the orchestrator.

**The Founder reviewed that and rejected it**, mid-design: an intake form that
can only save leaves them able to write an idea down and still unable to start
anything from the app, which is the exact gap this milestone exists to close.
A form that only saves is a suggestion box, not a front door.

The Founder's decision, in substance: **there must be a way for the Founder to
start work on a saved idea, from the UI.** This was not Design's call and not
Product's — recording it here so the paper trail shows its origin. Everything
else in Product's brief stands unchanged, including the part of it this
correction *does not* touch: **auto-start on submit remains out of scope.**
Product's argument against auto-start was never "starting is bad," it was that
submitting would silently become the first automatic dispatch of a new agent
type, reopening a sequencing decision the Founder has frozen three times
(DEC-008, DEC-010, DEC-012). A Founder clicking a start control is attended
human action — the same kind as Ask-Agent and Meetings, which already spend
money on a click. That distinction survives the correction intact and is the
load-bearing constraint on everything below.

The Save half of the design was already drafted against the narrower scope and
was revised, not discarded.

## 1. The central problem, restated

Two adjacent actions with wildly different consequences:

| | Save | Start |
|---|---|---|
| writes | one `tasks` row at `BACKLOG` + one history row | a status transition, and a dispatched agent |
| runs | nothing | Product, then the whole pipeline behind it |
| costs | $0.00 | real money, amount unknown (§4) |
| reversible | walk away and think | no stop button |

The design's whole job is making those two unmistakably different, in a UI
where **the existing spend-triggering controls are barely marked at all.** I
checked, rather than assuming: Ask-Agent (`generate_agents.py`
`render_ask_agent_section`) is a plain text input and an accent "Send" button
with *no* mention of cost anywhere. The Meetings form
(`generate_meetings.py`) gets closest with one 10.5px muted line — "this runs
for real and can take up to ~2 minutes" — which discloses *time*, not money.
So "at least as clear as the existing controls" is a very low bar, and Start
should clear it by a wide margin: it starts an eight-stage pipeline, not one
question.

## 2. Recommendation

**Concept A (`Main.dc.html`) — Save on the Ideas page, Start on the idea's own
Task Detail page.** Build it with `StartFlow.dc.html`'s two-step Start.

The reason is structural, not cosmetic: **the compose surface can never spend
money, because the expensive control does not exist on it.** Not greyed out,
not confirm-guarded — absent. A Founder who has just clicked a filled amber
"Save to Backlog" button cannot, by a reflex second click a moment later, land
on anything that dispatches an agent. Getting from "saved" to "started"
requires a deliberate navigation, and the destination page spends its whole
area telling you what starting does before offering to do it.

Everything else follows from that separation:

- **The Ideas page carries a standing ledger**, "In Backlog — saved, not
  started," directly under the form. A one-shot confirmation banner is read
  once and forgotten; a Founder wondering three days later why nothing is
  happening needs a *place* that still says "not started," not a notification
  they missed. The ledger is that place, and the list shrinking when a task
  starts is itself a signal.
- **The ledger doubles as the first-run empty state** — "No ideas saved yet.
  Anything you save above appears here and stays here until you start it."
- **`business_goal` renders back on Task Detail** (AC-5) in a panel titled
  "The idea — as you wrote it," escaped, `white-space: pre-wrap`, no Markdown
  or rich-text path anywhere (Product §8.3).

The cost of Concept A is one extra navigation between having an idea and
starting it. Given what that click buys — the impossibility of accidentally
spending money from a text box — it is the cheapest insurance in this design.

### Where Start lives, decided

**Task Detail only, for this milestone.** Not on the intake confirmation
(that is Concept B's error), not on Active Work rows (Concept C's), not in
several places at once. One control, one page, one URL — which also gives
Security and QA exactly one surface to reason about for the first route in
this product that dispatches an agent on a Founder's click. If the Founder
later finds the extra hop tiresome, adding a Start affordance to the Ideas
ledger row is a small additive change; removing one that shipped everywhere
is not.

## 3. The Start action — the shape (`StartFlow.dc.html`)

Four states, all server-rendered (this product runs no client JS and uses no
browser `confirm()`):

1. **Resting** — a panel on Task Detail, accent-bordered, headed "Start work
   on this idea" with a `SPENDS MONEY` pill, stating in full what starting
   does. Its control is **outlined, not filled**, and ends in an ellipsis:
   `Start work on TASK-025…`. It arms; it dispatches nothing.
2. **Confirm** — a screen whose entire body is the consequence, repeating the
   idea's title and text back so "which idea am I about to spend on" is never
   a question. The **filled** amber button appears here and only here, and its
   label names the agent and the spend: *"Yes — start Product on TASK-025 and
   spend."* Beside it: *"Cancel — leave it in the Backlog."*
3. **Started** — the mirror of the save confirmation, and just as emphatic:
   "Started — Product is working on TASK-025 now," the real transition
   (`BACKLOG → PLANNING`, owner Product), the dispatch timestamp, and two
   links that answer *where do I watch this* — Active Work, and Costs. **The
   Start control is removed from the page entirely**, so a second dispatch is
   impossible rather than merely discouraged — the same in-progress lock the
   Ask-Agent panel already implements ("a request is already in progress"),
   applied to a far more expensive action.
4. **Failed** — "Not started. TASK-025 is still in the Backlog." No agent was
   started, nothing was spent, the status is unchanged, try again. **The word
   "started" never appears unless a status change was actually written.**
   TASK-023 shipped a sandbox that reported success over a no-op and QA caught
   it; the Start path is the same shape of risk and does not get to repeat it.

### Design decision: Save and Start are separated by fill, step count and
### label — not by colour

The palette is closed and fully assigned: amber = active/primary, green =
passed, red = danger & open risk, blue = agent waiting, violet = actor
identity, gray = neutral. Two alternatives were considered and rejected in
`StartFlow.dc.html` §1:

- **Paint Start red** — rejected. Red means danger and open risk everywhere
  else in this product. Starting work is the thing the Founder is *supposed*
  to do; colouring it as a hazard misrepresents it and would train them to
  ignore red.
- **Invent a sixth colour for "expensive"** — rejected. Every prior design
  review in this project extended an existing convention rather than adding a
  family; a six-hue palette where the sixth means "costs money" is a new
  system for one button.

Instead: Save keeps the filled-amber primary (it is genuinely safe, and earns
one click). Start's arming control is **unfilled**, which in this UI has never
been the "go". The filled amber button appears exactly once in the Start flow,
on a screen the Founder cannot reach without passing the disclosure, wearing a
label that spells out what it does. Reinforced by a `SPENDS MONEY` pill —
a marker, in an existing colour, that no other control in the product carries.

## 4. The honest cost disclosure — a finding

The Start disclosure should tell the Founder what this will cost. **It cannot,
and it must say so.** Queried this session: `agent_runs` holds 13 rows and
**0 of them carry a `cost_usd` value.** There is no historical figure to
average, so any dollar estimate on that screen would be fabricated.

So the disclosure reads: *"How much? This product cannot tell you yet — none
of the 13 agent runs recorded so far carries a cost figure, so there is no
honest estimate to show. Watch it on Costs as it runs."* That is worse news
than a number and it is the only truthful thing available. It is also a
standing argument for finishing task-scoped cost attribution — not this
milestone's job, but worth CTO seeing stated plainly.

The disclosure also names the thing nobody has asked about: **there is no stop
button.** A dispatched stage runs to completion. The Founder should learn that
before the first click, not after.

## 5. The two alternates, honestly

### Concept B — `Receipt.dc.html`: one surface, staged

Save leads to a full-page receipt that *counts the things that did not
happen*: 1 task row, 1 history entry, **0 agents dispatched, 0 model calls,
$0.00 spent, 0 other tasks changed**. Then, on the same surface, it offers
Start.

**Its genuine strength**: that counted-nothings block is the single clearest
moment in any of the three concepts, and the shortest path from idea to
running work. I would like it to win.

**Why it doesn't**: it puts the free button and the expensive button on one
screen seconds apart. Save lands at the top of the page, and the Start arm
sits a short scroll below in the same visual language — exactly where a
reflex second click goes. And when the Founder navigates away, *nothing
anywhere still says "this is parked"*: no ledger, no list, no standing state.
A receipt is a notification, and notifications are read once.

**Recommendation: don't build the page, do steal the block.** The
counted-nothings idea is worth keeping as a possible later addition to
Concept A's save confirmation — but it is an enhancement, not a requirement,
and it is *not* part of what I am asking CTO to architect. Documented, not
silently dropped.

### Concept C — `Inline.dc.html`: capture and start from Active Work

No new page. A capture strip at the top of Active Work; saved ideas fall into
a permanently receded "Not started" zone below the running work, each row
carrying its own `Start work…` control.

**Its genuine strength**: the only concept where a parked idea is permanently
part of the company's status picture rather than a thing on its own page, and
where starting happens exactly where the Founder triages. It also forces the
`is_stuck()` question into the open, which is a virtue.

**Why it doesn't win**: three separate problems, any one of which would be
enough. It bolts a write form onto a page whose own headline today reads
*"Active Work — read-only."* It repeats a money-spending control once per
row, so the accidental-click surface grows with the backlog — the opposite of
what this feature needs. And it asks one screen to be a monitor, an authoring
form and a dispatch console simultaneously, which is how the dashboard stops
being scannable.

**One piece of it is worth keeping regardless of concept**: the receded
treatment for a `BACKLOG` row on Active Work — hollow gray dot, no gate line,
"Not started," and *no stuck badge*. See §8.

## 6. Validation, errors, and per-field caps (`Closeups.dc.html` §2–3)

**The rule that matters most: every rejection re-renders the form with the
Founder's typed text still in it.** Losing 300 words of idea to a validation
error is the worst thing this form can do and it is entirely avoidable.
Server-side validation is authoritative; browser `required`/`maxlength` are
convenience only.

- Empty title → *"Give the idea a title — a short name is all it needs."*
- Empty idea → *"Tell us the idea. One or two sentences is enough — Product
  takes it from there."*
- Whitespace-only counts as empty (strip before checking).
- Over cap → names the real count and the real limit: *"That title is 214
  characters. The limit is 160 — shorten it, or move the detail into the idea
  below."* Same shape as the existing ask-message/topic rejections.
- Save failure → *"Not saved. Nothing was written."* — never the word "saved"
  without a row id.

**Caps, recommended with the real numbers behind them:**

| Field | Real avg | Real max | **Cap** | Reasoning |
|---|---|---|---|---|
| `title` | 68 | **146** | **160** | The longest title this company actually uses is 146 (TASK-018). A tidier-looking 120 would have rejected a title already in the database. 160 clears the observed max with room and still fits the one-line Active Work card. |
| `business_goal` | 412 | 929 | **4,000** | Reuses the existing `MAX_DECISION_CHARS` value rather than inventing a new magic number — ~600 words, over 4× the longest idea anyone has written here. Deliberately half of `MAX_ASK_MESSAGE_CHARS` (8,000): an ask message is transient, this text is stored forever, re-rendered on a dashboard card, and concatenated into every agent transcript for the task. |
| `priority` | — | — | **allowlist** | Exactly one of `high`/`medium`/`low`. Anything else is **rejected, not coerced to medium** — a value that isn't one of the three did not come from this form, and silently accepting it hides that. |

160 + 4,000 chars ≈ 4 KB, far under the 64 KiB `MAX_BODY_BYTES` — so these
caps, not the transport limit, are the real bound on one submission, which is
what Product §8.4 asked for.

**Double-submit**: Save is cheap, so a duplicate row is a duplicate row, not
money — POST→redirect→GET (the pattern the existing routes already use) is
sufficient, which means **the confirmation must survive a redirect and name
the new task id** (e.g. `/ideas.html?saved=26`). Mechanism is CTO's; the
design requirement is that the id appears. Start is neither cheap nor
idempotent and gets the stricter guard in §3.

## 7. Nav placement (`Closeups.dc.html` §1)

**"Ideas", second, between Overview and Active Work.** The bar reads
left-to-right as the company's own lifecycle: Overview (how are we) → Ideas
(queued, not started) → Active Work (running) → Pipeline. It is a noun, like
all thirteen existing items — "New Idea" would be the only imperative in the
bar, and it describes the form rather than the page, which also holds saved
ideas. Rejected: "New Idea" first (demotes Overview, the intended landing
page, for a form used occasionally) and "Intake"/"Backlog" last (process
vocabulary for a one-person company; buries the only route that creates work
behind twelve read-only registers).

## 8. The two findings Product surfaced

**`is_stuck()` and `BACKLOG` — Design position, CTO's code call.** A parked
idea must not be presented as a failure. Recommendation: **exclude `BACKLOG`
from `task_is_stuck()`**, the same way `BLOCKED` and `FOUNDER_APPROVAL` are
excluded and for the same reason its own docstring gives — the status already
has a better-labelled treatment of its own. The age stays visible and honest
("In Backlog 4d · waiting for you to start it"); it is only the *failure
framing* that goes. Also, a `BACKLOG` row on Active Work should read "Not
started" with a hollow gray dot rather than today's "Gate: — · not yet on the
gate ladder", which is accurate but obscure. This satisfies AC-11.

**`priority` free text.** Intake writes only the three clean values;
retro-fixing the 24 existing rows stays out of scope. But wherever priority
renders, an unrecognised legacy value (`"P0 - Phase 1 Foundation"`) must
render **verbatim in the dimmest gray** — never mapped to a known colour,
never hidden, never crashed on; `NULL` renders as an em dash. Pill colours:
`high` takes the accent, `medium`/`low` are gray. Priority is a hint, not a
status, and every colour in this palette already means a status.

## 9. What CTO needs to decide

Carried forward from Product's §10, plus what the scope correction adds:

1. **`is_stuck()` and `BACKLOG`** — §8. Must not ship undecided.
2. **`project_id` on intake** — unchanged from Product's open question; the
   mockups render `1` ("AI-Pipeline Ops Bootstrap") because Task Detail and
   Active Work both have a Project field that otherwise shows an em dash.
3. **`cmd_task_create()`'s refactor shape** — unchanged.
4. **Caps** — §6 recommends 160 / 4,000 / allowlist with reasoning; CTO
   confirms or overrides.
5. **New: what the Start route actually dispatches, and its guard.** Design
   specifies the *behaviour* — one deliberate human click, two steps,
   idempotent against double-dispatch, honest on failure, control removed once
   running. The route, the dispatch mechanism, and how the "already running"
   check is made are CTO's. Two things Design will flag as non-negotiable
   from the screen's side: **the "Started" state must not render unless a
   status transition was actually written**, and **a failed dispatch must
   leave the task in `BACKLOG` and say so.**
6. **New: whether Start reuses the automation poller's dispatch path or a
   direct invocation.** Product's §3 argument turned on this route not being
   *automation*; Design's requirement is only that whatever CTO chooses stays
   human-triggered and attended, with no path by which saving alone reaches it.
7. **Confirmation-survives-redirect mechanism** — §6.

## 10. What this review is not asking for

No editing, no deleting, no CRUD surface, no attachments, no multi-project,
no rendering of `user_story`/`requirements`/`acceptance_criteria`, no
auto-start, no retro-fix of existing rows. Concept B's receipt and Concept C's
inline capture are documented and rejected, not quietly dropped. Design cannot
approve its own mockup — this goes to Product or the Founder for that call.
