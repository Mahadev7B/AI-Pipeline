# Code Review — TASK-023 (risks.id=3 durable closure: OS-level sandboxing for Developer)

Reviewer: code-review. Scope: handoffs.id=13, commit range `3121d13..c378ec7`
(cumulative diff reviewed; intermediate WIP snapshot `371aa21` noted).
Architecture baseline: `ops/reviews/cto-task023-architecture.md` (read in full,
including the Correction section after §3, §4, §5, §7) and
`ops/reviews/red-team-task023-reverification.md`.

**Verdict: REJECT — returned to Developer (IN_DEVELOPMENT).**

The allowlist/session-binding/identity-injection core of the broker is
correct and well-tested, the hook fixes are genuinely correct, the
zero-behavior-change claim for `opsdb.py` is verified, and the hard
no-provisioning constraint was honored. But the broker daemon — the
load-bearing security artifact of this milestone — is trivially crashable
and wedgeable by exactly the untrusted principal it exists to contain
(empirically confirmed during this review, not inferred), and the launch
path contains four independent, statically-determinable defects, any one of
which makes the first real launch fail. These are fixable now, in code and
runbook, without waiting for OS provisioning — that is what this REJECT
asks for.

## Verified independently (do not re-litigate on resubmission)

- **Hard constraint honored.** `id ai-developer` → no such user; `getent
  group ai-pipeline-dev ai-pipeline-db` → empty; `/etc/sudoers.d/` contains
  only `README`; no `/run/ai-pipeline`; no running `opsdb_broker` process.
- **All 4 pre-existing `ops/db/test_*.py` suites re-run by this reviewer:
  all pass** (`test_cost_tracking`, `test_gates_remaining`,
  `test_phase_progress`, `test_risk_register`), with `OPSDB_BROKER_SOCKET`
  unset — the handoff's zero-behavior-change claim is verified, not trusted.
  The `opsdb.py` refactors (`record_handoff`, `set_task_step_status`,
  `task_step_owner`, `compute_task_progress`, `record_activity`) preserve
  the CLI's messages and error contracts on the non-broker path.
- **All 3 new test files run: all pass** (`test_opsdb_broker.py`,
  `test_developer_pretooluse.py`, `test_trust_flag_monitor.py`).
- **BACKLOG drop verified against the live DB.** The single
  `developer`/`BACKLOG` row (`task_status_history.id=117`) is
  `from_status=NULL, note='created'` — `cmd_task_create`'s side-effect
  signature, exactly as Red Team's re-verification found. I agree with the
  drop; the docstring's documentation trail is exemplary.
- **Hook fixes are correct.** `strace -p 1`/`gdb -p 1` as first token now
  denied (token + basename match, so `/usr/bin/gdb` is caught too); the
  50,000-char ceiling denies before any parsing, and the test's timing
  check confirms the pathological shlex input returns in <2s. No
  false-positive on substring-bearing tokens. `bash -n` and `py_compile`
  clean on all new files.
- **The `/opt/claude-code` deviation is blessed.** `readlink -f $(which
  claude)` → `/opt/claude-code/bin/claude`, confirmed; the directory
  contains only `bin/claude` (+ `lost+found`); `/bin`,`/lib`,`/lib64` are
  symlinks into `/usr`, so the conditional real-bind loop is correct. A
  narrow read-only bind of the CLI install dir is the obviously-necessary
  minimal addition, no new exposure worth flagging.
- **No scope creep.** Exactly the §7 file list plus tests/runbook/unit;
  Developer's default Task-tool invocation path untouched; `developer.md`
  change is additive only, `tools:`/`hooks:` frontmatter untouched.
- **`--tools`/`--output-format`/`--max-budget-usd` match `agent_runtime.py`'s
  established CLI usage.**

## Blocking findings

### B1. The broker daemon is crashable and wedgeable by its untrusted client (empirically confirmed)

`opsdb_broker.py`'s own comment claims "a malformed request can never crash
this always-running daemon process." That is false, three ways, and I
reproduced two of them live against a real socket during this review:

