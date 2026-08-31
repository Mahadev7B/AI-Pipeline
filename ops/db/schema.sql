-- ops/db/schema.sql — Phase 1 operational database.
-- Implements DATA_MODEL.md verbatim. Reviewed by Red Team
-- (ops/reviews/red-team-schema.md) before implementation.
--
-- Applied by ops/db/opsdb.py, which also sets PRAGMA foreign_keys = ON
-- on every connection (SQLite does not enforce FKs unless told to).

CREATE TABLE IF NOT EXISTS projects (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  description TEXT,
  status      TEXT NOT NULL DEFAULT 'active'
              CHECK (status IN ('active','paused','done')),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS agents (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  name               TEXT NOT NULL UNIQUE,
  role               TEXT NOT NULL,
  model              TEXT NOT NULL DEFAULT 'configurable',
  model_status       TEXT NOT NULL DEFAULT 'experimental'
                     CHECK (model_status IN ('experimental','approved','rejected')),
  skills             TEXT NOT NULL DEFAULT '[]',       -- json array
  frameworks         TEXT NOT NULL DEFAULT '[]',       -- json array
  tools              TEXT NOT NULL DEFAULT '[]',       -- json array
  permissions_allow  TEXT NOT NULL DEFAULT '[]',       -- json array
  permissions_deny   TEXT NOT NULL DEFAULT '[]',       -- json array
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS tasks (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id                INTEGER REFERENCES projects(id),
  title                     TEXT NOT NULL,
  business_goal             TEXT,
  user_story                TEXT,
  priority                  TEXT,
  status                    TEXT NOT NULL DEFAULT 'BACKLOG'
                            CHECK (status IN (
                              'BACKLOG','PLANNING','MOCKUP','MOCKUP_REVIEW','ARCHITECTURE',
                              'RED_TEAM_REVIEW','READY_FOR_DEVELOPMENT','IN_DEVELOPMENT',
                              'CODE_REVIEW','QA','SECURITY_REVIEW','BLOCKED',
                              'FOUNDER_APPROVAL','READY_TO_RELEASE','DEPLOYED','DONE'
                            )),
  current_owner             TEXT,
  dependencies              TEXT,
  requirements              TEXT,
  acceptance_criteria       TEXT,
  mockup_design             TEXT,
  architecture_notes        TEXT,
  implementation_notes      TEXT,
  tests_required            TEXT,
  security_considerations   TEXT,
  developer_result          TEXT,
  code_review_result        TEXT,
  qa_result                 TEXT,
  security_result           TEXT,
  marketing_notes           TEXT,
  deployment_result         TEXT,
  blockers                  TEXT,
  founder_approval_required INTEGER NOT NULL DEFAULT 0 CHECK (founder_approval_required IN (0,1)),
  next_action               TEXT,
  created_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS task_status_history (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id         INTEGER NOT NULL REFERENCES tasks(id),
  from_status     TEXT,
  to_status       TEXT NOT NULL,
  changed_by_agent TEXT NOT NULL,
  changed_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_tsh_task ON task_status_history(task_id);

CREATE TABLE IF NOT EXISTS task_steps (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id      INTEGER NOT NULL REFERENCES tasks(id),
  title        TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending','in_progress','done')),
  weight       REAL NOT NULL DEFAULT 1,
  owner_agent  TEXT,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_steps_task ON task_steps(task_id);

CREATE TABLE IF NOT EXISTS agent_runs (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id          INTEGER NOT NULL REFERENCES agents(id),
  scope_type        TEXT NOT NULL CHECK (scope_type IN ('task','project','meeting','company')),
  scope_id          INTEGER,
  status            TEXT NOT NULL DEFAULT 'active'
                    -- 'failed' added Milestone 2B2: a real agent invocation
                    -- needs a persisted, queryable failure outcome distinct
                    -- from 'ended' (which only ever meant "over", not
                    -- "succeeded") — see ops/reviews/cto-milestone2b2-architecture.md.
                    CHECK (status IN ('active','waiting','blocked','ended','failed')),
  current_activity  TEXT,
  blocked_reason    TEXT,
  started_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_heartbeat_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at          TEXT,
  CHECK (
    (scope_type = 'company' AND scope_id IS NULL) OR
    (scope_type != 'company' AND scope_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_runs_agent_open ON agent_runs(agent_id, ended_at);

CREATE TABLE IF NOT EXISTS risks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_type   TEXT NOT NULL CHECK (scope_type IN ('task','project','company')),
  scope_id     INTEGER,
  raised_by_agent TEXT NOT NULL,
  title        TEXT NOT NULL,
  description  TEXT,
  severity     TEXT NOT NULL CHECK (severity IN ('low','medium','high')),
  status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','mitigated','resolved')),
  mitigation   TEXT,
  owner_agent  TEXT,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  resolved_at  TEXT,
  CHECK (
    (scope_type = 'company' AND scope_id IS NULL) OR
    (scope_type != 'company' AND scope_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_risks_scope_status ON risks(scope_type, scope_id, status);

CREATE TABLE IF NOT EXISTS agent_activity (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id  INTEGER NOT NULL REFERENCES agents(id),
  task_id   INTEGER REFERENCES tasks(id),
  summary   TEXT NOT NULL,
  detail    TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_activity_task ON agent_activity(task_id);

CREATE TABLE IF NOT EXISTS approvals (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id                   INTEGER REFERENCES tasks(id),
  request                   TEXT NOT NULL,
  requested_by_agent        TEXT NOT NULL,
  why                       TEXT,
  recommendation            TEXT,
  alternatives_considered   TEXT,
  expected_cost             TEXT,
  risks                     TEXT,
  consequence_if_not_approved TEXT,
  decision                  TEXT NOT NULL DEFAULT 'pending'
                            CHECK (decision IN ('approve','reject','discuss','pending')),
  decided_at                TEXT,
  created_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS decisions (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  title                     TEXT NOT NULL,
  date                      TEXT NOT NULL,
  problem                   TEXT,
  options_considered        TEXT NOT NULL DEFAULT '[]', -- json array
  decision                  TEXT NOT NULL,
  reason                    TEXT,
  tradeoffs                 TEXT,
  recommending_agent        TEXT NOT NULL,
  founder_approval_required INTEGER NOT NULL DEFAULT 0 CHECK (founder_approval_required IN (0,1)),
  founder_approval_id       INTEGER REFERENCES approvals(id),
  created_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS meetings (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  topic                 TEXT NOT NULL,
  initiated_by          TEXT NOT NULL CHECK (initiated_by IN ('founder','agent')),
  participating_agents  TEXT NOT NULL DEFAULT '[]', -- json array
  positions             TEXT NOT NULL DEFAULT '{}',  -- json object: agent -> statement
  agreements            TEXT,
  disagreements         TEXT,
  unresolved_questions  TEXT,
  recommendation        TEXT,
  founder_decision      TEXT,
  linked_decision_id    INTEGER REFERENCES decisions(id),
  created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS messages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id  TEXT NOT NULL,
  scope      TEXT NOT NULL CHECK (scope IN ('task','project','agent','meeting')),
  task_id    INTEGER REFERENCES tasks(id),
  project_id INTEGER REFERENCES projects(id),
  meeting_id INTEGER REFERENCES meetings(id),
  from_agent TEXT NOT NULL,
  to_agent   TEXT,
  body       TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK (
    (scope='task'    AND task_id    IS NOT NULL AND project_id IS NULL AND meeting_id IS NULL) OR
    (scope='project' AND project_id IS NOT NULL AND task_id    IS NULL AND meeting_id IS NULL) OR
    (scope='meeting' AND meeting_id IS NOT NULL AND task_id    IS NULL AND project_id IS NULL) OR
    (scope='agent'   AND task_id IS NULL AND project_id IS NULL AND meeting_id IS NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);

CREATE TABLE IF NOT EXISTS handoffs (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id                   INTEGER NOT NULL REFERENCES tasks(id),
  from_agent                TEXT NOT NULL,
  to_agent                  TEXT NOT NULL,
  work_completed            TEXT,
  files_changed             TEXT NOT NULL DEFAULT '[]', -- json array
  tests_added               TEXT,
  expected_behavior         TEXT,
  known_limitations         TEXT,
  receiving_agent_checklist TEXT,
  created_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
  -- Phase 3A Part B (TASK-015), §B.13: base_commit_sha/head_commit_sha
  -- (nullable TEXT, no CHECK constraint) are added by
  -- ops/db/opsdb.py's cmd_init()/_apply_additive_column_migrations(),
  -- not as a raw ALTER TABLE statement here. SQLite's ALTER TABLE ADD
  -- COLUMN has no "IF NOT EXISTS" form, so a plain ALTER TABLE statement
  -- in this executescript'd file would fail the second time `init` runs
  -- against an already-migrated database, breaking this command's own
  -- documented idempotency. opsdb.py checks PRAGMA table_info(handoffs)
  -- first and only ALTERs if the column is genuinely missing -- same
  -- additive, no-rebuild-and-copy migration the architecture doc calls
  -- for, just applied idempotently. See ops/DATA_MODEL.md.
);
CREATE INDEX IF NOT EXISTS idx_handoffs_task ON handoffs(task_id);

CREATE TABLE IF NOT EXISTS qa_results (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id           INTEGER NOT NULL REFERENCES tasks(id),
  tested_by_agent   TEXT NOT NULL,
  scenario          TEXT NOT NULL,
  result            TEXT NOT NULL CHECK (result IN ('pass','fail')),
  defect_summary    TEXT,
  reproduction_steps TEXT,
  returned_to_agent TEXT,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK (result = 'pass' OR returned_to_agent IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_qa_task ON qa_results(task_id);

CREATE TABLE IF NOT EXISTS review_results (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id          INTEGER NOT NULL REFERENCES tasks(id),
  review_type      TEXT NOT NULL CHECK (review_type IN ('code','security')),
  reviewed_by_agent TEXT NOT NULL,
  result           TEXT NOT NULL CHECK (result IN ('pass','reject')),
  findings         TEXT NOT NULL DEFAULT '[]', -- json array
  returned_to_agent TEXT,
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK (result = 'pass' OR returned_to_agent IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_review_task ON review_results(task_id);

CREATE TABLE IF NOT EXISTS deployments (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id             INTEGER NOT NULL REFERENCES tasks(id),
  version             TEXT NOT NULL,
  environment         TEXT NOT NULL,
  release_notes       TEXT,
  rollback_plan       TEXT NOT NULL,
  deployed_by_agent   TEXT NOT NULL,
  founder_authorized  INTEGER NOT NULL DEFAULT 0 CHECK (founder_authorized IN (0,1)),
  deployed_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK (founder_authorized = 1)
);

-- Phase 3A Part B (TASK-015): the automation poller's single automatic-
-- audit record. See ops/reviews/cto-phase3a-architecture.md §B.3
-- (corrected per Red Team's NB5: idx_automation_events_status and
-- idx_automation_events_started, added alongside the original
-- idx_automation_events_task -- both automation.py's own caps/spend-guard
-- queries and /automation.html's "what is running right now" query filter
-- on status/started_at; not a real performance concern at this project's
-- actual scale, added for cheap completeness/consistency).
-- `trigger_status_history_id UNIQUE` is the load-bearing, DB-enforced
-- idempotency guarantee (Founder's control #5) -- the specific
-- task_status_history row recording "this task entered CODE_REVIEW" can
-- be claimed by exactly one automation_events row, ever.
CREATE TABLE IF NOT EXISTS automation_events (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id                   INTEGER NOT NULL REFERENCES tasks(id),
  trigger_status_history_id INTEGER NOT NULL UNIQUE
                             REFERENCES task_status_history(id),
  status        TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','completed','failed','skipped')),
  outcome       TEXT CHECK (outcome IN ('pass','reject','error','interrupted','capped',NULL)),
  review_result_id INTEGER REFERENCES review_results(id),
  agent_run_id      INTEGER REFERENCES agent_runs(id),
  cost_usd          REAL,
  truncated         INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0,1)),
  skip_reason       TEXT,
  started_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_automation_events_task ON automation_events(task_id);
CREATE INDEX IF NOT EXISTS idx_automation_events_status ON automation_events(status);
CREATE INDEX IF NOT EXISTS idx_automation_events_started ON automation_events(started_at);

-- Phase 3A Part B (TASK-015): single-row kill-switch state. §B.4.
-- enabled=0 by default, seeded here at schema-apply time -- automation
-- does not run until the Founder deliberately turns it on once (the same
-- fail-closed-by-default discipline founder_auth.py's "setup required"
-- 503 already established). The only function permitted to write this
-- table is opsdb.set_automation_enabled(), called only by the two new
-- CSRF+session-gated routes (POST /api/automation/stop, /start) -- never
-- by the poller itself, never by any agent invocation.
CREATE TABLE IF NOT EXISTS automation_state (
  id           INTEGER PRIMARY KEY CHECK (id = 1),   -- exactly one row, ever
  enabled      INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0,1)),
  changed_by   TEXT NOT NULL DEFAULT 'system',
  reason       TEXT,
  changed_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
INSERT OR IGNORE INTO automation_state (id, enabled, changed_by, reason)
  VALUES (1, 0, 'system', 'Phase 3A shipped disabled by default — Founder must explicitly enable it.');
