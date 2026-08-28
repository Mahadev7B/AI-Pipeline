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

## PHASE 1 — Foundation *(complete, awaiting Founder review before Phase 2)*

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

## PHASE 2 — Control Center *(after Phase 1 is complete)*

Build the Founder-approved mockup direction into the real web application:
project overview, pipeline visualization, agent panel + detail/capability
view, Ask-Agent conversation interface, Executive Meeting UI, Founder Inbox,
activity feed, QA/review failures, decision history, project health, release
information.

## PHASE 3 — Automated Orchestration *(after Phase 2 is complete)*

Automate the handoffs already defined in the workflow (Developer complete →
Code Review; Code Review PASS → QA / FAIL → Developer; QA PASS → Security /
FAIL → Developer; Security PASS → Release prep). Production deployment stays
gated behind explicit Founder approval — this is never automated.

## Rule

Do not skip a phase gate. A phase that is technically easy to start early is
still not started early — Founder approval is the gate, not agent judgment.
