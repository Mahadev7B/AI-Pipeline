# Control Center Mockups — Phase 0

**v2.1 — correction pass on the approved v2 direction.** The Founder
approved v1's information architecture and, separately, v2's design
direction conceptually. This pass makes no design changes — it only
fixes seven consistency/correctness issues the Founder flagged before
giving final Phase 0 approval. See "v2.1 correction pass" below for the
exact list.

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
  TASK-002), shown as task-scoped here but explicitly noting a
  conversation can be project-, agent-, or meeting-scoped instead — all
  scopes are persisted and auditable, none require a task.
- `ExecutiveMeeting.dc.html` — **Executive Meeting, expanded**. The v1
  discussion card expanded to a full page: position statements, a
  requested extra perspective (Security), a follow-up exchange, agreement/
  disagreement, and a Founder decision panel that logs the decision to the
  operational record (SQLite, from Phase 1) with an auto-assigned ID —
  `DECISIONS.md` is generated from that record, not written to directly.
- `canvas.json` — lays all six artboards out on one canvas.

## v2.1 correction pass

The Founder approved v2's direction conceptually and asked for one
consistency/correction pass before final Phase 0 approval — no redesign.
Seven fixes, all content/copy-level:

1. **Agent-status counts now agree everywhere.** Overview's "Active Now"
   and the Agents view's state chips are drawn from the same 14-agent
   sample state (5 Working, 1 Blocked, 2 Waiting, 6 Available) — CEO Agent
   was missing from Overview's list while counted as Working in Agents;
   both now show it.
2. **Removed the hardcoded `DEC-002` reference** from the Executive
   Meeting's decision panel — a real system assigns decision IDs, a
   mockup shouldn't guess one.
3. **Corrected decision source-of-truth language** — the Executive
   Meeting no longer implies it writes to `DECISIONS.md` directly; it
   logs to the operational record, which generates the `DECISIONS.md`
   entry.
4. **Marketing/Launch Prep restored** as a parallel, non-blocking lane
   inside Pipeline's Release stage (still six major stages, nothing
   added as a seventh).
5. **Agent Conversation generalized** beyond task-only — badge now reads
   "Scope: Task · TASK-002" with a note that project-, agent-, and
   meeting-scoped conversations exist too; `DATA_MODEL.md`'s `messages`
   table updated to match (a `scope` column, `project_id` added,
   `task_id`/`meeting_id` both optional).
6. **Documented, in `ARCHITECTURE.md`**, that Company Health, agent
   Working/Waiting/Blocked/Available status, progress percentages, and
   elapsed time must all be computed from persisted state — never
   generated as free text by an LLM.
7. **Restored Approve/Reject/Discuss** on the Founder Inbox item in both
   Overview treatments — v2's compression to fit one viewport had
   dropped Reject.

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
