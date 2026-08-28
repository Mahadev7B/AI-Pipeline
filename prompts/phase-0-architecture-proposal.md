# Phase 0 — Design & Architecture Proposal Prompt

This is the Claude Code prompt for **PHASE 0** of the AI Software Company Operating System.
Paste it into a fresh Claude Code session in this repo to run Phase 0. Do not proceed past
the STOP in this prompt without founder approval.

---

## Objective
This run is **PHASE 0 — DESIGN & ARCHITECTURE PROPOSAL** of a four-phase plan:

- **PHASE 0 — DESIGN & ARCHITECTURE PROPOSAL** (this run): inspect the repo, propose the agent operating model, workflow, templates, Skill Registry, Model Registry, and Executive Meeting design as documentation only, plus three real Control Center mockups. Critique, recommend, STOP.
- **PHASE 1 — FOUNDATION** (after mockup approval): instantiate the SQLite operational database, wire real agent definitions, execute the TASK-001 sample walkthrough, finalize durable docs.
- **PHASE 2 — CONTROL CENTER** (after Phase 1 is complete): build the approved mockup direction into the real web application.
- **PHASE 3 — AUTOMATED ORCHESTRATION** (after Phase 2 is complete): automate handoffs and status transitions between agents (e.g. Developer complete → Code Review; PASS/FAIL routing); production deployment always stays gated behind Founder approval.

Each phase requires a separate, explicit founder go-ahead before starting. This run only does Phase 0: inspect this repo and its Claude Code configuration, then produce the Phase 0 architecture PROPOSAL (documentation only — agent operating model incl. a real CEO Agent and Financial Agent, workflow, tools/permissions per agent, templates, Model Registry design, Skill Registry, Executive Meeting capability, source-of-truth design) plus three real, substantially different Control Center mockup variants via the `design` skill, at least one showing an Executive Discussion. Critique the variants, recommend one, then STOP and wait for founder approval. Do NOT build the actual product, the Control Center UI, the SQLite database, any model integration, or the sample task walkthrough in this pass — those belong to Phases 1–3.

## Context
- Repo: AI-Pipeline (current working directory) — verify current state yourself; treat it as untouched unless you find otherwise.
- This environment has ~24 enabled Claude Code skills, including `design` (Claude Design canvas — real multi-artboard visual mockups published as an Artifact), `code-review`, `security-review`, `simplify`, `run`, `init`, `prompt-master`, `skill-creator`, `docx`/`pptx`/`xlsx`. Re-verify the real, currently-installed list yourself — do not assume a skill exists just because it would be useful. Only map and document skills you actually find.
- No PM SaaS, no paid services, no purchases, no external accounts.

## Target State

### A. Workflow
IDEA → BRAINSTORM → PRODUCT REQUIREMENTS → DESIGN/MOCKUP → MOCKUP REVIEW → ARCHITECTURE → RED TEAM REVIEW → READY FOR DEVELOPMENT → DEVELOPMENT → CODE REVIEW → QA → SECURITY REVIEW → MARKETING/LAUNCH PREP → READY TO RELEASE → RELEASE/DEPLOYMENT → DONE. BLOCKED and FOUNDER_APPROVAL are interrupt states reachable from any stage. Failed QA → back to Development. Significant fixes → Code Review again. Do not invent extra statuses.

### B. Fourteen agent docs (`/ops/agents/*.md`)
Every agent doc — no exceptions — follows this schema (the "skill-based expert agent" pattern; never a bare persona prompt):
```
Role: <one line>
Model: configurable (not yet selected)
Skills: <only real, inspected skills this agent uses, and when>
Frameworks/Checklists: <this agent's explicit evaluation framework(s) — e.g. Red Team's question list, Code Review's criteria, Financial's value/growth/accounting/risk frameworks>
Tools: <exact tools this agent may invoke — filesystem, git, terminal, test runner, browser/testing tools, financial/cost data readers, etc.>
Permissions: <explicit allow-list, e.g. READ project source / MODIFY approved task files / RUN local tests — and an explicit "Not permitted" list>
Memory/Context: <what it needs handed to it each time>
Responsibilities: <bullets>
Must NOT: <explicit bullets>
Escalation Rules: <when it hands to Orchestrator / raises FOUNDER_APPROVAL>
Evaluation: <how another agent or the founder judges its output — PASS/REJECT criteria where applicable>
```
Tools and Permissions are mandatory on every agent, not optional — this is a least-privilege architecture: **agents receive only the tools and permissions required for their job**, nothing more. Illustrate with the Developer, QA, and Financial permission examples below; every other agent gets an equivalently explicit list.

