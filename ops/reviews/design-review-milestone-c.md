# Design Review — Milestone C: Company-wide Risks Register (TASK-021)

Reviewing CTO's architecture in `ops/reviews/cto-milestone-c-architecture.md`
against DEC-009's Design-review gate. Mockups: `ops/mockups/milestone-c/`
(`Main.dc.html`, `FlatSeverityFirst.dc.html`, `Risk3Detail.dc.html`,
published as one canvas —
https://claude.ai/code/artifact/f99f9edd-aa31-4253-bb70-381f49c98978).
All content is the real, live `risks` table (4 rows) and the 5 real
`decisions` rows that literally name `risks.id=3`, queried directly
against `operations.sqlite3` on 2026-09-01 — not placeholder text.

---

## Verdict

**CTO's architecture is sound and ready for Development, with three
small, additive refinements — none of which change the data model,
the route, or the read-only/no-JS constraints.** Nothing here reopens
`risks.id=3` itself, touches TASK-017, or expands scope beyond what
Part 8 of the CTO doc already excludes. Recommended before Development:

1. Keep **status-first** grouping (Open/Mitigated/Resolved) as the
   page's primary structure — CTO's choice is correct — but add a
   small **"Needs attention" strip** at the top of the page, surfacing
   open + medium/high-severity risks as quick-jump links. This is the
   one structural addition; everything else below is a rendering
   refinement to what CTO already specified.
2. Move the "prior mitigation text not preserved" disclosure from
   **per-card** (CTO's §3.5, shown on every card with non-empty
   mitigation) to **page level**, shown once.
3. Cap the mitigation text block's width (e.g. `max-width:760px`,
   ~85ch) instead of CTO's literal `max-width:100%` — a pure
   readability fix, zero behavior change, one CSS value.

Related decisions as a compact chip row (not a full list) — CTO didn't
specify the concrete markup, only that a list should render; the
mockup confirms chips are the right call. Task-scoped link affordance
and nav placement are both confirmed as specified, no change needed.

---

## 1. Status-first vs. severity-first primary sort (§3.2, §6.3 item 1)

CTO's design: three sections, Open → Mitigated → Resolved, each
severity-descending inside. The brief asks whether severity should be
primary instead, given that being able to see `risks.id=3` clearly was
this milestone's whole motivating case.

**Tested directly**: `Main.dc.html` (status-first, as specified) and
`FlatSeverityFirst.dc.html` (a genuine severity-first alternative — a
single flat list, status shown only as an inline pill) render the same
4 real rows two different ways.

**Finding**: at today's row count, both orderings put `risks.id=3`
first — it's the only open risk, and it also happens to be the most
recently touched among the medium-severity rows, so severity-first
lands on it too. The two concepts are indistinguishable on the
question that motivated this milestone, *today*. They diverge once the
register has more history: severity-first has no way to express "this
was serious but is already handled" vs. "this is serious and still
open" — a resolved high-severity risk would render *above* an open
medium-severity one, which reads backwards for a Founder scanning what
still needs attention. Status is the more fundamentally actionable
axis in this project's own vocabulary (open = unaddressed, mitigated =
someone already responded, resolved = closed) — it's the same reason
task pipeline stages are the primary grouping on `/pipeline.html`
rather than a priority score. **Status-first, as CTO specified, is the
right primary sort.**

That said, the brief's underlying concern — a Founder must never have
to hunt through a status section to find the risk that most needs
their eyes — is real and worth designing for directly rather than
leaving it to "open happens to sort first." `Main.dc.html` adds a
**"Needs attention" strip**: a single callout, styled like the
Founder-approved phase-0 mockup's "Needs You" pattern
(`ops/mockups/control-center-phase-0/Main.dc.html`'s alert strip —
this is a reuse of an already-approved pattern, not a new one), listing
every open risk at medium/high severity with a jump link to its card.
At today's scale it's one line (`risks.id=3`). At real scale, this is
the thing that actually answers "what needs me" in one glance,
independent of which section it's filed under — it doesn't replace the
sections (they stay the honest, complete structure), it's a
severity-aware index into them. This is the one genuinely new element
this review adds to CTO's layout; everything else below is a rendering
refinement to what CTO already specified.

**Recommendation**: ship status-first sections (§3.2 as specified) +
the Needs-attention strip. Reject the flat severity-first structure
(`FlatSeverityFirst.dc.html`) as the primary layout.

---

