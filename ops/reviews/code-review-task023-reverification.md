# Code Review re-verification — TASK-023 (risks.id=3 durable closure: OS-level sandboxing for Developer)

Reviewer: code-review. Scope: `handoffs.id=14`, commit range
`eb0bf4a..c604783` (cumulative; in-progress snapshot `886b65a` inside the
range reviewed as part of the cumulative result). Baselines read in full:
my own prior REJECT (`ops/reviews/code-review-task023.md`), the CTO
architecture including the B3 addendum
(`ops/reviews/cto-task023-architecture.md`), and Red Team's PASS on that
addendum (`ops/reviews/red-team-task023-addendum-review.md`), including the
CONNECT-parse robustness contract.

**Verdict: REJECT — returned to Developer (IN_DEVELOPMENT).**

This is a strong pass on substance. B1 is genuinely fixed — I reproduced
both of my original live crashes and neither survives. The B3 egress
carve-out is architecturally faithful and its enforcement is real: I ran
the full sandbox → relay → Unix socket → host-side proxy chain end to end
for the first time in this milestone's history and watched
`api.anthropic.com:443` return `200 Connection Established` while
`evil.example.com:443` was `403`-ed host-side and direct external egress
failed with no route. The CONNECT parser held under 29 adversarial cases
plus short reads, a 128 KB no-newline flood and a 32 KB request line. All
four non-blocking items were done properly. All 8 suites pass, 183 checks.

It is nevertheless a REJECT, because the pass repeats the specific failure
that produced my first REJECT: code and config that cannot possibly work
on first real use, in ways determinable without any OS provisioning. Two of
the three blocking findings below were reproduced live by this reviewer,
and the third is a directly-specified CTO requirement that the code's own
comments claim to implement and do not. One of these (R1) I should have
caught in my previous review and did not — stated plainly below rather than
presented as new.

## Blocking findings

### R1. The sandbox cannot exec anything at all — the bind set is missing the root symlinks and `/etc` (reproduced live)

`launch_developer_sandboxed.sh` binds `--ro-bind /usr /usr` and then, for
`/bin`, `/lib`, `/lib64`, does **nothing at all** when they are symlinks:

```
for real_dir in /bin /lib /lib64; do
  if [ -d "$real_dir" ] && [ ! -L "$real_dir" ]; then
    BWRAP_ARGS+=(--ro-bind "$real_dir" "$real_dir")
```

with the comment "already reachable via the `/usr` bind above." They are
not. bwrap starts from an empty root and creates only the paths it is told
to; it does not recreate `/lib64 -> usr/lib64`. Every dynamically-linked
binary on this host requests interpreter `/lib64/ld-linux-x86-64.so.2`
(confirmed with `readelf -l` on `/usr/bin/timeout` and `file` on
`/opt/claude-code/bin/claude`), so that path must exist inside the
namespace. Run with the wrapper's exact bind set:

```
$ bwrap --unshare-all --die-with-parent --ro-bind /usr /usr --proc /proc \
        --dev /dev --tmpfs /tmp -- /usr/bin/timeout --signal=KILL 5 /usr/bin/echo hello
bwrap: execvp /usr/bin/timeout: No such file or directory      # exit 1
```

Adding `--symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64
/lib64` to the identical command prints `hello`, exit 0. Running the real
wrapper (throwaway sockets, throwaway worktree) produces exactly the same
error, so this is not a synthetic reproduction.

A second, independent gap sits behind it and is new in this pass:
`PYTHON_BIN="/usr/bin/python3"` (added here to exec the relay) is a symlink
to `/etc/alternatives/python3`, and `/etc` is not bound into the sandbox at
all. With the symlinks fixed but no `/etc`:

```
/usr/bin/timeout: failed to run command '/usr/bin/python3': No such file or directory   # exit 127
```

