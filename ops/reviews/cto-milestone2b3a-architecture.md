# CTO architecture proposal — Phase 2, Milestone 2B3A

TASK-009. Scope: remove the single-threaded blocking limitation from
`ops/control-center/server.py` safely, with deliberately bounded
concurrent agent invocations, as a foundation for Executive Meetings
(2B3B+) — not Executive Meetings themselves.

## The core problem, precisely

`server.py` (Milestones 2B1/2B2) uses `http.server.HTTPServer` —
strictly sequential, one request at a time. An Ask-Agent call is a real
model invocation (~3–13s observed, capped at 30s) with no lock held
during the subprocess itself, but the *server* still can't start a
second request until the first finishes, by construction. That was an
explicit, disclosed, accepted limitation for 2B2 ("Do not solve
concurrency merely by replacing HTTPServer with ThreadingHTTPServer" is
this milestone's own warning that the fix is not just that swap — it's
everything the single-threaded assumption was quietly relying on
elsewhere in the code).

## What the single-threaded assumption was quietly protecting — found by tracing the code, not assumed

Before proposing the fix, I traced every place `server.py`/`opsdb.py`
implicitly depended on "only one request executes at a time":

1. **`_handle_ask`'s "one open run per agent" guard is a
   SELECT-then-INSERT, not atomic.** Under strict sequential execution
   this was correct by accident — nothing could interleave between the
   `SELECT` and the `INSERT` because nothing else was ever running.
   Under real thread concurrency, two threads asking the *same* agent
   at nearly the same moment could both see "no open run" before either
   has inserted its own row — a classic check-then-act race. **This is
   a real, previously-latent bug this milestone must fix, not a new
   feature.** Verified the fix works: see "Atomicity fix," below.
2. **Connections are already fresh-per-request, never shared across
   requests.** `dbutil.connect()` and `opsdb.connect()` both open a new
   `sqlite3.Connection` on every call, and nothing in this codebase
   caches one at module scope. This turns out to be a *required* safety
   property for multi-threading (a Python `sqlite3.Connection` is not
   safe to use from a thread other than the one that created it, by
   default) — and it was already true, for an unrelated reason
   (Milestone 2B1's "close the connection promptly" discipline).
   Grepped the whole `ops/control-center` tree to confirm no code path
   holds or shares a connection across requests/threads.
3. **No lock is held across the multi-second subprocess call itself.**
   Every `opsdb.py` write (`start_run`, `send_message`, `end_run`) wraps
   its own statement in `with conn:` and returns immediately — the
   *connection* stays open across `invoke_agent()`'s multi-second call
   (so it can write the result afterward), but no open transaction/lock
   is held during that gap. I verified this matters concretely below,
   under "Considered and deferred: WAL mode."

## Proposed architecture

### 1. `http.server.ThreadingHTTPServer`, not `HTTPServer`

One-line swap for the request-dispatch model — but only correct once
paired with the fixes below, which is the actual point of this
milestone. `ThreadingHTTPServer.daemon_threads` defaults to `True` in
the Python version this environment runs (verified directly), so a
lingering in-flight request thread doesn't block process exit on its
own — see "Cancellation," below, for what still needs explicit handling.

GET/read traffic is **not** given any concurrency cap of its own — a
single trusted local Founder cannot realistically generate enough
concurrent read traffic to need one, and SQLite handles concurrent
readers cheaply. Only the expensive, real-cost, real-CPU model
invocations are bounded (next section).

### 2. Bounded concurrent model invocations — a `threading.BoundedSemaphore`, not a queue

`ops/control-center/agent_runtime.py` gains:

```python
MAX_CONCURRENT_INVOCATIONS = 3
_INVOCATION_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_INVOCATIONS)
```

`invoke_agent()` does a **non-blocking** `acquire()` as its first
action, after the allowlist check and before spawning any subprocess.
If the semaphore is already fully held, it returns immediately with a
new `error_kind="capacity_exceeded"` — never queues, never blocks a
request thread waiting for a slot. This is a deliberate choice: a
silent wait queue is exactly the kind of "declare victory by adding a
mechanism, not by reasoning about it" the brief warns against — an
explicit, honest, immediate rejection is simpler and more predictable
than an unbounded (or arbitrarily-bounded) wait. `server.py` handles
`capacity_exceeded` exactly like every other `invoke_agent()` failure
(`agent_runs.status='failed'`, no fabricated response, honest server
log) — no new HTTP-status special case, consistent with the existing
failure-handling philosophy from 2B2.

**Why `MAX_CONCURRENT_INVOCATIONS = 3`:** this milestone's own
acceptance test only requires 2 (Founder asks CTO and Financial at
once); 3 gives headroom to prove the bound is real without being
generous enough to invite real resource/cost exposure on a single local
machine. It anticipates 2B3B's near-term Executive Meeting participant
counts (a handful of agents weighing in) without pre-committing to that
milestone's still-unreviewed design. Not configurable from the browser —
it's a module constant, never derived from any request. Red Team should
confirm this number, or propose a different one with reasoning.

### 3. Atomicity fix: `opsdb.start_ask_agent_run()`

New plain function, same shape as `decide_approval()`/`end_run()`, but
using `BEGIN IMMEDIATE` (not `with conn:`) because the thing being made
atomic is a *check across rows* (does an open run exist at all) plus a
conditional insert — not a conditional update to one already-known row,
which is what the `UPDATE ... WHERE` pattern handles. `BEGIN IMMEDIATE`
acquires SQLite's write lock immediately, before any read, so a second
thread's `BEGIN IMMEDIATE` genuinely blocks (up to the existing 5s busy
timeout) until the first transaction commits — verified empirically
with 5 real concurrent threads each doing a read-sleep-write sequence
inside `BEGIN IMMEDIATE`: zero lost writes, total wall time matched full
serialization, not partial overlap.

