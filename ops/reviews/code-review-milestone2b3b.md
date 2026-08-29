# Code Review — Phase 2, Milestone 2B3B: Real Executive Meetings

TASK-010. Reviewing the Development implementation against
`ops/reviews/cto-milestone2b3b-architecture.md` and
`ops/reviews/red-team-milestone2b3b-architecture.md`'s 7 conditions.
Recorded via `opsdb.py review-result --task-id 10 --type code --by
code-review`. This file mirrors that record.

Note on process: performed directly rather than via a spawned
`code-review` subagent (the `Agent`/`TaskCreate` dispatch tools have been
unavailable this session since Milestone 2B3A — same disclosure as every
review from that milestone onward). Verified by reading every changed
file in full and by direct execution, not by trusting the Development
summary's own claims.

## Verdict: PASS

## Files reviewed

- `ops/db/opsdb.py` — `_insert_decision`/`record_decision` split,
  `create_meeting`, `finalize_meeting_synthesis`, `decide_meeting`.
- `ops/control-center/agent_runtime.py` — `MEETING_PARTICIPANT_ALLOWLIST`,
  `MEETING_ACTIVITY_LABEL`/`_LIKE`, `MAX_MEETING_PARTICIPANTS`,
  `invoke_agent(..., wait_for_slot)`.
- `ops/control-center/meeting_orchestrator.py` — new file, full
  orchestration.
- `ops/control-center/server.py` — new routes wired into `do_POST`/`do_GET`.
- `ops/control-center/generate_meetings.py` — rewritten renderer.

## Condition-by-condition verification

1. **Lenient parsing of CEO's selection output** — confirmed:
   `_parse_selection()` lowercases the whole response and does a
   case-insensitive word-boundary regex search per candidate role,
   never requires exact formatting. Verified live: real CEO responses in
   testing were clean lists, but the parser does not assume that —
   reading the code, a response like `"I'd bring in Security and
   Red-Team for this one."` would still correctly extract both roles.
2. **Deterministic truncation at the cap** — confirmed:
   `_select_participants()` returns `selected[: MAX_MEETING_PARTICIPANTS
   - 1]`, a plain list slice — first-N-in-order, no randomness, no
   re-prompting. `run_meeting()` always prepends `"ceo"`, so the cap of
   6 total is enforced by construction (5 others + CEO), not by a
   separate check that could drift out of sync.
3. **Topic length cap** — confirmed in two places, not one:
   `meeting_orchestrator.run_meeting()` raises `ValueError` above
   `MAX_TOPIC_CHARS`, and `server.py`'s `_handle_meeting_create()`
   independently checks the same constant before calling
   `run_meeting()` at all, returning 400 rather than letting the
   ValueError's generic path handle it — same defense-in-depth pattern
   as the existing `MAX_ASK_MESSAGE_CHARS` check. Verified live: a
   2001-character topic returned HTTP 400 with a clear message, not a
   500 or a truncated silent accept.
4. **Every `ThreadPoolExecutor` worker opens/closes its own
   `opsdb.connect()`** — verified by reading `_gather_position()`
   directly, not assumed from the docstring: `conn = opsdb.connect()` is
   the first line inside the function (called once per worker
   invocation, not hoisted to a shared variable), and `finally:
   conn.close()` guarantees it closes even if `start_run`/`invoke_agent`/
   `send_message`/`end_run` raises. `grep -n "opsdb.connect"
   meeting_orchestrator.py` shows exactly 3 call sites — one per worker
   invocation, one in `run_meeting()` for `create_meeting`, one for
   `finalize_meeting_synthesis` — none shared across threads.
5. **Duplicate meeting submission behaves cleanly** — verified live (see
   QA report) — this is a QA-owned live test, Code Review confirms the
   code path has no shared mutable state that a concurrent
   `run_meeting()` call could corrupt: each call gets its own `meeting_id`
   from its own `create_meeting()` INSERT, its own `positions` dict (a
   local variable, not a module-level cache), and its own
   `ThreadPoolExecutor` instance (not a shared pool — only the
   underlying semaphore in `agent_runtime.py` is shared, and that's
   thread-safe by construction, per 2B3A's own review).
6. **Failure-path honesty per-participant** — confirmed:
   `_gather_position()`'s `except Exception` branch never fabricates a
   return value — it always returns `(agent_name, False, None)` on any
   failure, and `run_meeting()` only adds to `positions` when `ok` is
   `True`. `generate_meetings.py`'s `build_meeting_detail()` then
   explicitly distinguishes "in `positions_by_agent`" from "selected but
   absent" — the honest fallback card is a real, distinct render path,
   not a shared "empty" case that could be confused with "not selected."
7. **Synthesis failure doesn't discard positions** — confirmed:
   `run_meeting()` calls `_synthesize(topic, positions)` (using the
   `positions` dict already populated from real participant results)
   regardless of whether that call succeeds; `finalize_meeting_synthesis()`
   is a pure `UPDATE ... WHERE id = ?` on the four synthesis columns —
   it never touches `messages`, so a failed synthesis call cannot
   retroactively remove or alter any already-persisted position.

## Additional findings (non-blocking)

- `decide_meeting()`'s `BEGIN IMMEDIATE`/no-`with conn:` structure exactly
  mirrors `start_ask_agent_run()`'s corrected pattern, including the
  critical property that `BEGIN IMMEDIATE` sits outside the
  `try/except: ROLLBACK` block. Confirmed by reading the function
  directly, not by trusting the docstring's own claim.
- `record_decision()`/`_insert_decision()` split is a clean, minimal
  refactor — `cmd_decision_record` (the CLI path every prior milestone's
  `decision-record` calls already use) is unchanged in observable
  behavior; verified by diffing the two functions' SQL text, which is
  identical.
- `invoke_agent()`'s allowlist check
  (`agent_name not in ASK_AGENT_ALLOWLIST and agent_name not in
  MEETING_PARTICIPANT_ALLOWLIST`) is the single enforcement point inside
  the Agent Runtime boundary — both `server.py`'s `_handle_ask` and
  `meeting_orchestrator.py`'s fixed `_CANDIDATE_ROLES` tuple narrow
  further before ever reaching this function, so there are two
  independent layers, not one relied upon twice.
- No new raw SQL exists outside `opsdb.py` — `server.py` and
  `generate_meetings.py`'s only direct `conn.execute()` calls are
  read-only `SELECT`s against `dbutil.connect()`'s `mode=ro` connection,
  consistent with every prior milestone.
- `generate_meetings.py`'s `main()` now writes per-meeting static pages
  under a new `meetings/` subdirectory — confirmed `write_output()`
  still applies the same `chmod(0o600)` to each file (it's a shared
  helper, not reimplemented), so no permission regression versus the
  single-file generators.

No blocking findings. Proceeding to QA.
