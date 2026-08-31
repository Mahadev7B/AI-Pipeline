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
