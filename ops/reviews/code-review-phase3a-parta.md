# Code Review — TASK-015 Phase 3A Part A (Chief of Staff Founder Interface)

Commit reviewed: `2e9ff4f656770e963796d55634b638d7ae671b1b` — "TASK-015 Part A:
Chief of Staff Founder interface (development complete, pending Code Review)."

Reviewed against the approved, corrected design:
`ops/reviews/cto-phase3a-architecture.md` §A.1-A.5, including every
"Correction (Security's/Red Team's ...)" passage that applies to Part A
(C3's exact `CONSULT:` candidate tuple, R3's cost/friction disclosure,
NB4's meeting_orchestrator refactor acceptance check). Skimmed
`ops/reviews/security-phase3a-threat-model.md` and
`ops/reviews/red-team-phase3a-architecture.md` for the reasoning behind
each required fix. Every changed/new file was read in full, not sampled;
findings below were independently verified against the actual code, not
taken from the developer's own handoff/activity-log claims.

**Verdict: PASS.**

## Verification, item by item

1. **Zero-tool guarantee.** `agent_runtime.py`'s diff touches only the
   validity check inside `invoke_agent()` (widened to also accept
   `CHIEF_OF_STAFF_ALLOWLIST`). `_run_claude()` itself has zero lines
   changed in this diff — `--tools ""` / `--strict-mcp-config` remain
   unconditional, built from a fixed `cmd` list with no parameter for a
   caller to request more. `CHIEF_OF_STAFF_ALLOWLIST` only widens *which
   agent_name strings* `invoke_agent()` will accept; it has no path into
   `_run_claude()`'s argv construction. This is the load-bearing property
   of the whole design and it holds.

2. **`orchestrator` stays out of `ASK_AGENT_ALLOWLIST`.** Confirmed
   unchanged (`ASK_AGENT_ALLOWLIST = ("cto", "qa", "ceo", "financial",
   "project-manager")`). `_handle_ask()` checks `agent_name not in
   agent_runtime.ASK_AGENT_ALLOWLIST` and 404s — `/api/agents/orchestrator/ask`
   still 404s. Exactly one route (`POST /api/chief-of-staff/ask`) reaches
   this agent identity.

3. **CSRF+session gating.** `do_POST()`'s dispatch: fail-closed credential
   gate, path matching (including the new `is_chief_of_staff_ask`
   branch, correctly excluded from every earlier match and excluding
   itself from `is_meeting_create`), 404 if nothing matches, then body
   parsing, then `_require_csrf_token()`, then (after login/logout
   short-circuits) `_authenticated_session()` — identical order to every
   other write route, before `_handle_chief_of_staff_ask()` ever runs.

4. **`CONSULT:` candidate tuple.** `meeting_orchestrator.CONSULT_CANDIDATE_ROLES
   = tuple(r for r in agent_runtime.MEETING_PARTICIPANT_ALLOWLIST if r !=
   "ceo")` = `("product", "cto", "financial", "marketing", "qa",
   "security", "red-team")` — exactly Security's C3 correction, computed
   once and imported by `chief_of_staff.py` (`_CONSULT_CANDIDATES =
   meeting_orchestrator.CONSULT_CANDIDATE_ROLES`), not a second hand-typed
   tuple.

5. **`CONSULT:` parsing never trusted as an instruction.** Traced
   `_parse_consult()` in `chief_of_staff.py`: a fixed regex requires a
   line literally starting with `CONSULT:`; only the text captured after
   the label is scanned, via word-boundary regex, against the fixed
   candidate tuple; an unrecognized name (`ceo`, `orchestrator`, or
   anything prompt-injected) simply never matches and is dropped. Python
   alone decides whether to call `run_consult_meeting()` — identical
   trust pattern to `_select_participants()`/`_parse_selection()`. One
   judgment call, disclosed in the developer's own handoff and in the
   docstring: on multiple `CONSULT:` lines, the *first* match is used,
   not the last (unlike Part B's stricter RT2 `VERDICT:` requirement).
   This is lower-stakes than RT2's binary-verdict problem — a spurious
   extra consult is bounded by the already-disclosed ~$4 worst case, not
   a silently wrong PASS/REJECT — and the design doc does not specify
   first-vs-last for this case. Acceptable as shipped; noted, not a
   blocker.

6. **`meeting_orchestrator.py` refactor.** Read `_gather_and_synthesize()`
   and both `run_meeting()`/`run_consult_meeting()` bodies. The extraction
   is genuinely mechanical: `run_meeting()`'s old inline
   gather-then-synthesize block is byte-for-byte the same logic, moved
   into the new function unchanged (same `ThreadPoolExecutor` sized to
   `MAX_CONCURRENT_INVOCATIONS`, same `positions` dict built from
   `as_completed()`, same call to `_synthesize()` then
   `opsdb.finalize_meeting_synthesis()`); `run_meeting()` calls it with
   the same `participants`/`topic` values it always computed, in the same
   place. `cap_participants()` was extracted from `_validate_selection()`'s
   inline dedup/cap loop with the same before/after logic verified
   equivalent (`deduped = validated + dropped` reconstructs the original
   list for the explanation text). This satisfies Red Team's NB4
   acceptance check by inspection, not merely by the developer's claim.

7. **`run_consult_meeting()` skips CEO-driven selection.** Confirmed: no
   call to `_select_participants()`; it uses the Chief-of-Staff-parsed
   `participants` argument directly, only defensively re-filtering `ceo`
   out and prepending it once. No wasted invocation.

8. **State digest boundedness.** `MAX_STATE_DIGEST_CHARS = 6_000` enforced
   in `_build_state_digest()` with an explicit truncate-and-flag. Every
   new `derived_state.py` helper (`open_risks_digest`,
   `active_tasks_digest`, `pending_approvals_digest`,
   `recent_decisions_digest`, `recent_status_transitions_digest`,
   `recent_review_qa_digest`, `recent_deployments_digest`) has its own
   `limit=` default matching the design doc's numbers, and applies
   `LIMIT ?` in SQL (the review/QA `UNION ALL` correctly limits the
   *combined* result, not per-table, avoiding a double-cap bug).
   `automation_status_digest()` is correctly and explicitly not
   implemented (Part B scope, not Part A).

9. **Never-fabricate discipline.** Present, correctly, only as a persona
   instruction — `.claude/agents/orchestrator.md`'s new section: "Never
   fabricate state or memory. If something isn't in the state block or
   the conversation so far, say you don't have that in view rather than
   guessing." Matches the Founder's exact requirement and is backed
   structurally by the digest being genuinely bounded (item 8) so the
   instruction is honest, not aspirational.

10. **Never-execute discipline.** Present in the same persona doc:
    explicit instruction not to treat a chat message as an executable
    command, with the doc itself connecting this to the structural fact
    (zero tools) rather than presenting the instruction as the only
    safeguard. Structurally confirmed by item 1 — there is no tool grant
    this invocation could use even if a prompt-injected instruction
    convinced the model to try.

11. **Orphan reconciliation.** `_reconcile_orphaned_runs()` gained a
    fourth call, `opsdb.reconcile_orphaned_runs(conn,
    agent_runtime.CHIEF_OF_STAFF_ACTIVITY_LIKE, status="failed")`,
    distinct from `ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE` so a crash
    mid-exchange isn't conflated with an orphaned validation step.

12. **XSS/escaping.** `generate_agents.py`'s `render_ask_agent_section()`
    now branches on `CHIEF_OF_STAFF_ALLOWLIST` vs `ASK_AGENT_ALLOWLIST`
    to pick `action`/`activity_like`/`panel_label`/`max_chars`, but reuses
    the exact same bubble-rendering code downstream — `e(m["body"])`,
    `e(action)`, `e(panel_label)`, `e(token or "")` all pass through the
    existing `layout.e()` escaping helper, identical discipline to every
    other agent's Ask-Agent panel.

13. **Maintainability/architecture consistency.** `chief_of_staff.py`
    mirrors `meeting_orchestrator.py`'s shape closely: pure orchestration
    glue, opens/closes short-lived `opsdb.connect()` connections per step
    (consistent with `meeting_orchestrator.py`'s own multi-connection
    convention, not a deviation), never touches `sqlite3` directly, never
    invokes the runtime except through `agent_runtime.invoke_agent()`.
    No duplicated logic found — the shared `cap_participants()` extraction
    and reused `CONSULT_CANDIDATE_ROLES` are genuine DRY wins, not
    over-engineering.

14. **`opsdb.py`/`schema.sql` untouched.** Confirmed — zero diff lines in
    either file in this commit. `ops/db/operations.sqlite3`'s binary diff
    is exactly one new `handoffs` row and one new `agent_activity` row
    (Development's own handoff for this task), not test-data pollution of
    the live database; the developer's own activity log states testing
    was done against an isolated `OPSDB_PATH`-scoped scratch database,
    consistent with what the binary diff actually shows.

15. **`report.py --check`.** Fails (`STALE`) at this commit — but bisecting
    confirmed the staleness was already present starting at `e81519d`
    ("TASK-015: create task record for Phase 3A"), several commits before
    the CTO architecture proposal and before this Development commit; at
    the prior milestone-close commit (`c8b6c39`) the check passes cleanly.
    This diff did not introduce the staleness and does not need to have
    fixed a pre-existing gap from an earlier, already-merged commit chain
    — not a defect in this diff, but worth flagging to whoever owns
    `ops/reports/CURRENT_STATUS.md` regeneration going forward.

## Non-blocking observations (not required for PASS)

- `_parse_consult()`'s first-match-wins behavior (item 5) is a reasonable,
  explicitly-disclosed judgment call given the bounded blast radius, but
  if a future revision tightens `CONSULT:` parsing the way Part B's
  `VERDICT:` parsing was tightened (RT2), this is the analogous line to
  revisit.
- `ops/reports/CURRENT_STATUS.md` should be regenerated and committed by
  whoever next touches the reporting pipeline (item 15) — pre-existing,
  not blocking this review.

## Conclusion

No unresolved finding from a prior reject applies here (first pass on
this diff). Every one of the 15 requested verification points was traced
against the actual shipped code, not the developer's report. The single
most important property in this diff — the zero-tool guarantee — holds
by direct inspection of `_run_claude()`'s untouched body. No correctness,
security, or architecture-consistency defect found. **PASS.**
