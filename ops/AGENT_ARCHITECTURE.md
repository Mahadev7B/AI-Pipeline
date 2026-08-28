# AGENT_ARCHITECTURE.md — Foundational Rule

## The rule

```
Agent = Role + Model + Skills + Expert Frameworks + Tools + Permissions
        + Memory/Context + Operating Rules + Evaluation + Escalation Policy
```

An agent is **never** merely "LLM + job-title prompt." Every agent doc in
`/ops/agents/` is written to this schema:

```
Role:                    <one line>
Model:                   configurable (not yet selected — see /ops/models/)
Skills:                  <only real, installed skills this agent uses, and when>
Frameworks/Checklists:   <this agent's own explicit evaluation framework(s)>
Tools:                   <exact tools/capabilities this agent may invoke>
Permissions:             <explicit allow-list, plus an explicit "Not permitted" list>
Memory/Context:          <what must be handed to it each time>
Responsibilities:        <bullets>
Must NOT:                <explicit bullets>
Escalation Rules:        <when it hands to Orchestrator / raises FOUNDER_APPROVAL>
Evaluation:              <how another agent or the Founder judges its output>
```

This is not cosmetic structure — it's how the system avoids the two
failure modes it's designed against: an agent that role-plays expertise it
doesn't actually have, and an agent that can act outside the scope of its
job because nothing ever wrote down what it's allowed to touch.

## Least privilege

Agents receive only the tools and permissions required for their job —
nothing more, and nothing "just in case." A Developer agent gets repo
filesystem/git/terminal/test-runner access and can modify approved task
files; it cannot deploy, spend money, or approve its own work. A Financial
agent can read approved cost data and produce analysis; it cannot initiate
a payment. Every agent doc states both what it *can* do and what it is
explicitly *not permitted* to do — the second list is not optional.

## Multi-expert-perspective reconciliation

Some questions don't have one right specialist answer — they need several
perspectives reconciled, with disagreement preserved rather than smoothed
over. The Financial Agent (`/ops/agents/financial.md`) is the concrete,
real example of this pattern in the current roster: it runs Value/Quality,
Growth, Accounting, Risk, and Unit-Economics frameworks in parallel on a
significant financial question, states where they agree and disagree, and
gives one recommendation with stated confidence and assumptions — instead
of averaging the disagreement away. High-impact conclusions built this way
are independently challenged by Red Team before they're acted on.

This pattern generalizes to any future agent that needs to weigh multiple
named, documented frameworks rather than one. It is documented here once,
generically, so a future agent can adopt it without re-deriving it —
**no such additional agent is being built in Phase 0.**

## What a framework is (and isn't)

A framework is a named, explicit, reusable checklist or analysis method —
e.g. Red Team's question list, Code Review's review criteria, or the
Financial Agent's value/growth/accounting/risk lenses. Where a framework is
*inspired by* documented public principles of real practitioners (see
`/ops/agents/financial.md`), the agent states which framework produced a
conclusion and never claims to be, or to have private knowledge of, the
real individual it's inspired by.

## Models are not chosen here

This document defines the *shape* every agent takes. Which model actually
powers a given agent is a separate, evaluated decision — see
`/ops/models/README.md`. No agent in this proposal has a model selected;
every agent doc says `Model: configurable`.
