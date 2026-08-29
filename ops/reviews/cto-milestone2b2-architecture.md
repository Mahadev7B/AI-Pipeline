# CTO architecture proposal — Phase 2, Milestone 2B2

TASK-007. Scope: prove one complete vertical slice — Founder asks a real
question of a real configured agent, through the existing controlled
write boundary, and gets a real answer, fully persisted. Read
`ops/reviews/design-conformance-milestone2b2.md` first; this proposal
answers the two questions it routed here.

## The core problem

`ops/control-center/server.py` (Milestone 2B1) can turn a browser click
into exactly one kind of database write: an approval decision. This
milestone needs a second kind — a real model invocation — without
opening a second, competing write path, without letting the browser
choose tools/permissions/model, and without inventing a UI-only status
that isn't backed by persisted execution state.

## Runtime research (done before writing this, not assumed)

I tested the actual `claude` CLI available in this environment before
proposing to depend on it — the flags below are verified, not read from
`--help` and taken on faith:

- `claude --agent <name> --tools "" -p "<question>" --output-format json
  --no-session-persistence` runs a real, one-shot, non-interactive
  invocation of the actual `.claude/agents/<name>.md` persona (verified:
  asking the `cto` agent "what is your role" returned the real CTO
  role description, not a generic answer) and returns structured JSON
  (`result`, `is_error`, `total_cost_usd`, `duration_ms`, `modelUsage`
  with the real model(s) used, `permission_denials`).
- `--tools ""` genuinely disables all tool use — verified adversarially:
  asked the `cto` agent to run `ls -la` and read a file; it attempted a
  `Grep` call, which was denied and reported in `permission_denials`,
  and the final response was an honest text explanation that it lacked
  tool access. No shell command ran, no file was read outside the
  sandboxed attempt-and-deny. This is the real enforcement Security must
  re-verify independently, not something this proposal is asking to be
  trusted on faith.
- An unregistered `--agent` name fails immediately, before any session
  starts, with a clean non-zero exit and a listed-agents error message —
  a second, CLI-native check on top of our own allowlist (defense in
  depth, not a substitute for it — the app-level allowlist below is
  still the authoritative gate, since we control what names we ever pass
  in the first place).
- `--no-session-persistence` prevents the CLI from writing its own
  session transcript to disk — important, since `messages`/`agent_runs`
  must be the *only* conversation store (see "Persistence" below); we
  don't want a second, shadow transcript sitting in `~/.claude` that
  nobody queries but that technically also remembers what was said.
- No `--permission-mode` flag is needed: with zero tools granted, there
  is nothing to prompt for, so nothing ever blocks waiting on a human —
  confirmed empirically (clean exit, no hang, across every test run).
- Cost per call in testing: ~$0.005–0.013, ~3 seconds. Passing
  `--max-budget-usd` as a hard per-call ceiling costs nothing and bounds
  worst-case spend from a single request.

## Proposed architecture

### 1. One Agent Runtime boundary: `ops/control-center/agent_runtime.py`

A new, small, dependency-free module. Application-facing interface:

```python
@dataclass
class RuntimeResult:
    ok: bool
    response_text: str | None = None
    model_used: str | None = None      # the real model the runtime reports back, never guessed
    cost_usd: float | None = None
    duration_ms: int | None = None
    error: str | None = None
    error_kind: str | None = None      # invalid_agent | runtime_unavailable | timeout | runtime_error

def invoke_agent(agent_name: str, transcript: str, timeout_s: float = 90.0) -> RuntimeResult: ...
```

This module knows nothing about SQLite, HTTP, or the browser. It takes a
registered agent identity and a plain-text conversation transcript, and
returns a result. `server.py` is the only caller; it owns turning that
result into persisted rows. This split is what keeps the interface
provider/model-neutral in practice, not just in name: a future adapter
(a different CLI, a hosted API, a different vendor) only has to
implement `invoke_agent()` with the same signature — nothing in
`server.py`, `generate_agents.py`, or the schema would need to change.

