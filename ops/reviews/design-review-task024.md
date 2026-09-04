# Design Review — TASK-024: the Founder idea journey

**Revision 2 — the DEC-015 revision.** Design · 2026-09-01 · **for the Founder.**

**This supersedes Revision 1 in full** (the Save/Start intake flow, Concepts A/B/C,
and *Brainstorm More*). Revision 1's artboards are kept at
`ops/mockups/task024/superseded/` rather than deleted — §9 records what survived,
what was dropped, and why.

**Governing input:** `ops/reviews/founder-directive-task024-deciphering-v2.md`
(Parts 1, 2 and 3, verbatim — it governs over every summary of it), then Product's
Revision 4 at `ops/reviews/product-task024-brief.md`, then DEC-015.

**Canvas:** https://claude.ai/code/artifact/cb4151f6-1fa2-4d17-ab71-981e13d629de
**Artboards:** `ops/mockups/task024/*.dc.html` · manifest `canvas.json`

**Status: MOCKUP_REVIEW.** The Founder reviews this before Development begins —
the Founder's own process order (Part 3 §11). Design cannot approve its own mockup.

---

## 0. What this is, plainly

A **clickable prototype with working navigation and no backend.** Every control moves
you between drawn states; nothing dispatches an agent, invokes a model or spends money.

The journey is walked with the **Founder's own real idea**, TASK-026, quoted byte-for-byte
from the record:

> *"the current UI so much verbose, it should be as simple as a dashboard, I'M THINKING like an ellipse where we can track flow"*

It was chosen for three reasons, not one. It is **real**. It is an **internal utility**, so
its depth is honestly **Light** and sections 5–7 are honestly empty — the mockup demonstrates
depth scaling without inventing a single competitor. And Part 2 §3's own worked example is
literally this idea, so the interpretation in the mockup is the directive's own standard
rather than Design's invention.

The Reconsider round uses the Founder's **real later feedback**, also verbatim
(*"almost there, UI i'm talking about is UI of my factory to track the app progress…"*),
so the send-back path shows a real correction producing a real change rather than a
staged one.

**Every database fact quoted on the canvas is real and was queried this session:**
0 of 13 `agent_runs` rows carry a cost; `task_steps` on 1 of 24 tasks; `project_id` NULL
on 20 of 24; one row in `projects`; `design` absent from `MEETING_PARTICIPANT_ALLOWLIST`.
Everything the product could not honestly know is drawn as a **bracketed placeholder**,
never filled in. §8 lists what could not be drawn honestly at all.

---

## 1. The central design problem, and how it is solved

The directive names it: the UI must make it easy to distinguish **what I said · what the
factory thinks I meant · what the factory thinks about the idea · what the factory
recommends · what I approved.** Everything else in this design is downstream of that.

**The solution is a fixed grammar of five voices, carried by four independent signals so
that no single one is load-bearing.** It is drawn in full on `Distinctions.dc.html`.

| Voice | Colour | Container shape | Kicker | Attribution |
|---|---|---|---|---|
| **You said** | gray (`--gray`) | recessed ground, 3px left rule, quotation marks, `pre-wrap` | `YOU SAID` | *your words, 20:03 UTC, never edited* |
| **We think you mean** | blue (`--blue`) | panel, 3px left rule | `WE THINK YOU MEAN` | *the company · round N · vN* |
| **What we think of it** | violet (`--violet`) | panel, 3px left rule | `WHAT WE THINK OF IT` | *the company · round N* |
| **We recommend** | amber (`--accent`) | **filled ground + full border** — the only one | `WE RECOMMEND` / `WE NEED FROM YOU` | *one recommendation, round N* |
| **You approved** | green (`--green`) | **double border + header bar** — built like a document, not a card | `YOU APPROVED` | *v3 · by you · 20:41 UTC* |

Four decisions inside that are worth stating rather than leaving to be discovered:

- **The palette is not extended.** DEC-002's five hues plus gray were already fully
  assigned and this feature spends all of them at once. Nothing new was invented for it.
