# Milestone B Design Review — Company-wide AI Cost Visibility

Design-review mockups for TASK-020 (DEC-009 Milestone B), reviewing
CTO's architecture in `ops/reviews/cto-milestone-b-architecture.md`.
Static mockups (not a clickable prototype) — matches this project's
zero-client-side-JS constraint and every prior Control Center screen,
same discipline as `ops/mockups/milestone-a/`.

Visual language copied verbatim from
`ops/mockups/control-center-phase-0/Main.dc.html` /
`ops/control-center/layout.py` (Style A, dark) and cross-checked
against `ops/mockups/milestone-a/` for consistency — no new visual
system introduced.

## Four artboards, two genuinely different concepts per surface

**`/costs.html`:**
- `Main.dc.html` (Concept A — recommended) — single-column
  stacked panels. Content is the **live database's real, current
  state**, queried directly this session: 0 rows in `meetings`, 0 rows
  in `automation_events`, and none of the 13 real `agent_runs` rows are
  Ask-Agent/Meeting/Chief-of-Staff/Automated-Code-Review invocations
  (all 13 are TASK-1's original pipeline-verification seed data). This
  is not a designed "empty state" — it is what the page would render
  today if shipped as-is.
- `CostsTwoColumn.dc.html` (Concept B) — two-column dashboard, path
  breakdown + share-of-spend bars on the left, by-agent + recent
  meetings on the right. Content is **illustrative, clearly labeled on
  the artboard** — the live DB has no real rows for these three paths
  to draw from, so this demonstrates the full/partial/zero-coverage
  disclosure CTO's §3.4 needs reviewed, using numbers that are
  internally consistent (path sums = headline total; agent sums = each
  path's total) and structured exactly to CTO's own composition, not
  an invented one.

**Meeting Detail's new cost section**, both built on the same
illustrative meeting (#6, "Is the $10/day automation ceiling still
right after Milestone B ships?" — real participant-allowlist agent
names that exist in the live `agents` table: ceo, cto, financial,
security, red-team; no real meeting exists in the live DB, disclosed
on both artboards):
- `MeetingDetailInline.dc.html` (Concept 1) — cost sprinkled across
  three existing components: the header meta line, a badge on each
  position card, a badge on each follow-up panel.
- `MeetingDetailPanel.dc.html` (Concept 2 — recommended) — one
  dedicated Cost panel placed directly under the header, mirroring
  Milestone A Task Detail's summary-strip precedent. Position cards
  and follow-up panels stay untouched.

See `ops/reviews/design-review-milestone-b.md` for the full review,
verdict, and specific recommendations relative to CTO's architecture.
