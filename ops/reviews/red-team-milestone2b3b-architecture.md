# Red Team review — Phase 2, Milestone 2B3B architecture

TASK-010. Reviewing `ops/reviews/cto-milestone2b3b-architecture.md`
before any code is written. Recorded via `opsdb.py review-result
--task-id 10 --type code --by red-team`. This file mirrors that record.

Note on process: performed directly rather than via a spawned red-team
subagent (the `Agent` dispatch tool has been unavailable this session
since Milestone 2B3A — same disclosure as every review from that
milestone onward). Same empirical-testing standard: claims below were
verified against real live invocations, not accepted on the proposal's
word.

## Verdict: PASS with conditions

Core design is sound and correctly reuses 2B3A's foundation rather than
re-deriving concurrency safety from scratch — the one real behavioral
addition (`wait_for_slot`) is narrowly scoped, doesn't touch the
existing Ask-Agent path, and doesn't expand the global concurrency
bound. The three Design Conformance questions were answered with real
reasoning, not just asserted. Two of the proposal's own claims were
independently verified live rather than trusted:

- **Participant-selection format compliance**: ran the actual CEO
  selection prompt twice with different real topics. Both times CEO
  returned a clean, exactly-formatted comma-separated list from the
  candidate set, with sensible, topic-appropriate selections (a
  rate-limiting question pulled in `product, cto, security, qa,
  red-team`; a pricing/strategy question pulled in `product, cto,
  financial, marketing, red-team`). The second case is a real 6-
  participant scenario (5 selected + mandatory CEO) — confirms the
  participant cap is a reachable case worth actually testing, not a
  theoretical one.
- **The 10s socket timeout doesn't fire during long synchronous work**:
  verified directly, not just reasoned about — ran a real Ask-Agent
  request through a driver script that injected an artificial 15-second
  delay in application code before the real invocation proceeded; the
  request completed successfully after ~20s with no dropped connection.
  Confirms `Handler.timeout=10` genuinely governs socket I/O stalls
  only, supporting the proposal's ~2-minute worst-case synchronous
  meeting request as safe from this specific failure mode.

## Answers to the proposal's 5 open questions

1. **Cap of 6 total participants**: affirmed, now with real evidence
   behind it (see above — a legitimate topic actually produced 6). Not
   too low (still lets a real cross-cutting question pull in 5 distinct
   lenses plus CEO) and bounds worst-case duration/cost to something
   disclosed and real.
2. **`wait_for_slot=True`, scoped only to meeting orchestration**:
   affirmed. It doesn't touch the semaphore's total capacity (still 3),
   doesn't touch the Ask-Agent route's existing non-blocking behavior at
   all (different call site, different default), and is the narrowest
   mechanism that actually satisfies "every selected participant gets
   invoked" without inventing a second concurrency primitive. A
   meeting-specific separate pool (the alternative posed) would be
   strictly worse — it would let meetings and Ask-Agent traffic run
   *more* real subprocesses simultaneously in total, directly
   undermining "concurrency is deliberately bounded" as a system-wide
   property.
3. **`meetings.positions` left unwritten, positions derived from
   `messages`**: affirmed — same reasoning already applied and accepted
   for Ask-Agent's "one conversation store" rule; duplicating position
   text into a second column is the same category of risk this project
   keeps correctly rejecting.
4. **No exclusivity guard on meeting-participant runs**: affirmed — the
   reasoning (each invocation is independent and stateless, unlike
   Ask-Agent's single ongoing per-agent thread) is sound, and forcing
   an exclusivity guard here would make multi-meeting operation
   impossible for no real correctness benefit.
5. **~2-minute worst-case synchronous request**: affirmed as safe from
   the specific failure mode tested (socket timeout) — see verification
   above. Real UX cost (a Founder's browser tab waiting up to 2 minutes)
   is disclosed, not hidden, and matches this project's already-accepted
   philosophy that a real result is worth a real, bounded wait rather
   than inventing async-job infrastructure to avoid it.

## Conditions Development must close

1. **Lenient parsing for CEO's selection output.** Both live tests
   returned clean, exactly-formatted responses, but that's not a
   guarantee — Development must parse case-insensitively, tolerate
   surrounding whitespace/punctuation, and match against the fixed
   candidate list by normalized substring/equality, not require exact
   formatting. Never trust anything CEO returns as a literal role name
   without validating it against `MEETING_PARTICIPANT_ALLOWLIST` first
   — same "validate every returned name" discipline the proposal already
   states for the allowlist itself.
2. **Deterministic truncation at the 6-participant cap.** If CEO
   nominates more than 5 others, take the first 5 in the order CEO
   listed them — no re-prompting, no silent randomness.
3. **A topic length cap**, matching `MAX_ASK_MESSAGE_CHARS`'s existing
   pattern — an unbounded topic field is the same class of gap that
   pattern already closed for Ask-Agent messages.
4. **Every `ThreadPoolExecutor` worker must open and close its own
   `opsdb.connect()`** — verify explicitly in Code Review, don't assume
   from the design doc's statement alone (this is exactly the kind of
   claim 2B3A's own Red Team review insisted on verifying by grep, not
   trusting).
5. **Duplicate meeting submission (a double-click on "Raise a
   question") is an accepted, disclosed v1 limitation, not a blocker.**
   Each submission creates a fully independent, valid meeting — real,
   not corrupted, just potentially redundant and doubly-costed. QA must
   confirm this behaves cleanly (no crash, no corrupted shared state)
   under a real concurrent double-submit, but no new dedup mechanism is
   required for this milestone.
6. **Failure-path honesty must be verified per-participant, not just
   per-meeting.** QA must confirm that when one participant's
   invocation fails, the meeting record shows a real absence (no
   position from that agent, and ideally a visible note that they were
   selected but didn't respond) rather than either fabricating a
   position or silently omitting any trace that they were asked at all.
7. **CEO's synthesis call failing must not discard already-gathered
   real positions.** QA must verify a meeting where every participant
   succeeds but the final synthesis call itself fails still persists
   and displays every real position, with `recommendation`/`agreements`/
   `disagreements`/`unresolved_questions` honestly `NULL`/"not
   available," never blocking on or discarding the real work already
   done.

## Additional scrutiny — no further blocking findings

- Considered whether `wait_for_slot=True`'s bounded wait could ever
  deadlock: `ThreadPoolExecutor(max_workers=3)` submitting at most 6
  participant tasks means at most 3 threads are ever concurrently
  competing for the 3-permit semaphore at once — no scenario where more
  waiters exist than could eventually be served, and each wait is itself
  bounded by the per-call timeout. No deadlock found.
- Cost: worst case ~8 real invocations per meeting (1 select + up to 6
  positions + 1 synthesis), each capped at `MAX_BUDGET_USD`. Real, but
  bounded and disclosed — consistent with the cost profile Ask-Agent
  already established per-request, just multiplied by a small, capped
  factor for a Founder-initiated, infrequent action.
