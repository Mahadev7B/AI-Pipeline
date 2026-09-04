# Red Team adversarial review — TASK-023 CTO addendum (model-API network carve-out, finding B3; B1/B2/B4 dispositions)

Reviewing the `## Addendum (Code Review's TASK-023 review ...)` section of
`ops/reviews/cto-task023-architecture.md` (B3 carve-out + B1/B2/B4
dispositions), against Code Review's REJECT (`ops/reviews/code-review-task023.md`),
my own two prior reviews on this milestone (`review_results.id=73` REJECT,
full text `ops/reviews/red-team-task023-review.md`; and the PASS
re-verification `ops/reviews/red-team-task023-reverification.md`), and
independent empirical testing in this environment (bwrap 0.9.0). This gate
is required and non-skippable per the Founder's standing instruction
because the addendum reopens exactly one egress path that `--unshare-all`
previously closed — a security property I previously blessed as
load-bearing for `risks.id=3`.

**Verdict: PASS.** The carve-out preserves the default-no-network,
fail-closed posture; the one exception is a single, named, host-enforced
channel that the sandboxed Developer cannot widen; the trust boundary is
genuinely 100% host-side; the simpler alternatives are correctly rejected
for a reason I independently verified; and the B1/B2/B4 dispositions are
concrete, buildable, and in B4's case the intellectually honest call
(remove an inert layer rather than fake it). The exfil-via-API residual is
disclosed honestly and its acceptance is reasonable for a medium-severity,
single-operator risk. One non-blocking item for Development/Security is
named below; it does not reopen the design and does not justify a REJECT.

---

## What I independently verified (not taken on the addendum's word)

All run live in this environment, bwrap 0.9.0, throwaway processes only (no
accounts/services provisioned), the §1 discipline:

1. **General egress is structurally blocked.** Raw TCP connect to an
   external IP (`93.184.216.34:443`) from inside `bwrap --unshare-all`:
   `OSError [Errno 101] Network is unreachable`. The carve-out does not
   reopen general egress.
