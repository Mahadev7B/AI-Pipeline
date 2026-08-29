# Code Review — Milestone 2B3B correction (TASK-010)

Reviewing the Development fix against
`ops/reviews/cto-milestone2b3b-correction-architecture.md` and
`ops/reviews/red-team-milestone2b3b-correction.md`'s 4 conditions.
Performed directly (no subagent-dispatch tool present this session).

## Verdict: PASS

## Changes reviewed

- `ops/control-center/server.py`: `_reconcile_orphaned_ask_agent_runs()`
  renamed to `_reconcile_orphaned_runs()`, now makes two calls to
  `opsdb.reconcile_orphaned_runs()` — one per activity-LIKE pattern —
  each with its own distinct log line. Call site in `main()` and the
  module-docstring cross-reference both updated to match.
- `ops/db/testing_guard.py` (new): opt-in structural refusal to run
  against the live database.

## Condition-by-condition verification

1. **Live kill -9 + restart test** — confirmed by direct execution, not
   trusted from a description: a real meeting was posted via HTTP
   against a scratch DB, the server process was `kill -9`'d while two
   real participant `claude` subprocesses were genuinely in flight
   (confirmed via `ps aux` showing both before the kill), leaving
   exactly one meeting-scoped `agent_runs` row `status='active',
   ended_at=NULL`. A fresh server start reconciled it to `'failed'` and
   printed `"reconciled 1 orphaned meeting-participant run(s)..."`. The
   meeting's detail page still rendered 200, with the correct existing
   "Selected, but no response was recorded" honest fallback for the
   reconciled participant — no special-casing was needed, confirming
   Red Team's read of `generate_meetings.py`'s render logic.
2. **Both reconciliation calls always execute** — confirmed by direct
   code read (`ask_count = ...`; `if ask_count: print(...)`; then
   unconditionally `meeting_count = ...; if meeting_count: print(...)` —
   no early return between them) and by a second live test: one orphaned
   Ask-Agent run and one orphaned meeting run were created together, and
   a single restart printed both distinct lines
   ("reconciled 1 orphaned Ask-Agent run(s)..." and "reconciled 1
   orphaned meeting-participant run(s)...") — neither masked the other.
3. **Resolved-path comparison in `testing_guard.py`** — confirmed by
   reading the module: both `opsdb.DB_PATH` and the computed live path
   go through `.resolve()` before comparison, not a raw string compare.
4. **`testing_guard.py` is never imported by production code** —
   confirmed by `grep -rn "testing_guard" ops/ .claude/` outside the
   module's own file and `ops/db/README.md` — zero hits in `opsdb.py`,
   `server.py`, or any `.claude/agents/*.md`.

## Additional findings (non-blocking)

- The renamed function's docstring correctly cross-references both the
  original 2B2 Red Team finding and this correction's own Founder
  conformance review, preserving the audit trail rather than rewriting
  history.
- No other startup/reconciliation code path exists that might have the
  same scoping gap — grepped for every `reconcile_orphaned_runs(` call
  site; there is exactly one caller (`server.py`'s
  `_reconcile_orphaned_runs()`), now covering both patterns.

No blocking findings. Proceeding to QA.
