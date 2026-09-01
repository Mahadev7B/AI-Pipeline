# Design Review — Milestone B: Company-wide AI Cost Visibility (TASK-020)

Date: 2026-09-01
Author: Design
Reviewing: `ops/reviews/cto-milestone-b-architecture.md` (CTO, TASK-020),
per DEC-009's Design-review gate — this milestone carries a genuine,
if small, Founder-facing UI surface (a new page, `/costs.html`, plus a
new section on an existing page, Meeting Detail), so the gate applies.
Unlike Milestone A's review (a layout pass over an already-sketched
screen), `/costs.html` is genuinely new UI with no existing analog on
this product besides `automation.html`'s narrower `render_spend()` —
this review builds and compares real concepts, not just a layout
critique of CTO's own sketch (CTO's document does not include a sketch
for `/costs.html` beyond the prose composition in §3.2).

Four real mockups accompany this review, published as one canvas:
**https://claude.ai/code/artifact/85aca8c9-5264-4858-a593-8ad192abbdb1**
(also on disk at `ops/mockups/milestone-b/`). Visual language copied
verbatim from `ops/mockups/control-center-phase-0/Main.dc.html` /
`ops/control-center/layout.py` (Style A, dark) and cross-checked
directly against `ops/mockups/milestone-a/`'s approved mockups for
consistency (see §4) — no new visual system introduced.

## A load-bearing finding before anything else: this milestone's own
## data does not exist yet, anywhere, in the live database

Confirmed by direct query against the live `operations.sqlite3` this
session: `meetings` has **0 rows**. `automation_events` has **0 rows**.
`agent_runs` has 13 rows total, and every one of them is TASK-1's
original pipeline-verification seed data (`scope_type='task'`,
`scope_id=1`) — none is an Ask-Agent, Meeting, Chief-of-Staff, or
Automated-Code-Review invocation. There is, today, no real row
anywhere in this system's operational history for three of the four
paths this milestone instruments, and the automation path's own
`automation_events` table — supposedly the one already-working
example — is also empty.

This is not a criticism of CTO's architecture (the design is correct
regardless of how much data exists to feed it) but it is a genuine,
disclosed finding this review is built around, for two concrete
reasons:

