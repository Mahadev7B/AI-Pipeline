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

---

## Addendum (Code Review's TASK-023 review, `ops/reviews/code-review-task023.md`, REJECT) — the model-API network carve-out (finding B3, the architecture decision), and the intended shape for B1/B2/B4

Development built this milestone code-only and Code Review REJECTed. One
finding (B3) is an architecture decision reserved for CTO + Red Team; three
(B1/B2/B4) are Development's to fix but need an unambiguous target stated
here. Nothing Red Team already blessed is reopened: the bwrap namespace
shape, the filesystem/PID containment results (§1 + the first Correction),
the five-verb broker allowlist and its session-binding/identity-pinning, the
`ai-developer` account, Developer-only scoping, and the invocation-model
change are all unchanged. This addendum changes exactly one previously-stated
property — §2.3's "no network by default, full stop" — narrowing it to "no
network *except one narrowly-brokered path to the model API*," and corrects
one overclaim in §5 point 1 / §6 about the in-sandbox hook layer. Both
changes are routed through Red Team as the required gate, not asserted as
settled.

### B3 (architecture decision) — the sandboxed `claude` CLI must reach the model API, and `--unshare-all` gives it no path

Code Review is correct and the gap is real: §1's feasibility spike only ever
exec'd `/bin/echo`, `/bin/sh`, and `curl` inside the sandbox, so it validated
that `--unshare-all` (which includes `--unshare-net`) blocks egress — a
verified *containment* property, and the direct closure of `risks.id=3`'s
exfiltration vector — but it never exec'd the real `claude` CLI, which must
reach the Anthropic model API to do any work at all. Under `--unshare-net` as
built, the sandbox has no interface, no route, and no reachable proxy, so the
first model call dies and every real sandboxed Developer session does zero
work. The letter of the architecture was implemented faithfully; the
architecture itself was incomplete. This addendum completes it.

**Chosen shape: keep `--unshare-all` exactly as designed — do NOT drop
`--unshare-net` — and add exactly one egress path: a single bind-mounted
Unix-domain socket served by a host-side, allowlisting forward/CONNECT proxy
that runs as a trusted account the sandboxed Developer cannot influence, and
that permits only the model-API host and denies everything else.**

Concretely:

- **The sandbox keeps zero network-namespace connectivity.** `--unshare-net`
  stays. The sandbox gets no veth, no route, no DNS, no reachable TCP
  destination. This preserves the exact containment §1 verified: general
  outbound egress is *structurally* impossible, not firewalled-and-widenable.
- **The one permitted egress is a Unix-domain socket, bind-mounted into the
  sandbox** (e.g. `--bind /run/ai-pipeline/egress.sock
  /run/ai-pipeline/egress.sock`, the exact same mechanism §3/§4.4 already use
  for the opsdb broker socket). Unix sockets traverse the *filesystem*
  namespace, not the *network* namespace, so this grants a single, named,
  auditable channel without granting any network interface at all — the same
  structural discipline as the filesystem bind-allowlist. A path not bound is
  not reachable, full stop.
- **A host-side allowlisting proxy owns the socket and enforces the
  allowlist.** It runs as the broker's trusted account (or a dedicated
  `ai-pipeline-egress` system account) — **never as `ai-developer`** — with
  the socket `chmod 660`, group `ai-pipeline-db` (or a dedicated group),
  exactly as the opsdb socket is. Its allowlist is a fixed config file owned
  by the trusted account, `0644 root`-owned / not writable by `ai-developer`
  and not bind-mounted into the sandbox — so the sandboxed Developer, even as
  root *inside its own user namespace*, cannot read or widen it. The proxy
  permits CONNECT to exactly the model-API host(s): `api.anthropic.com:443`
  in a normal deployment, and — in *this* hosting environment specifically —
  the configured agent egress proxy the environment already routes all
  outbound HTTPS through (`HTTPS_PROXY`, `/root/.ccr/README.md`), to which the
  host-side proxy chains as its own upstream. Everything else is denied.
- **What it does NOT permit, stated as precisely as §6 requires:** no general
  outbound egress; no package registries — `registry.npmjs.org`, `pypi.org`,
  `files.pythonhosted.org` et al. are **denied**, deliberately narrower than
  the ambient environment's own `NO_PROXY` list, so §2.3's "no ad-hoc
  `pip install` / unreviewed dependency" property is *preserved*, not
  reopened; no arbitrary C2 host; no DNS to arbitrary names. The carve-out is
  one destination class (the model API), not "the network."
