# CTO architecture update — Milestone 2B3B correction (TASK-010)

Triggered by the Founder's own conformance review (see
`ops/reviews/founder-conformance-review-milestone2b3b.md`, item #18).
Two things in scope for this correction pass: an objective defect that
needs no Founder scope decision, and a test-isolation safeguard the
Founder explicitly asked to be evaluated and, if small enough,
implemented in the same pass.

## 1. Objective defect: meeting-scoped `agent_runs` never reconciled on restart

**Problem.** `server.py`'s `_reconcile_orphaned_ask_agent_runs()` (built
in 2B2/2B3A specifically to fix "a crashed process leaves an open
`agent_runs` row forever") only ever passes
`agent_runtime.ASK_AGENT_ACTIVITY_LIKE` to
`opsdb.reconcile_orphaned_runs()`. Milestone 2B3B introduced a second,
structurally identical run-creator
(`meeting_orchestrator._gather_position()`, `current_activity` matching
`agent_runtime.MEETING_ACTIVITY_LIKE`) but never extended the startup
reconciliation to cover it. A server crash mid-meeting leaves that
participant's row `status='active', ended_at IS NULL` permanently —
that agent's derived status (`ops/db/derived_state.py`) would show it
as perpetually "Working" on a meeting that no longer exists, with no
code path that ever corrects it short of a manual DB edit.

**Why this needs no Founder scope decision.** This is not a product
feature or a design choice — `opsdb.reconcile_orphaned_runs(conn,
activity_like_pattern, status)` is already fully generic (it takes the
pattern as a parameter); the fix is purely "call the function that
already exists, with the pattern that already exists, a second time."
No new architecture, no new table, no new UI.

**Design.** Generalize
`_reconcile_orphaned_ask_agent_runs()` → `_reconcile_orphaned_runs()`
(name no longer Ask-Agent-specific) and call
`opsdb.reconcile_orphaned_runs()` twice — once per activity-LIKE
pattern — logging each count separately so a restart's console output
still distinguishes "N orphaned Ask-Agent run(s)" from "N orphaned
meeting-participant run(s)," matching the existing log message's
specificity rather than collapsing it into one vaguer count.

No change to `opsdb.py` is needed — `reconcile_orphaned_runs()` already
supports this by taking the pattern as an argument; this is entirely a
`server.py`-side fix, consistent with "server.py must never hold a raw
UPDATE of its own" (already true, unchanged).

## 2. Test-isolation structural guard

**Problem.** Two live-database test-contamination incidents have now
occurred (TASK-003 in Phase 1; the 4 leftover test meetings found and
removed during this milestone's closure). Both share the same root
cause: an ad hoc test script imported `opsdb.py`'s functions directly
without `OPSDB_PATH` being set in that exact process. `ops/db/README.md`
already documents the convention, but a documented convention is
reviewer discipline, not a structural guard — the Founder explicitly
asked not to rely on that alone.

**Design — smallest correct mechanism, not a test framework.** A new,
tiny module, `ops/db/testing_guard.py`: importing it raises immediately
(`SystemExit`, not a soft warning) if the resolved `opsdb.DB_PATH`
equals the real live database path. Any ad hoc test script adds one line
(`import testing_guard`) before importing `opsdb` itself; if `OPSDB_PATH`
wasn't set in that process, the script fails loudly before it can write
anything, instead of silently succeeding against
`operations.sqlite3`. This does not touch `opsdb.py`'s or `server.py`'s
real CLI/HTTP behavior at all — real product usage never imports this
module, so nothing about legitimate operation changes.

**Limitation, disclosed rather than hidden:** this is opt-in per script
— it cannot retroactively guard a script that doesn't import it, and it
does not change the CLI's normal command surface (which must remain
able to write to the live DB for real product work). It closes the
specific, observed failure mode (a script silently defaulting to the
live path) for any future script that adopts the one-line convention;
it does not eliminate the possibility of a future incident from a
script that doesn't adopt it. `ops/db/README.md` updated to state this
convention as required going forward for ad hoc/interactive testing.

Recorded via `opsdb.py review-result --task-id 10 --type code --by cto`
against the live database (this is a correction to the existing TASK-010,
not a new task).
