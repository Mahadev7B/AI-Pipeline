# Code Review round 5 — TASK-023 (risks.id=3 durable closure: OS-level Developer sandboxing, DEC-011)

Reviewer: code-review. Scope: `handoffs.id=17`, commit range `e2f17db..6cf0e9b`
(3 files, +754/-89). Binding instruments re-read: my own round-4 REJECT
(D1, D2, 6 non-blocking), `red-team-task023-addendum2-review.md` §4,
`cto-task023-architecture.md` addendum 2.

**Verdict: PASS — advanced to QA.**

Both round-4 blocking defects are genuinely fixed, and I re-derived each
one from inside a real `bwrap --unshare-all` sandbox against the shipped
code rather than reading the diff. Every number in the handoff is accurate.
The six non-blocking items are done. No regression in anything round 4
verified, including — the item I was most worried about — the real CLI's own
headers against the new, stricter validation.

All work below used fake credentials (`FAKE-CR105-CREDENTIAL-NOT-REAL-DO-NOT-USE`),
throwaway self-signed TLS servers and throwaway Unix sockets under the
session scratchpad. **No real credential material was read, copied, moved or
exposed, and no request left this host.** All rigs are torn down; no daemon
is left running; `git status` is clean and `ops/db/operations.sqlite3` is
byte-identical before and after every run (`88956699eed8a4d5662f4f8ef1609f34`).

---

## D1 — header-injection safety: FIXED, and the test can actually fail

**The factoring is the right one.** One primitive set, used everywhere a
string becomes part of a header line, rather than the duplicated check I
suggested: `breaks_header_framing()` (CR/LF/NUL, framing-only),
`is_header_name()` (RFC 9110 tchar), `is_header_value()` (SP/HTAB/VCHAR).
The same `is_header_value()` now guards `credential_prefix`, the credential
file and — via `_split_host_port()`'s new hostname charset check —
`gateway.upstream`'s host, which is the string that becomes the emitted
`Host:`. That closes the round-4 asymmetry where the trusted operator string
had the file's only header-safety check and the hostile one had none.

**Reproduced live, from inside a real sandbox, over the bind-mounted Unix
socket, against a host-side gateway whose upstream is a real TLS server that
treats a bare LF as a line terminator** (RFC 9112 §2.2). Asserting on what
the upstream *parsed*, not on status:

| shape | client sees | upstream parsed |
|---|---|---|
| `X-Foo: junk\nGET /steal HTTP/1.1\nHost: evil` | `400` | nothing |
| `X-Foo: junk\nx-api-key: ATTACKER-CHOSEN` | `400` | nothing |
| bare CR in value | `400` | nothing |
| NUL in value | `400` | nothing |
| **NUL in name** (the old `isspace()` accepted this) | `400` | nothing |
| trailing bare LF / trailing bare CR | `400` | nothing |
| DEL `0x7f` / VT `0x0b` in value | `400` | nothing |
| `X-Foo: junk\r\nx-api-key: ATTACKER-CHOSEN` (real CRLF) | `200` | one `x-api-key`, the injected one |
| `Content-Length: 4 ` (trailing space) | `200` | forwarded at `cl=4` |
| legitimate request | `200` | one `x-api-key`, the injected one |

Across the whole battery the upstream saw exactly three request lines, all
`POST /v1/messages`, each carrying **exactly one** `x-api-key` — the fake
credential. No `GET /steal`, no `ATTACKER-CHOSEN`, ever.

**The `Content-Length: 4 ` behaviour is unchanged**, as claimed, and the
OWS-exact `strip(" \t")` only moves behaviour in the fail-closed direction:
a value whose only offence was a trailing `\x0b`/`\x0c` used to be silently
repaired by Python's wider `strip()` and is now a `400`. I found no place
where the narrower strip loosens anything. (`_relay_response` still uses
plain `.strip()`, on the trusted response side — a different path, correctly
unaffected.)

