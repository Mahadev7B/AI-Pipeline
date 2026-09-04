# Code Review — TASK-024, the Idea Desk (slices 1 and 2)

**Reviewer:** code-review (independent)
**Date:** 2026-09-02
**Scope:** `ops/idea-desk/{server,pages,evaluator,seed_founder_idea,doctor}.py`,
the TASK-024 additions in `ops/db/opsdb.py`, the TASK-024 changes in
`ops/control-center/agent_runtime.py`.
**Why this review exists:** this code was written by the orchestrator directly and did
not pass through architecture / red-team / code review before landing. This is the
catch-up pass.

---

## Summary

The design is sound and the separations it claims are real: this process opens the
database `mode=ro` and cannot write, every write shells to `opsdb.py`, the credential
is imported from `founder_auth` rather than copied, and the immutability of the three
artifacts is enforced by omission in `opsdb.py` (no `idea-round-update`, no way to
rewrite `ideas.raw_idea`). The append-only round model, the `evaluating_since` /
`last_error` marker pair chosen over a new `status` CHECK value, and the refusal to
offer an approve-anyway path are all right.

**The sanitiser holds.** I attacked `pages.safe_html` with attribute injection, event
handlers, mismatched quotes, prefix-collision class names (`lab unknown`), unclosed
tags, double-escaped input, uppercase tags, whitespace variants, and stray closing
tags. Nothing dangerous survives, and the div-balancing is correct in every case I
could construct. Details and the one real (cosmetic) gap are in finding 6.

What blocks this is not the sanitiser. It is that the Idea Desk re-implements things
the rest of this codebase already solved, and drops the controls that came with them:
the login route without the brute-force/scrypt-serialisation fix that
`ops/control-center/server.py` carries as Security's required fix C1; an in-progress
marker with no counterpart to `opsdb.reconcile_orphaned_runs()`; and the one action in
the product that spends real money recording no `agent_runs` row at all, despite the
constants and the `--agent-run-id` column being added for exactly that and left unused.

---

## Required fixes

### 1. `POST /api/login` has no brute-force lockout and no scrypt serialisation — `ops/idea-desk/server.py:296-308`

`ops/control-center/server.py:247-253` defines `_LOGIN_LOCK`, `MAX_FAILED_ATTEMPTS = 5`
and `LOCKOUT_SECONDS = 30`, and its module docstring (lines 107-111) states the entire
check-verify-increment sequence is serialised under `_LOGIN_LOCK` per **Security's
required fix C1**, closing both the brute-force cap *and* "a concurrent-scrypt
memory-exhaustion DoS".

The Idea Desk serves the same credential, on the same loopback, from a
`ThreadingHTTPServer`, and calls `founder_auth.verify_passphrase(passphrase)` at
line 298 with no lock, no counter and no lockout.

Two concrete consequences:

* **Unthrottled oracle.** Port 8421 is an unlimited-rate guessing surface against the
  same passphrase port 8420 deliberately rate-limits. The control was not weakened by
  a threat-model change; it was simply not carried over.
* **Memory-exhaustion DoS.** `founder_auth.SCRYPT_N = 2**17`, `SCRYPT_R = 8`
  (`ops/control-center/founder_auth.py:60-61`) ⇒ `128 · N · r ≈ 134 MiB` per
  verification. `ThreadingHTTPServer` spawns an unbounded thread per connection and
  nothing serialises the call, so ~50 concurrent unauthenticated POSTs to
  `/api/login` allocate roughly 6.7 GB. This is precisely the DoS C1 was raised for,
  reintroduced on a new port.

Fix: reuse the Control Center's lockout, do not re-implement it. Lift
`_LOGIN_LOCK`/`_failed_count`/`_locked_until` and the serialised
check-verify-increment into a shared module both servers import (`founder_auth` is the
natural home, since both already import it) and call it from both. A second private
copy of the counter in `server.py` would be the same defect one file later — note the
Control Center's own comment that the counter is deliberately *global*, which a second
independent copy would silently break.

### 2. A stuck `evaluating_since` is unrecoverable, and the docstring's claim that it cannot happen is false — `ops/idea-desk/evaluator.py:410-463`, `ops/idea-desk/server.py:417-439`

`run_evaluation`'s docstring (lines 412-414) states: *"every exit path clears the
running marker, so a failure never leaves an idea stuck saying it is being
evaluated."* That is not true on two paths:

