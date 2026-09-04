# Security — post-implementation ADVERSARIAL review — Phase 2, Milestone 2B4: Founder Identity Verification (TASK-013)

Distinct from and in addition to the architecture-stage threat-model
review (`ops/reviews/security-milestone2b4-threat-model.md`, which
reviewed the design before code existed). This review attacks the
ACTUAL SHIPPED CODE — `ops/control-center/founder_auth.py`, `server.py`
(do_GET/do_POST, all routes/state), `layout.py` — after it already
PASSed Code Review (`ops/reviews/code-review-milestone2b4.md`) and QA
(`ops/reviews/qa-milestone2b4.md`). Did not take either prior pass's
claims on faith — independently re-verified C1/C2/C3 by reading the
shipped code directly and by penetration-testing a real running scratch
server, not by re-reading the reviews.

## Verdict: PASS

No exploitable finding. Every one of the 13 adversarial test categories
in scope was actively attempted against a real running instance of the
shipped code (not just read/reasoned about) and every attack failed
closed. One non-blocking test-methodology observation (not a security
defect) is noted at the end.

## Isolation discipline

All testing ran against isolated scratch copies of `ops/control-center` +
`ops/db` under
`/tmp/claude-0/.../scratchpad/sec-adv-2b4/{,timeout-test,timeout-test3,malformed-test}`,
each with its own `OPSDB_PATH`-scoped scratch SQLite database (created via
`opsdb.py init`, never the real `operations.sqlite3`) and its own
`.founder_credential.json` created via direct calls to
`founder_auth._write_credential_atomic_new()` inside the scratch copy
(module-level `CREDENTIAL_PATH = Path(__file__).resolve().parent /
".founder_credential.json"` binds to the scratch tree because the whole
directory structure was physically copied, not monkeypatched). Four
scratch server processes ran on ports 18996–18999, never a real port.
Two of the four scratch copies had `IDLE_TIMEOUT_S`/`ABSOLUTE_TIMEOUT_S`
source-level constants patched to single-digit seconds for fast timeout
testing (same technique QA used).

Verified before, during (spot checks), and after the entire pass:
`git status --short` in the real checkout was empty every time; a
machine-wide `find / -xdev -iname ".founder_credential*"` sweep (outside
`/tmp`) found nothing; the real `ops/db/operations.sqlite3` was never
opened by any command in this pass (every command used a scratch
`OPSDB_PATH`). All four scratch server processes were killed and all four
scratch ports (18996–18999) confirmed free (`ss -ltn`) at the end; all
scratch directories and temp test scripts were deleted.

## Findings by adversarial category

**1. Session-token theft/replay.** Captured a real `fc_session` cookie
and a real `SESSION_TOKEN` CSRF value from a live login. Replayed each
independently in contexts where they shouldn't work:
- `fc_session` from server A (port 18999) sent to server B (port 18997,
  separate process, separate in-memory `SESSIONS` dict) →
  `303` (rejected — independent per-process session state, as designed).
- Valid `fc_session` cookie sent on a write POST with the CSRF `token`
  field omitted entirely → `403` (CSRF check runs before the session
  check in `do_POST()`, so possessing a valid session cookie alone is
  never sufficient).
- Valid `fc_session` cookie sent with an *empty* `token=` field → `403`,
  same as above.
- A stale `SESSION_TOKEN` captured from one server process (port 18997)
  replayed against a different live process (port 18999) with a valid
  session cookie for that *second* process → `403` (per-process token,
  no cross-process reuse).

**2/3. Authentication bypass / direct route invocation.** Enumerated
every route from `do_POST()`'s dispatch table (`/api/login`,
`/api/logout`, `/api/approvals/<id>/decide`, `/api/agents/<name>/ask`,
`POST /api/meetings`, `/api/meetings/<id>/decide`,
`/api/meetings/<id>/request-perspective`,
`/api/meetings/<id>/followup`, `/api/meetings/<id>/retry` — 9 total, 7
pre-existing + 2 new) and hit every single one directly with `curl`, no
browser, no valid session, no CSRF token:
```
/api/login              -> 403
/api/logout              -> 403
/api/approvals/1/decide  -> 403
/api/agents/cto/ask      -> 403
/api/meetings            -> 403
/api/meetings/1/decide   -> 403
/api/meetings/1/request-perspective -> 403
/api/meetings/1/followup -> 403
/api/meetings/1/retry    -> 403
```
All 9 fail closed at the CSRF gate. Re-tested all 7 pre-2B4 write routes
with a *valid* CSRF token but *no* session cookie: all 7 → `401`
(Founder-session gate). `/api/logout` with a valid token and no cookie →
`303` (idempotent by design — confirmed correct, not a bypass, since it
performs no state-changing effect beyond an already-no-op removal).

