# ROADMAP.md

Four phases are currently defined and gated (Phase 0 through Phase 3
below; Phase 3 itself ships as authorized sub-slices, not all at once).
A possible Phase 4
is proposed, not yet defined or approved, at the bottom of this file. Each
phase requires a separate, explicit Founder go-ahead before the next one
starts. No phase begins itself.

*(Correction, Founder directive "PAUSE SECURITY HARDENING, FINISH PRODUCT
ARCHITECTURE FIRST", 2026-08-31: this file previously said "Four phases"
while only ever defining Phase 0 through Phase 3 — an inconsistency the
Founder flagged. Phase 4 was never scoped. It is now proposed, clearly
marked NOT STARTED / NOT APPROVED, at the bottom of this file — see
PROPOSED PHASE 4, below.)

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
  fix — see `DECISIONS.md` DEC-004. The first was closed via Milestone
  2B4 (`risks.id=2`, `mitigated`). The second (`risks.id=3`) was the
  subject of a dedicated Founder-directed architecture investigation
  (TASK-016, CTO → Security → Red Team → Chief of Staff, investigation
  only — no implementation): see
  `ops/reviews/chief-of-staff-risk3-synthesis.md` for the Founder-facing
  synthesis and the smallest-first-step authorization proposed. The
  Founder then authorized a narrow implementation milestone (TASK-017)
  which went through three real review rounds (Security: one CONCERNS,
  fixed; Red Team: two REJECTs, both fixed and re-verified, final PASS)
  before the Founder paused it mid-Development to prioritize finishing
  the product architecture first — see `DECISIONS.md` DEC-008.
  TASK-017's findings and approved design are preserved, not discarded;
  work resumes before any broader unattended automation, external
  users, production credentials, production deployment automation, or
  multi-user access. `risks.id=3` remains `open`, explicitly deferred
  by Founder direction, not resolved.

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

**Milestone 2A — DONE (TASK-005):** the remaining read-only screens —
Pipeline, Agents, Decisions, Meetings — plus shared nav. See
`ops/reviews/cto-milestone2a-architecture.md`,
`ops/reviews/red-team-milestone2a-architecture.md`,
`ops/reviews/design-conformance-milestone2a.md`.

**Milestone 2B1 — DONE (TASK-006):** the first live process
(`ops/control-center/server.py`) and the first write path — Founder Inbox
Approve/Reject/Discuss. See `ops/reviews/cto-milestone2b1-architecture.md`,
`ops/reviews/red-team-milestone2b1-architecture.md`.

**Milestone 2B2 — DONE (TASK-007):** real Ask-Agent conversations
(zero-tool, sandboxed model invocations) with persistent per-agent
threads. See `ops/reviews/cto-milestone2b2-architecture.md`,
`ops/reviews/red-team-milestone2b2-architecture.md`,
`ops/reviews/design-conformance-milestone2b2.md`.

**Milestone 2B3A — DONE (TASK-009):** controlled concurrent Agent Runtime
foundation — `ThreadingHTTPServer`, a bounded semaphore over real model
invocations, and the transaction-level fixes concurrency required. See
`ops/reviews/cto-milestone2b3a-architecture.md`,
`ops/reviews/red-team-milestone2b3a-architecture.md`.

**Milestone 2B3B — DONE (TASK-010, corrected and re-reviewed; TASK-011
round 2):** real multi-agent Executive Meetings — CEO-led participant
selection, bounded-concurrent position-gathering, synthesis, Founder
decision recording, and (round 2) request-perspective, follow-up, and
retry. See `ops/reviews/cto-milestone2b3b-architecture.md`,
`ops/reviews/red-team-milestone2b3b-architecture.md`,
`ops/reviews/cto-milestone2b3b-round2-architecture.md`,
`ops/reviews/founder-conformance-review-milestone2b3b.md`.

**Chief of Staff rename — DONE (TASK-012):** Founder-directed
human-facing role rename (Orchestrator → Chief of Staff, display/label
only — see `DECISIONS.md` DEC-005). Not a numbered milestone; a
documentation/UI correction run through the same full gate sequence.
See `ops/reviews/cto-chief-of-staff-rename.md`,
`ops/reviews/cto-chief-of-staff-rename-conformance.md`.