## 2. `risks.id=3`'s real mitigation text — does plain `pre-wrap` read acceptably? (§3.5, §6.3 item 3)

Rendered with the actual current content (2,820 characters, confirmed
zero literal newlines — genuinely one dense paragraph, not several
CTO's own doc correctly notes this). `Risk3Detail.dc.html` renders it
three ways for direct comparison.

**Variant 1 (CTO's literal spec — `max-width:100%`)**: at full card
width (which itself runs the full, unconstrained page width — this
product sets no page-level `max-width` on body content, confirmed by
rereading `layout.py`'s `page()`), line length on any reasonably wide
monitor stretches well past a comfortable reading measure. `pre-wrap`
itself does exactly what CTO's doc says it does — nothing more,
nothing less, since there are no embedded newlines to preserve today —
but "wraps at all" and "reads well" are different bars, and at this
length the difference is visible immediately in the mockup.

**Variant 2 (recommended — `max-width:760px`, ~85ch)**: same text, same
`pre-wrap`, one CSS value changed. This is not a truncation or an
expand-on-click affordance (CTO's own instruction not to
over-engineer for one risk's situation, honored) — every character
still renders, unconditionally. It's a pure line-length fix, and it
reads substantially better in the mockup: still a long block (this is
a genuinely dense 2,820-character disclosure and no CSS change makes
that not true), but no longer actively working against the reader.

**Recommendation**: keep CTO's `pre-wrap` treatment and its "no
truncate, no `<details>`, no rich-text renderer" discipline exactly as
specified — reject the `<details>`-collapse option CTO's own §6.3 item
3 floated, since this is the Founder's single highest-priority risk
and hiding it behind a click by default would undercut the whole point
of the milestone. Change only the one CSS value: `max-width:100%` →
`max-width:760px` (or an equivalent ~80–90ch measure) on the mitigation
block. This is not a change to CTO's architecture, only to the literal
CSS snippet in §3.5.

One thing this review did **not** add, deliberately: a "mitigation last
updated" timestamp. The schema has no column that captures that (that
is exactly Part 1's finding — there is no history, so there is no real
"last updated" date to show without fabricating one from `created_at`,
which would be wrong: `created_at` is when the risk was *raised*, not
when its mitigation text was last edited). The honest fix for that gap
is the `risk_history` table CTO already sketched and correctly deferred
— once it ships, a real "mitigation last updated {changed_at} by
{changed_by_agent}" line becomes available and should be added then,
not faked now.

---

## 3. Placement of the "prior versions not preserved" disclosure (§3.5, §6.3 item 2)

CTO's spec: render this notice on every card with non-empty
`mitigation` text — unconditionally, not detected per-risk, since the
database itself can't answer "was this one actually overwritten."
That underlying reasoning is correct and this review doesn't dispute
it. The question is placement.

**Tested**: `Main.dc.html` shows it once, page-level, in a small panel
below the header. `Risk3Detail.dc.html`'s Variant 1 shows CTO's literal
per-card placement for comparison.

**Finding**: the fact being disclosed — "this table stores no history"
— is a property of the whole `risks` table, true equally of every row,
not a per-risk fact that varies card to card. Repeating an
unconditional, table-wide statement on every card (all 4 of today's
real rows have non-empty mitigation, so CTO's rule would show it 4
times today, and on every future row with any mitigation text at all)
reads as boilerplate the more it repeats — exactly the "clutter on
every card, most of which were never edited multiple times" the
milestone brief asked Design to weigh. A single, clearly-worded,
page-level statement is *more* honest, not less: it correctly frames
the gap as systemic rather than something to notice-and-dismiss once
per card, and it costs nothing in visual weight from row two onward.

**Recommendation**: move the disclosure to page level (once, near the
top, styled as a small panel — see `Main.dc.html`), not per-card.
Wording can stay CTO's own text verbatim (`ops/reviews/cto-milestone-c-architecture.md`
Part 1.1) — only the placement changes.

---

## 4. "Related decisions" for company-scoped risks (§4.2, §6.3)

Real content: `risks.id=3` has 5 real related decisions (`decisions`
table ids 9, 10, 11, 12, 13 — CTO's doc estimated six by counting
`DEC-N` numbers in `ops/DECISIONS.md`'s own prose numbering, which is a
different, independent numbering scheme from `decisions.id`, per
`ops/DATA_MODEL.md`; the live query against the actual `decisions`
table returns 5 rows for `risks.id=3` today — worth a one-line
double-check against `DECISIONS.md`'s narrative count before
Development, but not a design concern). `risks.id=2` has 1,
`risks.id=4` has 1.

**Tested**: `Risk3Detail.dc.html`'s Variant 2 (compact chip row,
title-truncated with ellipsis, wraps) vs. Variant 3 (full vertical
list with titles and dates). At 5 real decisions sitting directly under
an already-2,820-character mitigation block, the full-list variant
reads as a second wall of text stacked on the first — it visibly
competes with the mitigation text for attention in the mockup, which
is the opposite of what a supporting cross-reference list should do.
The compact chip row stays legible, visually subordinate (smaller
type, muted color, pill styling matching this product's existing
`.pill` vocabulary), and scales reasonably — 5 chips wrap to two short
lines at the mockup's width; even a hypothetical 10+ would still read
as a scannable index, not prose.

**Recommendation**: render related decisions as a compact, wrapped chip
row (`Main.dc.html` / `Risk3Detail.dc.html` Variant 2's markup), not a
full list. Each chip: `#{id} — {title}` (title-truncated with
`text-overflow:ellipsis`, full title in a `title=""` tooltip), linking
to `decisions.html#decision-{id}` exactly as CTO's §4.2 specifies —
this changes only the visual rendering, not CTO's underlying query or
data source.

---

## 5. Task-scoped risk link affordance (§4.1, §6.3)

Real example: `risks.id=1` (`scope_type='task'`, `scope_id=1`, real
task "Verify Agent Pipeline"). Rendered in the mockup as a small
blue-tinted pill inline with the rest of the card's meta row (`Scope:
TASK-001 — Verify Agent Pipeline`, linking to `tasks/1.html`), visually
distinct from the plain-text "Company-wide" pill used for
`scope_type='company'` rows — small, correctly subordinate to the
card's title and severity/status pills, doesn't compete for attention.
Confirmed as CTO specified in §4.1; no change recommended.

---

## 6. Nav placement (§6.1)

"Risks" placed immediately after "Decisions" in the nav bar, matching
CTO's §6.1. Confirmed in the mockup (`Main.dc.html`'s nav strip) — it
reads correctly as an adjacent pair of company-governance, read-only
registers, and `risks.id=3` being cross-referenced from 5 real
decisions (§4 above) reinforces the adjacency in the actual live data,
not just in the abstract. No change recommended.

---

## 7. Consistency with the established visual system

Checked directly against `ops/control-center/layout.py`'s `CSS_TOKENS`
and against `generate_task.py`'s existing `render_risks()` /
`render_anchor_nav()` (the closest existing analog for a risk card and
a jump-nav row) — every mockup reuses the exact token set (`--panel`,
`--panel2`, `--border2`, `--red`/`--accent`/`--green` severity-status
mapping, `.card`/`.pill`/`.label` classes), the exact `Risk #{id} —
{title}` label convention already used on Task Detail, and the exact
anchor-pill jump-nav visual pattern already used there and on Task
Detail's own section nav. Nothing here introduces a new visual
element beyond the one addition named in §1 (the Needs-attention
strip), which itself reuses phase-0's already-approved alert-strip
pattern rather than inventing a new one. This reads as the same
product as Milestones A and B, not a third design era.

---

## Summary of concrete recommendations for Development

1. Add a page-level "Needs attention" strip (open + medium/high
   severity risks, quick-jump links) above the jump-nav pills — the one
   structural addition to CTO's §3.2/§3.4 layout.
2. Move the "prior mitigation text not preserved" disclosure from
   per-card to page-level, shown once, wording unchanged from CTO's
   Part 1.1.
3. Change the mitigation text block's `max-width:100%` (CTO's §3.5
   snippet) to a capped, readable measure (`max-width:760px` or
   equivalent ~80–90ch) — one CSS value, no other change to §3.5's
   `pre-wrap`/no-truncate/no-`<details>` discipline.
4. Render "Related decisions" as a compact, wrapped chip row (title-
   truncated, `title=""` tooltip), not a full vertical list — a
   rendering choice within CTO's §4.2 query/data source, unchanged.
5. Status-first section grouping (§3.2), task-scoped link styling
   (§4.1), and nav placement (§6.1) are all confirmed as CTO specified
   — no change.

None of the above touches the route, the shared computed functions
(`risk_register_rows()`, `related_decisions_for_risk()`), the schema,
or the read-only/no-write-route/no-client-side-JS constraints CTO's
architecture correctly holds throughout. Ready for Development with
items 1–4 folded in.
