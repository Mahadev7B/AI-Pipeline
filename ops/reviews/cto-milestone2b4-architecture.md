# CTO architecture proposal — Phase 2, Milestone 2B4

TASK: Founder Identity Verification for Consequential Write Actions.
Scope: close risk `id=2` ("Founder approval is not identity-authenticated")
as far as it can honestly be closed within this milestone's constraints —
stdlib-only, no new cloud infra, no paid identity provider, loopback-only
solo-Founder deployment unchanged, `risks.id=3` (Bash tool scoping)
explicitly untouched. Do not implement — this is the proposal Security and
Red Team review before Development builds it.

## The core problem, precisely, verified against the code

`server.py`'s `do_POST()` (lines 251–292 as of this writing) funnels every
one of the 7 write routes through exactly one check, in exactly one
place, before any dispatch to a handler:

```python
token = fields.get("token", [""])[0]
if not secrets.compare_digest(token, SESSION_TOKEN):
    ... 403 ...
```

`SESSION_TOKEN` is `secrets.token_urlsafe(32)`, generated fresh in memory
on every process start, embedded as a hidden field in every rendered
form. I confirmed the 7 routes by reading both the regex dispatch table
(lines 133–141) and every `_handle_*` method: `/api/approvals/<id>/decide`,
`/api/agents/<name>/ask`, `POST /api/meetings` (create),
`/api/meetings/<id>/decide`, `/api/meetings/<id>/request-perspective`,
`/api/meetings/<id>/followup`, `/api/meetings/<id>/retry` — no others
exist; the module's own comment at line 247 says so and matches what I
found.

`ops/SECURITY.md` already states, in five separate places (2B1, 2B2,
2B3A, 2B3B round 2), the exact limit of what this token proves: *"the POST
came from a page this server process rendered, this run — not that a
human, specifically the Founder, sent it."* `risks.id=2` in the live
database still reads "Founder approval is not identity-authenticated,"
`status='open'`. That gap — not the CSRF/replay gap 2B1 already closed —
is this milestone's job.

`risks.id=3` — "Bash permissions cannot be scoped below the tool-category
level" — is explicitly out of scope. It matters anyway, unavoidably, for
one specific finding below (see "What this does and does not prove"):
I traced through what this design can and cannot defend against, and an
honest trace runs straight into `id=3`'s territory without this proposal
touching it.

## 1. What "Founder authentication" means here

A single passphrase, known only to the Founder. No username — there is
exactly one Founder, ever, in this system's data model (`ops/PROJECT.md`:
"Founder — the human. Sole holder of final authority"); a username field
would be pure decoration with no access-control value and one more thing
that could be wrong. "Passphrase," not "password," deliberately — the
UX and the length floor below (§2) both push toward a genuinely long,
low-reuse-risk secret rather than a short password reused from
somewhere else.

**Rejected: anything more elaborate.** No hardware key/WebAuthn (real
value, but a new dependency and a UX the Founder didn't ask for, for a
threat model that's "another local process on this machine," not
"a remote attacker who could phish a password"). No OS-keychain
integration (`keyring`-style libraries are third-party; this project's
hard convention, stated in `opsdb.py`'s own docstring, is stdlib-only).
No TOTP/2FA (a second factor defends against "attacker knows the
password but isn't physically at the keyboard" — irrelevant when the
single remaining physical keyboard access point already is decisive, see
§11). A passphrase, correctly hashed and rate-limited, is the smallest
mechanism that actually answers "does the entity submitting this request
know a secret only the Founder was ever told" — which is the entire
question this milestone needs answered.

## 2. Credential mechanism

`hashlib.scrypt` (stdlib, no dependency) — parameters `N=2**17` (131072),
`r=8`, `p=1`, `dklen=32`. This matches OWASP's current general-purpose
scrypt recommendation, not the memory-constrained fallback (`N=2**14`);
this machine isn't memory-constrained and login happens rarely (once per
session, not once per request — see §4), so the extra cost buys real
resistance to offline brute force at negligible UX cost. Measured
directly on this machine: **~0.98s** per hash at `N=2**17` vs. **~0.045s**
at `N=2**14` — the stronger parameter is a non-issue for a human logging
in once every 30 minutes, and meaningfully raises the cost of guessing if
the credential file is ever read by something that shouldn't have it (see
§11 for what "shouldn't have it" actually means in this deployment).
`hashlib.scrypt`'s memory ceiling defaults to 32 MiB; `N=2**17, r=8`
needs ≈128 MiB (`128 * N * r` bytes) — `maxmem=132*1024*1024` must be
passed explicitly or the call raises `ValueError`. Verified this
concretely (ran it, confirmed the default fails, confirmed the explicit
`maxmem` succeeds).

