"""ops/db/testing_guard.py — structural refusal to run against the live
database, for ad hoc test scripts.

Two real live-database test-contamination incidents have happened in
this project (TASK-003 during Phase 1 QA; four leftover test meetings
found and removed during Milestone 2B3B's Founder conformance review) —
both from a script that imported `opsdb.py`'s functions directly without
`OPSDB_PATH` being set in that exact process. `ops/db/README.md` already
documents the convention (set OPSDB_PATH before testing); this module
makes the mistake fail loudly instead of relying on remembering to read
that convention every time.

Usage — add ONE line at the top of any ad hoc test script, before
importing opsdb itself:

    import sys
    sys.path.insert(0, "ops/db")
    import testing_guard  # noqa: F401 — raises if OPSDB_PATH isn't a scratch path
    import opsdb

If OPSDB_PATH was not set (or was set to the live database path) in the
process running the script, this raises SystemExit immediately, before
any write can happen.

This module must NEVER be imported by opsdb.py, server.py, or any other
production code path — it exists only for test scripts to opt into. Real
CLI/HTTP usage must keep writing to the live database with no extra
ceremony; this guard is not wired into that path and never will be.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import opsdb  # noqa: E402

_LIVE_DB_PATH = (opsdb.DB_DIR / "operations.sqlite3").resolve()

if opsdb.DB_PATH.resolve() == _LIVE_DB_PATH:
    raise SystemExit(
        "testing_guard: refusing to proceed — OPSDB_PATH is not set (or "
        f"resolves to the live database, {_LIVE_DB_PATH}), and this "
        "script imported ops/db/testing_guard.py, which requires a "
        "scratch database. Set OPSDB_PATH to a /tmp path in THIS exact "
        "process before running, e.g.:\n"
        "  OPSDB_PATH=/tmp/opsdb-test-$$.sqlite3 python3 your_script.py\n"
        "See ops/db/README.md."
    )

print(f"testing_guard: OK — running against scratch database {opsdb.DB_PATH}", file=sys.stderr)