1. **Uncaught database exceptions.** `handle_request()` catches only
   `(LookupError, ValueError, SystemExit)`. A schema-valid verb with
   schema-invalid content raises `sqlite3` exceptions straight through:
   confirmed — `{"verb":"activity-log","token":T,"args":{}}` →
   `sqlite3.IntegrityError: NOT NULL constraint failed:
   agent_activity.summary` escapes `handle_request`, which in daemon
   context kills `serve_forever()`. Non-string arg types
   (`InterfaceError`) and `database is locked` past the busy timeout
   (`OperationalError`) take the same path.
2. **Uncaught socket errors.** `_handle_connection()` has no try/except
   around `conn.sendall()`. Confirmed live: a client that sends a request
   and closes without reading the response produced
   `BrokenPipeError` at `opsdb_broker.py:363`, the accept loop died, and
   the next connection got `ConnectionRefusedError`. The sandboxed
   Developer process — the untrusted principal — can kill the broker with
   one line of Python.
3. **No socket timeout.** `_recv_request()` blocks on `conn.recv()` with
   no `settimeout()` in a single-threaded accept loop. A client that
   connects and holds the connection open (or never calls
   `shutdown(SHUT_WR)`) wedges the broker for every caller — including the
   launcher's own `register_session`.

Compounding consequence: `_sessions` is in-memory only, so the
systemd `Restart=on-failure` recovery from (1)/(2) silently invalidates the
live session's token mid-run — every subsequent `opsdb.py` call from the
still-running sandbox fails "invalid or unknown session token". These are
exactly the shapes the adversarial Security review will probe first.

**Fix shape:** per-connection `try/except OSError` + `conn.settimeout()`;
broaden the handler's catch to include `sqlite3.Error` (returning
`_err(...)`, never propagating); validate required arg types/presence
(`summary` string, etc.) before touching the DB. Single-threadedness itself
may stay (documented), but a single bad connection must cost one
connection, never the daemon.

### B2. The launch path fails on first real use — four independent, statically-determinable defects

All four are in code/config this pass could have gotten right without any
OS provisioning; "not executed end-to-end" is disclosed, but none of these
need execution to find:

1. **sudo strips the broker env.** `launch_developer_session.py` passes
   `OPSDB_BROKER_SOCKET`/`OPSDB_BROKER_TOKEN` via `Popen(env=...)`, but the
   command is `sudo -u ai-developer ...` with no `--preserve-env`, and the
   runbook's sudoers line (§3) has no `SETENV:` tag and no `env_keep`.
   sudo's default `env_reset` scrubs both variables; the wrapper's own
   guard (`OPSDB_BROKER_TOKEN is not set`) then exits 1 on every launch.
2. **The prompt file is unreadable by `ai-developer`.**
   `tempfile.mkdtemp()` creates a mode-0700 directory owned by the
   launcher's user; the wrapper (as `ai-developer`) cannot traverse it, so
   `[ -f "$PROMPT_FILE_PATH" ]` fails, always. The code's own comment
   half-acknowledges the problem then ships the broken default anyway. Fix
   in code (chgrp/chmod the scratch dir, or write the prompt inside the
   bind-mounted worktree) — not in prose.
3. **`opsdb-broker.service` runs the broker as root.** No `User=` is set
   (system units default to root), directly contradicting the unit's own
   comment ("Runs as the Founder's own account by default") and the
   architecture's "never as ai-developer, Founder's user or
   ai-pipeline-broker" instruction — and it breaks registration:
   `_default_trusted_uids()` becomes `{0}`, so the Founder-run launcher's
   `register_session` is refused via SO_PEERCRED on every launch. Least
   privilege and functionality both fail.
4. **The wall-clock timeout cannot kill the session.**
   `agent_runtime._kill_process_group()` catches only
   `ProcessLookupError`; `os.killpg` from the Founder's UID against a
   process group containing root-owned `sudo` and `ai-developer`-owned
   `bwrap`/`claude` raises `PermissionError`, uncaught, in the timer
   thread — nothing dies, the launcher keeps blocking on stdout, and
   `timed_out` misreports. Needs a privileged kill path (e.g. terminate
   the sudo child and rely on `--die-with-parent`, or `sudo -u ai-developer
   kill`) plus a `PermissionError` handler.

