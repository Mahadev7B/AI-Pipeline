# Red Team adversarial review — risks.id=3 milestone architecture (TASK-017, RED_TEAM_REVIEW stage)

Reviewing `ops/reviews/cto-risk3-milestone-architecture.md` (CTO's corrected
concrete design) and `ops/reviews/security-risk3-milestone-threat-model.md`
(Security's CONCERNS verdict + CTO's corrections against it), against the
Founder's exact authorization (Appendix E,
`ops/reviews/chief-of-staff-risk3-synthesis.md`) and my own prior
investigation-stage challenge (`ops/reviews/red-team-risk3-challenge.md`,
S8). Read in full before writing this document.

Independent verification performed, not accepted on either document's
word: read `ops/control-center/agent_runtime.py`'s `invoke_agent()`
allowlists directly; read `ops/control-center/server.py`'s `do_POST()`
dispatch chain and `APPROVAL_PATH_RE` convention directly; read all seven
tool-bearing `.claude/agents/*.md` frontmatter `tools:` lines directly;
read `ops/db/schema.sql` directly to confirm no naming collision from the
two proposed new tables; confirmed `.founder_credential*` is gitignored;
and — independently, a third time after CTO's and Security's own reads —
read the installed Claude Code CLI source
(`/opt/node22/lib/node_modules/@anthropic-ai/claude-code/cli.js`) myself
for both the per-subagent `sessionHooks` scoping claim **and** a question
neither prior document asked: what does the harness actually do when a
`PreToolUse` hook script itself fails partway through?

**Verdict: REJECT.** Not because the two-tier shape is wrong, not because
CTO's corrections to Security's two required findings are inadequate —
they are genuinely adequate, verified below — but because independent
reading of the installed CLI source surfaces a load-bearing engineering
requirement that is currently **absent from the design document entirely**,
and it goes directly to whether the "self-immune" hook self-immunizes at
all under a completely mundane failure mode, not just a deliberately
crafted one. This is a one-paragraph specification fix, not a redesign —
the same severity class as Security's own two required fixes — and I
expect it to be quick to fold in.

---

## 1. The new finding: `PreToolUse` hooks fail OPEN on any exit code except exactly `2`

I read `cli.js`'s own built-in description of hook contract semantics
directly (the same string the harness surfaces via its `/hooks` command),
independently of anything CTO or Security cited:

```
PreToolUse: "Before tool execution"
Input to command is JSON of tool call arguments.
Exit code 0 - stdout/stderr not shown
Exit code 2 - show stderr to model and block tool call
Other exit codes - show stderr to user only but continue with tool call
```

I confirmed this against the actual dispatch code
(`executePreToolHooks`/`iI(...)` in `cli.js`), which also supports a
second, JSON-based protocol (`hookSpecificOutput.permissionDecision:
"allow"|"deny"|"ask"`, parsed from stdout) — but the exit-code semantics
above govern what happens when that JSON is **absent or unparseable**,
i.e., exactly the failure case that matters here. I also confirmed
directly, by tracing the `catch` blocks around hook execution
(`hook_error_during_execution`, rendered in the UI as `"<hook> hook
warning"`, not as a block), that an exception thrown *during* hook
execution is treated as a **non-blocking warning**, not a denial.

**What this means concretely, and why it is not hypothetical**: `python3`
exits with status **1**, not 2, on any unhandled exception — a traceback.
Neither CTO's §2.2 pseudocode nor Security's review specifies that
`developer_pretooluse.py` must catch every possible failure and translate
it into an explicit, correctly-coded denial. As currently specified
("reads stdin... two check paths... deny if..."), the most natural,
literal implementation of this design is a script that prints a JSON
permission decision (or nothing) and relies on Python's default behavior
otherwise — which means **any input that makes the hook crash is treated
by the harness as "continue with tool call," i.e., fail-open**, not
fail-closed. Concrete, unforced ways this fires, none requiring
adversarial cleverness:

- The design's own §2.2 second bullet describes "a cheap `shlex`-based
  best-effort tokenization" of the Bash command string.
  `shlex.split()` **raises `ValueError`** on unbalanced quotes — a
  perfectly ordinary thing to appear in a real Bash command (e.g. `Bash
  (command="echo \"it's fine\"")` with an unescaped apostrophe inside
  double quotes in one particular quoting style, or any command a
  Developer pastes that happens to have mismatched quoting). If that
  exception isn't caught, the hook process exits 1, the harness's own
  documented contract treats that as "continue with tool call," and
  **the very Bash command being inspected — however dangerous —
  proceeds, undenied and unlogged** (nothing reaches `record_hook_denial`
  either, since the code path that would call it never executes).
- Malformed or unexpected `tool_input` JSON on stdin (a `file_path` that
  is `null`, a `command` field containing invalid UTF-8 bytes an editor
  might legitimately produce, an unexpected extra key) can raise on
  `.resolve()`, on `json.loads`, or on a naive `tool_input["file_path"]`
  key access — same fail-open outcome.
