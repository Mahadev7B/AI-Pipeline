# Red Team review — Phase 2, Milestone 2B1 architecture

TASK-006. Reviewing `ops/reviews/cto-milestone2b1-architecture.md` before
any code is written. Full findings recorded via `opsdb.py review-result
--task-id 6 --type code --by red-team` (id=11). This file mirrors that
record for the human-readable audit trail, per the pattern used in 2A.

## Verdict: PASS with conditions

Core design — loopback-only `HTTPServer`, a single POST boundary at
`/api/approvals/<id>/decide`, an atomic `UPDATE ... WHERE` for every state
transition, `decide_approval()` as the one write path shared by CLI and
server, and an honest (not overclaimed) writeup of what the token proves
— correctly satisfies every hard requirement in the Founder's brief and
is not overengineered. No simpler design was found that still satisfies
"one controlled boundary, no arbitrary SQL/shell, no blindly-trusted
client flag."

## Conditions Development/QA must close

1. **Real cross-process race, not just concurrent-HTTP.** The proposal
   only reasoned about concurrent requests to the server, which is moot
   since `HTTPServer` is single-threaded. The actual race is `server.py`'s
   long-lived writable connection vs. a concurrently-run `opsdb.py` CLI
   write hitting the same file, with no `timeout=` set anywhere in
   `connect()`. **Development must set an explicit SQLite busy timeout.
   QA must test true cross-process concurrent writes** (CLI process +
   running server at the same time), not just concurrent requests to the
   server alone.
2. **`decide_approval()` must commit explicitly**, not rely on a
   short-lived-connection assumption — `server.py` holds one long-lived
   connection across many requests. QA must verify durability by reading
   the row from a second, independent connection immediately after the
   POST returns.
3. **Token-injection mechanism must be pinned down before implementation**,
   not improvised mid-build: `build_inbox_html()` takes an optional
   `token` parameter (server passes the real one; static generation
   passes none, so the static snapshot's forms always fail closed).
4. **Server-side input validation.** The POST handler must independently
   validate the `decision` field against the exact 3-value allowlist and
   the `approval_id` path segment as an integer, before calling
   `decide_approval()`, so a malformed request gets a clean 400 — never a
   traceback/500. QA must test malformed POSTs.
5. **New dynamic-query attack surface.** GET routes like
   `/agents/<name>.html` now run a live parameterized query per request
   against URL-derived input, rather than only ever serving pre-generated
   files as in 2A. QA must confirm every URL-derived lookup key still
   goes through parameterized queries — no string-built SQL.
6. **Citation correction.** The architecture doc's claim that not writing
   Founder actions into `agent_activity` is "the exact kind of thing this
   project's Red Team has rejected before" is not substantiated by any
   prior review file — the underlying reasoning (`agent_activity.agent_id`
   is `NOT NULL REFERENCES agents(id)`, structurally incompatible without
   a schema change) stands on its own; the false precedent citation
   should be removed.

## Non-blocking notes

- The state machine (`pending → {approve,reject,discuss}`,
  `discuss → {approve,reject}`, `discuss → discuss` rejected,
  `approve`/`reject` terminal) is correct and matches the brief;
  enforcement is properly server-side regardless of UI state.
- No orphan/FK risk — `approvals.task_id` FK is enforced and task purge
  already blocks on any approvals row. Worth a one-line note in
  `DATA_MODEL.md` that nothing currently ties a pending approval to its
  parent task's status changing underneath it — not a blocker.
- Loopback bind + per-run in-memory token is the right call for 2B1 as
  documented. A cookie/startup-code login upgrade is explicitly **not**
  required now — it would itself be a session/login mechanism the
  Founder ruled out of this milestone's scope. Flag as a candidate for
  whichever milestone actually tackles Founder authentication.
- `decide_approval()` as the sole writer, shared by CLI and server, is
  the correct way to honor "opsdb.py is the only writer" — not a second
  writer. No mechanical enforcement stops a future direct `UPDATE`
  elsewhere, consistent with how this codebase already documents (not
  lints) analogous rules.