1. **I could not literally pull "an actual meeting from the live
   database" as the brief asked**, because none exists. Rather than
   mislabel fabricated content as real (the exact failure mode this
   whole milestone's NULL-handling discipline exists to prevent), the
   two `/costs.html` concepts split the difference honestly: Concept A
   (`Main.dc.html`, recommended) renders the page's **literal, real,
   current state** — genuinely $0.00/zero rows everywhere, which is
   what shipping today would actually produce, not a designed empty
   state. Concept B (`CostsTwoColumn.dc.html`) and both Meeting Detail
   concepts use **illustrative data, clearly labeled on the artboard
   itself** (a dashed accent-bordered advisory banner, same "not a
   real captured state" visual grammar this product already uses for
   dashed borders elsewhere — the CEO's AI-advisor position card, the
   request-perspective affordance), internally consistent with CTO's
   exact schema and composition, built only to let this gate evaluate
   the coverage-gap disclosure's legibility, which needs real content
   density to judge and which the live database cannot currently supply.
2. **It raises the real stakes of §3.4's honesty requirement.** The
   "historical NULL, not fabricated" discipline CTO's document treats
   as one disclosed edge case is, at this milestone's actual launch,
   not an edge case at all — it is close to the *entire* dataset for
   three of four paths, for as long as it takes real usage to
   accumulate. A page that leads with a triumphant "$0.00" with no
   further context would read as "nothing costs anything here," which
   is not true — it is "nothing has happened yet," a different fact.
   Concept A's mockup is built specifically to get this exactly right;
   see §1.1.

## Verdict

**Not ready for Development as literally specified, but for a narrower
reason than Milestone A's.** CTO's data model, schema change, and
call-site wiring (Parts 0–2) are sound and I have no changes to them.
What needs to change before Development starts:

1. **Layout**: use Concept A's stacked single-column structure for
   `/costs.html` (§1), not a two-column dashboard — see §1.3 for why.
2. **Wording**: add one rendering-only branch, "no invocations
   recorded yet" vs. "not available (recorded before cost tracking)"
   — two different real facts CTO's own count-based data already
   distinguishes but that his one worked example doesn't separately
   name (§1.1).
3. **Time window**: CTO's §3.2 composition defines only a "today"
   total, no all-time figure — I'm recommending one be added (§1.2).
4. **Meeting Detail**: use Concept 2's dedicated Cost panel (§2), not
   inline badges.
5. **§2.4's three extra instrumentation brackets should ship** —
   confirming CTO's own recommendation, not overriding it (§2.3).
6. **One coverage gap in CTO's own §3.2 grouping key**: `Synchronous
   review` (`REVIEWER_SYNC_ACTIVITY_LIKE`) is a real, distinct,
   cost-bearing invocation path that CTO's own composition already
   groups by, but the milestone's Founder-facing framing names only
   four paths — flagged in §3, not a blocker, but the UI must not
   silently drop or mis-bucket it.

Everything else is confirmed as specified. None of this requires a new
query, a new field, or a new attribution rule — every recommendation
below stays inside CTO's already-approved data sources, per the
brief's own scope discipline.

---

## 1. `/costs.html`

### 1.1 Concept A (`Main.dc.html`) — recommended: single-column stacked digest

Header note + two stat cards (Today / All-time) + three stacked panels
(by path, by agent, recent meetings) — the same vertical rhythm
Milestone A's Task Detail established (scalar facts promoted to a
compact top strip, long lists as separate stacked panels below), so
this reads as the same product, not a new one (see §4).

This concept is built around the finding above: it renders the page's
**real current state**, and it does the wording work that state
demands. Every "no invocations recorded yet" line is deliberately
**not** phrased as "not available (recorded before cost tracking)" —
that phrase means something specific and different (a real invocation
happened, its cost just wasn't captured). Conflating "hasn't happened"
with "happened, cost unknown" would be a real, if small, dishonesty in
the opposite direction from what CTO's own NULL discipline (§3.4)
guards against — currently CTO's design distinguishes these two facts
in principle (the count-based `{"available","usd","note"}` shape
already requires tracking a total-row count separately from a
tracked-count, exactly what a "0 of 0" vs. "0 of 5, 5 predate" check
needs) but his one worked prose example (`"$12.34 across 9 of 14
invocations..."`) only shows the populated case. **Recommendation**:
generate_costs.py's rendering functions add one small branch — when
the underlying total-row count is 0, render "No invocations recorded
yet" (no dollar sign, no fraction); when it's >0 and partially/fully
NULL, render CTO's exact `"$X.XX across N of M invocations (K recorded
before cost tracking)"` format unchanged. Pure wording, zero new
queries — the count this branches on is already required to exist by
CTO's own §3.4 spec.

