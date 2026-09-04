# Code Review — TASK-015 Phase 3A Part B (Limited Automated Orchestration)

Commit reviewed: `d11f7328b0df6d75d01caefbef18828f11b71bc` — "TASK-015 Part B:
limited automated Developer->Code Review orchestration (development
complete, pending Code Review)." Built on top of Part A's already-PASSed
`2e9ff4f`/`0ec66fe` (see `ops/reviews/code-review-phase3a-parta.md`).

Reviewed against the fully-corrected design: `ops/reviews/cto-phase3a-architecture.md`
§B.1-§B.13 including every "Correction (Security's/Red Team's ...)"
passage (C1-C4/R1-R6, RT1-RT3/NB1-NB5) — the corrected text taken as
authoritative. Cross-checked against `ops/reviews/security-phase3a-threat-model.md`
and `ops/reviews/red-team-phase3a-architecture.md` for reasoning. Every
changed/new file read in full. Findings independently verified against
the actual code and, where feasible, by direct execution (see below) —
not taken from the developer's own handoff/activity-log claims.

**Verdict: PASS.**

## Independent verification, the four required fixes

1. **RT3 (claim-before-eligibility-check ordering) — verified by direct
   execution, not just reading.** `_process_candidate()` calls
   `opsdb.create_automation_event()` as the literal first DB-writing step,
   strictly before `_review_claimed_event()`'s handoff/SHA/path checks.
   Wrote a scratch-DB script exercising `opsdb.create_automation_event()`
   directly: a second claim attempt for the same `trigger_status_history_id`
   correctly returns `None` (idempotency), and a claim attempt after
   `tasks.status` moved on to `QA` also correctly returns `None`
   (scenario 4) — in both cases exactly one `automation_events` row exists
   total. Traced every §B.10 skip path (2/3/6/8) in `_review_claimed_event()`
   — each is reached only after the claim succeeded (`event_id` already
   assigned), and each calls `_skip()`/`_end_event()` on that same
   `event_id`. No path exists where an eligible-looking candidate is
   evaluated without first being claimed. The per-task/company-wide cap
   checks (§B.7) are also performed post-claim, a deliberate, disclosed
   extension beyond RT3's literal scope, for the identical anti-infinite-
   reprocessing reason (consistent with NB1's expectation that a capped
   candidate gets a real row). Confirmed correct.

2. **RT2 (VERDICT: parsing) — verified by direct execution.** Ran
   `_parse_verdict()`'s actual regex/logic against three constructed
   inputs: (a) `"...VERDICT: PASS...\n\nVERDICT: REJECT"` (PASS mentioned
   mid-reasoning, REJECT as the true last line) → correctly returns
   `'reject'`; (b) a `VERDICT:` token present but not on the last line →
   returns `None`; (c) no `VERDICT:` line at all → returns `None`. The
   line-selection (`lines[-1]` after filtering blank lines) and anchored
   regex (`^VERDICT:\s*(PASS|REJECT)\s*$`) match the required "strictly
   last non-blank line, only that line parsed" specification exactly.
   `_invoke_and_record()` treats `None` as a distinct fourth outcome
   (`status='failed', outcome='error'`), never fabricating a `review_results`
   row. Confirmed correct.

3. **C1 (SHA validation) — verified, including the empirically-tested
   deviation.** `_SHA_RE` format check runs before `_commit_exists()`
   (existence check via `git cat-file -e -- <sha>^{commit}`), both before
   any SHA is used in `_git_diff()`/`_git_show_file()`. `_git_diff()` uses
   `[..., base_sha, head_sha, "--", *paths]` — revision/pathspec separated.
   Independently tested the developer's disclosed `git show <sha>:<path>`
   deviation by running both forms against this actual repo: `git show --
   "<sha>:<path>"` returns **exit 0 with zero bytes of output** (silently
   wrong, not merely non-idiomatic), while `git show "<sha>:<path>"`
   (no `--`) returns the correct file content. The claim is empirically
   true, not merely asserted, and the omission is safe because `head_sha`
   is already format/existence-validated hex before this call — it can
   never be misread as an option flag. Confirmed correct, and the judgment
   call is justified, not merely accepted on faith.

4. **§B.1.2/R1 (path validation + git-object retrieval)** — `_validate_repo_path()`
   rejects absolute paths, `..` components, and anything whose
   `resolve()` escapes `REPO_ROOT`, called for every `files_changed` entry
   before any filesystem/git operation; any single failing entry skips
   the whole candidate (never a partial file set). `_git_show_file()`
   retrieves content via `git show <head_sha>:<path>` — the git object
   database — never `Path(...).read_text()`. Traced in the actual code,
   not the developer's demonstration.

5. **C4 (reject-requires-returned_to)** — the check lives inside
   `opsdb.record_review_result()` itself (`raise ValueError(...)` for
   `result == "reject" and not returned_to`), not only in `cmd_review_result`'s
   wrapper — protects `automation.py`'s in-process calls. Confirmed.