**Milestone 2B4 — DONE (TASK-013):** Founder Identity Verification for
Consequential Write Actions — a locally authenticated Founder session
(passphrase + `scrypt` + session cookie) now gates all 9 write/auth
routes and every GET read; `risks.id=2` moved `open` → `mitigated` (see
`DECISIONS.md` DEC-006). See `ops/reviews/cto-milestone2b4-architecture.md`,
`ops/reviews/security-milestone2b4-threat-model.md`,
`ops/reviews/red-team-milestone2b4-architecture.md`,
`ops/reviews/cto-milestone2b4-conformance.md`.

**Milestone 2B5 — DONE (TASK-014):** Review/QA Failure History & Release
Readiness Visibility — two new read-only screens, `reviews.html`
(grouped `review_results`/`qa_results` history, collapsible past ~10
rows per task) and `releases.html` (real `deployments` history plus a
neutrally-framed release-readiness gap list), closing the last two
Phase-2-scoped capabilities ("QA/review failures," "release
information") named above. Both inherit Milestone 2B4's session gate
with zero new auth code. See
`ops/reviews/cto-milestone2b5-architecture.md`,
`ops/reviews/red-team-milestone2b5-architecture.md`,
`ops/reviews/cto-milestone2b5-conformance.md`.

Every Phase-2-scoped capability named at the top of this section
(project overview, pipeline visualization, agent panel + detail view,
Ask-Agent conversation interface, Executive Meeting UI, Founder Inbox,
activity feed, QA/review failures, decision history, project health,
release information) has shipped as of Milestone 2B5. Phase 2's own
scope being built out did not itself authorize Phase 3 — see PHASE 3,
below, for what has and has not since been separately authorized.

## PHASE 3 — Automated Orchestration *(full automation not yet authorized; a first, limited slice — Phase 3A — is DONE)*

Automate the handoffs already defined in the workflow (Developer complete →
Code Review; Code Review PASS → QA / FAIL → Developer; QA PASS → Security /
FAIL → Developer; Security PASS → Release prep). Production deployment stays
gated behind explicit Founder approval — this is never automated.

**Phase 3A — DONE (TASK-015):** the Founder authorized only a first,
narrowly-scoped slice of this phase, not the full automation described
above — see `DECISIONS.md` DEC-007. Two closely related capabilities
shipped:
- **Chief of Staff Founder conversational interface** — a real, plain-
  English, recommendation-first `POST /api/chief-of-staff/ask` (the
  first-ever real `claude --agent orchestrator` invocation in this
  system's history, zero-tool like every invocation before it), grounded
  in a bounded, freshly-assembled state digest every turn, able to
  gather other agents' real perspectives via a reused Executive Meeting
  mechanism (`run_consult_meeting()`) and synthesize a Founder-addressed
  answer, never treating a chat instruction as an executable command.
- **One automatic handoff, and only one**: Developer-complete → Code
  Review, run by a new in-process background poller
  (`ops/control-center/automation.py`), zero-tool exactly like every
  other invocation, gated by a default-disabled kill switch only the
  Founder can flip. PASS leaves the task at `CODE_REVIEW` for a human to
  advance to `QA`; REJECT is a mechanical status rollback to
  `IN_DEVELOPMENT`, never a new Developer invocation. No automatic
  QA→Security, no automatic Security→Release, no automatic production
  deployment, no automatic re-invocation of Developer, no autonomous
  initiation of unrelated work, no chat-triggered writes — all
  explicitly out of scope for Phase 3A and not built.

See `ops/reviews/cto-phase3a-architecture.md`,
`ops/reviews/security-phase3a-threat-model.md`,
`ops/reviews/red-team-phase3a-architecture.md`,
`ops/reviews/qa-phase3a.md` (the Founder's own 12-point acceptance test,
demonstrated end-to-end with real model invocations),
`ops/reviews/security-adversarial-phase3a.md`,
`ops/reviews/cto-phase3a-conformance.md`.

`risks.id=3` (Bash permissions cannot be scoped below the tool-category
level) remains `open` — Phase 3A does not resolve, narrow, or claim
progress on it. Its practical consequence genuinely increases under
Phase 3A in two disclosed, independently additive ways (a background
actor that can now act without any Founder-triggered request; a
data-driven filesystem/subprocess surface) — see `ops/SECURITY.md` and
`risks.id=3`'s own updated mitigation text for the full, undiluted
disclosure.

**The remainder of Phase 3** (automatic Code Review PASS → QA, QA →
Security, Security → Release, and any form of automatic production
deployment) **remains explicitly unauthorized** and does not begin
until the Founder separately approves that specific expansion — Phase
3A shipping does not itself authorize Phase 3B or any later slice, per
the Rule at the bottom of this file.

**TASK-017 (risks.id=3 hardening milestone) — paused mid-Development by
Founder direction, 2026-08-31** (see `DECISIONS.md` DEC-008): the
Founder chose to prioritize completing the product architecture needed
for Founder testing over continuing repeated architecture/Red Team
correction cycles on this one security mechanism. This is a
prioritization decision, not acceptance that `risks.id=3` is solved —
its findings, the approved (post-three-round) architecture document,
and CTO/Security/Red Team's recommendations are all preserved for when
this work resumes, which is required before any broader unattended
automation, external users, production credentials, production
deployment automation, or multi-user access.

**Remaining Phase 3 / Founder-testability architecture** — under
review per the same Founder directive: CTO and Chief of Staff are
producing a completion assessment covering the rest of Phase 3's
orchestration (remaining handoffs, rejection/rework loops, Founder
approval boundaries), a Founder Work Progress capability (per-task gate
visibility, sourced from the existing operational database, no second
project-management system), a cost/token tracking architecture, and a
concrete definition of "Founder Test Readiness" — see
`ops/reviews/cto-product-architecture-completion.md` for the initial
assessment and `ops/reviews/cto-product-architecture-completion-v2.md`
for the corrected, authoritative one (design/inventory only; the plan
below is what the Founder actually approved).

### Founder UI Completeness — APPROVED (Founder directive "FOUNDER CORRECTION — FINALIZE UI COMPLETENESS PLAN", 2026-08-31)

Authoritative UI audit (reconciled from `ops/reviews/cto-product-architecture-completion-v2.md`'s
own per-item table, correcting that document's own inconsistent prose
summary): **30 capabilities audited, 18 COMPLETE, 6 PARTIAL, 6
MISSING.** See that document for the full item-by-item table with
file/route citations.

Four milestones make up the official plan. All four are required before
the Founder-facing UI may be called **100% feature-complete**; the
Founder was explicit that this definition is not to be narrowed after
the fact:

- **Milestone A — DONE (TASK-019):** Active Work dashboard
  (`/active-work.html`) + Task Detail page (`/tasks/<id>.html`), shipped
  together (they share one computed progress model). Cleared CTO
  architecture, Design review, Red Team, Development (two fix rounds),
  Code Review (three rounds), QA (two rounds), a focused Security review,
  and CTO final conformance (CONFORMS, no drift) — see
  `ops/reviews/cto-milestone-a-architecture.md`,
  `ops/reviews/design-review-milestone-a.md`,
  `ops/reviews/red-team-milestone-a-review.md`,
  `ops/reviews/cto-milestone-a-conformance.md`. Two real defects were
  caught and fixed along the way: `gates_remaining()`/`gates_completed()`
  both needed correction for backward transitions and gate re-entry
  (ordinary parts of this system's own reject/rework loop, not edge
  cases) — both are now regression-tested (`ops/db/test_gates_remaining.py`,
  34 checks). Every dead `pipeline.html#task-{id}` anchor across the
  product now links to a real Task Detail page.
- **Milestone B — DONE (TASK-020):** Company-wide AI cost visibility
  (`/costs.html` + Meeting Detail's Cost panel). All five real invocation
  paths — Ask-Agent, Executive Meetings, Chief of Staff, automated Code
  Review, and Synchronous review (display-only pending TASK-017) — now
  persist and surface the cost they compute; previously only the
  automation poller did. Cleared CTO architecture, Design review, Red
  Team, Development (three fix rounds — the same Founder-facing copy
  bug caught twice more after an incomplete first fix), Code Review
  (three rounds), QA (with a genuine live end-to-end invocation test),
  a focused Security review, and CTO final conformance (CONFORMS) — see
  `ops/reviews/cto-milestone-b-architecture.md`,
  `ops/reviews/design-review-milestone-b.md`,
  `ops/reviews/red-team-milestone-b-review.md`,
  `ops/reviews/cto-milestone-b-conformance.md`.
- **Milestone C — DONE (TASK-021):** Company-wide Risks register
  (`/risks.html`), making `risks.id=3` finally visible in the product —
  three status-grouped sections, a "Needs attention" strip, and
  related-decision links. Cleanest of the three shipped milestones: no
  rejection rounds across CTO architecture, Design review, Red Team,
  Development, Code Review, QA, focused Security review, and CTO final
  conformance (CONFORMS) — see
  `ops/reviews/cto-milestone-c-architecture.md`,
  `ops/reviews/design-review-milestone-c.md`,
  `ops/reviews/cto-milestone-c-conformance.md` (Red Team's review was
  recorded via `review_results` in the operational database, task_id=21,
  no separate document). Also disclosed, not
  fixed (future work): risk mitigation text is destructively
  overwritten on update, with no history table — already lost three
  times for `risks.id=3` itself; the register page carries this
  disclosure honestly rather than hiding the gap.
- **Milestone D** — Project / Phase Progress, built on a small new
  structured representation (phase/milestone state exists today only as
  prose in this file) — no invented percentages; real fractions where
  genuinely queryable, otherwise an explicit status
  (Complete/In Progress/Not Started/Paused).

Build order: A → B → C → D, unless CTO finds a concrete dependency
requiring otherwise.

**Two distinct readiness states — kept separate everywhere this project
reports status, per the Founder's explicit instruction:**

- **Exploratory Founder Testing ready** = Milestones A + B + C complete.
  The Founder may begin testing a real app idea through the company at
  this point, if the Chief of Staff recommends it.
- **Founder UI 100% feature-complete** = Milestones A + B + C + D
  complete. A + B + C being done does **not** mean the UI is 100%
  complete — that claim requires D as well.

Security hardening (TASK-017/`risks.id=3`, see DEC-008) and the
remaining Phase 3 orchestration automation (Code Review PASS → QA, QA →
Security, Security → Release, automated Developer reinvocation,
production deployment automation) are explicitly **not** bundled into
this work and stay deferred exactly as before, unless a specific UI
milestone is found to introduce a genuinely new material vulnerability.

Gates per milestone: CTO architecture → Design review (where
Founder-facing UX changes) → Red Team → Development → Code Review → QA
→ focused Security review (scoped to newly introduced risk only) → CTO
final conformance. Per the Founder's explicit instruction: only a
concrete, blocking defect repeatedly stops progress through this
sequence — lower-severity hardening, theoretical edge cases, and
documentation nits are recorded as follow-up work, not grounds for an
open-ended review loop.

## PROPOSED PHASE 4 — Human AI Team Experience (NOT STARTED, NOT APPROVED)

Proposed only, per Founder directive 2026-08-31 ("PAUSE SECURITY
HARDENING, FINISH PRODUCT ARCHITECTURE FIRST"), Part 7. Nothing below
is built, scoped in detail, or authorized — this section exists solely
to position the idea in the roadmap for a later, separate Founder
approval, the same as any other phase.

Potential scope, as the Founder described it: persistent human-like
identity for each agent; individual voices; realtime voice
conversation; realistic avatars; lip sync / expression / listening
states; the Founder talking naturally to the Chief of Staff; Ask-Agent
with voice/avatar; Executive Meetings with visible, speaking agents; a
provider-neutral avatar and TTS architecture; graceful voice-only
fallback if avatar rendering lags.

This phase would not begin until Phase 3's remaining scope (or
whatever subset of it the Founder authorizes) is itself complete and
separately approved, per the Rule below — a phase that is technically
easy to start early is still not started early.

## Rule

Do not skip a phase gate. A phase that is technically easy to start early is
still not started early — Founder approval is the gate, not agent judgment.
