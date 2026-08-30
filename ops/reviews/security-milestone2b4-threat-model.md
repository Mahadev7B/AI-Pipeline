# Security threat-model review — Phase 2, Milestone 2B4: Founder Identity Verification for Consequential Write Actions

Reviewing `ops/reviews/cto-milestone2b4-architecture.md` (architecture-
proposal stage, pre-implementation, per that document's own framing:
"Do not implement — this is the proposal Security and Red Team review
before Development builds it"). Performed directly (no subagent-dispatch
tool present this session, same disclosure as every review since
Milestone 2B3A).

**Process note before the verdict**: no task row exists yet in
`tasks` for Milestone 2B4 (`python3 ops/db/opsdb.py query "SELECT id,title
FROM tasks WHERE id>12"` returns no rows). Every prior milestone's
architecture-stage review was logged against an already-created task id
(e.g. the 2B1 architecture commit is tagged `TASK-006`, and `task_id=6`
carries two separate `review_type='security'` rows in `review_results` —
one for the proposal, one post-implementation). `review_results.task_id`
is a `NOT NULL` FK, so this verdict cannot be persisted via `opsdb.py
review-result` until a task exists. **Action item for whoever owns task
creation: create the Milestone 2B4 task before this verdict can be
recorded in the DB.** This review stands as the authoritative written
verdict in the interim; the CLI call must be re-run once a task id exists.

## Verdict: REJECT / CONDITIONS

The overall design is sound and correctly scoped — the single passphrase
+ scrypt + session-cookie approach is the right "smallest appropriate"
mechanism, the credential-file handling is genuinely careful (atomic
0600 creation, no DB touch, no log/HTML leakage), and §11's central claim
is correct (see below, independently re-derived and, if anything,
understated). But two concrete, exploitable gaps in the design as
specified must be closed before Development builds it — both bear
directly on required threat-list items (16, 22, and 3/4/21) — so this is
not a clean PASS.

### Required changes (block Development start)