- This is not a hook contract this project has any existing pattern for:
  I confirmed directly (`ls ops/control-center/hooks/`, `find -iname
  '*hook*'`) that **no hook script exists anywhere in this codebase
  today**. There is no established local convention Development would
  naturally reuse, unlike almost everything else in this document (which
  correctly reuses `_git_show_file`, `start_ask_agent_run`,
  `_require_csrf_token`, etc.). This is the one genuinely novel piece of
  engineering in the whole milestone, and it currently has the least
  amount of the design document's own well-established "flag it
  precisely so Development doesn't have to rediscover it" discipline
  applied to it.

**Why this matters more here than an ordinary robustness bug would**: the
entire self-immunity property Part 2 is built around — and the property
§2.3, as corrected, is careful to scope precisely to "registration
timing" — implicitly assumes the hook, once registered and invoked, does
its job. A hook that silently no-ops on a crash is not "bypassable with
effort" like the already-disclosed base64/heredoc class — it is
**bypassable by accident**, by a Developer who isn't even trying, the
first time it hits an edge case in its own tokenization logic. Given that
this hook is also the mechanism meant to close the milestone's headline
purpose (S8, the self-widening-permissions finding), a fail-open crash on
a routine quoting edge case is a strictly worse failure mode than
anything either CTO's or Security's document currently discloses as open
— those documents are careful to say "bypassable by a deliberately
adversarial agent"; this is bypassable by an ordinary one, unintentionally,
on day one.

**Required, before Development builds** (a specification addition, not a
redesign — the same severity/cost class as Security's own two required
fixes): §2.2/§2.4 must state explicitly that `developer_pretooluse.py`
wraps *all* stdin-parsing, tokenization, and path-resolution logic in a
single broad `try/except` whose failure path is treated as **matching a
denial** (never as "no pattern matched, allow"), and that the script uses
whichever output mechanism Development confirms is authoritative (exit
code `2`, or the `hookSpecificOutput.permissionDecision: "deny"` JSON
form) — explicitly, not implicitly — for every deny path, including the
exception-handling fallback. This should get the same one-line empirical
verification CTO's document already requires for the matcher-YAML
question in §2.1/§3.3 (a concrete test: feed the hook a deliberately
malformed `tool_input` and a Bash command with unbalanced quotes, confirm
both are denied, not silently allowed, before trusting the hook in a real
Developer session).

---

## 2. Verifying CTO's corrections against Security's two required findings

### 2.1 §2.5/§4 — the CTO-self-edit disclosure

