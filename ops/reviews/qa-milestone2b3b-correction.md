# QA — Milestone 2B3B correction (TASK-010)

Performed directly (no subagent-dispatch tool present this session).
All testing used a scratch database (`OPSDB_PATH=/tmp/2b3b-correction/scratch.sqlite3`),
verified via the new `ops/db/testing_guard.py` guard itself (which
refused to run against the live DB when deliberately invoked without
`OPSDB_PATH`, confirming the guard's own correctness before using it for
everything else in this pass).

## Verdict: PASS

## 1. Real crash/restart recovery (the objective defect's own fix)

- Started a real server against a scratch DB, seeded with all 8 meeting
  participant agents.
- Posted a real `POST /api/meetings` request; confirmed via `ps aux`
  that two real `claude --agent <name>` subprocesses (`financial`,
  `red-team`) were genuinely in flight.
- `kill -9`'d the server process at that exact moment (not a clean
  shutdown) — confirmed the process and its subprocess group both
  terminated (no leftover `claude` processes).
- Confirmed via direct query: exactly one meeting-scoped `agent_runs`
  row was left `status='active', ended_at=NULL` (red-team's, the one
  still mid-flight at the kill).
- Restarted the server: it printed
  `"reconciled 1 orphaned meeting-participant run(s) from a prior server process."`
  and the row's status became `'failed'` with a real `ended_at`
  timestamp.
- Loaded the meeting's detail page: 200, and the reconciled participant
  renders the same honest "Selected, but no response was recorded" card
  every other real failure already renders — no visual or functional
  difference between a live failure and a crash-reconciled one.

## 2. Both reconciliation patterns fire independently in the same restart

- Manually created one orphaned Ask-Agent run (`scope_type='company'`)
  and one orphaned meeting run (`scope_type='meeting'`) directly against
  the scratch DB.
- A single server restart printed both distinct log lines and both rows
  were correctly reconciled to `'failed'` — confirms the fix does not
  silently favor one pattern over the other.

## 3. Test-isolation guard

- Confirmed the guard raises `SystemExit` with no `OPSDB_PATH` set (would
  otherwise resolve to the live DB) — verified the exact live path it
  reports matches the real `operations.sqlite3` location.
- Confirmed the guard passes silently through to a real scratch DB when
  `OPSDB_PATH` is set to a `/tmp` path — printed confirmation of the
  scratch path used.
- Confirmed (Code Review) it is never imported by any production code
  path.

## 4. No regression to existing 2B3B functionality

- Every route added in 2B3B (`POST /api/meetings`,
  `POST /api/meetings/<id>/decide`, `GET /meetings/<id>.html`,
  `GET /meetings.html`) still functioned correctly during this pass's
  live testing — the meeting created for the crash test rendered and
  behaved identically to 2B3B's own original QA pass aside from the one
  deliberately-crashed participant.

## Test isolation verification for this correction itself

Every command in this correction pass that wrote to a database used
`OPSDB_PATH` pointed at `/tmp/2b3b-correction/scratch.sqlite3`, and the
guard module was used directly in the ad hoc scripts that manually
inserted orphaned rows. No command in this correction pass wrote to the
live `operations.sqlite3` except the sanctioned `opsdb.py` CLI calls
used later, in this document's own closing section, to record the
review-gate results and regenerate reports — the same pattern every
prior milestone has used (test against scratch, record real audit
history against live).

No blocking findings. Proceeding to Security.
