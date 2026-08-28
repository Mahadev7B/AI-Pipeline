# Security Review — Phase 2, Milestone 1 (TASK-004)

## Scope
`ops/db/derived_state.py`, `ops/control-center/generate_overview.py`,
the resulting `ops/control-center/overview.html`.

## Findings

1. **Genuinely read-only, not just by convention.** The database
   connection is opened with `mode=ro` in the URI. Verified directly: an
   `INSERT` attempted through this connection raises
   `sqlite3.OperationalError: attempt to write a readonly database` —
   SQLite itself refuses it, not just a code-review convention that
   could be bypassed by a future edit. **PASS.**
2. **HTML injection: confirmed blocked.** A task titled
   `<script>alert(1)</script> & "quotes" <b>bold</b>` was created (QA,
   scratch DB) and the generated page contains only the escaped form
   (`&lt;script&gt;...`) — no raw tag reaches the output. **PASS.**
3. **Zero external network dependencies.** Unlike the Phase 0 mockup
   (which loads a Google Fonts stylesheet), this generator uses only a
   system-font stack — the page renders identically online or fully
   offline. Not required, but a genuine improvement worth noting.
   **PASS.**
4. **No credentials, secrets, or new third-party dependencies.**
   Confirmed by grep and import inspection — stdlib only (`html`, `os`,
   `sqlite3`, `sys`, `datetime`, `pathlib`, `urllib.parse`). **PASS.**
5. **File permissions.** `overview.html` was `rw-r--r--` after
   generation — same class of issue as `operations.sqlite3` in the
   Phase 1 review. Fixed: `chmod 0o600` in `main()`, same reasoning as
   `opsdb.py`'s `cmd_init`. **Fixed.**
6. **The URI-path bug Code Review found and fixed (`#`/`?` in a path
   silently opening the wrong database) is itself a security-adjacent
   finding**, not just a correctness one — a misconfigured `OPSDB_PATH`
   could otherwise cause this tool to silently read from an unintended
   file rather than failing loudly. Re-verified fixed here independently
   of Code Review's own test. **Confirmed fixed.**

## Verdict

**PASS.** No new gaps beyond the two already tracked in `DECISIONS.md`
DEC-004 (neither applies here — this milestone has no write path and no
subagent Bash usage at all).