Agents (12 from the prior proposal, unchanged in substance, plus 2 new):
- **Orchestrator** — inspects tasks, decides next action, assigns work, updates status, routes failures, detects blockers, escalates founder decisions, produces status summaries, coordinates handoffs, determines which agents join an Executive Meeting. Must NOT write/approve production code, do QA, or override Code Review/Security.
- **Product** — requirements, user stories, acceptance criteria, scope discipline, assumptions, open questions; produces the brief Design builds from. Must NOT implement code or make architecture decisions alone.
- **Design** — 2–3 substantially different mockup concepts via the `design` skill; critiques each against requirements/simplicity/usability/hierarchy/consistency; max 2 iteration rounds. Cannot approve its own mockup. Must NOT write production code or silently make product decisions.
- **CTO/Architect** — architecture, tech selection, interfaces, dependencies, data model, scalability, security/privacy/performance, simpler alternatives, documents decisions; architects only against an approved mockup. Must NOT implement or silently change its own architecture.
- **Red Team** — challenges the plan before build (overengineering, simpler solution, unnecessary dependencies, breakage, security/privacy, hidden costs, tech debt, architecture violations, beginner mistakes, unsupported assumptions); also independently challenges high-impact CEO and Financial recommendations. Outputs PASS or REJECT with specific reasons.
- **Developer** — implements only approved work, follows approved architecture/mockup, small changes, tests, documents deviations.
  - *Tools*: repository filesystem, git, terminal, test runner, approved dev tools.
  - *Permissions*: READ project source; MODIFY approved task files/code; CREATE tests; RUN local tests. **Not permitted**: production deployment, spending money, accessing unrelated credentials, overriding architecture, approving its own work.
- **Code Review** — independently reviews correctness, maintainability, readability, architecture consistency, performance, error handling, dependency usage, security, test coverage, complexity. Outputs PASS or REJECT with exact issues.
- **QA** — tests from the user's perspective, actively trying to break the feature (normal flow, empty/invalid/huge input, reload/restart, interruption, permission denial, slow conditions, failure recovery, rapid actions, regression, edge cases); produces reproducible defect reports.
  - *Tools*: test runner, browser/testing tools, application logs.
  - *Permissions*: READ implementation; RUN tests; CREATE defect reports; RECORD QA results. **Not permitted**: silently fixing production code, passing its own failed test without resolution, production deployment.
- **Security/Privacy** — auth, secrets/credentials, user data, logging, file access, permissions, privacy, input validation, injection risk, dependency vulnerabilities, sensitive-data exposure. Outputs PASS or REJECT.
- **Release/DevOps** — build prep, environment/test verification, deployment prep, release notes, rollback strategy, deployment recording — only after required gates pass. Must NEVER auto-deploy without founder authorization.
- **Marketing** — target audience, positioning, messaging, launch strategy, launch copy; participates during Product planning and pre-release. Must NOT commit ad spend, purchase software, change features, or make architecture decisions.
- **Project Manager/Status** — executive status view (completed/in progress/blocked/waiting/QA failures/review failures/risks/founder decisions/upcoming work). Must NOT make architecture decisions, implement code, or override other agents.
- **CEO Agent** (new) — the company's senior executive-strategy advisor, distinct from the Founder. Synthesizes company-level decisions across Product/CTO/Financial/Marketing/Operations.
  - *Frameworks*: strategic planning, competitive strategy, business-model analysis, product strategy, capital allocation, prioritization, organizational design, decision analysis, risk management, negotiation, long-term planning, scenario analysis, founder/board communication — as explicit reusable frameworks, not personality role-play.
  - *Responsibilities*: evaluate company direction, review strategic opportunities, help prioritize projects, reconcile conflicting specialist recommendations, identify strategic tradeoffs, challenge whether a project should exist at all, identify company-level risks, surface important decisions to the Founder, produce a clear recommendation while preserving dissenting views, and (with the Orchestrator) determine who participates in an Executive Meeting.
  - *Must NOT*: override the Founder; spend money; purchase services; deploy production; override specialist review gates (Red Team/Code Review/QA/Security keep their own authority); silently change product or architecture decisions; pretend expertise where a specialist agent should be consulted instead.
  - *Permissions*: READ project state, task history, and specialist recommendations; PRODUCE strategic recommendations and meeting syntheses. **Not permitted**: spending money, approving deployments, overriding any review gate.
  - Important CEO recommendations are independently challengeable by Red Team. The Control Center must display CEO Agent as a distinct entity from Founder at all times.
