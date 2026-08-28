# ROADMAP.md

Four phases. Each phase requires a separate, explicit Founder go-ahead before
the next one starts. No phase begins itself.

## PHASE 0 — Design & Architecture Proposal *(APPROVED 2026-08-28 — see DEC-003)*

Inspect the repo and installed Claude Code skills; propose the agent
operating model (14 agents incl. CEO and Financial), workflow, tools/
permissions per agent, templates, Skill Registry, Model Registry, and
Executive Meeting design — documentation only. Produce three real Control
Center mockups via the `design` skill. Critique and recommend one.

Explicitly out of scope for Phase 0 (all now superseded by Phase 1):
instantiating the SQLite database, writing any Control Center code, wiring
real Claude Code subagent configs, selecting/downloading any model, running
the sample task, or touching the actual product.

## PHASE 1 — Foundation *(APPROVED 2026-08-28 — CLOSED, see DECISIONS.md DEC-004)*

- Incorporate the data-model clarifications (agent execution runs,
  structured risks, objective task-step progress, a minimal projects
  entity) into `DATA_MODEL.md`, reviewed by Red Team before implementation.
- Instantiate the SQLite operational database from `DATA_MODEL.md`.
- Wire the 14 agent definitions as real, usable Claude Code subagents.
- Execute the `TASK-001` sample walkthrough end-to-end (fake work only) to
  prove the pipeline, including one mockup rejection, one design decision,
  a Developer → QA handoff, a QA failure and fix, a re-review, a Founder
  Approval example, and a Marketing touchpoint.
- Generate real status reporting (`ops/reports/CURRENT_STATUS.md`) from the
  live database.
- Finalize the durable docs (`PROJECT.md`, `ARCHITECTURE.md`, etc.) against
  what Phase 1 actually built.
- Workflow for this phase: Architecture → Red Team → Development → Code
  Review → QA → Security, same discipline the ops system itself defines.
  **Stop** after Security review and show the Founder what's truly
  functional vs. still mocked before Phase 2 begins.

## PHASE 2 — Control Center *(current phase, separately gated from Phase 1)*

Build the Founder-approved mockup direction into the real web application:
project overview, pipeline visualization, agent panel + detail/capability
view, Ask-Agent conversation interface, Executive Meeting UI, Founder Inbox,
activity feed, QA/review failures, decision history, project health, release
information.

**Gates, before any significant implementation:**
- CTO reviews and confirms the proposed Phase 2 architecture aligns with
  the Phase 1 foundation (schema, `opsdb.py`, subagent wiring) before
  Development starts on it.
- Red Team challenges the plan before Development begins — same
  discipline as Phase 1's schema review.
- The approved refined-dark Command Center direction (Style A —
  `ops/mockups/control-center-phase-0/Main.dc.html`) remains the visual
  source of truth.
- The Control Center reads real state from the Phase 1 operational
  database. Status, progress, and health are never recreated as mocked
  or hand-written values — they are computed the same way
  `ops/db/report.py` already computes them (shared logic, not a
  re-implementation that could drift).
- The Phase 1 schema and operating rules are not casually changed. Any
  meaningful architecture change goes back through CTO → Red Team and is
  documented, same as a schema change would be.
- CTO's role during Phase 2 extends past pre-development approval to
  **post-implementation architectural conformance** — watching for
  architecture drift, stale assumptions, platform gaps, data-model
  inconsistencies, unnecessary complexity, dependency risk, and
  technical debt as each milestone ships. CTO does not fix
  implementation directly; findings route to the responsible agent and
  still pass Code Review, QA, and Security.
- The two Phase 1 limitations (approval-decide not identity-
  authenticated; Bash not scoped below the tool-category level) are
  tracked as open risks (`risks` table, company-scoped) through Phase 2.
  Neither is hidden or silently marked resolved without a real technical
  fix — see `DECISIONS.md` DEC-004.

Phase 2 ships as a sequence of small, separately reviewed milestones
(Architecture → Red Team → Development → Code Review → QA → Security
each time), not one large build — see `ops/reports/CURRENT_STATUS.md`
and the task history for what's shipped so far.

**Milestone 1 — DONE (TASK-004):** a static, read-only Overview page
(`ops/control-center/generate_overview.py` → `overview.html`) reading
real Company Health, agent status, pipeline, activity, and Founder Inbox
state from the live database. No write actions yet. See
`ops/reviews/cto-phase2-architecture.md`,
`ops/reviews/red-team-phase2-architecture.md`, and
`ops/reviews/cto-phase2-milestone1-conformance.md`.

**Milestone 2 (not started):** the remaining screens (Pipeline, Agents,
Conversation, Meetings) and, only once a real interactive/write feature
needs it, a live process — not before.

## PHASE 3 — Automated Orchestration *(after Phase 2 is complete)*

Automate the handoffs already defined in the workflow (Developer complete →
Code Review; Code Review PASS → QA / FAIL → Developer; QA PASS → Security /
FAIL → Developer; Security PASS → Release prep). Production deployment stays
gated behind explicit Founder approval — this is never automated.

## Rule

Do not skip a phase gate. A phase that is technically easy to start early is
still not started early — Founder approval is the gate, not agent judgment.
