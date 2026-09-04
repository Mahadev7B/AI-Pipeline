# EXECUTIVE_MEETINGS.md — Multi-Agent Discussion Capability

**Design document for Phase 2 (Control Center).** Nothing here is built or
run in Phase 0 — this defines the shape the feature must take.

## What it's for

Some questions don't belong to one agent — e.g. "Should PDF support be part
of the MVP?" touches Product, CTO, Financial, Marketing, QA, and Red Team
differently. An Executive Meeting is how the system produces one
synthesized view of a cross-cutting question without pretending any single
agent owns the answer, and without making the Founder read six separate
reports to find out where they disagree.

## How it works

1. **Founder raises a question** (free text, e.g. via the Control Center's
   "Ask the team" affordance — see `MOCKUP_CRITIQUE.md` / the Command
   Center and Executive Discussion mockups).
2. **Chief of Staff + CEO Agent select participants.** Only agents with real
   relevant expertise join — not every agent speaks on every issue. Typical
   participants and their lens:
   - **CEO** — company-level strategic view.
   - **Product** — customer/value impact.
   - **CTO** — technical implications.
   - **Financial** — cost/economics/ROI (only when the question has a real
     financial dimension).
   - **Marketing** — market-positioning impact.
   - **QA** — testing/quality implications.
   - **Security** — privacy/security implications, where relevant.
   - **Red Team** — reasons *not* to proceed; assumptions to challenge.
3. **Each participant states its position** from its own responsibilities
   and frameworks (`/ops/agents/*.md`) — not a generic opinion. Evidence
   and assumptions are stated alongside the position, not left implicit.
4. **The record preserves, explicitly, per meeting** (see the `meetings`
   table in `DATA_MODEL.md`): each agent's position, its evidence/
   assumptions, areas of agreement, areas of disagreement, unresolved
   questions, and a synthesized recommendation (produced by CEO, not by
   averaging votes).
5. **The Founder decides.** The meeting produces a recommendation, never a
   binding decision. For an important question, the Founder's decision is
   written to `DECISIONS.md` (via the `decisions` table, linked back to the
   meeting) using the standard decision format.

## What this is not

- Not a chat log that gets deleted — every meeting is a durable record.
- Not a vote — disagreement is preserved and shown, not resolved by
  majority.
- Not a way to bypass a review gate — a meeting can recommend building
  something, but it still has to pass Red Team, Code Review, QA, and
  Security like anything else; it doesn't grant that a Founder-only
  decision (see `PROJECT.md`) is no longer needed.

## Example shape

```
EXECUTIVE DISCUSSION
Topic: Should PDF support be included in MVP?

CEO: <strategic framing>
Product: <customer/value take>
CTO: <technical implications>
Financial: <cost/ROI take>
Marketing: <positioning impact>
Red Team: <reasons not to, assumptions challenged>

Areas of Agreement: ...
Areas of Disagreement: ...
Decision Required: ...

[Ask Follow-up]   [Make Decision]
```

This exact shape is what the "Executive Discussion" element in at least one
Phase 0 mockup depicts — see `MOCKUP_CRITIQUE.md`.
