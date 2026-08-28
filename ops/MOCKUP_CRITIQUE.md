# MOCKUP_CRITIQUE.md — Control Center, Phase 0

Artifact: https://claude.ai/code/artifact/57fcb90b-fc73-4182-8a3a-12b70cadf39d
Source: `ops/mockups/control-center-phase-0/`

## Variant A — Pipeline First

**Strengths**
- Directly answers the Founder's most-asked question — "what's being
  worked on and where is it?" — in one glance. Status is unambiguous:
  a card sits in exactly one stage column, no interpretation needed.
- Fits the founder's own "keep MVP scope small" instinct: with 5 features
  it's calm, not cluttered.
- The visible QA-failure callout does exactly what "failures must be
  visible" asked for.

**Weaknesses**
- Agent information is compressed into a thin sidebar. "Click any agent
  and ask it something" isn't a first-class action here — it's an
  afterthought.
- Nine stage columns get cramped fast once more than a handful of
  features are active at once; doesn't scale gracefully.
- No natural home for an Executive Meeting — there's nowhere for a
  cross-cutting question to live.

## Variant B — Agent First

**Strengths**
- Directly answers "what is each agent doing right now" and delivers the
  founder's exact "Agent Capability View" spec (model, why that model,
  skills, frameworks, tools, permissions, evaluation history, confidence,
  Ask Agent) in the expanded panel — this is the closest of the three to
  what "click any agent" was actually asking for.
- Makes the 14-agent org (including CEO and Financial, clearly marked
  distinct from the Founder) tangible instead of abstract.

**Weaknesses**
- The pipeline is reduced to a thin strip — "where is each feature"
  takes more effort to answer than it should for what the Founder said
  is a top priority.
- As agents accumulate real activity, a flat grid of 14+ cards is the
  variant most likely to feel like "generic admin software" if it isn't
  actively curated (e.g. sorted by state, not just role order).
- Like A, no natural home for a cross-cutting Executive Meeting.

## Variant C — Command Center

**Strengths**
- Only variant that surfaces founder-only items (Inbox, Risks,
  Executive Discussion) as first-class, front-and-center content — and
  those are exactly the items the Founder said should interrupt them,
  per the founder-approval rules. Everything else is designed to be
  handled without asking.
- The Executive Discussion panel has a real, prominent home here, with
  the exact shape requested (per-agent positions, agreement/disagreement,
  decision required, Make Decision) — it isn't bolted onto a layout that
  wasn't built for it, the way it would be in A or B.
- Answers the widest span of the Founder's stated questions
  (what's being worked on / who owns what / what's blocked / what needs
  me / what's ready to release / what shipped) in a single screen — the
  "operate a company" feeling the brief asked for.

**Weaknesses**
- Highest information density of the three — busiest screen, most
  scrolling, and the one most at risk of sliding into clutter if new
  panels get added without discipline later.
- No agent gets the full expanded capability view here — that's
  necessarily a drill-in from elsewhere, not visible on this screen.

## Recommendation

**Command Center (Variant C)** as the landing view — but not as a
replacement for A and B's ideas. The nav bar already sketched into all
three mockups (Overview / Pipeline / Agents / Meetings / Decisions) is
the right reconciliation: **C becomes "Overview,"** and **A's pipeline
design becomes the dedicated "Pipeline" tab, B's agent roster + capability
view becomes the dedicated "Agents" tab.** Nothing from A or B is thrown
away — they become the deep-dive destinations Command Center's compact
sections link out to.

Reasoning: the Founder was explicit that agents should not constantly ask
"what should I do next," and should only interrupt for founder-only
decisions — which means the *first screen opened* should optimize for
"what needs me" and "what's the state of the company," not for either
pipeline mechanics or agent mechanics alone. Command Center is the only
variant built around that priority; Pipeline First and Agent First are
each excellent as the deeper view once the Founder has decided where to
look next.

## What this recommendation does not decide

- Visual theme (dark "operating console," warm amber accent, `Space
  Grotesk`) is Design's assumption for Phase 0, not confirmed with the
  Founder — flag any change before Phase 2 build-out.
- This is a direction recommendation, not implementation — no Control
  Center code exists yet (see `ROADMAP.md` — that's Phase 2, gated
  behind Founder approval of this direction).