```python
def start_ask_agent_run(conn, agent_name, activity_label, activity_like) -> int:
    conn.execute("BEGIN IMMEDIATE")
    try:
        ... SELECT agent id, SELECT existing open run, INSERT if none, COMMIT ...
    except Exception:
        conn.execute("ROLLBACK")  # only if a transaction is still open
        raise
```

Raises `LookupError` (unknown agent) / `ValueError` (already in
progress) — same convention as every other `opsdb.py` write function.
`server.py`'s `_handle_ask` calls this **one** function instead of its
own SELECT-then-`start_run` sequence; the write lock this holds is
released (`COMMIT`/`ROLLBACK`) before `invoke_agent()` is ever called —
never held across the model call, so this fix does not re-serialize
different agents' invocations.

### 4. Cancellation / process cleanup on server shutdown

`ThreadingHTTPServer` exiting `serve_forever()` (Ctrl+C) does not, by
itself, kill any `claude` subprocess a worker thread is still waiting
on — the child process is in its own process group
(`start_new_session=True`, added in 2B2 for the per-request timeout
kill) and would simply be orphaned, left running independently of the
now-exited parent. `agent_runtime.py` gains a small, thread-safe
registry (a `set` of process-group ids, guarded by a `threading.Lock`)
populated when a subprocess starts and cleared when it exits normally;
`server.py`'s shutdown path drains it (`killpg` on anything still
present) before the process exits. This is the smallest mechanism that
actually closes the gap — not a full graceful-shutdown framework, no
new dependency, a few lines against a data structure already implied by
the existing per-invocation `killpg` logic.

### 5. Considered and deferred: SQLite WAL mode

The natural next question for "many concurrent readers, an occasional
writer" is whether to switch `operations.sqlite3` to
`PRAGMA journal_mode=WAL`. Reasoned through explicitly rather than
skipped:

- **What WAL would buy**: readers never block on an in-progress writer
  (and vice versa) — the textbook case WAL exists for.