Salt: `secrets.token_bytes(16)` — fresh per credential, never reused,
stored alongside the hash (a salt is not a secret; its job is defeating
precomputed/rainbow-table attacks and ensuring two Founders on two
machines with the same passphrase would never produce the same stored
hash — moot here with exactly one Founder, but it's free and it's the
correct convention regardless).

Verification: derive `hashlib.scrypt(candidate_passphrase.encode(),
salt=stored_salt, n=stored_n, r=stored_r, p=stored_p, dklen=32,
maxmem=...)` and compare the **derived hash bytes** — never the raw
passphrase — against the stored hash via `secrets.compare_digest()`
(the same function, not a coincidence — `hmac.compare_digest` and
`secrets.compare_digest` are the same implementation; this codebase
already uses `secrets.compare_digest` for `SESSION_TOKEN`, so the new
check reuses the identical, already-reviewed primitive rather than
introducing a second one). Constant-time comparison here matters for the
comparison step itself, not the scrypt computation (scrypt's own timing
does not leak per-character information the way a naive
loop-until-mismatch string comparison would — that's exactly why hashing
before comparing is the correct order, not an incidental detail).

Minimum passphrase length enforced at set/change time: **12 characters**.
Not a full entropy estimator (dictionary-checking, zxcvbn-style scoring)
— that's real complexity this milestone doesn't need to build for a
single, cooperating user who has every incentive to pick something they
personally trust; a length floor plus telling the Founder to prefer a
multi-word passphrase over a short complex-looking one is the
"smallest appropriate" bar here, matching this project's own pattern of
picking one concrete, justified number over building a general-purpose
mechanism (`MAX_CONCURRENT_INVOCATIONS`, `MAX_RETRIES_PER_PARTICIPANT`,
etc.).

## 3. Secret bootstrap — new CLI tool, `ops/control-center/founder_auth.py`

**Two subcommands**, argparse-based, matching `opsdb.py`'s own CLI shape:

