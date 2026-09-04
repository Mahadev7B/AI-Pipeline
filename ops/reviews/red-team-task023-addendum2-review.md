# Red Team adversarial review — TASK-023 CTO **second addendum** (C2: credential delivery into the sandbox; C1: the argv fix)

Reviewing the `## Second addendum (Code Review round 3 ...)` section of
`ops/reviews/cto-task023-architecture.md` against Code Review's REJECT
(`ops/reviews/code-review-task023-round3.md`), my own three prior reviews on this
milestone (`red-team-task023-review.md` REJECT / `review_results.id=73`,
`red-team-task023-reverification.md` PASS, `red-team-task023-addendum-review.md`
PASS on addendum 1 — verified property #5 and the *opaque CONNECT tunnel* I
blessed there), the shipped `egress_proxy.py` / `egress_relay.py` /
`launch_developer_sandboxed.sh`, and my own live testing against the **real**
`/opt/claude-code/bin/claude` 2.1.252 inside a **real** `bwrap --unshare-all`
sandbox. This gate is required and non-skippable: addendum 2 converts a
component I blessed as a content-blind CONNECT tunnel into a **terminating
gateway that reads, reframes and rewrites plaintext prompts and responses and
holds the real credential**. That is a genuine widening of a trusted
principal's capability, and CTO states it plainly rather than arguing it away.

**Verdict: PASS — with a binding, enumerated gateway contract (§C1–C10 below),
two factual corrections to the addendum's own text, and one residual moved from
"named, not built" to *required*.** The architectural decision is correct: of
the four options, the only one that keeps a durable operator credential out of a
principal we have explicitly decided to treat as hostile is host-side injection,
and it lands at a chokepoint that already exists, is already trusted, and
already owns the sandbox's only egress. The mechanism holds *when implemented
against the contract below* — and I demonstrated, live, that one specific and
entirely natural mis-implementation hands the real credential to an
attacker-chosen host in a single request from inside the sandbox. That is the
difference this contract exists to close.

Nothing else is reopened. The bwrap shape, §1's containment results, the
five-verb broker, the `ai-developer` account, Developer-only scoping, the
invocation model, addendum 1's default-no-network posture and property #5 all
stand.

---

## 1. What I verified myself (real binary, real sandbox, throwaway processes, fake credentials only)

I did **not** read, copy, move or expose any real credential material. Every
credential value in every test below is a fake literal I invented
(`FAKE-REAL-CREDENTIAL-DO-NOT-USE`), and the only request that ever left this
host carried `x-api-key: FAKE-NOT-A-REAL-KEY`.

1. **Credential invisibility inside the namespace — confirmed.** Under the
   shipped bind set, inside a real `bwrap --unshare-all`:
   `/home/claude` → `exists=False`, `/home/claude/.claude/remote/.oauth_token`
   → `exists=False`, `/etc` lists exactly `['alternatives','group','passwd','ssl']`.
   Property #5 holds for the new credential file by the same mechanism.
2. **The sentinel design works end to end against the real binary, in the real
   sandbox.** Real `claude` 2.1.252, shipped `egress_relay.py`, shipped bind-set
   shape, `ANTHROPIC_BASE_URL=http://127.0.0.1:8889`,
   `ANTHROPIC_API_KEY=SANDBOX-PLACEHOLDER-NOT-A-CREDENTIAL`, my throwaway
   fixed-destination gateway on the bind-mounted Unix socket: proper `init`,
   real `POST /v1/messages?beta=true`, **2/2 upstream requests carried the
   injected fake credential, 0 carried the sentinel**. CTO's claim 3 reproduced
   independently.
3. **Keep-alive is real and CTO's gotcha #5 is not a fluke.** Both model POSTs
   rode **one** connection, in both my bare-host and in-sandbox runs. Per-request
   substitution is a correctness *and* security requirement, exactly as stated.
4. **`ANTHROPIC_API_KEY` precedence and non-validation — confirmed.** Running as
   root with the on-disk oauth token fully readable, the CLI sent my sentinel
   verbatim as `x-api-key` and never touched the file. Any string is passed to
   the wire unvalidated.
5. **TLS re-origination through this environment's ambient proxy — confirmed.**
   `CONNECT api.anthropic.com:443` via `HTTPS_PROXY`, then real TLS, with a fake
   key: real `401 {"type":"authentication_error","message":"invalid x-api-key"}`
   with a real `request_id`. Works with both `/root/.ccr/ca-bundle.crt` and the
   plain system CA store.