Consequences, all three of them load-bearing pieces of this pass: the B2.4
inner `timeout --signal=KILL` never runs, the B3 relay never runs, and
`claude` itself never runs. The sandbox is structurally non-functional on
this host — the same category as my original B3 ("a launch path that
structurally cannot function must not pass review"), now for a different
reason.

**Honest correction:** the `/bin`/`/lib`/`/lib64` loop is pre-existing
(unchanged since `eb0bf4a`) and my previous review explicitly blessed it
("so the conditional real-bind loop is correct"). That was wrong; I did not
exec anything in the sandbox then. The `/etc` half is new in this pass. Both
are live in the code under review and both must be fixed.

**Fix shape, and a trap to avoid.** Emit `--symlink usr/bin /bin` (etc.)
in the `else` branch of that loop rather than nothing. For `/etc`: do **not**
add a blanket `--ro-bind /etc /etc` — the runbook puts the egress allowlist
at `/etc/ai-pipeline/egress-allowlist.json`, and a whole-`/etc` bind would
make it visible inside the sandbox, contradicting the addendum's "not
bind-mounted into the sandbox" and Red Team's verified property #5. Bind the
narrow paths actually needed (`/etc/alternatives`, `/etc/ssl`,
`/etc/passwd`, …), or resolve `PYTHON_BIN` to the real interpreter. Derive
the final set by actually exec'ing inside the sandbox, not by reasoning —
that is what this whole finding is about. Note that TLS to the model API
will likely need the system CA bundle, which is also under `/etc`.

Once both gaps are patched (in a scratch copy only — I did not modify the
repo), the rest of the composition is correct and I verified it live:
the prompt arrives as one unmodified argv element with `$(whoami)`,
backticks and `; rm -rf /` uninterpreted; `HTTPS_PROXY=http://127.0.0.1:8889`;
the token delivered file → `--setenv`; cwd is the worktree;
`operations.sqlite3` and `.founder_credential.json` both absent from the
namespace; `api.anthropic.com:443` → `200 Connection Established` through
the relay; `evil.example.com:443` → `403` decided host-side; a direct
external TCP connect → `OSError`. That is the whole B3 design working. Only
the bind set is wrong.

### R2. `egress-proxy.service` cannot start as shipped — `ProtectHome=true` with a `WorkingDirectory=`/`ExecStart=` under `/home`

`ops/control-center/egress-proxy.service` sets `ProtectHome=true` while
`WorkingDirectory=/home/user/AI-Pipeline` and
`ExecStart=/usr/bin/python3 /home/user/AI-Pipeline/ops/control-center/egress_proxy.py`.
`ProtectHome=true` makes `/home` inaccessible and empty inside the unit's
mount namespace, so both the chdir and the script path fail. Reproduced by
emulating exactly that (a mount namespace with `/home` replaced by an empty
tmpfs):

```
CHDIR-FAILED (systemd: 200/CHDIR)
/usr/bin/python3: can't open file '/home/user/AI-Pipeline/ops/control-center/egress_proxy.py':
  [Errno 2] No such file or directory
```

The sibling `opsdb-broker.service`, edited in this same commit, sets
`ProtectHome=false` with an identical `WorkingDirectory`/`ExecStart` layout —
so the correct value is known and present one file away. This is a
cross-file consistency defect, and it means the B3 egress path, the largest
new piece of this pass, cannot be brought up by following the runbook.
Either `ProtectHome=false` (matching the broker) or `ReadOnlyPaths=` /
`InaccessiblePaths=` shaped so the install dir survives.

(Verified separately and correctly: the intentionally-invalid `User=`
placeholders do fail closed. `systemd-analyze verify` only warns at parse
time, and systemd fails the unit at start with 217/USER — it never silently
falls back to root. B2.3 is genuinely fixed.)

### R3. The timeout backstop does not close the stream, and a kill it cannot perform is silent — the original B2.4 hang survives

The addendum's B2.4 is explicit about the backstop: "add a `PermissionError`
handler to `agent_runtime._kill_process_group()` so the launcher's outer
timer **degrades gracefully (close the stream, record `timed_out`)**". Both
new comments assert this is what happens — `agent_runtime.py`: "the caller
records `timed_out` and closes the stream"; `launch_developer_session.py`'s
`_on_timeout`: "We still record `timed_out` and close the stream so the
outcome is honest even if the outer kill is a no-op."

The code does not close the stream. `_on_timeout` is exactly:

```python
timed_out.set()
agent_runtime._kill_process_group(proc)
```

and `_kill_process_group`'s `PermissionError` branch is a bare `pass` with
no log line of any kind. So when the outer kill is refused — the only
scenario the branch exists for, since the process group holds root-owned
`sudo` and `ai-developer`-owned `bwrap`/`claude` — the launcher stays
blocked in `for line in proc.stdout:` forever. `result["timed_out"]` is set
but nothing reads it until that loop ends, and it never ends. Nothing is
printed, nothing is returned, no `end_session` runs.

That is the failure mode of my original B2.4 verbatim ("nothing dies, the
launcher keeps blocking on stdout, and `timed_out` misreports"), and it is
precisely the case where a timeout that cannot be enforced must be loud
rather than ignored. The inner `timeout --signal=KILL` is a good primary and
will normally fire first — but a backstop that hangs silently when the
primary has already failed is not a backstop. Needed: close/`proc.stdout.close()`
(or otherwise unblock the reader) in `_on_timeout`, and emit a real warning
on the `PermissionError` path rather than swallowing it wordlessly.

## Non-blocking findings (fix with the above)

- **`.claude/agents/developer.md` replaces one overclaim with a smaller one
  in the other direction.** The new text is right about the sandbox, but its
  parenthetical asserts "The hook remains real and active in the ordinary,
  non-sandboxed Task-tool invocation path, **where the trust flag is set**."
  That is false on this host, and this milestone's own monitor says so:
  `python3 ops/control-center/trust_flag_monitor.py` prints `NOT TRUSTED —
  hasTrustDialogAccepted is false or absent`, and `~/.claude.json`'s
  `projects["/home/user/AI-Pipeline"].hasTrustDialogAccepted` is `False`.
  The old wording at least conditioned the claim ("once the trust-flag
  deployment fix ships"). Make it conditional again or drop it.
- **`egress_proxy._read_header_block()` silently discards bytes received
  after the `CRLFCRLF` terminator**, while its own comment says they "are
  handled by the tunnel pump." Verified: sending
  `CONNECT …\r\n\r\nPIPELINED` in one write returns `200` and `DEST-HELLO`,
  and `PIPELINED` never reaches the destination. Harmless for a client that
  waits for the `200` — but whether the real CLI does is exactly the
  still-open verify-against-the-real-binary item, and the failure mode would
  be a stalled TLS handshake that times out after 30s with no diagnostic.
  Split the buffer at the terminator and forward the remainder after
  dialling; it is a few lines.
- **Runbook §6b's prose contradicts its own command.** It says the allowlist
  config is "NOT writable or readable by `ai-developer`" two lines above
  `sudo chmod 0644 /etc/ai-pipeline/egress-allowlist.json`, which is
  world-readable on the host. The security property that matters (not
  bind-mounted, therefore not readable *or widenable from inside the
  sandbox*) does hold and I verified it; the sentence does not.
- **`RuntimeDirectory=ai-pipeline` in both units vs runbook step 5.**
  systemd chowns the runtime directory to each unit's `User=`/`Group=` on
  start and removes it on stop, overriding step 5's manual `chgrp
  ai-pipeline-db` / `chmod 2770`, which step 5 now claims the units "handle
  automatically". Under the runbook's recommended Option A (`Group=` the
  Founder's primary group), `/run/ai-pipeline` becomes `0770
  founder:foundergroup` and `ai-developer` cannot traverse it to reach
  either socket; and stopping either unit deletes the other's socket. Set
  `Group=ai-pipeline-db` on both units and add
  `RuntimeDirectoryPreserve=yes`.
- **`_write_session_files` leaves the session dir's mode to the umask.**
  `session_dir.mkdir(mode=0o750, exist_ok=True)` is masked by the process
  umask (a umask of 077 yields 0700 and reproduces my original B2.2), and
  `exist_ok=True` will not repair a pre-existing wrong mode. The two files
  are explicitly `chmod`ed; the directory should be too.
- **Handoff test-count misreport.** `tests_added` says `test_egress_proxy.py`
  is "15 checks"; it emits 12 (the docstring's own enumeration also sums to
  12). Small, but this project's history makes counts load-bearing — the
  authoritative totals I measured are in the next section.
- **`bwrap` is the one non-absolute binary** in an exec chain where
  `TIMEOUT_BIN`, `PYTHON_BIN`, `RELAY_SCRIPT` and `CLAUDE_BIN` are all
  hardcoded absolute; it depends on sudo's `secure_path`. Make it
  `/usr/bin/bwrap` (with an existence check) for consistency.
- **No `--clearenv`, and `NO_PROXY` is not neutralized.** The sandbox
  inherits whatever sudo's `env_keep` lets through; some distributions keep
  `http_proxy`/`https_proxy`/`no_proxy` by default. `egress_relay.py`
  overrides the four proxy variables in the child but leaves
  `NO_PROXY`/`no_proxy` alone, so an ambient entry could make `claude`
  bypass the relay for that host and fail with an unexplained no-route
  error. Prefer `--clearenv` plus explicit `--setenv`s, and clear
  `NO_PROXY`/`no_proxy` in the relay's child.

## Verified independently — do not re-litigate on resubmission

Everything here was re-run or reproduced by this reviewer, not taken from
the handoff.

**B1 — the two crashes I reported live are genuinely dead.** Against a
broker on a temp-path socket, over a copy of the live DB:
- `{"verb":"activity-log","token":T,"args":{}}` → clean
  `{"ok": false, "error": "activity-log requires a non-empty string
  'summary'"}`; no `sqlite3.IntegrityError` escapes and the daemon serves
  the next request. Same for `""` and for non-string summaries.
- A dict-valued `note` on `task-status` reaches sqlite3 and comes back as
  `_err("Error binding parameter 5: type 'dict' is not supported")` — the
  new `sqlite3.Error` clause catching an `InterfaceError`, exactly as
  intended. Daemon survives.
- 25× close-before-read (the `BrokenPipeError` that killed `serve_forever()`
  in my first review), 25× connect-and-immediately-close, malformed JSON,
  raw binary, and an oversized token: daemon alive throughout, accept thread
  still running.
- Held-open clients (one, one mid-write, five at once) no longer kill the
  daemon; they serialize others for up to the 10s `_CONN_TIMEOUT_S` and then
  service resumes — the tradeoff the addendum explicitly blessed and the
  code documents at `_CONN_TIMEOUT_S`.
- **The 10s timeout does not break legitimate slow work:** a client with a
  6s gap mid-request completed normally; a 12s gap was dropped and the
  daemon stayed up. The socket timeout is per-operation, so a slow DB call
  does not consume the `sendall` budget.

**B3 — the CONNECT-parse robustness contract genuinely holds.** 29
adversarial request lines against a real `EgressProxy` on a temp-path
socket, allowlist `{("localhost", <port>)}`:
- Decision is on the request-line target only, both directions: `Host:
  api.anthropic.com` with a denied request-line target → 403; `Host:
  evil.example.com` with an allowlisted request-line target → 200.
- IP literals refused before the allowlist check, including the raw IP equal
  to the allowlisted host's own resolved address → 403.
- Non-allowlisted port on an allowlisted host → 403.
- Hostname resolved host-side in `_dial`; the sandbox has no resolver, so it
  cannot influence resolution.
- Fail-closed on: `GET`, lowercase/mixed-case `connect`, missing port, port
  `0`, port `65536`, `99999999999999999999`, `0x1bb`, `+443`, non-decimal
  port names, bracketed and unbracketed IPv6, double space, tab in target,
  absolute-URI and `user@host` forms, leading whitespace, empty first line,
  bare-LF request smuggling, non-ASCII and NUL bytes, `HTTP/2.0`, missing
  version, trailing junk. Decimal- and octal-style IP encodings are denied by
  the hostname-exact allowlist.
- Short read (request line, no `CRLFCRLF`, then close) → `400`, not a guess.
  128 KB with no newline → `400` immediately (`_MAX_HEADER_BYTES` ceiling),
  no memory growth. 32 KB request line with a terminator → `400`.
- Leading-zero (`0<port>`) and uppercase-hostname forms are accepted and are
  *not* bypasses: they normalise to the same allowlisted destination and the
  proxy re-emits the parsed integer port upstream.
- The proxy stayed alive through every case and through 20× close-before-read
  and 20× abrupt close; thread-per-connection means a held-open client does
  not wedge it.

**B3 — the trust boundary is where it is claimed to be.** The allowlist
config is host-owned and never bind-mounted, so it is un-widenable from
inside (subject to R1's `/etc` caveat above). `egress_relay.py` is genuinely
untrusted-but-harmless: it parses nothing, connects only to
`EGRESS_UNIX_SOCKET`, and there is nothing else in the namespace to reach —
I confirmed in a live sandbox that the deny decision for
`evil.example.com:443` is made in the host-side proxy (it appears in the
proxy's own stderr log) and that a direct external connect fails with no
route. Subverting or replacing the relay gains nothing.

**B2 — three of four mechanisms compose correctly.** Token as a `0640` file
read by the wrapper (`$(<file)`) rather than an env var; prompt and token in
a session dir inside the group-shared worktree (setgid inheritance gives
them `ai-pipeline-dev`); `opsdb-broker.service` fail-closed `User=`
placeholders with Option A/B guidance that matches
`_default_trusted_uids()`. The runbook's sudoers line
(`NOPASSWD:SETENV:` on the exact wrapper path) matches what the launcher
actually issues (`--preserve-env=OPSDB_BROKER_SOCKET,OPSDB_EGRESS_SOCKET`)
— `SETENV:` is required for `--preserve-env` and is present. Wrapper
argument validation (argc, non-integer and `<1` wallclock, missing worktree/
prompt/token, dead sockets) all behaves correctly when exercised. The fourth
mechanism is R3.

**B4 — the correction is real.** No trust-flag seed anywhere in the wrapper,
launcher or runbook; `CLAUDE_CONFIG_DIR` still points at the ephemeral
tmpfs and the wrapper documents why that is intended; `trust_flag_monitor.py`
is scoped to `("qa", "cto", "devops")`. The sandbox half of the new
`developer.md` wording is accurate — only the parenthetical about the
non-sandboxed path overclaims (see non-blocking, above).

**Non-blocking items from my first review — all four done.** Exhaustive
exclusion derived from `opsdb.py`'s own source (29 `add_parser` names − 5
allowed = 24 excluded, matching the architecture's list exactly, and it will
catch future drift); the tautological sanity loop replaced by an exact
5-tuple assertion; `opsdb_broker.send_request` reused instead of a third
wire client (`_send_and_abandon` is a deliberate, documented exception);
broker-mode `task-status` now prints the broker's own authoritative values
with `(none)` instead of a literal `None`; `trust_flag_monitor` narrowed to
`except Exception`.

**Test suites — run by this reviewer, actual counts.** All 8 pass, 183
checks total: `test_opsdb_broker.py` 65, `test_egress_proxy.py` 12,
`hooks/test_developer_pretooluse.py` 14, `test_trust_flag_monitor.py` 8,
and the four pre-existing suites unmodified with `OPSDB_BROKER_SOCKET`
unset — `test_cost_tracking.py` 22, `test_gates_remaining.py` 34,
`test_phase_progress.py` 17, `test_risk_register.py` 11. Zero failures.
`bash -n` and `py_compile` clean on every changed file.

**Hard constraint honored.** `id ai-developer` → no such user; `getent group
ai-pipeline-dev ai-pipeline-db ai-pipeline-broker ai-pipeline-egress` →
empty; `/etc/sudoers.d/` contains only `README`; `/run/ai-pipeline` and
`/etc/ai-pipeline` do not exist; no `opsdb_broker`/`egress_proxy`/
`egress_relay` process running; no unit installed in
`/etc/systemd/system/`. All of my testing used throwaway processes on
temp-path sockets and a copy of the database.

**No scope creep.** The changed-file list is exactly the handoff's 14 files.
`developer.md`'s `tools:`/`hooks:` frontmatter is untouched and Developer's
default Task-tool invocation path is unchanged — `launch_developer_session.py`
remains deliberately unwired.

## What happens on resubmission

R1 and R2 are reproducible with the commands quoted above and should be
re-verified by actually exec'ing something inside the sandbox with the real
wrapper (a stub `claude` is enough — that is how the working end-to-end
result in R1 was obtained). R2 is a one-line unit-file change plus a
runbook note. R3 needs the stream actually closed and the swallowed
`PermissionError` made audible. The non-blocking items are all small and
should ship together. This review will re-verify each, and will re-run the
adversarial CONNECT and broker reproductions to confirm none of the fixes
regressed what is already correct.
