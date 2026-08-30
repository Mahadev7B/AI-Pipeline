# QA — Phase 2, Milestone 2B4: Founder Identity Verification (TASK-013)

Reviewed against `ops/reviews/cto-milestone2b4-architecture.md` (§1-13),
`ops/reviews/security-milestone2b4-threat-model.md`,
`ops/reviews/red-team-milestone2b4-architecture.md`, and the shipped code
(`ops/control-center/founder_auth.py`, `server.py`, `layout.py`). Code
Review already passed this milestone
(`ops/reviews/code-review-milestone2b4.md`); this pass is user-perspective,
adversarial, black-box HTTP testing against a real running server, not a
re-read of the code.

## Verdict: PASS

Every one of the 27 mapped scenarios behaved exactly as designed. No
defects found. Three additional adversarial checks beyond the original
list (malformed/truncated credential-file recovery, `setup`/`change`
safety-rail behavior, mid-request client disconnect) also passed cleanly.

## Isolation discipline

All testing ran against a scratch copy at
`/tmp/.../scratchpad/qa-milestone2b4/ops/{control-center,db}` (mirroring
the real `ops/` layout so `server.py`'s relative imports resolved
correctly), with `OPSDB_PATH` pointed at a scratch SQLite file created via
`opsdb.py init`, and `founder_auth.py`'s `CREDENTIAL_PATH` (resolved
relative to the scratch copy's own `__file__`) never touched the real
repo's credential path. Two scratch server processes ran on ports
18420/18421 (never touching a real port the Founder would use). Verified
before and after: `git status --short` in the real checkout showed
nothing at any point, and `ops/control-center/.founder_credential.json`
never existed there. Both scratch server processes and the scratch
directory were torn down at the end of the run; ports confirmed free.

## Scenario-by-scenario results

1. **Correct passphrase → login succeeds, gated page reachable.** PASS.
   `POST /api/login` with the right passphrase returned `303` to
   `/overview.html` with a session cookie; a follow-up `GET
   /overview.html` with that cookie returned `200`.
2. **Incorrect passphrase → clean failure.** PASS. `401`, no
   `Set-Cookie`, no session created (verified: the response carried no
   cookie and a subsequent request with no cookie was still
   unauthenticated).
3. **Empty passphrase → clean failure, not a crash.** PASS. `401`, same
   as any other wrong passphrase. Server unaffected.
4. **Malformed requests.** PASS on all four sub-cases against
   `/api/login`:
   - Missing `Content-Length`/no body at all → `400`.
   - 100KB body (`MAX_BODY_BYTES` is 64KB) → `400`.
   - Non-UTF-8 bytes in the passphrase field → `401` (decoded via
     `errors="replace"`, then just failed verification — no crash).
   - Null byte embedded in the passphrase field → `401`, same clean
     handling.
   Server stayed healthy (`200` on `/login`) after all four.
5. **Session cookie attributes.** PASS. Captured raw `Set-Cookie` header
   on a real login: `fc_session=...; HttpOnly; SameSite=Strict; Path=/`
   — `HttpOnly` present, `SameSite=Strict` present, no `Secure`, no
   `Max-Age`/`Expires`. Exactly as designed.
6. **Idle timeout.** PASS. Ran a second scratch instance with
   `IDLE_TIMEOUT_S` patched to 3s (source-level constant edit, isolated
   copy, real end-to-end HTTP test, not a mock). Logged in, confirmed
   `200` immediately, waited 4s with zero activity, confirmed the next
   `GET` returned `303` to `/login` and the server logged `"session
   expired (idle)"`.
7. **Absolute timeout despite activity.** PASS. Same patched instance,
   `ABSOLUTE_TIMEOUT_S` set to 6s. Logged in, then polled every 1.4s
   (well under the 3s idle window) — polls at t≈1.4/2.8/4.2/5.6s all
   returned `200`; the poll at t≈7.0s (past the 6s absolute cap) returned
   `303`, and the server logged `"session expired (absolute)"` — forced
   re-auth despite continuous activity, exactly as designed.
8. **Logout.** PASS. `POST /api/logout` cleared the session
   (`Set-Cookie: fc_session=; Max-Age=0`); a follow-up request with the
   old cookie jar was `303` (unauthenticated). Logging out a second time,
   and logging out with no session cookie at all, both returned the same
   clean `303` — idempotent, no error, matching the design's stated
   requirement.