- **Bridging the unmodified Node `claude` CLI to the socket.** The CLI honours
  `HTTPS_PROXY` as a `host:port` TCP endpoint, not a Unix socket. Two options,
  in preference order: (a) if the installed CLI's HTTP stack accepts a
  Unix-socket proxy directly, point `HTTPS_PROXY` at it and skip the bridge —
  a Development/Red Team verification item against the *real binary*, same
  discipline §1 used, not assumed; (b) otherwise, a tiny **fixed** relay
  started inside the sandbox binds `127.0.0.1:<port>` (the sandbox's own
  loopback, which bwrap brings up inside the new netns — verified below) and
  forwards to the bind-mounted Unix socket, with `HTTPS_PROXY=http://127.0.0.1:<port>`
  set for `claude`. The relay is inside the sandbox and therefore
  *untrusted*, but that is fine and by design: it can only forward to the one
  Unix socket, and the allowlist is enforced entirely host-side, in the
  trusted proxy, which the relay cannot bypass or widen. If the relay is used,
  it must be a fixed command (a small dedicated script or `claude` launched
  via a fixed `-- /bin/sh -c 'relay & exec claude …'` where **no task content
  enters shell syntax** — the wrapper's existing "content is data, never
  shell" discipline, §4.1 step 3, is preserved).

**Why not the alternatives (evaluated honestly):**

- *slirp4netns / user-mode networking:* gives the sandbox a real (NATed)
  network interface, then relies on an in-netns firewall to restrict it. But
  the sandboxed process is root *within its own user namespace* and holds
  `CAP_NET_ADMIN` for its own netns — it can flush or rewrite any nft/iptables
  rules placed *inside* that netns. An in-sandbox firewall is therefore
  widenable by exactly the principal it must constrain: disqualifying. Rejected.
- *nftables egress allowlist, whether in-netns or by dropping `--unshare-net`
  and filtering in the host netns:* the in-netns variant fails for the same
  `CAP_NET_ADMIN` reason. The host-netns variant (drop `--unshare-net`, share
  the host's network, restrict by destination IP on the host side) is not
  widenable by the sandbox, but it is strictly *weaker* than keeping the
  namespace: it is IP/port-based, so it is brittle against the API's IPs
  changing and against a shared-CDN IP also fronting non-API hosts, and it
  hands the sandbox a live interface with real routes as its default state,
  making any allowlist gap a general-egress hole rather than a no-op. Keeping
  `--unshare-net` and adding one Unix socket makes the *default* "no network"
  and the *exception* a single explicit channel — fail-closed, not
  fail-to-filtering. Rejected as the weaker posture.
- *A host-side proxy on host `127.0.0.1`, pointed at directly:* the sandbox's
  loopback is a *separate* netns loopback; the host's `127.0.0.1:<port>` is
  unreachable from inside (verified below — this is why the bridge/socket is
  required, and also a nice property: the host's own ambient agent proxy is
  not incidentally reachable from the sandbox either).

**Tested directly in this environment (bwrap 0.9.0, the §1 discipline — a
proposal verified, not asserted).** I built a throwaway host-side allowlisting
proxy on a Unix socket and a client run inside a real `bwrap --unshare-all`
sandbox with *only* that socket bind-mounted (no `useradd`, no persistent
daemon — throwaway processes only, per the hard constraint):

1. **General egress is structurally blocked.** From inside the sandbox, a raw
   TCP connect to an external `93.184.216.34:443` failed with `OSError`
   (network unreachable — no route in the netns). Confirms §1's containment
   still holds with the carve-out present.
2. **The host's own ambient proxy is unreachable.** A connect to the host's
   `127.0.0.1:43409` (this environment's agent proxy) from inside the sandbox
   failed with `ConnectionRefusedError` — the sandbox netns has its *own*
   loopback; the host proxy is not incidentally exposed. (That this is a
   *refused*, not *unreachable*, error also confirms loopback is *up inside*
   the sandbox — the fact option (b)'s in-sandbox relay depends on.)
3. **The one bound Unix socket is reachable and the host-side allowlist
   enforces.** Through the bind-mounted socket, a request naming
   `api.anthropic.com` got `200`; a request naming `evil.example.com` got
   `403` — the allow/deny decision is made in the host-side proxy, outside the
   sandbox's control.
4. **Structural absence when the socket is not bound.** Re-running the identical
   client with the socket *not* bind-mounted, the socket path did not exist
   inside the sandbox at all (`FileNotFoundError`) — the same "the path simply
   does not exist in that namespace" property §1 demonstrated for filesystem
   containment, not a denial-with-audit-trail.
5. **End-to-end CONNECT tunnel works, and the deny is enforced end-to-end.**
   With a host-side proxy that actually *tunnels* TCP to an allowlisted
   destination and an in-sandbox loopback relay bridging `127.0.0.1:8888` →
   the Unix socket (loopback bind/listen inside the sandbox succeeded, on an
   ephemeral port — confirming (b) is implementable): a CONNECT to the
   allowlisted destination tunnelled and round-tripped payload
   (`API-REPLY:hello`); a CONNECT to a non-allowlisted `8.8.8.8:53` was
   rejected `403 Forbidden` by the host-side proxy. This is the real shape the
   `claude` CLI will use, exercised with the CLI's own `HTTPS_PROXY`/CONNECT
   semantics (simulated), not just the raw socket.

**How a reviewer / QA tests this for real (add to the §7 QA charter):** inside
a live sandbox, (a) a real `claude` model call succeeds; (b) `curl
https://example.com`, a raw socket to `8.8.8.8:53`, and a connect to any
non-API host all fail with no route; (c) a CONNECT to a non-allowlisted host
*through* the egress proxy is `403`-ed at the host-side proxy; (d) a direct
connect to the host's own proxy address is unreachable; (e) the allowlist
config file is owned by the trusted account and not writable or readable by
`ai-developer`, and is not present in the sandbox mount namespace; (f)
`registry.npmjs.org`/`pypi.org` are denied (no ad-hoc package install).

**Residual risk, stated plainly (§6 discipline).** The single permitted path
*is itself a data channel*: a compromised or mistaken Developer session can
encode repository content or secrets it can read into the prompts it sends to
the model API. This cannot be closed while the CLI must reach the API at all —
it is inherent to the milestone's own goal of running a real model-backed
Developer under containment. It is, however, a *strictly smaller* channel than
the general egress `--unshare-net` closes: exactly one destination, no
arbitrary C2 host, no package-registry or paste-site exfil, and — because all
model traffic now funnels through one host-side proxy owned by a trusted
account — a single, auditable, loggable chokepoint where per-session volume
can be observed if that is later wanted. That observability is a follow-up
option, not part of this addendum's required scope; naming it here so it is
not mistaken for already-built. The exfil-via-API residual is the honest cost
of letting the CLI function, and the Founder should accept it explicitly at
Red Team review alongside the §4.2 ergonomics tradeoff, not have it minimized.

**Files this changes (guidance for Development, after Red Team blesses the
shape):** `launch_developer_sandboxed.sh` adds the one `--bind` for the egress
socket, the `HTTPS_PROXY` `--setenv`, and (if option (b)) the fixed relay
launch; a new host-side egress-proxy artifact (small, allowlisting, trusted
account) joins the §7 file list and goes through the same Code Review/QA/
Security gates as `opsdb_broker.py` — it is new, security-relevant network
surface and must not be waved through; the runbook (`task023-os-provisioning-runbook.md`)
gains the egress-proxy account/socket/allowlist provisioning steps and the
production-host equivalent of `api.anthropic.com`. This modifies §2.3's "no
network by default" bullet and §6's "outbound network / exfiltration / C2 …
closed by `--unshare-net`" bullet — both now read "closed except one
host-brokered, allowlisted, single-destination path to the model API," subject
to Red Team.

### B1 (broker robustness) — intended behavior; Development implements

The broker is the load-bearing security artifact and must survive anything its
untrusted client sends. Intended shape:

- **No exception escapes the accept loop.** Wrap `_handle_connection`'s body in
  `try/except OSError` (covers `BrokenPipeError`/`ConnectionResetError` on both
  `recv` and `sendall`) so one bad connection costs exactly one connection,
  never the daemon. Keep the accept loop's `try/finally conn.close()` and add
  the same catch-all there as a backstop. `_handle_connection` must never
  propagate.
- **Broaden the handler catch and validate before the DB.** In
  `handle_request`, add `sqlite3.Error` (the parent of `IntegrityError`/
  `OperationalError`/`InterfaceError`) to the caught set, returning `_err(...)`
  — never propagating. Additionally, validate required arg presence and type
  (e.g. `summary` is a non-empty `str`) *before* the DB call and return `_err`
  on failure, so schema-invalid content is a clean rejection, not a caught
  exception, and the DB is never needlessly touched.
- **Socket timeout.** `conn.settimeout(N)` (≈5–10s) immediately after `accept`,
  before `recv`, so a client that connects and holds cannot wedge the
  single-threaded loop indefinitely. Single-threadedness may remain (document
  it: a hostile client can still serialize others up to the timeout —
  acceptable for this trusted, low-QPS broker), but an idle/slow client must
  cost at most one timeout, never the daemon.
- **Session state on restart — decision: acceptable to lose, and must be
  in-memory, fail-closed.** Do **not** persist `_sessions` to disk. Persisting
  live capability tokens enlarges the attack surface (a stolen persisted token
  would outlive its session), and sessions are inherently ephemeral (one per
  live sandbox). Correct behavior: on broker restart, outstanding tokens become
  invalid — a token whose broker died should *not* keep working (fail closed).
  The launcher (`launch_developer_session.py`) is the live source of truth for
  the `token → task_id/agent` binding for as long as its sandbox runs, so it
  must treat an "invalid or unknown session token" reply as a signal to
  re-register (make `register_session` idempotent for the same token) or tear
  the sandbox down — not something the sandboxed process can recover on its
  own. And note: once B1's catch-all lands, the daemon no longer crashes on
  client input, so `Restart=on-failure` fires only on genuine faults — the fix
  is to stop the crashes, not to lean on restart. Fail-closed on a lost session
  is the intended security posture, not a bug to paper over with persistence.

### B2 (launch path) — intended mechanisms; Development implements

All four are fixable in code/config now, no provisioning needed to get them
right:

1. **Broker env survives `sudo`.** Preferred: pass the *token* as data via a
   file, not an env var — write it to a `0640` file owned by the launcher,
   group `ai-pipeline-dev`, and have the wrapper read it (same "content as
   data" discipline as the prompt file). This also keeps the token out of the
   process table and `/proc/<pid>/environ`. The non-secret socket *path* may
   stay an env var, but then the sudoers line needs a `SETENV:` tag and the
   `sudo` call `--preserve-env=OPSDB_BROKER_SOCKET` (named var only, never a
   blanket passthrough). The wrapper still `--setenv`s both into the sandbox,
   which is fine (sandbox-internal).
2. **Prompt file readable by `ai-developer`.** Do not rely on
   `tempfile.mkdtemp()`'s `0700`. Write the prompt file into the per-task
   worktree, which is already bind-mounted and group-shared via
   `ai-pipeline-dev` (§4.4), with the file `0640 <founder>:ai-pipeline-dev`; or,
   if a separate scratch dir is used, `chmod 0710` + `chgrp ai-pipeline-dev` the
   dir so `ai-developer` (a group member) can traverse and read. Prefer the
   worktree — it already carries the correct group and mode.
3. **Broker does not run as root.** Set `User=`/`Group=` in
   `opsdb-broker.service` (the founder's account or `ai-pipeline-broker`, group
   `ai-pipeline-db`), and set `OPSDB_BROKER_TRUSTED_UIDS` to the launcher's
   (Founder's) UID so `SO_PEERCRED`-gated `register_session` accepts it. The
   unit currently defaults to root, which both violates least-privilege and, via
   `_default_trusted_uids() == {0}`, breaks registration. Runbook must state the
   matching trusted-UID value.
4. **Timeout kill works across UIDs.** The launcher (Founder UID) cannot
   `killpg` a group of root-owned `sudo` and `ai-developer`-owned `bwrap`/
   `claude` — `os.killpg` raises `PermissionError`. Primary mechanism: enforce
   the wall-clock limit *inside* the sandbox, where the killer already has
   permission — `bwrap … -- /usr/bin/timeout --signal=KILL <N> claude …` — so
   expiry is enforced by `ai-developer` against `ai-developer`'s own process,
   and `--die-with-parent` reaps the rest of the tree. Backstop: add a
   `PermissionError` handler to `agent_runtime._kill_process_group()` so the
   launcher's outer timer degrades gracefully (close the stream, record
   `timed_out`) instead of throwing in the timer thread; if a hard outer kill of
   the privileged tree is ever required, do it via a narrowly-scoped
   `sudo -u ai-developer kill` (an `ai-developer`-owned signal to its own group),
   never a blanket sudoers grant. Recommend primary = inner `timeout` +
   `--die-with-parent`; the outer timer is only a backstop.

### B4 (trust-flag) — the honest disposition: redundant inside the sandbox, do not claim it as a live layer

Code Review is right on the mechanism: with `CLAUDE_CONFIG_DIR=/tmp/claude-config`
on an empty tmpfs that resets every session, `hasTrustDialogAccepted` can never
be true inside the sandbox, so `developer_pretooluse.py`'s `PreToolUse` hook —
already skipped in `-p`/print mode when the workspace is untrusted, per the
hook-invocation investigation — never fires inside the sandbox. §5 point 1
called shipping the trust-flag write "load-bearing … or the hook layer is
inert." The honest disposition, given everything else this milestone now is:

**The in-sandbox hook layer is genuinely redundant, and we should stop
claiming it as defense-in-depth inside the sandbox — not seed a trust flag to
force it to fire.** The whole reason this milestone moved to namespaces (§2.2)
is that string-pattern `PreToolUse` hooks are defeatable by subprocess
indirection, symlinks, and encoding. Inside the sandbox those bypasses are
*moot* — containment is now structural and kernel-enforced (filesystem/network/
PID namespaces + the broker), which is strictly stronger than anything a
denylist hook could add. A redundant weaker layer that also *cannot fire* is
not defense-in-depth; claiming it would be exactly the "overclaim a layer that
can't actually fire" the review warns against. So:

- **Do not add a trust-seed step for the sandbox.** We are not relying on the
  hook inside the sandbox, so there is nothing to make fire. (Separately: the
  hook-invocation investigation established the trust dialog is *skipped* in
  non-interactive `-p` mode, so `claude` runs inside the sandbox without a
  seeded trust flag; if `CLAUDE_CONFIG_DIR` needs seeding for unrelated runtime
  reasons, that is a functional detail for Development, not a containment layer.)
- **Correct §5 point 1 and the `developer.md` persona note.** §5 point 1's
  "must ship in the same pass or the hook layer is inert" is superseded: inside
  the sandbox the hook layer is *intentionally* superseded by the namespace
  containment, not broken-and-fixable. The persona note's "both are real" claim
  must be corrected so it does not present the in-sandbox hook as a second live
  layer — it is not.
- **The trust-flag concern remains real only for the non-sandboxed roles**
  (`qa`/`cto`/`devops`), which stay on native in-process invocation and still
  share the global trust file — exactly what the generalized `trust_flag_monitor`
  (§5 point 4, already shipped and tested) covers. That layer is correct and
  stays. This is the truthful "it can't fire inside the sandbox, and it doesn't
  need to" answer, not a papered-over gap.

This addendum, like the first Correction, goes to Red Team as the required,
non-skippable gate before Development resumes.

---

## Second addendum (Code Review round 3, `ops/reviews/code-review-task023-round3.md`, REJECT) — credential delivery into the sandbox (C2), and the argv fix (C1)

R1's bind-set fix finally let Code Review exec the *real* `claude` binary
through the *real* wrapper, and it found two things the milestone had never
reached before: an argv the CLI rejects outright (C1), and — behind it — that
the sandboxed CLI cannot authenticate, because the credential material it
reads lives at a path the bind set deliberately excludes (C2). Code Review was
right not to prescribe "just bind it": that is an architecture decision about
which secrets a potentially-compromised Developer session may hold, and it is
mine.

Nothing Red Team has already blessed is reopened. The bwrap namespace shape,
the filesystem/PID/network containment results (§1 and the first Correction),
the five-verb broker allowlist with its session-binding and identity-pinning,
the `ai-developer` account, Developer-only scoping, the invocation-model
change, and addendum 1's default-no-network/one-brokered-egress posture all
stand unchanged. This addendum changes exactly one thing: **how the sandboxed
CLI obtains model-API credentials** — and, as a direct consequence, which
transport the model path uses across the already-blessed egress socket. Both
changes are routed through Red Team, not asserted as settled.

### C1 — disposition: keep `stream-json`, add `--verbose`

The shipped exec line passes `--output-format stream-json` without `--verbose`;
CLI 2.1.252 rejects that combination in `-p` mode before any work happens.
Code Review reproduced it two independent ways and the fix is one token.

**Target: `--output-format stream-json --verbose`. Do not switch to `json`.**

The reason is not stylistic. §4.1 step 4 requires the launcher to stream
Developer's tool-call-by-tool-call activity to a watching human *as it is
produced*, and §4.2's entire disclosed ergonomics tradeoff — the human loses
the native inline Task-tool UI but keeps live visibility — rests on exactly
that property. `--output-format json` emits one object after the run
completes; it structurally cannot stream. `agent_runtime.py` uses `json`
correctly, because its callers are the unsupervised zero-tool paths where
nobody is watching and there is nothing to stream to. Matching
`agent_runtime.py` here would silently delete the one property that makes
§4.2's tradeoff acceptable, to save a flag. So the wrapper's deviation was the
right call and only its execution was wrong.

Confirmed against the real binary during this pass: with `--verbose` added and
nothing else changed, `/opt/claude-code/bin/claude` 2.1.252 starts correctly
inside a real `bwrap --unshare-all` sandbox and emits
`{"type":"system","subtype":"init",...,"tools":["Read","Edit","Write","Bash","Grep","Glob","Skill"]}`
with the `developer` agent resolved and cwd set to the worktree.

Two things Development owns alongside the one-token change, because a flag fix
is not the whole finding: the launcher's stdout consumer must be checked
against what `stream-json --verbose` *actually* emits (newline-delimited JSON,
many events per turn, not one terminal object — Code Review's own point that
this must be verified, not assumed), and the check must be run through the real
binary, since a stub `claude` accepts any argv and is what let this survive
three rounds.

### C2 — what I determined empirically, before deciding anything

Addendum 1's credibility came from testing rather than reasoning; the same
discipline applies here. All of the following was run live in this environment
against the real CLI, with throwaway processes and fake credential values only.
**The real credential material was never read, copied, moved, or written
anywhere** — only its path metadata was inspected.

**1. The exact credential path, named precisely rather than as a directory.**
Code Review's bisection localised the failure to "somewhere under
`/home/claude/.claude`." The binary itself is more specific — three hardcoded
absolute path constants:

```js
var T="/home/claude/.claude/remote",
    AOe=`${T}/.oauth_token`, iKt=`${T}/.api_key`, W2=`${T}/.session_ingress_token`
```

These are absolute and are resolved independently of `HOME` and of
`CLAUDE_CONFIG_DIR`. On this host `/home/claude/.claude/remote/` is `0700
root:root` and `.oauth_token` is 108 bytes, `0600 root:root`. That it is the
load-bearing file was confirmed behaviourally, not inferred: with `env -i`,
`HOME` and `CLAUDE_CONFIG_DIR` both pointed at empty scratch directories and no
other credential of any kind, the CLI still authenticated and sent
`Authorization: Bearer <…>` with a total header length of 115 — exactly
`len("Bearer ") + 108`, the oauth token file's own size.

This on its own disqualifies "bind it read-only," before any threat reasoning:
that path is an artifact of *this hosting container's* managed/remote CLI
build, not the credential shape of an ordinary `claude` install (which uses
`~/.claude/.credentials.json` or an OS keychain). Binding it would hard-code an
environment-specific path into the one script named by the sudoers line, and
would be wrong on the production host anyway — the exact objection Code Review
raised, confirmed.

**2. The CLI does not require a credential file to exist.** On the bare host,
`env -i`, empty `HOME`, empty `CLAUDE_CONFIG_DIR`, `ANTHROPIC_BASE_URL` pointed
at a throwaway local HTTP endpoint, and `ANTHROPIC_API_KEY` set to a plainly
fake string: no "Not logged in," no prompt — the CLI went straight to `POST
/v1/messages?beta=true` carrying `x-api-key: sk-ant-FAKE-…` verbatim. Two
consequences, both load-bearing: the **environment variable takes precedence**
over the on-disk token (that run had the oauth file readable and the CLI did
not use it), and the **value is not validated** — any string is passed through
to the wire.

**3. End-to-end, in the real sandbox, with zero credential material inside
it.** First verified that under the shipped bind set both `/home/claude` and
`/home/claude/.claude/remote/.oauth_token` resolve `exists=False` inside the
namespace. Then ran the real `/opt/claude-code/bin/claude` 2.1.252 under real
`bwrap --unshare-all`, with the shipped bind set plus `--verbose`, the shipped
relay shape (in-sandbox loopback → bind-mounted Unix socket),
`ANTHROPIC_BASE_URL=http://127.0.0.1:8889`, and `ANTHROPIC_API_KEY` set to a
non-secret sentinel literal. Result: no "Not logged in." A proper `init` event
with the full tool list and the `developer` agent resolved, then a real `POST
/v1/messages?beta=true`, terminating on my stub's own reply (`API Error: 400
FAKE-API: reached upstream`). Meanwhile the host-side component logged
`sentinel_seen=True swapped=True` and the upstream received the injected
credential (a fake stand-in) instead of the sentinel. **The CLI functioned end
to end with no credential material anywhere in the namespace.**

**4. Host-side TLS re-origination is viable in this environment.** A host-side
Python process opened a genuine TLS connection to `api.anthropic.com:443`
through this environment's ambient agent proxy (`HTTPS_PROXY`, CA bundle
`/root/.ccr/ca-bundle.crt`, per `/root/.ccr/README.md`) and received a real
`401 {"error":{"type":"authentication_error","message":"x-api-key header is
required"}}` with a real `request_id`. The trusted host-side component can
complete the outbound leg; the ambient proxy is not an obstacle to this shape.

**5. A gotcha found only by running it: keep-alive.** My first gateway
rewrote the credential on the first request of each connection. The CLI reuses
connections, and its **second** POST — on the same socket — arrived upstream
still carrying the sentinel. Re-implemented to parse every request on the
connection (request line, headers, `Content-Length` body, repeat), the leak
closed: 2/2 upstream requests carried the injected credential, 0 leaked the
sentinel. **Per-request substitution is a correctness requirement, not an
optimisation**, and it must be a QA assertion across a multi-request session
rather than a single call.

**6. The alternative mechanism, tested rather than speculated about.**
`apiKeyHelper` works inside the sandbox: with `{"apiKeyHelper": "<script>"}` in
the config dir and `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` set, the CLI executed the
script, took its stdout as the credential, and sent it as both `x-api-key` and
`Authorization: Bearer`. The binary also carries `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR`
and `CCR_OAUTH_TOKEN_FILE`. So a short-lived-token broker is genuinely
implementable — which is why it gets a real evaluation below rather than a
hand-wave.

### C2 — the decision

**Chosen: the credential-broker shape, realised as host-side auth injection at
the egress boundary that already exists. The sandbox holds a non-secret
sentinel; the real credential is added host-side and never enters the
namespace.** Concretely:

- `launch_developer_sandboxed.sh` sets `--setenv ANTHROPIC_BASE_URL
  http://127.0.0.1:$EGRESS_RELAY_PORT` and `--setenv ANTHROPIC_API_KEY
  <fixed non-secret sentinel literal>`. The sentinel is a documented constant
  (e.g. `SANDBOX-PLACEHOLDER-NOT-A-CREDENTIAL`), safe to hold in a reviewed
  script in git, because it is not a credential.
- `egress_relay.py` is unchanged in role: loopback → the one bind-mounted Unix
  socket. It remains untrusted-but-harmless for exactly the reason Red Team
  verified (attack angle 3): the sandbox has no other reachable destination, so
  whatever Developer does to the relay changes nothing about what the host side
  will forward.
- `egress_proxy.py` gains a second, model-API-gateway mode alongside its
  existing CONNECT mode: it terminates the plain-HTTP request arriving on the
  Unix socket, substitutes the sentinel credential header for the real one on
  **every** request on the connection, and re-originates over TLS to the
  configured model-API host — chaining through the ambient `HTTPS_PROXY` where
  one is configured — streaming the response back unmodified.
- The real credential lives in a file owned by the proxy's own trusted
  account, `0600`, alongside and under the same rules as the allowlist config:
  **not bind-mounted**, therefore structurally invisible inside the sandbox by
  Red Team's verified property #5, which Code Review re-confirmed this round
  with the file actually present on the host.
- Which header to inject is deployment configuration, not a code constant: a
  Console API key goes out as `x-api-key`, a claude.ai OAuth token as
  `Authorization: Bearer`. The gateway reads the credential *and its header
  form* from the trusted-side config.

**Why not bind the credential read-only — the blast radius, concretely.**
On this host the file is a durable, portable, long-lived bearer credential for
the operator's own account: not scoped to this session, not scoped to this
task, not refreshable-away, and usable by anyone who obtains it, from anywhere.
The tempting counter-argument is "the sandbox's only egress is the model API,
so a stolen token cannot leave." **That argument is false, and this is what
decides the question.** The sandbox has several legitimate, load-bearing
channels that carry attacker-chosen text out to a place a human or another
system will read it: it writes freely into the bind-mounted worktree, whose
contents are committed and pushed; and the broker's `handoff` and
`activity-log` verbs accept free-text fields (`work_completed`,
`known_limitations`, `summary`, `detail`) that land in `operations.sqlite3` and
are rendered into the control-center HTML. Those channels exist *by design* and
cannot be closed without destroying the milestone's purpose. A durable
credential placed inside the sandbox is therefore a durable credential that can
be smuggled out through the work product itself — precisely the class of secret
§2.3 and §6 promised to keep away from `ai-developer`. **Rejected.**

**Why not a short-lived token via `apiKeyHelper`** — the honest version, since
it does work. It is strictly better than binding the durable file: what leaks
is time-bounded. But it is still *a usable credential inside the sandbox*, and
the helper is invoked by the sandboxed process itself, so a compromised session
simply calls it again whenever it wants a fresh one. The TTL bounds the value
of a single captured token; it does not bound the session's access. And it
depends on something this project does not have and cannot build here: an
upstream that mints scoped, short-lived, per-session credentials. Nothing in
the auth model available to us issues a task-scoped API key. So it buys a real
but modest reduction at the cost of a mint/refresh service that does not exist.
**Rejected as the primary; recorded as the correct fallback** if a future
deployment's identity provider does support scoped short-lived tokens — in
which case it *composes* with the chosen shape (the gateway injects a
short-lived credential) rather than replacing it.

**Why not TLS-MITM between the CLI and the gateway.** Keeping HTTPS on the
in-sandbox hop and terminating it with a locally-minted CA trusted inside the
sandbox gives *exactly the same* plaintext visibility to *exactly the same*
component, while adding a CA to mint, distribute, rotate and bind into the
sandbox's trust store. Strictly more moving parts for zero additional security.
Plain HTTP over a host-local Unix socket has the identical property with none
of that. **Rejected as gratuitous complexity.**

**What the chosen shape costs — the real tradeoff, not a free win.** The
gateway must see model-API traffic in the clear in order to inject the header.
That is a genuine change to the trust story Red Team blessed: in addendum 1 the
host-side proxy was a CONNECT tunnel carrying opaque TLS that could not read a
byte of the payload; for the model path it now terminates plaintext and
re-originates, so it can read — and in principle alter — every prompt and every
response. Three points, the third conceded rather than argued away:

- The plaintext hop never leaves the host. It is the sandbox's own loopback
  into a bind-mounted Unix socket, inside the sandbox's netns, which addendum
  1's items 1–2 verified has no interface, route or DNS reaching anywhere else.
  No plaintext crosses a network.
- The component that sees the plaintext is the same trusted, non-`ai-developer`
  account that already owns the allowlist and already decides what the sandbox
  may reach. It is not a new principal in the trust model.
- **It is nonetheless a wider capability for that principal.** A bug or
  compromise in `egress_proxy.py` now reaches prompt and response *content*,
  not just destinations. That raises the review bar for this artifact, and it
  must be stated to Red Team and to the adversarial Security gate in those
  terms rather than presented as equivalent to what was already reviewed.
  (Context, not justification: this environment's own ambient agent proxy
  already re-terminates TLS — `/root/.ccr/README.md`, "TLS is re-terminated
  there" — so the gateway is not the first inspecting intermediary on this
  host. The production host may differ, and DevOps should not assume it does
  not.)

**A consequence that must not be left implicit: the CONNECT path now has no
permitted destination.** With model traffic moved to the gateway, nothing the
sandbox does uses `HTTPS_PROXY` or CONNECT any more, so the allowlist config
becomes *empty by default*. That is a strengthening, not a regression —
general egress is now closed at the proxy as well as at the netns — but it
means two egress mechanisms coexist with only one in use.
**Recommendation: keep the CONNECT path, with an empty allowlist, as
fail-closed reserve surface**; it is reviewed, tested and correct, and deleting
it to re-add it later is churn. But its role must be documented as reserve, and
the QA charter's CONNECT deny-tests (addendum 1 items (c) and (f)) stay,
because an empty allowlist that silently stopped denying would be invisible
otherwise. Whether to keep or delete it is Red Team's to endorse or overturn;
it should not be left ambiguous in code.

This also resolves, by construction, addendum 1's open option-(a)/option-(b)
question for the model path: the CLI is pointed at the relay via
`ANTHROPIC_BASE_URL`, not via `HTTPS_PROXY`, so the "does the CLI accept a
Unix-socket proxy directly" question no longer gates the model path at all —
option (b)'s in-sandbox relay is required and is what ships, verified above
against the real binary. `HTTPS_PROXY`/CONNECT behaviour against the real
binary remains untested and remains relevant only to the reserve path.

### C2 — residual exposure, stated plainly (§6 discipline)

1. **In-session API use by a compromised Developer**, at the deployment's
   expense, through the one permitted channel. Unchanged from addendum 1's
   already-disclosed and already-accepted exfil-via-API residual; the chosen
   shape does not make it worse, and does not close it.
2. **The gateway sees prompts and responses in plaintext.** New, named above.
   This is the price of the credential never entering the sandbox, and the
   Founder should accept it explicitly at Red Team alongside the §4.2
   ergonomics tradeoff and addendum 1's exfil residual — not have it folded in
   silently as an implementation detail.
3. **Spend is not actually contained.** `--max-budget-usd` is enforced by the
   sandboxed CLI itself — the untrusted side. A compromised session can issue
   requests the CLI's own accounting never sees, and the gateway will forward
   them. Real containment would require per-session request/byte counters and a
   hard cut-off *in the gateway*. **Not built, not required by this addendum,
   named so it is not mistaken for covered.** (The wrapper's
   `DEVELOPER_MAX_BUDGET_USD="5.00"` is separately still an unreviewed
   placeholder and stays flagged as one.)
4. **Production auth-shape parity is unverified.** Everything above was
   determined against this container's CLI build and its managed-OAuth
   arrangement. Whether the production deployment authenticates with a Console
   API key (`x-api-key`) or a claude.ai OAuth token (`Authorization: Bearer`),
   and whether that account's organisation permits API-key auth at all — the
   binary carries a "Your organization has disabled API key authentication"
   path — is a **DevOps pre-cutover verification**, in the same slot as §1's
   production-host feasibility re-run and held to the same standard. If the
   production account cannot present a header-injectable credential, this
   mechanism does not apply as designed and the milestone returns to CTO. It
   does not get patched around in code.
5. **Whether the CLI needs any destination besides the model API** was not
   exhaustively determined. My test endpoint saw a `HEAD /api/hello` preflight
   and the `/v1/messages` calls, both against `ANTHROPIC_BASE_URL`, and nothing
   else — but background telemetry that fails silently would not have shown up.
   A verify item for the §7 QA charter, not a claim.

### C2 — implementation targets for Development (after Red Team)

- **`launch_developer_sandboxed.sh`**: add `--verbose` (C1); add the
  `ANTHROPIC_BASE_URL` and sentinel `ANTHROPIC_API_KEY` `--setenv`s. Add **no**
  bind under `/home/claude` or any other credential path, and extend the
  existing fail-closed `case` guard that protects `EGRESS_ALLOWLIST_DIR` to
  cover the new credential-file directory the same way.
- **`egress_proxy.py`**: model-API gateway mode; per-request (not
  per-connection) credential substitution; credential and header-form read from
  a trusted-side `0600` config; TLS re-origination with the system CA bundle,
  chaining through `HTTPS_PROXY` when set; the CONNECT path retained unchanged
  as documented reserve. This is new security-relevant surface that now handles
  secret material — it goes through the full Code Review/QA/Security gates on
  its own merits and must not be waved through as "the same file we already
  reviewed."
- **`egress_relay.py`**: unchanged in role.
- **`ops/reviews/task023-os-provisioning-runbook.md`**: provisioning for the
  credential file (trusted account, `0600`, not bind-mounted, not under any
  bound path), the DevOps auth-shape verification step, and the empty-allowlist
  reserve-path note.
- **`known_limitations` in the next handoff** must stop implying the
  `HTTPS_PROXY` bridge is the only open real-binary question. Credential
  delivery was the thing that failed first, it is now answered by a named
  mechanism rather than a disclosure, and residuals 2–5 above are what belongs
  in that field instead.
- **§7 QA charter additions**: (g) a real sandboxed session authenticates and
  completes a model call with **no** credential file present anywhere in the
  namespace; (h) the credential path (`/home/claude/...` here, the production
  equivalent there) and the gateway's credential config both resolve
  `exists=False` inside the sandbox; (i) the sentinel never reaches upstream —
  asserted across a multi-request keep-alive session, not one call; (j) a
  positive control that the sentinel, if written into the worktree or a broker
  row, is worthless — demonstrating that the exfil path which would have been
  decisive under the bind-it option now carries nothing of value.

Code Review's six non-blocking items from round 3 are unchanged and remain
Development's, alongside the above.

This second addendum, like the first and like the original Correction, goes to
Red Team as the required, non-skippable gate before Development resumes.

---

## Third addendum (QA's TASK-023 FAIL, `ops/reviews/qa-task023.md`) — the permission model (D1), the operational database inside every sandbox (D2), commit and handoff integrity (D3), and the runbook's own smoke command (D4)

QA drove the real `claude` binary through the shipped wrapper against an
upstream scripted to return `tool_use` turns, so the agent made **real tool
calls inside the sandbox** for the first time in this milestone's seven review
rounds. That single methodological step produced four blocking defects, two of
which falsify claims *this document* makes. QA is right on all four, and right
that §4.2 named D1 as "a required empirical verification item, not assumed
either way" and it was never run. This addendum decides each one.

**Two of QA's findings falsify my own text, and I am correcting the text, not
softening it.** §3 point 1 and §6 bullet 6 said `operations.sqlite3` "is never
present inside the sandbox." Under §4.4's own mandated per-task git worktree it
was present, read-write, in every conformant sandbox, and QA forged a
`review_results` row claiming a Red Team PASS and flipped `risks.id=3` to
`resolved` through it. That is both halves of Red Team's original Finding 1,
reached by routing around the broker rather than bypassing it, through the one
path §4.4 *requires* to be bound. The claim was false from the day §4.4 was
written.

Nothing Red Team has blessed is reopened. The bwrap namespace shape, §1's
containment results, the five-verb broker allowlist with its
session-binding/identity-pinning, the `ai-developer` account, Developer-only
scoping, addendum 1's default-no-network/one-brokered-egress posture, and
addendum 2's credential-gateway contract (`red-team-task023-addendum2-review.md`
§4, C1–C10 plus the spend ceiling and path allowlist) all stand unchanged —
QA re-verified every one of them live and they all passed.

### Method — everything below was run, not reasoned about

Throwaway processes only. No `useradd`, no sudoers edit, no persistent
privileged daemon. **No real credential material was read, copied, moved or
exposed; every credential in every run is a fake literal and no request left
this host** (every upstream was a local throwaway serving scripted Anthropic-
shaped SSE). All git experiments ran in a **clone** of this repository under the
session scratchpad, never against the live repo. The live
`ops/db/operations.sqlite3` is byte-identical before and after
(`5df1db1d10466274bf0df8c395b88dcb`); the broker experiments used a *copy*.
`git status` is clean apart from this document, `git worktree list` shows only
the main worktree, `/run/ai-pipeline` and `/etc/ai-pipeline` do not exist, and
no daemon is left running.

The rig: a throwaway SSE upstream serving scripted `tool_use` turns, the real
`/opt/claude-code/bin/claude` 2.1.252, the **shipped** `egress_relay.py`, the
**shipped** `opsdb_broker.py` against a copy of the database, a dumb Unix-socket
byte-forwarder standing in for the gateway's socket end (the gateway's own
contract is not what is under test here — QA verified it live), and a real
`bwrap --unshare-all` sandbox whose bind set is the shipped wrapper's.

### 0. The finding that reframes D1: the CLI's permission layer sits *inside* the untrusted boundary

Before deciding what to grant, I had to know what a grant is worth. Three
results, all run:

1. **A partial grant is self-widening.** With `--allowedTools "Bash Edit Write"`,
   the session wrote `.claude/settings.local.json` into its own worktree with an
   ordinary interpreter one-liner
   (`python3 -c "open(<char-encoded path>,'w').write('{}')"`), and a worktree
   `.claude/settings.local.json` granting `Bash`/`Write` is honoured by the CLI
   (verified separately: with **no** argv grant at all, that file alone made the
   same denied calls succeed). The CLI does carry a dedicated `safetyCheck` that
   refuses `Write`, `cp` and shell redirection to settings files — and that check
   is a *string-pattern* layer, defeated by the interpreter indirection above.
   This is precisely the bypass class §2.2 and §3 use to reject hook-based
   options, reproduced against the CLI's own permission layer.
2. **The floor is real, though.** At *zero* grant the session could not write
   anywhere — `ls > inside.txt`, `touch inside2.txt`, `cp`, `printf >` and
   `python3 -c` are all denied. So the shipped configuration is not
   self-escapable; it is simply a configuration in which Developer can do
   nothing. There is no "small safe grant": the reachable states are **useless**
   or **complete**.
3. **A deny in argv is not widenable by a worktree file.** With
   `--settings '{"permissions":{"allow":["Write"],"deny":["Bash"]}}'` and a
   worktree file allowing `Bash`, the tool came back "Bash is disabled for this
   session, in subagents as well as here." Recorded as a fact for future use;
   **not relied on**, because per (1) it is one layer of the same
   pattern-matching kind this milestone exists to stop trusting.

**Therefore: the CLI permission layer is capability *enablement*, not
containment, and this document will not cite it as a layer anywhere.** The
containment is the namespace, the two brokers, and the bind set — and QA
already evaluated every one of those *with the permission layer entirely out of
the loop* (their `insandbox.py` probes executed arbitrary code inside the shipped
bind set with no CLI in the path). Everything in §6 that survived QA survived at
"full tool permissions." Granting them therefore costs nothing against the
threat model **once D2 and D4 are fixed** — and that conditional is the whole
point: D2 is exactly a capability that a fully-permitted session inherits.

### D1 — decision: an explicit, complete, argv-delivered grant, and a launcher that stops calling a denied session a success

**The grant.** `launch_developer_sandboxed.sh` adds one fixed argv element:

    --allowedTools "Bash Edit Write"

alongside the existing `--tools "Read,Edit,Write,Bash,Grep,Glob,Skill"`.
`Read`/`Grep`/`Glob` need no grant. Verified end to end: with this flag and
nothing else changed, a real sandboxed session ran `python3 -c`, created a file
in the worktree, and reached the broker (below). Without it, every one of those
is `permission_denied`.

**Why argv is the un-widenable delivery.** The wrapper is the fixed,
root-owned, sudoers-named script; the sandboxed uid cannot edit it, and the
grant is a command-line element, not a file the sandbox can reach. This is the
same discipline as the egress allowlist (`/etc/ai-pipeline`, not bind-mounted):
the policy lives where the untrusted principal cannot get at it. Per §0 the
sandbox can still *widen itself* via a worktree settings file — which is
survivable only because the grant is already complete, and which is contained
by D3's guarded-path commit check (a `.claude/**` change never leaves the
sandbox).

**Why not `--permission-mode bypassPermissions`.** It works — I confirmed
QA's incomplete observation in both directions: at euid 0 the CLI refuses
outright (`--dangerously-skip-permissions cannot be used with root/sudo
privileges`, exit 1), and at euid 65534 (an unprivileged stand-in for
`ai-developer`) it is accepted and the same calls succeed. But it is
uid-conditional, so the wrapper's behaviour would differ between the intended
deployment and every posture this project can actually test — `known_limitations`
#7 says the chain still cannot run as `ai-developer`, which would make the
milestone's central flag structurally unverifiable here. `--allowedTools`
behaves identically at both uids (verified at 0 and at 65534). It is also an
*enumeration*: a tool this design never granted stays denied instead of being
swept in by a blanket bypass. **Rejected in favour of the enumeration.**

**Why not the other modes.** `acceptEdits` allows Write/Edit but leaves `Bash`
denied — Developer cannot run a test. `dontAsk` denies everything with a
politely-worded refusal. `auto` allows Write but routes every `Bash` command to a
**model-side safety classifier**, which means an extra model call per command
through the credential gateway (spend and latency the ceiling must absorb) and a
fail-*closed*-on-unavailable behaviour I observed directly ("Classifier
unavailable … so auto mode cannot determine the safety of Bash"). Not a
containment layer for our threat model (the classifier judges intent, not
capability) and a new dependency on an upstream we deliberately treat as the
only permitted destination. **Rejected.**

**Why not a `.claude/settings.local.json` seeded into the worktree.** It works
(QA proved it), but it lives inside the bind-mounted, sandbox-writable worktree,
so the untrusted side can rewrite the file that describes its own permissions,
and — worse — a host-side commit would ship that rewrite into the repository.
**Rejected.** This is also consistent with addendum B4's decision not to seed a
trust flag: we do not place policy artifacts inside the sandbox to make a layer
appear to work.

**Consistency with B4.** B4 said the in-sandbox `PreToolUse` hook is not a
layer. §0 now says the same about the CLI permission layer. Both are
string-pattern mechanisms living inside the untrusted boundary; the honest
posture is to stop counting them and keep the kernel-enforced ones.

**Stopping a denied session from looking like a success.** A real session in
which `Write`, `python3 -c` and every meaningful command were denied still ended
`{"type":"result","subtype":"success","is_error":false}` with exit 0
(reproduced). That is a reporting defect independent of the grant, and it must
be fixed regardless, because it is what hid D1 for seven rounds.
`launch_developer_session.py` currently pumps the child's stdout as raw bytes
and never inspects it. It must **tee** the stream (still forwarding every byte
live, per §4.1 step 4) and parse the NDJSON it already receives:

- count `{"type":"system","subtype":"permission_denied"}` events (`tool_name`
  recorded for each);
- require exactly one terminal `{"type":"result",...}` event, with
  `subtype == "success"` and `is_error == false`;
- ask the broker, at `end_session`, how many verbs were served for this
  session's token (a new counter in the reply — the broker is trusted and
  already keeps the session record);
- check host-side whether the worktree changed at all
  (`git -C <worktree> status --porcelain -uall`).

`ok` becomes: exit 0 **and** a terminal `result` event **and**
`subtype == "success"` **and** `is_error == false` **and**
`permission_denied == 0` **and** (broker verbs served > 0 **or** the worktree
changed). Any failure is reported with its own message — a
`permission_denied`-riddled run must say *"the sandboxed session was denied N
tool permissions; the grant is misconfigured"* and return non-zero, never
"success". The counts belong in the returned dict and on stderr, so a watching
human sees them without reading the stream.

### D2 — decision: the per-task worktree is materialised with the database excluded, and the sandbox never gets a git object store

QA's defect is exact and its root cause is one line of §4.4 colliding with one
line of `git ls-files`. The decision has three parts, and a fourth that QA could
not have found because D2 was masking it.

**(a) Materialisation: a sparse per-task worktree that never writes the file.**
The launcher creates the worktree as

    git worktree add --no-checkout -b <task-branch> <path> <base-sha>
    git -C <path> sparse-checkout init --no-cone
    printf '/*\n!/ops/db/operations.sqlite3\n' > <path>/.git-worktree-info/sparse-checkout   # per-worktree
    git -C <path> checkout

Verified on git 2.43.0 against a clone of this repository:

- `ops/db/operations.sqlite3` **is never written to disk** in that worktree,
  while `ops/db/opsdb.py`, `schema.sql` and the rest of `ops/db` are present and
  intact — the sandbox needs those and keeps them.
- The sparse configuration lives in the **per-worktree** config
  (`config.worktree`, with `extensions.worktreeConfig=true` set on the
  repository), so the main working tree is untouched: its own
  `operations.sqlite3` was still present and unmodified throughout.
- `git status` in the sparse worktree is **clean** — the excluded path carries
  the `skip-worktree` bit (`git ls-files -v` → `S`), not a phantom deletion.
- A host-side `git add -A && git commit` in that worktree **preserves the
  database blob** at the new commit (921600 bytes, byte-identical) and does not
  record a deletion. This was the failure mode I was most worried about and it
  does not occur.
- Git supplies a **second, independent** fail-closed behaviour: if the file
  reappears at that path (a hostile or accidental write from inside the
  sandbox), `git add` — *including `git add -f`* — refuses to stage it ("paths
  … exist outside of your sparse-checkout definition … will not be updated in
  the index") and the commit does not carry it. A doctored database cannot ride
  out on the branch a human merges. Reproduced with a real forged SQLite file
  written at that exact path.

**(b) Enforcement: the wrapper refuses to launch, generically and fail-closed.**
Sparse checkout is a *materialisation-time* decision, not a runtime control —
if a worktree is ever created without it, nothing at runtime notices. So the
sudoers-named wrapper (which is independently invocable, as QA demonstrated by
calling it directly) gains a pre-launch guard that refuses, with a distinct exit
code, when:

1. the worktree contains this wrapper's own repository (i.e. it *is* the live
   repo root — D4);
2. `<worktree>/.git` is a **directory** rather than the linked-worktree *file*
   (a full clone, or the repo root: the object store and `.git/hooks` must never
   be inside the sandbox — see D3);
3. **any file anywhere under the worktree begins with the 15-byte `SQLite
   format 3` magic** — not a path match, so it also catches a renamed copy, a
   hardlink, or a future tracked database this document never anticipated;
4. credential material (`.founder_credential*`, `.credentials.json`) is present
   under the worktree.

Prototyped and measured on this host: **0.72 s** over the repository's 290
tracked files. All five cases behave correctly — the live repo root refuses on
(1); a conformant-but-non-sparse §4.4 worktree (exactly QA's D2 shape) refuses
on (3) naming the file; the sparse worktree is accepted; a database copied in
under an innocent name (`docs.dat`) refuses; a planted credential file refuses.
The launcher performs the same check plus a positive assertion that
`git ls-files -v ops/db/operations.sqlite3` reports `S`, so a broken
materialisation is caught by the component that did the materialising as well as
by the one that opens the sandbox.

**(c) Why not the alternatives — each was considered against "what if it
silently stops working".**

- **Stop tracking the database in git.** Rejected as the primary. It does not
  actually close the exposure it appears to: 178 commits in this repository's
  history touch `ops/db/operations.sqlite3`, so every historical blob remains
  reachable to anything holding the object store; closing it properly would mean
  rewriting the history of a pushed GitHub repository. It also changes how this
  project stores state (the database would no longer travel with a clone, and
  restore-from-clone disappears) for a benefit the sparse worktree already
  delivers. The git-readable mirror convention is unaffected either way —
  `DECISIONS.md`/`CURRENT_STATUS.md` are the human-readable mirrors and they are
  generated, tracked text. **If the Founder wants the database untracked for
  other reasons (binary merge conflicts, repository hygiene), that is a separate
  decision record, not a prerequisite of this milestone.** It *would* become a
  prerequisite if this project ever wanted a working git inside the sandbox —
  see D3.
- **Post-materialisation removal (`rm` after a full checkout).** Works, and is
  the fallback for a deployment whose git predates sparse-checkout (< 2.25), but
  it writes the real database to a group-writable path first and then depends on
  a cleanup step; it also loses git's own refusal-to-stage. Recorded as the
  documented fallback, with the same wrapper guard on top.
- **`skip-worktree` alone.** Weaker: the file is already on disk when the bit is
  set, and I observed `git add -A` **clearing** the bit on a reappeared file.
- **Shadowing the path inside the namespace with `--ro-bind /dev/null
  <worktree>/ops/db/operations.sqlite3`.** This works — with the real database
  present in the worktree, `sqlite3.connect` inside the sandbox failed "unable to
  open database file" while `ops/db/opsdb.py` stayed readable. Rejected anyway:
  when the exclusion *has* worked, bwrap creates the missing mount point, leaving
  an empty `operations.sqlite3` in the worktree host-side and making
  `os.path.exists` true inside the sandbox — reintroducing, as residue, the very
  file whose absence is the property. And a mitigation that lets a
  mis-provisioned worktree run is not fail-closed. Recorded as tested-and-
  rejected so the next reader does not re-derive it.

**(d) A new blocking defect this fix uncovers — `opsdb.py` cannot reach the
broker when the database is genuinely absent.** `opsdb.py`'s `main()` runs

    if args.command != "init" and not DB_PATH.exists():
        raise SystemExit(f"error: {DB_PATH} does not exist — run `opsdb.py init` first")

**before dispatch and without consulting `_broker_enabled()`.** So in the state
§3 point 1 always described — the file absent from the sandbox — *every* broker
verb dies before the broker is contacted. Verified directly: with `OPSDB_PATH`
pointed at a non-existent file and `OPSDB_BROKER_SOCKET`/`OPSDB_BROKER_TOKEN`
set, both `activity-log` and `handoff` exit 1 with the "does not exist" message.
**The broker write path has only ever worked because of D2.** Fixing D2 without
this would replace "the database is in the sandbox" with "Developer cannot
record anything," and the next QA round would find it. Development must gate that
check on `not _broker_enabled()`, and give the *excluded* verbs a broker-specific
message ("`query` is not available in a sandboxed session") instead of a
misleading instruction to run `opsdb.py init`.

**(e) Proof that the whole shape works — one real end-to-end run.** Real
`claude` 2.1.252, real `bwrap --unshare-all` with the shipped bind set, the
sparse worktree, the shipped `egress_relay.py`, the shipped `opsdb_broker.py`
against a copy of the database with a launcher-registered session token, and the
D1 grant. Scripted tool calls, and what came back:

| tool call from inside the sandbox | result |
|---|---|
| `ls -l ops/db/operations.sqlite3` | `No such file or directory` |
| `os.path.exists('ops/db/operations.sqlite3')` | `False` |
| `sqlite3.connect('file:…?mode=rw')` | `unable to open database file` |
| `find / -xdev -name '*.sqlite3'` | **nothing, anywhere in the namespace** |
| `Write PROBE_E2E.txt` | created, in the worktree |
| `opsdb.py activity-log --task-id 23 …` | **`activity logged`** — landed host-side on task 23 as `developer` |
| `opsdb.py query "SELECT id,title FROM decisions LIMIT 2"` | refused |
| `git status --short` | `fatal: not a git repository` (D3) |

§3 point 1 is now a true statement about a running system for the first time in
this milestone, and it is true *while* the broker write path works.

### D3 — decision: no git inside the sandbox; the launcher commits host-side, and the handoff SHAs come from the trusted side

QA is right that "commit within the worktree" is structurally impossible as
built. It should stay impossible. Two escalations I verified make the obvious
fixes unacceptable:

- **Binding the gitdir is host code execution.** A linked worktree's `.git`
  file points at `<repo>/.git/worktrees/<name>`, whose `commondir` is the main
  `.git` — so making git work inside the sandbox means binding the object store
  *and* `.git/hooks`. I wrote a `pre-commit` hook into a repository's shared
  `.git/hooks` and it executed on the next commit made **in a linked worktree**,
  as the committing user (uid 0 in my test). A sandbox with a bound gitdir can
  therefore run arbitrary code as the Founder the next time the Founder runs any
  git command. **Disqualifying.**
- **A sandbox-owned clone is host code execution too, on *read*.** The
  "give the sandbox its own self-contained repository and fetch from it
  host-side" option fails the same way: I set `diff.external` in a repository's
  `.git/config` and a plain host-side `git -C <repo> diff HEAD~1 HEAD` executed
  it. Any git command run against a gitdir the sandbox can write is arbitrary
  execution — `diff.external`, `core.pager`, `core.fsmonitor`, `alias.*`.
  **Disqualifying**, and it also cannot work at all unless the database is
  untracked *and* the history rewritten (§D2(c)): a clone's object store
  reconstitutes the database from HEAD in one command — I did it,
  `git cat-file -p HEAD:ops/db/operations.sqlite3` yielded a working 22-table
  database with all 81 `review_results` rows. **This is the fact that couples D2
  and D3: excluding the file from the checkout is worth nothing if the sandbox
  holds the objects.**

**Chosen shape.**

1. The sandbox has **no `.git` and no git**. The linked-worktree `.git` *file*
   stays (harmless — it is a pointer to a path that does not exist in the
   namespace), and `git` in the sandbox fails as it does today. The transcript
   must say so plainly instead of instructing Developer to run `git rev-parse`.
2. `launch_developer_session.py` records `base_commit_sha` **before** the
   sandbox starts (it created the worktree at that commit), on a per-task
   branch created by `git worktree add -b`.
3. When the session ends, the launcher, host-side, as the Founder's user:
   runs the **guarded-path check** — refuse to commit, loudly, if the session
   touched `.claude/**`, `.ai-pipeline-session/**`, `ops/db/operations.sqlite3`
   or `.gitignore` (prototyped; correctly flagged a planted
   `.ai-pipeline-session/broker-token` in a real worktree) — then `git add -A`
   and commits, and records `head_commit_sha`.
4. **The handoff's commit SHAs stop being client-supplied.** The broker forces
   `task_id` and `from_agent` already; `base_commit_sha`/`head_commit_sha` join
   them as broker/launcher-supplied values (the broker stores the handoff with
   them null; the launcher, which has ordinary direct database access because it
   is *not* sandboxed, fills them in immediately after the commit). This is
   strictly better than what the design asked for: the SHAs now come from the
   trusted side rather than from a session that could report any value.
   `assemble_developer_transcript()` must stop telling Developer to pass them.

Verified end to end on a real sparse worktree with a real branch: base
`8874fae…` → sandbox writes → guarded-path check → commit → head `3790a7d…`,
`git diff --stat base head` shows exactly the two files the session wrote, the
database blob is intact at the new commit, and the branch is visible from the
main repository for a human to review and merge.

**The cost, stated plainly.** Developer loses `git status`, `git diff` and
incremental commits inside the sandbox. That is a real ergonomic loss on top of
§4.2's, and it is the price of not handing a hostile-by-assumption principal a
gitdir. Two mitigations, both cheap: the launcher passes the base SHA and the
task branch name into the prompt so Developer knows where it stands, and the
launcher can render the post-session `git diff` into the handoff transcript the
Code Review poller already assembles. If in-sandbox git is ever judged
necessary, the prerequisite is not a bind — it is untracking the database *and*
rewriting history, and it is a new decision.

### D4 — decision: the runbook is wrong and the wrapper must refuse the repo root

`--worktree-path /home/user/AI-Pipeline` binds the live repository read-write
and puts the live database and `.founder_credential.json` inside the sandbox.
QA read the credential file's contents from inside. Both changes:

- **The runbook's §7 smoke command is corrected** to create a real per-task
  sparse worktree first and pass *that* path, with the ownership steps from
  step 2 applied to it. No procedure in this project may instruct an operator to
  bind the repository root.
- **The wrapper refuses it**, via D2(b) guard clauses 1, 2 and 4 — verified: the
  live repo root is refused in 4 ms on the "contains this wrapper's own
  repository" test, before any scan.
- **§6's claim that `.founder_credential.json` is "closed twice, independently"
  is corrected.** Under the runbook's own command exactly one of the two layers
  existed, and the one that existed (`0600` founder ownership) is the one §2.2
  calls the *second*. With D4 fixed the claim becomes true again, and it now says
  so conditionally: *closed twice given a conformant per-task worktree; the
  wrapper refuses non-conformant ones so the namespace layer cannot be silently
  absent.*

### Dispositions for QA's nine non-blocking findings

- **N1 — no broker rate/size ceiling (909 KB → 11.4 MB in 0.1 s): FIX NOW.**
  Red Team made the gateway ceiling binding with the argument that "a compromised
  session can currently spend the operator's account without limit, and the
  gateway is the only place a limit can exist." The identical argument applies to
  the broker and the host's disk, and the broker is the only place *that* limit
  can exist. Required: per-session ceilings on rows written and cumulative
  request bytes, plus a per-field length cap on the free-text fields
  (`summary`/`detail`/`work_completed`/`known_limitations`), fail-closed with an
  explicit "ceiling reached" error and a log line. Key them on the **session
  token**, which — unlike the gateway's case — is un-mintable by the sandbox
  because `register_session` is `SO_PEERCRED`-gated (this is why N5 must be fixed
  in the same pass). Numbers are starting values needing the same sign-off as
  `DEVELOPER_MAX_BUDGET_USD`.
- **N2 — 7.9 GB RAM-backed sandbox tmpfs: FIX NOW.** One flag, verified:
  `--size <bytes> --tmpfs /tmp` yields exactly the requested size (256 MiB in my
  test) instead of half of host RAM. Ship it with a placeholder value (1 GiB
  suggested) carrying the same "not a reviewed number" disclosure, and a QA
  assertion that a real session fits inside it.
- **N3 — unbounded broker hold-open DoS: disclosure FIX NOW, concurrency FIX
  LATER.** QA is right that "can still serialize others up to the timeout"
  understates "can deny the broker to every other caller indefinitely"; the
  docstring, the B1 disposition text and `known_limitations` must say the
  accurate thing. Mechanism: add a short first-byte deadline (≈2 s, distinct from
  the existing whole-connection timeout) now, which bounds what one hostile
  connection costs; real concurrency is deferred because the broker is
  low-QPS and single-tenant today — but it must be revisited *before* two
  concurrent sandboxes are ever supported, because at that point this becomes
  cross-tenant denial rather than self-denial. Named in `known_limitations`.
- **N4 — `.ai-pipeline-session/` not gitignored: FIX NOW.** One `.gitignore`
  line, plus it is already covered by D3's guarded-path commit check, plus the
  launcher's existing `rmtree` in `finally`. Three independent reasons the
  capability token cannot reach a commit; the `.gitignore` line is the cheapest
  and goes in.
- **N5 — identity-pinning depends on the sandbox's uid differing, unchecked:
  FIX NOW.** Adopt the cleaner inversion of QA's suggestion: the broker already
  receives `peer_uid` in `handle_request`, so require `register_session`/
  `end_session` from a peer **in** the trusted set and the five task verbs from a
  peer **not** in it. A single-account deployment then fails loudly at the first
  call instead of silently letting the sandbox mint tokens for any task. The
  wrapper additionally refuses to launch when its own euid is in
  `OPSDB_BROKER_TRUSTED_UIDS`. Note the testability cost honestly: this makes the
  all-as-one-uid posture every review round has used unrunnable, and QA will need
  two uids (`nobody` is available and sufficient, as QA's own two-uid gateway
  proof shows).
- **N6 — raw tracebacks on config-load failure: FIX NOW.** Catch
  `ValueError`/`JSONDecodeError` in `main()` and print the (already well-written)
  message alone. Trivial, and the 13 fail-closed refusals are worth presenting
  properly.
- **N7 — CONNECT reserve path not charged against the spend ceiling: FIX NOW.**
  Moot today with `allow: []`, which is exactly why it should be fixed now: the
  day a destination is added, that traffic would be both uncapped and
  content-opaque, and nothing would announce it. One call to
  `_session()`/`_charge()` in the CONNECT branch, plus a line next to the C9
  discussion.
- **N8 — two false statements in `developer.md`: FIX NOW**, as part of the
  honesty corrections below. Note that D2 makes the first one true and D2(d)
  makes the second one *wrong in a new way* if copied verbatim: the five broker
  verbs must **not** fail with "does not exist."
- **N9 — `known_limitations` #4 (endpoint set): CORRECT THE TEXT, DO NOT NARROW
  THE ALLOWLIST.** QA enumerated 55 gateway requests across two real tool-using
  agent loops and saw only `POST /v1/messages?beta=true` and
  `CONNECT api.anthropic.com:443` (denied, harmlessly). The disclosure should
  record that determination rather than continuing to say the set is unknown. The
  configured `allowed_paths` stays a superset: a missing path is a hard `403`
  that breaks a session, and QA's runs are evidence about *these* runs, not a
  proof of completeness across compaction, telemetry and longer sessions.

### Suite check 73 — QA is right, and here is what it must assert instead

`test_egress_gateway.py` calls `_peer_session_key()` on the **client** end of an
in-process socket, so `SO_PEERCRED` returns the proxy's own credentials and the
assertion `key == ("uid", os.getuid())` is a tautology. QA's escalation of Code
Review's note is correct: an implementation returning the daemon's *own* uid
would pass check 73 and checks 69–72, because the fork/pid-namespace battery
proves only that the key is not *resettable*, never that it is the *peer's*.

The replacement must assert on the **server** side and must **discriminate**:

1. Drive requests through the real accept path and read the key the daemon
   actually recorded (`proxy._sessions`' key), not a key recomputed on a client
   fd.
2. Drive a second client from a **different** uid — a forked child that
   `setuid`s to 65534 before connecting is enough and needs no account — and
   assert there are now **two** buckets, `{("uid", u1), ("uid", u2)}`, with
   independent ceilings.
3. Assert explicitly that the key for the second peer is **not** the daemon's
   own uid. That is the discrimination check 73 lacks, and it is the one that
   fails against the mutant QA described.
4. If the suite is not running with the privilege to change uid, the check must
   **report itself as skipped**, loudly, never pass silently — the failure mode
   this whole milestone keeps rediscovering.

Runbook §6b also gains the one line Code Review and QA both asked for about the
"table full of exhausted buckets → 429" path.

### Honesty corrections — every statement QA showed to be false

Development applies these as text changes in the same pass:

1. **§3 point 1** ("`operations.sqlite3` is removed from the sandbox's visible
   filesystem entirely … fails with 'no such file'") — was **false as built**
   for every conformant §4.4 worktree. It becomes true only with D2(a)+(b), and
   the sentence must now read as a property *enforced by* the sparse
   materialisation and the wrapper's fail-closed guard, naming both, rather than
   as an unexplained assertion.
2. **§6 bullet 6** ("Raw `sqlite3`-CLI/file-level access … the file is never
   present inside the sandbox") — same falsification, same correction. It must
   also stop implying the `sqlite3` CLI's absence matters: QA confirmed the CLI is
   not on `PATH`, and confirmed the Python module is — the module was the vector,
   exactly as §3 predicted and §6's wording obscured.
3. **§6 bullet 2** (`.founder_credential.json` "closed twice, independently") —
   false under the runbook's own §7 command, where the namespace layer was
   simply absent. Corrected per D4, conditioned on a conformant worktree that the
   wrapper now enforces.
4. **§4.4** — the bind-set bullet must state that the worktree is a *scrubbed,
   sparse* worktree with the database excluded, that the gitdir is deliberately
   **not** bound, and why (D3's two verified escalations).
5. **§4.2** — its "the human, watching the stream, manually intervenes" fallback
   is **not available** and must be deleted. QA established that interactive
   "ask" does not exist in `-p` mode, the default is *deny* rather than ask, and
   there is nothing to intervene in: the call fails and the model moves on. The
   section must instead point at D1's explicit grant and at the launcher's new
   denial accounting.
6. **§7 item 7(a)** ("commit within the worktree") — structurally impossible and
   deliberately staying so; replaced by D3's host-side commit and the
   trusted-side SHAs.
7. **`.claude/agents/developer.md`** — line 57's "`operations.sqlite3` is not
   present in your filesystem at all" becomes true with D2 and stays. Line 63's
   "every other `opsdb.py` command (including `query`) will fail with a clean
   'does not exist' error" must be rewritten: with D2(d) fixed, the *five* broker
   verbs work and everything else fails with an explicit
   "not available in a sandboxed session" message. The persona note must also say
   that `git` does not work inside the sandbox, that the launcher commits the
   work host-side on a per-task branch, and that Developer must **not** try to
   supply commit SHAs to `handoff`.
8. **`opsdb_broker.py`'s docstring and addendum B1's text** — "a hostile client
   can still serialize others up to the timeout" understates an unbounded denial
   (N3). Say what is true.
9. **`known_limitations`** — must stop being silent about the permission model
   (it is not mentioned anywhere in the milestone), the broker's missing ceiling
   (N1), the unbounded sandbox tmpfs (N2) and the uncharged CONNECT path (N7);
   and must carry the new D3 ergonomic loss and the D2 materialisation dependency
   ("a worktree created without the sparse exclusion is refused, not
   silently accepted").
10. **Red Team's two factual corrections** (addendum-2 review §3: the real CLI
    *does* still issue CONNECTs; the recommended empty allowlist was
    incompatible with `AllowlistConfig.load()`'s guard, resolved by C9) have been
    living in runbook §7b only. They are hereby folded into this document, as
    handoff `known_limitations` #9 asked.

### What Development implements (after Red Team)

1. **`launch_developer_sandboxed.sh`** — the `--allowedTools "Bash Edit Write"`
   grant; `--size <bytes>` before `--tmpfs /tmp`; the pre-launch worktree guard
   (repo-root, `.git`-directory, SQLite-magic scan, credential scan) with its own
   exit code; refuse to launch when euid is in the broker's trusted set.
2. **`launch_developer_session.py`** — sparse per-task worktree creation on a
   per-task branch with the `skip-worktree` assertion; NDJSON tee and the
   `permission_denied`/terminal-`result`/broker-verb-count/worktree-changed
   success contract; guarded-path check; host-side commit; base/head SHA
   recording onto the session's handoff row; transcript changes (no git, no
   client-supplied SHAs, base SHA and branch name supplied).
3. **`ops/db/opsdb.py`** — gate the `DB_PATH.exists()` guard on
   `not _broker_enabled()` (D2(d)); broker-specific message for excluded verbs.
4. **`ops/control-center/opsdb_broker.py`** — per-session row/byte/field
   ceilings (N1); trusted-vs-sandbox peer-uid split on the verb set (N5);
   first-byte deadline and corrected DoS wording (N3); verb-count in the
   `end_session` reply.
5. **`ops/control-center/egress_proxy.py`** — charge the CONNECT branch (N7);
   catch config-load exceptions in `main()` (N6).
6. **`ops/db/test_egress_gateway.py`** — the check-73 replacement above.
7. **`.gitignore`** — `.ai-pipeline-session/` (N4).
8. **`ops/reviews/task023-os-provisioning-runbook.md`** — the §7 smoke command
   (D4); the per-task sparse-worktree creation recipe as a numbered step (it is
   currently "a human or a follow-up DevOps change should wire this in", which is
   how D2 happened); a minimum git version (2.25 for sparse checkout; 2.43.0 is
   what was verified here) in the step-0 production-host checks; §6b's one line.
9. **`.claude/agents/developer.md`** — the corrections in item 7 above.

### QA charter additions for the next round

(k) With the shipped argv, a scripted tool-using session **completes real
work** — edit a file, run a test suite, and record both a `task-status` and a
`handoff` through the broker — and **zero** `permission_denied` events appear in
the stream. (l) `ops/db/operations.sqlite3` resolves `exists=False` inside the
sandbox **and** `find / -xdev -name '*.sqlite3'` returns nothing, while
`opsdb.py activity-log` still succeeds — the two must be asserted together, or
D2(d) hides. (m) The wrapper **refuses** a non-sparse worktree, the repo root, a
worktree containing a renamed database, and a worktree containing credential
material — each with its own exit code, and the mutation must be shown to fail
the assertion (the round-5 discipline). (n) A session that is denied a tool
permission makes the launcher return non-zero with a message naming the denial
count. (o) A forged database written at the excluded path inside the sandbox is
**not** staged by the host-side commit. (p) `.claude/**` and
`.ai-pipeline-session/**` changes made inside the sandbox block the commit
loudly. (q) The broker's new per-session ceiling holds against the same
adversarial shape QA used for N1 (20 × 500 KB rows), and the tmpfs is bounded.

### Residual risk, unchanged or newly named

- **Everything §6 already lists as not-closed remains not-closed**, including
  truthful-but-wrong broker rows, namespace escape, Developer's own judgment
  inside its allowed reach, the other six roles, and production-host parity.
- **The permission grant is complete inside the sandbox, by decision.** A
  compromised session has full `Bash`/`Write`/`Edit` within the bind set. That is
  the same reach QA's own probes had when they verified §6's closed vectors, and
  it is the reach the containment is designed for — but it must be stated in
  those words rather than implied by a config file nobody documented.
- **The sandbox can self-widen its own CLI permissions** (§0). Contained, not
  closed: it changes nothing outside the session, and D3's guarded-path check
  keeps it out of the repository.
- **The exclusion is a materialisation-time property with a runtime guard, not a
  kernel-enforced one.** If both the launcher's assertion and the wrapper's scan
  were removed, the D2 exposure returns. That is why the scan is generic
  (SQLite magic, any filename) rather than a single path comparison, and why the
  mutation test in (m) is required rather than optional.
- **Nothing here was run as `ai-developer`** — `known_limitations` #7 still
  stands. The uid-sensitive results above were obtained with uid 65534 as the
  unprivileged stand-in, which is what let me establish that the D1 grant is
  uid-independent and that `bypassPermissions` is not.

This third addendum, like the first two and like the original Correction, goes
to Red Team as the required, non-skippable gate before Development resumes.