- **The Founder's own words carry no company colour at all.** They are the only element on
  any screen rendered as a literal quotation on a recessed ground. They are not the
  company's claim and they do not get the company's palette.
- **Colour is never the only signal.** Container shape, a kicker naming the speaker in
  words, and an attribution line all survive a grayscale print, a screenshot and
  colour-blindness.
- **The legend is in the page chrome**, on every screen of the journey. The Founder learns
  the grammar once.

**The test the design has to pass** is drawn as its own block on `Distinctions.dc.html`:
five statements about one idea, side by side, such that none of them can be read as
another — out of context, in grayscale, by someone who has not read the legend.

**One honest weakness, stated rather than hidden.** Violet already means *actor identity*
elsewhere in this product and is asked here to also mean *the company's judgment of the
idea*. That is a second meaning for one hue and it is the weakest link in the system. It is
written on the artboard itself, not only here.

### 1.1 The pairing that never goes away

Product §6's requirement — *the Founder must always be able to open the product and see the
words they originally typed, next to what the company decided those words meant, forever, on
the same screen, not in an archive* — is met literally. **The raw idea appears on all ten
stages**, in the same place, in the same treatment. On stages 5, 6 and 7 it is a compact
one-line strip; on 3, 8 and 10 it sits directly beside the interpretation or the approved
brief. It is present on the screen where the factory is still running (stage 10), which is
the screen where it is most tempting to drop it.

---

## 2. The concise/expanded split, in practice

Product §5's rule, rendered rather than described:

> **Concise = everything needed to decide whether to approve. Expanded = everything needed
> to check that decision.**

**How it is built.** The concise layer is **ten question rows**, one per Founder question,
each carrying its full answer in prose on the panel ground. The expanded material sits
behind one control per row — *"+ Show the working · sections 5 and 6"* — and opens into a
**visually recessed inset** with a darker ground, a thinner rule and a kicker naming which
of Part 2's fifteen sections it is. The two layers do not look alike, so a Founder can tell
at a glance which one they are reading.

**Four rules the rendering enforces:**

1. **The page says so at the top:** *"Ten answers, about two minutes. You can approve from
   this page without opening anything."* If that sentence is not true of a round, the round
   is wrong, not the sentence.
2. **Every expander is labelled with what it contains**, by section number. A control that
   says only "more" invites the Founder to assume something decision-relevant is behind it.
3. **The Company View is never behind a disclosure.** It closes the concise layer, always
   visible, always the same six fields.
4. **The uncomfortable answers stay in the concise layer.** Question 4 on this idea is
   answered *"We don't know, and here is why"* in full, in the concise layer, at the same
   size as every other answer. It is not softened and it is not demoted.

**The check I applied to my own draft**, which is also Product's AC-29: read only the
concise layer, decide, then open everything and ask whether the decision would have changed.
On this idea it would not. Every fact that could change the answer — the data floor, the
missing differentiation, the ellipse being uncommitted, the two open questions — is above the
fold in the concise answers. The expanded layer holds *evidence*, never *news*.

**The ten questions map onto the fifteen sections exactly as Product specified**, and each
expander names its sections: Q1→1+2, Q2→3, Q3→4, Q4→5+6, Q5→7, Q6→8, Q7→9+10+12, Q8→11,
Q9→13, Q10→14, closing on §15.

---

## 3. Depth scaling, and the three labels

**Depth is shown as a chip with its one-line reason beside it**, not as a setting buried in
a panel. It appears on the interpreting screen (stage 2) and again on the result strip
(stage 3), each time reading:

> **Light** — nobody outside this company chooses between this screen and an alternative; it
> is our own operating console. Competitor and market analysis could not change the
> recommendation, so it will not be produced.

Beside it, the honest note that the other setting exists, that Full has to name *who chooses
and what else they could choose*, and that Full costs more — which is part of why the
Founder is shown which one ran.

**At Light, sections 5–7 are drawn as present-and-not-produced**, with the reason, never
silently absent. Section 5's block carries the line that matters most:

> *This is not the claim that there are no competitors. We have not looked, and we cannot look.*