9. **Server restart wipes sessions.** PASS. Logged in, confirmed the
   cookie worked (`200`), killed the process, started a fresh one against
   the same scratch credential/DB, and confirmed the *old* cookie now got
   `303` (unauthenticated) against the new process.
10. **Stale browser tab.** PASS — same evidence as item 8/9: a cookie
    captured before logout, replayed afterward, is correctly rejected on
    its very next request, never treated as still-valid.
11. **Forged/tampered cookie, session fixation.** PASS on both angles.
    A made-up `fc_session=AAAA...` value got `303` (never accepted).
    Attempting a fixation attack — sending a login POST with an
    attacker-chosen `Cookie: fc_session=ATTACKER_CHOSEN_SESSION_ID`
    header already set — the server's `Set-Cookie` response minted its
    own fresh random session id (`xktg6R...`), never adopting or
    reflecting the attacker's chosen value; the attacker's original value
    was confirmed still invalid afterward (`303`).
12. **CSRF on login/logout.** PASS. `POST /api/login` without the
    `token` field → `403`. `POST /api/logout` without the `token` field
    → `403` (confirmed with an explicit empty body and Content-Length: 0,
    ruling out a curl artifact where no body/no Content-Length header at
    all produces a `400` from the earlier body-size check instead — that
    `400` is itself correct malformed-request handling, not a CSRF-bypass
    finding).
13. **Replay across restart.** PASS. Captured a real CSRF token from one
    server process, restarted the process (fresh `SESSION_TOKEN`), and
    replayed the old token in a login POST — `403`, rejected.
14. **Full-app-lock.** PASS. With no session, `GET` on every page type
    (`/`, `/overview.html`, `/pipeline.html`, `/agents.html`,
    `/decisions.html`, `/meetings.html`, `/inbox.html`) consistently
    returned `303` to `/login` — no gated content rendered anywhere.
15. **Fail-closed with no credential file.** PASS. Started a completely
    fresh scratch server with no `.founder_credential.json` present.
    Every route tested — every GET page, `/login` itself, `POST
    /api/login`, `POST /api/approvals/1/decide` — returned `503` with the
    fixed setup-required message. No bypass, no default credential.
16. **Brute force / lockout, fast rejection.** PASS. Drove the counter to
    5 failures, confirmed the 6th attempt (even with the *correct*
    passphrase) got `429` in ~10ms — confirmed via wall-clock timing this
    was the fast-reject path, not another ~1s scrypt call.
17. **Concurrent authorized logins.** PASS. Fired 2 simultaneous
    correct-passphrase logins; both got `303` with two distinct
    `fc_session` values (`oDsyt...` / `8xHlr...`) — no corruption, no
    collision.
18. **Concurrent unauthorized attempts (60-concurrent, independently
    reproduced).** PASS, and matches Code Review's own numbers closely
    enough to independently confirm C1's fix: fired 60 truly simultaneous
    wrong-passphrase POSTs at my own scratch server. Result: **5 real
    verifications (`401`), 55 fast-rejected (`429`), total wall time
    3.6s**. This is exactly the shape C1's full-serialization fix
    predicts — only the first 5 requests to win the lock pay the real
    ~1s scrypt cost; everything after the 5th failure is rejected near-
    instantly without touching `hashlib.scrypt`. Server logs showed no
    errors; server stayed responsive; confirmed zero rows written to
    `agent_runs`/`messages`/`approvals` from this flood (see item 25).
19. **XSS-shaped passphrase.** PASS. `<script>alert(1)</script>` as the
    passphrase → ordinary `401`. Grepped the full response body: no
    unescaped reflection anywhere, no `alert(1)` substring present at
    all — the value is never echoed, not even escaped-and-shown.
20. **SQLi-shaped passphrase.** PASS. `' OR '1'='1` → ordinary `401`,
    server unaffected (this route never touches SQL, as expected — no
    crash, no behavior change).
21. **Secret absent from HTML.** PASS. Captured every rendered page
    (overview/pipeline/agents/decisions/meetings/inbox, `/login`, and the
    `401`/`403` error pages) and grepped all of them for the passphrase,
    the stored hash, the stored salt, and both session ids used in
    testing — zero matches anywhere. The only credential-adjacent value
    ever present in HTML is the CSRF `token` field, which is the
    intended, by-design behavior (unchanged since 2B1).
22. **Secret absent from logs.** PASS. Grepped the full server stderr
    log across the entire test run for the passphrase, the stored hash,
    and both session ids — zero matches. Log lines matched the design's
    stated format exactly (`founder login FAILED (n/5)`, `login lockout
    triggered`, `session expired (idle/absolute)`, etc.) with no
    passphrase/hash/salt/session-id content in any of them.
