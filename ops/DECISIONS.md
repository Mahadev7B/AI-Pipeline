# DECISIONS.md — Decision Log

Append-only. Never silently reverse a prior decision — if an agent believes
an existing decision should change, it proposes a **new** decision entry
and runs it through review; the old entry stays as-is for history.

From Phase 1 onward, this file is the git-readable mirror of the `decisions`
table in the operational SQLite database (see `DATA_MODEL.md`) — SQLite is
the writable source of truth, this file is the durable, diffable export.

## Format

```
### DEC-<NNN> — <short title>
Date: <YYYY-MM-DD>
Problem: <what needed deciding>
Options considered: <list>
Decision: <what was chosen>
Reason: <why>
Tradeoffs: <what was given up>
Agent recommending it: <agent name>
Founder approval: <required/not required — and outcome if resolved>
```

## Log

### DEC-001 — Control Center mockup direction (recommended, pending Founder approval)
Date: 2026-08-28
Problem: Which of three Control Center visual/structural directions should Phase 2 build from?
Options considered: Variant A (Pipeline First), Variant B (Agent First), Variant C (Command Center) — see `MOCKUP_CRITIQUE.md` for full critique of each.
Decision: Recommend Variant C (Command Center) as the landing "Overview" screen, with Variant A's pipeline design as the dedicated "Pipeline" tab and Variant B's agent roster/capability view as the dedicated "Agents" tab — reconciling all three rather than discarding two.
Reason: The Founder's stated priority is minimizing interruptions to founder-only decisions; Command Center is the only variant that puts Founder Inbox, Risks, and Executive Discussion front-and-center on first open, while still preserving A's and B's strengths as deeper views.
Tradeoffs: Command Center is the busiest single screen of the three; agent capability detail is a drill-in rather than visible on the landing view.
Agent recommending it: Design Agent (critique), Orchestrator (log entry).
Founder approval: **APPROVED 2026-08-28.** Command Center = Overview, Pipeline First = Pipeline tab, Agent First = Agents tab.

### DEC-002 — Control Center visual style: dark vs. light (recommended, pending Founder approval)
Date: 2026-08-28
Problem: Which visual treatment should the approved Command Center structure use — the existing dark "operating console" direction, or a new lighter/premium alternative?
Options considered: Style A — refined dark (`Main.dc.html`); Style B — lighter premium (`OverviewLight.dc.html`) — see `MOCKUP_CRITIQUE.md`, "Visual style" for full critique.
Decision: Recommend Style A (refined dark) as the primary direction; keep Style B on file as a considered alternative rather than discarding it.
Reason: The product's core value is watching AI agents work in real time — a console aesthetic communicates that more directly than a document-like light theme, which reads calmer but less "live."
Tradeoffs: A risks tipping into "ops-tool" territory if not kept disciplined; B is easier on the eyes for long sessions but undersells that a live system is running underneath.
Agent recommending it: Design Agent.
Founder approval: **APPROVED 2026-08-28.** Refined dark (Style A) is the default visual direction; Style B (light) is retained as an optional future theme, not built in Phase 2 unless separately requested.

### DEC-003 — Phase 0 final approval
Date: 2026-08-28
Problem: Whether the Phase 0 architecture proposal (14-agent operating model, workflow, templates, Skill/Model Registry, Executive Meetings) and the Control Center design direction (DEC-001, DEC-002) are approved to proceed into Phase 1 — Foundation.
Options considered: Approve as-is; request further iteration; reject and restart.
Decision: **APPROVED.** Phase 0 is complete. Phase 1 — Foundation begins, scoped to: instantiating the SQLite operational database (per the data-model clarifications below), wiring the 14 agent definitions as real Claude Code subagents, executing the TASK-001 sample walkthrough, and generating real status reporting. Phase 2 (Control Center UI) remains explicitly out of scope until Phase 1 is reviewed and separately approved.
Reason: Two rounds of mockup refinement (v2, v2.1) resolved every open concern the Founder raised; the remaining data-model clarifications (agent_runs, risks, task_steps, projects) are architecture-level fixes, not design changes.
Tradeoffs: None — this is a gate opening, not a scope tradeoff.
Agent recommending it: Orchestrator.
Founder approval: **APPROVED 2026-08-28.**

