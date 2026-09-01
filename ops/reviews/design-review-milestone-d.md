# Design Review — Milestone D: Project / Phase Progress (`/progress.html`)

Date: 2026-09-01
Reviewing: `ops/reviews/cto-milestone-d-architecture.md` (TASK-022, DEC-009
Milestone D — the fourth and **final** milestone of the Founder UI
Completeness plan). Design-review gate per DEC-009's own sequence:
CTO architecture → **Design review** → Red Team → Development → Code
Review → QA → focused Security review → CTO final conformance.

Mockups: `ops/mockups/milestone-d/` (`Main.dc.html`, `TwoZone.dc.html`,
`Closeup.dc.html`), published as one canvas:
https://claude.ai/code/artifact/ec86a51c-365e-4621-95d2-5bab56c92cfd

Content is real: the live `phases` table does not exist yet (confirmed
directly — `sqlite_master` has no such row), so these mockups render
CTO's own named real values (Part 3–5) exactly as specified — Phase
0/1/2/3/3A statuses and fractions, the Founder UI Completeness
sub-plan's real 3-of-4, real decision ids (2, 5, 10, 12, 13) and task
ids (15–22), and TASK-016/017's live `FOUNDER_APPROVAL` status,
TASK-018's `ARCHITECTURE`, TASK-022's `MOCKUP_REVIEW` — all queried
this session, not invented.

## Verdict

**CTO's architecture is sound and matches this project's established
schema/CLI/page discipline — approved as the data model, computed
functions, backfill sequence, and CLI shape (Parts 1–3, 5, 6, 8–11
need no change.** But the **page layout as literally specified in Part
4.3 (one flat, ordered tree, historical phases first) is not ready to
build as-is.** It buries the one genuinely live, actionable fact — the
Founder UI Completeness sub-plan sitting at 3 of 4, with TASK-017 in
`FOUNDER_APPROVAL` — under three "Complete" rows a Founder has to read
past first. **Recommendation: build CTO's exact tree (Part 4.3,
unchanged), but add the "Right now" panel from Concept A
(`Main.dc.html`) between the readiness header and the tree.** This is
additive, not a rewrite of CTO's data model or query shape — it reuses
`founder_readiness_summary()` and the same `phases`/`active_tasks_digest()`
rows the tree and Part 4.4 section already compute, surfaced a second
time, higher on the page, in summary form. One round should close this.

## 1. Does the flat phase tree surface "what's happening right now"?

**No, not as literally specified — this is the review's central
finding.** CTO's Part 4.3 order (Phase 0 → 1 → 2 → 3 [with 3A and
Founder UI Completeness nested] → 4) is the correct *narrative* order —
it should stay the tree's order, because a phase tree that reordered
itself by recency would stop reading as a phase tree. But it means the
first three rows a Founder sees below the readiness header are all
"Complete," and the one row that actually changed today — Founder UI
Completeness, 3 of 4 — sits two indent levels deep, roughly two-thirds
of the way down a page whose header the Founder has explicitly asked,
repeatedly, to answer "how far along is the company" *without reading
ROADMAP.md*. A page that requires scrolling past historical
"complete" rows to find the one live number is the same failure mode
DEC-009 exists to fix, just relocated from ROADMAP.md's prose to a new
page's layout.

This is exactly the situation Milestone A's own "what needs my
attention" pattern (Founder-decision-needed sorted first) and
Milestone C's "Needs attention" strip (phase-0's "Needs You" pattern,
reused a second time) were built to solve — and Milestone D needs its
own version of it, not a new mechanism. `Main.dc.html`'s "Right now"
panel is that version: a compact, accent-bordered card, directly below
the readiness header, showing the Founder UI Completeness sub-plan's
3-of-4 state and linking straight to TASK-016/017/018 (the three tasks
currently needing Founder attention) — before the historical tree
begins. It reuses data the page already computes (`founder_readiness_summary()`,
the same `phases` row, `active_tasks_digest()`) — no new query, no new
computed function, purely a placement decision.

`TwoZone.dc.html` explores a more aggressive alternative — restructure
the whole page into a "Live now" zone (Phase 3's full subtree,
dominant) and a receded "Company history" zone (Phase 0/1/2/4,
single-line-per-row) — and it does solve the same problem, more
thoroughly. **Not recommended for this milestone**, for one reason:
it changes the tree's *order*, not just its emphasis, which drifts
further from CTO's Part 4.3 spec than the review needs to ask for, and
loses the one property a strict phase-number tree has that a
recency-sorted one doesn't — a Founder scanning for "where's Phase 2"
can find it in the same place every time. Keep it on file as the
considered alternative (this README documents it), not built.

## 2. The two readiness booleans