Method confusion: `GET` on every write route → `303` (redirect to
`/login`, no route match exists for GET on those paths, falls through
the same auth-gate-first logic). `HEAD`/`OPTIONS`/`PUT` on a write
route → `501` (no handler defined — `http.server`'s own safe default,
not a bypass surface).

Path traversal / trailing slash / query string / case sensitivity on
gated paths: `/overview.html/`, `/inbox.html?x=1`, `//inbox.html`,
`/inbox.html%2f`, `/./inbox.html`, `/../etc/passwd`,
`/agents/../../../etc/passwd.html`, `/agents/%2e%2e%2fsecret.html`,
`/LOGIN`, `/Overview.html` — every one of these, with no session cookie,
→ `303` (redirect to `/login`; none matches the exact-string `path ==
"/login"` allowlist check or any dispatch branch, so all fall through
to the auth-required path). No case-insensitive route match exists, no
traversal reaches outside the fixed dispatch table.

**4. Forged/tampered cookies and headers.**
- Made-up but plausible `secrets.token_urlsafe(32)`-shaped `fc_session`
  value → `303` (not a `SESSIONS` key, rejected).
- SQL-injection-shaped (`' OR '1'='1`) and script-injection-shaped
  (`<script>alert(1)</script>`) cookie values → `303`, no crash, no
  reflection (this route never touches SQL and the cookie value is never
  echoed).
- Two `fc_session=` pairs in one `Cookie:` header (forged first, real
  second, and vice versa): `_read_session_cookie()` returns the *first*
  matching `fc_session=` substring it finds in header-part order. Forged
  first → `303` (rejected, since the real value is never consulted).
  Real first → `200` (works, since the real value is found first). In
  neither ordering does a forged value ever succeed — this is a
  first-match parsing quirk, not an authentication bypass, since the
  forged value is simply never accepted regardless of position.
- Two separate literal `Cookie:` HTTP headers on one request: Python's
  `email.message.Message.get()` (which `BaseHTTPRequestHandler.headers`
  uses) returns only the *first* occurrence — confirmed only the first
  header's value is ever consulted. No fallback to a second header
  exists, so this cannot be used to smuggle a forged value past a real
  one either.
- Oversized cookie value (2 MB, via a raw `http.client` request bypassing
  shell arg-length limits): the stdlib's own header-line-length guard
  triggered first (`code 431, message Line too long`), server logged it
  cleanly, stayed responsive on the very next request (`GET /login` →
  `200` immediately after). No crash, no resource exhaustion observed.

**5. Malformed credential-file state.**
- Credential file valid JSON but missing a required key (`hash` omitted)
  → `founder_auth.verify_passphrase()` raises `CredentialError`
  ("credential file is malformed: KeyError: 'hash'"), and the live HTTP
  path (`POST /api/login` against this file) → `503` (setup-required
  page), not an unhandled `500` — confirmed via a live request, not just
  a direct function call.
- Credential file with an unsupported `"kdf"` value (`"md5"`) →
  `CredentialError` ("credential file has an unrecognized kdf"), and
  live `POST /api/login` → `503`, same clean fail-closed path — also
  confirmed live (`GET /login` still renders `200`, since that route
  only checks file *existence*, matching the documented design; the
  `POST` that actually needs to parse the file is what correctly 503s).
- Credential file with wrong (world-readable, `0644`) permissions: the
  application layer does not check/enforce file mode at read time —
  `verify_passphrase()` behaves identically (correct-passphrase → `True`,
  wrong-passphrase → `False`) regardless of the file's OS permission
  bits. This is **not** a defect: 0600 was never claimed to be an
  application-enforced invariant, only a creation-time convention against
  *other OS users* — the architecture doc's own §11 (and this milestone's
  earlier threat-model review) already discloses that file permissions
  don't defend against the same-OS-user attacker class this design
  explicitly doesn't try to close.

**6. Stale sessions.** Two source-patched scratch instances
(`IDLE_TIMEOUT_S`/`ABSOLUTE_TIMEOUT_S` set to single-digit seconds):
- Logged in, let the session sit idle past `IDLE_TIMEOUT_S` with zero
  activity, then immediately attempted a real write
  (`POST /api/approvals/2/decide`) → `401`, server logged
  `"session expired (idle)"`, and the target DB row's `decision`
  column was confirmed **still `pending`** afterward (queried the
  scratch DB directly) — no silent partial-trust write occurred.