Genuinely fixed, not softened or buried. The corrected §2.5 quotes Red
Team's own Stage 3 finding in full rather than the DevOps-only half, uses
language at least as direct as the DevOps paragraphs ("more direct... no
Bash trickery, no encoding indirection, no shell-parsing evasion
required"), and the corrected §4 recommended `risks.id=3` disclosure text
names CTO explicitly alongside DevOps, with the same "if anything, more
direct" framing carried through into the text that will actually land in
the risk register. I checked this is not merely present but *equally
weighted* with the DevOps disclosure, not a subordinate footnote — it is.
One irony worth naming plainly, not as a blocking defect but because it
sharpens exactly what "reduced, not closed" costs in practice: the
document I am reviewing right now, and its own correction of this exact
gap, were both authored by a `cto`-typed session holding the same
unrestricted `Write`/`Edit` this section discloses as unclosed. That is
not a flaw in this document — it is the plainest possible illustration of
why the Founder's authorization frames this as reduction with disclosure,
not closure, and CTO's document does not pretend otherwise anywhere in
the text I read.

### 2.2 §2.3 — the "closes the loop... completely" overclaim

Genuinely fixed. The corrected §2.3 now separates *registration timing*
(proven, no exceptions) from *detection completeness for the
self-protection paths* (not proven, and explicitly restated as exactly as
bypassable as everything else in the hook) in language a reader cannot
mistake for "basically closed." It reproduces Security's own concrete
`python3 -c` example rather than gesturing at it abstractly. This holds.

### 2.3 §2.2 — does the substring-list addition close the class of bypass, or just the one example?

I independently constructed two further variants, as the task asked, before
accepting the fix as sufficient:

1. **Glob/wildcard reference, no encoding at all** —
   `python3 -c "import glob; p=glob.glob('.claude/agents/dev*.md')[0]; ..."`.
   The literal string `.claude/agents/developer.md` never appears in this
   command; `.claude/agents/dev*.md` does. This defeats the corrected
   plain-substring check exactly as easily as the pre-correction
   command-anchoring gap did, with **no obfuscation technique at all** —
   not base64, not heredoc, just a shell glob character.
2. **String concatenation without any encoding** —
   `python3 -c "p='.claude'+'/agents/dev'+'eloper.md'; ..."`. Again, no
   encoding, no base64, just splitting a literal so no contiguous
   substring match fires.

Both confirm what the document's own text already says plainly and does
not overclaim: the §2.2 addition closes exactly the one concrete case
Security named (route the edit through a command name outside the
six-command anchor list) and nothing more. It does not "raise the bar"
against the general class in any way that would survive five more seconds
of adversarial thought — a plain substring list was never going to, and
the document does not claim it does. **This is not a required fix**: the
document's own honesty about the residual ("remains open, undiminished")
is exactly matched by what I independently found, so there is no
disclosure gap here, only a confirmation that the underlying mechanism
(substring matching) has the ceiling both CTO's and Security's prior-stage
documents already named correctly. I record this because the task asked
me to try constructing a bypass myself, not because it changes the
verdict.

### 2.4 The `reviewer_invocations`/`hook_denials` tables — justified, not overengineered

I independently re-verified the `automation_events.trigger_status_history_id
UNIQUE` constraint in `ops/db/schema.sql` and confirm CTO's reasoning:
forcing a human-repeatable action through that constraint would either
block a legitimate re-run or require dropping a guarantee Red Team's own
Phase 3A review required be strict. A second, small, structurally distinct
table is the right call, not machinery for its own sake — it is two
`CREATE TABLE IF NOT EXISTS` blocks with no migration complexity, no new
class of table shape this codebase hasn't already used four times over
(`automation_events`, `agent_runs`, `qa_results`, `review_results` all
follow the same start/end-row pattern). I checked for a naming collision
against the live schema directly — none. I do not have an overengineering
finding here; my own investigation-stage recommendation (build the
smallest real slice, ship logging as load-bearing not an afterthought) is
what this document actually does.

### 2.5 Scope discipline against Appendix E

I re-checked the design against the Founder's exact authorization text
line by line, independently of Security's own pass. I reach the same
conclusion Security did: no QA/CTO/DevOps tool scoping is proposed
anywhere; the two skill-doc edits are documentation-only and are exactly
what item 2's "no sanctioned path (native tool grant **or skill**)"
wording requires be closed; no deployment-gating change appears. On the
one interpretive question Security flagged (three new HTTP routes against
the "no change to Founder-facing routes" exclusion) — I independently
traced `do_POST()`'s dispatch chain myself and confirm the three new
routes would join the exact same `is_X`-chain-then-`_require_csrf_token`-
then-`_authenticated_session`-check pattern every existing write route
already uses, with the same `APPROVAL_PATH_RE`-style digit-bounded ID
regex convention available to copy. I agree with Security: this is
"reuse of an existing mechanism via a new route," consistent with Phase
3A's own precedent, and does not need to block Development — one
confirming sentence in the design (not a redesign) is enough, matching
Security's own non-blocking framing.

---

## 3. Independent hunting — what else I checked, and what I found

- **The `handoffs`-lookup query for Code Review/Security does not check
  current task stage before running.** `SELECT * FROM handoffs WHERE
  task_id = ? AND from_agent = 'developer' AND to_agent = 'code-review'
  ORDER BY id DESC LIMIT 1` returns the most recent such handoff
  regardless of where the task currently sits in its lifecycle. A human
  double-clicking, or re-triggering a review after the task has already
  progressed past that gate (e.g. into QA or RELEASED), would run a real
  review against stale committed content and attempt a real status
  write. CTO's document doesn't specify what happens next. My own
  reading is this is very likely caught by `opsdb.record_task_status()`'s
  own Python-enforced transition-validity logic (which CTO's own §4
  independently confirms exists, just not schema-mirrored) rejecting an
  invalid backward transition — but the design document does not say so,
  and should: either confirm the state-machine guard covers this case
  cleanly (a friendly rejection, not an unhandled exception surfacing a
  500 to the Founder), or add an explicit task-status check before
  invoking the reviewer. **Non-blocking** (a robustness note, in the same
  category as Security's non-UTF8-artifact finding), not required before
  Development starts, but worth naming so Development doesn't have to
  rediscover it.
- **Pre-existing zero-tool path via `MEETING_PARTICIPANT_ALLOWLIST`**: I
  confirmed directly that `security` and `red-team` are already members
  of `agent_runtime.MEETING_PARTICIPANT_ALLOWLIST` today, independent of
  anything this milestone adds — meetings already invoke them zero-tool.
  This is consistent with, not contradictory to, CTO's §1.2 framing (the
  carve-out is that *interactive Task-tool sessions* are the untouched
  path, and meetings already go through `invoke_agent()` today exactly
  like the new synchronous routes will) — no new attack surface here,
  just confirms the existing shape rather than surfacing a gap.
- **Route/task-ID validation, race conditions between concurrent
  invocations**: I checked `start_ask_agent_run`'s guard is keyed on
  `(agent_id, activity_like)`, confirmed by reading `opsdb.py` directly —
  this means at most one running invocation *per reviewer role*
  system-wide, not per task. A human triggering security review for task
  B while task A's security review is still running (up to 120s) would
  hit this guard. That's an inherited, already-accepted tradeoff (Security
  confirmed no *new* race is introduced), but the 120s window makes it
  more likely to actually surface than it has been for the poller so far,
  since a human can trigger it on demand. Worth a clean, human-readable
  error message rather than a raw `ValueError` bubbling up — **non-
  blocking UX note**, not a security or correctness defect.
