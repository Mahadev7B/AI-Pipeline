# Code Review — Phase 2, Milestone 2B4: Founder Identity Verification (TASK-013)

Reviewing the actual shipped diff, independently, against the approved
design (`ops/reviews/cto-milestone2b4-architecture.md` incl. §13's C1–C3
fixes, `ops/reviews/security-milestone2b4-threat-model.md`'s 24-item
threat table, `ops/reviews/red-team-milestone2b4-architecture.md`'s F1/F2
findings). Not trusting the Developer's own commit-message report of test
results — re-derived or independently reproduced every load-bearing claim
below.

**Diff reviewed**: `git diff 4332168^..7bdd040` (the correct range —
`4332168` is TASK-013's first commit and predates `95d01ee`, the last
Chief-of-Staff-rename commit, in chronological order; the range the task
prompt suggested, `95d01ee..7bdd040`, would have silently dropped
`founder_auth.py`'s entire history). Confirmed this by `git log` order and
by diffing both ranges' stats before picking the correct one.

## Verdict: PASS

No blocking findings. Two small non-blocking notes at the end.

## 1. C1 — concurrency race fix (the original blocking Security finding)

Read `server.py`'s `_handle_login()` directly, not the report. `_LOGIN_LOCK`
is acquired at the top of the method and held across the **entire**
check-lockout → `founder_auth.verify_passphrase()` (the real `~1s` scrypt
call) → increment-or-reset section — there is no early exit or lock
release between the lockout check and the failure-counter update. This is
exactly what C1 required (full serialization, not a "dict get/set" guard).

**Independently reproduced, not just read.** Built a fully isolated
scratch copy of `ops/control-center` + `ops/db` under
`/tmp/.../scratchpad/c1test/ops/{control-center,db}` (directory structure
mirrored so `Path(__file__)`-relative paths resolve inside the scratch
tree — module-level `CREDENTIAL_PATH = Path(__file__).resolve().parent /
".founder_credential.json"` binds at import time, so a same-process
monkeypatch attempt does *not* redirect it; a real filesystem copy does).
Created a scratch credential file via `founder_auth._write_credential_atomic_new()`
directly (never touched the real repo's `.founder_credential.json`), ran
the scratch `server.py` as a subprocess against a scratch `OPSDB_PATH` on
a scratch port (18422, never the real 8420), fetched the live CSRF token
from `GET /login`, then fired 60 simultaneous wrong-passphrase
`POST /api/login` requests from 60 threads.

**Result: exactly 5 × 401 (real verifications) and 55 × 429 (clean lockout
rejections)** — matching the Developer's claimed 5/55 split exactly. Cross-
checked against the scratch server's own log: exactly 5
`"founder login FAILED"` lines, exactly 55 `"login attempt rejected"`
lines, exactly one `"lockout triggered"` line. This is the correct,
predictable outcome of the code as written (first 5 threads to acquire
`_LOGIN_LOCK` run a real scrypt verification and fail; the 5th sets
`_locked_until`; every later acquirer sees `now < _locked_until` and gets
an immediate 429 without ever calling scrypt) — confirms C1 is genuinely
fixed, not merely reported fixed. Scratch environment fully torn down
after the test (`rm -rf` the scratch tree, `pkill` the scratch server
process); `git status` on the real repo is clean.

## 2. C2 — CSRF on `/api/login`

`do_POST()` computes `is_login`/`is_logout`/route matches first, then
unconditionally does `MAX_BODY_BYTES`/decode/`parse_qs`, then calls
`self._require_csrf_token(fields)` — which checks
`secrets.compare_digest(token, SESSION_TOKEN)` — **before** branching to
`self._handle_login(fields)`. `_handle_login()` itself never touches
`fields.get("passphrase", ...)` until after that CSRF check has already
returned successfully to its caller. Confirmed live in the scratch test
above: `login_page()` embeds the current `SESSION_TOKEN` as a hidden
field, and the fired requests only succeeded in reaching the lockout/verify
logic because they carried a valid token — an invalid-token version (not
separately scripted, but trivially implied by `_require_csrf_token`'s
unconditional placement ahead of the `is_login`/`is_logout` dispatch)
would 403 before ever reaching `_handle_login`. Matches C2 exactly.

## 3. C3 — malformed payload handling

`/api/login` and `/api/logout` go through the identical
`Content-Length`/`MAX_BODY_BYTES` check, `.decode("utf-8",
errors="replace")`, `parse_qs()` call already used by every other route —
no new parsing branch was added for these two routes. `fields.get("passphrase",
[""])[0]` defaults a missing field to `""`, which
`founder_auth.derive_hash()`/`hashlib.scrypt` accepts without raising
(confirmed by reading `derive_hash()`'s docstring and Red Team's own
independent reproduction, not just re-asserted). Matches C3.

## 4. Credential handling (founder_auth.py)

- No `print`/log call anywhere in `founder_auth.py` touches the
  passphrase, derived hash, or salt — read every `print()`/`sys.stderr.write()`
  call site in the file; all reference only status/paths/error types, never
  secret material.
- `setup`: `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` —
  atomic creation at the final mode, no TOCTOU window, `O_EXCL` gives a
  second guard against the `path.exists()` race, matching the design
  exactly (`_write_credential_atomic_new`).
- `change`: writes to a sibling `.tmp-<pid>-<hex>` file (dot-prefixed
  `.founder_credential` stem, correctly matching the `.gitignore` glob per
  §13's requirement) with the same `O_EXCL|0600` creation, then
  `os.replace()` — single atomic POSIX rename, matching the design exactly
  (`_write_credential_atomic_replace`).
- Grepped the entire diff and `ops/control-center/founder_auth.py` for any
  `opsdb`/`sqlite3`/`conn.execute` reference: none exist. Confirmed via
  `git diff 4332168^..7bdd040 -- ops/db/opsdb.py ops/db/schema.sql` = empty
  (see item 9 below) — the credential path is never touched by SQL or by
  `opsdb.py`.

## 5. Session cookie

`_set_session_cookie()`: `Set-Cookie: fc_session=<id>; HttpOnly;
SameSite=Strict; Path=/` — read the literal header-construction f-string
directly. No `Secure` attribute (correct per design: plain HTTP over
loopback), no `Max-Age`/`Expires` (correct: session cookie, cleared only
by browser close or explicit logout). `_clear_session_cookie()` correctly
adds `Max-Age=0` only for the logout-clearing case, not the normal
session-setting path.

## 6. Full-app-lock

Traced `do_GET()`'s dispatch directly: the fail-closed credential-gate
check runs first (item 7), then the only unauthenticated path is
`path == "/login"`; every other branch is reached only after
`self._authenticated_session() is None` has already been checked and, if
true, redirected to `/login` — this check sits above the entire
path-dispatch if/elif chain (`/`, `/overview.html`, `/pipeline.html`,
`/agents.html`, `/agents/<name>.html`, `/decisions.html`,
`/meetings.html`, `/meetings/<id>.html`, `/inbox.html`), so no GET route
can be reached without a valid session except `/login` and the (also
unauthenticated-by-necessity) setup-required 503 page. Matches design §7
exactly — this is the "whole Control Center requires unlock" decision
both Security and Red Team concurred with.

## 7. Fail-closed

`_check_credential_gate()` is called as the literal first statement in
both `do_GET()` and `do_POST()`, before path parsing, before CSRF checks,
before anything else — a missing credential file returns 503
(`setup_required_page()`) on every route, GET and POST, `/login` and
`/api/login` included. Confirmed by reading the first lines of both
methods directly.

## 8. F1 disclosure in SECURITY.md

`ops/SECURITY.md`'s new "Founder Identity Verification (Milestone 2B4,
TASK-013)" section explicitly discloses the shared-lockout self-DoS
residual risk, using language that traces Red Team's F1 finding faithfully
(not softened or omitted): "an attacker already inside this design's own
assumed threat class... can flood `/api/login` and reliably win most of
each 30-second lockout cycle's 5 real-verification slots, denying the
Founder's own genuine logins far more often than not for as long as the
flood continues," with the same "no cheap in-scope fix... risks.id=3's
territory" framing as the source finding. Matches.

## 9. No opsdb.py / schema.sql / agent_runtime.py / meeting_orchestrator.py changes

`git diff 4332168^..7bdd040 -- ops/db/opsdb.py ops/db/schema.sql
ops/control-center/agent_runtime.py ops/control-center/meeting_orchestrator.py`
produces **zero** output — confirmed empty, not just "small." This
feature never touches SQLite or the model-invocation boundary, as
required.

## 10. Maintainability / architecture consistency

`founder_auth.py`'s CLI shape (`argparse.ArgumentParser(...)`,
`add_subparsers(dest="command", required=True)`,
`sub.add_parser(...).set_defaults(func=...)`) matches `opsdb.py`'s
existing convention exactly (compared side by side). Stdlib-only
end-to-end (`argparse`, `base64`, `getpass`, `hashlib`, `json`, `os`,
`secrets`, `sys`, `time`, `pathlib` — no third-party import). No new
abstractions beyond what the design specified — no extra class hierarchy,
no speculative generality. The `server.py` diff is narrowly scoped: hunks
land only in the module docstring, imports, new module-level constants,
`_error_page`/new helper functions, the top of `do_GET()`/`do_POST()`
(the two new gate checks + login/logout dispatch), and `main()` (one new
startup call). The bodies of the seven pre-existing `_handle_*` write
handlers are byte-for-byte unchanged — confirmed via the diff hunk
locations, not just visual skim. The `generate_*.py` diffs are minimal
`token=token` threading additions to already-existing `page()` calls,
matching architecture doc §12's explicit "no changes required for the
write forms themselves" scoping. No unnecessary refactoring found
anywhere in the diff.

## 11. Race conditions beyond C1 — SESSIONS dict access

Grepped every `SESSIONS`/`SESSIONS_LOCK` reference in `server.py`. Every
read, insert, and delete of `SESSIONS` (`_authenticated_session()`'s
get/delete×2, `_handle_login()`'s insert, `_handle_logout()`'s pop) is
inside a `with SESSIONS_LOCK:` block — no code path touches the dict
outside the lock. Session-fixation is structurally impossible:
`_authenticated_session()` only ever looks up or deletes; `_handle_login()`
is the sole insertion point, always with a freshly minted
`secrets.token_urlsafe(32)`, never a client-supplied value.

## 12. Test coverage / the claimed 60-concurrent-request test

No test file was committed and no `qa_results`/activity-log row records
the Developer's claimed test independently of the commit message prose —
so per the task's own instruction, I did not take the report on faith. I
built and ran an equivalent test myself (§1 above, full methodology and
numbers there) against an isolated scratch copy of the code, a scratch
credential file, and a scratch `OPSDB_PATH` — never the live DB or the
repo's real `.founder_credential.json`. My own independently reproduced
result (5×401 / 55×429, matching the scratch server's own audit log
exactly) corroborates the Developer's reported numbers. This is the one
place I'd flag as a process gap worth raising non-blocking below: the
concurrency proof exists only as commit-message prose, not as a
repo-committed regression test, so it can silently rot on the next change
to `_handle_login()`.

## Non-blocking notes (do not gate this PASS)

1. **No regression test committed for C1.** The 60-concurrent-request
   proof is real (independently reproduced above) but lives only in the
   commit message, not as an automated test anyone will re-run on a future
   change to `_handle_login()`/`_LOGIN_LOCK`. Recommend a follow-up task to
   add a lightweight concurrency test (can reuse this review's scratch-copy
   technique) so a future refactor that accidentally narrows the lock's
   scope gets caught automatically rather than requiring a manual re-audit.
2. **Task DB state**: `tasks.status` for TASK-013 currently reads
   `BACKLOG` and `risks.id=2` is still `open` (correctly — a
   post-implementation Security pass, not this review, is the gate for
   moving it to `mitigated`, per both the CTO doc and Security's own
   review). Flagging only so whoever owns task-state transitions notices
   the status hasn't been advanced to `CODE_REVIEW`/`SECURITY` yet — not a
   code defect.

## Summary

C1, C2, C3 all verified against the actual shipped code, not the
Developer's report — C1 additionally independently reproduced under real
concurrent load with numbers matching the claim exactly. Credential
handling, cookie flags, full-app-lock, fail-closed gating, F1 disclosure,
DB/agent-runtime isolation, and architecture/CLI-convention consistency
all confirmed by direct reading. No blocking findings. **PASS.**