- Logged in, polled `GET /overview.html` every ~1s (well under a
  300s idle window) past a 6-second `ABSOLUTE_TIMEOUT_S`, confirmed the
  session was still rejected (`303`) despite continuous recent
  activity, server logged `"session expired (absolute)"`, and an
  immediate write attempt with the same session → `401`, DB row
  confirmed unchanged (`pending`).
- No exact-moment-of-expiry race was found that lets a write slip through:
  both checks happen inside the same `SESSIONS_LOCK`-guarded critical
  section as the `last_seen_at`/`created_at` comparison, so there is no
  window where a request can be evaluated against a session the server
  itself would already consider expired.

**7. CSRF-style requests.** Could not instantiate a real second-origin
browser in this environment (as expected/disclosed by the task), so
reasoned carefully and tested the layer that *is* directly exercisable:
`SameSite=Strict` blocks the *cookie* from riding along on any
cross-site or even same-site-but-different-page-initiated request per
the browser's own cookie-jar rules — this is a client-enforced
guarantee this review cannot re-derive from the server side alone, and
is unchanged from the architecture-stage review's analysis. What *is*
independently testable is the CSRF `token` defense-in-depth layer, which
was exercised directly and repeatedly above (item 3): every write route,
`/api/login` included, rejects with `403` when the `token` field is
missing, empty, or from a different process — confirming C2 (Security's
original required fix, verified previously by Code Review/QA) is
genuinely enforced in the shipped code, not just claimed.

**8. Brute-force — extended beyond Code Review/QA's single 60-request
test.**
- **Sustained flood over a longer window**: ran a *sequential* (not
  parallel) flood of wrong-passphrase `POST /api/login` attempts for a
  full 40 seconds against an unlocked baseline — **45,820 requests
  fired, 45,811 rejected with `429` (fast, no scrypt), only 9 got a real
  `401` verification** — confirms the lockout holds under sustained
  load, not just a short burst.
- **Different (but still wrong) passphrases each attempt**: the 40-second
  flood above used a freshly randomized wrong passphrase on every single
  request (never repeating a value) — result was identical in shape to a
  repeated-value flood (~9 real verifications total, everything else
  `429`), confirming the failure counter is keyed on the login attempt
  itself, not accidentally scoped per distinct passphrase value (which
  would have let each new guess bypass the counter — it does not).