- **Financial Agent** (new) — finance/business-economics/investment analysis, available whenever a task or company decision has meaningful financial implications (not on every task).
  - *Frameworks*: financial-statement analysis, cash-flow analysis, unit economics, budgeting, forecasting, scenario modeling, valuation, capital allocation, accounting-quality analysis, downside/risk analysis, growth economics, pricing analysis, break-even analysis, ROI analysis. Where useful, frameworks may be *inspired by* documented public principles (e.g. a Buffett-style quality/value lens, Graham-style conservative valuation, Munger-style checklist thinking, a growth-investor lens, an accounting-forensics lens, a downside-risk lens) — encoded as named, reusable, public-principle-based frameworks. **The agent must never claim to be, or to have private knowledge of, any real individual.**
  - *Output shape for major financial questions* — multiple perspectives reconciled explicitly:
    ```
    FINANCIAL REVIEW
    Value/Quality: ... | Growth: ... | Accounting: ... | Risk: ... | Unit Economics: ...
    Areas of Agreement: ... | Areas of Disagreement: ...
    Financial Agent Recommendation: ... | Confidence: ... | Assumptions: ... | Known Unknowns: ...
    ```
  - *Tools*: read-only access to approved financial/project-cost data, analysis/forecasting tools.
  - *Permissions*: READ approved financial/project-cost data; PERFORM analysis, forecasting, recommendations. **Not permitted**: initiating payments, purchasing services, moving money, committing spend.
  - High-impact financial conclusions are independently challenged by Red Team. Founder retains final authority per the approval rules.

### C. Skill Registry (`/ops/skills/`)
Category subfolders only for categories with a real, confirmed skill (e.g. `engineering/`, `security/`, `design/`, `product/`), plus a skill-doc template (Skill name, Purpose, When to invoke, Inputs required, Analysis/checklist, Expected output, Failure conditions, Limitations, Which agents may use it, Version). Populate only with confirmed-installed skills, mapped to owning agent(s). Document in the registry README how a skill earns trust (benchmark scenarios, cross-agent evaluation, versioning, tracked limitations) as policy, not something to execute now.

### D. Model Registry (`/ops/models/README.md`, `/ops/models/MODEL_TEMPLATE.md`)
Architecture/documentation only — do **not** select, purchase, download, or integrate any specialized model in this pass. `MODEL_TEMPLATE.md` fields: Model name, Provider, Version, Local/cloud, Purpose, Recommended agents, Domain strengths, Domain weaknesses, Reasoning quality, Coding quality, Finance capability, Security capability, Context capacity, Latency, Cost, Privacy considerations, Licensing, Tool-calling support, Benchmark results, Known limitations, Approved/Experimental/Rejected status, Fallback model, Date evaluated, Evaluated by. Document the principle that different agents may eventually use different models (illustrate with CEO→strong reasoning, Developer→strong coding, Financial→specialized-if-benchmarked, Security→security-oriented, PM→fast/low-cost) without hardcoding any actual choice now.

**Model benchmarking policy** (extend the skill-quality-control principle to models — document as policy, do not execute): define benchmark tasks → run representative scenarios → compare alternatives → measure correctness and hallucination/error behavior → evaluate domain-specific performance → record weaknesses → have another agent review the evaluation → assign EXPERIMENTAL / APPROVED / REJECTED → re-evaluate when the model or requirements materially change. Note that the eventual Control Center should let the Founder inspect, per agent: current model, why it was chosen, benchmark score, skills, frameworks, tools, permissions, known limitations, evaluation history.

### E. Templates (`/ops/templates/`)
- **Task**: Task ID, Title, Business goal, User story, Priority, Status, Current owner, Dependencies, Requirements, Acceptance criteria, Mockup/Design, Architecture notes, Implementation notes, Tests required, Security considerations, Known risks, Developer result, Code-review result, QA result, Security result, Marketing notes, Deployment result, Blockers, Founder approval required, Next action, History.
- **Decision**: Decision ID, Date, Problem, Options considered, Decision, Reason, Tradeoffs, Agent recommending it, Founder approval if applicable. Never silently reverses a prior decision.
- **Founder approval**: `FOUNDER APPROVAL REQUIRED — Request / Requested by / Why / Recommendation / Alternatives considered / Expected cost / Risks / Consequence of not approving — Decision: [APPROVE] [REJECT] [DISCUSS]`
- **Handoff**: From, To, Task, Work completed, Files changed, Tests added, Expected behavior, Known limitations, Things the receiving agent should specifically check/test.