CTO's Part 4.2 spec — a pill-like `YES`/`NOT YET` plus one honest
qualifying clause ("3 of 4 UI Completeness milestones done," "Milestones
A + B + C complete") — is correct as specified and **should not
change.** `Closeup.dc.html` panel 1 tests the two alternatives directly
against it: a stark boolean-only pill answers "not yet" with no sense
of how close, which recreates the exact opacity problem DEC-009 exists
to close; a fully narrated sentence is exactly the "narrated" language
CTO's own Part 3.4 forbids, and invites the kind of softened phrasing
this project has already had to correct once (DEC-009's own recount of
CTO's inconsistent 16/7/7 vs. 18/6/6 prose summary). CTO's original
treatment is the right middle point and is confirmed, not revised.

**Prominence**: CTO's Part 4.2 already places this at the very top of
the page, above the phase tree — correct, and confirmed not buried.
The one adjustment this review makes is treating it as its own
labeled card ("Founder readiness — computed, not narrated") with
larger pill sizing than a normal in-tree status pill, so it reads as
the page's headline the instant it loads, not as one more row in a
list of similarly-styled pills further down. See `Main.dc.html`'s
readiness panel.

## 3. Status pill colors

Confirmed against this project's actual established convention (not
assumed by analogy) — read directly from `generate_overview.py`'s
`STATUS_COLOR`/`HEALTH_COLOR` and `generate_risks.py`'s `_STATUS_COLOR`:
green = complete/done/passed, accent (amber) = active/in_progress, red
= open risk / danger / Founder-action-urgently-needed, gray = neutral /
not_started, blue = agent "waiting," violet = reserved specifically for
the AI-actor/human-actor identity marker and the cross-page "needs
attention" alert strip (phase-0, Risks) — never a status value.

`complete` → green, `in_progress` → accent, `not_started` → gray: all
three already match this convention exactly, no design call needed.
**`paused` — the one genuinely new value — recommend blue**, reusing
the existing "waiting" semantic one level up (a phase, not an agent
run, but the same idea: temporarily halted, not urgent, not active).
Red is rejected because it already means "open risk" / "danger"
everywhere else in this product, and a Founder-directed pause (DEC-008)
is a deliberate, calm decision, not an alarm — coloring it red would
misrepresent it. Violet is rejected because it's already spoken for
(actor identity, alert strips) and reusing it for a status pill would
blur an established, unrelated meaning rather than extend the
convention, which is exactly the anti-pattern CTO's own Part 9.1 asked
Design to specifically avoid. See `Closeup.dc.html` panel 2 for the
three options side by side with real rationale each.

## 4. Nested rendering (one level of indentation)

Confirmed: indent + a thin left-border connector line (`border-left:2px
solid var(--border2)`), the treatment used in `Main.dc.html`'s Phase 3
subtree, reads clearly at the two real levels of nesting this data
actually has (Phase 3 → Founder UI Completeness → Milestone D) — no
accordion, no collapse, no client-side JS, matching this project's
established flat server-rendered discipline exactly as CTO's Part 4.5
requires. `Closeup.dc.html` panel 3 isolates this specific nesting
with the real Milestone D row and confirms it. This also matches Part
2's own stated constraint ("at most two levels deep... no recursive CTE
needed") — nothing in the real data goes deeper, so no third-level
treatment needs to be designed now.

One added recommendation, not a change to CTO's data model: the
in-progress branch of the tree (Phase 3 itself, and the Founder UI
Completeness row nested under it) should carry a subtle
`background:var(--accent-soft)` tint and slightly heavier type weight
relative to the plain historical rows — see `Main.dc.html`. This is a
styling-only change (same rows, same order, same data) that gives the
one active branch visual weight without touching CTO's tree structure
or requiring reordering (the `TwoZone.dc.html` alternative's more
invasive fix).

## 5. Part 4.4 "in-flight work" section — now partially redundant, not wrong

CTO's Part 4.4 (reusing `active_tasks_digest()` for TASK-016/017/018,
unchanged) is correct and should still be built exactly as specified —
it remains the authoritative, complete, never-stale list, and matters
if that list ever grows beyond three rows. The "Right now" panel this
review adds (§1 above) shows the *same three tasks* in summary form
higher on the page. This is an intentional, small duplication (a
headline callout plus the fuller register below it), same pattern as
Milestone C's Risks page (its own "Needs attention" strip duplicates a
subset of the fuller register below) — not a sign one of the two
should be cut.

## What does not need another round

Schema (Part 2), the backfill sequence and its real sourced values
(Part 5), the CLI shape (Part 6), the staleness-prevention discipline
(Part 7), nav placement after Decisions/before Risks (Part 8.1 —
confirmed correct, no change), and the security framing (Part 9.2) are
all approved as specified. Only the page layout (Part 4.3's ordering
vs. emphasis) needed a Design call, and it has one now: keep CTO's
order, add the "Right now" panel.

## Recommendation to CTO / Development

Ready for Red Team with one addition folded into Part 4's page spec:
the "Right now" panel (`Main.dc.html`), built from
`founder_readiness_summary()` plus the same `phases` row already
computed for the Founder UI Completeness node in the tree — no new
computed function, no new query, no schema change. Concept B
(`TwoZone.dc.html`) is documented and rejected, not silently dropped.
The `paused` pill's color (blue) and the readiness header's exact
treatment (pill + clause, CTO's own Part 4.2 confirmed) are real design
decisions this document records, not left for Development to improvise.
