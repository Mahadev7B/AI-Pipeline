# Red Team review — Milestone 2B3B correction (TASK-010)

Reviewing `ops/reviews/cto-milestone2b3b-correction-architecture.md`
before Development. Performed directly — `Agent`/`TaskCreate` remain
unavailable this session (confirmed again for this correction pass: no
subagent-dispatch tool is present in this session's tool list).

## Verdict: PASS with conditions

## 1. Reconciliation fix

Sound and minimal — reusing the existing generic
`opsdb.reconcile_orphaned_runs()` rather than writing a second
implementation is exactly the discipline this project already applies
elsewhere. One challenge: **does reconciling a meeting-participant run
as `'failed'` on restart correctly interact with the honest-failure
rendering already built for a normal in-flight failure?** Checked
`generate_meetings.py`'s `build_meeting_detail()`: it distinguishes
"in `positions_by_agent`" (a message exists) from "selected but absent"
(no message) — it does not inspect `agent_runs.status` at all. A
reconciled `'failed'` run with no corresponding message therefore
renders identically to a live, non-crash failure — the same honest
"Selected, but no response was recorded" card. Confirmed correct: no
special-casing needed, the existing failure-rendering path already
covers this case for free, because it was built to key off the presence
of a real message, not the run's status.

**Condition 1:** Development must verify live — not just reason about —
that a genuinely killed (`kill -9`, not a clean shutdown) server process
mid-meeting, followed by a real restart, actually reconciles the
open meeting-participant run(s) and that the meeting page still renders
correctly afterward. Same rigor 2B3A's own review required for the
analogous Ask-Agent case.

**Condition 2:** The log-message split (per-pattern counts) must not
silently swallow a count of zero for one pattern while reporting a
nonzero count for the other in a way that looks like only Ask-Agent
runs were ever checked — Development should verify both calls always
execute, not just the first if the first raises.

## 2. Test-isolation guard

Correctly scoped — a one-line opt-in import, not a rewrite of `opsdb.py`
or `server.py`'s real behavior. Considered and rejected the alternative
of a hard runtime check inside `opsdb.connect()` itself (e.g., refusing
to write unless some `--i-know-this-is-live` flag is passed): that would
break every legitimate real CLI/HTTP usage path, which must be able to
write to the live database without extra ceremony — correctly avoided
by the proposal.

**Condition 3:** Confirm the guard's check is against the *resolved,
absolute* path (`Path.resolve()`), not a raw string comparison — a
relative-path or symlink difference between how `opsdb.DB_PATH` and the
guard's own computed live path are constructed could produce a false
negative (guard doesn't fire when it should) just as easily as a false
positive.

**Condition 4:** This module must never itself be imported by
`opsdb.py`, `server.py`, or any other production code path — it exists
only for ad hoc test scripts to opt into. Development must not wire it
into the real CLI.

## Additional scrutiny — no further blocking findings

- Confirmed this correction does not reopen or touch either open risk
  (`risks.id=2`, `risks.id=3`) — it's an internal robustness/tooling fix,
  not an authorization change.
- Confirmed the correction does not implement any of the six
  Founder-decision items from the conformance review (§4 of that
  document) — verified by reading the CTO proposal, which is scoped to
  exactly the reconciliation gap and the test guard, nothing else.

Proceeding to Development with conditions 1–4 to close.