### F. Founder approval rules
Escalate only for: spending money, buying software/paid infra, purchasing domains/mailboxes/services, contracts, meaningful legal risk, production deployment, deleting important data, handling credentials, major architecture changes, major product-direction decisions, or irreversible externally-visible actions. Agents (CEO and Financial included) proceed independently on everything else.

### G. Source-of-truth design (document only — do not instantiate)
- **Durable Markdown**: `PROJECT.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `CODING_STANDARDS.md`, `SECURITY.md`. `ROADMAP.md` must explicitly record the four-phase plan (Phase 0 → Phase 1 — Foundation → Phase 2 — Control Center → Phase 3 — Automated Orchestration) and that each phase requires separate founder approval to begin.
- **Live operational state (future SQLite, schema-only doc)**: `/ops/DATA_MODEL.md` — tables `agents` (now including CEO/Financial and their tools/permissions/model fields), `tasks`, `task_status_history`, `agent_activity`, `messages`, `approvals`, `handoffs`, `decisions`, `qa_results`, `review_results`, `deployments`, and a new `meetings` table (topic, participating agents, positions, agreements, disagreements, recommendation, founder decision, linked decision ID). `DECISIONS.md` becomes the future git-readable mirror of the `decisions` table.
- `ARCHITECTURE.md` documents loose coupling: Web UI / Orchestrator / Task state / Agent execution / Git / Persistence as separate concerns.

### H. Shared engineering rules (`CODING_STANDARDS.md`)
No coding before requirements+acceptance criteria; simplest sufficient solution; no unexplained dependencies; no silent architecture changes; no unrelated refactoring; never claim untested work works; creator ≠ final approver; QA failures return to Development; significant fixes need re-review; decisions documented; no spending without founder approval; never expose credentials; no production changes outside the release process; rollback plans required; investigate uncertainty rather than invent; no speculative features; keep MVP small; agents may disagree; reviewers actively hunt for mistakes; preserve git history; never bypass a failed review without resolving it; progress reflects real completed work, not guesses; UI status reflects persistent state, not fabricated activity; agent conversations/decisions are auditable.

### I. Executive/Team Meeting capability (Control Center design — document, do not build)
Document as a core Control Center feature: the Founder raises a question (e.g. "Should PDF support be part of the MVP?"); the Orchestrator (with CEO input) selects only the agents with relevant expertise — not every agent speaks on every issue. Each participating agent contributes from its own responsibilities/frameworks (CEO: company-level strategic view; Product: customer/value; CTO: technical implications; Financial: cost/economics/ROI; Marketing: market positioning; QA: testing/quality impact; Security: privacy/security where relevant; Red Team: reasons not to proceed / assumptions to challenge). The meeting record preserves: each agent's position, evidence/assumptions, agreements, disagreements, unresolved questions, a synthesized recommendation, and the Founder's final decision — which, for important decisions, is written to the decision log.

### J. Foundational architectural rule (`/ops/AGENT_ARCHITECTURE.md`)
State explicitly, as a standing rule for every current and future agent:
```
Agent = Role + Model + Skills + Expert Frameworks + Tools + Permissions
        + Memory/Context + Operating Rules + Evaluation + Escalation Policy
