# Design Review — Milestone A: Active Work Dashboard + Task Detail Page (TASK-019)

Date: 2026-08-31
Author: Design
Reviewing: `ops/reviews/cto-milestone-a-architecture.md` (CTO, TASK-019),
per DEC-009's Design-review gate (required wherever a milestone carries
Founder-facing UX changes). Scope discipline matches CTO's own: this is
a **UX/layout review of an already-specified data/field design**, not a
from-scratch mockup exercise. No new fields, no new queries proposed —
everything below stays inside CTO's approved data sources.

Two real mockups accompany this review, published as one canvas:
**https://claude.ai/code/artifact/2b4b2c81-e314-4e98-b768-823a68a474fc**
(also on disk at `ops/mockups/milestone-a/`). Both render real, current
data queried directly from `operations.sqlite3` this session — TASK-016/
017/018 for the Active Work dashboard, TASK-017's full history (per
CTO's own Part 5 walkthrough) for Task Detail — not placeholder content.
Visual language is copied verbatim from `ops/mockups/control-center-phase-0/Main.dc.html`
/ `ops/control-center/layout.py` (Style A dark) — no new visual system.

## Verdict

**Not ready for Development as literally specified in §3.3/§4.2.** The
underlying data model, computed functions, and field list in Parts 1–2
are sound and I have no changes to them — that work is correct and
should proceed unchanged. What needs to change before Development
starts is **layout only**: CTO's own §7.1 flagged four rendering
questions as open for this gate, and on all four I'm recommending a
specific answer that differs from CTO's illustrative sketch. I'm also
flagging one **live, real-data-confirmed defect** in the gates-remaining
algorithm (§1.4/§1.5) that is not a layout question and needs a Red
Team/Development fix, not a Design opinion — see "Blocking finding"
below. Everything else in this document is a layout recommendation, not
a blocker; CTO/orchestrator can decide how many of the non-blocking
ones to take.

---

## 1. Active Work dashboard

### 1.1 Does CTO's card (§3.3) scan at a glance? No — not as drawn.

