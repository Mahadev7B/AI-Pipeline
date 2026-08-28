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
Founder approval: **APPROVED 2026-08-28.** Command Center = Overview, Pipeline First = Pipeline tab, Agent First = Agents tab.

### DEC-002 — Control Center visual style: dark vs. light (recommended, pending Founder approval)
Date: 2026-08-28
Problem: Which visual treatment should the approved Command Center structure use — the existing dark "operating console" direction, or a new lighter/premium alternative?
Options considered: Style A — refined dark (`Main.dc.html`); Style B — lighter premium (`OverviewLight.dc.html`) — see `MOCKUP_CRITIQUE.md`, "Visual style" for full critique.
Decision: Recommend Style A (refined dark) as the primary direction; keep Style B on file as a considered alternative rather than discarding it.
Reason: The product's core value is watching AI agents work in real time — a console aesthetic communicates that more directly than a document-like light theme, which reads calmer but less "live."
Tradeoffs: A risks tipping into "ops-tool" territory if not kept disciplined; B is easier on the eyes for long sessions but undersells that a live system is running underneath.
Agent recommending it: Design Agent.
Founder approval: **APPROVED 2026-08-28.** Refined dark (Style A) is the default visual direction; Style B (light) is retained as an optional future theme, not built in Phase 2 unless separately requested.

### DEC-003 — Phase 0 final approval
Date: 2026-08-28
Problem: Whether the Phase 0 architecture proposal (14-agent operating model, workflow, templates, Skill/Model Registry, Executive Meetings) and the Control Center design direction (DEC-001, DEC-002) are approved to proceed into Phase 1 — Foundation.
Options considered: Approve as-is; request further iteration; reject and restart.
Decision: **APPROVED.** Phase 0 is complete. Phase 1 — Foundation begins, scoped to: instantiating the SQLite operational database (per the data-model clarifications below), wiring the 14 agent definitions as real Claude Code subagents, executing the TASK-001 sample walkthrough, and generating real status reporting. Phase 2 (Control Center UI) remains explicitly out of scope until Phase 1 is reviewed and separately approved.
Reason: Two rounds of mockup refinement (v2, v2.1) resolved every open concern the Founder raised; the remaining data-model clarifications (agent_runs, risks, task_steps, projects) are architecture-level fixes, not design changes.
Tradeoffs: None — this is a gate opening, not a scope tradeoff.
Agent recommending it: Orchestrator.
Founder approval: **APPROVED 2026-08-28.**

### DEC-004 — Phase 1 Foundation complete, two known gaps disclosed
Date: 2026-08-28
Problem: Whether Phase 1 (SQLite operational database, 14 wired subagents, TASK-001 walkthrough, real status reporting) is complete and ready for Founder review before Phase 2 begins.
Options considered: Declare complete with gaps disclosed; hold Phase 1 open until gaps are closed.
Decision: Declare Phase 1 **complete**, with two gaps explicitly disclosed rather than silently accepted: (1) `approval-decide` has no real identity check — a `--confirm-founder-decision` flag makes it a deliberate act but not enforced authentication; (2) subagent `Bash` tool grants are not scoped below the tool-category level, so a subagent's actual shell access is broader than its documented Permissions section implies. Neither blocks Phase 1's stated goal (a working, auditable, deterministic operational core); both require an identity/permission layer that is Phase 2/3 (Control Center) scope.
Reason: Holding Phase 1 open until these are closed would mean waiting on infrastructure (real user auth, finer-grained tool scoping) that doesn't exist yet and wasn't asked for in Phase 1 — better to ship a disclosed, honest state than delay for an unscoped fix.
Tradeoffs: The Founder is trusting procedural/documented enforcement (agent role docs, CLI speed bumps) over technical enforcement for these two specific actions until Phase 2 or later.
Agent recommending it: Security (see `ops/reviews/security-phase1.md`), Orchestrator.
Founder approval: **Pending — this is what Phase 1's completion report is asking the Founder to review.**