* **Crash inside the `finally`.** Lines 455-462: if `_opsdb("idea-evaluation-end", …)`
  itself fails, the exception is caught, printed to stderr, and swallowed.
  `_opsdb` fails for real reasons — `subprocess.TimeoutExpired` after its 30 s
  timeout, a `SQLITE_BUSY` past `connect()`'s 5 s wait, a non-zero exit. The marker
  stays set.
* **Process death.** The thread is `daemon=True` (line 474). Ctrl-C, a crash, a reboot
  or the `pkill` the file's own port-conflict message and `doctor.py` both tell the
  Founder to run, all leave `evaluating_since` set with no thread to clear it.

The consequence is not cosmetic. `pages.idea_page:496-497` returns `evaluating_page`
whenever `evaluating_since` is set, *before* any other branch, so `/idea/N`,
`/close/N`, `/correct/N`, `/approve/N` and `/evaluate/N` all render the same
self-refreshing "The company is considering your idea" screen whose only control is
"Back to your ideas". `cmd_idea_evaluation_start` (`ops/db/opsdb.py:1890`) refuses a
new evaluation while the marker is set. The idea is permanently frozen and the
Founder's only exit is hand-editing the database.

`ops/db/opsdb.py:608 reconcile_orphaned_runs()` and its `run-reconcile` CLI
(line 2015) are exactly this pattern, already built and already called at Control
Center startup. Nothing analogous exists here: `_ensure_schema()` runs `init` and
nothing else, and there is no `idea-evaluation-cancel` command.

Fix: (a) add a startup reconciliation to `server.py:main()` that clears
`evaluating_since` for every idea and records a `last_error` saying the evaluation was
interrupted by a restart — reusing `reconcile_orphaned_runs`'s shape, not inventing a
second one; (b) give `evaluating_page` a "Stop waiting" control backed by an
`idea-evaluation-end --error` write, so an in-process hang is also escapable;
(c) correct or delete the docstring claim at lines 412-414.

### 3. Idea evaluation records no `agent_runs` row and no cost — `ops/idea-desk/evaluator.py:113-124`

`_invoke` calls `agent_runtime.invoke_agent(...)` and discards `result.cost_usd`,
`result.model_used` and `result.duration_ms`. No `opsdb.start_run` / `opsdb.end_run`
pair wraps it.

Every other invocation site in this codebase does the opposite —
`meeting_orchestrator.py:108,215,273,368,527,632`, `chief_of_staff.py:379,407,445`,
`automation.py:469,488,520`, `reviewer_sync.py:236`, `control-center/server.py:817` —
all open a run with an `*_ACTIVITY_LABEL` and close it with `cost_usd=result.cost_usd`.

The evidence that this was meant to happen and was simply not wired:

* `agent_runtime.py:122-123` defines `IDEA_EVALUATION_ACTIVITY_LABEL` and
  `IDEA_EVALUATION_ACTIVITY_LIKE`. Both are **dead** — a repo-wide grep finds no
  reader of either. Only `IDEA_EVALUATION_TIMEOUT_S` and the allowlist are used.
* `opsdb.py:1800,1803` inserts `idea_rounds.agent_run_id` and
  `opsdb.py:2189` exposes `--agent-run-id` on `idea-round-add`. `evaluator.py:432-445`
  never passes it, so the column is always NULL.

So the single action the UI describes as *"This one spends money… the only part that
spends money"* (`pages.py:479-485`, `list_page`'s footer at `pages.py:346-348`) is the
one action invisible to `/costs.html`, to the by-path cost breakdown, and to the
restart-time run reconciliation that `IDEA_EVALUATION_ACTIVITY_LIKE` was defined to
drive.

Fix: wrap each `_invoke` in `opsdb.start_run(..., IDEA_EVALUATION_ACTIVITY_LABEL,
scope="idea", scope_id=idea_id)` / `end_run(..., cost_usd=result.cost_usd)`, following
`meeting_orchestrator._position()`'s existing shape; pass the synthesis run's id to
`idea-round-add --agent-run-id`; and include `IDEA_EVALUATION_ACTIVITY_LIKE` in the
startup reconciliation from finding 2.