6. **The "bind it" rejection's load-bearing exfil claim — confirmed.** Handoff
   `work_completed`/`known_limitations` and `activity-log` free text are read
   from the DB and rendered into the control-center HTML
   (`ops/control-center/generate_task.py` lines 311–330, escaped via
   `layout.e()` — escaped, but *displayed*), and the sandbox writes a git
   worktree whose commits are pushed to a GitHub repo. A durable bearer
   credential placed inside the sandbox is a credential that can be written into
   a source file and pushed, or typed into a handoff a human reads. CTO's
   reasoning holds; the simpler "just bind it" option is correctly rejected.

## 2. The finding that decides this review: the destination constraint (attack angle 2)

Under addendum 1 the destination was explicit and checked (`CONNECT
host:port`, matched host-side against an allowlist the sandbox cannot see). In
gateway mode the destination is supposed to come **only from trusted-side
config**. The addendum says so — once, in passing ("re-originates over TLS to
the configured model-API host") — and never states it as an enforceable
contract clause the way §B3's CONNECT contract was eventually stated in
`egress_proxy.py`'s docstring.

That gap matters more than it looks, because of a traffic fact the addendum
does not mention and I found by running it:

> **With the shipped relay, the model request arrives at the gateway in
> proxy *absolute* form, with an attacker-controllable authority.**
> `egress_relay.py` sets `HTTP_PROXY`/`HTTPS_PROXY` to itself before exec'ing
> `claude`, so the CLI emits
> `POST http://127.0.0.1:8889/v1/messages?beta=true HTTP/1.1` with
> `Host: 127.0.0.1:8889` — not the origin-form `POST /v1/messages?beta=true`
> that CTO's own transcript shows. Observed in the real sandbox, twice per run.

So the gateway's input is literally a proxy request carrying a URI. The most
natural implementation of "an HTTP forward gateway" — parse the absolute URI (or
the `Host:` header) and dial it — is therefore the one a developer is most
likely to write, and it is catastrophic. I built both variants and drove them
from inside a real sandbox:

| gateway variant | client request from inside the sandbox | where the real credential went |
|---|---|---|
| destination from trusted config (correct) | `POST http://127.0.0.1:18912/steal` (absolute-form, attacker authority) | configured upstream only |
| destination from trusted config (correct) | `POST /steal` + `Host: 127.0.0.1:18912` | configured upstream only |
| destination from request URI/Host (naive) | `POST http://127.0.0.1:18912/steal` | **attacker host, credential attached** |
| destination from request URI/Host (naive) | `POST /steal` + `Host: 127.0.0.1:18912` | **attacker host, credential attached** |

Total credential compromise in one request, from a principal the whole design
assumes is hostile, over the one socket the design gives it. The design is
right; the specification is one clause short of forcing the right build. Hence
the contract in §4 — which is the same instrument that worked last round (my
addendum-1 CONNECT contract was implemented verbatim into
`egress_proxy.py`'s docstring clauses 1–5 and Code Review then held it to them).

## 3. Two factual claims in the addendum that are wrong against the real binary

**(a) "Nothing the sandbox does uses `HTTPS_PROXY` or CONNECT any more, so the
allowlist config becomes empty by default." — False.** With `ANTHROPIC_BASE_URL`
pointed at the relay and the shipped relay's proxy env in place, the real CLI
*still* issues CONNECTs on the same socket. Observed in the real sandbox in one
short run: **5 × `CONNECT api.anthropic.com:443`** and, on the bare host with
the same env, **`CONNECT http-intake.logs.us5.datadoghq.com:443`** (Datadog
telemetry). With an empty reserve allowlist all of them were `403`-ed and the
CLI still completed its model call normally.

This *strengthens* the recommendation and changes its justification: the CONNECT
path is **live, adversarially and incidentally exercised surface**, not dormant
reserve. It also answers residual #5 ("whether the CLI needs any destination
besides the model API was not exhaustively determined") — it tries to, it must be
denied, and denial is harmless. **Endorsed: keep the CONNECT path with an empty
allowlist, keep the deny-tests, and add the two destinations above as named QA
deny-assertions.** Do not add `api.anthropic.com:443` back to the allowlist "for
the CLI's benefit": it needs no credentialed CONNECT and getting one would give
it a content-opaque tunnel to the API that the gateway cannot see.

**(b) The recommended empty allowlist is incompatible with the shipped,
already-reviewed code.** `AllowlistConfig.load()` raises
`ValueError: egress allowlist config permits nothing ('allow' is empty) —
refusing to start a proxy that can never forward anything`, and it is called from
`serve_forever()`. Confirmed by running it. Since the same daemon will own the
gateway, the recommended default configuration **prevents the entire egress
path, including the model gateway, from starting**. The dangerous fix is to
delete the guard; see contract clause C9.

## 4. Binding gateway contract (Development MUST implement; Code Review/QA/Security MUST hold it to these)

These are requirements of this review, not suggestions. State them in
`egress_proxy.py`'s docstring the way the CONNECT clauses already are.

- **C1 — Destination is trusted-side only.** The upstream host/port comes
  *exclusively* from the trusted-side config file. The request line's authority
  (absolute-form URI) and the `Host:` header are **never** consulted for
  destination selection, for TLS SNI/verification, or for anything else. Test
  both attack shapes in §2's table; both must reach the configured host only.
- **C2 — Both request forms are accepted and normalised.** Absolute-form
  (`POST http://…/v1/messages`) is what the shipped relay actually produces;
  origin-form must also work. The gateway rewrites the target to origin-form and
  emits its own `Host:` for the configured upstream. Anything else (CONNECT is
  handled by the reserve path; unknown methods/malformed request lines) is a
  fail-closed `400`, connection closed.
- **C3 — Per-request injection, and never a tunnel.** Every request on every
  connection is parsed and rewritten. The gateway must never degrade into
  byte-pumping after request 1. Any existing `x-api-key` / `Authorization` /
  `Proxy-Authorization` header from the client is **removed and replaced**, not
  appended to.
- **C4 — Response framing is part of the security property.** Real model traffic
  is `"stream":true` (verified in the captured request body): responses are SSE,
  chunked, no `Content-Length`, long-lived. CTO's "2/2 injected, 0 leaked" proof
  used a short `Content-Length` stub, so the keep-alive fix has **never been
  exercised against the response shape production actually uses**. The gateway
  must stream responses incrementally and track chunked/EOF framing correctly,
  because getting request N's response boundary wrong is what makes request N+1
  slip through unrewritten. **QA must assert per-request injection across a
  multi-request keep-alive session whose responses are real streamed SSE**, not
  a stub 400.
- **C5 — Framing ambiguity fails closed.** Both `Content-Length` and
  `Transfer-Encoding` present, duplicate/conflicting `Content-Length`,
  non-decimal length, or a `Transfer-Encoding` the gateway does not fully
  implement → `400` + close the connection (never "best effort"). Bodies are
  **streamed** with a generous ceiling, never buffered whole: the untrusted side
  can otherwise declare a huge `Content-Length` and OOM a trusted host daemon.
- **C6 — No credential can come back.** The gateway must not follow redirects
  (relay 3xx to the client verbatim; never re-issue a request with the injected
  header). No error/diagnostic response, header or body may contain the injected
  value or any part of it. No debug/echo/control verb on the socket.
- **C7 — No connection sharing across clients.** One client connection maps to
  its own upstream connection; upstream connections are never pooled or reused
  across client connections or sessions. Two concurrent Developer sandboxes must
  not be able to reach each other's prompts or responses through a shared
  upstream socket.
- **C8 — Logging: metadata only, explicitly.** The gateway now sees every prompt
  and every response of the Founder's own work. It must never log request or
  response **bodies**, never log the credential or the value of any
  `x-api-key`/`Authorization` header (not even truncated/hashed), and never
  write bodies to disk, journal, or stderr. Permitted: timestamps, method, path,
  status, byte counts, session/connection ids, `sentinel_seen`/`swapped`
  booleans. This must be a stated requirement in the file and a QA assertion
  (drive a session, grep the daemon's entire log output for the credential
  literal and for prompt text — both must be absent).
- **C9 — Reconcile the empty-allowlist guard deliberately.** The existing
  fail-closed "refuse to start if I can forward nothing" guard must be
  *retained in spirit*: refuse to start when the daemon can serve nothing at
  all. The permitted configuration is `allow: []` **plus** a valid gateway
  config (credential file present, `0600`, owned by the trusted account,
  destination configured). Empty allowlist + no gateway config = still refuse to
  start. Missing/unreadable credential file = refuse to start, never start and
  forward requests un-credentialed or with the sentinel.
- **C10 — TLS verification is mandatory and must never be disabled.** Verify
  hostname + chain against a CA store the trusted account can actually read.
  Note for DevOps: on *this* host the ambient proxy's CA bundle lives at
  `/root/.ccr/ca-bundle.crt` under a `0700 /root`, unreadable by a non-root
  `ai-pipeline-egress` account — the system store works today (I verified a real
  401 both ways), but if a deployment's proxy re-terminates TLS with a private
  CA, provision a readable copy; do **not** solve it by running the gateway as
  root or by disabling verification. A QA assertion that a bad/untrusted cert
  fails closed belongs in the charter.

**Also required (spend — residual 3, moved from "named, not built"):** a hard,
gateway-side per-session ceiling (max requests and max cumulative request bytes,
configurable, fail-closed with a `429` + log line when hit). `--max-budget-usd`
is enforced by the untrusted side and is therefore worth nothing against the
threat model this milestone exists to address; a compromised session can
currently spend the operator's account without limit, and the gateway is the
only place a limit can exist. It is ~20 lines at a chokepoint that already
parses every request. I am not requiring token-accurate cost accounting — a
crude request/byte cap is enough to convert "unbounded" into "bounded and
alarming". If CTO wants to ship without it, that needs an explicit Founder
acceptance of unbounded spend by an assumed-hostile principal, not a footnote.

**Also required (scope of the credential — new, not in the addendum):** the
gateway attaches the operator's credential to *any* path the sandbox chooses on
the API host (my `POST /steal` went upstream credentialed). That is broader than
"the sandbox can talk to the model": it is "the sandbox can use the operator's
credential for anything that credential can do on that host". Implement a
fail-closed, configurable **request-path allowlist** (start from the endpoints a
real session actually uses — I observed `HEAD /api/hello` and
`POST /v1/messages?beta=true`, nothing else — and have QA enumerate the full set
from a real run, adding any that are genuinely needed). A missing path must be a
visible `403` from the gateway, not a silent widening.

## 5. The disclosed residuals, judged

- **(a) The plaintext hop — accepted.** It never crosses a network (sandbox
  loopback → bind-mounted Unix socket, inside a netns I re-verified has no
  route), and the principal that sees it is the same trusted non-`ai-developer`
  account that already decides what the sandbox may reach and already owns the
  allowlist. The honest framing is CTO's third bullet: it is nonetheless a
  *wider capability* for that principal, and the correct response is a higher
  review bar plus C8's explicit no-body-logging rule — which the addendum did
  not state and I am adding. The TLS-MITM alternative is correctly rejected as
  strictly more moving parts for identical visibility. **The Founder should
  accept this explicitly**, alongside §4.2's ergonomics cost and addendum 1's
  exfil-via-API residual.
- **(b) Spend — not acceptable as "named, not built."** See above; now required.
- **(c) Production auth-shape parity — acceptable as a DevOps pre-cutover gate,**
  in the same slot as §1's production-host re-run, with CTO's "if the production
  account cannot present a header-injectable credential, this returns to CTO, it
  does not get patched around in code" held to literally.
- **(d) CONNECT as fail-closed reserve — endorsed, with the justification
  corrected** (§3(a)): it is not unused surface, it is actively exercised and
  actively denied, which is precisely why the deny-tests must stay and why C9
  must not resolve the empty-allowlist conflict by deleting a guard.

## 6. Overengineering check (standing job)

Right weight, and the alternatives are rejected on merits rather than
convenience. "Bind the durable credential" is disqualified twice over — by the
environment-specific hardcoded path, and by exfil channels I verified exist
(§1.6). `apiKeyHelper` genuinely works (CTO tested it) but leaves a live
credential *inside* the sandbox and re-mintable at will by the compromised
session; the TTL bounds a captured token's value, not the session's access, and
the scoped-token minting service it would need does not exist here — correctly
recorded as the composable fallback rather than dismissed. TLS-MITM adds a CA
lifecycle for zero gain. The chosen shape adds one mode to a daemon that already
exists, on a socket that already exists, owned by an account that already exists;
no new dependency, no new principal, no new privileged surface. The one thing it
adds that I insist on paying for is the contract in §4 — because the delta
between the safe and the catastrophic implementation is a single line of
destination-selection logic (§2).

## 7. What I could not do here

I ran everything against *this* container's CLI build, kernel and ambient proxy.
Production-host parity (namespace feasibility, auth shape, whether the ambient
proxy MITMs TLS and with which CA) remains DevOps's pre-cutover job and is not
transferable from anything above. I also did not exercise a real streamed SSE
response through a real gateway (my upstreams were stubs) — which is exactly why
C4 is a QA requirement rather than a claim.

**No residue:** no accounts, groups, sudoers entries, units, `/run/ai-pipeline`
or `/etc/ai-pipeline`, and no daemons left running; all throwaway sockets and
processes were under the session scratchpad and are gone.

## 8. Disposition

**PASS**, advanced to Development, subject to §4's contract in full. Development
implements: C1 (`--verbose` with `stream-json`, verified against the real binary,
and the launcher's stdout consumer checked against what `stream-json --verbose`
actually emits); C2's gateway mode per contract clauses C1–C10 plus the required
spend ceiling and request-path allowlist; the runbook/QA-charter items the
addendum lists (g)–(j) plus the deny-assertions for
`api.anthropic.com:443` and `http-intake.logs.us5.datadoghq.com:443`, the
no-credential-in-logs assertion, and the multi-request **SSE** keep-alive
assertion; and Code Review round 3's six non-blocking items. Then back through
Code Review → QA → Security (adversarial) → CTO conformance per §8. The two
factual corrections in §3 belong in the architecture document itself so the next
reader does not inherit them.