### B3. `--unshare-all` leaves the sandboxed `claude` CLI no path to the model API — flag to CTO/Red Team, do not silently "fix"

The architecture's "no network by default" (§2.3) was validated only with
`/bin/echo`/`/bin/sh`/`curl` (§1's spike never exec'd `claude` itself). The
wrapper binds no network, no proxy socket, nothing but the opsdb socket —
so the sandboxed CLI's first API call fails and every real session dies
having done no work. This is faithful to the letter of the architecture,
so it is not a Development defect in the same sense as B1/B2 — but the
handoff's known_limitations does not name it, and a launch path that
structurally cannot function must not pass review. Required: name it
explicitly and take it back to CTO/Red Team for the narrow carve-out
decision (host-side API proxy over a bind-mounted Unix socket would
preserve the no-general-egress policy). Do not widen the sandbox
unilaterally.

### B4. The trust-flag deployment fix (§5 point 1) is absent, and the ephemeral config dir makes it structurally impossible as designed

§5 point 1 is explicit: without the trust-flag fix "the hook layer ... is
inert" in the new `-p`-mode invocation path, and it "must ship in the same
pass." §7 item 8 lists "the one-time trust-flag write for the fixed
launcher path" as required deployment config. What shipped: the
*generalized monitor* for qa/cto/devops (§5 point 4 — good, correct,
tested) — but no trust-flag write step anywhere in the runbook, and the
wrapper sets `CLAUDE_CONFIG_DIR=/tmp/claude-config` on a tmpfs that starts
empty every session, so `hasTrustDialogAccepted` can never be true inside
the sandbox and `developer_pretooluse.py` silently never fires there. The
defense-in-depth layer the persona note promises ("both are real") is
inert in every sandboxed session, with no runbook step that could fix it.
Required: seed the trust entry into the sandbox-local config at launch
(wrapper or launcher), or bind a prepared read-only config — plus the
matching runbook step — or an explicit, CTO-acknowledged disclosure that
sandboxed sessions run hook-less by design.

## Non-blocking findings (fix with the above)

- `ops/db/test_opsdb_broker.py` tests 13 of the 24 excluded verbs, not all
  24 — the handoff's "sample of all 24" phrasing notwithstanding, the
  architecture's whole Correction section is about exhaustiveness. Derive
  the exclusion list (all `sub.add_parser` names minus `ALLOWED_VERBS`) and
  assert rejection for every one, so the test also catches future drift.
  Also: the "is in ALLOWED_VERBS (sanity)" loop iterates `ALLOWED_VERBS`
  checking membership in itself — tautological, delete or replace with an
  assertion of the exact expected 5-tuple.
- `test_opsdb_broker.py:_socket_call()` re-implements
  `opsdb_broker.send_request()` line for line — the third copy of the wire
  client, in the same commit whose `send_request` docstring says it exists
  so the client is "not reimplemented a third time". Use `send_request`.
- Broker-mode `cmd_task_status` prints the client-supplied `--task-id`
  (which the broker ignores) and prints literal `None` when `from_status`
  is null (`result.get('from_status', '?')` — the key exists). Print the
  broker's authoritative task/values instead.
- `trust_flag_monitor._best_effort_log_alert()`'s `except BaseException:
  pass` swallows `KeyboardInterrupt`/`SystemExit`; `except Exception` is
  the right breadth for best-effort logging.
- Very large prompts pass through `-p "$PROMPT_TEXT"` as a single argv
  element — fine today, but ARG_MAX-bounded; consider `-p "$(cat ...)"`→
  stdin if transcripts grow.

## What happens on resubmission

B1 is verifiable with the same in-process/socket reproductions used here
(add them to `test_opsdb_broker.py`). B2.1–B2.4 are verifiable statically
plus by unit tests (no provisioning needed). B3/B4 need either code+runbook
changes or explicit CTO/Red Team-bound disclosures in the handoff — not
silence. Prior findings must all be addressed or explicitly answered; this
review will re-verify each.
