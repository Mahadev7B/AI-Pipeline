# DECISIONS.md — Decision Log

Append-only. Never silently reverse a prior decision — if an agent believes
an existing decision should change, it proposes a **new** decision entry
and runs it through review; the old entry stays as-is for history.

From Phase 1 onward, this file is the git-readable mirror of the `decisions`
table in the operational SQLite database (see `DATA_MODEL.md`) — SQLite is
the writable source of truth, this file is the durable, diffable export.

## Format

```
### DEC-<NNN> — <short title>
Date: <YYYY-MM-DD>
Problem: <what needed deciding>
Options considered: <list>
Decision: <what was chosen>
Reason: <why>
Tradeoffs: <what was given up>
Agent recommending it: <agent name>
Founder approval: <required/not required — and outcome if resolved>
```

## Log

### DEC-001 — Control Center mockup direction (recommended, pending Founder approval)
Date: 2026-08-28
Problem: Which of three Control Center visual/structural directions should Phase 2 build from?
Options considered: Variant A (Pipeline First), Variant B (Agent First), Variant C (Command Center) — see `MOCKUP_CRITIQUE.md` for full critique of each.
Decision: Recommend Variant C (Command Center) as the landing "Overview" screen, with Variant A's pipeline design as the dedicated "Pipeline" tab and Variant B's agent roster/capability view as the dedicated "Agents" tab — reconciling all three rather than discarding two.
Reason: The Founder's stated priority is minimizing interruptions to founder-only decisions; Command Center is the only variant that puts Founder Inbox, Risks, and Executive Discussion front-and-center on first open, while still preserving A's and B's strengths as deeper views.
Tradeoffs: Command Center is the busiest single screen of the three; agent capability detail is a drill-in rather than visible on the landing view.
Agent recommending it: Design Agent (critique), Orchestrator (log entry).
Founder approval: **Required — this is a Phase 0 recommendation awaiting explicit Founder approval before Phase 2 (Control Center) can begin.**
