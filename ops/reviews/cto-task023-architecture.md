# CTO architecture — TASK-023: risks.id=3 durable closure (OS-level/process-separation sandboxing for Developer)

Architecture and investigation only, per this project's convention (design
first, review, then Development — nothing in this document has been
implemented in product code). Builds directly on
`ops/reviews/cto-risk3-architecture-investigation.md` (§3.1–3.8, read in
full) and `ops/reviews/cto-risk3-hook-invocation-investigation.md`, under
the Founder's explicit mandate at DEC-011 (`decisions.id=14`): pursue real
OS-level/process-separation sandboxing for Developer "(and any other role
the scoping finds warrants it)," rather than accept the narrowed,
non-adversarial-only Developer-denylist protection. Red Team review is a
required, non-skippable gate on this milestone per the Founder's explicit
instruction — nothing in this document should be read as a recommendation
to shortcut that, and it does not.

## 0. What this document decides

1. A concrete sandboxing shape for Developer (§1–§2).
2. A concrete control for the `operations.sqlite3` bind-mount gap my own
   prior investigation flagged and did not solve (§3).
3. Exactly how supervised invocation changes, and why only Developer is in
   scope (§4).
4. A real feasibility result for this hosting environment, tested directly,
   not assumed (§1).
5. Whether TASK-017's remaining cheap fixes fold into this milestone or ship
   separately (§5).
6. What this architecture closes and does not close (§6).
7. A file-level implementation and sequencing plan (§7).

## 1. Feasibility spike — tested directly in this environment, not assumed

My own prior investigation (§3.7) flagged, honestly, that "unprivileged
user-namespace creation may be restricted by kernel configuration on the
actual host this runs on — this needs a feasibility spike before being
taken further." That spike is done. Results, run directly in this
environment (`/home/user/AI-Pipeline`, live host, not a synthetic
description):

**Kernel toggle files.** `/proc/sys/kernel/unprivileged_userns_clone` and
`/proc/sys/kernel/apparmor_restrict_unprivileged_userns` do not exist on
this kernel. Absence of these specific files is not itself proof of
anything (different distros expose the same control differently) — so this
alone was not treated as the answer; the actual behavioral test below is
the real evidence.

**`unshare`/namespace test.** A first, naive attempt
(`unshare --user --pid --mount-proc echo ok`) failed with `mount /proc
failed: Operation not permitted`. Root-caused, not left unexplained: this
is a known `unshare` usage detail (`--mount-proc` needs the calling process
to actually be PID 1 of the new namespace, which requires `--fork`), not a
kernel/userns restriction. Re-run with `--fork` succeeded cleanly:
`unshare --user --map-root-user --mount --pid --fork /bin/sh -c 'mount -t
proc proc /proc && echo mount-ok'` → `mount-ok`, exit 0.

**Bubblewrap, the actual mechanism §3.7 proposed.** Not present in this
environment by default; installed via `apt-get install -y bubblewrap`
(`bubblewrap 0.9.0-1ubuntu0.1`, candidate already in the apt cache — no
custom build needed). Three load-bearing tests, all run for real:

- **Basic sandboxed exec, as root:** `bwrap --ro-bind / / --proc /proc
  --dev /dev --unshare-all --die-with-parent /bin/echo "bwrap-root-ok"` →
  succeeded, exit 0.
- **Unprivileged exec — the specific case my prior investigation flagged
  as uncertain:** created no new infrastructure, just re-ran the identical
  command as the pre-existing unprivileged `nobody` account via `su -s
  /bin/sh nobody -c '...'` → succeeded, exit 0, `unpriv-bwrap-ok`. This is
  the direct answer to the flagged uncertainty: unprivileged user-namespace
  creation is **not** restricted by this host's kernel configuration.
- **Network isolation:** inside a `--unshare-all` sandbox, `curl` to
  `http://example.com` failed immediately (`curl exit=6`, could not
  resolve host) — no interface, no DNS, no route reachable. Real, not a
  documented claim taken on faith.
- **Filesystem containment:** a path never bind-mounted into the sandbox
  (`/tmp/bwrap-test/outside-secret.txt`, present on the host) was
  unreachable from inside (`cannot create ...: Directory nonexistent`) —
  not a denial with an audit trail, a path that structurally does not
  exist in that namespace. A single file bind-mounted read-write
  (simulating `operations.sqlite3`) was reachable and a write made inside
  the sandbox was visible on the host afterward — confirming §3.7's own
  named gap precisely: bind-mounting a raw file read-write gives the
  sandboxed process the same raw file-level access to it any other Bash
  command would have. §3 below is the control for that.

**Conclusion: bubblewrap/namespace sandboxing is feasible in this hosting
environment, verified empirically, including in the unprivileged case.**
This is a positive result where the prior investigation had explicitly
flagged an open question — stated plainly, not softened, and not
overclaimed either: this container is a development/investigation
environment, not confirmed identical to the production deployment host
(kernel version, container-runtime restrictions, and cloud-provider
seccomp policy can differ host to host). **A DevOps-owned pre-implementation
verification of the same three tests against the actual production host is
a required step in §7's rollout plan, not assumed transferable.** Given
this project's own established discipline (the hook-invocation
investigation's insistence on testing against the real binary rather than
inferring from docs), that check should not be skipped.

