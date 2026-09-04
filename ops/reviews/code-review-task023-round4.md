# Code Review round 4 — TASK-023 (risks.id=3 durable closure: OS-level Developer sandboxing, DEC-011)

Reviewer: code-review. Scope: `handoffs.id=16`, commit range `95e9523..64ec49f`
(7 files, +2192/-94). Baselines read in full: my own three prior reviews
(`code-review-task023.md` B1–B4, `code-review-task023-reverification.md`
R1–R3, `code-review-task023-round3.md` C1/C2 + 6 non-blocking),
`cto-task023-architecture.md` including both addenda, and — as the binding
instrument for this round — `red-team-task023-addendum2-review.md` §4
(clauses C1–C10, the spend ceiling, the request-path allowlist) plus
`red-team-task023-addendum-review.md` (verified property #5).

**Verdict: REJECT — returned to Developer (IN_DEVELOPMENT).**

This is by far the strongest submission this milestone has produced. C1
(`--verbose`) is genuinely fixed and I confirmed it against the **real**
binary through the **shipped** wrapper — the check three previous rounds
never made. The gateway is well-built: Red Team's own credential-theft
exploit fails against it in both shapes, with the attacker listener
recording **zero connections and zero bytes**, while the real CLI completes
a real streamed session through it. Every number in the handoff is accurate.
Full verification detail is in §"Verified — do not re-litigate" below.

It is nevertheless a REJECT, on two findings, both of which I reproduced
end-to-end from inside a real `bwrap --unshare-all` sandbox against the
shipped code with a fake credential. Both are *misses in the new gateway*,
not regressions, and both defeat a clause of the binding contract that
Development believes it implemented.

---

## Blocking findings

### D1. Header VALUES are never checked for bare CR/LF — request smuggling and credential-header injection onto the credentialed upstream connection (contract C5 + the mandated path allowlist)

`parse_request_head()` (`ops/control-center/egress_proxy.py:452-473`)
rejects every other smuggling primitive Red Team named — obs-fold
continuations, malformed header **names**, CL+TE, duplicate CL, non-decimal
CL, `Transfer-Encoding` on a request. It never validates the header
**value**. Because the head is split on `\r\n`, a **bare LF** (or a bare CR)
inside a value survives `value.strip()` and is then written verbatim into
the upstream request by `_build_upstream_head()` (line 1048,
`lines.append(f"{name}: {value}")`).

Reproduced live, from inside a real sandbox, through the shipped
`EgressProxy`, over real TLS, against an upstream that treats a bare LF as a
line terminator (which RFC 9112 §2.2 explicitly permits a recipient to do,
and many servers and proxies do):

```
client (in sandbox):  POST /v1/messages HTTP/1.1
                      X-Foo: junk\nGET /steal HTTP/1.1\nHost: evil
upstream parsed:      request_lines_parsed: ['POST /v1/messages HTTP/1.1',
                                             'GET /steal HTTP/1.1']

client (in sandbox):  POST /v1/messages HTTP/1.1
                      X-Foo: junk\nx-api-key: ATTACKER-CHOSEN
upstream parsed:      x_api_key_lines: ['x-api-key: ATTACKER-CHOSEN',
                                        'x-api-key: FAKE-REAL-CREDENTIAL-…']
```

Both returned `200` to the sandbox. The bytes the gateway put on the wire
are deterministic and can be seen without a server at all, by calling the
shipped `_build_upstream_head()` on the shipped `parse_request_head()`
output:

```
b'POST /v1/messages HTTP/1.1\r\nHost: localhost:18443\r\n
  X-Foo: junk\nx-api-key: ATTACKER-CHOSEN\r\n
  x-api-key: FAKE-REAL-CREDENTIAL\r\nContent-Length: 0\r\n
  Connection: keep-alive\r\n\r\n'
```

Why this is blocking, not cosmetic:

- **It bypasses the request-path allowlist**, which is not a nicety but one
  of Red Team's two "also required" items: *"the gateway attaches the
  operator's credential to any path the sandbox chooses … Implement a
  fail-closed, configurable request-path allowlist. A missing path must be a
  visible 403, not a silent widening."* `POST /steal` is correctly 403'd
  through the front door (I verified that) and then walks in through this
  one, on the same TLS connection, after the real credential has been
  attached.
- **It is exactly the class C5 exists to close.** C5's own words are
  "framing ambiguity fails closed … never 'best effort'". A bare LF in a
  field-value *is* framing ambiguity, and CR, LF and NUL are all outside the
  field-value octets RFC 9110 §5.5 permits. The gateway is emitting a
  malformed request built from untrusted input.
- **The correct check already exists elsewhere in this same file.**
  `GatewayConfig.load()` line 639 does `if not isinstance(prefix, str) or
  "\r" in prefix or "\n" in prefix: raise ValueError(…header-safe…)` for
  `credential_prefix`. The trusted-side, operator-written string is
  validated for header safety; the untrusted, sandbox-supplied one is not.

Fix shape (Development's call, but it is small): in the header loop of
`parse_request_head()`, reject any value containing `\r`, `\n` or `\x00`
with a fail-closed `400`, the same way the name check already does. Add the
case to `test_egress_gateway.py`'s C5 battery in all three shapes (bare LF,
bare CR, NUL), asserting on the bytes `_build_upstream_head()` emits, not
just on the client-visible status — the status is `200` in both attacks
above, so a status-only assertion would not have caught this.

### D2. The required spend ceiling resets on every `fork()` — it bounds a cooperative client only, which is not the threat model

`_peer_session_key()` (line 808) keys the budget on the peer's
`SO_PEERCRED` `(pid, /proc start-time, uid)`. The docstring justifies this
as *"The peer is the in-sandbox `egress_relay.py` process — one per live
sandbox — so its (pid, start-time, uid) is a stable per-session identity for
as long as that sandbox runs."*

That premise does not hold under this milestone's own threat model. The
sandbox is assumed hostile; nothing obliges it to route through the relay,
and it may create arbitrarily many processes. Against a gateway configured
`max_requests_per_session: 5`, from inside a real sandbox:

```
same process, 12 requests   -> 429 × 12   (ceiling works against a cooperative client)
one fork() per request, 12  -> 200 × 12   (12/12 forwarded upstream, credentialed)
```

All twelve reached the configured upstream carrying the real (fake)
credential, every one of them after the parent's budget was logged
`gateway_budget_exceeded`. Three lines of attacker code inside the sandbox
restore unbounded spend.

Red Team moved this item from "named, not built" to **required** with a
specific justification: *"`--max-budget-usd` is enforced by the untrusted
side and is therefore worth nothing against the threat model this milestone
exists to address; a compromised session can currently spend the operator's
account without limit, and the gateway is the only place a limit can
exist … its job is to convert 'unbounded' into 'bounded and alarming'."* As
shipped, the gateway-side ceiling has the same defect as
`--max-budget-usd`: it binds only a client that chooses to be bound. The
control does not do the one job it was mandated to do.

`known_limitations` item 5 discloses the *lesser* degradations (the
`/proc`-unreadable fallback, the 256-entry table eviction) but not this one,
and the module docstring positively asserts the opposite. Given three rounds
of this milestone spent on making comments true, an untrue security-property
claim in the file's own contract restatement should not ship.

What I probed for a fix, so Development does not have to re-derive it:

- **Keying on the pid namespace does NOT work.** I checked: from inside the
  shipped bind set, `unshare --pid --fork` succeeds (`rc=0`, new
  `pid:[…]` inode), so a pid-ns-derived key is forgeable too.
- **Keying on the peer `uid` DOES work** and is a two-line change. The
  sandbox cannot alter the host uid `SO_PEERCRED` reports (it is root only
  inside its own user namespace). It is coarser — two concurrent sandboxes
  under `ai-developer` would share one budget — but that fails *closed*, and
  a shared ceiling that cannot be reset is worth more than a per-process one
  that can. Note the current `/proc`-unreadable fallback degrades in the
  wrong direction, to `(pid, uid)`, i.e. to the weaker key.
- **A trusted-side session identity is not the architecture change the
  docstring implies.** This codebase already passes exactly such a thing to
  the sandbox as data: `OPSDB_BROKER_TOKEN`, read from a `0640` file by
  `launch_developer_sandboxed.sh:105` and `--setenv`'d in. A per-session
  egress socket (one bind-mounted socket per sandbox, keyed by which
  listener accepted) is a second option with no new secret at all.

Whichever is chosen, the docstring and `known_limitations` must describe the
resulting property accurately. If CTO decides a per-account ceiling is the
right stopping point, that is a legitimate answer — but it has to be stated,
not asserted as something stronger.

---

## Verified — do not re-litigate on resubmission

Everything below I re-derived myself with throwaway processes, fake
credentials (`FAKE-REAL-CREDENTIAL-DO-NOT-USE-CR101`) and self-signed
throwaway certs. **No real credential material was read, copied, moved or
exposed, and no request left this host.**

**C1 — fixed destination. Red Team's exploit fails.** Attacker listener on
`127.0.0.1:18912` recording every connection and byte; gateway configured to
`localhost:18443`. From inside a real `bwrap --unshare-all` sandbox, over
the bind-mounted Unix socket: absolute-form with attacker authority
(`POST http://127.0.0.1:18912/v1/messages`), `http`- and `https`-scheme
variants, and origin-form with `Host: 127.0.0.1:18912`. **Attacker log: 0
bytes, 0 connections.** Every request reached `localhost:18443` with
`Host: localhost:18443`. `_normalise_request_target()` returns only a path
and `_gateway_dial(cfg)` has no parameter through which request data could
arrive — I read every call path as well as running it. Config-side too:
`gateway.upstream` refuses IP literals, bracketed IPv6, missing/zero/
out-of-range/whitespace ports and non-strings.

**Path allowlist — fail-closed, both request forms, in-sandbox.**
`POST /steal` (origin **and** absolute form), the EC2 metadata GET
(`/latest/meta-data/iam/security-credentials/`, both forms), an unknown
path, `/v1/messages/../steal`, the `%2f`-encoded and `;`-suffixed variants,
and `//127.0.0.1:18912/steal` — all `403`, all with a
`gateway_denied_path` log line, none reaching upstream. Exact-match
semantics on the pre-`?` path is the right primitive. Config-side it cannot
be emptied or widened: `[]`, a non-list, relative entries, entries with
whitespace or a `?`, and non-strings are all refused at load.

**Per-request injection over REAL SSE.** 3 requests on ONE client
connection, upstream answering with genuinely chunked `text/event-stream`
and no `Content-Length`: 3/3 `200`, 3/3 carried exactly one
`x-api-key: <real credential>`, **0 sentinel leaks**, all three on upstream
connection #1. Client-supplied `x-api-key` was replaced, not appended.

**With the real CLI, end-to-end.** Real `/opt/claude-code/bin/claude`
2.1.252, shipped `launch_developer_sandboxed.sh` run byte-identical under
real bwrap: **exit 0**, **3 NDJSON events**, `init` 1943 bytes with
`tools=['Read','Edit','Write','Bash','Grep','Glob','Skill']`, `developer`
present in `agents`, `apiKeySource=ANTHROPIC_API_KEY`, cwd = the worktree,
`result.subtype=success`, `is_error=False`, and the answer text came from my
throwaway upstream — so the whole gateway path was live. Two model POSTs,
bodies **4128** and **23683** bytes, both `swapped=True sentinel_seen=True`,
**0 sentinel leaks upstream**, 0 attacker bytes. `_stream_process_output`'s
raw byte pump handled the real NDJSON without truncation or interleaving.

**CONNECT reserve retained and actively denying.** In that same real-CLI
run: **5 × `CONNECT api.anthropic.com:443` → 403**, and the CLI completed
normally. Datadog telemetry CONNECT also 403 in the direct battery.

**The self-reported large-body bug, and the CONNECT ceiling it touched.** A
25,024-byte first request body arriving in the same read as its head is now
forwarded and credentialed (`200`). The looser gateway rule is still
bounded: `_SocketReader.read_header_block()` caps the *head block* at 16 KB
and the buffer cannot exceed ~16 KB + one 64 KB read. The CONNECT path's
stricter rule is **not** weakened — verified directly rather than inferred:
0 pipelined → `200`; 4 KB pipelined → `200` and **all 4096 bytes reached the
destination**; 50 KB pipelined → `400` with no dial; a 20 KB header block →
`400`.

**CL/TE fail-closed.** `400` for: CL+TE together, duplicate CL, `0x10`,
`+10`, TE-only, `Transfer-Encoding: identity`, obs-fold, `Host : h`,
oversized head, >200 headers, non-permitted methods, NUL in the target,
CONNECT arriving on the gateway path. `413` **before any body read** for
`Content-Length: 99999999999999999` and for 40 MB against a 32 MB ceiling.
(`Content-Length: 4 ` → accepted at 4 after `strip()`; that is
RFC-conformant OWS handling, not a defect.)

**C6 — no redirect following, no diagnostic leakage.** A 302 with
`Location: http://127.0.0.1:19999/pwn` was relayed to the sandbox verbatim
and never followed; no `/pwn` request appeared anywhere and the attacker
listener stayed silent. Every rejection is a bare status with
`Content-Length: 0`, no body.

**C7 — no cross-session upstream reuse.** 29 client connections produced
**29 distinct upstream TLS connections**; the 3 keep-alive requests shared
connection #1 and nothing else was shared. Upstreams are dialled lazily per
client connection and closed in `finally`.

**C8 — metadata-only logging.** Drove real and synthetic sessions, then
grepped the daemons' entire stderr: **0** occurrences of the credential
literal, **0** of the sentinel value, **0** of prompt or SSE body text.
`_log()`'s coercion is structural — non-scalars become `<type>`, strings are
truncated to 200 and CR/LF-escaped — so a future caller cannot hand it a
buffer.

**C9 — the guard is reconciled, not deleted.** `allow: []` + valid gateway
starts; `allow: []` with no gateway, with `gateway: null`, and with no
`allow` key at all each refuse with the intended message. Credential file:
missing, empty, whitespace-only, `0644`, `0640`, sentinel-valued,
multi-line, a directory, and owned by another uid — **all nine refuse to
start**.

**C10 — TLS.** I tried `verify`, `insecure`, `check_hostname`,
`verify_mode`, `tls_verify`, `ssl_verify` as config keys: none exists, all
ignored, `check_hostname=True` / `CERT_REQUIRED` every time. Untrusted cert
→ **`502`**, `gateway_upstream_error error=SSLCertVerificationError`, and
**0 requests reached the rogue upstream** — the credential is sent only
after a verified handshake. `main()` as root: `refusing_to_start`, exit 1,
no socket bound. `credential_header` is constrained to the two forms;
`credential_prefix` rejects embedded CR/LF; all three ceilings reject
non-positive, bool, float, string and `None`.

**All 6 round-3 non-blocking items are fixed, and I ran each one.**
(1) the read-error branch classifies correctly — `(False,'read_error')` with
no timeout, `(False,'timeout')` when the event is set, `(True,None)` on
clean EOF — and the caller now emits honest text for each; (2) the
`_read_header_block` docstring now says "up to the header ceiling" and
explains why the gateway's rule differs; (3) `agent_runtime._run_claude`
names why it may ignore the bool; (4) `_write_out` falls back cleanly on a
text-only `sys.stdout` (no `AttributeError`); (5) the `CLAUDE_BIN` guard
fires — a symlink out of the bound tree exits 1 with the intended message,
a real file inside it proceeds; (6) the runbook's Option B now has the
`ai-pipeline-broker` database/directory ownership steps including
`-wal`/`-shm` and the setgid bit, plus a verification command.

**Tests — my counts, not the handoff's.** 9 suites, **237 checks**, 0
failures: `test_opsdb_broker.py` 65, `test_egress_proxy.py` 13,
**`test_egress_gateway.py` 53**, `test_developer_pretooluse.py` 14,
`test_trust_flag_monitor.py` 8, `test_cost_tracking.py` 22,
`test_gates_remaining.py` 34, `test_phase_progress.py` 17,
`test_risk_register.py` 11. Exactly the handoff's claim. The 4 pre-existing
`ops/db/test_*.py` suites are unmodified and pass; `ops/db/operations.sqlite3`
is byte-identical before and after every run
(`7eb2c001d1fd995e20caa20e82e331f0`).

**No scope creep.** Exactly the 7 files in `files_changed`.
`launch_developer_session.py` remains referenced only from comments and
docs — Developer's default Task-tool invocation path is untouched.

**Hard constraint honored.** `id ai-developer` → no such user; no
`ai-pipeline-*` groups; `/etc/sudoers.d/` contains only `README`;
`/run/ai-pipeline` and `/etc/ai-pipeline` do not exist; no unit installed;
no daemon left running. All my rigs lived under the session scratchpad and
are removed; `git status` is clean.

---

## Non-blocking findings (fix alongside D1/D2)

- **`_reject()`'s docstring is now untrue.** It claims `detail` is "always a
  fixed metadata string chosen by this module, never client content", but
  `parse_request_head` raises `f"method not permitted: {method}"` and the
  CONNECT path passes `f"{host}:{port} is not in the egress allowlist"` —
  both client-controlled. The behaviour is safe (log-only, never in the
  response body, truncated to 200 and CR/LF-escaped by `_log`), so this is a
  comment fix, not a code fix. This milestone has twice made comment
  accuracy a review item; keep the standard.
- **An LF-only request head hangs instead of failing fast.** A request using
  bare-LF line endings never satisfies `read_header_block`'s CRLFCRLF search
  and holds a thread until the 30 s idle timeout with no `rejected` log
  line. Fail-closed and bounded, but a `400` would be cheaper and audible.
- **`session_requests` is read outside the budget lock** at the
  `gateway_request` log site, so two concurrent requests can both log the
  post-increment value (observed: two connections both logging
  `session_requests=2`). Cosmetic; the enforcement itself is correctly
  locked.
- **Unknown `gateway.*` config keys are silently ignored.** Safe today
  (there is no key to disable anything), but a typo in
  `max_requests_per_session` silently reverts to the 500 default. A
  strict-key check would make a mis-provisioned ceiling loud.
- **Duplicate identical `Content-Length` is rejected on requests
  (`len(...) > 1`) but accepted on responses (`len(set(...)) > 1`).** The
  asymmetry is in the safe direction and the upstream is the trusted end;
  worth a one-line comment saying so deliberately.
- **`test_egress_gateway.py` has no adversarial-client budget case.** Its
  ceiling tests all run from one process, which is why D2 survived. The
  regression test for D2 must fork.

---

## On the deliberately unexercised real-endpoint leg

`known_limitations` item 3 states plainly that no test in this pass touched
`api.anthropic.com`, and why. **That scoping is honest and I endorse it** —
it is the correct reading of the hard constraint, and CTO's and Red Team's
separate real-401 observations are cited as inherited evidence rather than
re-claimed. Item 2 (production auth-shape parity) and item 4 (the endpoint
set) are likewise accurately bounded.

For QA/DevOps rather than for this round, and **not** grounds for this
REJECT:

1. **One real-endpoint smoke test belongs to DevOps at cutover**, not here:
   with the real credential in the `0600` file, drive one
   `POST /v1/messages` through the gateway to the real host and confirm a
   real non-401 response and a real streamed SSE close. Everything in this
   round used a self-signed CA; the real chain, the real
   `Transfer-Encoding`/trailer behaviour and the real ambient proxy have
   never met this code.
2. **QA must enumerate the endpoint set from a real run.** My real-CLI
   session used only `POST /v1/messages?beta=true` (no `HEAD /api/hello`
   this time), which does not prove the set is complete for longer sessions
   with tool use, compaction or telemetry.
3. **D1's fix should be re-tested against a real endpoint**, since whether
   Anthropic's front end is bare-LF tolerant determines the severity there
   even though it does not change the correctness of the fix.

---

## What happens on resubmission

D1 is a few lines in `parse_request_head()` plus three test cases asserting
on emitted upstream bytes. D2 is a decision about the session key followed
by a few lines, a forking regression test, and honest text in both the
docstring and `known_limitations`. Ship them with the six non-blocking items
together. I will re-run the full battery above — including Red Team's
fixed-destination exploit, the real-CLI chain, the CONNECT ceiling probes
and all 9 suites — and will specifically re-test the two smuggling shapes
and the fork-per-request budget probe.

Nothing else in this diff needs to change. The gateway's architecture,
its fail-closed posture, its logging discipline and its config validation
are right, and I would expect a fourth round to be short.
