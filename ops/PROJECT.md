# PROJECT.md — AI Software Company Operating System

Status: **PHASE 2 — CONTROL CENTER** (Phase 0 approved 2026-08-28 — DEC-003; Phase 1 approved and closed 2026-08-28 — DEC-004)

## What this is

A lightweight, git/markdown-based operating system that lets a set of specialized
Claude Code agents work like a disciplined software team, with the Founder
retaining final authority over money, irreversible, legal, and major-direction
decisions. No Jira/Linear/Monday/TFS or other paid PM software — everything is
files in this repo plus (from Phase 1 onward) a local SQLite database for live
operational state.

This system does **not** build the founder's actual product. It is the
scaffolding that will later help agents build it.

## Founder vs. CEO Agent

These are never the same entity:

- **Founder** — the human. Sole holder of final authority: money, legal risk,
  production deployment, credentials, major architecture/product-direction
  decisions, and anything irreversible or externally visible.
- **CEO Agent** — an AI executive-strategy advisor (see `/ops/agents/ceo.md`).
  It synthesizes company-level recommendations and can be overruled by the
  Founder at any time. It cannot spend money, deploy, or override a review
  gate.

Every document and every Control Center mockup in this system keeps these two
visually and structurally distinct.

## Where things live

```
/ops
  PROJECT.md              this file
  ROADMAP.md               the 4-phase plan and what gates each phase
  ARCHITECTURE.md          system architecture + loose-coupling principle
  AGENT_ARCHITECTURE.md    the foundational "what is an agent" rule
  DECISIONS.md             decision log (append-only, never silently reversed)
  CODING_STANDARDS.md      the 24 shared engineering rules
  SECURITY.md              security/privacy posture and rules
  DATA_MODEL.md            the operational database schema (implemented — ops/db/schema.sql)
  EXECUTIVE_MEETINGS.md    multi-agent discussion capability design (Phase 2, not built yet)
  MOCKUP_CRITIQUE.md       critique + recommendation for the 3 Control Center mockups
  AGENT_STATUS.md          workflow statuses and legal transitions
  /ops/agents/             one file per agent (14 total) — role docs; see also .claude/agents/
  /ops/skills/             Skill Registry (real, installed skills only)
  /ops/models/             Model Registry (design only — no model selected)
  /ops/templates/          task / decision / founder-approval / handoff templates
  /ops/db/                 operations.sqlite3 (the live database), schema.sql,
                           opsdb.py (the only writer), report.py, derived_state.py,
                           README.md (test-vs-live database convention)
  /ops/control-center/     generate_overview.py + overview.html (Phase 2 Milestone 1)
  /ops/reviews/            Red Team / Code Review / Security / CTO conformance reports
  /ops/reports/            CURRENT_STATUS.md — regenerate with `python3 ops/db/report.py`
  /ops/mockups/            the Phase 0 Control Center mockups (visual source of truth)
.claude/agents/            the 14 agents wired as real, invocable Claude Code subagents
```

Individual per-task markdown files (`/ops/tasks/TASK-NNN.md`) and
`/ops/approvals/PENDING.md`/`RESOLVED.md`, mentioned in earlier drafts of
this document, were superseded before Phase 1 shipped: tasks and
approvals live in `operations.sqlite3` as structured rows, not hand-
maintained markdown files — see `ops/DATA_MODEL.md`.

## Seeing current status

- `python3 ops/db/report.py` → regenerates `ops/reports/CURRENT_STATUS.md`
  (git-tracked markdown snapshot).
- `python3 ops/control-center/generate_overview.py` → regenerates
  `ops/control-center/overview.html`, open it in a browser for the
  Founder-facing dark Overview page (Phase 2 Milestone 1 — read-only,
  real data, no write actions yet).

Both read `ops/db/operations.sqlite3` directly and compute everything
via `ops/db/derived_state.py` — neither is hand-edited.

## Founder approval rules

Agents proceed independently whenever allowed. They escalate to the Founder
only for: spending money, buying software or paid infrastructure, purchasing
a domain/mailbox/service, signing a contract, accepting meaningful legal
risk, production deployment, deleting important data, handling credentials,
a major architecture change, a major product-direction decision, or any
irreversible/externally-visible action. See `/ops/templates/founder-approval.md`
for the escalation format.

## Skills vs. agents

Skills (the Claude Code skills actually installed in this environment) are
**tools** an agent uses — see `/ops/skills/`. They never replace the agent
architecture defined in `/ops/AGENT_ARCHITECTURE.md` and `/ops/agents/*.md`.
