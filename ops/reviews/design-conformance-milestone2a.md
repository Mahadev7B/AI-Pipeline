# Design Conformance Review — Phase 2, Milestone 2A

Checking the planned Pipeline / Agents / Agent Detail / Decisions /
Meetings screens against the approved Phase 0 dark mockups
(`ops/mockups/control-center-phase-0/*.dc.html`, Style A) before any
architecture work.

## Visual system — reused verbatim, not reinterpreted

Same tokens as Milestone 1: `--bg #0b0d10`, `--panel #14171c`, panel2/
border/border2, `--accent oklch(78% 0.14 75)`, the green/red/blue/violet/
gray semantic set, `--mono`/`--sans` stacks. `Pipeline.dc.html` and
`Agents.dc.html` already establish the structural patterns for the two
biggest new screens — reuse those patterns, don't invent new ones:

- **Pipeline**: `Pipeline.dc.html`'s six-major-stage-with-substate-lanes
  layout is the reference. Carry it forward as-is.
- **Agents**: `Agents.dc.html`'s grouped-roster + capability-panel
  layout is the reference, **with one resolved deviation** — the
  mockup's five functional groups (Executive/Product/Engineering/
  Operations/Oversight) were illustrative sample structure, not backed
  by a real column in the `agents` table. Milestone 2A's data rules
  ("every ... must come from real state," "empty states are better than
  fake data") mean this milestone cannot invent that taxonomy. Routing
  to CTO's architecture review to decide the real-data-backed
  replacement (see `ops/reviews/cto-milestone2a-architecture.md`) —
  flagging here as a Design-conformance-relevant gap, not deciding it
  here.
- **Agent Detail**: `Agents.dc.html`'s right-side capability panel is
  the reference for field layout (Role/Model/Skills/Frameworks/Tools/
  Permissions/Activity/Blockers/Confidence). Milestone 2A renders this
  as its own page per agent (no live server, no JS panel-swap — see
  CTO's architecture proposal) rather than an in-page panel; the *field
  set and visual treatment* carry over, the *interaction mechanism*
  necessarily changes from "click to swap panel" to "navigate to a
  page." That's a real, disclosed deviation, not a redesign.
- **Decisions / Meetings**: no Phase 0 mockup exists for a dedicated
  Decisions list or a Meetings *history* list (Phase 0 only mocked a
  single in-flight Executive Discussion, not a history view). New
  screens, same visual system (panel/label/pill conventions,
  color-by-severity or color-by-outcome where applicable) — not a
  deviation, an extension using the established components.

## Executive Meetings as first-class navigation

Founder's instruction is explicit: Meetings must have their own nav
destination, not be nested inside another screen. Confirmed as a
requirement for the shared nav shell — see CTO's architecture proposal
for the nav mechanism.

## Non-negotiables carried forward from Milestone 1

- No element styled as clickable unless it does something (still no
  write actions in this milestone — same rule, same reasoning).
- Founder vs. CEO Agent stay visually distinct wherever both appear
  (violet solid "FOUNDER · HUMAN" vs. dashed hexagon "CEO AGENT · AI" —
  same treatment as every prior screen).
- No Jira/TFS/spreadsheet/Kanban-clone feel — dense but composed, not
  a raw table dump. Decisions/Meetings lists in particular should read
  as cards, not table rows.

## Verdict

Conformant, with the agent-grouping gap routed to CTO/Red Team for a
real-data-backed resolution before Development.