- `python3 ops/control-center/founder_auth.py setup` — first-time only.
  Refuses (prints a message, exits 1) if a credential file already
  exists, and says to use `change` instead — this is a safety rail
  against an accidental silent overwrite of the Founder's own passphrase,
  not a security boundary (see §11 for why it can't be one). Prompts
  twice via `getpass.getpass()` (entry + confirmation, must match),
  enforces the 12-character floor, then writes the credential file.
- `python3 ops/control-center/founder_auth.py change` — requires knowing
  the **current** passphrase first (prompted via `getpass.getpass()`,
  verified via the same scrypt+`compare_digest` check §2 describes)
  before accepting a new one. Again, a safety rail for the Founder's own
  workflow (catches "I fat-fingered `setup` again" or documents "I
  deliberately rotated this"), not a defense against a co-resident
  process — see §11.

**Why `getpass.getpass()`, not an environment variable**: an env var
passed inline on a command line lands in shell history and is visible to
any other process on this machine via `/proc/<pid>/environ` for the
lifetime of that process (the same "same-OS-user" exposure the whole
rest of this design has to reason about, made strictly worse by lingering
in `ps`/`/proc` output); a persistent `export` in a shell rc file is
worse still. `getpass.getpass()` reads from the controlling TTY with
echo off and the value never touches argv, environment, or history —
correctly the smaller exposure surface of the two, for the one thing in
this whole design that must never be persisted anywhere in cleartext
even briefly.

**Where it lives, and how it's written so it's never briefly
world-readable**: `ops/control-center/.founder_credential.json` — dot-
prefixed, outside git (see §12's `.gitignore` entry). `dbutil.py`'s
existing `write_output()` (`path.write_text(content); path.chmod(0o600)`)
is the established 0o600 convention in this codebase, but it has a real
TOCTOU gap for this specific use — a brief window between the file
existing (world/group-readable, whatever the process umask leaves it at)
and the `chmod` call landing. That gap is fine for a rendered HTML page;
it is not fine for a credential file. `founder_auth.py` instead:
  - `setup`: `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`
    — the file is created *at* mode 0600, atomically, and `O_EXCL` means
    the call itself fails if the file already exists (a second guard
    against the same race `setup`'s own already-exists check has a
    smaller window against).
  - `change`: write the new credential to a sibling temp file created the
    same restrictive way, then `os.replace(tmp_path, real_path)` — a
    single atomic filesystem rename on POSIX, so there is no observable
    intermediate state (never "old file deleted, new file not yet
    written," never a moment the file is world-readable).

**Content** (JSON, matching this codebase's existing preference for
small readable JSON files over a binary format):

```json
{
  "version": 1,
  "kdf": "scrypt",
  "n": 131072, "r": 8, "p": 1, "dklen": 32,
  "salt": "<base64>",
  "hash": "<base64>",
  "created_at": "2026-08-30T12:00:00Z"
}
```

Recording the KDF parameters *in* the file (not just as code constants)
means a future parameter increase doesn't invalidate every existing
credential — `founder_auth.py` always verifies using whatever parameters
are actually stored, and a future milestone could add "re-hash with
stronger parameters on next successful login" without a breaking schema
change. Not built now — noted so the format doesn't need to change later
to support it.

**Fail closed, not an insecure default**: `server.py` checks whether
`.founder_credential.json` exists on **every** request (a single `Path.exists()`
stat call — negligible cost, and it means running `founder_auth.py setup`
in a second terminal while the server is already running is picked up on
the very next request, no restart required). If it does not exist, every
route — GET and POST alike, including `/login` itself — returns **503**
with a fixed "Founder setup required: run `python3
ops/control-center/founder_auth.py setup`" message. There is no
"first request creates a default credential" fallback, no
`FOUNDER_PASSPHRASE=changeme` default anywhere in source — the server is
inert for every consequential and non-consequential route alike until
the Founder has deliberately run the setup command from their own
terminal.

## 4. Session mechanism

**On successful `/api/login`**: server generates `secrets.token_urlsafe(32)`
(same construction as `SESSION_TOKEN`, a separate value), stores it as a
key in an in-memory dict, `SESSIONS: dict[str, dict]`, holding
`created_at` and `last_seen_at` (both `time.monotonic()`, not wall-clock
— immune to a system clock change mid-session). Delivered via
`Set-Cookie: fc_session=<id>; HttpOnly; SameSite=Strict; Path=/` — no
`Secure` attribute, no `Max-Age`/`Expires`.

- **`HttpOnly`**: nothing server-rendered needs to read this cookie from
  JavaScript (this app renders no client-side script that touches
  cookies at all); `HttpOnly` costs nothing and removes any future
  accidental JS-readable exposure as a possibility, by construction.
- **`SameSite=Strict`**: this app has no legitimate cross-site
  interaction, ever — no external site should ever be able to cause a
  browser to submit this cookie. `Strict` (not `Lax`) also means even a
  same-site top-level navigation from an external referrer won't carry
  it, and — more relevant to this specific threat model — it blocks a
  request forged by *another local page open in the same browser*
  (e.g., something rendered by a different local tool, or a
  DNS-rebinding attempt against `127.0.0.1`) from riding along with this
  cookie, which is exactly the class of "another local process/page
  reaches the Control Center" scenario item 1 of the Founder's threat
  model names.
- **No `Secure`**: this traffic is plain HTTP over loopback, unchanged
  since 2B1's explicit, justified decision not to add TLS ("loopback-only
  traffic never leaves the machine's kernel, so there is no network
  attacker positioned to intercept it"). Setting `Secure` on an HTTP-only
  cookie means Chrome/Firefox simply never send it — that would silently
  break every login, not add protection against a threat (a network
  eavesdropper) that doesn't exist at this boundary. Consistent with the
  prior, already-reviewed TLS decision, not a new one.
- **No `Max-Age`/`Expires` (session cookie)**: the cookie disappears when
  the browser process itself closes. Combined with the idle/absolute
  timeouts below, this means nothing about "being logged in" survives
  closing the browser — matching this whole design's existing philosophy
  (`SESSION_TOKEN` itself already survives nothing but the current
  process's lifetime) applied consistently on the client side too, not
  just the server side.

**Idle timeout: 30 minutes** (`IDLE_TIMEOUT_S = 1800`) since
`last_seen_at`, checked lazily — every authenticated request bumps
`last_seen_at`; a request arriving after the gap treats the session as
gone (removed from `SESSIONS`, logged, see §9) and responds exactly like
"never logged in" (401 for POST, redirect-to-`/login` for GET).
**Absolute timeout: 12 hours** (`ABSOLUTE_TIMEOUT_S = 43200`) since
`created_at`, regardless of activity — bounds how long a session can ever
be silently reused even under continuous activity, so a browser left
open and actively polled by something for an entire day still forces
re-entry of the passphrase at least once a day. Both numbers are module
constants, not configurable from the browser, same convention as every
other bound in this codebase (`MAX_CONCURRENT_INVOCATIONS`,
`MAX_BUDGET_USD`, etc.) — Red Team should confirm or push back on the
specific numbers, not the mechanism.

**Explicit logout**: `POST /api/logout` — removes the session id from
`SESSIONS` (if present; idempotent if already logged out or already
expired — logging out twice is not an error) and responds with
`Set-Cookie: fc_session=; Max-Age=0` to clear it client-side, then
redirects to `/login`. Protected by the same CSRF `SESSION_TOKEN` field
every other POST route already requires (see §6) — it does **not**
require an already-valid Founder session first, since "I want to make
sure I'm logged out" must work even from a stale/expired session's own
still-open tab.

**Server restart wipes every session — deliberate, not an oversight.**
`SESSIONS` is a plain in-memory dict, exactly like `SESSION_TOKEN`
already is. Considered persisting it (a small local JSON file, refreshed
per login) and rejected: it would need the exact same "must never be
committed, must be 0600, must be readable only by this process" treatment
as the credential file itself — real additional surface — to protect
state (an active session id) that is genuinely fine to lose on restart,
because restarting `server.py` is *itself* a deliberate Founder action
(they typed the command), and re-entering a passphrase once immediately
after is trivial friction, not a workflow break. It's also the more
conservative failure mode: a stale session can never silently survive
past whatever the running process's code currently is — every restart
is an implicit "start every session over," never an implicit "trust
whatever was true before this code changed."

**Multiple tabs**: cookies are per-origin, not per-tab — every tab in
the same browser profile automatically shares one `SESSIONS` entry.
Nothing bespoke needed; this is ordinary browser cookie behavior.
**Stale tabs**: a tab loaded before an idle-timeout expiry or a logout
will hit the same lazy check on its next request (GET or POST) and get
routed to `/login` or a 401, same as any expired-session web app — no
separate mechanism needed, because every request (not just login)
re-validates against `SESSIONS`, not against something cached in the
page itself.

## 5. Centralized authorization boundary — reusing the exact existing location

`do_POST()`'s existing check (lines 264–277) is the one place in this
codebase every write route already funnels through. This design adds the
Founder-session check **immediately after** the existing CSRF token
check, in the same function, before any `_handle_*` dispatch — not a
second ad hoc check scattered into each handler:

```python
# existing, unchanged:
token = fields.get("token", [""])[0]
if not secrets.compare_digest(token, SESSION_TOKEN):
    ... 403 ...
    return

# new, same location, before any dispatch:
session = _authenticated_session(self)   # cookie lookup + expiry check + last_seen_at bump
if session is None:
    self._send_html(401, _error_page(401, "Sign-in required",
        'Your Founder session has expired or was never started. <a href="/login">Sign in</a>.'))
    return

# dispatch unchanged: _handle_decide / _handle_ask / _handle_meeting_* / ...
```

`do_GET()` gets a symmetric check at the top, before its existing
path-based if/elif chain, with a short unauthenticated allowlist
(`/login`, and the fixed setup-required page when no credential file
exists yet — §3, §7): every other path, absent a valid session, gets a
303 redirect to `/login` rather than any real content.

**Concretely traced through 2 of the 7 routes, to prove the ordering is
what it claims to be:**

- **`POST /api/approvals/<id>/decide`**: `do_POST()` matches the path →
  reads/parses the body → checks CSRF `token` (403 if wrong) → checks
  `_authenticated_session()` (401 if no/expired session) → **only then**
  calls `self._handle_decide(...)`, whose first and only DB-touching line
  is `opsdb.decide_approval(conn, approval_id, decision)`. No code path
  reaches `opsdb.decide_approval()` — the sole function permitted to
  write `approvals.decision` — without passing both checks first.
- **`POST /api/meetings/<id>/followup`** (the one SECURITY.md already
  flags as this system's largest single-route cost exposure, no round
  cap): same `do_POST()` gate, same two checks, same ordering, before
  `self._handle_meeting_followup(...)` is ever called — whose first
  DB-touching action is a read-only eligibility check, and whose first
  *write*/model-invoking action is
  `meeting_orchestrator.gather_followup_reply()`, which is what actually
  spends a real `$0.50`-capped invocation. The unbounded-rounds risk
  SECURITY.md already discloses for this route is **unchanged in shape**
  by this milestone — it's still true that a valid, authenticated
  Founder session can send unlimited follow-ups — but the population of
  requesters who can ever reach that unbounded surface at all is now
  gated by a real credential check that didn't exist before, for the
  reasons and with the limits stated in §11.

Every one of the other 5 routes (`ask`, meeting create, meeting decide,
request-perspective, retry) sits behind the identical two checks in the
identical order — verified by reading `do_POST()`'s single dispatch
block, not asserted.

## 6. Relationship to the existing `SESSION_TOKEN` — kept, not replaced

**Both checks apply to every write route, in the order shown above.**
They answer different questions and neither subsumes the other:

- `SESSION_TOKEN` (CSRF/anti-replay): "did this POST originate from a
  page *this exact server process* rendered, this run" — defends against
  a stale cached page, an old bookmark, or (even under `SameSite=Strict`,
  as defense in depth against a browser bug or a same-machine page that
  somehow bypassed `SameSite`) a request forged from elsewhere.
- The new Founder-session cookie: "is there currently an unlocked,
  unexpired Founder session at all" — defends against the thing
  `SESSION_TOKEN` was explicitly disclosed to never defend against
  (§11): anything that can merely read a rendered page.

Dropping `SESSION_TOKEN` now that the cookie exists would be a pure
regression — it's already implemented, already reviewed, costs nothing
to keep, and removing it would reopen exactly the stale-page-replay gap
2B1 closed for zero benefit. Keeping both is not redundant complexity;
each closes a distinct, real gap the other does not.

## 7. Read-only UX while locked — the whole Control Center requires unlock

**Decision: GET pages do NOT stay visible unauthenticated.** Every route
— read and write alike — requires a valid Founder session, except
`/login` itself (and the fixed "setup required" page, §3).

**Why, against the actual threat model**: the Founder's own brief names
"another local user/process reaches the Control Center" as threat item 1
— that is squarely a *reader*, not just a writer. The content behind GET
routes is not incidental: `inbox.html` shows Founder approval requests
with recommendation/alternatives/risk framing, `meetings.html`/
`meetings/<id>.html` show live executive positions and follow-up
conversations (which, per `EXECUTIVE_MEETINGS.md`'s framing, can include
financial and strategic reasoning), `decisions.html` shows the full
decision log. None of that is public-facing product content — it's the
Founder's own operational and decision-making record. Gating only writes
and leaving reads open would mean "another local user on a shared
machine" (explicitly named in the threat model) could read all of it
without ever needing to forge anything. There's no meaningful cost to
gating reads too: a solo Founder unlocks once per session (§4's
30-minute idle / 12-hour absolute window) and every page they'd ever
load is already behind that one unlock.

**What this does not change**: the git-committed static snapshots
(`inbox.html`, `meetings.html`, etc., written by each generator's own
`main()`) are unaffected — they were never served by `server.py` to begin
with, and access to them is already governed by ordinary OS file
permissions on the repository checkout itself (and `dbutil.write_output()`'s
existing `0o600`), not by anything this milestone changes. This decision
is specifically about the live HTTP server's GET routes.

## 8. Brute-force defense

One global, in-memory counter and lockout timestamp — not per-IP (every
request originates from `127.0.0.1`; an IP-keyed limiter would be
theater) and not per-credential-identity (there is exactly one Founder,
one credential, ever):

```python
_LOGIN_LOCK = threading.Lock()
_failed_count = 0
_locked_until = 0.0   # time.monotonic()
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
```

On `POST /api/login`: if `time.monotonic() < _locked_until`, reject
immediately (429, "too many attempts, try again in Ns") **without**
running `scrypt` at all — rejecting before paying the hash cost avoids
turning the lockout window itself into a free way to burn server CPU by
hammering it. Otherwise, verify; on failure increment `_failed_count`,
and once it reaches `MAX_FAILED_ATTEMPTS`, set `_locked_until = now +
LOCKOUT_SECONDS` and reset the counter; on success, reset the counter to
zero (a successful login always clears any partial failure streak).

**Combined cost, stated honestly**: `scrypt` at `N=2**17` already costs
≈1s/attempt; 5 attempts (≈5s) plus a 30s lockout caps sustained guessing
at roughly one attempt per 7 seconds — for a genuine 12+ character
passphrase (the enforced floor), that is not a remotely practical
brute-force timeline. For a weak but 12-character-minimum passphrase
it's a real, if smaller, deterrent — the honest limit here is the
Founder's own passphrase strength, which this design can enforce a floor
on but can't force to be strong; that limitation is disclosed here, not
hidden.

**Does not need to survive a restart, and doesn't** — in-memory only,
same reasoning as `SESSIONS` (§4): a restart is already a deliberate
Founder action, and by the time someone can restart this process they
already have a level of local access (§11) that makes a reset lockout
counter the least of what it grants them.

## 9. Auditability

Same convention as every existing log line in this file —
`sys.stderr.write(f"[control-center] ...\n")`, via the existing
`log_message` override — extended with these events, **never** logging
the passphrase, the derived hash, the salt, a session id, or the CSRF
`SESSION_TOKEN` value itself:

- Successful login: `"[control-center] {addr} founder login succeeded"`
- Failed attempt: `"[control-center] {addr} founder login FAILED
  ({_failed_count}/{MAX_FAILED_ATTEMPTS})"`
- Lockout triggered: `"[control-center] {addr} login lockout triggered —
  locked for {LOCKOUT_SECONDS}s"`
- Rejected attempt while locked: `"[control-center] {addr} login attempt
  rejected — currently locked"`
- Logout: `"[control-center] {addr} founder session ended (logout)"`
- Session expiry detected lazily on a later request (idle or absolute):
  `"[control-center] session expired (idle)"` /
  `"[control-center] session expired (absolute)"` — no session id in the
  line; the fact and the reason are the useful signal, the identifier
  itself is exactly the kind of bearer value that shouldn't appear in a
  log file at all.
- Denied protected action (valid route, no/expired session):
  `"[control-center] {addr} rejected {method} {path} — no authenticated
  Founder session"`
- Credential file created/changed while the server is already running
  (detected by comparing the file's mtime against a value cached at last
  successful login-attempt check): `"[control-center] WARNING: founder
  credential file was created or modified while this server is running
  — if you did not just run founder_auth.py, treat this as a real
  incident."` This does not prevent a same-OS-user actor from rewriting
  the credential (§11 explains why nothing at this layer can) — it makes
  that event loud and detectable in the one place the Founder is already
  looking (the terminal running `server.py`), rather than silent.

## 10. Concurrency

`SESSIONS` (a dict) and the lockout counter/timestamp (§8) are shared
mutable state reachable from multiple `ThreadingHTTPServer` worker
threads. Both are guarded by ordinary `threading.Lock`s around each brief
read-modify-write — the same category of primitive `agent_runtime.py`
already uses for its process-group registry (2B3A's shutdown-cleanup
mechanism), not a new pattern. This is explicitly **not** a third
competing concurrency system: it never touches SQLite (no interaction
with the existing `BEGIN IMMEDIATE` / atomic-`UPDATE` patterns) and never
touches `agent_runtime`'s `BoundedSemaphore` (no interaction with
`MAX_CONCURRENT_INVOCATIONS`). Login/logout/session-touch operations are
infrequent (once per session, not once per request) and each lock is
held only for a dict get/set — there is no scenario in this design where
a request thread blocks waiting on a model invocation while holding
either of these locks, so it cannot introduce the kind of contention
2B3A's `BEGIN IMMEDIATE` design was built to avoid.

## 11. What this security guarantee IS and is NOT — stated without softening

**What is now technically enforced that wasn't before**: a write to
`approvals.decision`/`agent_runs`/`messages` via any of the 7 POST
routes, and now every GET read too, requires possession of a passphrase
that is never servable, never embedded in any rendered page, and not
recoverable from anything an HTTP client can observe — verified via a
salted `scrypt` hash stored outside git, checked with a rate-limited,
constant-time comparison. This closes a real, previously-open gap for
**any local actor that does not already have filesystem read/write
access to this repository as the Founder's own OS user** — a different
local OS account, a more sandboxed local process, or a browser tab on
this machine that isn't part of the Founder's own tooling can no longer
turn "I can fetch `127.0.0.1:8420`" into a forged write merely by reading
a page, the way `ops/SECURITY.md` disclosed for every milestone through
2B3B round 2.

**What this does NOT close — traced through deliberately, not assumed**:
an agent invoked with Bash tool access, per the still-open `risks.id=3`,
runs as the **identical OS-user/filesystem principal** as the Founder in
this system's current invocation model. That agent can already read
`ops/control-center/.founder_credential.json` directly (0600 permissions
restrict *other OS users*, not the owning user's own other processes),
and — more directly — it can simply run `python3
ops/control-center/founder_auth.py change` (after reading the current
credential to answer its own "current passphrase" prompt, or, failing
that, deleting the credential file and running `setup` fresh, since
`setup`'s "already exists" refusal is a safety rail, not a permission
boundary against the file's own owner) and mint a session it knows the
passphrase to, exactly as it could already read a served page's
`SESSION_TOKEN` before this milestone. **This is not a regression** —
nothing that worked before stops working, and the class of attacker this
milestone does neutralize is real and was genuinely open before. But it
is not, and cannot structurally be, a defense against risk `id=3`'s
territory: no local credential file, however well-hashed, creates an
OS-level privilege boundary between two processes that already share the
same OS user. Closing that would require either touching `risks.id=3`
(explicitly out of scope this milestone) or introducing a genuinely
different kind of infrastructure (a separate OS account, an OS keychain
with per-process access grants, a hardware-backed secret) that this
milestone's own constraints (stdlib-only, no new infra, no elaborate
mechanism beyond what the threat model justifies) correctly rule out
adding speculatively. The one concrete thing this proposal *does* add
against that specific gap is detection, not prevention (§9's credential-
file-change warning) — narrowing "silent forgery" to "forgery the
Founder would see logged," not eliminating it.

**Draft updated `risks.id=2` language**, for Security to confirm, refine,
or push back on (current DB row via `python3 ops/db/opsdb.py query
"SELECT * FROM risks WHERE id=2"`; the actual update, when approved,
runs via `python3 ops/db/opsdb.py risk-resolve`, not a direct edit):

> **Title** (unchanged): Founder approval is not identity-authenticated
> **Proposed status**: `mitigated` (not `resolved` — see below for why)
> **Proposed description**: "Founder-facing actions — all 7 write routes
> and every GET read — now require a locally authenticated Founder
> session: a passphrase known only to the Founder, verified via a salted
> `scrypt` hash stored outside git (0600, owner-only), gated by a
> server-side session cookie (`HttpOnly`, `SameSite=Strict`, 30-minute
> idle / 12-hour absolute timeout, in-memory only, wiped on restart),
> rate-limited against brute force. This closes the gap for any local
> actor that does not already share the Founder's own OS-user filesystem
> access — a real, previously-open gap. It does **not** close the case
> where an agent runs with Bash tool access under the Founder's own OS
> user (risk `id=3`): such an agent can read or overwrite the credential
> file directly, exactly as it could already read a served page's CSRF
> token before this milestone. Closing that requires resolving risk
> `id=3` first, or a different class of infrastructure this milestone's
> scope deliberately excludes. See `ops/reviews/cto-milestone2b4-architecture.md`."

`mitigated` rather than `resolved` because a real, previously-open class
of attacker is now closed — this is not cosmetic relabeling — but the
risk's own title ("not identity-authenticated") is not fully false
anymore only for a subset of actors, not all of them; calling it
`resolved` would overclaim exactly what this section was written to not
do.

## 12. Files touched (for Development, after Security/Red Team sign-off)

- `ops/control-center/founder_auth.py` — **new**. Credential file
  load/verify (`scrypt` + `compare_digest`), `setup`/`change` CLI
  subcommands (argparse, `getpass.getpass()`), the JSON credential format
  and its atomic-write helpers (§3). No HTTP/session logic here — that
  stays in `server.py`, next to `SESSION_TOKEN`, matching the existing
  separation between `agent_runtime.py` (invocation mechanics) and
  `server.py` (HTTP dispatch, existing token).
- `ops/control-center/server.py` — `do_GET()`/`do_POST()` gain the
  centralized Founder-session check (§5); new `GET /login`,
  `POST /api/login`, `POST /api/logout` routes; `SESSIONS` dict +
  `threading.Lock`; lockout counter/timestamp + its lock (§8); cookie
  parse/set/clear helpers; the fail-closed "setup required" 503 path
  (§3); module docstring updated with the same disclosure discipline as
  every prior milestone (§11's language, condensed).
- `ops/control-center/layout.py` — `page()`/`nav_html()` need a way to
  render a "Log out" affordance (posts to `/api/logout` with the existing
  CSRF token field) in the Founder badge area, and a minimal locked/login
  page template distinct from the normal chrome (no nav links that lead
  to gated content). Exact placement is Development's call, not
  prescribed further here.
- `ops/control-center/generate_inbox.py`, `generate_meetings.py`,
  `generate_agents.py` — **no changes required for the write forms
  themselves.** The CSRF `token` hidden field stays exactly as-is; the
  new Founder-session check rides on the browser's automatic cookie,
  never a form field, so none of the existing token-threading through
  `build_html(conn, token=...)` needs to change shape. Worth stating
  explicitly since it's the main reason this design doesn't churn every
  generator file the way a form-field-based session token would have.
- `.gitignore` — add `ops/control-center/.founder_credential*` (wildcard,
  matching this file's existing "defense in depth in case one ever lands
  here by mistake" convention next to `ops/db/test*.sqlite3`).
- `ops/SECURITY.md` — new "Founder Identity Verification (Milestone
  2B4)" section, same disclosure format as every prior milestone's
  section: what's technically enforced, what still isn't, explicitly
  cross-referencing this document and §11's finding about `risks.id=3`.
- `ops/db/README.md` — no change required; this milestone does not touch
  the DB-write path, the `OPSDB_PATH` testing convention, or `opsdb.py`
  itself.
- `risks` table (`id=2`) — status/description update per §11's draft,
  applied via `opsdb.py risk-resolve` by whoever owns that step after
  Security's review, not by this document.

## Open questions for Red Team and Security

1. Is `scrypt` at `N=2**17, r=8, p=1` the right cost parameter, or should
   it be tuned differently given this machine's actual profile (Security
   may want to benchmark on the real deployment target, not just this
   environment)?
2. Is 30-minute idle / 12-hour absolute the right session lifetime, or
   does the Founder's actual usage pattern (long-running meetings,
   Ask-Agent threads) argue for a longer idle window specifically?
3. Is the full-app-lock decision (§7) the right call, or does Security
   weigh "a solo Founder's own convenience reading Overview at a glance"
   higher than the multi-local-user threat item 1 names? This was
   explicitly framed as CTO+Design's call per the Founder's brief — Red
   Team/Security should still pressure-test the reasoning, not just the
   number.
4. Is the credential-file-change warning (§9) worth building given it's
   explicitly disclosed as detection, not prevention — or is it not
   worth the code for what it actually buys?
5. §11's finding — that this milestone cannot, by construction, defend
   against an agent with Bash tool access because that agent shares the
   Founder's own OS-user filesystem principal — is the single most
   important claim in this document. Red Team should try to break it
   before accepting it: is there a cheaper, still-in-scope mechanism that
   narrows this further without touching `risks.id=3`, or is the
   detection-only fallback (§9) genuinely the best available answer
   here?
6. `MAX_FAILED_ATTEMPTS=5` / `LOCKOUT_SECONDS=30` — flat lockout, not
   exponential backoff. Red Team should confirm this is sufficient or
   request backoff given the combined cost math in §8 is the load-bearing
   argument for "sufficient."
