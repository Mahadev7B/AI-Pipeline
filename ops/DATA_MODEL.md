# DATA_MODEL.md — Live Operational State

**Phase 1 status: implemented.** This is the schema `ops/db/schema.sql`
implements verbatim; `ops/db/opsdb.py` is the only supported way to write
to it. See `ARCHITECTURE.md` for why SQLite is the writable source of
truth and `DECISIONS.md` for the durable, generated mirror.

## Why SQLite

Free, local, zero-config, no server, no paid service — matches "no paid
PM software." It is the single writable source of truth for live state.
The `.sqlite3` file itself is committed to Git for this phase (no server
to host it on) — see "Known limitation" at the end of this document.

## Tables

### projects *(new — Phase 1 clarification)*
`id, name, description, status (active/paused/done), created_at`

Minimal on purpose — this is not multi-project management, it exists so
`tasks.project_id` and `messages.project_id` reference something real
instead of a bare, undefined ID. Do not add fields to this table without
a real, current need for them.

### agents
`id, name, role, model, model_status (experimental/approved/rejected),
skills (json), frameworks (json), tools (json), permissions_allow (json),
permissions_deny (json), created_at, updated_at`

No status/activity column here on purpose — see "Deterministic derived
state" below. Whether an agent is Working/Waiting/Blocked/Available is
never stored; it's computed from `agent_runs`.

### tasks
All fields from `/ops/templates/task.md`, plus a project link: `id,
project_id (nullable fk → projects), title, business_goal, user_story,
priority, status, current_owner, dependencies, requirements,
acceptance_criteria, mockup_design, architecture_notes,
implementation_notes, tests_required, security_considerations,
developer_result, code_review_result, qa_result, security_result,
marketing_notes, deployment_result, blockers, founder_approval_required,
next_action, created_at, updated_at`

No `progress` column and no `known_risks` free-text column — both are now
structured, queryable state: progress comes from `task_steps`, risks come
from the `risks` table.

### task_status_history
`id, task_id, from_status, to_status, changed_by_agent, changed_at, note`

### task_steps *(new — Phase 1 clarification)*
`id, task_id, title, status (pending/in_progress/done), weight (default
1), owner_agent, created_at, completed_at (nullable)`

The objective mechanism progress percentages come from. See "Deterministic
derived state" below for the formula. An agent cannot report a progress
number directly — there is no column for one to write to.

### agent_runs *(new — Phase 1 clarification)*
`id, agent_id, scope_type (task/project/meeting/company), scope_id
(nullable — null only when scope_type=company), status (active/waiting/
blocked/ended), current_activity, blocked_reason (nullable), started_at,
last_heartbeat_at, ended_at (nullable)`

An agent is **Working** if it has a row here with `status=active` and no
`ended_at`. **Blocked** / **Waiting** come from a row with that status
instead. **Available** means no open run at all. `scope_type=company`
covers coordination work with no single task/project/meeting behind it
(e.g. Orchestrator triage, CEO general strategy review, PM compiling a
status report) — company-scoped work is still a real run, not an
exception to the rule. See `ARCHITECTURE.md`, "Derived UI state must be
deterministic."

### risks *(new — Phase 1 clarification)*
`id, scope_type (task/project/company), scope_id (nullable — null only
when scope_type=company), raised_by_agent, title, description, severity
(low/medium/high), status (open/mitigated/resolved), mitigation
(nullable), owner_agent (nullable), created_at, resolved_at (nullable)`

Company Health is computed from this table (open risks by severity) plus
blocked-task and failed-review counts — never from an agent's prose
summary of "how things feel." See `ARCHITECTURE.md`.

### agent_activity
`id, agent_id, task_id (nullable), summary, detail, created_at`

A free-text activity log entry — narrative, for the Activity feed. Not
what Working/Waiting/Blocked/Available is computed from; that's
`agent_runs`.

### messages
`id, thread_id, scope (task/project/agent/meeting), task_id (nullable),
project_id (nullable), meeting_id (nullable), from_agent, to_agent
(nullable — null = broadcast/founder), body, created_at`

A conversation is not required to belong to a task. `scope` says which of
the four kinds a thread is, and exactly one of `task_id` / `project_id` /
`meeting_id` is set to match it — `agent`-scoped threads (a general
question to an agent, not tied to a specific piece of work) leave all
three null. Every scope is persisted and auditable the same way; `agent`
scope is not a lesser, unsaved case.

### approvals
Mirrors `/ops/templates/founder-approval.md`: `id, task_id (nullable),
request, requested_by_agent, why, recommendation, alternatives_considered,
expected_cost, risks, consequence_if_not_approved, decision
(approve/reject/discuss/pending), decided_at, created_at`