### 4. Two shapes of well-formed roster JSON crash the evaluation and destroy a completed, paid-for run — `ops/idea-desk/evaluator.py:210` and `ops/idea-desk/evaluator.py:229-230`

Line 229-230:

```python
"out": [[str(a), str(b)] for a, b in
        (e for e in data.get("out", []) if isinstance(e, (list, tuple)) and len(e) >= 2)],
```

The filter admits `len(e) >= 2` but the unpack demands exactly 2. The prompt at
line 200 shows `["ceo, financial", "…"]` — a model that instead writes
`["ceo", "financial", "why they add nothing"]`, which is a natural reading of the same
instruction, raises `ValueError: too many values to unpack (expected 2)`. Verified.

Line 210 and 229: `data.get("in", [])` and `data.get("out", [])` return `None`, not
`[]`, when the model emits an explicit `"out": null` — `TypeError: 'NoneType' object
is not iterable`. Verified.

Both are thrown inside `_select_roster`, so they are caught by `run_evaluation`'s bare
`except Exception` (line 451) and surface to the Founder as *"something broke inside
the evaluation. That is a bug on our side"* — which is accurate but expensive: the
whole multi-agent run is discarded. Every other consumer of model output in this file
defends itself (the `isinstance` guards, `SELECTABLE` membership, the `depth`
whitelist); these two lines are the gap in an otherwise careful pattern.

Fix: `for a, b in …` → `entry[0], entry[1]` on the filtered entry; `data.get("in", [])`
→ `data.get("in") or []` in both places.

### 5. A Founder correction is silently lost when the evaluation it triggered fails — `ops/idea-desk/server.py:384-400`, `ops/idea-desk/evaluator.py:432-445`

`POST /api/correct/N` passes `note` straight to `evaluator.start()`. The note is only
ever persisted as `idea-round-add --founder-note` (line 443), i.e. **only on the
success path**. If the evaluation fails for any of the reasons above, the Founder's
words are gone — they see "The last evaluation did not finish", and the correction
they wrote is not in the database, not in the history panel, and not in any form
field.

This contradicts the product's central promise, stated in `close_panel`
(`pages.py:691`) and in the `_history` panel's own heading: nothing is deleted, your
words stay on record. A correction is the Founder's input, exactly like an edit, and
`idea_edits` shows the pattern for storing it independently of any round.

Fix: persist the correction before starting the evaluation (either its own
`idea_notes`-style append, or an `--founder-note` on a pending record), and have
`idea-round-add` attach the already-stored note rather than carry it through the
thread. At minimum, re-render the correction textarea pre-filled with the lost note
after a failure.

### 6. `safe_html` balances `<div>` but not the inline tags, so a stray `<b>` does escape the card — `ops/idea-desk/pages.py:237-247`

The comment at lines 235-236 states the balancing exists *"so a stray closing tag can
never escape the card it was written into and start eating the page."* The loop only
tracks `<div>`/`</div>`. `b`, `i`, `em`, `strong` are emitted unbalanced:

* `safe_html('<b>unclosed bold')` → `'<b>unclosed bold'` (verified).
* `safe_html('<strong/>')` → `'<strong>'` (verified) — the self-closing form the
  contract at `evaluator.py:282` never asks for, but which a model writes anyway,
  becomes an *opening* tag.

`<b>`/`<strong>`/`<em>`/`<i>` are HTML active-formatting elements: the parser
reconstructs them after the enclosing `</div>` closes, so an unclosed one bolds the
following Q&A cards, the Company View and the action bar. This is a rendering defect,
not an XSS one — no attribute or event handler survives, and I could not construct one
that does — but the stated invariant is only half-delivered.

For the record, what I tried and what the sanitiser correctly rejected: `<script>`;
`<b onclick="x">`; `<img src=x onerror=…>`; `<div class="sk" onclick="x">`;
`<div class="sk"onmouseover=alert(1)>`; `<div class="sk" >` (trailing space);
`<span class="lab unknown">` (prefix collision with `lab unk`); `<BR>`;
pre-escaped `&lt;script&gt;`; `<div class="sk` (unterminated);
`</div></div></div></div>` at depth 0 (all dropped);
`<div class="sk"><div class="two"><div>a</div>` (correctly closed to depth 0). The
`re.split(r"(<div[^>]*>|</div>)")` loop cannot mis-classify a text piece as a tag,
because `<` only re-enters the string via the four substitutions above it and each
emits a complete tag.