The one implementation today shells out to the `claude` CLI via
`subprocess.run([...], shell=False, timeout=timeout_s, ...)` — argv list,
never a shell string, so there is no shell-injection surface regardless
of what the Founder's message contains (a message containing `; rm -rf /`
or backticks is just inert text inside one argv element; it is never
interpreted by a shell). Failure modes map to `error_kind`:
`FileNotFoundError` (the `claude` binary itself isn't on PATH) →
`runtime_unavailable`; `subprocess.TimeoutExpired` → `timeout`;
non-zero exit or unparseable stdout → `runtime_error`; agent name not in
`ASK_AGENT_ALLOWLIST` → `invalid_agent` (checked here, before any
subprocess is even started — belt-and-suspenders with the CLI's own
`--agent` validation).

### 2. The allowlist — enforced once, in the trusted module, never client-supplied

```python
ASK_AGENT_ALLOWLIST = ("cto", "qa", "ceo", "financial", "project-manager")
```

Exactly the Founder's brief's conservative starting roster. The browser
sends an agent *name* (e.g. from the URL path `/agents/cto.html`'s own
"Ask Agent" form); `server.py` checks it against this tuple before doing
anything else — an unlisted name (including a real agent like
`developer` that simply isn't enabled yet, or a nonexistent one) is
rejected the same way, a clean 404/403, never a partial success. Tools,
system prompt, and model selection are never client-supplied — the
browser only ever sends an agent name and a message; `--agent`,
`--tools ""`, and the absence of `--model` (letting the CLI's own
default/auto-mode choose, then reporting back whatever it actually used)
are all hardcoded in `agent_runtime.py`, not derived from anything in
the request.

**Why zero tools, not read-only tools, for v1:** the brief allows
"read-oriented agents" but is explicit that even read-oriented agents'
write capability needs explicit CTO/Red Team/Security sign-off before
exposure through conversational chat. I'm reading that the same caution
extends to *any* tool access in an unsupervised loop — the difference
between this and my spawning a review subagent earlier in this project
is supervision: when I spawn `cto` as a subagent, a human (channel: me,
ultimately the Founder) is watching the tool calls in real time and can
interrupt. An HTTP-triggered subprocess has no such supervision. Zero
tools means the vertical slice is still completely real (a live model
call, the agent's real persona, a real response) without opening any
file-access or execution surface at all. Read-only tool access
(Read/Grep/Glob) for these same agents is a reasonable 2B3+ ask once
Security has had a chance to evaluate it specifically — not assumed here.

### 3. Schema: one narrow, necessary addition — `agent_runs.status` gains `'failed'`

Checked both tables the brief points at before touching anything:

- **`messages.scope`** already has an `'agent'` value whose CHECK
  constraint (`task_id IS NULL AND project_id IS NULL AND meeting_id IS
  NULL`) and `DATA_MODEL.md`'s own description ("a general question to
  an agent, not tied to a specific piece of work") are *exactly* the
  brief's "company/general" scope — just an existing, different word for
  the same concept. `messages` has zero rows today, so a rename to
  `'company'` (matching `agent_runs.scope_type`'s existing vocabulary)
  would cost nothing data-wise — but "costs nothing" is not the same as
  "necessary." Functionally, `'agent'` already works. I'm not proposing
  the rename: `DATA_MODEL.md`'s Rules already say not to casually mutate
  Phase 1 schema, and a purely cosmetic cross-table naming mismatch
  (worth noting, not worth a migration) doesn't clear that bar on its
  own. Red Team should weigh in if it disagrees.
- **`agent_runs.status`** genuinely cannot represent what the brief
  requires. Today: `CHECK (status IN ('active','waiting','blocked',
  'ended'))` — `'ended'` means only "this run is over," with no way to
  persist *how* it ended. The brief's lifecycle
  (`queued → running → completed` or `queued → running → failed`) needs
  a real, queryable distinction between a successful and a failed
  invocation — "must produce a clear failed agent_run," "status remains
  deterministic from persisted execution state." There is no column to
  encode this today. This is the one case the brief's own instruction
  applies to: **STOP casual Development, treat as a schema change,
  route through Red Team.**

  Proposed migration (small, additive, zero data at risk —
  `agent_runs` currently has 13 rows, none of which need to change):
  widen the CHECK constraint to `status IN ('active','waiting','blocked',
  'ended','failed')`. `'failed'` is terminal exactly like `'ended'`
  (`ended_at` gets set either way) — it only differs in *outcome*, which
  is exactly what the brief's two-branch lifecycle needs. SQLite can't
  `ALTER` a CHECK constraint directly, so this requires the
  rebuild-and-copy technique (`CREATE TABLE agent_runs_new (...)`, copy,
  drop, rename) — the same category of operation as any SQLite schema
  change, executed once, disclosed, with a before/after row-count check.
  Existing rows are unaffected (`'ended'` stays `'ended'`; nothing is
  reinterpreted).

  On "queued": this system's write boundary (`server.py`) is a
  single-threaded `HTTPServer` handling one request at a time — there is
  no request queue with observable wait time in this design. I'm folding
  "queued" and "running" into a single `'active'` transition (the run
  row is created, with `ended_at IS NULL`, the instant the request is
  accepted and validated, before the subprocess call starts) rather than
  inventing a `'queued'` status that would never actually be observed as
  distinct from `'active'` in this synchronous architecture. Flagging
  this simplification for Red Team explicitly rather than deciding it
  silently — if a future milestone makes this asynchronous (a real job
  queue, background workers), `'queued'` becomes meaningful and can be
  added then, the same additive way `'failed'` is being added now.

- `opsdb.py`'s `cmd_run_end` currently hardcodes `status = 'ended'`.
  Gains an optional `--status {ended,failed}` (default `ended`) rather
  than a new near-duplicate command — one function, two outcomes, same
  as `decide_approval()`'s pattern in Milestone 2B1.
- New `opsdb.py` command: `message-send` — `messages` has a schema but
  no writer anywhere in `opsdb.py` today (a real, pre-existing gap, not
  introduced by this milestone). Mirrors the existing scope-consistency
  pattern already used by `risk-add`/`agent_runs`: `--scope
  {task,project,agent,meeting}` plus the matching required/forbidden
  `--task-id`/`--project-id`/`--meeting-id`, `--thread-id`,
  `--from-agent`, `--to-agent`, `--body`. `server.py` calls this the
  same way it already calls `opsdb.decide_approval()` — through
  `opsdb.py`, never a raw `INSERT`.

### 4. The write route: `POST /api/agents/<name>/ask`

Second POST route on the existing server, second and last write path
this milestone adds — no new server process, no new port, no new auth
mechanism. Reuses the exact session-token gate from Milestone 2B1
(`secrets.compare_digest` against the same per-process `SESSION_TOKEN`) —
one boundary, one token, two write routes now instead of one. Sequence,
entirely inside `server.py`, mirroring `decide_approval()`'s
validate-before-write discipline:

1. Validate token (403 if wrong/missing — identical to the approvals
   route).
2. Validate `agent_name` against `ASK_AGENT_ALLOWLIST` (404 if not
   enabled/unknown — never a 500, never a partial attempt).
3. Validate the message body is non-empty and under a size cap (8KB —
   generous for a real question, small enough to reject anything that
   looks like an attempt to overflow the runtime call).
4. Check for an already-open run for this agent
   (`agent_runs` with `ended_at IS NULL`) — if one exists, reject with a
   clean 409 ("a request to this agent is already in progress") rather
   than allowing two overlapping invocations to interleave. This is this
   route's equivalent of `decide_approval()`'s atomic re-decision guard —
   a double-click while the first request is still running gets a clean,
   honest rejection instead of a second concurrent subprocess.
5. Only once all four checks pass: create the `agent_runs` row
   (`scope_type='company'`, `status='active'`) via `opsdb.py run-start`,
   then persist the Founder's message via `opsdb.py message-send`
   (`from_agent='founder'`, `to_agent=<agent_name>`).
6. Build the transcript (existing thread history + the new message, as
   plain text — see "Persistence" below) and call
   `agent_runtime.invoke_agent()`.
7. On success: persist the agent's response as a second `message-send`
   row (`from_agent=<agent_name>`, `to_agent='founder'`), then
   `opsdb.py run-end --status ended`.
8. On failure (any `error_kind`): `opsdb.py run-end --status failed` —
   **no response message is ever inserted on failure.** The failed run
   itself, visible on the conversation thread, is the honest record;
   nothing pretends the agent answered when it didn't.
9. Redirect 303 back to `/agents/<name>.html`, which re-renders the full
   thread (and the run's terminal status) from persisted state — the
   same POST/redirect/GET pattern Milestone 2B1 already established, no
   new refresh mechanism.

### 5. Persistence — one thread per agent, `messages`/`agent_runs` as the only store

`thread_id = f"agent-{agent_name}-company"` — deterministic, so asking
an agent a second time always continues the same thread rather than
starting a new one, and a browser refresh or full server restart shows
the identical history because it's read fresh from SQLite on every
request, not cached anywhere in the server process. Founder vs. agent
messages are distinguished **structurally** by `from_agent`/`to_agent`
(`'founder'` is a plain string value, not a row in `agents` — no agent
is named `founder`, confirmed against the live table — so there's no
collision risk), never inferred from message text or formatting.

The transcript handed to `invoke_agent()` is built fresh from the
`messages` table on every turn (prior turns formatted as plain
`"Founder: ..."` / `"<agent>: ..."` lines, then the new message) — the
CLI's own `--no-session-persistence` flag means it never remembers
anything between calls on its own, by design, so `messages` is
mechanically the only place conversation state can live. This is a
disclosed scaling simplification: a very long conversation means a
larger transcript on every turn (more input tokens, more cost) — fine
for this milestone's "prove the slice" scope, worth revisiting if
conversations get long in practice.

### 6. Status display — real, not decorative

Agent Detail's existing "Current status" (already wired to `agent_runs`
in Milestone 2A) is untouched. The new Ask-Agent section adds its own
status line sourced from the *same* mechanism: the open run (if any) for
this agent shows the conversation as in-progress; the most recent
`agent_runs` row's `status` (`ended` vs `failed`) is what the UI reads
to badge each turn — never a word the model happened to generate. This
directly closes design-conformance finding 5.

## Files touched

- `ops/control-center/agent_runtime.py` — new.
- `ops/control-center/server.py` — new POST route, imports
  `agent_runtime`.
- `ops/control-center/generate_agents.py` — `build_agent_detail()`
  gains a new "Ask Agent" section (conversation thread + form, gated on
  `ASK_AGENT_ALLOWLIST`; an honest "not enabled for conversation in this
  milestone" note for every other agent — never a dead-looking button).
- `ops/db/schema.sql` — widen `agent_runs.status` CHECK to add
  `'failed'`.
- `ops/db/opsdb.py` — `cmd_run_end` gains `--status {ended,failed}`; new
  `message-send` command.
- `ops/DATA_MODEL.md` — document the `agent_runs.status` addition and
  the `messages.scope='agent'` == company/general clarification (no
  rename, just make the equivalence explicit since this proposal
  surfaced the naming mismatch).

## Open questions for Red Team

1. Is folding `queued` into `active` (synchronous, single-threaded
   server, no real queue) an acceptable simplification for 2B2, or
   should a `queued` status exist even though nothing would currently
   observe it as distinct from `active`?
2. Is zero tool access (`--tools ""`) the right call for every
   allowlisted agent in this milestone, or should any of CTO/QA/CEO/
   Financial/Project-Manager get read-only tools now rather than in a
   later, explicitly-reviewed milestone?
3. Does not renaming `messages.scope`'s `'agent'` value hold up, or does
   Red Team want the cosmetic rename anyway for cross-table consistency
   with `agent_runs.scope_type`?
4. Any objection to the "one open run per agent → 409" duplicate-submit
   guard, or is there a better way to handle a double-click that doesn't
   risk falsely blocking two genuinely separate, fast Founder questions?