## 2. Chosen shape: namespace-primary hybrid, scoped to Developer only

**Recommendation: neither §3.6 nor §3.7 as originally, separately framed —
a hybrid that takes bubblewrap namespace confinement (§3.7) as the primary,
kernel-enforced containment layer, adds one dedicated low-privilege OS
account for Developer specifically as a cheap second layer (a narrow slice
of §3.6, not its full seven-role scope), and closes §3.7's own named
database-write gap with a broker (§3).** Applied to Developer only.

### 2.1 Why not full §3.6 (a distinct OS user for every one of the seven
roles, as originally scoped)

Full OS-user separation is real and does close the adversarial-bypass gap
— but its cost, as my own prior investigation named, is structural and
project-wide: it requires every one of the seven supervised roles to move
off Claude Code's native, in-process Task-tool subagent delegation onto
out-of-process subprocess invocation, plus passwordless `sudo` and
file-ownership engineering across every shared path, for roles that do not
need it. Six of the seven roles (`code-review`, `security`, `red-team` are
already, separately, moving to zero-tool invocation per §3.1 of the prior
document — unaffected by anything here; `qa`, `cto`, `devops` have real but
narrower, more enumerable Bash needs that the prior investigation already
named as a better fit for the cheaper hook/broker-script pattern, §3.2/§3.5,
not full sandboxing) gain nothing from a distinct OS user that bwrap's own
namespace containment doesn't already provide for the one role that
actually needs kernel-enforced isolation. Paying the full project-wide
cost of §3.6 to solve a single-role problem is disproportionate — the same
judgment the original investigation made, now confirmed rather than
revisited, because nothing in this scoping found a second role that
warrants it (see §4.3).

### 2.2 Why bwrap alone (§3.7, unmodified) is not quite enough either

Bubblewrap closes the subprocess/symlink/encoding bypass gap that made
every hook-based option (§3.2–§3.5) fundamentally limited against a
determined adversary — genuinely, kernel-enforced, verified in §1. But
bwrap's isolation is namespace-based, not identity-based: everything inside
the sandbox still runs under whatever UID launched it. If Developer's
sandboxed process runs as the Founder's own UID (the simplest version of
§3.7), a hypothetical **kernel-level namespace-escape** (a real, if rare,
class of Linux CVE — user-namespace/overlayfs bugs have happened
industry-wide, this is not invented for this document) would hand an
adversarial process the Founder's own full identity on the host, including
everything §1's containment was supposed to keep away from it. A dedicated,
low-privilege OS account closes exactly that specific residual scenario, at
low marginal cost (one `useradd`, one narrowly-scoped `sudo` rule, one
shared group) — real defense-in-depth, not redundant with the namespace
layer, because the two fail independently: an attacker has to defeat
*both* the namespace boundary *and* the UID/file-permission boundary to
reach `.founder_credential.json`, not just one.

### 2.3 The chosen shape, concretely