6. **RT1 (record_task_status extraction)** — `record_task_status()` is a
   genuine plain, `conn`-taking function; `cmd_task_status` is now a thin
   wrapper catching `ValueError` and printing the same message format as
   before. Ran both a fresh `init` and a re-`init` against an
   already-initialized scratch DB — no error either time (idempotency
   holds), and a simulated pre-Phase-3A `handoffs` table (missing the two
   new columns, with an existing row) correctly gained both columns via
   the `ADD COLUMN` path with the existing row's data preserved
   unchanged. Confirmed no regression to the CLI's documented behavior.

## Remaining required checks

- **Zero-tool guarantee**: `git diff` on `agent_runtime.py` touches zero
  lines inside `_run_claude()` (confirmed via `grep`) — only
  `invoke_agent()`'s allowlist check widens. `AUTOMATED_REVIEW_ALLOWLIST`
  only widens which `agent_name` strings are accepted, no path into argv
  construction.
- **Four caps**: read `_check_task_lifetime_cap`/`_check_daily_invocation_cap`/
  `_check_daily_spend_cap` in full — correct exclusion of the just-claimed
  row from its own prior-count query, correct `$0.50`-per-running-row
  reservation (counts the just-inserted row exactly once, via the
  `running` query, not doubled with `spent`), correct `outcome='capped'`
  set at both cap call sites, correct per-cycle batch cap (no row created
  for the 6th+ candidate, picked up next cycle — matches NB1's note that
  this case never sets `outcome='capped'` because no row exists).
- **Per-candidate isolation**: `_poll_once()`'s loop wraps each
  `_process_candidate()` call individually; `_process_candidate()`'s own
  inner try/except ends the claimed event `failed/error` before
  re-raising, which `_poll_once()`'s per-candidate catch then logs and
  `continue`s past — one candidate's exception cannot abort the batch or
  leave a row `running`.
- **Kill switch**: `opsdb.set_automation_enabled()` is the only writer of
  `automation_state`; called only from `_handle_automation_toggle()`,
  reached only through `do_POST()`'s existing CSRF-then-session gate
  (identical order/position to every other write route, traced in
  `server.py`). The poller only reads it, twice per candidate cycle
  (top-of-cycle and immediately pre-claim).
- **Crash recovery**: `reconcile_stuck_automation_events()` is called
  inside `_reconcile_orphaned_runs()`, itself called in `main()` before
  the poller thread is started — correct ordering.
- **Schema migration**: `automation_events`/`automation_state` match
  §B.3/§B.4 exactly, including NB5's two extra indexes. `handoffs.base_commit_sha`/
  `head_commit_sha` migration verified empirically idempotent and correct
  on both a fresh and a pre-existing DB (see above).
- **XSS/injection**: every dynamic value in `generate_automation.py`
  passes through `layout.e()`; `chief_of_staff.py`'s automation section is
  plain-text fed into a model transcript, not rendered HTML, so no `e()`
  discipline applies there. Every new `opsdb.py` write function uses
  parameterized queries throughout.
- **`risks.id=3`**: confirmed via direct DB diff (`before.sqlite3` vs.
  `after.sqlite3`, extracted from the two commits) — `status` unchanged
  (`open`), `description` byte-identical, only `mitigation` appended. No
  other risk row touched.
- **Live DB hygiene**: `git show d11f732 -- ops/db/operations.sqlite3`
  diffed programmatically — two new empty tables
  (`automation_events`/`automation_state`, seeded with the one kill-switch
  row) plus one legitimate new `agent_activity` row (Development's own
  handoff summary for this task, matching this project's existing
  convention). No leaked test tasks/automation_events rows in the live DB.
- **`report.py --check`**: ran it — passes clean (`OK: ... matches the
  live database`).
- **Compile check**: `py_compile` clean on every touched Python file.

## Non-blocking observations (not required for PASS)

- `derived_state.automation_status_digest()`'s docstring promises a
  `"spend_ceiling_usd"` key in its return dict; the actual `return {...}`
  does not include that key (only `spend_today_usd`). No caller currently
  reads the missing key (`generate_automation.py` uses its own local
  `SPEND_CEILING_USD` literal, `chief_of_staff.py` doesn't reference it
  either), so this is a harmless docstring/code mismatch, not a bug —
  worth a one-line fix next time this file is touched.
- `ops/SECURITY.md`'s Part B section states the `risks.id=3` consequence
  language was "Appended to its `description`" — it was actually appended
  to `mitigation` (the developer's own handoff correctly discloses this
  as judgment call #3, since `risk-resolve` has no `--description` flag).
  Minor doc-wording inaccuracy in `SECURITY.md` itself; the DB write is
  correct and the disclosure elsewhere is accurate.

## Conclusion

All four independently-required fixes (RT3, RT2, C1, C4) verified not
merely present as text but functionally correct — RT3 and RT2 confirmed
by direct execution against the actual shipped functions, C1's SHA/`--`
handling confirmed by testing `git show` behavior directly against this
repository. RT1's extraction, the four caps, per-candidate isolation, the
kill switch's write boundary, crash recovery ordering, the schema
migration's idempotency, XSS discipline, and DB hygiene were each traced
in the actual code (not the developer's report) and hold. Two harmless,
non-blocking documentation nits found, neither a defect in behavior.
**PASS.**