**The three labels are shown in the one place they can be shown honestly.**
`FullDepth.dc.html` draws the Full-depth expanded layer with **every value as a bracketed
structural placeholder** — `[competitor]`, `[what they offer]`, `[overlap with our idea]`,
`[where they appear stronger]`, `[where our idea could differentiate]`. The directive bans
invented competitor information and a mockup is not exempt from that, so no competitor was
invented to make the sheet look finished.

That sheet shows, as they would actually render today:

- The **standing disclosure on the section itself**, verbatim: *"Research has not been
  performed; all entries below are company inference or unknown."*
- **COMPANY INFERENCE** on the substitute and on the named competitor — and **substitutes
  before vendors**, because how people solve the problem today is more decision-relevant and
  needs no verification.
- **UNKNOWN** as a first-class entry: *"We are not aware of an established competitor here,
  and cannot check. That is not evidence there are none."*
- **VERIFIED / CURRENT struck through and marked unreachable**, with the reason (it requires
  a preserved source and no agent here can produce one) and the consequence: *if this label
  ever appears on a real evaluation, treat it as evidence that something fabricated it.*
- The **Founder-checkable prompt** on the named third party: *"Before committing, check
  whether [competitor] already does this — we cannot."*
- A **Company View at Full depth with unknown competitor data**, which lands on
  **OPPORTUNITY: Unclear** and **RECOMMENDATION: Investigate first** — Product's requirement
  that *Investigate first* be a reachable outcome rather than a value nobody selects, drawn
  as the case that reaches it.

---

## 4. The journey, stage by stage

Ten stages, one artboard each, laid left-to-right in journey order, plus `Main.dc.html` —
the walkable window that mounts each of them behind a clickable rail.

| # | Stage | Artboard | What it settles |
|---|---|---|---|
| 1 | RAW IDEA | `S1RawIdea.dc.html` | **Save Idea** (filled, free) and **Refine / Interpret…** (outlined, ellipsis). Neither spends on this click — the compose surface still has no spend control on it. *Refine* opens the disclosure; the standing "In Backlog — saved, not started" ledger stays. |
| 2 | FACTORY INTERPRETING | `S2Interpreting.dc.html` | Roster (*Product · CTO · Red Team*) with a reason per role **and the roles left out with their reasons**; depth and its reason; **no progress bar and why**; no transcripts; leaving is free. |
| 3 | FACTORY UNDERSTANDING | `S3Understanding.dc.html` | Your words beside our reading; concise questions 1–3 with expansion; roster/depth strip. |
| 4 | IDEA EVALUATION | `S4Evaluation.dc.html` | Concise questions 4–10 and the **Company View**. Same page as stage 3 — the rail splits it only so it can be jumped to, and the screen says so. |
| 5 | FOUNDER REVIEW | `S5Review.dc.html` | **Edit/Correct · Reconsider · Approve Brief**, each with what it costs on itself. Both question states drawn: two questions with their stakes, and the honest zero. |
| 6 | CORRECTION / RECONSIDERATION | `S6Reconsider.dc.html` | What Reconsider actually does: feedback captured verbatim, the spend warning **on the button**, round counter, round 2's real delta. Edit/Correct beside it, free and attributed to the Founder. |
| 7 | FOUNDER APPROVAL | `S7Approval.dc.html` | What approving does and does not do; approvable with a question still open; **silence is not consent**. |
| 8 | APPROVED BRIEF | `S8ApprovedBrief.dc.html` | **WHAT I APPROVED** as a distinct artifact — double border, header bar, seal — beside the raw idea. The three artifacts, the version ladder, and what downstream agents receive. |
| 9 | START WORK | `S9StartWork.dc.html` | Arm → confirm → started, plus the drawn failure and double-click states. |
| 10 | FACTORY BEGINS EXECUTION | `S10Running.dc.html` | What was actually written, **the four things this screen will not show and why**, and where to watch it. |

Plus three reference sheets: `Distinctions.dc.html` (the five voices), `HonestStates.dc.html`
(ten honest states drawn), `FullDepth.dc.html` (§3).