`decision` transitions *(Milestone 2B1)*: `pending → approve|reject|discuss`,
`discuss → approve|reject`. `approve`/`reject` are terminal — no code path
transitions out of them. `discuss → discuss` is rejected (already flagged,
re-clicking is a no-op, not a new state). Enforced atomically by
`opsdb.decide_approval()`, the only function permitted to write this
column — see `ops/control-center/server.py` for the Founder-facing write
path. Nothing currently ties a pending/discuss approval to its parent
task's status changing underneath it (e.g., the task being independently
marked `DONE` elsewhere) — noted as a known gap, not a blocker.

### handoffs
Mirrors `/ops/templates/handoff.md`: `id, task_id, from_agent, to_agent,
work_completed, files_changed (json), tests_added, expected_behavior,
known_limitations, receiving_agent_checklist, created_at`

### decisions
Mirrors `DECISIONS.md`'s format: `id, title, date, problem,
options_considered (json), decision, reason, tradeoffs,
recommending_agent, founder_approval_required (bool), founder_approval_id
(nullable fk → approvals), created_at`

**Two independent numbering schemes — do not conflate them.** This
table's `id` is a plain auto-incrementing sequence with no relationship
to the `DEC-NNN` labels used in `DECISIONS.md` — those are assigned by
hand in the markdown file as the durable narrative record, while `id`
here just orders database rows. A row's `title` is the only reliable way
to match a database decision to its `DECISIONS.md` entry (if it has
one — not every database decision is significant enough to also get a
hand-written `DEC-NNN` entry, and not every `DEC-NNN` entry originates
from a database row — DEC-001 through DEC-004 predate most of this
table's contents). Found via a stray `task_status_history` note
("Mockup approved as DEC-004") that referred to `decisions.id = 1` using
a label that `DECISIONS.md` later assigned to something else entirely —
see `ops/reviews/cto-phase2-milestone1-conformance.md`.

### qa_results
`id, task_id, tested_by_agent, scenario, result (pass/fail), defect_summary
(nullable), reproduction_steps (nullable), returned_to_agent (nullable),
created_at`

### review_results
`id, task_id, review_type (code/security), reviewed_by_agent, result
(pass/reject), findings (json), created_at`

### deployments
`id, task_id, version, environment, release_notes, rollback_plan,
deployed_by_agent, founder_authorized (bool), deployed_at`

### meetings
`id, topic, initiated_by (founder/agent), participating_agents (json),
positions (json — agent → statement/evidence/assumptions), agreements,
disagreements, unresolved_questions, recommendation, founder_decision
(nullable), linked_decision_id (nullable fk → decisions), created_at`

## Deterministic derived state

These are the exact formulas `ops/db/report.py` and, from Phase 2, the
Control Center must use — never an LLM's free-text estimate:

- **Agent status** — `SELECT status FROM agent_runs WHERE agent_id=? AND
  ended_at IS NULL ORDER BY started_at DESC LIMIT 1`; no open run =
  Available.
- **Task progress %** — `100 * SUM(weight WHERE status='done') /
  SUM(weight)` over that task's `task_steps`. A task with no steps yet
  has no progress percentage to show — not 0%, not a guess; the UI shows
  "not yet broken into steps."
- **Company Health** — a simple, disclosed threshold, not a hidden
  formula: `Good` if zero `high`-severity open risks and ≤1 blocked task;
  `Fair` if one high-severity open risk or 2–3 blocked tasks; `Poor`
  otherwise. Change the thresholds by proposing a `DECISIONS.md` entry,
  not by editing the report script silently.
- **Elapsed activity time** — `now - agent_runs.started_at` (or
  `last_heartbeat_at` where present), computed at read time.

## Rules

- The Orchestrator is the only writer of `tasks.status` and
  `task_status_history`. Nothing else mutates status directly (see
  `ARCHITECTURE.md`).
- Each agent writes its own `agent_runs`, `agent_activity`, `qa_results`,
  and `review_results` rows — that's real per-table ownership, not a
  free-for-all; `opsdb.py`'s subcommands are grouped by which agent role
  they belong to (documented in the CLI's own `--help`).
- `approvals.decision` starts `pending` and is only ever set by the
  Founder, never by an agent.
- `qa_results.result = fail` and `review_results.result = reject` must
  always set `returned_to_agent` — a failure that doesn't route anywhere
  is a bug in the tooling, not a valid end state (rule 21,
  `CODING_STANDARDS.md`).
- No table stores a value that section "Deterministic derived state"
  above computes — if a future change adds one, that's a schema bug.

## Known limitation

The `.sqlite3` file is committed to Git because this system has no server
to host a database on, per "no paid infrastructure." Git handles binary
diffs for a small SQLite file adequately for one founder operating
sequentially through agents, but it is not a real concurrency story —
two people (or two automated processes) writing at once would conflict
at the Git level, not the database level. Acceptable for Phase 1; revisit
if Phase 3 automation ever means multiple writers at once.