The advisory box at the top of Concept A ("Cost tracking begins
today...") is the one genuinely new piece of copy this review adds
beyond CTO's spec — it exists specifically to state the distinction
above once, in plain language, at the top of the page, rather than
leaving a Founder to infer it from five separate "no invocations"
lines. Small, cheap, and matches this project's own "informative not
alarmist" precedent for the staleness badge (Milestone A) and the
NULL-cost disclosure CTO's own §5.1 item 3 asks this gate to check.

### 1.2 A genuine gap in CTO's own composition: no all-time figure

CTO's §3.2 `company_cost_digest()` defines exactly one headline number:
**today's total**. Given §1's own finding — this system will run for
a meaningful stretch of time with "today" being sparse or entirely
zero, especially the first several days after this ships — a
Founder's honest first question on this page ("how much have we spent
on AI, total, ever?") has no answer under CTO's literal spec until
enough days accumulate that summing "today" repeatedly becomes
informative. That's a real usability gap, not a hypothetical one.

**Recommendation**: add a second headline figure, all-time total,
computed exactly like "today's total" minus the date filter — the
identical query CTO's own §3.2 first bullet already specifies, just
without `WHERE started today`. This is not new attribution logic, not
a new source, not a time-window *toggle* (this product has a standing
zero-client-side-JS constraint, confirmed against `ops/mockups/milestone-a/README.md`
and every existing `generate_*.py` — an interactive tab control is
out of scope regardless), just a second static number next to the
first. Both mockups render Today and All-time as two side-by-side stat
cards, matching Automation's own single-stat-card visual weight
(`render_spend()`), scaled to two.

I'm not recommending a "this week" figure on top of Today/All-time —
two real numbers answer the Founder's likely questions (right now /
ever) without a third that mostly duplicates All-time at this data
volume; CTO/Product can revisit if usage grows enough that "this week"
becomes meaningfully different from "all-time."

### 1.3 Concept B (`CostsTwoColumn.dc.html`) — built to test the coverage-gap disclosure, not recommended as the primary layout

Left column: by-path breakdown with a share-of-spend bar per row (a
different, legitimate use of the bar-chart affordance from what
Milestone A's review rejected — Milestone A correctly ruled out a
progress bar for `gates_completed`/`gates_remaining` because no real
total existed; here, the four-or-five path sums genuinely do sum to a
real total, so a proportional share bar is an honest representation,
not an implied ceiling. Labeled explicitly as "not a ceiling" in the
mockup to keep it visually distinct from Automation's own ceiling bar,
per §3.5's explicit "no denominator, no bar tied to a limit"
instruction for the headline figure — the share bar is a different
kind of bar, applied only to the by-path breakdown, never to the
headline number). Right column: by-agent + recent meetings, demoted to
secondary.

**Why I'm not recommending this as the primary layout**: demoting
by-agent and recent-meetings to a narrower sidebar undersells them.
"How much have I spent talking to the CTO agent" and "which meeting
cost the most" are both real, first-class Founder questions per CTO's
own §3.2 rationale for including them at all — a two-column layout
that visually subordinates them to the path breakdown implies a
hierarchy CTO's own spec doesn't establish. Concept A's equal-weight
stacked panels (matching Task Detail's own established pattern, §2.2
of the Milestone A review) is the more honest information hierarchy
for four sections CTO lists as coequal. The share-of-spend bar concept
from Concept B is still worth keeping — I'd fold it into Concept A's
by-path panel (both mockups on the canvas show this technique; take it
from whichever one Development builds).

### 1.4 Historical-NULL wording (§5.1 item 3): confirmed informative, not alarming

CTO's exact phrase — "not available (recorded before cost tracking)" —
reads as a fact, not a warning: no red, no icon implying something is
broken. Both mockups render it in plain `--text3` gray, consistent
with how this exact same phrase-shape already reads elsewhere on this
product (`task_cost_usd()`'s existing "not available" line on Task
Detail — confirmed unchanged in Milestone A's approved mockup). No
change recommended to the wording itself, only the "0 rows" branch in
§1.1.

---

## 2. Meeting Detail — new cost section

### 2.1 Concept 1 (`MeetingDetailInline.dc.html`) — cost sprinkled inline

Total cost added to the header meta line; a small `$` badge added to
each position card's top-right corner; a badge added to each
follow-up panel's header. Tested specifically because the brief asks
"how does this fit without cluttering" — this is the version that
answers "minimize new surface area" most literally.

**Problems found building it, real ones**: (1) a badge on a position
card competes for the same top-right corner Milestone A's own
Founder-needed pill and this page's own CEO/red-team border treatments
already use to carry meaning — adding a third small element there
measurably increases visual noise on the one component of this page
that most needs to stay about *content*, not metadata. (2) CTO's own
carefully-worded NULL phrase ("not available (recorded before cost
tracking)") does not fit in a badge — the mockup is forced to abbreviate
to "n/a," which reads more like an error than an honest disclosure,
directly working against §5.1 item 3's "informative not alarmist"
requirement. (3) Cost ends up explained in three different places
(header line, card corner, follow-up panel) with no single place a
Founder can look to get the whole picture at once — the opposite of
"at a glance."

### 2.2 Concept 2 (`MeetingDetailPanel.dc.html`) — recommended: one dedicated Cost panel

Placed directly under the header (before the position grid), mirroring
Milestone A Task Detail's own precedent exactly — "promote scalar
facts... into one summary panel directly under the header" (Milestone
A review, §2.2), reused here for the identical reason: cost here is a
handful of scalar-ish facts (a total, a coverage count, one line per
invocation) that don't belong buried inside a component built for
substantive position content. The panel has room for CTO's full NULL
phrase, room for the CEO-selection footnote CTO's §3.3 asks for
verbatim, and keeps every existing component (position cards,
follow-up threads) untouched — directly answering "without cluttering"
by not touching what already works.