**Walkability.** Artboards on this canvas share no runtime state, so cross-stage navigation
lives in one place: `Main.dc.html` mounts each stage through `dc-import` and drives it from
a clickable ten-step rail plus Back/Next. Each stage also advances itself — its own forward
control calls back into the shell — so the journey can be walked by using the screens rather
than the rail. Standing alone on the canvas, each stage's **local** controls still work
(expanders, the arm-then-confirm, the reconsider box, the version ladder). One authored copy
of each screen, two ways to read it.

---

## 5. What Reconsider does, decided

The directive says *"the Founder provides feedback and the company re-evaluates"* and leaves
the rest to Design. What is drawn:

- **The feedback box is the action**, not an afterthought. It is the only thing round 2 has
  that round 1 did not, and the screen says so: *without it we would re-run the same
  reasoning on the same input and hand you the same answer, at the same price.*
- **The spend warning is on the control**, in its label — *"Send back for round 2 — this
  spends again"* — not in a paragraph above it. Product §8's requirement, rendered.
- **Rounds are numbered and visible**, with the honest line reserved for round 3:
  *another round costs again — it may be cheaper to approve and correct downstream.* It does
  not block.
- **Round 2 reports what did not change as well as what did.** A delta that lists only
  changes reads as agreement about everything else. The drawn round 2 carries five marked
  lines — CLOSED, SHARPER, NEW, SAME, OPEN — including one still-open question that the
  company did not quietly decide.
- **Edit/Correct is the other half of the same screen**: free, zero `agent_runs`, and the
  new version is **authored by the Founder**, with the added line marked as theirs wherever
  it appears afterwards, including downstream. And the screen states the boundary: an edit
  never reaches the raw idea, which has no edit path anywhere in the product, for anyone.

---

## 6. Start Work — what survived, and what changed

**Survived from Revision 1, unchanged in shape:** arm-then-confirm; outlined control arms and
dispatches nothing; the filled control appears exactly once, on a screen whose whole body is
the consequence; the control is **removed** after firing rather than disabled; and the failure
state says *"Not started. TASK-026 is still in the Backlog"* — the word "started" never
rendering unless a transition was written.

**Changed:** it now applies to **Approve Brief & Start Work** only, and the label
`Start work on TASK-025…` from Revision 1 is gone — Product was right that the first click
starts *understanding*, not building.

**Added, from Part 3 §5 and Product §8.1/§9.2** — the confirm screen states four things:
agents begin working; **real AI cost may be incurred and there is no estimate** (0 of 13
recorded runs carries a figure); the **approved brief** is what those agents receive, with
the raw idea beneath it labelled as context; and **there is no stop button.**

---

## 7. Honest states, drawn

`HonestStates.dc.html` draws ten, several with the tempting wrong version beside them, marked:

1. **"We are not aware of established competitors, and cannot check. That is not evidence
   there are none."** — beside the struck-through *"There are no competitors"*, which is
   always a failure and is the sentence the Founder most wants to hear.
2. **"We don't know, and here is why"** — in the concise layer, at full size.
3. **"We do not yet see a strong differentiation"** — a complete answer, not a gap.
4. **An empty competitor section that says why it is empty** (Light depth, with the reason).
5. **Zero Founder questions** — a passing score, with the note that eight small questions
   would be the failure.
6. **"Not started. Still in the Backlog."**
7. **No cost estimate**, with the enforced-ceiling slot drawn empty and bracketed.
8. **No progress bar**, with the bar this product will not ship shown as a hatched
   placeholder and labelled.
9. **A roster of one** — legitimate, never silent.
10. **A perspective that could not be consulted** — *Design would have been material here;
    `design` is not on the meeting participant allowlist today.*

The rule underneath all ten is on the sheet: *an empty space with a reason is information;
an empty space without one is a bug; a filled space without evidence is a lie.*

---

## 8. What I could not draw honestly

Stated plainly, because a mockup that quietly invents the parts it cannot know is the exact
failure this feature exists to prevent.