- **New OS account**: `ai-developer` — `useradd --system --no-create-home
  --shell /usr/sbin/nologin ai-developer` (production host's actual
  `useradd`/equivalent to be confirmed by DevOps; this environment is
  Ubuntu/`apt`-based and this exact command was not run against the live
  repo's host as part of this investigation — named here as the concrete
  step, not executed, consistent with "architecture only, do not
  implement"). Owns nothing sensitive by default.
- **Bwrap namespace, per Developer invocation**: new mount, PID, network,
  UTS, IPC, and cgroup namespaces (`--unshare-all`), explicit
  `--ro-bind`/`--bind` allowlist (§4.4), `--die-with-parent` (sandbox and
  everything in it dies with the launcher, no orphaned processes).
- **Default: no network inside the sandbox.** Closes exfiltration/C2 and
  unreviewed package installation for free, and matches this project's
  existing "no dependency added without justification" rule (`developer.md`
  "Must NOT" list) — a new dependency that needs installing is already
  supposed to go through review before it's added, so "the sandbox can't
  reach the network to `pip install` something ad hoc" is enforcement of an
  existing policy, not a new restriction invented here. If this proves too
  disruptive in practice, a narrow allowed-egress mechanism (e.g. a
  host-side package-install proxy) is a small, later, revisitable follow-up
  — not a reason to default open.
- **`operations.sqlite3` is not present inside the sandbox at all** — see
  §3. Only a narrow, fixed-verb broker socket is bind-mounted.
- **`.founder_credential.json` and anything else Founder-only**: unchanged,
  600, owned by the Founder's own user — not bind-mounted into the sandbox
  (namespace exclusion), and, as the second independent layer, unreadable
  even by direct UID/permission check if `ai-developer` somehow escaped the
  namespace (defense named in §2.2).

## 3. Closing the `operations.sqlite3` gap: a validated-function broker, not a bind-mounted file

My own prior investigation (§3.7) named this precisely and did not solve
it: bind-mounting `operations.sqlite3` read-write into any sandbox — bwrap
or otherwise — gives the sandboxed process the exact same raw file-level
access to it that plain Bash has today, because filesystem sandboxing only
controls *paths*, not what a process with a legitimate mount does once it
has one. §1's own test reproduced this directly: a file bind-mounted
read-write was fully writable from inside the sandbox, host-side, no
different from an unsandboxed write. Denylisting the `sqlite3` CLI binary
specifically does not close this either — Python's standard library ships
its own `sqlite3` module, and Developer legitimately needs Python inside
the sandbox for real work, so any interpreter available for legitimate use
is also capable of opening the raw file directly, with no separate binary
required.

**The concrete control, matching this task's own explicit instruction
("brokering all DB writes through validated `opsdb.py` functions only, no
raw `sqlite3` CLI/file access inside the sandbox")**:

1. **`operations.sqlite3` is removed from the sandbox's visible filesystem
   entirely** — not bind-mounted, read-only or read-write, at all. A
   `sqlite3 operations.sqlite3 ...` or a raw Python `sqlite3.connect(...)`
   call from inside the sandbox fails with "no such file" — structural, not
   pattern-matched, the same discipline §1's containment test already
   demonstrated for any other unbound path.
2. **New `ops/control-center/opsdb_broker.py`** — a small, always-running,
   host-side daemon (runs as the Founder's own user, or a dedicated trusted
   `ai-pipeline-broker` system account — never as `ai-developer`), listening
   on a fixed Unix domain socket (e.g. `/run/ai-pipeline/opsdb.sock`),
   started the same way DevOps already manages `server.py`'s own process
   lifecycle. It exposes an **explicit, exhaustively enumerated allowlist
   of exactly five RPC verbs** — `handoff`, `task-status`,
   `task-step-status`, `task-progress`, `activity-log` — each individually
   re-scoped beyond what `opsdb.py`'s own CLI accepts (task-id binding to
   the invoking sandbox session, broker-injected agent identity, and, for
   `handoff`/`task-status`, a restricted target-value allowlist). **See the
   Correction section immediately below for the exhaustive verb table, the
   exclusion list, and the session-binding/identity-pinning mechanism that
   makes it enforceable** — a prior version of this document claimed this
   set was already "small, closed, and fixed" while its own parenthetical
   listed the unscoped `query` verb and other roles' governance-write verbs
   inside that same "closed" set; Red Team's review (`review_results.id=73`)
   found that self-contradiction and this section has been corrected
   accordingly. This remains a small refactor of `opsdb.py` (expose the
   existing validated logic as plain callables the broker can import and
   call directly, not a rewrite of any validation logic) plus new,
   genuinely new, security-relevant code (the daemon itself) that must go
   through this project's normal Code Review/QA/Security gates like
   anything else — named explicitly here so it is not waved through as
   "just reuse," even though it reuses 100% of the existing validated write
   logic.
3. **`opsdb.py`, modified with one new client mode**: an
   `OPSDB_BROKER_SOCKET` environment variable — when set (only inside the
   sandbox), every command serializes its already-validated arguments and
   ships them to the broker instead of calling `connect()` and writing
   directly. When unset (every other invocation path, all six other
   roles, `automation.py`, direct human use), behavior is byte-for-byte
   identical to today — zero change to any non-Developer path.
4. **Socket file permissions**: owned by the broker's own account, group
   `ai-pipeline-db` (new, shared between the broker account and
   `ai-developer`), `chmod 660` — only the sandboxed Developer process (via
   the bind-mounted socket path) and the broker itself can use it.

**What this closes, stated precisely**: raw file/CLI access to the
database from inside the sandbox — the specific, concrete gap this task
required a real control for. **What this does not close, stated equally
precisely, matching §5 of the prior investigation's own honest disclosure**:
a Developer session, compromised or merely mistaken, can still submit a
*well-formed, schema-valid* but *substantively false* row through the
broker — the broker validates structure (foreign keys, enum membership,
parameterized values), the same as `opsdb.py` always has, not the honesty
of the content. That is a materially different problem (content
truthfulness/provenance, not access scoping) than this task was scoped to
solve, and this document does not manufacture a fix for it — it is named
here, explicitly, as still open, not silently dropped. See §6.

---

## Correction (Red Team's TASK-023 review, `review_results.id=73`, REJECT) — exhaustive broker verb allowlist and empirically-verified PID-namespace containment

Red Team rejected the version of this document that first went to review, on
two findings. Both are narrow and both are fixed here without reopening
anything else Red Team found sound: the bwrap namespace shape, the
filesystem/network feasibility results (§1), the dedicated `ai-developer`
OS account, Developer-only scoping, the invocation-model change (§4), and
the TASK-017 fold-in reasoning (§5) are unchanged by this correction.

### Finding 1 (blocking): the broker's verb set was not actually "small, closed, and fixed"

The prior text in §3/§7 claimed a "small, closed, fixed set of RPC verbs ...
no raw SQL passthrough verb, ever" while its own parenthetical listed the
SELECT-only `query` verb and other roles' governance-write verbs
(`decision-record`, `risk-resolve`, `review-result`, `qa-result`) inside
that same "closed" set. Red Team read `cmd_query` directly and found it
executes arbitrary free-text SQL constrained only by
`stmt.lstrip().upper().startswith("SELECT")` — no table/row scoping —
meaning a sandboxed Developer session could read the entire schema
(`messages`, `approvals`, `decisions`, `deployments`, every other task's
rows) through what this document called "closed." Red Team also found that
none of `opsdb.py`'s write functions verify the caller-supplied
`--by`/`--by-agent` argument against the actual caller's identity, so
exposing other roles' write verbs over the broker would let a compromised
Developer session forge a Red Team PASS, a QA PASS, a Founder decision
record, or even resolve `risks.id=3` itself — through the very channel this
document presented as the fix.

**The corrected design, replacing the prior §3/§7 language in full:**

The broker exposes exactly five RPC verbs, and no others. Every other
`opsdb.py` subcommand — including `query` — is excluded from the
Developer-facing socket entirely.

| Verb | Client-supplied args accepted | Broker-enforced (never trusts a client-supplied value) | Additional scope restriction |
|---|---|---|---|
| `handoff` | `work_completed`, `files`, `tests_added`, `expected_behavior`, `known_limitations`, `checklist`, `base_commit_sha`, `head_commit_sha` | `task_id` forced to this session's bound task; `from_agent` forced to `"developer"` | `to_agent` allowlisted to `"code-review"` only — the only handoff target Developer's role doc (`.claude/agents/developer.md`) and this project's own handoff history (`handoffs` table: 12/12 rows are `developer` → `code-review`) ever show |
| `task-status` | `owner` (optional), `note` (optional) | `task_id` forced to this session's bound task; `by` forced to `"developer"` | `to` allowlisted to `{IN_DEVELOPMENT, CODE_REVIEW, BACKLOG}` only — the only three statuses `task_status_history` shows Developer has ever set (`CODE_REVIEW` ×11, `IN_DEVELOPMENT` ×5, `BACKLOG` ×1); every other `VALID_STATUSES` value (`RED_TEAM_REVIEW`, `QA_REVIEW`, `SECURITY_REVIEW`, `DEPLOYED`, etc.) rejected |
| `task-step-status` | `step_id`, `status` (`pending`/`in_progress`/`done`) | broker looks up `step_id`'s owning `task_id` before forwarding and rejects the request if it does not equal this session's bound task | none beyond the task binding |
| `task-progress` | `task_id` (must equal the session's bound task; any other value rejected) | — | read-only; `opsdb.py`'s own implementation already sums only one task's own `task_steps` rows, no schema-wide exposure |
| `activity-log` | `summary`, `detail` (optional) | `task_id` forced to this session's bound task; `agent` forced to `"developer"` | none beyond the task binding |

**Explicitly and exhaustively excluded from the Developer-facing socket** —
every other `opsdb.py` subcommand, with no exceptions: `init`, `query`
(dropped entirely, not re-scoped — see below), `project-create`,
`agent-upsert`, `task-create`, `task-update`, `task-step-add`, `run-start`,
`run-heartbeat`, `run-end`, `run-reconcile`, `agent-status`, `risk-add`,
`risk-resolve`, `phase-add`, `phase-set-status`, `message-send`,
`qa-result`, `review-result`, `approval-create`, `approval-decide`,
`decision-record`, `task-purge-scratch`, `deployment-record`. This list was
produced by enumerating every `sub.add_parser(...)` call in `ops/db/opsdb.py`
directly (29 subcommands total), not by patching only the four verbs Red
Team happened to name in its review text — the five included above are the
only ones with any support in Developer's own role doc or this project's
actual historical write pattern (`.claude/agents/developer.md`'s single
named write path, `handoff`; `task_status_history`/`agent_activity`/
`task_steps` rows attributed to `developer` in the live database).

**Why `query` is dropped entirely rather than re-scoped.** §4.1 step 1
already has `launch_developer_session.py` assemble the full task record
(task fields, architecture notes, mockup) into the prompt *before* the
sandboxed process starts — Developer does not need a live read path into
`operations.sqlite3` for anything in its normal workflow, and nothing in
its role doc asks for one. Building a narrow, purpose-built read verb
(e.g. "my own task's current row") would itself be new, security-relevant
code requiring its own review, for a need this design has no evidence it
actually has. If a real need for one surfaces later, adding it is a new,
separately-reviewed decision — not something this correction pre-authorizes.

**How task-binding and identity-pinning are actually enforced, not just
asserted.** `launch_developer_session.py` generates a random per-session
token (`secrets.token_hex(16)`) when it starts a Developer sandbox for a
specific `task_id`, and registers `(token, task_id, agent="developer")`
with `opsdb_broker.py` over the same socket *before* launching the
sandbox — using a registration verb the broker only accepts from a
connection whose peer credentials (`SO_PEERCRED`) resolve to the Founder's
own UID or the broker's own trusted account, never `ai-developer`'s UID, so
the sandboxed process itself can never call it. The token is passed into
the sandbox as a new `OPSDB_BROKER_TOKEN` environment variable alongside
the existing `OPSDB_BROKER_SOCKET` (§3 point 3); `opsdb.py`'s broker-client
mode includes it on every RPC. The broker resolves `task_id`/`agent` from
its own session table keyed by that token — never from a client-supplied
field — for every one of the five verbs above, and the session entry is
removed when `launch_developer_session.py` detects the sandboxed process
has exited. This is what makes the per-verb "forced"/"bound" restrictions
in the table above real enforcement rather than a documentation convention
the broker's own code doesn't actually check.

This closes both halves of Finding 1: `query`'s unscoped schema-wide read is
gone, and the four other-roles' governance-write verbs are excluded
outright — a sandboxed Developer session cannot construct a request the
broker will forward for any of them, regardless of what its own
compromised session claims about its identity.

### Finding 2 (non-blocking): §6's PID-namespace claim was cited to a test §1 never ran — now actually run

§6 previously claimed `ptrace`/`gdb`/`strace` containment was "closed
structurally by the PID namespace ... verified in §1," but §1's own test
list only ever covered filesystem containment, network isolation, and
basic root/unprivileged exec — no test against a real host PID was run.
Red Team caught the overclaim; the missing test has now actually been run,
in this same environment, as part of this correction pass:

- A real host process was started (`sleep 120`, host PID 2333, confirmed
  live via `ps -p 2333`).
- From inside a `bwrap --unshare-all` sandbox: `ps aux`/`ps -ef` list only
  the sandbox's own remapped PIDs (1–4); PID 2333 does not appear anywhere
  in the output. `ls /proc` inside the sandbox lists only `1, 2, 5, 6` —
  PID 2333 is not present as an entry at all, not merely hidden by
  permission.
- `gdb -p 2333` from inside the sandbox: `ptrace: No such process.` — gdb
  cannot even locate the target to attempt an attach.
- `strace -p 2333` from inside the sandbox: `strace: attach:
  ptrace(PTRACE_SEIZE, 2333): No such process` — same result.
- Sanity check that the PID namespace itself is real (not merely `ps`
  failing for an unrelated reason): the sandbox's own shell reports itself
  as PID 2 (`echo $$`) / PID 3 (`/proc/self/status`), consistent with being
  an early PID in a freshly unshared namespace, not the host's actual PID
  for that same process.

**§6's bullet is corrected accordingly** (see §6 below): PID-namespace
containment is now empirically verified, the same evidentiary standard as
the other bullets in that list, not inferred from `--unshare-all`'s
documented flag semantics alone.

---

## 4. How supervised invocation changes, and why Developer only

### 4.1 What changes, concretely

Today, per my own prior investigation's framing (flagged there as an
assumption needing independent verification, not settled — preserved with
that same qualification here): a human's interactive `claude` session
delegates work to `developer` via Claude Code's native Task-tool subagent
mechanism, inline, within the same OS process the human is already
watching. Any real OS-level or namespace-level isolation can only be
applied to a distinct process launch — a kernel cannot put a new mount/PID/
network namespace around code running inside an existing process's own
thread — so this structural requirement is **shared by §3.6 and §3.7
equally**, not unique to the OS-user-separation option as originally
framed. Whichever shape is chosen, Developer's supervised invocation must
move from in-process delegation to out-of-process subprocess invocation.

One piece of new, directly-gathered evidence narrows the previously-flagged
uncertainty about whether this is even a supported pattern: this project's
own `agent_runtime.py` already invokes `claude --agent <role> ...` as a
real child OS process via `subprocess.Popen` for the unsupervised
(zero-tool) paths, and the installed CLI binary itself contains a distinct,
named subprocess-spawn primitive (`spawnClaudeCodeProcess`, used for its
own background-task/session-store mechanism, confirmed present via direct
inspection of `/opt/claude-code/bin/claude`, the same evidentiary standard
the hook-invocation investigation used). Whatever Task-tool's own internal
delegation mechanism turns out to be — still not independently verified
here, and should be treated as Red Team/Security's job to confirm, not
assumed — subprocess-based invocation of `claude --agent developer ...` is
not new capability being requested of the harness; it is a documented,
already-used invocation mode of the same CLI, and this project has already
built and shipped code using it.

**New flow for Developer specifically**:

1. `ops/control-center/launch_developer_session.py` (new, host-side, runs
   as the Founder's own user, invoked by the orchestrator in place of a
   native Task-tool delegation for Developer work) assembles the task
   prompt/transcript (task record, architecture notes, coding standards —
   reusing existing transcript-assembly conventions where applicable).
2. It runs `sudo -u ai-developer
   ops/control-center/launch_developer_sandboxed.sh <args>` via
   `subprocess.Popen(..., start_new_session=True)` — the same pattern
   `agent_runtime._run_claude()` already establishes, extended with the
   `sudo -u` prefix and real tool grants (`--tools
   "Read,Edit,Write,Bash,Grep,Glob,Skill"` in place of `--tools ""`).
3. `launch_developer_sandboxed.sh` (new, fixed, reviewed, non-parameterized
   in any shell-interpreted way — task content is passed as data, not
   spliced into shell syntax) builds and runs the actual `bwrap ... --
   claude --agent developer ...` invocation, with `OPSDB_BROKER_SOCKET`
   set.
4. The launcher streams the subprocess's stdout live to the human's
   terminal/session as it is produced (`--output-format stream-json` if
   the harness supports incremental streaming in this mode, else `text`) —
   not a batch replay assembled after the fact.

### 4.2 What "a human watching tool calls in real time" now means — named honestly

This is a real, disclosed change in ergonomics, not a footnote. The human
still watches Developer's tool-call-by-tool-call activity as it happens,
but as a streamed subprocess output feed rather than the native, richer
inline Task-tool UI (in-context diff rendering, native tool-approval
prompts). One specific consequence that must be verified empirically,
not assumed, before this ships: Claude Code's native interactive "ask"
permission-escalation outcome — relied on by §3.2 of the prior
investigation as a live human answering an in-band prompt — may not be
available at all in `-p`/print-mode subprocess invocation, per the CLI's
own documented behavior already surfaced in the hook-invocation
investigation ("the workspace trust dialog is skipped when Claude is run
in non-interactive mode"). If "ask" does not function in this mode
(**flagged here as a required Development/Red Team verification item, not
assumed either way**), escalation for a genuinely needed but denied
operation becomes coarser: the human, watching the stream, manually
intervenes (kills the session, adjusts the task, re-launches) rather than
answering an in-band prompt. This is a real cost, and the Founder should
sign off on accepting it explicitly as part of Red Team review, not have it
minimized here.

### 4.3 Why only Developer

DEC-011 itself scopes this to "the Developer role (and any other role the
scoping finds warrants it)." This scoping found no second role that
warrants the same treatment:

- `code-review`, `security`, `red-team` are already, independently, moving
  to zero-tool invocation (§3.1 of the prior investigation) — they have no
  Bash/filesystem surface left to sandbox once that ships.
- `qa`, `devops` have real Bash needs, but ones the prior investigation
  already characterized as genuinely enumerable (run the app, run tests,
  inspect build/deployment state) — a better fit for the cheaper
  broker-script/allowlist pattern (§3.5) than for full namespace
  sandboxing, and there is no new evidence from this scoping that changes
  that judgment.
- `cto` (this role) needs broad *read* access across the whole repository
  and its own docs to reason about architecture, and does not have
  Developer's combination of broad Write/Edit plus open-ended,
  Bash-execution-heavy iterative work — the same asymmetry the original
  investigation named.

Developer remains the one role whose legitimate work is genuinely
open-ended (arbitrary debugging commands, ad hoc one-liners, dependency
installation) *and* whose blast radius (Write/Edit plus unrestricted Bash)
is the largest of the seven — the same profile that made TASK-017 and this
whole risk register entry center on Developer from the start. If a future
scoping pass finds a concrete reason to extend this to another role, that
is a new architecture decision, not something this document pre-authorizes.

### 4.4 Bind-mount allowlist and file ownership

- **Working tree**: a dedicated git worktree per Developer task (§3.4 of
  the prior investigation, previously "real but only as a component" — now
  load-bearing rather than optional), `--bind <worktree-path>
  <worktree-path>` (read-write). Owned via a shared `ai-pipeline-dev` group
  (Founder's user and `ai-developer` both members, directory `g+rwx` with
  the setgid bit so new files inherit the group) — not `ai-developer`-only
  ownership of the whole repository, which would lock the Founder's own
  account out of files Developer created, a real, easy-to-hit operational
  papercut the prior investigation's §3.6 discussion did not spell out this
  concretely.
- **`operations.sqlite3`**: not shared via file ownership at all under this
  design — only the broker (§3), running as a separate trusted account,
  ever opens the file directly. This is a meaningful simplification over
  what §3.6 originally worried about needing for the database specifically.
- **`.founder_credential.json`**: unchanged, 600, Founder-owned, not
  bind-mounted, not group-shared.
- **Standard system paths**: `--ro-bind /usr /usr` (+ `/bin`, `/lib`,
  `/lib64` symlinks or real binds, per §1's own working test recipe),
  `--proc /proc`, `--dev /dev`, `--tmpfs /tmp` (ephemeral, sandbox-local,
  gone when the sandbox exits).
- **Broker socket**: `--bind /run/ai-pipeline/opsdb.sock
  /run/ai-pipeline/opsdb.sock` (read-write) — the sandbox's only path to
  any persisted operational state.
- **sudoers**: one line, narrowly scoped to the exact fixed script path —
  `<founder-user> ALL=(ai-developer) NOPASSWD:
  /home/user/AI-Pipeline/ops/control-center/launch_developer_sandboxed.sh`
  — never a general `NOPASSWD: ALL`. This is real, new, security-relevant
  surface (the prior investigation was right to flag it), scoped as
  tightly as sudoers syntax allows.

## 5. TASK-017's remaining cheap fixes: fold in, with a concrete reason beyond "cheap and available"

**Recommendation: fold all three items into this milestone's Development
pass, not a separate follow-up task — with one adjustment to the
self-checking monitor's scope.**

This is not merely "they're cheap, might as well." There is a real,
structural reason specific to this architecture:

1. **The trust-flag deployment fix becomes a load-bearing prerequisite,
   not an optional improvement.** Developer's new invocation path (§4) is
   itself a `-p`/print-mode subprocess call — exactly the invocation
   context the hook-invocation investigation proved silently skips
   frontmatter `PreToolUse` hooks entirely when the workspace is untrusted.
   Without the trust-flag fix, the hook layer this document is asked to
   treat as "defense-in-depth layered under the new sandboxing" would not
   fire at all in the new architecture either — the exact same silent gap,
   reproduced in a new context, not fixed by anything else in this
   document. It must ship in the same pass or the hook layer is inert.
2. **The self-revert vulnerability the hook-invocation investigation found
   fatal is closed structurally by this architecture, not by a better
   denylist entry.** That finding's core problem was that Developer's own
   Bash access could rewrite the shared `~/.claude.json` trust file,
   because it lives outside the repo but inside the same OS user's reach.
   In the new architecture, `ai-developer`'s own trust-config file is not
   bind-mounted into the sandbox at all — it is not merely denylisted, it
   does not exist in the sandbox's mount namespace, the same structural
   guarantee §1 verified for every other unbound path. This closes half of
   TASK-017's own worst finding as a direct side effect of adopting
   namespace sandboxing, not a new fix — worth stating plainly rather than
   re-deriving a weaker hook-based patch for a problem this design already
   solves differently.
3. **The two secondary bugs** (leading-space `" gdb"`/`" strace"` substring
   check, `shlex.split()` hang-to-fail-open) are real, cheap, and
   Development is already touching `developer_pretooluse.py`'s invocation
   context in this same pass — fixing them here is close to free and there
   is no reason to defer known, live gaps.
4. **The self-checking trust-flag monitor**: its original purpose — detect
   silent reversion of the shared trust flag — is substantially moot for
   Developer specifically once the sandbox structurally prevents Developer
   from reaching that file at all. It is **not** moot for `qa`/`cto`/
   `devops`, which remain on native, in-process, trust-file-dependent
   invocation (§4.3) and in principle still share the same global
   `~/.claude.json` the Founder's own session uses. **Recommendation:
   fold the monitor in, but generalize its scope to the shared trust file
   for the three roles that still depend on it, not Developer** — smaller
   than originally designed, but still real, still cheap, and now scoped
   accurately to where the concern actually still lives.

## 6. Threat model — what this closes and does not close

**Closes, kernel-enforced, verified in §1 (not pattern-matched, not a
prompt convention):**

- Filesystem containment — Developer's sandboxed process cannot reach any
  path not explicitly bind-mounted (the task worktree, the broker socket,
  read-only system paths), immune to the subprocess-indirection,
  symlink, `cd`-trick, and encoding bypasses that were the fundamental,
  disclosed, unclosable gap of every string-pattern hook option (§3.2's own
  analysis). The path simply does not exist in that namespace, regardless
  of what command or interpreter is used to try to reach it.
- `.founder_credential.json` read — closed twice, independently: namespace
  exclusion (not bind-mounted) and, as defense-in-depth, real UNIX file
  permissions against the dedicated low-privilege `ai-developer` UID.
- `ptrace`/`gdb`/`strace` against `server.py` or any host process — closed
  structurally by the PID namespace; the sandboxed process cannot see host
  PIDs to target them at all. **Empirically verified directly, not inferred
  from `--unshare-all`'s flag semantics** — see the Correction after §3 for
  the actual test (`ps aux`/`ps -ef`/`gdb -p`/`strace -p` against a live
  host PID, all confirming the PID is unreachable). This bullet previously,
  incorrectly, cited "verified in §1" for this specific claim; §1 never ran
  this test — corrected per Red Team's review (`review_results.id=73`).
- Outbound network/exfiltration/C2/unreviewed package installation — closed
  by `--unshare-net` under the "no network by default" policy (§2.3),
  verified directly in §1.
- The trust-flag self-revert vector (TASK-017's own fatal QA finding) —
  closed structurally for Developer, per §5.
- Raw `sqlite3`-CLI/file-level access to `operations.sqlite3` — closed by
  the broker design in §3; the file is never present inside the sandbox.

**Does not close — stated plainly, same discipline as every prior review
in this project, not softened:**

- **Truthful-but-wrong `opsdb.py`/broker calls.** A Developer session can
  still submit a well-formed, schema-valid, but substantively false
  status/handoff/decision row through the broker, exactly as it could
  through direct `opsdb.py` invocation today. Content-honesty/provenance is
  a materially different problem than access scoping and is not solved
  here — named explicitly, not silently dropped, per §3.
- **A kernel-level namespace/container-escape vulnerability.** Bwrap's
  guarantee is only as strong as the host kernel's own namespace
  implementation; this is a real, standing residual risk shared by
  essentially any sandboxing technology built on the same Linux primitives
  (not unique to bwrap, not invented for this document). The dedicated
  low-privilege `ai-developer` account is the specific, named mitigation
  for exactly this scenario — it limits what an escape actually reaches,
  it does not make the scenario impossible.
- **Developer's own judgment, within its allowed reach.** This architecture
  narrows *where* Developer's Bash/Write/Edit access can go, not *what*
  Developer, as a model, decides to do inside the worktree it is
  legitimately editing. A defect introduced on purpose or by mistake inside
  the sandbox's allowed surface is unaffected by any of this — that remains
  Code Review/QA/Security's job, unchanged.
- **The other six roles' Bash exposure.** This milestone is explicitly
  scoped to Developer only (§4.3). `qa`/`cto`/`devops` remain exactly where
  the prior investigation left them — real but partial hook/broker-script
  narrowing (§3.2/§3.5 of the prior document), not sandboxed, not
  addressed further here.
- **Production-host parity.** §1's feasibility result is real and positive,
  but measured in this development/investigation container, not the
  production deployment host. DevOps must independently re-run the same
  three tests against the actual production host before this ships (§7) —
  not assumed transferable.

## 7. Implementation and rollout plan

**Files/scripts touched or added:**

1. **NEW** `ops/control-center/opsdb_broker.py` — Unix-socket daemon;
   imports `opsdb.py`'s existing validated command logic (small refactor of
   `opsdb.py` to expose it as plain callables, not a rewrite); exhaustive
   five-verb allowlist per the Correction after §3 (`handoff`,
   `task-status`, `task-step-status`, `task-progress`, `activity-log`
   only — **not** 1:1 with `opsdb.py`'s full subcommand set); session-token
   task-id binding and broker-injected agent identity per the same
   Correction; no `query`/`SELECT` verb of any kind exposed. Runs as the
   Founder's own user or a new trusted `ai-pipeline-broker` account — never
   as `ai-developer`.
2. **MODIFIED** `ops/db/opsdb.py` — add `OPSDB_BROKER_SOCKET`-driven client
   mode (socket call instead of direct `connect()` when set); zero
   behavior change for every invocation where the variable is unset.
3. **NEW** `ops/control-center/launch_developer_sandboxed.sh` — fixed,
   reviewed, non-parameterized-in-shell-syntax wrapper; builds the actual
   `bwrap ... -- claude --agent developer ...` argv per §2.3/§4.4; the
   sudoers NOPASSWD target.
4. **NEW** `ops/control-center/launch_developer_session.py` — host-side
   launcher (Founder's own user); assembles the transcript, invokes (3) via
   `sudo -u ai-developer` + `subprocess.Popen`, streams output live, applies
   timeout/budget/process-group-kill per the existing `agent_runtime.py`
   convention.
5. **MODIFIED** `ops/control-center/hooks/developer_pretooluse.py` — the
   two secondary bug fixes named in §5 (token-boundary check for
   `gdb`/`strace`; command-length ceiling before `shlex.split()`).
6. **MODIFIED** `.claude/agents/developer.md` — persona note describing the
   sandboxed invocation path (the same convention `code-review.md`'s
   "Automated-invocation mode" section already establishes), while noting
   the existing `hooks:` block still applies as a second layer once the
   trust-flag fix ships.
7. **NEW (folded per §5, generalized scope)** a trust-flag monitor covering
   the shared `~/.claude.json` state that `qa`/`cto`/`devops` still depend
   on.
8. **New OS/deployment configuration (no product schema change — this
   design deliberately reuses existing tables via the broker rather than
   adding new ones)**: `useradd ai-developer`; `ai-pipeline-dev` and
   `ai-pipeline-db` shared groups; the one narrowly-scoped sudoers line;
   `bubblewrap` installed on the production host; the one-time trust-flag
   write for the fixed launcher path (mechanism per the hook-invocation
   investigation §2).

**Sequencing:**

1. `opsdb_broker.py` + `opsdb.py` client-mode change — independently
   buildable and testable now (env-var opt-in, zero risk to any other
   role), can clear Code Review/QA on its own before anything else depends
   on it.
2. DevOps: production-host feasibility re-verification (§1's three tests,
   re-run against the real deployment host) — gates whether §2's chosen
   shape proceeds as designed or needs revisiting; `useradd`, shared
   groups, sudoers line, `bubblewrap` install — in parallel with (1).
3. `launch_developer_sandboxed.sh` + `launch_developer_session.py` —
   depends on (1) and (2).
4. Trust-flag deployment fix + the two secondary bug fixes in
   `developer_pretooluse.py` — bundled with (3)'s rollout since the new
   invocation path is what makes them load-bearing again (§5).
5. `.claude/agents/developer.md` persona-note update.
6. Generalized trust-flag monitor for `qa`/`cto`/`devops` — independent,
   lowest priority of this list.
7. **End-to-end QA charter for this milestone, live-reproduced, not
   design-level only** (matching the discipline that found TASK-017's own
   fatal gap in the first place): a real Developer task run through the
   full sandboxed path, confirming (a) legitimate work still succeeds
   (edit files, run tests, commit within the worktree, submit a real
   handoff through the broker) and (b) each of the closed vectors in §6 is
   actually blocked live — a credential-read attempt, a `ptrace` attempt, a
   raw `sqlite3` CLI attempt against the (absent) database path, and a
   network-egress attempt, each run for real inside the sandbox, not
   asserted from the design alone.

## 8. Gate sequence

Per the Founder's explicit instruction, unchanged and non-skippable: CTO
architecture (this document) → Red Team → Development → Code Review → QA →
Security (adversarial) → CTO final conformance. Nothing in this document's
own confidence level is a basis for shortening that sequence — the
feasibility result in §1 is real, but it does not substitute for
independent adversarial review of the design itself, particularly the new,
genuinely security-relevant `opsdb_broker.py` daemon and the sudoers/UID
boundary, both of which are new attack surface this document is
introducing, not merely narrowing.
