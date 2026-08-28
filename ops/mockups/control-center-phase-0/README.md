# Control Center Mockups — Phase 0

**v2 — refined per Founder feedback on v1.** The Founder approved v1's
information architecture (Command Center as Overview, Pipeline First as
the Pipeline tab, Agent First as the Agents tab) and asked for one more
design iteration before approving Phase 0. This directory holds that
refined round.

Published as one multi-artboard canvas — an Artifact, not application
code, same URL as v1 (this is an update, not a new artifact):

**https://claude.ai/code/artifact/57fcb90b-fc73-4182-8a3a-12b70cadf39d**

(Private by default — share it from the page's share menu if you want
someone else to open the link.)

## What's here

- `Main.dc.html` — **Overview, Style A (refined dark)**. Answers "what
  needs me / how's the company / what's being worked on / which agents
  are active / what just happened" in one viewport, no scrolling. Adds a
  real "Active Now" list (agent, current task, elapsed time) in place of
  v1's bare "4/14 working" count.
- `OverviewLight.dc.html` — **Overview, Style B (lighter premium)**. Same
  structure as `Main.dc.html`, different visual treatment — for comparing
  the two aesthetic directions side by side (see "Visual style" below).
- `Pipeline.dc.html` — **Pipeline, refined**. Six major stages (Product,
  Design, Architecture, Development, Review, Release), each containing
  its real detailed substates as nested lanes (e.g. Product → Brainstorm /
  Requirements) instead of one column per internal status.
- `Agents.dc.html` — **Agents, refined**. The 14-agent roster grouped by
  function (Executive, Product, Engineering, Operations, Oversight) and
  state-filterable (Working / Blocked / Waiting / Available); the
  Agent Capability detail panel from v1 is kept, now with an "Open
  conversation" affordance.
- `AgentConversation.dc.html` — **new**. Expands "Ask Agent" into a real
  multi-turn conversation example (Founder asking Developer about
  TASK-002), explicitly marked as saved/auditable against the task.
- `ExecutiveMeeting.dc.html` — **Executive Meeting, expanded**. The v1
  discussion card expanded to a full page: position statements, a
  requested extra perspective (Security), a follow-up exchange, agreement/
  disagreement, and a Founder decision panel that writes to `DECISIONS.md`.
- `canvas.json` — lays all six artboards out on one canvas.

Still static mockups (not a clickable prototype), still sample/placeholder
data only. No real task data, no real founder decision.

## Visual style — two directions shown, neither approved yet

- **A (dark, `Main.dc.html`)** — refined continuation of v1: near-black
  panels, warm-amber accent, `Space Grotesk` display type. Kept per the
  Founder's "do not throw it away" note, tightened for this round.
- **B (light, `OverviewLight.dc.html`)** — new premium-light direction:
  warm off-white background, deep bronze accent, `Fraunces` serif display
  paired with `Inter` body text — aiming for "calm executive stationery,"
  not generic light-mode admin UI.

See `../../MOCKUP_CRITIQUE.md` for the critique of both and a
recommendation — still pending Founder approval.

## Founder vs. CEO Agent

Every artboard marks the Founder with a solid avatar labeled
"FOUNDER · HUMAN" and the CEO Agent with a dashed hexagon avatar labeled
"CEO AGENT · AI ADVISOR" — never the same visual treatment, never merged.