1. **The per-round cost ceiling.** Product §8.4 permits a maximum only if it is recomputed
   from the mechanism CTO actually builds, and explicitly forbids copying the figure in the
   brief. That mechanism does not exist. So the slot is drawn, empty and bracketed —
   `[ per-round maximum — computed from the real dispatch path; not yet wired ]` — on the
   interpret disclosure, the reconsider panel and the Start confirm. **CTO fills it or it
   stays empty.** An empty slot with a reason is the honest state; a copied number is not.
2. **Any competitor, at Full depth.** No competitor, substitute, price, feature or market
   fact is named anywhere on this canvas. `FullDepth.dc.html` shows the *shape* of that
   layer with every value bracketed.
3. **The Founder's title for the idea.** The Founder typed the idea, not a title. The compose
   field therefore shows placeholder text rather than a value, and every later screen
   identifies the idea as **TASK-026** — which is real — rather than putting words in the
   Founder's mouth.
4. **Any timing.** No ETA, no duration, no "usually takes about" anywhere. Nothing has run
   often enough to have a history.
5. **The internal debate.** It is referenced as reachable in one click and is not drawn,
   because no such meeting has been held for this idea and drawing one would be fake
   evidence.

---

## 9. What changed from Revision 1, and why

| Revision 1 | Now | Why |
|---|---|---|
| Three concepts (A/B/C) for one intake screen | **One direction, ten stages** | The visual language is settled (DEC-002 and Revision 1). The open question is the journey, not the aesthetic. |
| *Brainstorm More* | **Gone entirely** | The Founder rejected the concept. Not renamed — removed. |
| Start = the whole pipeline from a raw idea | **Start = execution of an approved brief** | DEC-013/014/015. |
| `Start work on TASK-025…` | **Approve Brief & Start Work** | The first click starts understanding, not building. |
| Save/Start as the central tension | **The five-way voice distinction as the central problem** | Part 3 §6. Save/Start survives as one stage of ten. |
| — | **Concise/expanded split, depth chip, three labels, honest states** | Part 2 and Part 3 §1, §7, §10. |

**Kept, deliberately:** the principle that **the compose surface carries no control that
spends on click**; the **arm-then-confirm** treatment of a consequential action; *"Not
started. Still in the Backlog"*; the standing "saved, not started" ledger and its
double-duty as the first-run empty state; and the finding that **no honest cost estimate
exists**.

**Documented and rejected, again:** Concept B's receipt page and Concept C's inline capture
(`superseded/`). Concept B's counted-nothings block *did* survive — it is the
"0 agents dispatched · 0 model calls · nothing spent · 0 other tasks changed" line on the
saved state of stage 1.

---

## 10. Open, for the Founder and then CTO

**For the Founder** — this is what the gate is for:

1. Does the five-way distinction actually hold for you when you walk it? That is the whole
   feature, and it is the one thing I cannot check on my own behalf.
2. Is the concise layer genuinely enough to approve from without expanding anything?
3. Is *Refine / Interpret…* the right pairing with *Save Idea* on the compose surface, given
   that neither spends on the click?

**For CTO, carried forward and added:**

- All twelve of Product §13's open questions stand.
- **The cost-ceiling slot** (§8.1) — computed and rendered, or left empty. Not copied.
- **Where the "authored by the Founder" attribution is stored**, so an edited line can be
  marked as the Founder's on every later screen and in downstream transcripts.
- **The approved brief as a pointer to a version**, not a copy — stage 8 renders it that way.
- **Whether `design` joins the participant allowlist.** Stage 2 renders its absence as a
  visible, named gap; if the allowlist changes, that line changes with it.

**What Design will flag as non-negotiable from the screen's side:** the raw idea renders on
every screen of the journey and is never editable; "started" never renders without a written
transition; no number appears that the records cannot support; and no competitor claim
renders without one of the three labels.

---

## 11. What this review is not asking for

No production code, no schema, no routes. No editing the raw idea, by anyone. No auto-start,
no auto-approval, no timeout. No research capability. No scores, meters or percentages on the
Company View. No invented competitors, market numbers, costs, durations or progress —
anywhere, including in the mockup.

**Design cannot approve its own mockup.** This goes to the Founder.