**C1 — Concurrent-login race defeats the stated brute-force cap and opens
a memory-exhaustion DoS.** §8's pseudocode is check-then-act
(`if locked: reject` / else `verify` / `on failure: increment, maybe
lock`) and §10 explicitly says the locks are "held only for a dict
get/set," not across the scrypt call itself — meaning the ~1s, ~128 MiB
`hashlib.scrypt` verification runs *outside* the lock. Concretely: N
simultaneous `/api/login` requests can each observe `_locked_until` in
the past before any of them increments `_failed_count`, so each proceeds
to run scrypt independently. `ThreadingHTTPServer` has no cap on
concurrent connections to this route (unlike agent invocations, which are
`BoundedSemaphore`-capped at 3) — nothing stops an attacker opening, say,
50–100 simultaneous connections, each triggering a real ~128 MiB scrypt
computation before the lockout timestamp catches up to reject *new*
arrivals. This breaks the "≈1 attempt/7s sustained" cost math §8 relies
on as its sufficiency argument (item 16), and 50–100 concurrent 128 MiB
allocations is a real memory-pressure DoS against the server process
itself (item 22 — this is exactly what "concurrent authentication
attempts" as a named threat is warning about). **Fix**: hold `_LOGIN_LOCK`
across the *entire* check→verify→increment critical section (serializing
login attempts), which for a solo Founder's actual login frequency costs
nothing and closes both problems at once — or, if serializing scrypt is
rejected for some reason, add an explicit `BoundedSemaphore` capping
in-flight `/api/login` requests (e.g. 1–2), matching the
`MAX_CONCURRENT_INVOCATIONS` pattern already established in this
codebase for exactly this class of problem.

**C2 — `/api/login`'s CSRF-token requirement is unstated, and matters
here specifically.** §4 explicitly says `/api/logout` "is protected by
the same CSRF `SESSION_TOKEN` field every other POST route already
requires," but never says whether `/api/login` requires it too. This is
not cosmetic: if `/api/login` does *not* require `SESSION_TOKEN`, a
remote attacker page the Founder merely has open in another tab can
auto-submit a blind cross-origin POST of guessed passphrases directly to
`127.0.0.1:8420/api/login` (`SameSite=Strict` blocks the *cookie* from
riding along, but does not block the POST from being sent at all — this
is the classic "attacker page targets localhost" pattern this project's
own loopback threat model already reasons about elsewhere). If
`/api/login` *does* require `SESSION_TOKEN`, this is closed outright,
because an external origin can never learn the current process's token
value (it would have to first fetch `/login`'s rendered HTML, and
cross-origin `fetch`/`no-cors` cannot expose that value back to attacker
JS). **Fix**: require `/api/login` to carry the same `token` field as
every other write route, and say so explicitly in the design doc (this
also cleanly answers threat items 3 and 4 for the one route that
currently reads as ambiguous).

**C3 — Malformed-payload handling on `/api/login` is unstated.** The
document doesn't say what happens on a missing `passphrase` field, an
oversized body, or non-UTF-8 bytes. The existing `do_POST()` pattern
(`MAX_BODY_BYTES` cap before parsing, `.decode("utf-8", errors="replace")`,
`fields.get(name, [""])[0]` defaulting missing fields to `""`) already
handles all three safely and should obviously extend to `/api/login` —
but the design doc should say so explicitly rather than leaving it
implicit, since this is the one new route reachable by an unauthenticated
caller by construction (that's the whole point of a login route) and
therefore the one route where "what does a hostile body do" most needs a
stated answer, not an inferred one. Verify an empty-string passphrase
fed into `hashlib.scrypt(b"", ...)` doesn't raise (it doesn't — scrypt
accepts a zero-length password), so this fails safe today, but Development
should confirm this explicitly and add a test.

None of C1–C3 require new infrastructure or touch `risks.id=3` — all
three are within the milestone's own stated constraints and are
straightforward fixes to the design as written.

### Non-blocking recommendations (do not gate sign-off)

- **12-character minimum passphrase**: adequate for the *in-scope* online
  brute-force threat (scrypt `N=2**17` cost + the fixed lockout, once C1
  is fixed, makes online guessing infeasible regardless of the exact
  floor). The only scenario where the floor matters more is offline
  cracking of an exfiltrated credential file — but that exfiltration path
  is exactly the co-resident-OS-user scenario §11 already discloses as
  out of scope (an attacker with `id=3`-class access already has
  everything, not just the hash). Recommend bumping to 16 as cheap
  defense-in-depth (scrypt's memory-hardness resists but does not fully
  defeat GPU/large-VRAM parallel cracking), but this is not a blocking
  finding given where the real exposure boundary actually sits.
- **Idle timeout UX/data-loss edge case**: this app has no client-side JS
  and no page auto-refresh (confirmed — grepped for `setInterval`/`fetch`/
  meta-refresh across `ops/control-center`, none found), so a Founder
  silently reading a long meeting thread for >30 minutes then composing a
  follow-up will hit the idle timeout and, on submitting a plain HTML
  form, get redirected to `/login` with the typed message lost (no
  draft-preservation mechanism). Not a security defect, but flag to
  Development as a real usability edge case worth a graceful answer
  (e.g., re-render the form pre-filled after re-auth) — the alternative
  failure mode is the Founder picking an unreasonably long idle window to
  route around the friction, which would be a security regression.
- Gitignore-ordering reminder: land the `.founder_credential*` entry in
  the same commit that introduces `founder_auth.py`, before `setup` is
  ever run for real, so there's no window where `git add -A` could pick
  up a real credential file. Also confirm any sibling temp file used for
  atomic `change` writes is itself dot-prefixed with the same
  `.founder_credential` stem, so it falls under the same glob (the doc
  doesn't specify the temp filename).

## Independent verification of specific claims (not taken on the CTO doc's word)

**DB write path — confirmed clean.** Reread every write-path description
in §3 (JSON file, `os.O_EXCL`/`os.replace`) and §4 (in-memory `SESSIONS`
dict) top to bottom: there is no `opsdb.*` call anywhere in the proposed
credential or session mechanism. `operations.sqlite3` is git-tracked
(confirmed: `git ls-files | grep operations.sqlite3` finds it) — the
credential/hash/salt/session-id never touching it is correctly load-
bearing, and the design as written keeps it that way. Addressed.

**`.gitignore` pattern — confirmed it matches.** Proposed entry
`ops/control-center/.founder_credential*` against the proposed real
filename `ops/control-center/.founder_credential.json`: a trailing `*`
glob matches any suffix including `.json`, so this is a straightforward
match — verified by direct pattern inspection, not assumed. (See temp-
file caveat above.) Addressed.

**§11's central claim — independently re-derived, and actually
understated, not just conceded.** Tried to find a cheaper mitigation
within stdlib/no-new-infra before agreeing with the CTO doc:
- File-permission tricks don't help — 0600 restricts *other OS users*,
  not the owning user's other processes, which is exactly the attacker
  class in question.
- A CLI-level gate on `founder_auth.py` (e.g. a TTY check to make
  scripted invocation harder) is theater against this attacker: a
  Bash-capable agent doesn't need to invoke `founder_auth.py` at all — it
  can write the JSON credential file directly with a one-line `python3 -c`
  call (`json.dump({...}, open(path, "w")); os.chmod(path, 0o600)`),
  bypassing any CLI-surface protection entirely, since the CLI is not a
  privilege boundary, just a script owned by the same user.
- Going further than the CTO doc did: on a default Linux configuration
  (classic ptrace permissions, `yama.ptrace_scope=0`, which is the
  default on most non-hardened distros), a same-UID process can
  `PTRACE_ATTACH` to the running `server.py` process and read its memory
  directly — including the live `SESSIONS` dict and `SESSION_TOKEN`,
  without ever touching the credential file at all. This means the
  credential-file argument in §11 is actually the *weaker* of two
  independent same-UID bypasses available to a Bash-capable co-resident
  agent; live process memory access is a second, arguably easier one, not
  mentioned in the CTO doc. This strengthens rather than weakens §11's
  conclusion: there is no cheaper in-scope mitigation, and the true
  boundary really is the OS-process/UID boundary that only `risks.id=3`
  (or genuinely new infrastructure — separate OS account, hardware key,
  OS keychain with per-process grants) can close. **Concur with §11,
  independently verified, not merely accepted.**

**Session fixation — traced, confirmed not present.** §4: on successful
`/api/login` the server always calls `secrets.token_urlsafe(32)` fresh
and stores it as a new `SESSIONS` key, delivered only via a
server-set `Set-Cookie` response header. Nothing in the design reads an
inbound `fc_session` cookie value and reuses it as the new session id on
login — a pre-set attacker-chosen cookie value is simply overwritten by
the server's own `Set-Cookie` on successful auth. `token_urlsafe(32)` is
256 bits of CSPRNG output, not guessable. Addressed.

**Scrypt parameters — defensible.** `N=2**17, r=8, p=1` matches OWASP's
current stated general-purpose recommendation exactly, not a
memory-constrained fallback; the measured ~0.98s/hash cost is consistent
with that parameter choice and appropriate for a rarely-invoked login
path. No objection.

**Full-app-lock (open question 3) — concur with gating GET routes too.**
The Founder's own threat item 1 ("another local user/process reaches the
Control Center") is a *reading* threat, not just a writing one, and the
GET-served content (inbox recommendations, meeting positions/financial
reasoning, decision log) is exactly the operational record that
shouldn't be readable by an unauthenticated local viewer. Gating reads
costs a solo Founder one unlock per 30-minute-idle/12-hour-absolute
window — negligible. Concur with §7's decision as written.

**Brute-force flat lockout (open question 6) — sufficient, once C1 is
fixed.** No per-IP limiting is correctly dismissed as theater
(loopback-only, single source address). Flat 5/30s vs. exponential
backoff: given the scrypt cost and 12-char floor, the combined-cost math
in §8 is sound *once serialized* — exponential backoff would add
complexity without meaningfully changing the practical guessing timeline
for a 12+ character passphrase. Concur with the flat design, contingent
on C1.

## Draft `risks.id=2` language

Concur substantively with the CTO's §11 draft. Endorsing it with one
addition — noting the conditions above must ship before this status
change is applied (this milestone gets the same two-pass treatment as
every prior one: an architecture-stage review now, a post-implementation
Security pass before `risk-resolve` actually runs):

> **Title** (unchanged): Founder approval is not identity-authenticated
> **Status**: `mitigated` (not `resolved`) — **apply only after
> Development ships C1–C3 above and Security completes a
> post-implementation pass**, not directly off this architecture review.
> **Description**: "Founder-facing actions — all 7 write routes, the new
> `/api/login`/`/api/logout` routes, and every GET read — require a
> locally authenticated Founder session: a passphrase known only to the
> Founder, verified via a salted `scrypt` hash (`N=2**17, r=8, p=1`)
> stored outside git (0600, owner-only, never touching
> `operations.sqlite3`, logs, or generated HTML), gated by a
> server-side session cookie (`HttpOnly`, `SameSite=Strict`, 30-minute
> idle / 12-hour absolute timeout, in-memory only, wiped on restart),
> rate-limited against brute force (serialized verification — see
> Security's Milestone 2B4 threat-model review for why this must be
> serialized, not just counter-checked). This closes the gap for any
> local actor that does not already share the Founder's own OS-user
> filesystem/process principal — a real, previously-open gap. It does
> **not** close the case where an agent runs with Bash tool access under
> the Founder's own OS user (risk `id=3`): such an agent can read or
> overwrite the credential file directly, or attach to the running server
> process and read session state directly, exactly as it could already
> read a served page's CSRF token before this milestone. Closing that
> requires resolving risk `id=3` first, or a different class of
> infrastructure this milestone's scope deliberately excludes. See
> `ops/reviews/cto-milestone2b4-architecture.md` and
> `ops/reviews/security-milestone2b4-threat-model.md`."

## Required-threat-list disposition (all 24, none skipped)

1. Another local user/process reaches the Control Center — **Addressed**: full-app-lock (§7) + loopback bind; every route but `/login`/setup-required requires a valid Founder session.
2. Someone copies the `fc_session` cookie or `SESSION_TOKEN` CSRF value — **Mitigated** for the in-scope class (XSS/JS exfiltration blocked by `HttpOnly`; cross-site theft blocked by `SameSite=Strict`); **accepted-out-of-scope** for the co-resident-OS-user class (`id=3`), per §11.
3. Forged POST requests — **Addressed** for the 7 existing routes (dual CSRF+session gate, unchanged pattern extended); **needs explicit statement** for `/api/login` — see C2.
4. CSRF-style requests — **Addressed** via `SameSite=Strict` + CSRF token; same C2 caveat on `/api/login` specifically.
5. Replay of stale requests — **Addressed**: per-process `SESSION_TOKEN` regeneration + independent session-timeout, unchanged mechanism from 2B1, correctly retained.
6. Stolen session material — **Mitigated**/accepted-out-of-scope, same disposition as item 2.
7. Unauthorized approval — **Addressed**: `/api/approvals/<id>/decide` gated by both checks.
8. Unauthorized Founder decision — **Addressed**: `/api/meetings/<id>/decide` gated.
9. Unauthorized Ask-Agent invocation — **Addressed**: `/api/agents/<name>/ask` gated.
10. Unauthorized Executive Meeting creation — **Addressed**: `POST /api/meetings` gated.
11. Unauthorized request-perspective — **Addressed**: gated, same pattern.
12. Unauthorized follow-up — **Addressed** for *who* can reach the route; the pre-existing unbounded-rounds $ exposure (SECURITY.md, 2B3B round 2) is unchanged in shape, correctly disclosed as such, not silently fixed.
13. Unauthorized retry — **Addressed**: gated, bounded by `MAX_RETRIES_PER_PARTICIPANT`, unchanged.
14. Server restart — **Addressed by design**: sessions wiped, forces re-auth; correct conservative failure mode, not an oversight.
15. Stale browser tabs — **Addressed**: every request lazily re-validates against `SESSIONS`, not client-cached state.
16. Credential brute force — **Not yet addressed as specified** — see C1 (concurrency race undermines the stated attempt cap).
17. Credential leakage into logs — **Addressed**, verified: §9's log lines never include passphrase/hash/salt/session id/token.
18. Credential leakage into SQLite — **Addressed**, independently verified: no `opsdb.*` call anywhere in the credential/session design.
19. Credential leakage into generated HTML — **Addressed**, verified: passphrase never echoed; session cookie delivered only via `Set-Cookie` header, never embedded in page body (unlike the CSRF token, which is by design).
20. Credential leakage into Git — **Addressed**, verified pattern match; contingent on gitignore entry landing before first real `setup` run (see recommendation).
21. Malformed authentication payloads — **Under-specified** — see C3.
22. Concurrent authentication attempts — **Not yet addressed as specified** — see C1 (race + memory-exhaustion DoS risk).
23. Session fixation — **Addressed**, traced and confirmed: server never accepts a client-supplied session id, always mints fresh on login.
24. Logout/lock correctness — **Addressed**: `/api/logout` is idempotent, works from an already-expired session, correctly clears the cookie (`Max-Age=0`).

## Summary

Design direction: sound, correctly scoped, appropriately honest about its
own limits (§11). Three concrete fixes required before Development
starts (C1 concurrent-login race/DoS, C2 CSRF-gate `/api/login`, C3
state malformed-payload handling explicitly) — none require new
infrastructure or touch `risks.id=3`. Two non-blocking recommendations
(passphrase floor, idle-timeout UX). `risks.id=2` should move to
`mitigated` only after these ship and a post-implementation Security pass
confirms them, not off this architecture-stage review alone.
