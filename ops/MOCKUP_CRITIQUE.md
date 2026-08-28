# MOCKUP_CRITIQUE.md — Control Center, Phase 0

Artifact: https://claude.ai/code/artifact/57fcb90b-fc73-4182-8a3a-12b70cadf39d
Source: `ops/mockups/control-center-phase-0/`

**Status: v2's direction is approved conceptually.** A v2.1 correction
pass (consistency fixes only, no redesign) followed — see
`ops/mockups/control-center-phase-0/README.md`, "v2.1 correction pass"
for the exact list. Final Phase 0 approval is pending that pass.

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

---

## v2 refinement (this round)

The Founder approved the v1 information architecture (C → Overview, A →
Pipeline tab, B → Agents tab — see DEC-001) and asked for one more
iteration before approving Phase 0. Same artifact, updated in place.

### Overview
**Change:** compressed to fit one viewport with no scrolling, answering
all five of the Founder's stated questions (what needs me / company
health / what's being worked on / which agents are active / what just
happened) without requiring a scroll. "4/14 working" replaced with a real
"Active Now" list — agent, current task, elapsed time — per the Founder's
explicit ask.
**Tradeoff:** to fit above the fold, most sections are now compact
summaries with a "view more" link rather than full detail — that's the
intended design (Overview orients, the dedicated tabs go deep), but worth
confirming it doesn't feel too terse in real use once real data volume
is higher than this sample.

### Pipeline
**Change:** collapsed to six major stages (Product, Design, Architecture,
Development, Review, Release), each showing its real substates as nested
lanes inside the stage rather than one column per internal status. Both
the simple stage and the exact detailed status are visible at once, as
asked.
**Tradeoff:** Review's three sub-lanes (Code Review / QA / Security) make
that column taller than the others — acceptable at 5 features, worth
watching once more features are active in Review simultaneously.

### Agents + Agent Conversation
**Change:** roster now grouped by function (Executive, Product,
Engineering, Operations, Oversight) with state-filter chips (Working /
Blocked / Waiting / Available) at the top, so it reads as an org chart,
not a flat grid. "Ask Agent" is now a real conversation view
(`AgentConversation.dc.html`) with a multi-turn example and an explicit
"saved to TASK-002 · auditable" marker, addressing the Founder's
persistence/auditability requirement directly in the mockup.
**Tradeoff:** grouping by function means an agent's position in the list
no longer directly reflects urgency (a Blocked agent in Operations sits
below a Working agent in Engineering) — the state-filter chips are the
mitigation, not a replacement for state-first sorting; worth deciding
which the Founder actually reaches for first in real use.

### Executive Meeting
**Change:** expanded to a full page supporting all four asks — a
follow-up exchange shown inline, a "request another agent's perspective"
affordance (with Security's requested perspective shown as a worked
example), explicit Areas of Agreement/Disagreement, and a Founder
decision panel with real options plus a note that confirming writes to
`DECISIONS.md`.
**Tradeoff:** none significant — this is close to what was asked for
directly; the main open question is whether decision options should
always be pre-generated (as shown) or sometimes free-text, which is a
Phase 2 interaction-design question, not a Phase 0 one.

### Visual style — A (dark) vs. B (light)

**A — Refined dark** (`Main.dc.html`): continues v1's direction, tightened.
Reads as an operations/command console — appropriate for a tool whose job
is actively supervising AI agents in real time. Risk: dark, dense
dashboards can tip into "SOC/ops-tool" territory if not kept disciplined;
this pass leans on generous spacing and a single accent to avoid that.

**B — Lighter premium** (`OverviewLight.dc.html`): warm off-white,
serif display type, bronze accent — reads closer to a calm executive
workspace than an operations console. Easier on the eyes for long
reading sessions; less obviously "there's a system running underneath."

**Recommendation: A, the refined dark direction**, as the primary style —
this product's core value is *watching AI agents work in real time*, and
a console aesthetic communicates that more directly than a document-like
light theme. B is a genuinely strong alternative, not a placeholder;
worth keeping on file if the Founder decides later that "calm and
document-like" matters more than "live operations" as the dominant
feeling once real usage patterns are known.

This is a recommendation, not a decision — logged as DEC-002 in
`DECISIONS.md`, pending Founder approval alongside the rest of this
refinement.