CTO's own sketch is four lines of uniform-weight plain text per task:
title, a bracketed `[Founder needed: No]`, a gate/progress line, an
owner/bounces/last-event line, a next/elapsed/cost line. Every field
carries the same visual weight. That fails the Founder's own stated
requirement ("every active task at a glance") for a concrete reason:
there is no path for the eye to find the one or two facts that actually
matter — Founder-needed and stuck — without reading all four lines in
full, every time, for every row. At 3 rows today that's tolerable; at
"dozens" (CTO's own stated target scale) it stops working.

**Recommendation, built into the mockup**: two-tier *typographic*
hierarchy, not two-tier *interaction*. Every row is still one flat
`<a>` card (zero JS, zero `<details>` needed here — reserved for
Task Detail's genuinely long lists, see §2.3) but with three visually
distinct layers:
1. A **status dot** (left edge, 8px) — red for an interrupt
   (`BLOCKED`/`FOUNDER_APPROVAL`), the existing `--accent` amber for
   normal in-progress work. Reuses `agents.html`'s own
   `STATE_COLOR` convention exactly, not a new color meaning.
2. **Primary line** (13px, full weight): `TASK-### — title`, with the
   `Founder needed` pill right-aligned — the one element on the page
   allowed to be red *and* bold. An interrupt (`BLOCKED`/
   `FOUNDER_APPROVAL`) gets Pipeline's own existing `Needs Attention`
   treatment reused verbatim (red-soft card background, red border) —
   not a new pattern.
3. **Secondary lines** (11–11.5px, `var(--text2)`/`var(--text3)`,
   visibly de-emphasized): current gate + two-number progress + owner
   on one line, bounces/last-event/next/elapsed/cost on a second. Every
   CTO-specified field is still shown, by default, with no click needed
   — I am **not** recommending hiding fields behind an expand for this
   page. At single-digit-to-dozens scale, two compact lines per row
   (what the mockup renders) reads fine; a `<details>` disclosure would
   save vertical space Founder Active Work doesn't need to save, at the
   cost of one extra click on every single row just to see whether
   "Bounces: 3" belongs to a task that's actually fine or in trouble.

This is a genuine change from CTO's sketch, not a color pass: it
answers §7.1 item 1 (card vs. table) with a **third option** — neither
CTO's flat card nor a dense single-line table, but a card with real
visual hierarchy inside it.

### 1.2 Do not build a progress bar for the two gate numbers

CTO was right (§1.5) not to render `N/M` as a fraction, since no fixed
total exists for most tasks. The same reasoning extends one step
further than CTO's document states: **do not render a progress bar
either**, even an unlabeled one. `render_stage_column()`'s existing
progress bar (`generate_pipeline.py`) is driven by `task_progress_fraction()`,
a *different*, already-real fraction (task_steps-based) — reusing that
same visual affordance for `gates_completed`/`gates_remaining` would
silently imply a proportion to the Founder that the data explicitly
does not support (a bar reads as "X% of a whole" even with no numbers
printed on it). The mockup renders this as plain text chips — "2 done
· 5 to go" — deliberately, not a bar. This is the one place I'd ask
Development to be careful not to reach for the nearest existing
component out of habit.

### 1.3 Founder-needed pill color: reuse Inbox's convention, not a new "urgent red"

CTO's spec didn't fix a color for `[Founder needed: Yes/No]`. I
recommend against making `Yes` a stronger red than an interrupt banner
— "needs a decision" and "something failed" are different facts, and
this project already has an established, different treatment for
"awaiting a Founder decision" (`generate_inbox.py`'s `Awaiting decision`
pill: `--gray-soft`/`--text2`, not red; `--blue` reserved for "flagged
for discussion"). The mockup follows that precedent: `Founder needed:
Yes` uses `--red-soft`/`--red` (it does need to stand out — TASK-16's
row is genuinely the thing the Founder should look at first) but stays
visually distinct from — not identical to — the interrupt banner's red,
and `Founder needed: No` uses the same neutral gray-soft as Inbox's own
"nothing pending" language. Small, but this is exactly the kind of
palette-invention check §7.1 item 6 asks this gate to make.

### 1.4 Sort order (§3.5): confirmed

Founder-action-required first, then stuck, then most-recently-active —
agreed, no changes. The mockup's three real rows sort as TASK-16
(Founder needed), TASK-18 (more recent last-event), TASK-17 (older
last-event) under exactly this rule.

### 1.5 Stuck badge treatment (§7.1 item 4): confirmed informative, not alarmist

`STUCK_THRESHOLD_DAYS=3` and its justification (§2.1) are reasonable —
no change recommended. No currently-active task exceeds it, so the
mockup shows the intended treatment as a labeled reference chip rather
than fabricating a stuck row: a neutral gray pill (`No activity in 4d ·
threshold 3d`), not red, sitting next to (not replacing) the
Founder-needed pill. Confirms CTO's own instinct that stuck and
Founder-needed are separate, differently-weighted signals.

### 1.6 One rendering addition beyond CTO's spec: a 4-number summary strip

The mockup adds a compact top-of-page strip (`Active tasks` /
`Founder decision needed` / `Blocked or paused` / `Stuck`) — four counts
over the exact same `active_work_rows()` list already being rendered,
zero new query, matching `Overview`'s existing `Company Health` panel
pattern. This is a genuine "at a glance" improvement (the Founder's own
phrase) that costs nothing new to compute. I'd recommend it, but flag
it as optional, not required for Milestone A to ship — Development can
cut it if it's judged scope creep.

---

## 2. Task Detail page

### 2.1 Single flowing page — confirmed, plus a pure-HTML anchor nav

Agreed: this should be one server-rendered page, not tabs (matches this
project's zero-client-side-JS constraint and its own established
"single flowing page" convention, e.g. `reviews.html`). Given the
genuinely large amount of information (11 sections per CTO's list), the
mockup adds one thing CTO's doc doesn't mention: a row of plain
`<a href="#section-id">` anchor pills at the top, one per major section.
This is native HTML anchor scrolling — zero script, zero interactivity
beyond what an ordinary same-page link already does in any browser —
and directly answers "does this need internal sections/anchors" from
the brief. Recommended addition, low cost (a handful of `id` attributes
plus one small `<div>` of links already present in `generate_*.py`
patterns elsewhere).

### 2.2 Promote scalar facts out of the section list, into one summary strip

CTO's 11-item section list mixes two very different kinds of
information: a handful of **single facts** (owner, elapsed, bounce
*count*, next action, Founder-action-required, cost) and several
**genuinely long lists** (gate timeline, status history, handoffs,
findings, decisions, risks, activity). Rendering all 11 as equal-weight
stacked sections buries the facts a Founder would want fastest (cost,
next action, elapsed) at arbitrary positions down a long page. The
mockup pulls the six scalar facts into one compact summary panel
directly under the header/interrupt-banner, with the bounce-count stat
linking down to the findings section rather than repeating the content
there. Everything CTO specified is still present — this is a
reordering/promotion, not a removal, and directly answers the brief's
"flag anything CTO's field list should... reorder."

### 2.3 Gate timeline: vertical, not kanban-shaped — confirmed distinct from Pipeline

§7.1 item 3 asked specifically for a treatment distinct from Pipeline's
kanban columns. The mockup uses a vertical connected timeline (filled
green check circle = DONE, open amber ring = CURRENT, hollow gray
circle = WAITING), each DONE/CURRENT entry carrying its own inline
one-line review-history note. This is a different shape by
construction — a single vertical list can't be confused with Pipeline's
horizontal stage columns — and it reuses the exact color meanings
(`--green` = pass, `--red` = reject inline in the notes, `--accent` =
current) already established everywhere else in the product.

### 2.4 One real redundancy in CTO's own §4.2 section list, confirmed against TASK-017's real data

CTO's own Part 5 walkthrough admits it directly: "Code Review / QA /
Security findings: **see Gates above** — all four architecture-stage
findings (#48-51) shown inline." For TASK-017 specifically, the same
four `review_results` rows would render **three times** on one page
under CTO's literal §4.2 list — once inline in the Gate timeline
(item 2), once in the Bounce Count section's row list (item 3), and
once more in full in the Findings section (item 6). That's not a
hypothetical scaling concern; it's exactly what CTO's own worked
example shows would happen today. The mockup resolves this the way
§4.2 itself already gestures at: Gate timeline gets a short inline
note per event; Bounce Count becomes a single number (in the summary
strip, §2.2) that links to Findings; Findings is the one place the full
finding text — the specific quoted CONCERNS/REJECT/PASS language —
lives in full. Recommend CTO's Development handoff make this explicit
rather than leaving three sections to independently re-render the same
four rows.

### 2.5 Empty-state sections (handoffs, decisions, risks, activity for TASK-017)

CTO's Part 5 already writes these as specific, honest, non-generic
"none, and here's why" sentences rather than a bare "none" — the
mockup keeps that discipline exactly, rendering each as its own short
paragraph rather than compressing four empty sections into one
generic "nothing recorded" block. This matters here specifically: the
risks section's explanation (why `risks.id=3` correctly does *not*
appear on a task-scoped page) is load-bearing content, not filler, and
would be actively misleading if shortened to just "None."

---

## 3. Blocking finding — not a layout question, flagged for Red Team/Development

Using TASK-019 itself (this milestone's own tracking task) as a live
data check, `gates_remaining()` (§1.5) breaks for any task whose
`tasks.status` moves **backward** in `GATE_STATUS_ORDER` relative to a
gate it has already evidenced as completed. This isn't hypothetical —
it already happened, on this exact task: TASK-019's real
`task_status_history` shows `BACKLOG → ARCHITECTURE` (row 135) then
`ARCHITECTURE → MOCKUP_REVIEW` (row 136) for the Design-review gate.
`MOCKUP_REVIEW` sits at index 2 in `GATE_STATUS_ORDER`, *before*
`ARCHITECTURE` at index 3 — the reverse of what CTO's own §1.6 table
specifies ("Design review... recorded while status is still
`ARCHITECTURE` or `RED_TEAM_REVIEW`", i.e. `tasks.status` should never
actually become `MOCKUP_REVIEW` for this gate). Under CTO's design as
written: `gates_completed()` correctly evidences `ARCHITECTURE` as done
(§1.4's forward-exit check still works), but `gates_remaining()`
(§1.5, purely structural — "every entry strictly after
`effective_status`") would **also** list `ARCHITECTURE` as still
remaining, because `effective_gate_status = 'MOCKUP_REVIEW'` sits
before it in the list. That's two disagreeing facts about the same gate
rendered on one page — exactly the fabrication failure mode §1.1's own
no-fabrication reasoning exists to prevent, just triggered from the
opposite direction (a status moving backward, not skipping forward).
This needs either an orchestrator-behavior fix (don't set
`tasks.status = 'MOCKUP_REVIEW'` for the Design-review gate at all, per
CTO's own §1.6 model) or a `gates_remaining()` fix (exclude anything
already present in `gates_completed()`), decided by CTO/Development —
not a Design call, flagged here because it surfaced in this session's
own real-data check and would otherwise ship silently. I did not build
this contradiction into either mockup; both mockups use TASK-016/017/018,
none of which exhibit this pattern, specifically so the layout review
above isn't confused with this separate data-correctness issue.

---

## 4. Nav placement (§6.1)

Confirmed: "Active Work" immediately after "Overview" is the right
position — it's the natural next click from the company-wide snapshot
to "what needs me, per task." No change. `/tasks/<id>.html` correctly
stays off the nav bar, matching `/agents/<name>.html`/`/meetings/<id>.html`
precedent.

## 5. Summary of concrete recommendations

| # | Item | Status |
|---|---|---|
| 1 | Active Work: two-tier typographic hierarchy (not CTO's flat 4-line card) | **Change requested** |
| 2 | No progress bar for the two gate-count numbers | **Change requested** |
| 3 | Founder-needed pill: gray/red split matching Inbox precedent, not a new red | **Change requested** |
| 4 | Sort order (Founder-needed → stuck → recency) | Confirmed as-is |
| 5 | Stuck badge: neutral gray, not alarmist red | Confirmed as-is |
| 6 | Active Work summary strip (4 counts) | Optional addition |
| 7 | Task Detail: single flowing page + anchor nav | **Anchor nav is a change requested**; single-page confirmed |
| 8 | Task Detail: promote scalar facts to one summary strip | **Change requested** |
| 9 | Task Detail: vertical (not kanban) gate timeline | Confirmed, as specified |
| 10 | Task Detail: findings shown once, not 3x, cross-linked | **Change requested** |
| 11 | Nav placement | Confirmed as-is |
| 12 | `gates_remaining()` backward-transition defect (TASK-019's own real data) | **Blocking — Red Team/Development, not Design** |

Everything under "Confirmed as-is" needs no further Design round.
Everything under "Change requested" is small (CSS/markup reorganization
of already-approved data, no new query, no new field) and should not
require a second Design review round — one implementation pass
incorporating items 1/2/3/7/8/10 plus a resolution of item 12 is enough
to move to Red Team.
