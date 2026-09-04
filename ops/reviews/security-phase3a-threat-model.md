# Security threat-model review — Phase 3A (TASK-015): Chief of Staff Founder Interface + Limited Automated Orchestration

Reviewing `ops/reviews/cto-phase3a-architecture.md` (architecture-proposal
stage, pre-implementation, per that document's own framing and the
Founder's stated gate sequence: CTO Architecture -> **Security Threat
Model** -> Red Team -> Development -> Code Review -> QA -> Security
Adversarial Review -> CTO Post-Implementation Conformance). Performed
directly (no subagent-dispatch tool present this session). Read in full
(1225 lines), plus `ops/SECURITY.md`, `ops/control-center/agent_runtime.py`,
`ops/control-center/server.py`, `ops/control-center/founder_auth.py`,
`ops/control-center/meeting_orchestrator.py`, `ops/db/schema.sql`,
`ops/db/opsdb.py`, and `ops/db/derived_state.py` — every substantive claim
below is independently verified against the actual code, not taken on the
CTO doc's word (see "Independent verification" throughout).

`tasks.id=15` confirmed live (`status='BACKLOG'`, title matches). `risks`
table confirmed live: `id=3` ("Bash permissions cannot be scoped below the
tool-category level") is `open`, `owner_agent='cto'`, unchanged — matches
the CTO doc's own stated fact exactly.

## Verdict: REJECT / CONDITIONS

The overall direction is sound and the single most consequential decision
in the document — zero-tool automated Code Review over real Bash grants
for an unsupervised invocation (§B.1) — is correct, and I independently
re-derive rather than merely accept it (see "The central risks.id=3
question" below). But four concrete gaps in the design as specified must
be closed before Development starts. None require new infrastructure,
none touch `risks.id=3`'s own resolution, and all are cheap, specific
fixes to the design as written — the same posture as Milestone 2B4's own
threat-model review, which is the correct analog for this stage.

---

## The Founder's required gate question, answered directly, not superficially

**"The Security threat model must specifically examine how autonomous
operation changes the consequence of agents having Bash access under the
same OS-user principal."**

`risks.id=3` today means: any process running as the Founder's own OS
user — most concretely, an agent invoked with Bash tool access somewhere
else in this system's normal (non-Ask-Agent, non-meeting,
non-Chief-of-Staff) configuration — can read `.founder_credential.json`,
`PTRACE_ATTACH` to `server.py` and read `SESSIONS`/`SESSION_TOKEN` out of
live memory, or forge any CSRF+session-gated POST after reading a served
page's token. Every prior milestone's disclosure of this (2B1 through
2B4, all reread above) frames the *consequence* of that access as bounded
by what a forged request can trigger: flip a decision flag, spend a
capped model invocation, and so on — because until Phase 3A, **every
single thing that ever happens in this system happens in direct response
to an HTTP request the same-OS-user attacker itself would have to send.**
There has never been a clock. Phase 3A changes that in two, not one, ways
that must both be named:

1. **A new, real background actor exists that acts without any request
   at all.** `automation.py`'s poll loop (§B.2) is, confirmed by reading
   `server.py` in full, the first background thread/poller/scheduler this
   codebase has ever had — verified directly, not assumed (grepped for
   `threading.Thread`, `Timer`, `sched`, `schedule` anywhere in
   `ops/control-center/`; nothing exists today outside per-request
   handling and the `ThreadPoolExecutor` `meeting_orchestrator.py` already
   uses for bounded concurrent gathering within one request). This means
   the practical consequence of `risks.id=3` is no longer strictly
   bounded by "whatever a same-OS-user attacker chooses to trigger" — it
   now also includes "whatever the poller decides is eligible on its own,
   on a 20-second cycle, forever, as long as the process runs." A
   same-OS-user attacker doesn't even need to forge a request to get *a*
   real model invocation to run; they only need to get a task into
   `CODE_REVIEW` with a plausible-looking handoff (which they can already
   do today, e.g. via `opsdb.py task-status`/`opsdb.py handoff` directly —
   both are the Founder's own `opsdb.py` CLI, runnable by the same
   attacker class already inside this design's own threat model), and the
   automation acts *for* them, unattended, without them needing to touch
   `server.py` or its session token at all. This is a genuinely new
   *initiation* vector, not merely a new destination for an old one.

2. **The invocation this new actor triggers is, for the first time, one
   that reads real repository content assembled by data-driven,
   `handoffs`-table-controlled Python** (§B.1.2) — a second, independently
   real new surface layered on top of the first. Even though the model
   invocation itself remains zero-tool (verified below), the Python code
   *around* it, running as the same OS user, now walks real filesystem
   paths and shells out to `git` based on database content an attacker in
   this exact threat class (same-OS-user, can already write to
   `operations.sqlite3` via `opsdb.py`) directly controls. This is the
   surface the CTO doc's own §B.1.2 names and mitigates — see the
   stress-test below for whether that mitigation is actually sufficient,
   because it is a **second, independent way `risks.id=3`'s consequence
   increases**, distinct from and additive to point 1.

Both of these are correctly *named* in the CTO doc (§B.1's "Why option
(b) is rejected" passage, and §B.1.2's own framing), and I concur that
neither is closed, narrowed, or claimed to be resolved by this design —
that restraint is correct and should not be walked back. What I require
below is that the *specific* new consequence (an unattended actor with
data-driven filesystem/subprocess access, on a same-OS-user-writable
database, is now real) is stated with this precision in `ops/SECURITY.md`
(draft below), not folded into a generic "consequence increases" line —
because the exact mechanism (a poller reacting to attacker-writable DB
state, no request required) is what a future reader needs to reason about
`risks.id=3` correctly, and it is a materially different shape of risk
than every prior milestone's "an attacker could forge a request" framing.

---

## The six explicit open questions, answered in full

**1. Are the numeric constants reasonable?**
Yes, as *ceilings* — no objection to any of the five values
(`POLL_INTERVAL_S=20`, `MAX_AUTOMATED_INVOCATIONS_PER_TASK=3`,
`MAX_CANDIDATES_PER_CYCLE=5`, `MAX_AUTOMATED_INVOCATIONS_PER_DAY=20`,
`MAX_AUTOMATION_SPEND_USD_PER_DAY=$10.00`). `$10/day` matches the existing
disclosed ~$10 Executive-Meeting worst case already accepted at Milestone
2B3B round 2; the invocation/candidate counts are conservative relative to
`MAX_CONCURRENT_INVOCATIONS=3`. My finding is not with the *values* but
with how they are *enforced* — see Required Condition C2 and Non-blocking
R2 below: the spend/count ceilings are read-then-decide, not
DB-constraint-backed the way the per-event idempotency guard is, so they
hold only under the design's own (correct, but unstated-as-a-requirement)
single-poller-process assumption. Tune-or-not is a Red Team/product
question; the enforcement gap is a Security question and is addressed
below.

**2. Is the zero-tool, Python-assembled-transcript design for automated
Code Review (§B.1) actually sufficient?**
Sufficient for the disclosed, bounded scope — not equivalent to
human-supervised review, and the CTO doc says so plainly, which is the
right way to ship this. On independent scrutiny, yes, there is a real,
realistic class of defect this design would structurally miss: **cross-file
consistency and duplication defects** — a helper reimplemented instead of
reused, an invariant defined in a file outside `files_changed` being
silently violated, a scoping predicate copy-pasted instead of centralized.
This is not a generic "less context is worse" observation; it is the
*specific* defect class this very codebase's own development history has
already produced and had to fix more than once (`agent_runtime.py`'s own
comment on Milestone 2B2's post-implementation review flagging a
copy-pasted scoping predicate as a root cause; `derived_state.py`'s
explicit reason for existing — "the single, shared implementation of every
deterministic-state formula" — is a direct response to this exact failure
mode having happened before). A bounded-context reviewer that only ever
sees the diff's own files cannot catch a Developer quietly reintroducing
that exact class of problem. This does **not** change my recommendation —
the limitation is honestly disclosed, PASS never auto-advances past
`CODE_REVIEW` (a human still decides when to move to `QA`), and REJECT is
the fail-toward-caution direction already — but §B.1.1's disclosure text
should name this specific defect class explicitly (see Non-blocking R4),
not only the generic "cannot explore beyond the assembled bundle" framing,
so a human deciding whether to trust a PASS before manually advancing
knows precisely what wasn't checked.

**3. Is the `base_commit_sha`/`head_commit_sha` handoff-time recording
(§B.13) reliable enough to build on?**
**No — not as specified.** This is Required Condition C1 below, not a
"Red Team should verify" deferral. The two new columns are free-text,
Developer-supplied strings with no format or existence validation before
being passed as positional arguments to a `git diff`/`git show`
subprocess. Two independent problems: (a) nothing confirms either SHA
resolves to a real commit object in this repository before use — a typo,
a SHA from a different clone/fork, or a stale value left over from
`git rebase`/history rewrite would either error at `git diff` time in an
unhandled way or, worse, silently diff against the wrong commit and feed
a *misleading* transcript to the automated reviewer, directly undermining
§B.1's own central claim that the assembled transcript is real and
useful; (b) nothing validates the SHA string's *shape* before it becomes
a positional git argument — a string beginning with `-` could be
misinterpreted as a git option rather than a revision, the same class of
argument-injection risk this project's own convention (fixed argv,
`subprocess.run`, never a shell string) exists specifically to avoid
elsewhere. §B.1.2's careful path validation does not cover this — it
validates `files_changed` entries, not the SHA arguments used in the same
git invocations. See Required Condition C1.

**4. Should `automation_events`/`automation_state` be treated as
Founder-sensitive beyond the existing session gate?**
No. Their contents (task titles, review findings, cost figures, skip
reasons) are the same sensitivity class as `reviews.html`, `meetings.html`,
and `decisions.html` already show today, all already gated by Milestone
2B4's full-app-lock session check applied uniformly to every GET route —
confirmed the new `/automation.html` explicitly follows that same pattern
("session-gated like every other page," §B.5). No incremental gate is
needed; this table introduces no new class of exposed information, only a
new instance of a class this system already protects correctly.

**5. Is "skip silently, discoverable on request" right for all seven
§B.10 scenarios?**
Mostly yes — I do not require a new Founder-visible-flag mechanism (a real
UI surface Phase 3A's own scope discipline correctly avoids inventing).
One non-blocking distinction worth drawing (R6, below): scenario 6
(invalid file path in a handoff) is a stronger signal of a real, possibly
adversarial data problem than the other six routine skips, and deserves
visual distinction on `/automation.html` and in the Chief of Staff's
digest, not a new escalation mechanism. Scenario 7 (found `running` at
startup) already gets a startup print statement via the existing
reconciliation pattern — sufficient, matches precedent.

**6. Should "STOP doesn't kill an in-flight subprocess" be tightened for
Phase 3A?**
No — concur with the CTO's disclosed design as-is. The bound here
(`AUTOMATED_REVIEW_TIMEOUT_S=120`, `$0.50`-capped, at most one invocation
per triggering event) is at least as tight as Ask-Agent's own previously
accepted precedent (Milestone 2B3A, Red Team-reviewed and accepted), and
this is unattended automation acting on code review, not a Founder
actively watching a live conversation — the "emergency" framing is
correctly answered by the bound being small and disclosed, not by
building process-kill machinery this project has twice now (2B3A, and by
extension here) judged unnecessary complexity for what it would buy.

---

## Independent threat-modeling of the new surfaces (per the Founder's required list)

### The central `risks.id=3` consequence question (§B.1) — independently re-derived, not accepted on the CTO doc's word

**Verified the zero-tool baseline claim myself.** Read `agent_runtime.py`'s
`_run_claude()` (the *only* function in this codebase that ever shells out
to `claude`) in full: `--tools ""` and `--strict-mcp-config` are
unconditional in the argv list it builds — there is no branch, no
parameter, no code path in this function that varies these two flags by
`agent_name`. `invoke_agent()`'s own validity check is a plain tuple
membership test (`agent_name not in ASK_AGENT_ALLOWLIST and ... not in
MEETING_PARTICIPANT_ALLOWLIST`) — widening it to also accept
`CHIEF_OF_STAFF_ALLOWLIST`/`AUTOMATED_REVIEW_ALLOWLIST` per the file-list
plan changes *which names are permitted to invoke at all*, never *what
flags a permitted invocation runs with*. This confirms, by direct code
reading rather than by trusting the doc's own claim, that: (a) every
existing invocation in this system's history genuinely has been zero-tool
(there is no code path it could have taken that wasn't), and (b) the Chief
of Staff's and automated Code Review's new invocations structurally cannot
be special-cased into getting more — the mechanism that would have to
change to break this is `_run_claude()`'s own two hardcoded flags, not
anything either new allowlist or new caller controls.

**Does §B.1's reasoning hold up under scrutiny, or is there a gap?** The
reasoning — that Code Review's real job is judgeable from content (diff +
full file content + task metadata), not from open-ended exploration
capability — holds up as a *disclosed, bounded* claim, and correctly does
not overclaim equivalence to a human-supervised session (see open question
2's defect-class finding above). Where I would push back if the doc had
claimed *more*: it does not, and that restraint is exactly right. The
actual gap is not in this reasoning but in two structural details the doc
raises and partially, not fully, closes: the SHA-handling gap (Required C1)
and the per-candidate isolation gap (Required C2) — both concrete,
specified, fixable before Development starts, neither requiring a
different top-level decision than the one §B.1 already made.

### The filesystem-touching poller surface (§B.1.2) — stress-tested

`Path(repo_root, path).resolve()` staying inside `repo_root` **is** a
sound mitigation against the classic traversal case
(`"../../../etc/passwd"`, an absolute path) — `.resolve()` normalizes `..`
components and, critically, *also follows symlinks*, which is the correct
choice here: a malicious symlink placed inside the repo (e.g.
`files_changed` naming an innocuous-looking path that is actually a
symlink pointing at `/etc/passwd` or anywhere outside `repo_root`) is
still caught by the containment check, because `.resolve()` dereferences
it before the check runs. A cheaper mitigation using only
`os.path.normpath()` (no symlink resolution) would **not** catch this —
`.resolve()` is the right primitive, not an interchangeable one.

Is rejecting on a `..` component after normalization redundant with the
`resolve()`-containment check? **Yes, given `resolve()` is already being
used** — a `..` component cannot survive `.resolve()`'s own normalization,
so anything the standalone `..`-component check would reject, the
containment check already rejects too. It is not harmful (defense in
depth, and cheap), but it is genuinely redundant as specified, not an
independent second line of defense catching something the other misses.

**What the containment check does *not* address, and what §B.1.2 leaves
ambiguous**: whether the "full final content of every changed/added file"
is retrieved via `git show <head_commit_sha>:<path>` (reading the
committed blob from git's own object database — immune to a live
working-tree symlink or a TOCTOU race between validation and read, since
git never touches the filesystem symlink at that path when resolving a
tree object) or via a direct Python filesystem read
(`Path(repo_root, path).read_text()` on the live working tree — which
*would* remain exposed to a symlink swapped in between the `resolve()`
check and the actual read, or simply present in the working tree at read
time regardless of what the commit's own tree object says). The doc's
wording doesn't commit to either. See Non-blocking R1: recommend the
design explicitly specify `git show <sha>:<path>` for content retrieval,
which closes this more robustly than path validation alone ever can,
while keeping `resolve()`-based path validation as legitimate
defense-in-depth for the pathspec arguments themselves (which the `git
diff`/`git show` invocations still need validated, non-option-injecting
strings for — see Required C1's `--` separator requirement, which applies
equally here).

**Null-byte injection**: a `files_changed` entry containing an embedded
null byte (`"safe.py\x00../../etc/passwd"`) is not silently accepted —
`pathlib.Path`/`open()` both raise `ValueError: embedded null byte`
immediately, which fails closed by construction (Python's own stdlib
behavior, not something this design has to build). The actual risk here
is not the null byte being exploited — it's whether the *resulting
exception* is handled per-candidate or aborts the whole cycle. See
Required Condition C2.

### Idempotency (`automation_events.trigger_status_history_id UNIQUE`) — verified as a real, DB-enforced guarantee

Traced the actual claim-then-act sequence as specified: the
`automation_events` row (with its `UNIQUE` `trigger_status_history_id`) is
inserted **before** `invoke_agent()` is ever called, inside its own
transaction — the same "reserve exclusivity before spending a real
invocation" discipline `gather_requested_position()`'s own TASK-011 QA
round-2 fix already established (verified by rereading that function in
`meeting_orchestrator.py`: `opsdb.add_meeting_participant()` — the atomic
reservation — runs before `agent_runtime.invoke_agent()`, with an explicit
rollback path (`_release_reservation()`) if the invocation doesn't pan
out; the new design's stated discipline is the same shape). SQLite's
`UNIQUE` constraint makes a second `INSERT` attempting to claim the same
`trigger_status_history_id` fail atomically at the database layer, not by
an application-level race-prone check — this holds **even across two
genuinely independent OS processes** each running their own poller thread
(a real, if edge-case, scenario nothing in this design's own stated
"one poller thread per process" assumption actually prevents at the
process level — see below), because the enforcement is a real SQL
constraint, not an in-memory lock. **No TOCTOU gap exists in the
duplicate-invocation guarantee specifically.** This is correctly the
strongest guarantee in the whole design, and it is verified, not merely
accepted.

### Kill-switch bypass — every write path traced

`opsdb.set_automation_enabled(conn, enabled, reason=None, by="founder")`
is the only function the design proposes to write `automation_state`.
Tracing every other write path in the proposal: the poller (`automation.py`)
only ever *reads* `automation_state` (per §B.2's own description and
§B.10 scenario 5's fail-closed-on-read-error framing); no agent invocation
anywhere in this design (Chief of Staff, automated Code Review, or any
existing Ask-Agent/meeting participant) has a code path that could call an
`opsdb.py` write function directly — the zero-tool guarantee verified
above means none of them could shell out to `opsdb.py` even if they tried,
and none of the *Python* orchestration code (`chief_of_staff.py`,
`automation.py`) is described as ever calling `set_automation_enabled()`.
The schema seeds the row disabled at apply time (`INSERT OR IGNORE ...
VALUES (1, 0, ...)`), and the table's own `id=1` `CHECK` guarantees
exactly one row can ever exist, so there is no way to create a second,
differently-configured row. **As specified, nothing other than the two
new CSRF+session-gated routes can set `enabled=1`.** This holds
structurally as long as Development does not add a second call site to
`set_automation_enabled()` — recommend Code Review treat "grep confirms
exactly two call sites for `set_automation_enabled(`" as an explicit
acceptance check, the same discipline this project already applies
elsewhere (e.g. `agent_runtime.py`'s own comment on centralizing scoping
predicates).

### Spend guard bypass — real, narrow, and must be disclosed (not blocking a code fix, but blocking silence about it)

See Required Condition C2/Non-blocking R2's fuller treatment below. Short
version: the daily spend and per-task/per-day invocation *counts* are
enforced by a read-then-decide pattern (`SELECT SUM(cost_usd) ... ` then,
separately, an `INSERT`), not by a database constraint the way the
per-event idempotency guarantee is. This is correct and race-free under
the design's own stated assumption of exactly one poller thread in exactly
one running server process. Nothing in this system prevents a second
`server.py` process from being started against the same
`operations.sqlite3` file (there is no PID file, no exclusive lock, no
startup check) — if that ever happened, two independent poller threads,
each reading its own view of "today's spend so far," could each
independently decide a new candidate fits under the ceiling and both
proceed, jointly exceeding `MAX_AUTOMATION_SPEND_USD_PER_DAY`/
`MAX_AUTOMATED_INVOCATIONS_PER_DAY` by up to one extra poll cycle's worth
of invocations (not unboundedly — each poller still independently enforces
its own cap on its own next check, so this is a one-cycle overshoot, not
runaway spend). This is the same class of implicit single-process
assumption `SESSION_TOKEN`'s own in-memory, per-process design already
relies on throughout this codebase (already accepted, never previously
required to be enforced by a lock) — I am not requiring new locking
machinery here, only that this specific, previously-unstated assumption be
written down explicitly, the same way every other assumption in this
document is.

### The new Chief-of-Staff invocation (Part A) — verified

**Zero-tool, no special-casing**: verified above (`_run_claude()`'s
hardcoded flags) — this holds identically for `orchestrator` as for every
other allowlisted name; there is no code path that could grant it more
even if the transcript content tried to convince it otherwise (see
prompt-injection trace below).

**`CONSULT:` parsing genuinely never trusted as an instruction**: matches
`_select_participants()`'s/`_parse_selection()`'s existing pattern exactly
— deterministic Python, word-boundary regex, matched only against a fixed
candidate tuple, deciding entirely on its own whether and how to act;
model output is a signal, never an executed instruction. Verified this
holds even under an adversarial framing: if a Founder message (or a
prompt-injected one, e.g. one embedded in stale digest content) tries to
make the Chief of Staff's reply claim "I should get Bash access" or emit
`CONSULT: some-name-not-in-the-candidate-list`, neither has any effect —
the runtime flags are fixed regardless of transcript content (verified
above), and the parser can only ever extract names that literally match
the fixed candidate tuple via regex; a fabricated name outside that tuple
simply never matches, full stop. **One real gap found here, not a
structural one but a specification one** — see Required Condition C3: the
architecture doc's own prose defining the candidate tuple is internally
contradictory ("filtered to `MEETING_PARTICIPANT_ALLOWLIST` minus
`ceo`/`orchestrator`" immediately followed by "CEO is always eligible for
consultation too — allowed through unchanged, same list"). This is
precisely the kind of allowlist definition that must be unambiguous before
Development builds the one function this whole safety property rests on.

### Cost/DoS via chat — real, disclosed-amplification finding

`POST /api/chief-of-staff/ask` carries the identical CSRF+session gate as
every other write route — no new authorization gap. But there is **no
rate limit on the chat messages themselves**, only on what happens
downstream once a message triggers a consult (`MAX_MEETING_PARTICIPANTS`,
`MAX_CONCURRENT_INVOCATIONS`, the `$0.50`-per-call cap bound *one*
meeting's cost, not how many meetings can be triggered per unit time).
This is "more of the same disclosed risk" in the same sense
`ops/SECURITY.md`'s existing "Executive Meetings round 2" section already
frames `POST /api/meetings`/`/followup`'s own lack of a rate limit — not a
new authorization gap, since it still requires the same session+CSRF any
other write does. What is new is the *amplification in convenience*: a
single, ordinary-looking chat message ("what does CTO and Financial
think?") can now trigger the same up-to-~$4 real spend a purpose-built
meeting-creation form previously required a deliberate, separate action to
reach — lowering the friction for the same already-accepted risk class,
not creating a new one. Per this project's own established disclosure
discipline (every "what's different in magnitude, not in kind" passage in
`SECURITY.md`), this needs its own explicit line — drafted below.

### New write functions in `opsdb.py` — injection surface and CHECK-constraint review

Verified `opsdb.py`'s existing convention directly: every write is a
parameterized query; the only two f-string-built SQL statements in the
entire file (`cmd_task_update`'s `SET {set_clause}`, the QA-scratch purge
helper's `FROM {table}`) interpolate only fixed, source-controlled column
and table names drawn from hardcoded Python lists
(`TASK_UPDATE_FIELDS`, `PURGE_CHECK_TABLES`) — never user- or
request-supplied values, and every actual data value in both statements
still goes through `?` placeholders. This is a real, verified, safe
pattern, and the new functions the CTO doc proposes (`set_automation_enabled`,
`create_automation_event`, `end_automation_event`,
`reconcile_stuck_automation_events`, `record_review_result`) all take
structured, typed arguments (ints, bools, fixed-choice enums) with no
described reason to deviate from full parameterization — hold Development
to this existing standard, which the doc does not contradict.

**CHECK constraints**: no existing `CHECK` is altered. `automation_events`/
`automation_state` are new tables; `handoffs.base_commit_sha`/
`head_commit_sha` are new nullable columns added via a plain `ADD COLUMN`
(`handoffs` has no `CHECK` constraint today, confirmed by reading
`schema.sql` — nothing to weaken). `review_results`'s existing
`CHECK (result = 'pass' OR returned_to_agent IS NOT NULL)` is unchanged.

**One required fix, not a new injection risk but a consistency gap**: see
Required Condition C4 — the reject-requires-`returned_to` invariant
currently lives only in `cmd_review_result`'s CLI-argument check
(`if args.result == "reject" and not args.returned_to: raise
SystemExit(...)`), not in any plain function (none exists yet — that's
exactly what this refactor is for). If the extraction doesn't move this
check down into `record_review_result()` itself, `automation.py`'s direct,
in-process calls (never through the CLI, per this codebase's own
established convention for in-process callers) would depend solely on the
schema's own `CHECK` constraint to catch a reject-without-returned_to
call — fail-safe (the write is still rejected), but inconsistent with
every other refactored write function in this file, which all raise a
clear, typed `LookupError`/`ValueError` rather than relying on the schema
to catch a programming error.

### Credential/secret exposure — confirmed clean, not assumed

Reread every code-path description in Parts A and B: nothing touches
`founder_auth.py`, `.founder_credential.json`, `SESSION_TOKEN`, or
`SESSIONS`. The Chief of Staff's state digest reads only
`operations.sqlite3` tables (`risks`, `tasks`, `approvals`, `decisions`,
`task_status_history`, `review_results`/`qa_results`, `deployments`,
`automation_events`/`automation_state`) — none of which, per
`ops/SECURITY.md`'s own stated Phase 0-3 scope, ever contain real
credentials, financial data, or PII in this project. No new logging call
site described anywhere in the proposal writes anything beyond
`type(exc).__name__: {exc}`-style error summaries to `stderr`, matching
every existing pattern in this codebase. One non-blocking consistency
note only — see R5 (transcript-size truncation in error logs).

---

## Required changes (block Development start)

**C1 — Validate `base_commit_sha`/`head_commit_sha` before use.** Before
any `git diff`/`git show` invocation uses either SHA: (a) validate format
(e.g. `^[0-9a-f]{7,40}$`) so a malformed value can never be interpreted as
a git option; (b) confirm each SHA resolves to a real commit object in
this repository (`git cat-file -e <sha>^{commit}`, or equivalent) before
trusting it for a diff; (c) always separate revision arguments from
pathspec arguments with `--` in every git subprocess invocation (`git
diff <base> <head> -- <path1> <path2> ...`), the same argument-injection
discipline `agent_runtime.py`'s own fixed-argv `Popen` call already
establishes elsewhere in this codebase. Any failure routes to the same
fail-closed skip path §B.10 already establishes for scenario 3 (missing
SHAs) — add this as an explicit eighth scenario ("recorded base/head SHA
does not resolve to a real commit in this repository") rather than
leaving it to fall through an unhandled `git` subprocess error.

**C2 — Isolate per-candidate failures inside one poll cycle.** The
pseudocode in §B.2 shows exactly one `try/except Exception` wrapping the
*entire* `_poll_once()` call inside `run_poll_loop()` — correct for
protecting the whole poll thread from dying, insufficient for protecting
one cycle's *other* legitimate candidates from one malformed candidate
(a null-byte path, a `git` error, any other exception during transcript
assembly). `_poll_once()`'s own per-candidate loop body must wrap each
candidate's processing individually: any exception there must (a) mark
that candidate's already-claimed `automation_events` row `failed`/
`skipped` with a concrete reason before moving on — never leave it
silently `running` for `reconcile_stuck_automation_events()` to find only
at the next server restart — and (b) continue to the next candidate in the
same cycle, not abort the batch. This is the same "one bad participant
must not abort the whole meeting" discipline `_gather_position()` already
applies one layer up in `meeting_orchestrator.py`, applied one layer
deeper here.

**C3 — Resolve the `CONSULT:` candidate-list contradiction before
Development builds the parser.** §A.3's own text is self-contradictory
about whether `ceo` is filtered out of or included in the candidate set
the `CONSULT:` parser matches against. This is the one place a
prompt-injection-adversarial safety property (a Founder or adversarial
message cannot make the Chief of Staff trigger a consultation with an
agent outside the approved list) depends on a precise, unambiguous
definition — matching `_select_participants()`'s own existing discipline
of stating its exact candidate list and required format explicitly, not
leaving it to be inferred. State the final tuple exactly before
Development starts.

**C4 — Move the reject-requires-`returned_to` check into
`record_review_result()` itself, not only its CLI wrapper.** Required so
`automation.py`'s direct, in-process calls get the same clear, typed
`ValueError` every other refactored write function in `opsdb.py` raises
for a caller-side contract violation, rather than depending solely on the
schema's own `CHECK` constraint (still correctly fail-safe, but
inconsistent with this file's own established convention, and a worse
error message for whoever debugs it).

None of C1-C4 require new infrastructure, touch `risks.id=3`'s own
resolution, or change the CTO's central §B.1 decision — all four are
concrete, cheap fixes to the design as specified.

## Non-blocking recommendations (do not gate sign-off)

- **R1** — Specify that "full final content of every changed/added file"
  (§B.1) is retrieved via `git show <head_commit_sha>:<path>` (the git
  object database), not a live filesystem read of the working tree — this
  closes a working-tree symlink/TOCTOU exposure more robustly than
  `resolve()`-based path validation alone can, while `resolve()`-based
  validation remains correct, necessary defense-in-depth for the pathspec
  arguments the `git diff`/`git show` invocations still need.
- **R2** — State explicitly in `ops/SECURITY.md` that the spend/count
  ceilings (§B.6/§B.7) are enforced correctly only under this design's own
  single-poller-process assumption (the same implicit assumption
  `SESSION_TOKEN`'s per-process design already relies on) — the per-event
  idempotency guarantee (§B.3) remains genuinely DB-enforced regardless;
  only the *aggregate* ceilings would be capable of a one-cycle overshoot
  if that assumption were ever violated. No new locking required; this
  needs to be written down, not built around.
- **R3** — Disclose in `ops/SECURITY.md` that Part A's `CONSULT:` mechanism
  is a new, lower-friction path to the same already-accepted "no rate
  limit on a consequential write route" risk class `POST
  /api/meetings`/`/followup` already carry — a single ordinary chat
  message can now reach the same up-to-~$4 worst case a purpose-built
  meeting form previously required.
- **R4** — Name the specific defect class (cross-file duplication/
  invariant violations elsewhere in the repo) automated Code Review's
  bounded context structurally cannot catch, in §B.1.1's disclosure text,
  not only the generic "cannot explore beyond the assembled bundle"
  framing.
- **R5** — Truncate `automation.py`'s own unhandled-error log lines the
  same way `agent_runtime.py` already truncates `stderr_text[:2000]` —
  the assembled review transcript can be up to 60,000 characters and an
  unbounded dump into a failure log line is an easy, avoidable
  inconsistency with this codebase's existing style. Not a real
  secret-exposure risk (no real secrets/PII exist in this system's scope
  today, and stderr is local-terminal-only).
- **R6** — Visually distinguish §B.10 scenario 6 (invalid file path — a
  stronger signal of a real/possibly-adversarial data problem) from the
  other six routine skip scenarios on `/automation.html` and in the Chief
  of Staff's `automation_status_digest()`, without building a new
  Founder-visible-flag mechanism.

---

## Draft `ops/SECURITY.md` language

CTO's own file-by-file list (§ "What Phase 3A explicitly does NOT do" /
file-change list) correctly identifies the topics a new `SECURITY.md`
section must cover, but the draft below adds the two findings above that
were not yet named with the required precision (the specific new
autonomous-actor mechanism under "the Founder's required gate question,"
and the chat-triggered consult-cost amplification, R3) and folds in C1-C4
as commitments once shipped. Recommend the following section, appended
after "Founder Identity Verification (Milestone 2B4, TASK-013)":

> ## Chief of Staff Interface + Limited Automated Orchestration (Phase 3A, TASK-015)
>
> Full design in `ops/reviews/cto-phase3a-architecture.md`; independently
> reviewed in `ops/reviews/security-phase3a-threat-model.md` (REJECT/
> CONDITIONS at the architecture stage, four required fixes — folded into
> the shipped design) and `ops/reviews/red-team-phase3a-architecture.md`.
>
> **This is the first milestone in this system's history to introduce a
> background actor that acts without any HTTP request triggering it.**
> `automation.py`'s poll loop (a `threading.Thread(daemon=True)` inside
> `server.py`'s existing process, `POLL_INTERVAL_S=20`) is the first
> scheduler/poller of any kind this codebase has ever had. This changes
> the practical consequence of `risks.id=3` ("Bash permissions cannot be
> scoped below the tool-category level") in two independent, additive
> ways, neither of which this milestone resolves, narrows, or claims
> progress on:
> 1. A same-OS-user actor no longer needs to forge an authenticated HTTP
>    request to get a real, costed model invocation to run — writing a
>    plausible `CODE_REVIEW`-transition and `handoffs` row via `opsdb.py`
>    directly (already possible before this milestone, under the same
>    already-open risk) is now sufficient; the poller acts on its own,
>    unattended, on a 20-second cycle.
> 2. The Python code around that invocation, running as the same OS user,
>    now walks real filesystem paths and shells out to `git` based on
>    `handoffs.files_changed`/`base_commit_sha`/`head_commit_sha` — data
>    the same-OS-user actor already controls. Mitigated by path validation
>    (reject absolute paths, reject anything resolving outside
>    `repo_root`, reject a `..` component after normalization — redundant
>    with but cheap alongside the `resolve()`-based containment check),
>    commit-SHA format/existence validation, and a `--` separator between
>    revision and pathspec arguments in every `git` invocation (Security's
>    required fix). The real, unsupervised model invocation this triggers
>    remains, and must remain, zero-tool (`--tools ""`,
>    `--strict-mcp-config`, unconditional in `agent_runtime._run_claude()`
>    regardless of caller) — the same restriction applied to every
>    invocation this system has ever made, extended to two new allowlists
>    (`CHIEF_OF_STAFF_ALLOWLIST`, `AUTOMATED_REVIEW_ALLOWLIST`) that cannot,
>    by construction, receive more.
>
> **The Chief of Staff (`/api/chief-of-staff/ask`) is the first real
> `claude --agent orchestrator` invocation in this system's history** —
> every prior appearance of `orchestrator` in `agent_runs`/
> `task_status_history` was a deterministic Python step wearing that
> identity's name for attribution, never a subprocess. Same CSRF+session
> gate as every other write route; same zero-tool guarantee as every other
> invocation. A Founder message asking it to consult other agents produces
> a `CONSULT: <names>` line, parsed by deterministic Python matched only
> against a fixed, pre-approved candidate tuple — never trusted as an
> executable instruction, identical in kind to CEO's own existing
> participant-nomination trust pattern. A consult-triggering message can
> cost up to ~$4 (8 real, `$0.50`-capped invocations) worst case, disclosed
> once, closed-form, matching this codebase's existing convention. **This
> is a new, lower-friction path to an already-accepted risk**: like `POST
> /api/meetings`/`/followup` before it (see "Executive Meetings round 2"
> above), there is no rate limit on how many chat messages — each
> potentially triggering a new up-to-~$4 consult meeting — can be sent per
> unit time, only the same session+CSRF gate every write route already
> carries.
>
> **Kill switch** (`automation_state.enabled`, default `0`, seeded
> disabled at schema-apply time): the only function that can write this
> table is `opsdb.set_automation_enabled()`, called only by the two new
> CSRF+session-gated routes (`POST /api/automation/stop`/`start`) — traced
> every other code path in this design; nothing else, including the
> poller itself or either new model invocation, can set it. Stopping
> prevents any **new** automatic action from starting on the poller's next
> flag check; it does **not** forcibly kill an already-in-flight
> `code-review` subprocess — the same disclosed, previously-reviewed and
> accepted limitation Ask-Agent's own Ctrl+C behavior has carried since
> Milestone 2B3A, bounded here to at most one `$0.50`, 120-second-capped
> invocation.
>
> **Idempotency** (`automation_events.trigger_status_history_id UNIQUE`):
> verified as a real, database-enforced guarantee, not an
> application-level check alone — the claim (`INSERT`) happens before any
> real invocation, inside its own transaction; a second attempt to claim
> the same triggering event fails atomically at the SQLite layer, holding
> even across two independent server processes were that ever to happen.
> **The daily spend (`MAX_AUTOMATION_SPEND_USD_PER_DAY=$10.00`) and
> invocation-count ceilings, by contrast, are enforced by a read-then-decide
> check, not a database constraint** — correct and race-free only under
> this design's own single-poller-process assumption (the same implicit
> assumption `SESSION_TOKEN`'s in-memory, per-process design already
> relies on throughout this codebase). Running a second `server.py`
> process against the same database — nothing today technically prevents
> this — could allow the aggregate ceilings to be exceeded by up to one
> extra poll cycle's worth of invocations; the per-event
> duplicate-invocation guarantee above is unaffected either way.
>
> **`risks.id=3`** — unchanged, `open`. Recommend appending (not
> overwriting) its `description` once this ships:
> "Phase 3A (TASK-015) introduced the first background actor in this
> system's history that acts without an HTTP request triggering it, and
> the first data-driven (attacker-writable, same-OS-user-controlled)
> filesystem/subprocess surface — both increase this risk's practical
> consequence without being resolved, narrowed, or mitigated by anything
> in this design; the invocation this actor triggers remains zero-tool,
> unconditionally, by construction. See
> `ops/reviews/cto-phase3a-architecture.md`, `ops/reviews/security-phase3a-threat-model.md`."

---

## Summary

Design direction: sound. The central §B.1 decision (zero-tool automated
Code Review, real Bash grants explicitly and correctly rejected for an
unsupervised invocation) independently re-derives correctly and is not
merely accepted on the CTO doc's word — verified directly against
`agent_runtime.py`'s hardcoded, caller-independent tool/MCP flags. Four
concrete fixes required before Development starts (C1 commit-SHA
validation + `git` argument-injection hardening, C2 per-candidate failure
isolation, C3 resolve the `CONSULT:` candidate-list self-contradiction, C4
move the reject-requires-`returned_to` check into the plain
`record_review_result()` function) — none require new infrastructure or
touch `risks.id=3`'s own resolution. Six non-blocking recommendations
(R1-R6) strengthen specific mitigations and disclosures without gating
sign-off. `risks.id=3`'s practical consequence genuinely increases under
this design, in two specific, named mechanisms (an unattended background
actor; a same-OS-user-controlled filesystem/subprocess surface) — correctly
not resolved, narrowed, or hidden by this milestone, and the draft
`SECURITY.md` language above states both mechanisms with the precision
this stage requires, not only the CTO doc's own generic framing.
