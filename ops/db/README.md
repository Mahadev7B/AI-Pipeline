# ops/db/ — Operational Database

`operations.sqlite3` is the live company data — real tasks, real
decisions, real agent activity. `opsdb.py` is the only supported way to
write to it (see `ops/DATA_MODEL.md` for the schema and
`ops/ARCHITECTURE.md` for why SQLite). `report.py` generates
`ops/reports/CURRENT_STATUS.md` from it.

## Reading

```bash
python3 ops/db/opsdb.py agent-status
python3 ops/db/opsdb.py query "SELECT id, title, status FROM tasks ORDER BY id"
```

`query` only runs `SELECT` statements — it refuses anything else. There
is no `sqlite3` CLI binary in this environment; use `query`, not a raw
`sqlite3 ops/db/operations.sqlite3 "..."` invocation (that command does
not exist here — if you see that instruction anywhere, it's stale).

## Real product work vs. testing the tool itself

These are different things and must never share a database:

- **Real product QA** (an agent testing a real task's real feature and
  recording the result) → writes to `operations.sqlite3` via
  `opsdb.py qa-result`. This is correct, intended, live company data.
- **Testing `opsdb.py`/`report.py` themselves** (invalid input, edge
  cases, "does this command behave correctly" checks) → must **never**
  touch `operations.sqlite3`. Set `OPSDB_PATH` first:

  ```bash
  OPSDB_PATH=/tmp/opsdb-test-$$.sqlite3 python3 ops/db/opsdb.py init
  OPSDB_PATH=/tmp/opsdb-test-$$.sqlite3 python3 ops/db/opsdb.py task-create --title "..." --by qa
  OPSDB_PATH=/tmp/opsdb-test-$$.sqlite3 python3 ops/db/report.py   # writes a sibling *.CURRENT_STATUS.md, not the real report
  ```

  `report.py` respects `OPSDB_PATH` the same way, and when it's set,
  writes its report next to the scratch database instead of overwriting
  `ops/reports/CURRENT_STATUS.md` — unless `OPSDB_REPORT_PATH` is set
  explicitly. Prefer a path outside the repo (e.g. `/tmp`); `.gitignore`
  also excludes `ops/db/test*.sqlite3` and `ops/db/*.CURRENT_STATUS.md`
  as defense in depth, in case a scratch file ever lands inside the repo
  by mistake.

This isn't a style preference — a scratch task created directly against
the live database (`TASK-003`, created during Phase 1 QA and removed
2026-08-28 once this convention was established) is exactly the mistake
this file exists to prevent happening again.

## Known, disclosed authorization limitations (see `DECISIONS.md` DEC-004)

1. `approval-decide` requires `--confirm-founder-decision`, but that is a
   deliberate speed bump, not real authentication — anything running the
   CLI can still pass the flag. Real enforcement needs an identity layer,
   which is Phase 2/3 (Control Center) scope.
2. Every subagent's `Bash` tool grant is not scoped below the tool
   category — a subagent's role doc may say "no implementation tools,"
   but it technically still has shell access beyond `opsdb.py`. This is
   an environment-level limitation, not something Phase 1 code can fix.

Neither is hidden or "fixed" by working around it in this README — they
are open, tracked in `DECISIONS.md`, and intended to be revisited once
Phase 2/3 introduces real identity/permission scoping.
