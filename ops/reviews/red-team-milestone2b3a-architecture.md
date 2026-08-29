# Red Team review — Phase 2, Milestone 2B3A architecture

TASK-009. Reviewing `ops/reviews/cto-milestone2b3a-architecture.md`
before any code is written. Recorded via `opsdb.py review-result
--task-id 9 --type code --by red-team`. This file mirrors that record.

Note on process: the `Agent` subagent-dispatch tool became unavailable
partway through this milestone (session-level change, not a project
decision). This review was performed directly rather than via a spawned
`red-team` subagent — same adversarial standard, same empirical testing
discipline the project has used throughout, just executed by the CTO/
orchestrator role directly. Disclosed here rather than silently changing
how review gates are staffed without saying so.

## Verdict: PASS with conditions

Core design is sound: the diagnosis (a real, previously-latent
check-then-act race in the "one open run per agent" guard, invisible
only because nothing could race under strict single-threading) is
correct and independently re-verified — not just trusted. The choice of
`ThreadingHTTPServer` + a bounded semaphore for the *expensive* resource
(model subprocesses, not HTTP threads) is the right shape. One real bug
found in the proposed atomicity fix's exception handling (below) — must
be fixed before this ships, not after. One proposed mechanism (the
process-group shutdown registry) is unnecessary complexity for what it
actually buys — recommend dropping it in favor of the already-existing
reconciliation path.

## Blocking finding — fix before Development proceeds

