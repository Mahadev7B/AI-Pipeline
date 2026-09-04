# ARCHITECTURE.md

## System architecture (target — built across Phases 1–2, documented now)

Six concerns, kept behind clear interfaces so any one of them can be
replaced later without rewriting the rest of the system:

1. **Web UI (Control Center)** — the Founder-facing application (Phase 2).
   Reads live state, never writes directly to Git or to agent execution.
2. **Chief of Staff** — the only thing that decides what happens next and
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

- The Chief of Staff is the only writer of Task State. The UI reads Task
  State and sends founder actions (approve/reject/ask-agent) through the
  Chief of Staff — it does not mutate rows directly.
- No agent is hard-coded to one model or provider. Each agent's `model`
  field is `configurable`; the Model Registry (`/ops/models/`) is where a
  real choice eventually gets recorded, benchmarked, and approved per
  agent — not decided in this architecture doc.
- Skills (`/ops/skills/`) are tools an agent calls; they are not a
  replacement for the agent's own role, must-not list, or evaluation
  criteria.

## Derived UI state must be deterministic, never invented

Some values shown in the Control Center are computed *from* persisted
state rather than stored directly — that computation must be
deterministic application code, never an LLM narrating what it thinks
the state probably is. This applies at minimum to:

- **Company health** — computed from the real counts of blocked tasks,
  open risks, and review failures in Task State, not a model's summary
  judgment of "how things feel."
- **Agent status (Working / Waiting / Blocked / Available)** — derived
  from whether an agent currently has an assigned, in-progress task in
  `tasks`/`task_status_history`, and whether it's waiting on a specific
  named blocker — not asserted independently per screen. The Overview's
  "Active Now" count and the Agents view's state filter chips read the
  same underlying agent-state query; if they'd disagree, that's a bug in
  the query layer, not a rendering choice either screen is free to make.
- **Progress percentages** — computed from real completed subtasks or an
  equivalent objective measure (rule 22, `CODING_STANDARDS.md`), never a
  round-sounding number an agent offers because it seems about right.
- **Elapsed activity time** — computed from `agent_activity.created_at`
  timestamps against the current time, not estimated.

An agent may *describe* its own activity in prose (that's the point of
Agent Conversations) — but the structured badges, counts, and bars the
Control Center renders come from one queryable state layer that both the
Overview and every dedicated tab read identically. See also rule 23,
`CODING_STANDARDS.md`.

## Explicitly not built yet

No code implementing any of the above exists yet. This document describes
the target shape for Phase 1 (Task State + Agent Execution wiring) and
Phase 2 (Web UI), gated by Founder approval of this proposal.
