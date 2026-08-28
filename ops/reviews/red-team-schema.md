# Red Team Review — Phase 1 Schema (`DATA_MODEL.md` / `ops/db/schema.sql`)

Reviewed before Developer implementation, per the Founder's explicit
requirement for Phase 1.

## Overengineering / simpler-alternative check

15 tables for a system with one Founder and currently only sample data.
Each one maps to a requirement the Founder stated directly (task
lifecycle, decisions, approvals, handoffs, QA/review results,
deployments, meetings, messages, risks, task_steps, agent_runs,
projects, agents) — none are speculative. Two design choices considered
and rejected as unnecessary complexity for this phase:

- **`meetings.positions` as JSON, not a normalized `meeting_positions`
  table.** Accepted as-is — a 16th table to make six agent statements
  independently queryable is not justified yet. Revisit only if a real
  need to filter/query individual positions shows up.
- **A `current_run_id` column on `agents` instead of a separate
  `agent_runs` table.** Rejected — that would duplicate state (two
  places that could disagree) instead of the one queryable table the
  Founder specifically asked for. Keep `agent_runs` as the sole source.

**Verdict on scope: not overengineered.** Every table traces to a stated
requirement; no speculative future-proofing found.

## Required before implementation (blocking)

1. **Enums need `CHECK` constraints, not just app-level validation.**
   `tasks.status`, `agent_runs.status`/`scope_type`, `risks.severity`/
   `status`/`scope_type`, `qa_results.result`, `review_results.result`/
   `review_type`, `approvals.decision`, `messages.scope`,
   `projects.status` — every one of these is currently only documented
   as an allowed value list, not enforced by the database. A bug in
   `opsdb.py` could otherwise write an invalid status straight into the
   source of truth. `schema.sql` must add `CHECK (col IN (...))` for all
   of them.
2. **Foreign keys must actually be enforced.** SQLite does not enforce
   `FOREIGN KEY` by default — it silently accepts orphaned references
   unless `PRAGMA foreign_keys = ON` is set on every connection.
   `opsdb.py` must set this pragma on every connection it opens, not
   just declare the FKs in DDL and assume they're checked.
3. **Scope-consistency constraints, not just documentation.** `agent_runs`
   and `risks` document "scope_id nullable, null only when
   scope_type='company'" and `messages` documents "exactly one of
   task_id/project_id/meeting_id is set" — both are currently prose, not
   enforced. Add `CHECK` constraints (SQLite supports multi-column CHECK
   expressions) so the database itself rejects a row that violates its
   own documented invariant, rather than relying on every future caller
   of `opsdb.py` to get it right.

## Recommended, not blocking

4. Add indexes on every foreign-key column used in a lookup the
   deterministic-state formulas depend on: `agent_runs(agent_id,
   ended_at)`, `task_steps(task_id)`, `risks(scope_type, scope_id,
   status)`. Not needed at current data volume, but free to add now and
   avoids a silent full-table-scan habit forming.
5. Timestamps should be stored as ISO-8601 text via SQLite's
   `CURRENT_TIMESTAMP` default, not Unix epoch integers — matches the
   rest of this system's preference for human-readable, git-diffable
   state over compact encodings.

## Security/privacy

No PII or credential fields anywhere in the schema — confirmed. The
`.sqlite3` file being committed to Git is already documented as a known,
accepted limitation in `DATA_MODEL.md`; Red Team concurs it's acceptable
for one-founder sequential operation and not worth a server/hosting
dependency to avoid at this phase.

## Confirms the Founder's specific concern is addressed

No column anywhere allows an agent to write a raw progress percentage,
a raw "Working" status flag, or a raw health string — progress comes
only from `task_steps`, status only from `agent_runs`, health only from
a query over `risks` + blocked tasks. Confirmed structurally, not just
by convention.

## Verdict

**PASS, conditional on items 1–3.** Development may proceed once
`schema.sql` includes the `CHECK` constraints and `opsdb.py` sets
`PRAGMA foreign_keys = ON`. Items 4–5 are recommended and included in
this pass since they're low-cost, but are not a blocking condition.
