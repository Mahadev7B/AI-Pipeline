# Design conformance — Phase 2, Milestone 2B2

TASK-007. Checked the planned Ask-Agent screen against the Founder-approved
Phase 0 mockup, `ops/mockups/control-center-phase-0/AgentConversation.dc.html`
(Style A / DEC-002, the same dark visual system every Phase 2 screen has
used since Milestone 1).

## What the mockup establishes (source of truth)

- Header: back-link to Agents, agent avatar, agent name + live status,
  a scope indicator ("Scope: Task · TASK-002 ▾ · auditable").
- Message list: Founder messages right-aligned in a solid violet bubble
  labeled "<name> · Founder · <time>"; agent messages left-aligned in a
  neutral panel-colored bubble labeled "<agent-name> · <time>".
- Input bar: "Ask <Agent> a follow-up…" placeholder + a Send button.
- A footer note: "This one is task-scoped. Conversations can also be
  project-, agent-, or meeting-scoped — none require a task ID. Every
  scope is persisted and auditable, never a side channel."

## Conformance findings

1. **Bubble layout, colors, and labeling reused as-is.** Violet
   solid/right for Founder, neutral panel/left for agent, timestamp
   captions — no deviation. This is exactly the CSS token system already
   shared via `layout.py`, so no new visual system is introduced.
2. **Founder label**: the mockup's illustrative bubbles say "Alex ·
   Founder." Per the precedent already established and disclosed in
   Milestone 2A's CTO post-implementation review (`ops/reviews/...` —
   the nav badge's hardcoded "Alex" was replaced with the role label
   "Founder," since no founder/users table exists and inventing a
   specific name is exactly the fake-data pattern this project's data
   rules forbid), the chat bubbles use "Founder" only, not "Alex,"
   continuing that same fix rather than reintroducing the issue in a new
   screen.
3. **Scope selector**: the mockup shows a switchable scope control
   ("Task · TASK-002 ▾"). Milestone 2B2's brief scopes conversations to
   company/general only when started from Agent Detail (no task/project/
   meeting picker). Routed to CTO as a legitimate simplification
   question rather than silently deviating — see the architecture
   proposal's "Conversation scope" section for the resolution and
   reasoning; the mockup's scope *concept* (multiple non-task-required
   scopes, all persisted and auditable) is preserved, only the
   interactive picker is deferred.
4. **Which agent is invocable**: the mockup illustrates "Developer" as
   the example agent. Milestone 2B2's brief explicitly restricts real
   invocation to read-oriented roles (CTO/QA/CEO/Financial/
   Project-Manager) — a scope decision from the Founder's brief, not a
   design deviation; the mockup's chrome pattern applies identically
   regardless of which agent is shown.
5. **Status must be real, not decorative.** The mockup's header shows
   "● Working — TASK-002" as static illustrative copy. Milestone 2B2's
   hard requirement ("must never display 'Working' simply because an
   LLM generated that word... status remains deterministic from
   persisted execution state") means this header status must be wired
   to a real `agent_runs` row, not copied from the mockup's illustrative
   text — flagged for Development, not a mockup deviation since the
   mockup was never meant to imply otherwise.

## Verdict

Conformant. No redesign — same dark visual system, same bubble/header/
input pattern, one disclosed simplification (scope picker deferred) and
one continuation of an already-approved fix (no invented Founder name).
Routed to CTO for the architecture question in item 3 and confirmation
that item 5's status display is backed by real state before Development
starts.
