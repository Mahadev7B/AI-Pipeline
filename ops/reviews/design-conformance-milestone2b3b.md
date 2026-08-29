# Design conformance — Phase 2, Milestone 2B3B

TASK-010. Checked the planned Executive Meetings screens against the two
existing approved artifacts: `ops/EXECUTIVE_MEETINGS.md` (the Phase 2
design doc — the functional spec) and
`ops/mockups/control-center-phase-0/ExecutiveMeeting.dc.html` (the
Founder-approved Phase 0 mockup — the visual spec). Both already exist
and are approved; no new mockup work is needed for this milestone.

## What the mockup establishes (visual source of truth)

- Header: back-link, "Executive discussion" label, topic as a large
  display heading, "Raised by \<name\> · \<role\> · \<time\>" byline.
- A grid of position cards, one per participant — CEO Agent visually
  distinct (violet dashed border/background), Red Team visually distinct
  (red-tinted border/background), every other participant in the
  standard neutral panel style.
- A "requested perspective" card style for an agent added after the
  fact, labeled "— requested by \<name\>".
- A dashed "add another perspective" affordance.
- A follow-up conversational thread (violet Founder bubbles / neutral
  agent bubbles, same visual language as the Ask-Agent mockup).
- A two-column "Areas of agreement" / "Areas of disagreement" section.
- A decision panel: several preset decision-option buttons plus a
  "Confirm decision" action, with copy noting this logs to the
  operational record and assigns an ID automatically.

## What the design doc establishes (functional source of truth)

Five steps: Founder raises a question → Orchestrator + CEO Agent select
participants (real relevant expertise only, not every agent every time)
→ each participant states its position from its own real
responsibilities/frameworks → the record preserves positions, evidence/
assumptions, agreement, disagreement, unresolved questions, and a CEO-
synthesized recommendation (never an averaged vote) → the Founder
decides, with an important decision written to `DECISIONS.md` via the
`decisions` table, linked back to the meeting.

## Conformance findings

1. **Core visual language reused as-is**: position-card grid, CEO's
   violet-dashed distinction, Red Team's red-tinted distinction,
   agreement/disagreement two-column layout, decision-panel styling —
   all drawn from the same shared token system every Phase 2 screen has
   used since Milestone 1. No redesign.
2. **Deliberately deferred from this milestone** (routed to CTO as scope
   questions, not silently dropped): the "request another agent's
   perspective" mid-meeting affordance, and the meeting-scoped follow-up
   conversational thread. Both are real, additional interactive features
   layered on top of a complete meeting record — this milestone's job is
   the core real vertical slice the design doc's five steps describe
   (raise → select → position → synthesize → decide). Consistent with
   this project's established incremental-milestone pattern (2B1 shipped
   the write boundary before 2B2's Ask-Agent; 2B2 shipped one real agent
   invocation before 2B3A's concurrency foundation) — CTO to confirm
   this scoping and flag it explicitly in the architecture proposal
   rather than have it discovered later as a silent gap.
3. **Preset decision-option buttons**: the mockup shows several
   auto-generated candidate decisions as clickable buttons. Generating
   genuine, non-fabricated candidate options would require yet another
   synthesis step (and a real risk of inventing options that don't
   accurately reflect the discussion if done cheaply) — routed to CTO
   for a build-vs-simplify call; a free-text decision field (matching
   how the existing Decisions screen already works) is a legitimate,
   less risky alternative if CTO judges the preset-button synthesis not
   worth the complexity for v1.
4. **Founder identity in the byline**: the mockup says "Raised by Alex ·
   Founder · 9:40am" — per the precedent already established and fixed
   in Milestone 2A's CTO post-implementation review (no invented
   specific Founder name; "Founder" the role label only, matching the
   nav badge and Ask-Agent chat bubbles), the meeting byline must say
   "Founder," never "Alex."
5. **Founder vs. CEO Agent distinction**: preserved exactly as the
   mockup shows it (violet solid for Founder elsewhere in this system,
   violet *dashed* specifically for CEO Agent — the mockup's own
   position-card treatment for CEO already encodes this correctly; no
   change needed).
6. **Status must be real, not decorative**: any "in progress" / "agent
   contributing" state shown while a meeting is being gathered must
   come from real `agent_runs` rows (scope_type='meeting'), the same
   deterministic-status rule already enforced for every other screen —
   flagged for Development, not a mockup deviation.

## Verdict

Conformant, with three items explicitly routed to CTO for a scoping/
build decision rather than assumed: (a) confirm the mid-meeting
"request a perspective" and follow-up-thread features are out of this
milestone's scope, (b) decide preset-decision-buttons vs. free-text
decision, (c) confirm participant selection is genuinely CEO-driven (not
simplified to Founder-picks-a-checklist) — since the design doc is
explicit that Orchestrator + CEO select participants, and the Founder's
brief for this milestone said to implement "as previously specified."
