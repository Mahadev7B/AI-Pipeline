# DATA_MODEL.md — Live Operational State (Design Only)

**Phase 0 status: design document only. No database file is created in this
phase.** SQLite is instantiated in Phase 1, from this schema, after the
Founder approves this proposal and a mockup direction.

## Why SQLite

Free, local, zero-config, no server, no paid service — matches "no paid
PM software." It becomes the single writable source of truth for live
state; `DECISIONS.md` becomes a generated, git-readable mirror of the
`decisions` table (see `ARCHITECTURE.md`).

## Tables

### agents
`id, name, role, model, model_status (experimental/approved/rejected),
skills (json), frameworks (json), tools (json), permissions_allow (json),
permissions_deny (json), created_at, updated_at`

### tasks
All fields from `/ops/templates/task.md`: `id, title, business_goal,
user_story, priority, status, current_owner, dependencies, requirements,
acceptance_criteria, mockup_design, architecture_notes,
implementation_notes, tests_required, security_considerations,
known_risks, developer_result, code_review_result, qa_result,
security_result, marketing_notes, deployment_result, blockers,
founder_approval_required, next_action, created_at, updated_at`

### task_status_history
`id, task_id, from_status, to_status, changed_by_agent, changed_at, note`

### agent_activity
`id, agent_id, task_id (nullable), summary, detail, created_at`

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

### handoffs
Mirrors `/ops/templates/handoff.md`: `id, task_id, from_agent, to_agent,
work_completed, files_changed (json), tests_added, expected_behavior,
known_limitations, receiving_agent_checklist, created_at`

### decisions
Mirrors `DECISIONS.md`'s format: `id, title, date, problem,
options_considered (json), decision, reason, tradeoffs,
recommending_agent, founder_approval_required (bool), founder_approval_id
(nullable fk → approvals), created_at`

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

### meetings *(new — supports Executive Meetings, see EXECUTIVE_MEETINGS.md)*
`id, topic, initiated_by (founder/agent), participating_agents (json),
positions (json — agent → statement/evidence/assumptions), agreements,
disagreements, unresolved_questions, recommendation, founder_decision
(nullable), linked_decision_id (nullable fk → decisions), created_at`

## Rules

- The Orchestrator is the only writer of `tasks.status` and
  `task_status_history`. Nothing else mutates status directly (see
  `ARCHITECTURE.md`).
- `approvals.decision` starts `pending` and is only ever set by the
  Founder, never by an agent.
- `qa_results.result = fail` and `review_results.result = reject` must
  always set `returned_to_agent` — a failure that doesn't route anywhere
  is a bug in the tooling, not a valid end state (rule 21,
  `CODING_STANDARDS.md`).