Fix: extend the balancing loop to the inline tags (track a stack, drop unmatched
closers, append missing closers), or drop `<b>`/`<i>`/`<em>`/`<strong>` from the
contract and let the models mark emphasis some other way. Whichever is chosen,
`safe_html` needs unit tests — see finding 11.

### 7. Non-ASCII digits pass `isdigit()` and crash `int()` — `ops/idea-desk/server.py:244` and `ops/idea-desk/server.py:343`

`str.isdigit()` is True for `'²'`, `'³'`, `'½'`-class characters that `int()` rejects
(`int('²')` → `ValueError`; verified). `GET /idea/²` therefore reaches `int(rest)` at
line 247 and produces a 500 "Something broke" page with a traceback on stderr, instead
of the 404 the guard was written to produce. Same at line 343 for every POST endpoint.

Fix: `rest.isascii() and rest.isdigit()` in both places, or `try: idea_id = int(rest)
except ValueError: → 404`. (No traversal risk exists — nothing here touches the
filesystem — and no injection risk: every subprocess argument is passed as a separate
`argv` element with no shell, and `idea_id` is `str(int(...))` by the time it reaches
`opsdb()`. That part is correct.)

### 8. `GET /approve/N` offers an Approve button on rounds that cannot be approved — `ops/idea-desk/server.py:263-269`, `ops/idea-desk/pages.py:704-725`

`_action_bar` (`pages.py:651-664`) correctly hides Approve when the recommendation is
not in `APPROVABLE`, and explains why. But `/approve/N` is reachable by typing the
URL, and `approve_panel` unconditionally renders an Approve button against
`rounds[-1]`. Submitting it hits `cmd_idea_approve`'s recommendation gate
(`opsdb.py:1841-1846`) and returns a 409 "That was refused".

The defence in depth works — that is the right layering, and the CLI gate is the
authoritative one. The defect is that the UI presents an action it knows will fail.
`/approve/N` on an already-approved idea has the same shape.

Fix: in the `render == "approve"` branch, redirect to `/idea/N` unless
`rounds[-1]["recommendation"] in pages.APPROVABLE` and the status is not already
`approved` — mirroring the check `_action_bar` already makes rather than adding a
third copy of it.

### 9. The evaluation's `finally` clears a marker it may no longer own — `ops/idea-desk/evaluator.py:455-463`, `ops/idea-desk/evaluator.py:466-474`

The DB-level guard in `cmd_idea_evaluation_start` correctly prevents a double-clicked
button from spending twice. But there is a window after `idea-round-add` clears
`evaluating_since` (`opsdb.py:1804`) and before the `finally` block's
`idea-evaluation-end` completes — up to `_opsdb`'s 30 s timeout. If the Founder starts
a second evaluation inside that window (the page they land on invites exactly that),
run A's `finally` then clears run B's marker and `_clear(idea_id)` wipes run B's
progress list. The database now says no evaluation is running while B's thread is
still spending money, and a third can be started on top.

The window is narrow and needs a fast Founder, but it is reachable and the failure is
silent duplicate spend.

Fix: have `idea-evaluation-start` return a token (its `evaluating_since` timestamp is
enough) and pass it to `idea-evaluation-end --if-since <token>`, making the clear a
compare-and-swap; `_clear(idea_id)` likewise only when the token matches. This is the
same ownership problem `end_run(run_id, …)` already solves by keying on the run id.

### 10. `idea-round-add` validates that `--answers` is JSON but not that it is the shape `pages.py` requires — `ops/db/opsdb.py:1778-1789`, consumed at `ops/idea-desk/pages.py:516-517`

`cmd_idea_round_add` checks `json.loads()` succeeds and nothing more. `pages.idea_page`
then does `answers.get(str(num))` and `pair[0]`. A round written with
`--answers '"hello"'` (valid JSON, wrong shape) makes `/idea/N` raise `AttributeError`
and return a permanent 500 for that idea, with no way to remove the row — `idea_rounds`
is deliberately append-only and immutable.

`evaluator._validate` (lines 383-407) is the only thing enforcing the shape, and it
sits in the caller rather than the writer, so any other user of the documented CLI
bypasses it. Related, in `_validate` itself: `entry = [""]` passes the truthiness check
at line 393 and stores an empty answer; `str(entry[0])` on a dict stores a Python repr
as the answer text; and neither `title` (line 407) nor any answer has a length cap, so
a 16 KB title lands in `list_page`'s single-line row.