- **Founder-credential and DB-file exposure via the Red Team artifact
  route**: I independently re-confirmed `.founder_credential*` is
  gitignored and `operations.sqlite3` is git-tracked, matching Security's
  findings exactly. Nothing further to add.

---

## 4. Answering the five questions in my mandate directly

1. **Do CTO's corrections genuinely address Security's findings?** Yes,
   for both required findings (§2.1, §2.2 above), verified independently,
   not merely "text was added."
2. **Did I find anything CTO and Security both missed?** Yes — §1 above,
   the fail-open-on-hook-crash gap. This is the headline finding of this
   review, the same weight class as S8 was at the investigation stage: a
   real, independently-verified, currently-undocumented way the
   milestone's central mechanism doesn't do what it's meant to do, under
   a completely ordinary failure mode, not merely a deliberately
   adversarial one.
3. **Overengineering/hidden-cost check**: none found. `reviewer_invocations`
   and `hook_denials` are justified, minimal, and match this codebase's
   own established table-shape conventions (§2.4 above).
4. **Scope discipline**: clean. Nothing in the design exceeds Appendix E
   (§2.5 above).
5. **Is the residual CTO/DevOps disclosure an acceptable amount of "still
   open"?** Yes, on its own terms — the Founder's authorization
   explicitly anticipated "reduced, not closed," explicitly required
   disclosure rather than closure as the bar for item 2's DevOps half, and
   CTO's corrected document meets that bar honestly for both DevOps and
   CTO now. This does not need further mitigation before shipping *within
   the milestone's authorized scope*. It should not, however, be read as
   "S8 is closed" anywhere this milestone's own risk-register text gets
   written — and the corrected §4 text I read does not make that mistake.

---

## 5. What must change before Development starts

**One required change**: add the fail-closed exception-handling and
exit-code/output-contract specification for `developer_pretooluse.py`
described in §1 above to CTO's document (§2.2 and/or §2.4), plus
Development's own empirical verification of it (malformed input, deny —
not allow), alongside the matcher-YAML empirical test §2.1 already
requires. This is a specification paragraph, not a new mechanism, a new
table, or a scope change — it does not touch the two-tier shape, the
route design, the audit tables, or anything Security already required.
It is the one thing standing between "this document" and a genuine PASS.

**Everything else in this document — the corrected §2.3/§2.5/§4
disclosures, the §2.2 substring addition, the three synchronous routes,
the two new tables, the file-by-file change list — holds up under
independent verification and does not need to change.** I am not
manufacturing additional findings to pad this review; §2 and §3 above are
confirmations and non-blocking notes, not required fixes, and I've been
explicit about which is which throughout.