**`start_ask_agent_run()`'s proposed exception handling breaks if
`BEGIN IMMEDIATE` itself fails.** Verified empirically: if `BEGIN
IMMEDIATE` can't acquire the write lock within the busy timeout, it
raises `sqlite3.OperationalError: database is locked` — and at that
point **no transaction is open**. The proposal's sketch wraps `BEGIN
IMMEDIATE` inside the same `try/except Exception: conn.execute
("ROLLBACK"); raise` block that guards the SELECT/INSERT — so a `BEGIN
IMMEDIATE` failure would be caught, `ROLLBACK` would then ALSO raise
(`OperationalError: cannot rollback - no transaction is active`,
reproduced directly), and the *second* exception is what a caller would
actually see — a confusing "cannot rollback" error masking the real
"database is locked" one, instead of a clean, honest capacity/busy
signal.

**Fix**: `BEGIN IMMEDIATE` must execute *outside* the try/except that
performs `ROLLBACK` — if it raises, there's nothing to roll back and the
original `OperationalError` should propagate as-is. Only the block
*after* a successful `BEGIN IMMEDIATE` needs the rollback-on-exception
guard. `server.py`'s `_handle_ask` must catch `sqlite3.OperationalError`
from this call specifically and map it to the same honest "busy, try
again" handling as `capacity_exceeded` — this is a second, real way a
Founder request can hit contention besides the semaphore, and it needs
the same non-crashing treatment.

## Answers to the proposal's 5 open questions

1. **`MAX_CONCURRENT_INVOCATIONS = 3`**: Accepted as-is. Considered
   whether running on the same machine as the orchestrating Claude Code
   session itself changes this — it doesn't materially: each `--tools
   ""` invocation is a lightweight, mostly network-bound API call (no
   local tool execution), not a heavy local-compute process. 3 remains
   a reasonable, conservative bound with real headroom for the stated
   2-agent acceptance test.
2. **WAL-mode deferral**: Sound, affirmed. The reasoning (no lock held
   across the subprocess call; every write is a brief, individually
   committed statement; the git-committed-file discipline cost is real
   and ongoing, not one-time) holds up against the actual code, verified
   by grep, not just read. **What would reopen this**: QA should watch
   for any `sqlite3.OperationalError: database is locked` under real
   concurrent load (not simulated), or GET-request latency measurably
   degraded while an Ask-Agent call is in flight — either is evidence
   this deferral needs revisiting, not before then.
3. **`BEGIN IMMEDIATE` + dedicated function vs. a `UNIQUE` partial
   index**: The dedicated-function approach is correct; a partial
   unique index keyed on a `LIKE`-pattern condition is exactly the kind
   of fragile, version-sensitive SQLite feature use this project has
   otherwise avoided (see the `messages.scope` naming discussion in
   2B2's architecture review — prefer simple, explicit code over clever
   schema tricks). No change requested here, beyond the exception-
   handling fix above.
4. **Non-blocking semaphore acquire vs. a bounded wait queue**:
   Non-blocking, immediate rejection affirmed as the right call —
   predictable, no new timeout-within-a-timeout complexity, consistent
   with "explicit and honest" over "silently queued." **Condition**:
   the semaphore's `acquire()`/`release()` must wrap the *entire*
   subprocess lifecycle in `try/finally` — acquired immediately after
   the allowlist check, released on every exit path (success, timeout,
   `runtime_unavailable`, `runtime_error`, JSON-parse failure, and the
   new `OperationalError` case above). Code Review must verify this
   explicitly, not assume it.
5. **Process-group shutdown registry — REJECT as proposed, recommend a
   simpler alternative.** This is real, unnecessary complexity for what
   it buys. Startup reconciliation (`reconcile_orphaned_runs`, already
   shipped in 2B2) already correctly marks any leftover open Ask-Agent
   run `'failed'` on the next server start — the *database* consequence
   of a Ctrl+C mid-invocation is already handled honestly. The only gap
   is the orphaned OS process itself briefly continuing — but it's
   already bounded (the existing per-call timeout and `--max-budget-usd`
   cap still apply to it) and will exit on its own. Building a
   thread-safe registry plus a drain-on-shutdown path adds real state
   and real failure modes (what if the drain itself hangs? what if
   `killpg` races with the process's own natural exit?) to close a gap
   that's small, bounded, and self-resolving on a single local trusted
   machine. **Recommendation**: drop the registry; document "Ctrl+C
   during an active Ask-Agent call may leave that one subprocess running
   briefly until it completes on its own (bounded by the existing
   timeout/budget caps); the resulting `agent_runs` row reconciles to
   `'failed'` on next server start" as an accepted, disclosed
   limitation instead — this is the "prefer standard-library/minimal-
   dependency solutions if sufficient" instruction applied literally:
   the simplest sufficient answer here is *no new mechanism*.

## Additional scrutiny — no other findings

- **No new browser-facing surface from `ThreadingHTTPServer`** —
  confirmed by reading `server.py`'s route table: threading changes only
  *how* existing routes are dispatched, adds no route, no new way for
  the browser to reach a subprocess/SQLite/tool/model/config directly.
- **"Connections are fresh-per-request" — verified by grep, not taken
  on faith**: no module-level `sqlite3.connect(...)` call anywhere in
  `ops/control-center/*.py` or the relevant `opsdb.py` functions; every
  connection is opened inside a function body and closed before it
  returns (or at request end).
- **No other module-level mutable state without a lock** — grepped for
  list/dict/set literals at module scope in `server.py` and
  `agent_runtime.py`; the only module-level state is `SESSION_TOKEN`
  (an immutable string, set once at import time — safe to read from any
  thread without a lock) and the new semaphore itself (already
  thread-safe by construction, that's what `threading.BoundedSemaphore`
  is for).
- **SQLite isolation gap between COMMIT and a concurrent SELECT** —
  considered and ruled out: SQLite is not a distributed system: once a
  writer commits, any subsequent read (a new statement/transaction) sees
  the committed data immediately, no eventual-consistency window exists
  to race against.

## Summary of conditions Development must close

1. Fix `start_ask_agent_run()`'s exception handling so `BEGIN IMMEDIATE`
   failing doesn't trigger a masking `ROLLBACK` error (see Blocking
   finding).
2. `server.py` must catch `sqlite3.OperationalError` from
   `start_ask_agent_run()` and handle it as a clean busy/retry signal,
   same treatment as `capacity_exceeded`.
3. Verify (Code Review must check explicitly) the semaphore
   acquire/release wraps every exit path of `invoke_agent()`.
4. Drop the process-group shutdown registry; document the accepted
   Ctrl+C limitation instead (see item 5 above).
5. QA must watch for real lock-contention evidence (per item 2 of the
   5 answered questions) as part of concurrent-load testing, to confirm
   the WAL-mode deferral was the right call in practice, not just in
   theory.