Fix: move the shape validation into `cmd_idea_round_add` (ten keys, each a
2-element array of strings; `view` carrying the six required keys with `rec` in the
four allowed values) so the sole writer enforces the invariant the sole reader
assumes, and have `evaluator._validate` call the same function rather than keep a
second copy. Add a length cap on `title` and reject empty concise answers.

### 11. There are no tests, and `safe_html` is the function that most needs them — `ops/idea-desk/` (no test file)

`ops/db/` carries eight `test_*.py` files and the standard at
`ops/CODING_STANDARDS.md:11` is "Never claim something works without testing it." The
Idea Desk ships 2,092 lines with none. The specific gap that matters: `safe_html` is a
hand-rolled escape-then-partially-unescape sanitiser — the highest-risk function in
the module and the one most likely to be "improved" later by someone who does not know
which of its five substitutions are load-bearing and in what order.

Fix: add `ops/idea-desk/test_idea_desk.py` covering, at minimum — the twenty-odd
`safe_html` cases enumerated in finding 6 (each asserting the exact output string);
`_extract_json` against fenced, unfenced, prose-with-braces, two-object and truncated
input; `_validate` against each rejection branch and each coercion; and the roster
parsing against the malformed shapes in finding 4.

### 12. `_ensure_schema` swallows a migration failure and starts the server anyway — `ops/idea-desk/server.py:431-439`

The `except Exception` prints advice and returns. The server then binds the port and
serves. Every subsequent evaluation dies inside `_idea_row`'s migration check
(`opsdb.py:1735-1739`) — which is a good, clear message, but it arrives at the end of
a run that already spent money on agent calls, rather than at startup where the
problem actually is. The commit that added this ("Migrate the database on every start")
was written precisely because a stale schema is not hypothetical.

Fix: if `init` fails, refuse to start, with the same directness as the port-in-use
message at lines 456-468.

---

## Non-blocking observations

These are not required for a pass, but should be picked up.

* **`ops/idea-desk/pages.py:494,499,538-539,600-602,622` — `flash` is dead.** It is
  never passed by any caller. As written it is also the one path in `pages.py` that
  interpolates a parameter into HTML *without* `e()`, so it is a trap for the next
  person who wires it up. Delete it or escape it.
* **`ops/idea-desk/pages.py:309` — `error_page`'s `status` parameter is unused;** the
  real status is passed separately to `_send`. Every call site passes both and they
  can disagree — `ops/idea-desk/server.py:406` sends **HTTP 200** with a page titled
  "501". Drop the parameter and derive the title from the status actually sent.
* **`ops/idea-desk/server.py:337-339` — `out.rsplit("id=", 1)[-1]`** parses the new id
  out of `opsdb`'s human-readable stdout, then interpolates it into a `Location`
  header. Not currently exploitable (the format is fixed and numeric), but a `--json`
  output mode on `idea-create`, or a `.isdigit()` check before the redirect, removes
  the coupling to a print string.
* **`ops/idea-desk/server.py:133-142` — `opsdb()` does not distinguish
  `subprocess.TimeoutExpired`** from a refusal. A 30 s timeout surfaces as the generic
  500 "Something broke" rather than the accurate "the database is busy".
* **`ops/idea-desk/seed_founder_idea.py:257` duplicates `server.py:72-76`'s read-only
  connect** and omits its `quote()` of the path; `line 248`'s `subprocess.run` omits
  the `timeout=` every other `opsdb` wrapper in the module set carries. Import the
  helper rather than keeping a third copy.
* **`ops/idea-desk/server.py:173-192` — expired sessions are only evicted when that
  exact sid is presented again.** Unbounded in principle, trivial in practice on a
  single-Founder loopback server. Worth a sweep if the login route stays unthrottled
  (finding 1), since each failed-then-abandoned session is a permanent dict entry.
* **`ops/idea-desk/doctor.py:53` hardcodes the branch name
  `claude/orchestrator-chief-of-staff-f35grl`** and reports `!!` on any other branch.
  This will be wrong the first time work moves branches, and a diagnostic tool that
  cries wolf is worse than none. Read the expected branch from the repo (upstream
  tracking ref) or drop the assertion to informational.