One addition beyond CTO's literal §3.3 spec, matching Milestone A's
own anchor-nav precedent: an anchor-pill row (`Cost · Positions ·
Follow-up · Synthesis · Decision`) since a Meeting Detail page with a
new section is now long enough to benefit from the same zero-JS anchor
navigation Milestone A added to Task Detail. Optional, cheap, not a
blocker.

### 2.3 §2.4's three extra instrumentation brackets — confirmed, should ship

CTO's own document already lays out both options here in full and
recommends shipping the three brackets (`_select_participants()` — no,
`_synthesize()` and `gather_followup_reply()` — yes) rather than the
disclosed partial-total fallback. I'm confirming that recommendation,
not overriding it: a meeting "total" that silently omits what CTO's
own document calls "plausibly the single most expensive call in most
meetings" (the CEO's synthesis) is a materially misleading number to
label "total" on a Founder-facing page, worse than the small,
bookkeeping-only cost of three new `start_run()`/`end_run()` brackets
CTO already scoped. Both mockups' Cost panels are built assuming this
ships (a synthesis line item appears in the per-invocation list) — if
Development/Red Team ultimately descope it, the panel still works,
minus that one line, with CTO's own disclosed fallback wording
("participant positions only") substituted for the total's caption.

---

## 3. Flag: CTO's own "four paths" framing undercounts CTO's own grouping key by one

CTO's §3.2 composition groups by five real, already-defined constants
(`agent_runtime.py:65-151`): `ASK_AGENT_ACTIVITY_LIKE`,
`MEETING_ACTIVITY_LIKE`, `CHIEF_OF_STAFF_ACTIVITY_LIKE`,
`AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE`, and
`REVIEWER_SYNC_ACTIVITY_LIKE` — the last one a genuinely distinct,
Founder/human-triggered invocation category (TASK-017's synchronous
Code/Security/Red-Team review routes, `reviewer_sync.py`), not a
sub-case of automation. The milestone's own Founder-facing framing
(this brief included) names only four paths — Ask-Agent, Meetings,
Chief of Staff, and (automated) Code Review — and never mentions
Synchronous review by name anywhere in CTO's prose outside the raw
constant list.

This isn't a data-source change (I'm not proposing new attribution —
the grouping key already exists, already correct, already in CTO's own
composition) — it's a **UI completeness flag**: if `generate_costs.py`
is built by literally reading the milestone's four-path framing rather
than CTO's own five-constant list, `Synchronous review` rows either
get silently dropped from the by-path breakdown or (worse) miscounted
into a bucket they don't belong to, understating that bucket's own
coverage gap. Both mockups render it as an explicit fifth row (`Concept
A`: "not used yet," honest given TASK-017 is currently paused;
`Concept B`: illustrative "$0.00 · not used yet" for the same reason)
specifically so this gate doesn't let a real fifth category go
unnoticed the way the brief's own framing almost did.