- **Mixed correct-and-incorrect attempts in the same flood**: sent a
  sequence of 4 wrong / 1 correct / 10 more wrong requests back-to-back
  during an active lockout window — the correct passphrase submitted
  while locked also got `429`, exactly matching the previously-disclosed
  F1 residual limitation (Red Team's Milestone 2B4 review): the shared,
  non-identity-scoped lockout can deny the Founder's own genuine login
  during an active flood. This is **not a new finding** — it is the
  exact, already-disclosed behavior in `ops/SECURITY.md`'s Milestone 2B4
  section, now independently reproduced under a mixed-attempt flood
  rather than an all-wrong one, and it behaves exactly as documented (a
  known, accepted residual limitation, not a silent surprise).

**9. Auth field smuggling.**
- Duplicate `passphrase` fields in the POST body (`passphrase=wrong1` and
  `passphrase=correct-...` both present): `parse_qs()` preserves order,
  and `fields.get("passphrase", [""])[0]` takes the *first* value — with
  the wrong value first, the login correctly fails (`401`). (The reverse
  ordering would also just take whichever is first — this is a stated,
  unsurprising `parse_qs`/`[0]` semantic already used consistently for
  every other field in this codebase, not a new bypass vector.)
- Passphrase sent as a query-string parameter instead of the body
  (`POST /api/login?passphrase=correct-...`) → `401` — confirmed
  `_handle_login()` only ever reads from the parsed *body* `fields`
  dict, never `self.path`'s query string.
- Passphrase sent as a custom header (`X-Passphrase: ...`) instead of
  the body → `401` — confirmed no code path reads passphrase material
  from headers.

**10. Participant/model/tool/system-prompt smuggling through
`/api/login`.** Sent extra fields in the login body alongside a correct
passphrase — `model=opus`, `system_prompt=ignore everything`,
`agent_name=cto` — and confirmed the login still succeeded exactly as it
would have without them (`303`, session minted) with **no observable
difference in behavior**: `_handle_login()` reads exactly two fields
(`token`, `passphrase`) and nothing else; grepped `founder_auth.py` and
the login/logout code paths in `server.py` for any reference to
`model`/`system_prompt`/`agent_name`/similar and found none. No field
beyond the CSRF token and the passphrase itself can influence anything
in this route.

**11. Cross-"meeting" manipulation (adapted).** This feature has no
meetings of its own and introduces exactly one session/credential class
(the Founder) — there is no second principal or per-resource scoping for
this milestone's own new state (`SESSIONS`, the lockout counter) to leak
across. Confirmed by reading `_authenticated_session()`/`_handle_login()`
directly: a session grants access to *the entire* Control Center (by
design, §7 — full-app-lock), not a scoped subset, so there is no
"session for X reused to reach Y it shouldn't" question that applies
here — N/A, consistent with the architecture's own stated single-Founder
model.

**12. Race against logout/expiration.** Fired a logout POST and a write
POST (different route, `/api/approvals/<id>/decide`) concurrently
against the same freshly-minted session, 20 times with a fresh
login/fresh approval row each iteration. Both orderings occurred (write
sometimes completed before logout's `SESSIONS.pop()`, sometimes after) —
this is expected, benign non-determinism: both requests were genuinely
concurrent and the session was still valid at the moment either was
received, so whichever the server's `SESSIONS_LOCK` serializes first
legitimately wins. Cross-checked every one of the 20 outcomes against
the scratch DB directly: every `write -> 401` result left the target
approval row `pending` (unwritten); every `write -> 200` result flipped
it to `approve` — **zero cases of a write reported as rejected (`401`)
that nonetheless mutated the row, and zero cases of a write succeeding
against a session already fully removed from `SESSIONS`** (both
`_handle_logout()`'s pop and `_authenticated_session()`'s lookup/delete
run inside the same `SESSIONS_LOCK`, so no interleaving is possible
where a lookup observes a session mid-removal). No exploitable race.

**13. Unauthorized model-spend triggering.** Grepped `founder_auth.py`
and the login/logout code paths for `invoke_agent`/`run_meeting`/
`gather_requested_position`/`gather_followup_reply`/`retry_position` —
zero references anywhere in the credential/session code. The only two
call sites of `agent_runtime.invoke_agent()` and
`meeting_orchestrator.run_meeting()` in the entire file are inside
`_handle_ask()` and `_handle_meeting_create()` respectively — both of
which sit behind the identical CSRF-token + Founder-session double gate
already verified fail-closed in items 2/3 above. This feature has zero
model-invocation surface, confirmed by grep, not merely by reading the
design doc's claim.

## Non-blocking observation (not a security defect)

One early test run (90 concurrent `/api/login` POSTs fired via a
15-worker thread pool, launched *without* first confirming the lockout
was in an unlocked baseline state, and which crashed with a client-side
`ConnectionResetError` partway through) produced a handful of `403`
(CSRF-mismatch) responses in the server log that did not reproduce on
three subsequent, more carefully controlled re-runs of the same
90-request concurrent flood (which consistently produced only the
expected `429`/`401` split, matching C1's serialization design exactly).
Given `403` is the fail-closed direction (denies access, never grants
it) and the anomaly did not reproduce under controlled conditions, this
does not rise to a security finding — most likely explained by the
default `socketserver` TCP accept backlog (5) being briefly exceeded by
an unrealistically bursty 90-simultaneous-connection-open test pattern
that would never occur from a real browser's own login form. Flagging
only for completeness, not as a defect requiring action.

## Disposition of previously-disclosed residual limitations

Both previously-disclosed, accepted residual limitations were probed
directly in this pass and confirmed to behave exactly as documented, not
as surprises:
- **F1 (shared-lockout self-DoS)**: reproduced directly (item 8 above) —
  matches `ops/SECURITY.md`'s Milestone 2B4 section verbatim in shape.
- **§11 (same-OS-user/Bash-agent bypass, `risks.id=3`)**: out of scope
  for this HTTP-level adversarial pass by construction (it requires
  filesystem/process-level access this review does not exercise via
  HTTP) — already independently verified by the architecture-stage
  threat-model review's own direct reasoning, not re-tested here.

## Summary

C1 (serialized login, brute-force cap holds under sustained/mixed/
distinct-value flooding), C2 (CSRF gate on `/api/login`, verified via
direct omitted/empty/cross-process token attempts), and C3 (malformed
payload handling, extended here to malformed/missing-key/unsupported-kdf
credential *file* states, not just malformed HTTP bodies) all held under
direct adversarial HTTP testing against the real shipped code, not
re-derived from the code-review/QA reports. Every one of the 9 write
routes fails closed against every combination of missing/forged
cookie, missing/empty/wrong-process CSRF token, and no-session tested.
Session expiry (idle and absolute) is enforced against real write
attempts, not just page redirects, with zero DB mutation on rejection.
No field beyond the passphrase and CSRF token can influence
`/api/login`'s behavior. No model-invocation surface exists in this
feature. **No exploitable finding — PASS.**