Recorded via `python3 ops/db/opsdb.py review-result --type code --by
red-team --result reject --returned-to cto` (architecture-stage review,
same pattern as Security's own Stage 2 CONCERNS/reject recording),
citing this document.

---

## 6. Re-verification of §2.2a's correction (TASK-017, second pass)

CTO added §2.2a to `ops/reviews/cto-risk3-milestone-architecture.md`,
marked "Correction (Red Team's TASK-017 milestone review section 1)."
This section re-verifies that correction against the installed CLI
source directly (`/opt/node22/lib/node_modules/@anthropic-ai/claude-code/cli.js`),
a third independent read of the hook-dispatch code (after my own §1 read
above), tracing the actual functions this time by name: `iI()` (the
`PreToolUse` result reducer), `rZ6()` (the hook-subprocess spawn/collect
function), `Es4()` (the stdout-JSON parser), `ks4()` (the JSON-to-permission-
decision mapper), and the Zod schema `Wj6` the harness validates hook
stdout against. Not accepted on the document's word — read independently,
line by line, against the actual minified source.

**Verdict: REJECT again.** The core exception-handling mechanism CTO's
correction specifies — wrapping the hook in `except BaseException` — is
genuinely, verifiably correct and closes the finding it was written to
close. But the "Required structure" pseudocode in §2.2a that is supposed
to pin down this fix contains a control-flow bug that, if implemented as
literally sketched, denies **every single tool call, including benign
allowed ones**, on every invocation — not a redesign to fix, a one-line
structural correction, the same severity/cost class as my original
finding and CTO's own §2.2a correction itself.

### 6.1 Confirmed correct: `except BaseException` genuinely catches the crash class that mattered

Read directly: `iI()`'s per-hook execution path calls `rZ6()`, which spawns
the hook's `command:` via `spawn(..., {shell:true})`. Ordinary OS process
semantics govern what happens inside that child process — nothing in
`rZ6()` intercepts or special-cases a Python traceback. Confirmed: a
`ValueError` from `shlex.split()` on unbalanced quotes, an uncaught
`KeyError`/`TypeError` from malformed `tool_input`, or any other ordinary
Python exception, left uncaught, produces Python's default behavior
(traceback to stderr, exit code 1) — and `except BaseException` catches
all of these, including a stray `sys.exit()`/`SystemExit` raised deeper in
the call stack (`SystemExit` is a direct subclass of `BaseException`, not
of `Exception` — CTO's stated reason for the broader catch is technically
correct). This part of the correction holds.

### 6.2 Confirmed correct: the per-step guard structure resolves my original "boundary" concern

Traced the pseudocode's control flow directly: every narrower `try/except`
(around `json.loads`, `Path.resolve()`, `shlex.split()`) is nested
*inside* the single outer `try` in `main()`, not structured as several
independent top-level `try/except` blocks. Any code running between two
guarded steps — including glue code in `_evaluate()` not itself wrapped —
is still covered by the outer `except BaseException`, because it executes
within the outer `try`'s dynamic scope. There is no gap between steps of
the kind my original review's "outer vs. inner boundary" concern named.
This resolves cleanly.

### 6.3 REQUIRED — the pseudocode's own `sys.exit()` placement causes every invocation, including successful ones, to hit the except branch

The "Required structure" pseudocode (§2.2a) is:

```python
def main():
    raw_stdin = None
    try:
        raw_stdin = sys.stdin.read()
        payload = _parse_payload(raw_stdin)
        decision, matched_rule = _evaluate(payload)
        _emit_decision(decision, matched_rule)
        if decision == "deny":
            _log_denial(payload, matched_rule)
        sys.exit(0 if decision == "allow" else 2)   # <-- inside the try
    except BaseException as exc:
        _emit_decision("deny", "hook_internal_error")
        _best_effort_log_internal_error(raw_stdin, exc)
        sys.exit(2)
```

`sys.exit(...)` raises `SystemExit`. The final `sys.exit(0 if decision ==
"allow" else 2)` line — the *normal, successful* termination for every
ordinary invocation, allowed or denied — sits **inside** the same `try`
block the `except BaseException` clause guards. Since `SystemExit` is a
`BaseException`, this call is caught by the very handler that is supposed
to be reserved for genuine internal failures. Concretely: a completely
benign, non-adversarial Write to an allowed path — `_evaluate()` returns
`("allow", None)` cleanly, no exception anywhere in the real logic — still
raises `SystemExit(0)` on the pseudocode's own last line of the `try`
block, which is then caught by `except BaseException`, which
unconditionally overwrites the decision to `"deny"` with
`matched_rule="hook_internal_error"` and exits 2. **As literally sketched,
this script denies 100% of tool calls, always, regardless of `_evaluate()`'s
actual result.** This is not a hypothetical edge case reachable only by
malformed input — it is the default, every-single-invocation behavior of
the pseudocode as written.

This is a basic, well-documented Python semantics fact (any exception
raised anywhere inside a `try` block, including its own last statement, is
caught by a matching `except` clause in the same frame) — not a subtle
misreading. I traced it against the actual control flow twice to be sure
before including it here.

**Why this must be corrected in the document, not left to Development to
discover and patch under pressure**: this bug is maximally loud — it
would deny literally the first canary test §2.1 already requires
(`Write(file_path="/tmp/canary.txt", ...)`, expected to be allowed) — so
it is very likely to surface immediately, unlike my original finding,
which was silent. That is real mitigation, but it is not the same as the
document being correct. Two concrete risks of leaving it as-is:

1. A developer under time pressure, seeing "every tool call is being
   denied," has an obvious, tempting, **wrong** fix: wrap the final
   `sys.exit()` call (or the whole hook) in a broader
   `try/except SystemExit: pass`-style pattern to "stop it from
   interfering" — which would suppress the *legitimate* deny path's own
   `sys.exit(2)` too, silently reintroducing something close to the
   original fail-open bug this correction exists to close, from the
   opposite direction.
2. The document explicitly frames this pseudocode as pinning down "the
   shape" Development implements against (§2.2a: "this sketch exists to
   pin down the shape, not to be copied verbatim... Two properties this
   sketch is required to convey, not merely illustrate"). A shape that
   itself doesn't run correctly is not a reliable reference for the one
   piece of code this entire milestone's headline property depends on.

**Required fix** (one-line class of correction, not a redesign — matching
the cost of my original finding and of this correction's own framing):
move the success-path `sys.exit(...)` call **outside** the guarded `try`
block (e.g., compute `decision` inside `try`, `except BaseException` sets
a local flag/re-derives a forced-deny decision, then a single `sys.exit(...)`
call after the `try/except` — reached in both the normal and exception
cases — decides the process's actual exit code). Any structure where the
*legitimate* exit calls are not themselves inside the scope of the
`except BaseException` handler resolves this.

### 6.4 Non-blocking, worth folding in on the same edit pass

- **The except handler's own two calls are not themselves guarded.** If
  `_emit_decision("deny", "hook_internal_error")` or
  `_best_effort_log_internal_error(raw_stdin, exc)` were to raise inside
  the `except` block (e.g., a write failure formatting the JSON), nothing
  catches that — Python's default uncaught-exception behavior applies
  again, one layer deeper, reproducing the original bug. Low probability
  (tiny in-memory writes to a normal pipe/DB connection) but the
  document's own comment ("must not itself raise") is currently an
  assertion, not a structural guarantee. A trivial nested
  `try/except: pass` around these two calls, immediately before the final
  `sys.exit(2)`, closes this without adding real complexity.
- **CTO's stated mechanism for why "stray text on stdout" causes fail-open
  is not quite what the source shows, though the practical requirement
  survives it.** I traced `Es4()` directly: if trimmed stdout doesn't
  start with `{`, or `JSON.parse` throws outright, `Es4()` returns
  `{plainText: A}` with **no** `validationError` set — and `iI()` falls
  through to plain exit-code semantics (`status===2` → still correctly
  denies). Stray non-JSON text around the JSON therefore does **not**, by
  itself, force fail-open the way §2.2a states — as long as exit code 2 is
  still set, the deny is still honored. What **does** force fail-open
  *regardless of exit code* is different and more subtle: stdout that
  starts with `{` and parses as syntactically valid JSON but fails the
  harness's Zod schema (`Wj6` — every field optional, but a wrong enum
  value, e.g. `"permissionDecision": "denied"` instead of `"deny"`, or
  content nested outside `hookSpecificOutput`, fails validation) —
  `iI()`'s `if(p){...non_blocking_error...return}` branch fires
  **before exit code is even checked**, ignoring `status===2` entirely.
  In practice this is adequately covered by §2.2a's own required empirical
  test (both the canary and the malformed-input test exercise the same
  shared `_emit_decision()` and would catch a schema-shape bug directly
  against the real harness) — so this is not a new required fix, but the
  document's rationale should be corrected: the actual risk is a
  schema-invalid JSON *shape* in `_emit_decision()`'s own output, not
  "stray print() text" per se, and exit code 2 is **not** a reliable
  fallback for that specific failure mode the way §2.2a's text implies.
- **The disclosed timeout/"cancelled" residual is accurate, confirmed by
  direct source read, and should be joined by one more sentence naming a
  sibling gap of the same class.** Traced `iI()`'s hook-result loop
  directly: when `rZ6()` reports `U.aborted` (timeout), the yielded result
  carries only `message`/`outcome:"cancelled"` — no `blockingError`, no
  `permissionBehavior` — so nothing in the reducer loop ever sets a deny
  decision for that hook, confirming CTO's disclosure exactly as written.
  Worth adding, in the same paragraph rather than as a new separate
  finding: `except BaseException` cannot catch OS-level process
  termination (a `SIGKILL` from an OOM-killer, or an unhandled `SIGTERM`)
  — the same "no Python code runs at all" failure class as the timeout
  case, not closed by anything in §2.2a's fix, and — like the timeout
  case — very low-probability given the hook's cheap, stdlib-only,
  no-subprocess, no-network design. Naming both together, rather than only
  the timeout case, keeps the disclosure complete without changing its
  conclusion (still non-required, still disclosed rather than fixed).

### 6.5 What must change before Development starts (this pass)

**One required change**: fix §2.2a's "Required structure" pseudocode so
the legitimate `sys.exit(...)` call(s) are not themselves inside the
`try` block guarded by `except BaseException` (§6.3) — the pseudocode as
currently written denies every tool call unconditionally, not just crash
cases. This is the one thing between this document and a genuine PASS,
the same framing my original review used for the first-pass finding.

**Recommended, same edit pass, not independently blocking** (§6.4): guard
the except handler's own two calls; correct the stated rationale for the
stdout-JSON requirement (schema validation, not "stray text," is the
actual exit-code-independent fail-open mechanism); and extend the
disclosed timeout/"cancelled" residual to also name OS-level signal
termination as the same class of gap.

**Everything else re-verified in this pass holds**: the `BaseException`
catch itself is correct and sufficient for the crash class my original
finding named; the per-step guard nesting resolves the boundary concern
cleanly; the timeout/"cancelled" disclosure is accurate and appropriately
scoped, matching this project's own disclosure discipline, and does not
need to become a required fix.

Recorded via `python3 ops/db/opsdb.py review-result --task-id 17 --type
code --by red-team --result reject --returned-to cto`, citing this
section.

---

## 7. Third pass — verifying the reordering fix to §2.2a (TASK-017, third pass)

Read §6 above (my own prior finding) and the current
`ops/reviews/cto-risk3-milestone-architecture.md` §2.2a in full before
writing this section, per the task brief. Traced the "Required structure"
pseudocode line by line against the actual text now in the document
(lines 563–629 as currently committed), not against the summary of what
CTO claims to have changed.

### 7.1 The success path genuinely never passes through `except BaseException`

Confirmed by direct trace. The guarded `try` in `main()` now contains
exactly three statements — `raw_stdin = sys.stdin.read()`,
`payload = _parse_payload(raw_stdin)`, `decision, matched_rule =
_evaluate(payload)` — and nothing else; the block ends with a comment
("the guarded region ends here") immediately followed by the `except
BaseException as exc:` clause. Ordinary Python scoping rules apply: if
none of the three statements raises, control does not enter the `except`
clause at all — it falls through to the first statement textually
following the entire `try/except` construct, which is the "Success path"
block (`_emit_decision(decision, matched_rule)`, the conditional
`_log_denial`, then `sys.exit(0 if decision == "allow" else 2)`). That
block sits at the same indentation level as `try:`/`except:`, i.e.
outside both, so its `sys.exit()` call — which raises `SystemExit`, a
`BaseException` — has no enclosing `try` left to be caught by. This is
exactly the reordering CTO's document claims and it is correct. The
maximally-loud bug from my second-pass review (100% of calls, including
the canary, denied) is genuinely gone.

### 7.2 The nested fallback (point 4) does not reintroduce any version of the bug

Traced the `except BaseException` block's own structure: its two
substantive calls (`_emit_decision("deny", "hook_internal_error")`,
`_best_effort_log_internal_error(raw_stdin, exc)`) are wrapped in a nested
`try/except BaseException: <hardcoded stdout.write fallback>`, and the
handler's own `sys.exit(2)` sits **after** that nested `try/except`,
at the outer `except` block's indentation — i.e., inside the outer
`except`'s scope but outside the nested `try`. There is no third layer of
`try` wrapping this `sys.exit(2)`, so nothing re-catches it. This
resolves cleanly and matches the same pattern already verified correct
for the outer level in §7.1: an exit call is safe exactly when it sits
outside every `try` whose matching `except` could intercept
`SystemExit`, and that is true here at both the outer and nested level.

### 7.3 No other blocking control-flow bug in the "required to convey" properties

The document is explicit (line 552) that this pseudocode's job is to pin
down three specific properties — `BaseException` (not `Exception`)
catching; per-step guards with a diagnosable `matched_rule`; and exit
calls never running inside the handler's own scope — not to be Development's
literal, field-accurate implementation. Checked all three against the
actual text: all three are correctly conveyed and, per §7.1–§7.2, actually
compile-and-run correctly as sketched, not merely correctly described in
prose. No exit call, return, or raise anywhere in the corrected structure
sits inside a scope that unintentionally catches it.

### 7.4 The three follow-ups are substantive, not superficial

- **Zod-schema attribution (point 5)**: re-checked against my own §6.4
  trace of `Es4()`/`iI()`/`Wj6`. The corrected text now states precisely
  what I found independently last round — stray non-JSON text alone does
  *not* force fail-open (exit code still governs when stdout doesn't parse
  as JSON at all), and the actual exit-code-independent trap is
  syntactically-valid JSON that fails the harness's Zod schema. This is a
  real technical correction, not a rewording — the prior text was
  factually imprecise about the mechanism and is now accurate.
- **SIGKILL/SIGTERM addition (point 6)**: re-checked. The added sentence
  correctly generalizes the disclosed timeout/"cancelled" residual to the
  same "no Python code runs at all" class for OS-level signal termination,
  correctly scoped as non-required given the hook's synchronous,
  subprocess-free, stdlib-only design (no plausible long-running or
  externally-killable code path). Accurate, not just superficially present.
- **Nested fallback (point 4)**: verified structurally correct in §7.2
  above, not merely claimed.

### 7.5 Two non-blocking specification-completeness findings for Development

Neither of these is a bug in what's written — the document is explicit
that this pseudocode is a sketch of *shape*, not a literal
implementation — but both are exactly the kind of thing a Developer
skimming this section (having just absorbed two rounds of careful
`sys.exit()`-placement reasoning) could transcribe without noticing, so
I'm naming them rather than leaving them to be rediscovered:

1. **The success path's own `_log_denial` call is exactly as unguarded as
   the except-handler's calls were before this round's fix, and did not
   get the same treatment.** `_emit_decision(decision, matched_rule)` and
   `_log_denial(payload, matched_rule)` (the latter commented "best-effort;
   must not raise") sit in the success-path block, deliberately outside
   any `try`, so that `sys.exit()` isn't caught (correct, per §7.1). But
   that also means if `_log_denial` — a real SQLite write, the single most
   failure-prone line in this script — raises (e.g. a lock contention
   error), nothing catches it: the process crashes with Python's default
   uncaught-exception behavior (exit 1), which is fail-open by the
   harness's exit-code contract. In practice this is very likely safe:
   `_emit_decision` runs first and, per §2.2a's own traced `Es4()`
   behavior, the harness parses whatever valid JSON already reached stdout
   *regardless of exit code*, and CPython's normal interpreter-shutdown
   sequence flushes stdout on an uncaught exception (this is not an abrupt
   kill of the kind §2.2a's own SIGKILL disclosure describes). But that
   safety is an unstated assumption about buffering/shutdown order, not a
   structural guarantee — exactly the standard the document itself just
   applied to the except-handler's own calls ("the document's own comment
   ... is currently an assertion, not a structural guarantee," §6.4).
   Recommend one line of symmetry: either wrap `_log_denial` (and,
   trivially, `_emit_decision`) in their own best-effort guard the same
   way the except-handler's calls now are, or add `sys.stdout.flush()`
   immediately after `_emit_decision()` and say explicitly that this is
   why a subsequent `_log_denial` failure is safe to leave unguarded.
   Cheap, same cost class as everything else in this document's disclosure
   discipline.

2. **`_evaluate()`'s sketch, if transcribed literally, denies 100% of
   Bash calls for the wrong reason, before ever reaching the Bash-specific
   checks.** The sketch unconditionally does `path =
   Path(payload["tool_input"]["file_path"]).resolve()` first, catching
   `KeyError` and returning `("deny", "file_path resolve failed: ...")`,
   *before* the Bash-specific `shlex.split()` block runs. A real
   `Bash(command="echo canary")` `tool_input` has no `file_path` key at
   all, so the first check's `KeyError` fires unconditionally for every
   Bash call, returning an early deny before the Bash-specific logic is
   ever reached — meaning, if implemented exactly as sketched, *every*
   Bash tool call is denied with a nonsensical "file_path resolve failed"
   reason, never mind what the command actually contains. This fails
   closed, not open — the opposite direction from every finding in §1 and
   §6 above — and would almost certainly be caught immediately by §2.1's
   own required canary test (`Bash(command="echo canary")`, expected
   allow) before any real Developer session relied on the hook. I am not
   treating this as blocking for that reason, and because the document is
   explicit the field-access details here are elided ("..." placeholders)
   and not one of the three properties the sketch is required to convey.
   But it is the same defect *class* — an unconditional check placed where
   a conditional one belongs — that produced this document's two prior
   REJECTs, now in a new spot, and it costs one sentence to close: state
   explicitly that the file_path check and the command check are
   mutually exclusive per `tool_name` (or per key presence via `.get()`
   rather than unconditional indexing), not sequential-and-unconditional
   as literally sketched.

Neither of these changes the verdict. Both fail toward safety or toward
an immediately-visible break (not silent fail-open), both are cheap
one-line fixes, and neither reaches the severity bar that produced my
first two REJECTs on this document (a silent, hard-to-notice fail-open
under ordinary non-adversarial input, or a total, undetected denial of
every call). I record them because the task asked me to hunt for exactly
this class of thing on this pass, not because either one independently
justifies a fourth REJECT round.

### 7.6 Verdict

**PASS.** The control-flow bug that produced my second REJECT (the
success-path `sys.exit()` sitting inside the `except BaseException`
guard) is genuinely, verifiably fixed by the one-line reordering — traced
directly against the actual pseudocode text, not accepted on CTO's
summary. The nested fallback added for my prior §6.4 non-blocking note is
structurally sound and does not reintroduce any version of the bug at its
own level. The three follow-up corrections (Zod-schema attribution,
SIGKILL/SIGTERM disclosure, nested-fallback guard) are substantive
technical corrections, independently re-verified against my own §6.4
trace, not superficial rewording. I found two further non-blocking
specification-completeness gaps (§7.5) worth folding into the same edit
pass Development will make anyway, but neither is a defect in what's
written, neither is silent-fail-open, and neither meets the bar that
justified the first two REJECTs. Three rounds of REJECT on one document
is a real cost; this document has earned the close. Development may
proceed against `ops/reviews/cto-risk3-milestone-architecture.md` §2.2a
as currently written, folding in §7.5's two recommendations on the same
pass as the rest of Development's own implementation work.

Recorded via `python3 ops/db/opsdb.py review-result --task-id 17 --type
code --by red-team --result pass`, citing this section.