---

## 4. Consistency with Milestone A's established visual system — checked explicitly

- **Color semantics**: red reserved for interrupt/reject states,
  unused anywhere on these four mockups (no cost figure is ever an
  "alarm," per §5.1 item 3) — confirmed against Milestone A's own
  reasoning for why the Founder-needed pill isn't the interrupt-banner
  red (Milestone A review §1.3). Accent/amber used for the one genuine
  interactive-adjacent element (the all-time stat card, the by-path
  share bar) — never for a warning. Dashed borders reused for exactly
  what this product already uses them for: "this is a real thing, but
  not an ordinary captured position/row" (the CEO AI-advisor card, the
  request-perspective affordance, and — new here — the illustrative-
  content advisory banners on both `CostsTwoColumn.dc.html` and the two
  Meeting Detail concepts).
- **Typography hierarchy**: `.label` (10px, uppercase, `--text3`) for
  every section header, `.panel`/`.card` radii and padding taken
  verbatim from `layout.py`'s `CSS_TOKENS` (not re-derived), the exact
  same 26px/13px display size for `<h1>` as Task Detail. No new font,
  no new type scale.
- **Spacing**: 16px between stacked panels, 8-11px card gaps — matches
  Task Detail's own rhythm exactly (`ops/mockups/milestone-a/TaskDetail.dc.html`),
  not a fresh value.
- **Nav**: `Costs` added as an eleventh pill, immediately after
  `Automation` — confirmed against CTO's own §3.2 instruction and
  Milestone A's own nav-placement precedent (new top-level pages join
  the end of the existing bar; `/meetings/<id>.html`-style detail pages
  stay off it — `/costs.html` is a top-level page, so it belongs on the
  bar, unlike a hypothetical `/costs/<id>.html`).

No new visual system, no new color, no new component shape introduced
anywhere in this review — everything traces to `layout.py`,
`render_spend()`, or `ops/mockups/milestone-a/`.

---

## 5. Summary of concrete recommendations

| # | Item | Status |
|---|---|---|
| 1 | `/costs.html`: Concept A (single-column stacked digest) | **Recommended layout** |
| 2 | `/costs.html`: Concept B (two-column dashboard) | Not recommended as primary — keep its share-bar technique |
| 3 | Wording branch: "no invocations recorded yet" vs. "not available (recorded before cost tracking)" | **Change requested** — rendering-only, zero new queries |
| 4 | All-time headline total alongside Today | **Change requested** — same query as CTO's §3.2 bullet 1, minus the date filter |
| 5 | Meeting Detail: Concept 2 (dedicated Cost panel) | **Recommended layout** |
| 6 | Meeting Detail: Concept 1 (inline badges) | Not recommended — clutters position cards, forces NULL-phrase abbreviation |
| 7 | §2.4's three extra instrumentation brackets | **Confirmed — should ship**, per CTO's own recommendation |
| 8 | `Synchronous review` shown as an explicit fifth by-path row | **Change requested** — CTO's own composition already includes it; the Founder-facing "four paths" framing must not cause it to be dropped |
| 9 | Anchor-pill nav on Meeting Detail (Cost · Positions · Follow-up · Synthesis · Decision) | Optional addition, matches Task Detail precedent |
| 10 | Nav placement (`Costs` after `Automation`) | Confirmed as specified |
| 11 | §3.5 no-ceiling, no-denominator headline figure | Confirmed as specified — the share-of-spend bar in item 2 is a distinct, disclosed exception scoped only to the by-path breakdown, never the headline number |

Items 3/4/5/8 are small (wording/query additions inside already-approved
data, or a layout choice between two built concepts) and should not
require a second Design review round — one implementation pass
incorporating items 1/3/4/5/7/8 (plus a decision on optional item 9)
is enough to move to Red Team.
