# Red Team re-verification — TASK-023 correction pass (risks.id=3 durable closure)

Re-reviewing `ops/reviews/cto-task023-architecture.md`'s `## Correction (Red
Team's TASK-023 review, review_results.id=73, REJECT)` section (inserted
after §3) and the corrected §6, against my own prior REJECT
(`review_results.id=73`, full text `ops/reviews/red-team-task023-review.md`).
This is an adversarial re-verification, not a re-read of the document's own
prose — every claim below was checked against the live `ops/db/opsdb.py`
source and the live `operations.sqlite3` database, and the PID-namespace
test was independently re-run in this environment rather than taken on the
document's word.

**Verdict: PASS.** Both of my prior findings are genuinely, verifiably
resolved — not merely reworded. One new, narrow, non-blocking evidentiary
defect was found during this re-verification and is disclosed below; it
does not reopen either original finding and does not, on its own, justify
another REJECT.

---

## Finding 1 (prior blocking) — verified RESOLVED

**Independent re-enumeration of `opsdb.py`'s subcommands.** I read
`ops/db/opsdb.py` in full (not reused from my prior review) and counted
every `sub.add_parser(...)` call in `main()`: exactly **29** subcommands
(`init`, `query`, `project-create`, `agent-upsert`, `task-create`,
`task-status`, `task-update`, `task-step-add`, `task-step-status`,
`task-progress`, `run-start`, `run-heartbeat`, `run-end`, `run-reconcile`,
`agent-status`, `risk-add`, `risk-resolve`, `phase-add`, `phase-set-status`,
`message-send`, `activity-log`, `qa-result`, `review-result`, `handoff`,
`approval-create`, `approval-decide`, `decision-record`,
`task-purge-scratch`, `deployment-record`). This matches the corrected
document's own "29 subcommands total" claim exactly. The document's
5-included / 24-excluded split is exhaustive and correct: I checked every
name in both lists against my own enumeration and found no omission, no
duplication, and no name that doesn't exist in the real file.

**`cmd_query` is gone from the broker, and the exclusion is real, not
partial.** `cmd_query` (`ops/db/opsdb.py:68-80`) is unchanged — still a
free-text `SELECT`-only passthrough with no table/row scoping — but it is
correctly listed among the 24 excluded verbs, and the document's reasoning
for dropping it entirely (the launcher assembles the task record into the
prompt before the sandbox starts; nothing in Developer's role doc asks for
a live read) is sound and matches `.claude/agents/developer.md`, which I
re-read and confirms no read-path requirement beyond what §4.1 step 1
already provides.

**Other roles' governance-write verbs are excluded outright, not
re-scoped-with-a-hole.** `review-result`, `qa-result`, `decision-record`,
`risk-resolve`, `approval-create`, `approval-decide`, and
`deployment-record` are all present in the excluded list and, per the
broker's design (an *allowlist* of exactly 5 verbs the broker forwards, not
a denylist over `opsdb.py`'s full surface), a request naming any of them
has no path through the broker at all — structurally different from my
prior finding, where the parenthetical listed them as already inside the
"closed" set.

**Historical-write-pattern claims verified directly against the live
database**, not taken on faith:

```
task_status_history, changed_by_agent='developer', grouped by to_status:
  CODE_REVIEW      11
  IN_DEVELOPMENT    5
  BACKLOG           1

handoffs: 12/12 rows are developer -> code-review
```

This matches the document's cited figures exactly. (See the one caveat on
the `BACKLOG` figure under "New finding," below — the number is right, its
characterization as evidence of legitimate `task-status` usage is not.)