* **No `Content-Security-Policy` on any response (`ops/idea-desk/server.py:154-163`).**
  The Control Center does not set one either, so this is not a regression — but the
  Idea Desk is the first place in this product that deliberately un-escapes
  model-authored HTML, which is exactly the situation CSP is defence-in-depth for.
  `default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors
  'none'` costs one header and would have contained finding 6's class of bug entirely.
* **`ops/idea-desk/evaluator.py:91-110` — `_extract_json`'s fallback is a
  first-`{`-to-last-`}` slice.** The fenced-block path is correct (verified: the
  non-greedy `\{.*?\}` still extends to satisfy the trailing fence, so nested objects
  parse). But unfenced output with a brace anywhere in the surrounding prose, or two
  JSON objects, fails and discards the run. It fails *closed*, which is right — the
  cost is that a minutes-long paid evaluation is thrown away over punctuation. A
  brace-depth scan forward from each `{` is about eight lines and removes the whole
  class.
* **`ops/idea-desk/evaluator.py:113-124` — one failed perspective aborts everything.**
  With `IDEA_EVALUATION_TIMEOUT_S = 180` and up to five sequential agent calls, a
  single timeout on the fourth discards the three that succeeded. Consider degrading
  (synthesise from whoever answered, and say in the round who did not) rather than
  losing the run.
* **`ops/idea-desk/pages.py:465` — the evaluating page refreshes every 6 s forever,**
  with no elapsed-time display and no upper bound. Once finding 2 is fixed this is
  survivable; a visible "started N minutes ago" would still help the Founder tell a
  slow run from a stuck one.
* **`ops/idea-desk/server.py:253-262` — `/close/N` and `/correct/N` silently drop
  their panel** when `evaluating_since` is set, because `idea_page` returns
  `evaluating_page` before looking at `panel`. Correct behaviour, invisible reason.

## What I checked and found sound

Recorded so the next reviewer does not redo it:

* **Injection.** Every `opsdb` invocation passes a list to `subprocess.run` with no
  `shell=True`; no Founder- or model-supplied value is ever concatenated into a command
  string. Agent names reaching `agent_runtime.invoke_agent` are filtered against
  `SELECTABLE` at `evaluator.py:215` before use and re-checked against
  `IDEA_EVALUATION_ALLOWLIST` at `agent_runtime.py:297`.
* **Traversal.** No path segment reaches the filesystem; the only URL-derived values
  are integers (modulo finding 7).
* **SQLite connections.** `_connect()` callers at `server.py:92-106` and `109-123`
  both close in a `finally`; `seed_founder_idea.py:257-261` does too. No leaked
  connections on any path I traced. The read-only URI means a bug cannot write.
* **Concurrency.** `SESSIONS` is only touched under `SESSIONS_LOCK`; `PROGRESS` only
  under `_PROGRESS_LOCK`; `SESSION_TOKEN` and `BUILD` are immutable after import. The
  only shared-mutable-state defect is the cross-run ownership issue in finding 9, which
  is a logical race, not a data race.
* **CSRF.** The per-process token plus `SameSite=Strict; HttpOnly` matches the Control
  Center's model. The token being readable from the unauthenticated `/login` is the
  same disclosed property the Control Center documents at its lines 131-144, not a new
  gap.
* **Database consistency on failure.** `idea-round-add` sets `status`,
  `evaluating_since = NULL` and `last_error = NULL` in one transaction with the round
  insert (`opsdb.py:1796-1811`), so there is no window where a round exists without the
  status having moved. The redundant `idea-evaluation-end` that follows on the success
  path is harmless.

---

## Verdict

**REJECT** — returned to developer.

Twelve required fixes, listed above. Findings 1, 2 and 3 are the ones that matter
most, and they share a cause worth stating plainly: each is a control this codebase
had already built, reviewed and documented (Security's fix C1;
`reconcile_orphaned_runs`; the `agent_runs` cost trail) that the Idea Desk did not
carry across when it became its own program. Two of the three left their constants and
their column behind, unused, as evidence that the intent was there. When these come
back for re-review I will check the fixes against the originals rather than in
isolation — a private second copy of the lockout counter, or a second reconciliation
routine, would not clear finding 1 or 2.