**The control is real and the test can fail — I checked this rather than
taking it on faith.** I built a mutant of `egress_proxy.py` with the pre-fix
`value.strip()` and `any(ch.isspace())` restored, and ran the shipped
78-check suite against it: **9 checks fail**, including the live ones, with
the failure text showing the real smuggled request
(`['POST /v1/messages HTTP/1.1', 'GET /steal HTTP/1.1', …]`) and the real
attacker credential reaching the stub. The CONTROL check (#34) passes in
both directions, which is exactly what a control should do. I then ran the
same mutant as a *live gateway* against my own independent rig and the
sandbox smuggled `GET /steal` and `x-api-key: ATTACKER-CHOSEN` through it —
so my rig is not blind either.

**The weaker response-direction rule is defensible.** I drove five crafted
responses from a hostile upstream, each in isolation, plus a plain-`200`
control:

- bare LF (splitting one response into two toward the sandbox), bare CR and
  NUL: **fail closed** — `gateway_upstream_framing_error`, connection torn
  down, and **zero bytes relayed to the client**. I confirmed by reading the
  code that the check sits *before* `conn.sendall(head_bytes)`, and the
  empty client reads confirm it.
- obs-text (`caf\xe9-\xff`) and a VT `0x0b`: relayed verbatim.

That is the stated design, and it is the right call. Neither obs-text nor a
non-CR/LF/NUL C0 can terminate a header line, so nothing can be split; and
the party on the receiving end is the *untrusted* sandbox, so the residual
is self-harm, not a credential exposure. It is disclosed accurately in
`known_limitations` #10.

## D2 — the spend ceiling: FIXED, and the key really is unforgeable

**Reproduced the round-4 attack myself, ceiling 5, from inside a real
sandbox:** 12 requests, one per `fork()`, strictly serial, 12 distinct pids
→ `200 200 200 200 200` then `429 × 7`. Exactly **5** requests reached the
upstream. A same-process follow-up afterwards is still `429`. A request from
a **fresh pid namespace** (`unshare --pid --fork --mount-proc`, rc=0, so the
namespace really was created) is also `429`.

**I verified the uid claim independently rather than accepting the
docstring's reasoning.** With a host-side observer reporting raw
`SO_PEERCRED`, from inside a real `bwrap --unshare-all` sandbox launched by
host uid 1000:

- `uid_map` holds exactly one entry; `setuid(0)`, `setuid(1)` and
  `setuid(65534)` all fail `EINVAL`; only the single mapped uid succeeds.
- **`unshare --user --map-root-user` succeeds and reports `id -u` = 0
  inside** — and the host still sees `SO_PEERCRED uid=1000`. Same with a
  nested user+pid namespace. The obvious next attacker move does not work.
- Conversely, keying really is on the *peer*: my uid-0 sandbox and a
  host-side uid-1000 client each got their own independent 5-request bucket
  against the same daemon (5 + 5 = 10 forwarded upstream, in that order).

**The byte ceiling is exactly as fork-proof as the request ceiling** — I
tested it separately with `max_request_bytes_per_session: 400`: 6 × `200`
then `429` forever, across 12 distinct pids and a fresh pid namespace, with
`reason=per-session request-byte ceiling reached` then
`reason=session budget already exhausted` × 7. Same bucket, same key, same
non-resetting behaviour.

**The eviction change is not abusable.** With a uid key a sandbox can only
ever occupy one bucket, so it cannot fill the 256-entry table at all; the
new "table full of exhausted buckets → `429` rather than evict" path is
unreachable from inside the boundary and would require 256 distinct local
accounts able to reach the socket. The residual that remains — a *non*-
exhausted bucket can still be evicted, resetting a partial budget — is
stated plainly in `known_limitations` #5 and is logged.

**The honesty fixes are real and I found no new overclaim.** The module
docstring, `_peer_session_key()`, `_SessionBudget`, `known_limitations` #5
and runbook §6b now all say the same true thing: a **per-account** ceiling,
shared by every process and every concurrent sandbox under that uid, with no
timed reset — it stays exhausted until the daemon restarts. The operator
consequences are spelled out (size for total work between restarts;
concurrent sandboxes contend; exhaustion denies the next session). The
rejection of a per-session token is argued in writing and the argument is
correct — a token inside the hostile boundary lets the sandbox choose which
bucket to spend, so it adds a weaker second bucket and a secret-distribution
surface without raising the floor. Naming a per-session *socket* as future
launcher work is the right disposition. Runbook §7b carries the QA assertion
that **the forking shape must be run**, not just the cooperative one.

I checked every sentence of the rewritten text against what I observed.
Everything asserted is something I reproduced.

---

## The six round-4 non-blocking items

1. **`_reject()`'s docstring** now names the two client-derived tokens it
   really interpolates and why they are safe. Accurate.
2. **LF-only head** is a fast, logged `400` (`0.00s`, not the 30 s hang),
   with `detail=bare-LF line endings in header block`. **And it did not
   break SSE** — I checked the case that worried me most, since the new scan
   compares CRLFCRLF and LFLF *positions*: 3 keep-alive requests on one
   connection against a genuinely chunked `text/event-stream` upstream whose
   every event ends `\n\n` → 3 × `200`, 5 events each, one upstream
   connection, one `x-api-key` each, `sentinel_seen=True swapped=True`, 0
   leaks. Bodies that are nothing *but* `\n\n` also survive: a 4 KB and a
   25 KB LFLF body arriving in the **same write as the head** were forwarded
   intact (4007 and 25001 bytes upstream) — the round-4 large-body fix is
   not regressed. `head_error()` works on **both** head paths: a clean EOF
   after one request closes silently (no spurious `400`), while a malformed
   follow-up head on a keep-alive connection is a `400` with a log line.
3. **`_charge()` returns counters read under the lock.** Correct.
4. **Unknown `gateway.*` keys are a startup refusal** naming the offending
   key; the correctly-spelled key still loads.
5. **The duplicate-`Content-Length` request/response asymmetry** now carries
   the comment saying why.
6. **The budget battery forks.** Verified above.

## Tests, integrity, constraints

**My counts, not the handoff's.** 9 suites, **262 checks**, 0 failures —
`test_opsdb_broker.py` 65, `test_egress_proxy.py` 13,
**`test_egress_gateway.py` 78** (was 53), `test_developer_pretooluse.py` 14,
`test_trust_flag_monitor.py` 8, `test_cost_tracking.py` 22,
`test_gates_remaining.py` 34, `test_phase_progress.py` 17,
`test_risk_register.py` 11. Exactly the handoff's claim.
`ops/db/operations.sqlite3` unchanged. `py_compile` clean on both Python
files, `bash -n` clean on the wrapper. Exactly the 3 files in
`files_changed` — no scope creep. Hard constraint honored: `id ai-developer`
→ no such user, no `ai-pipeline-*` groups, `/etc/sudoers.d/` contains only
`README`, `/run/ai-pipeline` and `/etc/ai-pipeline` do not exist, no unit
installed, no daemon left running.

**No regression with the real CLI — the check that mattered most.** Real
`/opt/claude-code/bin/claude` through the **shipped**
`launch_developer_sandboxed.sh`, byte-identical, under real bwrap, against a
throwaway Anthropic-shaped SSE upstream: **exit 0**, **3 NDJSON events**,
`apiKeySource=ANTHROPIC_API_KEY`, `result.subtype=success`,
`is_error=False`, and the answer text came from my throwaway upstream. Two
`POST /v1/messages?beta=true` on **one** gateway connection, bodies 4088 and
23643, both `sentinel_seen=True swapped=True`, each carrying exactly one
`x-api-key` (the fake credential), **0 sentinel leaks upstream**, **0**
occurrences of the credential or sentinel in the daemon's log.
**6 × `CONNECT api.anthropic.com:443` → 403**, CLI unaffected.

**The real CLI's headers pass the new stricter validation.** Both requests
carried **21** real header names — `X-Stainless-*`, `anthropic-beta`,
`anthropic-dangerous-direct-browser-access`, `x-app`, `User-Agent`,
`X-Claude-Code-Session-Id` and the rest. I re-ran all **42** captured header
lines through the shipped `is_header_name()`/`is_header_value()` directly:
**0 rejected**. The new rule is not too strict for legitimate CLI traffic.

---

## Non-blocking observations (for QA/DevOps, not for a re-round)

- **`test_egress_gateway.py` check 73 is weaker than it reads.** It calls
  `_peer_session_key()` on the **client** end of the socket, so `SO_PEERCRED`
  returns the *proxy's* uid; because the in-process proxy runs under the same
  uid as the test, `key == ("uid", os.getuid())` would hold even if the code
  keyed on the daemon's own uid. Checks 69–72 are the real proof and they are
  decisive, and my own two-uid probe confirmed genuine peer keying — so this
  is a test-comment/robustness nit, not a gap in the property.
- **Runbook §6b describes the per-account ceiling but not the "table full of
  exhausted buckets → 429" path**, which only the `_session()` docstring
  covers. Unreachable in this design's shape; worth one line if the key ever
  changes.
- Round-4's three handed-forward QA items stand unchanged and are still the
  right ones: a real-endpoint smoke test at cutover (DevOps), enumerating the
  endpoint set from a real long session with tool use, and re-testing D1's
  fix against the real front end (which sets its severity there, not its
  correctness).
- `known_limitations` #6 (connection-count DoS) and #7 (the chain still
  cannot run as `ai-developer`) remain accurate and correctly out of scope.

## What I did not re-litigate

Everything listed under round 4's "Verified — do not re-litigate" was
re-exercised only for regression, and I found none: the fixed destination,
the fail-closed path allowlist in both request forms, per-request injection
over real chunked SSE, no redirect following, no cross-session upstream
reuse, metadata-only logging, the 13 startup-refusal cases, the TLS contract
(`main()` as root still refuses to start — I hit this myself building the
rig), and the CONNECT reserve denials.