2. **The host's own ambient agent proxy is unreachable from the sandbox.**
   Connect to `127.0.0.1:43409` (this env's `HTTPS_PROXY`) from inside the
   sandbox: `ConnectionRefusedError` — the sandbox netns has its own
   loopback; the host proxy is not incidentally exposed. (Refused, not
   unreachable, also confirms loopback is up inside the sandbox — the
   property option (b)'s in-sandbox relay depends on.)
3. **The one bound Unix socket + a host-side allowlisting CONNECT proxy
   enforces correctly, including port scope.** Through the bind-mounted
   socket, with a host+port allowlist of exactly `api.anthropic.com:443`:
   `api.anthropic.com:443` -> `200 Connection Established`;
   `evil.example.com:443` -> `403`; `api.anthropic.com:22` (allowlisted
   host, wrong port) -> `403`; `8.8.8.8:53` (raw IP) -> `403`. The
   allow/deny decision is made host-side, outside the sandbox's control. An
   exact host+port allowlist denies raw-IP CONNECTs and non-443 ports as a
   side effect — the sandbox has no DNS of its own, so it cannot rebind or
   redirect the hostname the host-side proxy resolves.
4. **Socket-absent path is structurally absent.** Re-running the identical
   client with the socket not bind-mounted: `FileNotFoundError` — "the path
   does not exist in that namespace," not a denial-with-audit-trail.
5. **The allowlist config, host-side and not bind-mounted, is invisible in
   the sandbox.** A host file at a known absolute path, not bound, resolves
   `os.path.exists(...) == False` inside the sandbox. The sandboxed
   Developer — even as root in its own user namespace — cannot read or
   widen the allowlist.
6. **CAP_NET_ADMIN IS held inside the sandbox netns.** `CapEff` inside
   `bwrap --unshare-all` decodes with bit 12 (CAP_NET_ADMIN) set. This is
   the load-bearing fact behind rejecting slirp4netns / in-netns nftables:
   the sandbox is root over its own netns and could flush any firewall
   rules placed *inside* that netns. Confirmed — the rejection of those
   alternatives is sound, not asserted.

## The specific attack angles, probed

1. **Widen/bypass the allowlist.** Config is host-side, not bind-mounted
   (verified #5) — cannot be widened from inside. The one socket speaks only
   the forward/CONNECT protocol; the addendum proposes no config-reload or
   control verb over it, so there is no control surface to reach. DNS
   rebinding / hostname-that-resolves-elsewhere fails because the sandbox
   has no resolver and the host-side proxy resolves the name itself.
   Raw-IP / non-443 encodings are denied by an exact host+port match
   (verified #3). **Sound, with one implementation-contract caveat, below.**
2. **Is the CONNECT proxy a general tunnel?** It tunnels only to
   `api.anthropic.com:443` (non-443 denied, #3), i.e. to the real API IP the
   host-side proxy resolves. Once tunneled, the sandbox controls its own TLS
   — but only toward the real API. It cannot pivot to another host or port.
   That the tunnel is a data channel to the API is exactly the disclosed
   residual (angle 4), not an undisclosed hole.
3. **The in-sandbox loopback->socket relay is genuinely "untrusted-but-
   harmless."** Confirmed: enforcement is 100% host-side. The sandbox has no
   network route at all (#1), so whatever the Developer does to the relay —
   replace it, rewrite it — the only reachable egress remains the single
   bound Unix socket to the host-side proxy, which enforces regardless. The
   Developer controlling the relay changes nothing about what the host
   proxy will forward. The trust boundary really is entirely host-side.
4. **The exfil-via-API residual.** Honestly disclosed, correctly framed as
   inherent to running a real model-backed Developer at all (the CLI must
   reach the API), and correctly framed as strictly smaller than the general
   egress `--unshare-net` closes: one destination, no C2, no registries/
   paste-sites, single auditable chokepoint. For a medium-severity,
   single-operator risk, accepting it (with volume-observability named as a
   follow-up option, not silently promised as built) is reasonable. No cheap
   mitigation is being skipped — you cannot prevent prompt-embedded exfil
   while permitting the API. The Founder should sign off on this explicitly,
   as the addendum itself asks.
5. **Fail-closed-on-restart session model.** In-memory `_sessions`, launcher
   re-registers idempotently or tears the sandbox down, sandbox cannot
   self-recover. Tokens are 128-bit (`secrets.token_hex(16)`), not
   collidable across sessions; registration is `SO_PEERCRED`-gated to the
   Founder UID so the sandbox can never call it. On mid-session restart the
   token is invalid = fail closed. No race that lets a stale/unregistered
   token through. Sound.
6. **B1/B2/B4 dispositions are adequate, unambiguous build targets.**
   - B1: concrete — `try/except OSError` per connection, add `sqlite3.Error`
     to the handler catch returning `_err`, `conn.settimeout()`, validate
     required arg presence/type before the DB, in-memory fail-closed
     sessions. Buildable exactly as stated.
   - B2: four concrete mechanisms. Passing the token as a `0640` file rather
     than an env var is not just correct against sudo `env_reset` — it is a
     real improvement (keeps the capability token out of the process table
     and `/proc/<pid>/environ`). Prompt-in-worktree, `User=`/trusted-UID in
     the unit, and inner `timeout` + `--die-with-parent` (with a
     `PermissionError` backstop) are all correct and buildable.
   - B4: the honest disposition — do NOT seed a trust flag to force an inert
     hook to fire; drop the in-sandbox hook-as-defense-in-depth claim and
     correct the §5.1 / persona-note overclaim. This is the right call, and
     it loses nothing real: the `PreToolUse` string-pattern hook was always
     defeatable by subprocess/symlink/encoding — precisely the bypasses the
     namespaces now close structurally. A weaker layer that also cannot fire
     is not defense-in-depth. The trust-flag concern that remains real
     (non-sandboxed qa/cto/devops) is covered by the already-shipped
     generalized monitor. Removing a security-theater claim rather than
     adding complexity to fake it is the correct, non-hand-wavy answer.
7. **Overengineering / simpler-alternative check.** The Unix-socket +
   host-proxy is not new architectural weight — it is a second instance of
   the exact mechanism already established for the opsdb broker socket
   (§3/§4.4). Keeping `--unshare-net` and adding one explicit socket makes
   the default "no network" and the exception a single fail-closed channel,
   which is strictly safer posture than drop-`--unshare-net`+host-firewall
   (IP-based, brittle to API IP changes and shared-CDN fronting, and
   fail-to-filtering rather than fail-closed). slirp4netns / in-netns
   nftables are correctly disqualified by the CAP_NET_ADMIN fact I verified
   (#6). The only added moving part is the optional in-sandbox relay
   (option b), needed only if the CLI cannot do a Unix-socket proxy directly
   — correctly flagged as a verify-against-the-real-binary item. Right
   weight, not overengineered.

## Non-blocking (required Development + adversarial-Security focus, not a design hole)

The addendum specifies the allowlist *behaviorally* ("permit
`api.anthropic.com:443`, deny everything else") and correctly routes the new
egress-proxy artifact through the full Code Review/QA/Security gates with
explicit deny-tests in the QA charter (items (c) and (f)). It does not spell
out the CONNECT-matching robustness contract, and Security should hold the
implementation to it explicitly: match the allow decision on the
proxy-parsed CONNECT request-line target host:port (never a client-supplied
`Host:` header); resolve the hostname host-side and never trust a
client-supplied IP literal; deny/fail-closed on any parse ambiguity,
malformed request line, non-CONNECT method, IPv6/decimal-encoded targets, or
trailing junk. My testing shows a correct exact-match implementation
achieves all of this (and denies raw-IP and non-443 as a side effect), so
this is an implementation-quality contract the downstream adversarial
Security gate is designed to catch — not an unclosed hole in the
architecture. Naming it so it is not left implicit. Add a QA-charter
assertion that a CONNECT to a raw IP equal to the API's resolved address is
also denied, to lock the "match on hostname, not IP" property.

## What I could NOT do in this environment

I verified the sandbox/socket/allowlist mechanics with a throwaway proxy and
a real bwrap sandbox, but I did not exercise the actual `claude` CLI's own
`HTTPS_PROXY`/Unix-socket behavior (whether option (a) direct Unix-socket
proxy works or option (b)'s relay is required) — the addendum already flags
this as a verify-against-the-real-binary Development/Red Team item, and it
remains one. A fully tool-bearing interactive session (or DevOps on the
production host) should confirm it before this ships, alongside the §7
production-host feasibility re-run.

## Disposition

**PASS**, advanced to Development. Everything the addendum reopens is sound,
honestly disclosed, and adequately specified as a build target. Development
must now implement: (B3) the carve-out — `--unshare-net` retained, one
bind-mounted egress Unix socket, a host-side allowlisting forward/CONNECT
proxy running as a trusted non-`ai-developer` account with a host-owned,
non-bind-mounted allowlist config permitting only the model-API host(s)
(and this env's chained agent proxy) and denying all else including package
registries, plus the CLI bridge (option a if the real binary supports it,
else the fixed option-b relay); (B1) broker crash/wedge hardening + in-memory
fail-closed sessions; (B2) the four launch-path fixes (token-as-file, prompt
readable via the shared group, non-root broker + trusted UID, cross-UID
timeout kill); (B4) drop the in-sandbox trust-flag seed and correct the §5.1
/ persona-note overclaim; plus the non-blocking Code Review items
(exhaustive 24-verb exclusion test, reuse `send_request`, broker-mode
`task-status` printing authoritative values, `trust_flag_monitor` except
breadth) and the CONNECT-matching robustness contract named above. Then back
through Code Review -> QA -> Security (adversarial) -> CTO conformance per §8.