**Session-binding/identity-pinning mechanism is a real, concrete design,
not an assertion.** The `OPSDB_BROKER_TOKEN` (`secrets.token_hex(16)`,
128-bit, unguessable), broker-side session table keyed by that token
(never trusting a client-supplied `task_id`/`agent` field), and
`SO_PEERCRED`-gated registration (registration only accepted from a
connection whose peer UID is the Founder's own or the broker's own trusted
account, never `ai-developer`'s UID) is a coherent, standard, and correctly
reasoned mechanism:

- `SO_PEERCRED` is a real, kernel-verified (not client-spoofable) Linux
  primitive for Unix-domain-socket peer credentials — appropriate use here.
- The fact that `ai-developer` is one shared OS account across all
  Developer sessions does not weaken this: registration is performed by
  the *launcher*, running as the Founder's own user, strictly before the
  sandboxed process (running as `ai-developer`) is ever started — the
  sandboxed process itself can never reach the registration verb regardless
  of how many concurrent Developer sessions share that UID.
- A compromised Developer session cannot forge another concurrent session's
  token: each sandbox gets its own isolated mount/PID namespace (§1), so it
  cannot read another sandbox's environment variables via `/proc`, and
  128-bit tokens are not brute-forceable over a live socket in any
  practical time frame. (I did not find an explicit rate-limit/backoff
  requirement named for the broker's socket-accept loop — worth a Development
  note, but not a blocking gap given the token's entropy.)

**Conclusion on Finding 1**: the corrected design closes both the
schema-wide-read leak and the other-roles'-write-forgery leak. This is an
architecture-level closure, correctly still gated behind Code Review/QA/
Security on the actual implementation per §8 — which the document says
explicitly and does not try to skip.

## Finding 2 (prior non-blocking) — verified RESOLVED, independently reproduced

The corrected §6/Correction text replaces the prior false "verified in §1"
citation with a real, described test (`ps aux`/`ps -ef`, `ls /proc`,
`gdb -p`, `strace -p` against a live host PID, from inside a
`bwrap --unshare-all` sandbox, plus a `$$`/`/proc/self/status` sanity
check that the PID namespace is genuinely remapped, not merely `ps`
failing for an unrelated reason).

I did not take this on faith either — I reproduced it myself, live, in
this same container:

```
$ nohup sleep 300 & echo $!
2521
$ ps -p 2521            # host: real, running
$ bwrap --ro-bind / / --proc /proc --dev /dev --unshare-all \
    --die-with-parent /bin/sh -c 'ps aux; ls /proc | head'
    -> only sandbox-local PIDs 1-4 visible; /proc lists only 1,2,5,6
$ bwrap ... gdb -p 2521 -batch -ex quit
    -> ptrace: No such process.
$ bwrap ... strace -p 2521
    -> strace: attach: ptrace(PTRACE_SEIZE, 2521): No such process
```

This matches the document's described results essentially verbatim (same
error strings, same shape of result, different PID number as expected for
a different run). The correction's §6 wording ("Empirically verified
directly, not inferred from `--unshare-all`'s flag semantics") is now
accurate, not an overclaim.

## New finding (non-blocking): the `task-status` verb's `BACKLOG` allowlist entry is justified by misattributed evidence

The corrected §3 table's third column claims the `task-status` verb's
`to` allowlist (`{IN_DEVELOPMENT, CODE_REVIEW, BACKLOG}`) is "the only
three statuses `task_status_history` shows Developer has ever set
(`CODE_REVIEW` ×11, `IN_DEVELOPMENT` ×5, `BACKLOG` ×1)." The counts are
correct (verified above), but I traced the single `BACKLOG` row directly:

```
task_id=12, from_status=NULL, to_status=BACKLOG, changed_by_agent=developer,
note='created'
```

`from_status=NULL` and `note='created'` are the signature of
`cmd_task_create`'s own automatic `task_status_history` insert
(`ops/db/opsdb.py:202-206` — every `task-create` call writes exactly this
row shape). This row was produced by the **`task-create`** verb (already
correctly excluded from the broker's allowlist), not by a genuine
`task-status` call moving an existing task to `BACKLOG`. There is, in
fact, **zero** historical evidence that Developer has ever legitimately
used `task-status` itself to set `BACKLOG` — the document's own stated
evidentiary methodology ("the only ... Developer has ever set") does not
actually support including `BACKLOG` in this verb's target allowlist.

**Why this doesn't reopen Finding 1 or rise to blocking**: `task_id` is
still forced to the session's own bound task for every `task-status` call,
so even with `BACKLOG` allowed, a compromised or buggy Developer session
can only push *its own* current task backward, never another task or
another agent's work — there is no cross-task or cross-role reach here,
and no scenario resembling forged governance authority. The practical
blast radius is bounded to "Developer can stall its own task's pipeline
state," which is a workflow/audit-trail concern, not an access-control
one.

**Recommended fix for Development** (does not require another Red Team
pass on its own, but should be corrected before/while building, the same
category as my prior Finding 2): either drop `BACKLOG` from the
`task-status` allowlist since no genuine use case is shown, or correct the
citation to state plainly that the `BACKLOG` figure comes from
`task-create`'s side effect rather than real `task-status` usage, and make
an explicit (not evidence-free) case for keeping it if it's still wanted.

## Secondary observation (non-blocking): `task-status`'s `owner` field passthrough is unrestricted

The `task-status` verb accepts `owner` from the client with no allowlist
or forcing (unlike `to`/`task_id`/`by`). I checked whether `tasks.current_owner`
is used anywhere as an access-control or gating field —
`ops/db/derived_state.py`, `ops/control-center/chief_of_staff.py`, and
`ops/control-center/generate_active_work.py` all treat it as **display-only**
metadata, never as an authorization check. This makes the unrestricted
passthrough low-risk (a compromised session could set a misleading owner
label on its own bound task, a cosmetic-integrity issue, not privilege
escalation) — noted for completeness, not a required fix.

## What I re-checked and still find sound (unchanged from my first review)

The bwrap namespace design, the `ai-developer` dedicated OS account
reasoning, Developer-only scoping (§4.3), the invocation-model change and
its honestly-disclosed "ask"-permission ergonomics gap (§4.2), and the
TASK-017 fold-in reasoning (§5) are all unchanged by this correction and I
have no new objection to any of them.

## Disposition

**PASS.** Both of my prior findings (`review_results.id=73`) are genuinely
resolved, independently verified against the live `opsdb.py` source, the
live database's historical write patterns, and a self-reproduced
PID-namespace/`gdb`/`strace` containment test — not accepted on the
document's own say-so. One new, bounded, non-blocking evidentiary defect
(the `BACKLOG` justification in the `task-status` allowlist) and one minor
non-blocking observation (`owner` passthrough) are disclosed above as
required cleanup items for Development, not grounds for a second REJECT.

Per DEC-011's gate sequence (§8 of the architecture document): CTO
architecture → **Red Team (this review, PASS)** → Development → Code
Review → QA → Security (adversarial) → CTO final conformance. This does
not itself advance the task's status automatically — a human/orchestrator
does that, per this milestone's synchronous-invocation-mode convention
(`ops/reviews/cto-risk3-milestone-architecture.md` §1.3.3/§1.5), and per
this review's own recorded `task-status` write below (recorded on the
reviewer's own authority as an ordinary, non-Founder-authorization gate
transition, the same as any other Red Team PASS in this project).
