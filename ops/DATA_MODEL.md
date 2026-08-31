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

### agent_runs *(new — Phase 1 clarification; `status` widened Milestone 2B2)*
`id, agent_id, scope_type (task/project/meeting/company), scope_id
(nullable — null only when scope_type=company), status (active/waiting/
blocked/ended/failed), current_activity, blocked_reason (nullable), started_at,
last_heartbeat_at, ended_at (nullable)`

An agent is **Working** if it has a row here with `status=active` and no
`ended_at`. **Blocked** / **Waiting** come from a row with that status
instead. **Available** means no open run at all. `scope_type=company`
covers coordination work with no single task/project/meeting behind it
(e.g. Chief of Staff triage, CEO general strategy review, PM compiling a
status report) — company-scoped work is still a real run, not an
exception to the rule. See `ARCHITECTURE.md`, "Derived UI state must be
deterministic."

`status='failed'` *(Milestone 2B2)*: added because `'ended'` only ever
meant "this run is over," with no way to persist *how* it ended.
Ask-Agent (`ops/control-center/agent_runtime.py`,
`ops/control-center/server.py`) needs a real, queryable distinction
between a successful and a failed model invocation — `'failed'` is
terminal exactly like `'ended'` (`ended_at` is set either way), it only
differs in outcome. Added via SQLite's rebuild-and-copy technique (no
`ALTER` of a `CHECK` constraint); all 13 pre-existing rows were
`'ended'` and are unaffected. See
`ops/reviews/cto-milestone2b2-architecture.md`.

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

**`scope='agent'` is this table's "company/general" concept** — same
thing `agent_runs.scope_type='company'` means, just an existing,
different word for it (confirmed during Milestone 2B2's architecture
review; not renamed, since `messages` had zero rows either way and a
purely cosmetic cross-table rename didn't clear the "don't casually
mutate Phase 1 schema" bar — see
`ops/reviews/cto-milestone2b2-architecture.md`). Milestone 2B2's
Ask-Agent conversations use `thread_id = "agent-<name>-company"` with
`scope='agent'`.

Phase 3A Part A (TASK-015) puts a real model invocation behind
`thread_id = "agent-orchestrator-company"` for the first time —
previously, every `messages`/`agent_runs` row attributed to
`orchestrator` was a deterministic Python step wearing that identity's
name (e.g. meeting-participant validation), never a real `claude --agent
orchestrator` subprocess. The Chief of Staff Founder interface (`POST
/api/chief-of-staff/ask`) is exactly that first real invocation — no
schema change was needed for this: it's the same `agent-<name>-company`
formula Ask-Agent already established, applied to a new agent name the
schema already supported. See `ops/reviews/cto-phase3a-architecture.md`
§A.1-A.5 and `ops/SECURITY.md`, "Chief of Staff Founder Interface (Phase
3A Part A, TASK-015)."

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