- **What it costs here specifically**: `operations.sqlite3` is
  committed to git (`DATA_MODEL.md`'s "Known limitation" already
  documents why — no server to host a database on). WAL mode leaves
  `-wal`/`-shm` sidecar files that must be checkpointed
  (`PRAGMA wal_checkpoint(TRUNCATE)`) before the main file is a complete,
  standalone snapshot fit to commit — a real, ongoing discipline burden
  every future commit of the DB file would need to remember, and a real
  way to (accidentally) commit an inconsistent-looking file if
  forgotten.
- **Whether it's actually needed for this milestone's goal**: traced
  above (§3) — no `opsdb.py` write holds a lock across the multi-second
  subprocess call; every write is a single brief statement, individually
  committed. The actual reader-blocked-by-writer window in the current
  design is milliseconds (one `INSERT`/`UPDATE`), not seconds. The
  stated goal — "another Control Center page remains responsive during
  an Ask-Agent call" — is achieved by `ThreadingHTTPServer` +
  connection-per-request + brief-transaction discipline alone, not by
  WAL.

**Recommendation: do not adopt WAL mode this milestone.** It's real
complexity (an ongoing git-commit discipline, not just a one-time
config flip) for a problem this design doesn't actually have, given how
the codebase already writes. Revisit only if QA's real concurrent-load
testing (§ Required Gates) finds actual contention (busy-timeout
retries or failures) in practice — that would be evidence, not
speculation, for taking on the cost. Red Team should scrutinize this
reasoning specifically, since it's the one place this proposal is
choosing *not* to add a mechanism the brief explicitly asked to have
evaluated.

### 6. Everything else stays exactly as it was

Founder session-token authorization (`server.py`'s existing
`SESSION_TOKEN`, `secrets.compare_digest`), `ASK_AGENT_ALLOWLIST`,
zero-tool/zero-MCP invocation flags, `--max-budget-usd`, the
response-size cap, `opsdb.py` as the sole writer, one Agent Runtime
boundary, `agent_runs`/`messages` as the sole conversation/execution
store, deterministic status derivation — none of this changes. This
milestone is additive (a real bug fix + a real bound + real cleanup),
not a redesign.

## Files touched

- `ops/control-center/server.py` — `ThreadingHTTPServer`; `_handle_ask`
  calls `opsdb.start_ask_agent_run()` instead of its own SELECT+insert;
  shutdown path drains the subprocess registry.
- `ops/control-center/agent_runtime.py` — `MAX_CONCURRENT_INVOCATIONS`,
  the bounding semaphore, `capacity_exceeded` error kind, the
  process-group registry + drain function.
- `ops/db/opsdb.py` — new `start_ask_agent_run()` plain function
  (no CLI wrapper needed — this is Ask-Agent-specific, unlike
  `start_run`/`end_run`/`send_message`, which are general-purpose).
- `ops/SECURITY.md` / module docstrings — document the concurrency
  model and its bound, same disclosure discipline as every prior
  milestone.

## Open questions for Red Team

1. Is `MAX_CONCURRENT_INVOCATIONS = 3` the right number, or does Red
   Team want it lower (tighter resource/cost bound) or higher
   (more 2B3B headroom)?
2. Is the WAL-mode deferral (§5) sound, or does Red Team want it
   adopted now regardless, given the milestone explicitly asks for
   "database locking/busy behavior" to be evaluated?
3. Is `BEGIN IMMEDIATE` + a dedicated `start_ask_agent_run()` the right
   fix for the check-then-act race, or is there a simpler mechanism
   (e.g. a `UNIQUE` partial index) Red Team would prefer?
4. Is the process-group-registry approach to shutdown cleanup
   proportionate, or does Red Team consider it unnecessary complexity
   for a local dev tool (i.e., accept orphaned processes as a disclosed
   limitation instead)?
5. Any concern with capacity-exceeded failures still creating (and
   immediately failing) an `agent_runs` row, rather than rejecting
   before any row is created?
