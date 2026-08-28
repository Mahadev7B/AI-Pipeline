# PROJECT.md — AI Software Company Operating System

Status: **PHASE 1 — FOUNDATION complete, awaiting Founder review before Phase 2** (Phase 0 approved 2026-08-28 — see `DECISIONS.md` DEC-003)

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
  DATA_MODEL.md            future SQLite schema (design doc only, Phase 0)
  EXECUTIVE_MEETINGS.md    multi-agent discussion capability design
  MOCKUP_CRITIQUE.md       critique + recommendation for the 3 Control Center mockups
  AGENT_STATUS.md          workflow statuses and legal transitions
  /ops/agents/             one file per agent (14 total)
  /ops/skills/             Skill Registry (real, installed skills only)
  /ops/models/             Model Registry (design only — no model selected)
  /ops/templates/          task / decision / founder-approval / handoff templates
  /ops/tasks/              individual task files (created from Phase 1 onward)
  /ops/approvals/          PENDING.md / RESOLVED.md (created from Phase 1 onward)
  /ops/reports/            CURRENT_STATUS.md (created from Phase 1 onward)
```

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
