# Model Registry

**Architecture/documentation only. No model is selected, purchased,
downloaded, or integrated in Phase 0 — or in this document at all.**

## Why this exists

The agent architecture (`AGENT_ARCHITECTURE.md`) explicitly does not
hard-couple every agent to one model or provider — every agent doc says
`Model: configurable`. This registry is where a real per-agent model
choice eventually gets recorded, *after* it's been benchmarked, not
because it's popular or marketed as specialized.

## How an agent eventually gets a model

Illustrative only — none of these are decided:
- **CEO** → a strong reasoning model (executive synthesis, multi-perspective reconciliation)
- **Developer** → a strong coding model
- **Financial** → a specialized financial model, *only if* benchmarked and approved
- **Security** → a security-oriented model/toolset
- **Project Manager** → a fast, low-cost model (high-frequency, routine reporting)

Every other agent stays on a general default until there's a documented
reason to specialize.

## Benchmarking policy (see also `MODEL_TEMPLATE.md`'s status field)

A model is not trusted because it's popular or marketed as specialized.
Before it's approved for an important agent:

1. Define benchmark tasks representative of that agent's real work.
2. Run representative scenarios.
3. Compare against the current default and any other real alternative.
4. Measure correctness.
5. Measure hallucination/error behavior.
6. Evaluate domain-specific performance (e.g. financial reasoning for
   Financial, coding correctness for Developer).
7. Record weaknesses — not just the score.
8. Have another agent review the evaluation (never self-graded).
9. Assign status: `EXPERIMENTAL`, `APPROVED`, or `REJECTED`.
10. Re-evaluate when the model or the agent's requirements materially
    change — approval is not permanent.

## What the Control Center should eventually show (Phase 2 — not built yet)

Per agent: current model, why it was chosen, benchmark score, skills,
frameworks, tools, permissions, known limitations, evaluation history.

## Status

No entries exist yet. `MODEL_TEMPLATE.md` defines the fields a real entry
will use once model research/evaluation happens — explicitly out of scope
for Phase 0 per the Founder's instructions ("do not choose or purchase
specialized models yet").