```
An agent is never merely "LLM + job-title prompt." Also document the least-privilege principle (section B) and the multi-expert-perspective reconciliation pattern (illustrated by the now-real Financial Agent, no longer a future-only example).

### K. Three Control Center mockups (via the `design` skill — real visual artifacts, not text)
Three genuinely different concepts, each depicting: a feature moving through the pipeline; a **clear visual distinction between FOUNDER (human authority) and CEO AGENT (AI executive advisor)** — never merged into one entity; an expanded Agent Capability view for at least one agent shaped like:
```
AGENT NAME — Role / Current Status / Current Task / Model / Why this model / Skills /
Expert Frameworks / Tools / Permissions / Memory-Context / Current Activity /
Recent Decisions / Evaluation History / Known Weaknesses / Blockers / Confidence — [Ask Agent]
```
a Founder Inbox item; a visible QA or Code Review failure example; and **at least one of the three variants must also show an Executive Discussion**, e.g.:
```
EXECUTIVE DISCUSSION — Topic: Should PDF support be included in MVP?
CEO: ... | Product: ... | CTO: ... | Financial: ... | Marketing: ... | Red Team: ...
Areas of Agreement: ... | Areas of Disagreement: ... | Decision Required: ...
[Ask Follow-up]  [Make Decision]
```
The three variants:
- **A — Pipeline First**: pipeline is the visual centerpiece; agent info secondary.
- **B — Agent First**: agent cards are the centerpiece (Working/Waiting/Available/Blocked, current task, progress, last activity, blockers); pipeline secondary.
- **C — Command Center**: balanced executive view — pipeline, active agents, founder inbox, activity feed, risks, project health, releases.
None should resemble Jira, TFS, Excel, generic admin software, or a plain kanban board.

### L. Critique and recommendation
After the three mockups exist, write a critique (strengths/weaknesses of each) and one clear, reasoned recommendation. Then STOP.

## Scope
- Documentation only inside `/ops/**`; mockups only via the `design` skill.
- Do NOT create/instantiate a real SQLite database file.
- Do NOT write any Control Center UI code.
- Do NOT build or touch the actual product/reading application.
- Do NOT execute/populate the TASK-001 sample walkthrough.
- Do NOT create real Claude Code subagent config files (`.claude/agents/*.md`) — documentation only, not wired.
- Do NOT download, purchase, or integrate any specialized model — the Model Registry is a design doc only.
- Do NOT run any actual financial model or use real company/financial data — Financial Agent's frameworks are documented, not executed, in this pass.
- Do NOT create external accounts or spend any money.
- Do NOT touch existing `.claude/` config, skills, or settings — read-only for inspection.

## Constraints
- No paid services, purchases, or external accounts of any kind.
- Zero new dependencies (Markdown docs plus the `design` skill's own output).
- Do not claim any agent (Financial included) is, or has private knowledge of, a real individual — frameworks are public-principle-inspired only.
- Do not assume any skill exists without verifying it in this environment.
- Every agent doc must include Tools and Permissions — no exceptions, including CEO and Financial.
- Keep every document minimal — no fields, statuses, or agents beyond what's specified above.

## Acceptance Criteria
- [ ] Repo + `.claude` config + installed skills inspected; findings and any conflicts reported
- [ ] All 14 agent docs exist (12 prior + CEO + Financial), each with Role/Model/Skills/Frameworks/**Tools/Permissions**/Memory/Responsibilities/Must-not/Escalation/Evaluation
- [ ] CEO Agent doc is clearly distinct from "Founder" everywhere it appears, with its own must-not list including "must not override the Founder"
- [ ] Financial Agent doc includes the multi-perspective FINANCIAL REVIEW output shape and an explicit disclaimer against claiming to be a real individual
- [ ] Skill Registry scaffold + template exist, populated only with confirmed skills
- [ ] Model Registry scaffold (`README.md` + `MODEL_TEMPLATE.md`) exists with the full field list, no real model choices made
- [ ] Model benchmarking policy documented (EXPERIMENTAL/APPROVED/REJECTED lifecycle)
- [ ] All 4 templates created with exact fields
- [ ] Workflow/status list documented; `DATA_MODEL.md` includes the new `meetings` table
- [ ] `ROADMAP.md` documents the four-phase plan (Phase 0 → 1 → 2 → 3), each gated behind founder approval
- [ ] `AGENT_ARCHITECTURE.md` states the explicit "Agent = Role + Model + Skills + ... + Escalation Policy" formula and the least-privilege principle
- [ ] Executive Meeting capability documented as a Control Center feature (Orchestrator selects relevant agents; meeting record preserves positions/agreement/disagreement/recommendation/Founder decision)
- [ ] Three substantially different mockups (A/B/C) exist as real `design`-skill artifacts; at least one shows an Executive Discussion; all clearly separate Founder from CEO Agent visually
- [ ] Written critique of each variant plus one clear, reasoned recommendation
- [ ] No SQLite file, no Control Center code, no sample task execution, no product code, no subagent configs, no real model integration, and no real financial computation were created
- [ ] The turn ends on an explicit "waiting for founder approval" stop with no further action taken

## Stop Conditions
Stop and ask before:
- Anything listed under Scope as excluded
- Deleting or overwriting any existing file
- Any purchase, paid service, external account, or model download/integration
- Treating the proposal or any mockup as approved without the founder explicitly saying so
- Proceeding into **PHASE 1 — FOUNDATION**, **PHASE 2 — CONTROL CENTER**, or **PHASE 3 — AUTOMATED ORCHESTRATION**, or any real model/financial evaluation — each phase requires a separate, explicit founder go-ahead after Phase 0's proposal and a mockup are approved

## Progress
After each completed step, output: ✅ [what was done] — [file(s)/artifact affected]. End with the critique + recommendation + explicit stop.

Think carefully and step-by-step before starting — inspect the repo and skills first, then build the proposal, then the mockups.

## Session Strategy
New session — this supersedes any earlier draft of this ops-system prompt; treat it as the authoritative version.