**`base_commit_sha`, `head_commit_sha` (nullable TEXT — Phase 3A Part B,
TASK-015).** A plain, additive `ALTER TABLE ADD COLUMN` pair (no `CHECK`
constraint changed, so this did not need the rebuild-and-copy technique
Milestone 2B2's `agent_runs.status` widening required) — applied
idempotently by `opsdb.py`'s `cmd_init()` (checked via `PRAGMA
table_info()` first, since `ALTER TABLE ADD COLUMN` has no `IF NOT
EXISTS` form and a raw statement in `schema.sql` would break `init`'s own
documented idempotency on a second run). Populated by Developer at
handoff time (`opsdb.py handoff --base-commit-sha <sha>
--head-commit-sha <sha>`, `git rev-parse HEAD` before/after the task's own
work) — nullable for backward compatibility with every pre-Phase-3A
handoff row, and for non-code handoffs where the concept doesn't apply.
This is what lets the automation poller (`ops/control-center/automation.py`)
assemble a real `git diff`/file-content transcript between two explicit
commits, rather than a timestamp heuristic — a wrong base commit would
feed a *misleading*, not merely incomplete, transcript to an automated
reviewer. See `ops/reviews/cto-phase3a-architecture.md` §B.13.

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

### automation_events *(new — Phase 3A Part B, TASK-015)*
`id, task_id, trigger_status_history_id (unique fk → task_status_history),
status (running/completed/failed/skipped), outcome
(pass/reject/error/interrupted/capped, nullable), review_result_id
(nullable fk → review_results), agent_run_id (nullable fk → agent_runs),
cost_usd (nullable), truncated (bool), skip_reason (nullable), started_at,
ended_at (nullable)`

The single automatic-audit record for `ops/control-center/automation.py`'s
poller. `trigger_status_history_id UNIQUE` is the load-bearing,
database-enforced idempotency mechanism: the specific
`task_status_history` row recording "this task entered `CODE_REVIEW`" can
be claimed by exactly one `automation_events` row, ever — the claim
(`INSERT`, `status='running'`) happens before any real invocation, inside
its own transaction (`opsdb.create_automation_event()`), as the very
first step for any eligible-looking trigger row — strictly before every
eligibility check (a missing handoff, an invalid SHA, an invalid file
path), not only before the real model invocation. This is deliberate:
every eligibility/cap failure still produces exactly one permanent,
claimed, `status='skipped'` row, so the same trigger event is never
re-evaluated on a later poll cycle. A `review_results` row referenced by
some `automation_events.review_result_id` is automated; every other
`review_results` row is human-supervised — no new column on that shared
table. `outcome='capped'` is used for the two genuine per-task-lifetime
and daily-spend/count cap scenarios specifically (not the per-cycle batch
cap, which never claims a row at all — a candidate beyond the per-cycle
limit is simply picked up on a later cycle). See
`ops/reviews/cto-phase3a-architecture.md` §B.3/§B.7/§B.10.

### automation_state *(new — Phase 3A Part B, TASK-015)*
`id (=1, exactly one row, ever), enabled (bool, default 0), changed_by
(default 'system'), reason (nullable), changed_at`

The single-row kill switch. Seeded `enabled=0` (disabled) at schema-apply
time via `INSERT OR IGNORE` — automation does not run until the Founder
deliberately turns it on once, the same fail-closed-by-default discipline
`founder_auth.py`'s "setup required" 503 already established. The only
function permitted to write this table is `opsdb.set_automation_enabled()`,
called only by the two new CSRF+session-gated routes (`POST
/api/automation/stop`/`start`) — never by the poller itself, never by any
agent invocation. See `ops/reviews/cto-phase3a-architecture.md` §B.4/§B.5.

### meetings
`id, topic, initiated_by (founder/agent), participating_agents (json),
positions (json — agent → statement/evidence/assumptions), agreements,
disagreements, unresolved_questions, recommendation, founder_decision
(nullable), linked_decision_id (nullable fk → decisions), created_at`

**`participating_agents` shape (Milestone 2B3B round 2, TASK-011).** From
this round on, `opsdb.create_meeting()` writes this column as a JSON array
of objects, not bare strings:

```json
[{"name": "cto", "source": "selected", "requested_by": null},
 {"name": "security", "source": "requested", "requested_by": "founder"}]
```

`source` is `"selected"` for CEO (always) and every participant CEO
nominated/Chief of Staff validated at meeting-creation time, or
`"requested"` for a participant added later via `POST
/api/meetings/<id>/request-perspective` (item 2). `requested_by` is
`null` for a `"selected"` entry, or the literal string `"founder"` for a
`"requested"` one — this system has no per-person Founder identity (see
`ops/SECURITY.md`), so `"founder"` is the only value it can honestly
record, the same string every other Founder-attributed write in this
schema already uses (`initiated_by`, `decide_meeting(by="founder")`).

**Backward compatibility.** Every `meetings` row created before this
round shipped holds the *original* flat shape — a bare JSON array of
name strings, e.g. `["ceo", "cto", "product"]` — written by the pre-round-2
`create_meeting()`. No migration/backfill was performed (Red Team's
Milestone 2B3B round 2 review, finding 5a, considered one and left the
choice to Development — a normalization helper was judged the smaller,
lower-risk change for this early-stage feature's small row count).
**Every reader of this column, without exception, must go through
`opsdb.normalized_participants()` (or its single-entry counterpart,
`opsdb._normalize_participant()`)** — never index or iterate the raw JSON
directly. A bare string normalizes to `{"name": <string>, "source":
"selected", "requested_by": null}` — the only thing a pre-existing row
could have meant. This is not optional: a bare-string row read as if it
were the new object shape (or vice versa) raises `TypeError` at the first
membership/attribute access, which is exactly the regression Red Team's
review caught (finding 5b) against `generate_meetings.py`'s two
pre-round-2 readers before this round's fix.

**Participant-cap semantics (unrevised).** `MAX_MEETING_PARTICIPANTS = 6`
(`ops/control-center/agent_runtime.py`) is the single, binding total cap
on `participating_agents` — CEO plus every `"selected"` and every
`"requested"` entry combined, never two separate pools. CTO's Milestone
2B3B round 2 architecture proposal considered letting a manually-
requested addition (item 2) exceed this cap via a new
`MAX_REQUESTED_PARTICIPANTS` constant; Red Team's review of that round
did not affirm the revision (the cited mockup evidence didn't support the
specific number proposed, and it materially enlarged an already-reviewed
cost bound) — see `ops/reviews/red-team-milestone2b3b-round2.md`, finding
1. `opsdb.add_meeting_participant()` therefore enforces
`MAX_MEETING_PARTICIPANTS` as the total cap, atomically, with no second
constant anywhere in the codebase.

**Thread-id conventions for `messages.meeting_id`-scoped rows (Milestone
2B3B round 2).** A single meeting now spans up to three distinct kinds of
thread, all sharing `scope='meeting'` and the same `meeting_id` — do not
filter by `meeting_id` alone when a *specific* thread's content is
wanted, since two different kinds of thread can carry messages from the
same `from_agent`:
- `meeting-{id}` — the shared positions thread every participant's
  *original* position is written to (unchanged since Milestone 2B3B;
  item 2's manually-requested participants write here too, once —
  it's a real position on the topic, just gathered later).
- `meeting-{id}-orchestrator` — Chief of Staff's one-time validation note
  (item 1), never a participant's position.
- `meeting-{id}-{agent_name}` — one distinct thread per (meeting,
  participant) follow-up conversation (item 3), separate from that
  participant's original position in `meeting-{id}` above.

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

- The Chief of Staff is the only writer of `tasks.status` and
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