### DEC-004 — Phase 1 Foundation complete, two known gaps disclosed
Date: 2026-08-28
Problem: Whether Phase 1 (SQLite operational database, 14 wired subagents, TASK-001 walkthrough, real status reporting) is complete and ready for Founder review before Phase 2 begins.
Options considered: Declare complete with gaps disclosed; hold Phase 1 open until gaps are closed.
Decision: Declare Phase 1 **complete**, with two gaps explicitly disclosed rather than silently accepted: (1) `approval-decide` has no real identity check — a `--confirm-founder-decision` flag makes it a deliberate act but not enforced authentication; (2) subagent `Bash` tool grants are not scoped below the tool-category level, so a subagent's actual shell access is broader than its documented Permissions section implies. Neither blocks Phase 1's stated goal (a working, auditable, deterministic operational core); both require an identity/permission layer that is Phase 2/3 (Control Center) scope.
Reason: Holding Phase 1 open until these are closed would mean waiting on infrastructure (real user auth, finer-grained tool scoping) that doesn't exist yet and wasn't asked for in Phase 1 — better to ship a disclosed, honest state than delay for an unscoped fix.
Tradeoffs: The Founder is trusting procedural/documented enforcement (agent role docs, CLI speed bumps) over technical enforcement for these two specific actions until Phase 2 or later.
Agent recommending it: Security (see `ops/reviews/security-phase1.md`), Orchestrator.
Founder approval: **APPROVED 2026-08-28. Phase 1 — Foundation is formally closed.** Recorded as decision id=2 in the operational database (`decisions` table), linked to approval id=3 — see `ops/db/opsdb.py query "SELECT * FROM decisions WHERE id=2"`. The two disclosed gaps are not resolved by this approval — they carry forward as tracked risks (company-scoped, `risks` table) into Phase 2, not silently dropped.

