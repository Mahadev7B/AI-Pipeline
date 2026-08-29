# CTO architecture proposal — Phase 2, Milestone 2B3B

TASK-010. Scope: real Executive Meetings — a Founder-raised question
genuinely gathers real, concurrent positions from real configured
agents, gets a real CEO-synthesized recommendation, and the Founder
records a real decision against it. This is the first *multi-agent*
real invocation in the system, built directly on 2B3A's bounded
concurrent Agent Runtime foundation — that milestone existed specifically
to make this one possible without re-litigating concurrency safety.

Read first: `ops/EXECUTIVE_MEETINGS.md` (functional spec),
`ops/reviews/design-conformance-milestone2b3b.md` (this proposal answers
its three routed questions), `ops/reviews/cto-milestone2b3a-architecture.md`
and its Red Team review (the concurrency machinery this milestone reuses,
not re-derives).

## Answering Design Conformance's three routed questions

1. **Mid-meeting "request a perspective" and the follow-up thread: out of
   scope for 2B3B.** These are real, separable feature increments on top
   of a complete meeting record, not part of the design doc's core five
   steps. Building them now would roughly double this milestone's
   surface area for two features the Founder didn't ask for by name.
   Flagged explicitly, not silently dropped — a natural 2B3C candidate.
2. **Preset decision-option buttons: not built. Free-text decision
   instead**, matching the existing Decisions screen's pattern. Real
   candidate-option synthesis would need its own careful prompt design
   and its own risk of the options not honestly reflecting the
   discussion if under-specified — not worth the added complexity and
   risk for v1 when a free-text field is equally real and strictly
   simpler.
