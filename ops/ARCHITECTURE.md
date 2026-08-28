# ARCHITECTURE.md

## System architecture (target — built across Phases 1–2, documented now)

Six concerns, kept behind clear interfaces so any one of them can be
replaced later without rewriting the rest of the system:

1. **Web UI (Control Center)** — the Founder-facing application (Phase 2).
   Reads live state, never writes directly to Git or to agent execution.
2. **Orchestrator** — the only thing that decides what happens next and
   assigns work. Talks to Task State and to Agent Execution; the UI never
   talks to Agent Execution directly.
3. **Task state** — the live operational record (SQLite from Phase 1 — see
   `DATA_MODEL.md`). Single writable source of truth for status, ownership,
   activity, messages, approvals, handoffs, decisions, QA/review results,
   deployments, and meetings.
4. **Agent execution** — however an individual agent's turn actually runs
   (currently: a Claude Code subagent). Not hard-coded to one model or
   provider — see `AGENT_ARCHITECTURE.md` and `/ops/models/`.
5. **Git** — source of truth for code and for durable narrative docs
   (`PROJECT.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `CODING_STANDARDS.md`,
   `SECURITY.md`). `DECISIONS.md` is a git-readable generated mirror of the
   `decisions` table once the database exists in Phase 1 — one writable
   source (SQLite), one durable human-readable export (Markdown/Git).
6. **Persistence** — file storage for anything durable that isn't rows in
   SQLite (agent doc files, skill/model registry entries, task templates).

## Why the split

- SQLite gives the Control Center something fast and queryable to render
  live (who owns what, what's blocked, what needs Founder approval) without
  parsing Markdown on every page load.
- Markdown/Git gives every decision and architectural choice a durable,
  diffable, human-readable record that survives independent of any
  database file, and preserves *why* — not just *what*.

## Coupling rules

- The Orchestrator is the only writer of Task State. The UI reads Task
  State and sends founder actions (approve/reject/ask-agent) through the
  Orchestrator — it does not mutate rows directly.
- No agent is hard-coded to one model or provider. Each agent's `model`
  field is `configurable`; the Model Registry (`/ops/models/`) is where a
  real choice eventually gets recorded, benchmarked, and approved per
  agent — not decided in this architecture doc.
- Skills (`/ops/skills/`) are tools an agent calls; they are not a
  replacement for the agent's own role, must-not list, or evaluation
  criteria.

## Explicitly not built yet

No code implementing any of the above exists yet. This document describes
the target shape for Phase 1 (Task State + Agent Execution wiring) and
Phase 2 (Web UI), gated by Founder approval of this proposal.
