# Code Review round 3 — TASK-023 (risks.id=3 durable closure: OS-level sandboxing for Developer)

Reviewer: code-review. Scope: `handoffs.id=15`, commit range `10126cb..a0238ea`
(10 files). Baselines read in full: my own two prior REJECTs
(`ops/reviews/code-review-task023.md` B1–B4,
`ops/reviews/code-review-task023-reverification.md` R1–R3 + 8 non-blocking),
`ops/reviews/cto-task023-architecture.md` including both the Correction and
the B3 Addendum, and `ops/reviews/red-team-task023-addendum-review.md`
(verified property #5).

**Verdict: REJECT — returned to Developer (IN_DEVELOPMENT).**

R1, R2, R3 and all 8 non-blocking items are genuinely fixed. I re-derived
every claim in the handoff rather than trusting it, and every number in it
is accurate — including the 184-check total and the `claude --version`
result. The `/etc` handling is the right shape and Red Team's property #5
survives with the allowlist file actually present on the host, which I
created and removed myself.

It is nevertheless a REJECT, and for the third time for the same underlying
reason: **the launch path still cannot function on first real use, and this
time I proved it by running the real `claude` binary through the real
wrapper — which is exactly what my previous review asked for and what
Development stopped one step short of doing.** Development's chain
verification used a *stub* `claude` (which accepts any argv) and ran the
real binary only for `--version` (which needs neither valid flags nor
credentials). With R1's bind set now fixed, the chain reaches the real CLI
for the first time in this milestone's history — and the real CLI rejects
the wrapper's own argv and then cannot authenticate.

One of the two findings below (C1) is pre-existing and my first review
explicitly blessed the flag set that contains it. That was wrong; stated
plainly here rather than presented as new, the same way I handled R1.

## Blocking findings

### C1. The shipped `claude` argv is invalid — every launch exits 1 before any work (reproduced, twice)

`launch_developer_sandboxed.sh`'s exec line passes
`--output-format stream-json` with no `--verbose`. The installed CLI
(2.1.252) refuses that combination in `-p`/print mode:

```
$ bash <shipped wrapper, byte-identical> <worktree> <prompt> <token> 150
Error: When using --print, --output-format=stream-json requires --verbose
$ echo $?
1
```

Reproduced two independent ways: through the real wrapper under real bwrap
with the real binary, and directly on the bare host with no sandbox at all —

```
$ env -i HOME=/tmp PATH=/usr/bin:/bin /opt/claude-code/bin/claude \
    --agent developer --tools "Read" --output-format stream-json \
    --max-budget-usd 5.00 -p "hi"
Error: When using --print, --output-format=stream-json requires --verbose
```

so no provisioning, no sandbox and no account are needed to find it. It is
deterministic, it fires before any model call, and it makes every real
sandboxed Developer session do zero work.

`agent_runtime.py` — the established convention the wrapper's flags were
justified against in my first review — uses `--output-format json`, which
has no such requirement. The wrapper deviates to `stream-json` (correctly,
per §4.1 step 4's live-streaming requirement) but without the `--verbose`
the CLI demands for it.

Adding `--verbose` alone, in a scratch copy, makes the CLI start correctly:
it emits a proper `{"type":"system","subtype":"init"...}` event with
`"tools":["Read","Edit","Write","Bash","Grep","Glob","Skill"]`, the
`developer` agent resolved, cwd = the worktree. So the fix is one token —
but it must be *verified against the real binary*, and the launcher's
stdout consumer must be checked against what `stream-json --verbose`
actually emits, not assumed.

**Honest correction:** my first review said "`--tools`/`--output-format`/
`--max-budget-usd` match `agent_runtime.py`'s established CLI usage." Two of
the three do; `--output-format` does not, and I never ran the real binary
with these flags. That check is what this finding is.

### C2. With C1 patched, the sandboxed real CLI cannot authenticate — and the cause is the bind set, not the network

With `--verbose` added and nothing else changed, the real CLI runs inside
the real sandbox and immediately returns:

```
"terminal_reason":"api_error", "result":"Not logged in · Please run /login"
```

exit 1, and **zero connections reached the egress proxy** (its log shows no
CONNECT at all) — so the B3 carve-out is never even exercised.

This is not a network or provisioning artifact, and I did not stop at
assuming it was. Isolated live:

- Same narrow bind set, but with the network **shared** (no
  `--unshare-net`): still `Not logged in`. So it is not the netns.
- `--ro-bind / /`, `--clearenv`, `HOME=/tmp`,
  `CLAUDE_CONFIG_DIR=/tmp/claude-config`, no network change: **works**. So
  it is not the cleared environment, not `HOME`, and not the ephemeral
  config dir.
- Bisecting that working case by masking one tree at a time: masking
  `/var`, `/run`, `/root` or `/home/user` — still works. Masking `/home`,
  `/home/claude`, or `/home/claude/.claude` — `Not logged in`.

So on this host the CLI's credential material lives at a filesystem path
under `/home/claude/.claude/` that the wrapper's bind set (deliberately and
correctly) excludes. That location is specific to this hosting container,
so I am explicitly **not** prescribing "bind it" — a read-only bind of
another account's credential store into a sandbox whose entire purpose is
keeping Founder-only material out of `ai-developer`'s reach is exactly the
kind of unilateral widening the architecture forbids, and the production
answer for a provisioned `ai-developer` account will be different anyway.

What this pass must not do is ship a launch path that structurally does no
work while disclosing something else. `known_limitations` names the
"CLI-vs-relay `HTTPS_PROXY`" item and the TLS/CA question; it does **not**
name credential delivery into the sandbox, which is the thing that actually
fails first, before either of those can be reached. Required, pick one:

1. a named mechanism in the wrapper + runbook (an `ai-developer`-owned
   credential file bound read-only, an API key delivered as data the way the
   broker token already is, or equivalent) — this is new security-relevant
   surface and should be routed past CTO/Red Team, not invented in code; or
2. an explicit, CTO-acknowledged disclosure in `known_limitations`, the
   runbook, and the §7 QA charter that credential provisioning for
   `ai-developer` is an unsolved prerequisite of cutover — stated, not
   silent.

Either way the handoff must stop implying the only open real-binary
question is `HTTPS_PROXY` behaviour.

## Verified fixed — do not re-litigate on resubmission

Everything below was re-run or re-derived by me, with throwaway processes
only.

**R1 — the sandbox execs, for real.** From the wrapper's own emitted argv
(dumped from a byte-identical scratch copy of the shipped script, not
hand-written):

- `bwrap … -- /usr/bin/timeout --signal=KILL 5 /usr/bin/echo hello` → `hello`,
  exit 0.
- `… /usr/bin/python3 -c 'print("py-ok")'` → `py-ok`, exit 0 (the
  `/etc/alternatives` bind doing its job for PATH-resolved `python3`).
- `… /opt/claude-code/bin/claude --version` → `2.1.252 (Claude Code)`,
  exit 0 — Development's claim, reproduced.
- The runbook's new step-5 hand-run check, pasted verbatim: same result,
  exit 0.

**Red Team property #5 holds with the file actually present.** I created
`/etc/ai-pipeline/egress-allowlist.json` (0644 root) on the host, then from
inside the real bind set: `/etc/ai-pipeline` → `exists=False`,
`/etc/ai-pipeline/egress-allowlist.json` → `exists=False`,
`os.listdir("/etc")` → exactly `['alternatives','group','passwd','ssl']`.
Also confirmed in the same run: `/etc/shadow` absent, `/etc/sudoers` absent,
`/etc/ssl/certs` present with 305 certs, `operations.sqlite3` absent,
`.founder_credential.json` absent, `/home/user` absent. Host artifact
removed immediately afterwards; `/etc/ai-pipeline` does not exist now.

**The `EGRESS_ALLOWLIST_DIR` guard actually fires.** Editing the enumerated
list to include `/etc` → exit 1 with the intended message; editing it to
include `/etc/ai-pipeline` itself → exit 1 as well (the trailing-slash
`case` pattern matches the empty remainder correctly). It is a real guard,
not a comment.

**The `readlink`-emitted `--symlink` approach is correct and robust enough.**
On this host it emits `--symlink usr/bin /bin`, `usr/sbin /sbin`,
`usr/lib /lib`, `usr/lib64 /lib64` (no `/lib32`, `/libx32`, both absent). A
relative target is re-created verbatim and resolves inside; an absolute
target (`/usr/bin`) would also resolve, since `/usr` is bound; a nested
symlink resolves within the bound tree; a dangling host symlink stays
dangling inside, i.e. degrades exactly as the host does, with no new
failure mode. Crucially, the wrapper's own exec chain never depends on any
of them — `TIMEOUT_BIN`/`PYTHON_BIN` are absolute real paths — so a
pathological host layout costs Developer's convenience, not the launch.

**The `/usr`-resolution guard is enforced and not meaningfully bypassable.**
`readlink -f` canonicalises, so no `..` or symlink trick reaches the `case`
with a path that later resolves elsewhere; `-z`/`-x` checks precede it; a
resolution outside `/usr` exits 1 rather than silently widening the bind
set. This is a host-layout sanity check rather than a security boundary,
which is the right role for it and what the comment claims.

**The argv-ordering fix is correct.** `--clearenv` precedes every
`--setenv`; `--proc`/`--dev`/`--tmpfs /tmp` precede every bind. I verified
the consequence directly: with a worktree, prompt file, token file and both
sockets living under `/tmp`, all of them are visible and usable inside the
sandbox and `os.listdir("/tmp")` shows the bind's own path — the exact
shadowing Development self-reported is gone. Nothing else in the emitted
argv is order-sensitive: `--chdir` is applied after namespace setup
regardless of position, and no two binds overlap.

**R2 — the units are consistent and neither runs as root.** Emulating
`ProtectSystem=strict` + `ProtectHome=false` (read-only `/home`): chdir to
`/home/user/AI-Pipeline` succeeds, `egress_proxy.py` is readable and parses,
and a write under `/home` is refused `Read-only file system` — the property
the comment claims. The `ProtectHome=true` control still reproduces
`CHDIR-FAILED (200/CHDIR)` and `can't open file …egress_proxy.py`. Both
units now carry `User=` placeholders that fail closed (217/USER, unchanged
from round 2), `Group=ai-pipeline-db`, `RuntimeDirectoryPreserve=yes`,
`ProtectSystem=strict`, `NoNewPrivileges=true`, `ProtectHome=false`. The
runbook's step 5 and step 6 text now match the units.

**R3 — reproduced end to end, and the normal path is unharmed.** Driving
`run_sandboxed_developer_session` with `os.killpg` patched to raise
`PermissionError` and a child that never dies:

```
elapsed_s = 13.0
ok=False  returncode=None  timed_out=True  kill_refused=True  abandoned=True
error = "…exceeded 3s and could NOT be killed by this launcher (cross-UID kill
         refused); its output stream was abandoned…"
```

both warnings printed to stderr, `end_session` called, session dir removed.
Development's 13.1s claim reproduced at 13.0s. The original hang is gone.

The read-loop rewrite does not damage the normal path:
- **No lost or duplicated output.** 200,000 lines / 11,000,000 bytes from a
  child that exits: byte-for-byte identical to the expected stream,
  `ok=True`, `returncode=0`, no partial lines.
- **No busy loop.** A child silent for 6s then exiting: 0.00s of launcher
  CPU across the whole call.
- **The kill-succeeds path still behaves.** Real `killpg`, child that never
  exits: `timed_out=True`, `kill_refused=False`, `abandoned=False`,
  `returncode=-9`, returned at 3.0s (no 5s drain penalty, because EOF
  arrives immediately).

**Both previously-false comments are now accurate.** `agent_runtime.py` no
longer claims the caller "closes the stream" (it doesn't, deliberately, and
the docstring now says why); `_on_timeout` no longer claims to close it
either and explains the buffered-stream/lock reasoning. The stated reason
for abandoning `for line in proc.stdout` is sound.

**`_kill_process_group()`'s new `bool` is handled by every caller.** There
are exactly two: `agent_runtime._run_claude` (line 327, ignores it — safe,
same-UID children, and the docstring says so) and
`launch_developer_session._on_timeout` (uses it). No other call site exists
in the repo.

**All 8 non-blocking items from round 2 are done, and correctly.**
1. `developer.md` — every claim now verifiable on this host:
   `trust_flag_monitor.py` prints `NOT TRUSTED — hasTrustDialogAccepted is
   false or absent` (verbatim match, exit 1), and
   `~/.claude.json` `projects["/home/user/AI-Pipeline"]
   .hasTrustDialogAccepted` is `False`. The claim is correctly scoped ("on
   THIS host", "until the separate trust-flag deployment fix ships") and the
   hook is truthfully described as live in neither mode. No third
   inaccuracy. `tools:`/`hooks:` frontmatter untouched.
2. `_read_header_block` → `(header, leftover)`: **no byte is dropped or
   duplicated in either direction.** Verified against a real proxy with a
   fake upstream that coalesces its `200` with payload: upstream-early
   delivered exactly once, `200` exactly once; a pipelined client
   `CLIENTHELLO` echoed exactly once; a 4 KB pipelined payload (realistic
   ClientHello size) forwarded in full; a terminator split across three
   writes still parses and tunnels.
3. Runbook §6b prose now matches its own `chmod 0644` and states the real
   property (not bind-mounted ⇒ not readable or widenable from inside).
4. `Group=ai-pipeline-db` + `RuntimeDirectoryPreserve=yes` on both units,
   with runbook step 5/6 updated to match.
5. `_write_session_files` now `chmod`s the directory: under `umask 077` it
   is `0750` (was `0700`), files `0640`, and a pre-existing `0700` directory
   is repaired.
6. Test-count claim is now exact and true (13, see below).
7. `BWRAP_BIN=/usr/bin/bwrap` with an existence check; `CLAUDE_BIN` also
   gains an `-x` check.
8. `--clearenv` + explicit `--setenv PATH/LANG/TERM`, and the relay pops
   `NO_PROXY`/`no_proxy`/`ALL_PROXY`/`all_proxy`.

**No regression in what round 2 already blessed.** `opsdb_broker.py` is not
in this diff at all, so B1 cannot have regressed. `egress_proxy.py`'s
CONNECT decision path (`parse_connect_target`, the IP-literal check, the
allowlist match) is untouched; I spot-re-ran the contract against a live
proxy anyway: Host-spoof with a denied request-line target → 403; raw IP
literal → 403; short read → 400; 16 KB-ceiling flood → 400; and the daemon
served a normal CONNECT afterwards.

**Test suites — run by me, actual counts.** All 8 pass, **184 checks**,
zero failures, matching Development's claim exactly:
`test_opsdb_broker.py` 65, `test_egress_proxy.py` 13,
`hooks/test_developer_pretooluse.py` 14, `test_trust_flag_monitor.py` 8,
`test_cost_tracking.py` 22, `test_gates_remaining.py` 34,
`test_phase_progress.py` 17, `test_risk_register.py` 11. The four
pre-existing `ops/db/test_*.py` suites are unmodified and pass with
`OPSDB_BROKER_SOCKET` unset; I also confirmed re-running them leaves
`ops/db/operations.sqlite3` byte-identical. `bash -n` and `py_compile` clean
on every changed file.

**Hard constraint honored, and nothing left behind.** `id ai-developer` →
no such user; no `ai-pipeline-dev`/`-db`/`-broker`/`-egress` groups;
`/etc/sudoers.d/` contains only `README`; `/run/ai-pipeline` and
`/etc/ai-pipeline` do not exist; no unit in `/etc/systemd/system/`; no
`opsdb_broker`/`egress_proxy`/`egress_relay`/`bwrap` process running. All of
my own testing used throwaway sockets under the session scratchpad and was
cleaned up.

**No scope creep.** Exactly the 10 files in the handoff's `files_changed`.
`launch_developer_session.py` is still referenced only from comments and
docs — Developer's default Task-tool invocation path is untouched.

## Non-blocking findings (fix with the above)

- **`abandoned` mislabels a non-timeout stream failure.**
  `_stream_process_output` also returns `False` when `select`/`os.read`
  raises `OSError`/`ValueError` without any timeout, and the caller then
  emits `"exceeded {timeout}s and could NOT be killed by this launcher
  (cross-UID kill refused)"` — which would be false. Gate that message on
  `timed_out.is_set()` and give the read-error case its own text.
- **`_read_header_block`'s "Never discard them" is stronger than the code.**
  A client that pipelines more than `_MAX_HEADER_BYTES` (16 KB) in the same
  burst as the CONNECT gets the whole connection rejected `400`, because the
  ceiling check runs after the extend regardless of whether the terminator
  already arrived. Verified: 4 KB pipelined → forwarded in full; 50 KB →
  `400` with a log line. That is fail-closed and audible, so it is fine
  behaviour — but the docstring should say "up to the header ceiling".
- **`agent_runtime._run_claude` would hang if its own kill were ever
  refused.** It ignores the new `bool` and then calls `proc.communicate()`
  to reap. Unreachable today (same-UID children) and unchanged by this diff,
  but now that the refusal case is a real, returned value one line away, a
  comment naming why that caller can ignore it belongs there.
- **`_stream_process_output` requires `sys.stdout.buffer`.** Fine for the
  real CLI path; it would `AttributeError` under a test harness that
  replaces `sys.stdout` with a text-only object. A `getattr(sys.stdout,
  "buffer", None)` fallback is two lines.
- **`CLAUDE_BIN` is not held to the same standard as `TIMEOUT_BIN`/
  `PYTHON_BIN`.** It gets an `-x` check but no `readlink -f` and no
  "resolves under a bound tree" guard, so a `/opt/claude-code/bin/claude`
  that is a symlink out of the bound directory would fail inside the sandbox
  with a bare `No such file or directory`. Same three lines as the other two.
- **Runbook Option B does not say how `ai-pipeline-broker` gets read/write
  on `ops/db/operations.sqlite3`** (nor on its directory, which SQLite needs
  for `-wal`/`-journal`). Pre-existing, not introduced here, but a human
  following Option B will stop at exactly that point.

## What happens on resubmission

C1 is a one-token change that must be confirmed by running the real binary
through the real wrapper — a stub `claude` cannot catch it, which is the
whole lesson of this round. C2 needs either a named, reviewed mechanism or
an explicit disclosure; if the disclosure route is taken, the handoff and
runbook must say plainly that a real sandboxed session cannot authenticate
today. Both, plus the six non-blocking items, should ship together. I will
re-verify each, re-run the 8 suites, and re-run the real-binary chain.