3. **Participant selection: genuinely CEO-driven, not Founder-picks-a-
   checklist.** The design doc is explicit ("Orchestrator + CEO Agent
   select participants... only agents with real relevant expertise
   join") and the Founder's brief said implement this milestone "as
   previously specified" — simplifying away the one mechanic the doc
   names first would be the most contestable deviation available, for
   real but avoidable complexity (one extra ~3-8s CEO call). Built as
   proposed below.

## The five steps, mapped to real mechanism

### 1. Founder raises a question

`POST /api/meetings` — new write route, same token-gated boundary as
every other write (`secrets.compare_digest` against the existing
`SESSION_TOKEN`; no new authorization mechanism). Body: `topic` only.
This single POST synchronously runs the entire meeting (steps 2–4 below)
and redirects to the finished meeting page — see "Why synchronous," below.

### 2. Orchestrator + CEO Agent select participants

`MEETING_PARTICIPANT_ALLOWLIST = ("ceo", "product", "cto", "financial",
"marketing", "qa", "security", "red-team")` — the exact eight roles
`EXECUTIVE_MEETINGS.md` names. Checked each of the four not already
allowlisted for Ask-Agent (`product`, `marketing`, `security`,
`red-team`) against `.claude/agents/*.md`: all four have Bash in their
*normal* configuration (`marketing` also has Write) — identically the
same risk profile `cto`/`qa`/`ceo`/`financial` had before Ask-Agent's
zero-tool restriction neutralized it. The same restriction (`--tools ""`,
`--strict-mcp-config`) applies to every meeting-participant invocation,
for the same reason already reviewed and shipped in 2B2/2B3A — this is
not a new safety model, it's the existing one extended to more role
names.

**CEO is always a participant** — never optional, matching the mockup
(CEO's card is never absent) and the doc's framing (CEO gives a
strategic-framing position *and* performs the synthesis in step 4 — two
distinct calls, not one). "Orchestrator" in the doc's phrase maps to
this server's own code enforcing the allowlist and validating CEO's
output — the actual judgment call ("which of the other seven are
relevant to this topic") is a real CEO invocation: given the topic and
the seven non-CEO candidate role names, CEO is asked to return the
relevant subset. Its response is parsed for role names and **every name
is validated against the fixed allowlist before use** — CEO's output
selects *which* of eight fixed, pre-approved identities participate; it
never supplies a new identity, a tool, or a model. Capped at 6 total
participants (including CEO) even if CEO nominates all seven others, to
bound worst-case orchestration time and cost.

### 3. Each participant states its real position

This is where 2B3A's foundation gets reused, not rebuilt. Real
concurrent invocation of up to `agent_runtime.MAX_CONCURRENT_INVOCATIONS`
(3, unchanged — meetings do not get a separate, larger concurrency
budget; they compete for the same global bound as any concurrent
Ask-Agent traffic, so "concurrency is deliberately bounded" holds
system-wide, not per-feature) participants at once via
`concurrent.futures.ThreadPoolExecutor(max_workers=3)` (stdlib — no new
dependency), one `invoke_agent()` call per participant thread.

**One real behavioral difference from Ask-Agent, needed and scoped
narrowly**: Ask-Agent's semaphore acquire is non-blocking by design (an
ad-hoc single request should fail fast and honestly, never queue
silently — 2B3A's Red Team affirmed this). A meeting needs *every*
selected participant's position, not "whichever 3 happened to win the
race" — an instant-reject for participants 4–6 would silently produce
an incomplete meeting. `invoke_agent()` gains one new parameter,
`wait_for_slot: bool = False` — when `True` (used *only* by meeting
orchestration, the Ask-Agent HTTP route's call is untouched, `False` by
default), the semaphore acquire blocks (bounded by the same per-call
`timeout_s`) instead of failing immediately. The semaphore itself is not
touched — still exactly 3 real permits, system-wide, shared by every
caller. A `ThreadPoolExecutor(max_workers=3)` submitting more than 3
participants means the 4th+ simply wait for a pool worker, and once
running, wait (briefly, bounded) for a semaphore slot — both bounds are
the same "3," reinforcing each other, not stacking into a fourth-power
concurrency knob to reason about.

**Persistence — one source of truth, not a duplicate.** Every
participant's position is written via `opsdb.send_message()` —
`scope='meeting'`, `meeting_id=<id>`, `from_agent=<participant>` — the
*same* mechanism Ask-Agent already uses, just a different scope value
the schema already anticipated (`messages.scope CHECK (...,'meeting')`
has existed since Phase 1, unused until now). **`meetings.positions`
(the existing JSON-object column) is deliberately left unwritten** — a
considered decision, not an oversight: writing the same position text
into both `messages` and a JSON blob would be exactly the kind of
duplicated state this project's reviews have repeatedly flagged (most
recently 2B2's "one conversation store" rule). A meeting's positions are
rendered by querying `messages WHERE meeting_id=? ORDER BY id`, same
pattern as an Ask-Agent thread. Each participant invocation also gets a
real `agent_runs` row (`opsdb.start_run()`/`end_run()`, `scope_type=
'meeting'`, `scope_id=<meeting id>`, `current_activity=
MEETING_ACTIVITY_LABEL` — a distinct label/LIKE-pattern from Ask-Agent's,
so the two are never confused, though `scope_type` alone already
separates them) — this is what makes "Working" status appear correctly
on the Agents roster/Agent Detail while an agent is contributing to a
meeting, reusing the *existing* deterministic-status derivation, not a
new concept. **No exclusivity guard** (unlike Ask-Agent's "one open run
per agent") — a considered omission: two different meetings needing the
same agent's perspective concurrently is legitimate (each invocation is
fully independent and stateless, its own transcript, no shared
mutable conversation the way a single agent's Ask-Agent thread is), so
blocking it would make multi-meeting operation impossible for no real
safety benefit.

**Thread safety**: each worker thread opens its own `opsdb.connect()` —
never shares a connection across threads, the same hard rule 2B3A
established and verified.

**Failure isolation**: a participant that times out or errors gets its
honest failure recorded (`agent_runs.status='failed'`, **no fabricated
position message** — if a participant's real invocation fails, the
meeting simply doesn't include a position from them, and says so, never
invents one) — this mirrors Ask-Agent's "never fabricate an answer on
failure" rule exactly, now applied per-participant instead of
per-request.

### 4. CEO synthesizes

A fourth (or Nth, but conceptually the "closing") CEO invocation, given
the topic and every participant's real, persisted position text, asked
to produce agreement, disagreement, unresolved questions, and a
recommendation. This is a **separate call from CEO's own position** in
step 3 — synthesizing requires seeing everyone else's input first, which
doesn't exist yet when CEO gives its own position concurrently with the
others. Parsed into the four corresponding `meetings` columns
(`agreements`, `disagreements`, `unresolved_questions`, `recommendation`)
— genuinely CEO's own words, not template-filled, matching the doc's
"produced by CEO, not by averaging votes." **If this call itself fails**
(timeout/runtime error), the meeting is still saved with every real
position that succeeded — `recommendation` etc. simply stay `NULL`,
rendered honestly as "not available" rather than fabricated.

### 5. The Founder decides

`POST /api/meetings/<id>/decide` — same token boundary. Body:
`decision` (free text, see Design Conformance item 3). New plain
function `opsdb.decide_meeting()`: one atomic transaction that creates a
real `decisions` row (via a newly-extracted plain
`opsdb.record_decision()` — `cmd_decision_record` becomes a thin
wrapper, same refactor pattern as every prior milestone's CLI
functions) and sets `meetings.founder_decision` +
`meetings.linked_decision_id` together, guarded by
`WHERE founder_decision IS NULL` (same one-time-only pattern as
`decide_approval()`) so a meeting's decision, once recorded, cannot be
silently overwritten by a second submission.

## Why synchronous, not a background job

The whole `POST /api/meetings` request blocks until the meeting
completes — selection (~3–8s) + up to 2 batches of ≤3 concurrent
participants (~3–30s each, bounded by `DEFAULT_TIMEOUT_S`) + synthesis
(~3–30s). Worst case with 6 participants: roughly 30s (selection) + 30s
+ 30s (two participant batches) + 30s (synthesis) ≈ 2 minutes — a real,
disclosed, bounded worst case, not an open-ended wait. This is
consistent with Ask-Agent's existing synchronous design and doesn't need
a new polling/background-job mechanism: 2B3A's `ThreadingHTTPServer`
already means every *other* Control Center page stays responsive while
this one request is in flight, which is the actual problem an async job
queue would otherwise be solving. Building one now would be exactly the
kind of unnecessary framework the Founder's brief has repeatedly warned
against.

## Files touched

- `ops/control-center/agent_runtime.py` — `MEETING_PARTICIPANT_ALLOWLIST`,
  `MEETING_ACTIVITY_LABEL`/`_LIKE`, `invoke_agent(..., wait_for_slot=False)`.
- `ops/control-center/server.py` — `POST /api/meetings`,
  `POST /api/meetings/<id>/decide`, `GET /meetings/<id>.html`.
- `ops/control-center/generate_meetings.py` — meeting detail rendering
  (position cards, synthesis, decision panel/form); list view gains a
  "Raise a question" form and links each row to its detail page.
- `ops/db/opsdb.py` — `record_decision()` (extracted plain function),
  `decide_meeting()` (new, atomic).
- `ops/DATA_MODEL.md` / `ops/SECURITY.md` — document `messages.scope=
  'meeting'` going live, the meeting-participant allowlist and its
  shared safety reasoning, and `wait_for_slot`'s effect on the
  concurrency model.

## Open questions for Red Team

1. Is capping total participants at 6 (including mandatory CEO) the
   right number, or should it be lower/higher given the worst-case
   ~2-minute synchronous request duration?
2. Is `wait_for_slot=True` (blocking acquire, scoped only to meeting
   orchestration) an acceptable, narrow deviation from 2B3A's
   non-blocking-only concurrency model, or does Red Team want a
   different mechanism (e.g. a meeting-specific smaller pool) instead?
3. Is leaving `meetings.positions` unwritten (deriving positions from
   `messages` instead) the right call, or does Red Team want the JSON
   column populated too (and if so, as a cache of what, derived how,
   kept in sync how)?
4. Is skipping an exclusivity guard for meeting-participant runs (an
   agent can serve two concurrent meetings) sound, or does Red Team see
   a real problem this creates?
5. Any concern with the worst-case ~2-minute synchronous request
   duration itself, given the whole point of 2B3A was responsiveness?