### DEC-005 — Human-facing role rename: Orchestrator → Chief of Staff
Date: 2026-08-30
Problem: Founder directive: rename the human-facing company role currently called "Orchestrator" to "Chief of Staff" — a role-name clarification only, explicitly not a change to authority, permissions, or responsibilities, and explicitly not a second/duplicate agent. Exactly one operating coordination agent must remain.
Options considered: Rename the DB `agents.name` value and every stored TEXT reference across ~10 tables (rejected — unnecessary migration risk, would also rewrite history); rename `.claude/agents/orchestrator.md`'s filename and `subagent_type` (rejected — would break every invocation across this whole operating system and risks reading as two agents, exactly what the Founder forbade); add a single Founder-facing `display_name()` mapping layer applied only at render sites, leaving the internal machine identity `orchestrator` unchanged everywhere (adopted).
Decision: Introduced `ops/db/derived_state.py`'s `display_name()`, a one-entry mapping (`{"orchestrator": "Chief of Staff"}`, default fallback the key itself) applied only at Founder-facing render sites — agent roster/detail, pipeline task-owner, Overview, Founder Inbox, Decisions byline, Executive Meeting validation note, `CURRENT_STATUS.md`'s Agents section. Internal machine identity, the `agents` table row, `.claude/agents/orchestrator.md`'s filename and `subagent_type`, and every historical record (this file, `ops/reviews/*.md`, stored message/decision/review body text, the approved Phase 0 mockups) remain `orchestrator`/"Orchestrator" unchanged, permanently.
Reason: Smallest safe change per the Founder's explicit instruction to prefer preserving the stable machine identity and avoid unnecessary database/runtime migration, while giving every current and future Founder-facing render site a single, consistent source of truth for the display label.
Tradeoffs: Historical text (old reviews, this file's own DEC-001–004 above, stored message bodies) correctly keeps reading "Orchestrator" forever — an intended, disclosed outcome (a record reflects the name that existed when it was created), not a bug or an incomplete rename. The other 13 agents' identical raw-machine-key rendering is unchanged — out of scope, not incidentally fixed.
Agent recommending it: CTO (see `ops/reviews/cto-chief-of-staff-rename.md`, Red Team rounds at `ops/reviews/red-team-chief-of-staff-rename.md`), Chief of Staff/Orchestrator.
Founder approval: **APPROVED 2026-08-30 (Founder directive, Part A).** TASK-012, all gates PASS/CONFORMS — see `ops/reviews/code-review-chief-of-staff-rename.md`, `ops/reviews/qa-chief-of-staff-rename.md`, `ops/reviews/security-chief-of-staff-rename.md`, `ops/reviews/cto-chief-of-staff-rename-conformance.md`. Recorded as decision id=8 in the operational database.

### DEC-006 — Milestone 2B4: Founder authentication mechanism selection
Date: 2026-08-30
Problem: The session-token mechanism (Milestone 2B1 onward) proves a request came from a page this server process rendered, but does not prove a human, specifically the Founder, sent it — `risks.id=2`, open since Phase 1. This milestone had to materially close that gap for the current local/internal, solo-Founder, loopback-only Control Center deployment, without adding a paid identity provider, external cloud infrastructure, or any third-party dependency unless the threat model genuinely required it (Security and Red Team both confirmed it did not).
Options considered: Auth0/Clerk/Firebase/OAuth/enterprise IAM (rejected — disproportionate cost/dependency for a single local trusted operator's own machine; would require separate Founder approval for external cost/dependency anyway); an environment-variable passphrase (rejected — leaks via shell history and `/proc/<pid>/environ`, worse exposure than the alternative, and forces re-entry every process start with no session UX); a single Founder passphrase, `hashlib.scrypt`-hashed, credential stored outside git in a 0600 file bootstrapped via a new stdlib-only CLI, gated by a server-side session cookie layered onto the existing centralized `do_POST()`/`do_GET()` check (adopted).
Decision: Implemented `ops/control-center/founder_auth.py` (`scrypt` N=2**17/r=8/p=1, 16+ character passphrase floor, atomic 0600 credential file outside git, never touching `operations.sqlite3`) plus a Founder-session cookie (`HttpOnly`, `SameSite=Strict`, 30-minute idle / 12-hour absolute timeout, in-memory only, wiped on restart) gating all 9 write/auth routes and every GET read at the same centralized location the pre-existing CSRF `SESSION_TOKEN` check already occupied — kept, not replaced. Fully serialized `/api/login` verification closes both the stated brute-force attempt cap and a concurrent-`scrypt` memory-exhaustion DoS, independently verified three separate times under adversarial conditions (Code Review's 60-simultaneous reproduction, Security's 45,820-request/40-second sustained flood) — all PASS.
Reason: The smallest credible mechanism for the actual deployment model — a solo Founder's own local internal tool, not a public SaaS product — that genuinely answers "does the entity submitting this request know a secret only the Founder was ever told," backed by a real, independently-reproduced technical guarantee rather than a documented convention.
Tradeoffs: Does not and structurally cannot defend against an agent with Bash tool access sharing the Founder's own OS-user filesystem/process principal (`risks.id=3`, explicitly out of scope this milestone) — such an agent can read or overwrite the credential file directly, run `founder_auth.py` itself, or `PTRACE_ATTACH` the running server process and read session state out of memory. Also disclosed: the shared, non-identity-scoped lockout can itself be flooded by an actor already inside this design's own threat class to deny the Founder's own genuine logins (Red Team's Milestone 2B4 finding F1) — no cheap in-scope fix exists without touching `risks.id=3`. Neither gap is hidden; `risks.id=2` moves to `mitigated`, deliberately not `resolved`.
Agent recommending it: CTO (see `ops/reviews/cto-milestone2b4-architecture.md`), Security threat model (`ops/reviews/security-milestone2b4-threat-model.md`), Red Team (`ops/reviews/red-team-milestone2b4-architecture.md`).
Founder approval: **APPROVED 2026-08-30 (Founder directive, Part B — Milestone 2B4).** TASK-013, all gates PASS/CONFORMS — see `ops/reviews/code-review-milestone2b4.md`, `ops/reviews/qa-milestone2b4.md`, `ops/reviews/security-adversarial-milestone2b4.md`, `ops/reviews/cto-milestone2b4-conformance.md`. Recorded as decision id=9 in the operational database. `risks.id=2` moved `open` → `mitigated` — see `ops/db/opsdb.py query "SELECT * FROM risks WHERE id=2"`.