23. **Secret absent from SQLite.** PASS. Dumped the entire scratch
    `OPSDB_PATH` database (`sqlite3.Connection.iterdump()`) and grepped
    for the passphrase, hash, and salt — zero matches (no `opsdb.*` call
    exists anywhere in the credential/session code, confirmed
    behaviorally, not just by reading the code). The real repo's
    `operations.sqlite3` was never opened by any command run during this
    QA pass (all commands used `OPSDB_PATH` pointed at the scratch file).
24. **Secret absent from Git.** PASS. `git status --short` in the real
    checkout was checked before, during (spot checks), and after the
    entire QA pass — empty every time. No `.founder_credential*` file
    ever appeared in the real repo checkout.
25. **No DB mutation / no agent_runtime invocation after failed auth.**
    PASS. After dozens of failed logins, a 60-concurrent flood, and
    XSS/SQLi-shaped attempts, queried the scratch DB directly:
    `agent_runs` = 0 rows, `messages` = 0 rows, `approvals` with a
    decision = 0 rows. Zero mutation from any unauthorized/failed
    traffic.
26. **Existing-feature regression — write routes still wired
    correctly.** PASS. Seeded a real pending approval via
    `opsdb.py approval-create`, then: (a) with a valid Founder session +
    valid CSRF token, `POST /api/approvals/1/decide` → `303`, and the DB
    row's `decision` really did flip to `approve` — full end-to-end
    proof the pre-existing CSRF-gated write path is untouched and still
    reaches `opsdb.decide_approval()`. (b) Logged out, seeded a second
    pending approval, and confirmed the identical POST against it (with
    a stale/no session) returned `401` and the DB row was **not**
    mutated — confirming the new Founder-session gate is additive, not a
    replacement, and that it actually blocks the write rather than just
    decorating the response. (Did not additionally invoke a real
    Executive Meeting create/decide/follow-up route, since that spends a
    real costed model invocation via `agent_runtime`/`meeting_orchestrator`
    — the `do_POST()` dispatch table confirms every meeting route sits
    behind the exact same two checks, in the same order, as
    `/api/approvals/<id>/decide`, so the approvals-route proof generalizes;
    spending real invocation budget to re-prove identical wiring per route
    wasn't judged worth it.)
27. **Founder Inbox/Overview/Agents pages render correctly, "Log out"
    present.** PASS. With a valid session, all six nav pages returned
    `200` and each contained exactly one "Log out" affordance (posting to
    `/api/logout` with the CSRF token field) in the nav — matches
    `layout.py`'s `_logout_form_html()`/`nav_html()` design.

## Additional adversarial checks beyond the mapped list

- **Malformed/truncated credential file recovery** (Red Team's
  non-blocking recommendation): truncated `.founder_credential.json` to
  invalid JSON mid-run. `GET /login` still rendered fine (that route
  only checks file *existence*, not parseability, per §3's design).
  `POST /api/login` against the corrupted file returned a clean `503`
  (setup-required page), not a `500`/traceback — the `CredentialError` →
  503 path works as documented. Restored the valid file and confirmed
  login immediately worked again — no server restart needed, matching
  the hot-reload design.
- **`setup`'s overwrite refusal**: running `founder_auth.py setup` again
  against an existing credential file exits 1 with a clear message and
  leaves the original passphrase intact (confirmed: the original
  passphrase still logged in afterward).
- **`change` with the wrong current passphrase**: exits 1, "Nothing was
  changed," and confirmed the original passphrase still works afterward
  — the safety rail does not silently rotate on a wrong guess.
- **Interrupted client mid-POST**: sent a login POST and killed the
  client mid-flight (`timeout 0.05 curl ...`); server survived, stayed
  responsive on the next real request.

## Notes for the written record

No defects found — this is a clean PASS across every mapped scenario plus
the additional adversarial checks. The disclosed residual limitations
(shared-lockout self-DoS, F1; same-OS-user/Bash-agent bypass, §11) are
architecture-level, already disclosed in `ops/SECURITY.md`-bound language
in the reviewed documents, and out of scope for this QA pass to
"fix" — they behaved exactly as disclosed when probed (e.g., a correct
passphrase submitted during an active lockout window does get rejected
with `429`, confirming the disclosed self-DoS shape is real and matches
the documentation, not a surprise).
