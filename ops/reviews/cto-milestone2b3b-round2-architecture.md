# CTO architecture proposal — Phase 2, Milestone 2B3B round 2 (TASK-011)

Gate 2 of 8 for TASK-011. Scope: the four Founder-authorized items from
`ops/reviews/founder-conformance-review-milestone2b3b.md` §4 — 1
(participant selection), 2 (mid-meeting "request another perspective"),
3 (meeting-scoped follow-up thread), 5 (manual retry of a failed
participant). Items 4 and 6 are out of scope and not discussed below.

Read first: `ops/reviews/design-conformance-milestone2b3b-round2.md`
("Design Conformance round 2") — this document resolves every open
question it raised. It is not restated here except where its own
citations are the basis for a decision.

This proposal builds directly on the shipped first pass
(`ops/reviews/cto-milestone2b3b-architecture.md`) and does not restate
mechanism it doesn't change: `MAX_CONCURRENT_INVOCATIONS=3`, the
synchronous-per-request model, `_gather_position()`'s prompt template,
`_synthesize()`, and `decide_meeting()` are unchanged and reused as-is.

## A rule that applies to all four items, stated once

**Every new write in this document is its own new POST route against an
already-created meeting** — `/api/meetings/<id>/request-perspective`,
`/api/meetings/<id>/followup`, `/api/meetings/<id>/retry` — same
`SESSION_TOKEN` gate as every existing write (`secrets.compare_digest`,
no new auth mechanism), same `<id>` + body-params shape as the existing
`/api/meetings/<id>/decide`. None of the three extend or reopen
`run_meeting()`. This is Design Conformance round 2's own routing note
(§2, "New POST routes, not an extended `run_meeting()`"), adopted
without change.

**Every new call site that invokes an agent for meeting-scoped work uses
`wait_for_slot=True` (blocking), never Ask-Agent's fail-fast mode.**
Stated as one rule rather than three separate picks: a meeting-scoped
call is always a continuation of something the Founder is actively
engaged with (adding a participant, following up, retrying a specific
failure) and deserves a real answer, not an instant "at capacity, try
again" — the same reasoning the first pass already used for
`_gather_position()`. Only the ad-hoc, fire-and-forget Ask-Agent route
stays fail-fast. This resolves Design Conformance round 2's item-3
"blocking vs. fail-fast" question, and applies identically to item 2's
manual add and item 5's retry.

## Item 1 — Participant selection: a real, deterministic Orchestrator step

**Decision: a deterministic code step, not a second LLM invocation. No
new allowlist entry anywhere.**

Design Conformance round 2 framed the real choice correctly and left it
open on purpose. Resolving it against both role docs' own wording:
`ops/agents/orchestrator.md` line 4 — "Never builds, approves, or tests
anything itself" — and its explicit "Not permitted: ... making a
Founder-only decision" (line 31 lists "overriding Code Review or
Security Review" and similar boundaries in the same spirit). A second
LLM call asked to independently judge "which of these roles are
relevant to this topic" *is* a second creative judgment on the same
question CEO already owns (`EXECUTIVE_MEETINGS.md`'s "Typical
participants and their lens" is written from CEO's strategic vantage,
not Orchestrator's workflow vantage) — building that call would make
Orchestrator do exactly the kind of approving/judging its own role doc
forbids, not resolve the conformance gap. A deterministic
validation/bounding step is Orchestrator's actual native lane
("workflow only... assigns work, tracks status, routes failures") and
is real, attributable work without becoming a second opinion competing
with CEO's.

**Mechanism.** Split what `_select_participants()` currently does into
two functions with two owners:

- `meeting_orchestrator._select_participants(topic) -> list[str]`
  (unchanged CEO call + `_parse_selection()`) now returns the **raw**
  parsed candidate names — allowlist-filtered by the existing regex (it
  can only ever match a name from `_CANDIDATE_ROLES`), but **not
  truncated**. This is CEO's judgment call, unchanged from today.
- New `meeting_orchestrator._validate_selection(conn, candidates:
  list[str]) -> tuple[list[str], str]` — Orchestrator's step. Pure
  Python: dedupes, drops `"ceo"` if CEO redundantly nominated itself,
  deterministically truncates to `MAX_MEETING_PARTICIPANTS - 1` (exact
  cap logic `_select_participants` used to inline), and builds a short
  explanation string ("Validated CEO's nomination: product, financial,
  qa. Admitted 3 of 3 — within the 5-other cap."). No `invoke_agent()`
  call — this never touches `ASK_AGENT_ALLOWLIST` or
  `MEETING_PARTICIPANT_ALLOWLIST`, because it never becomes a `claude
  --agent` subprocess. Latency added: effectively zero (pure in-process
  Python) — the first pass's ~2-minute worst-case budget
  (`cto-milestone2b3b-architecture.md` lines 180-194) is unchanged, not
  silently revised.

**Attribution — real, not a docstring comment.** `"orchestrator"` is
already a real row in the `agents` table (`agents.id=1`, confirmed by
direct query against `ops/db/operations.sqlite3`) — separate from
`ASK_AGENT_ALLOWLIST`/`MEETING_PARTICIPANT_ALLOWLIST`, which gate
*invocation*, not *attribution*. `opsdb.start_run()` needs no allowlist
change to accept `"orchestrator"` as `agent_name` today. Sequencing
matters: `_validate_selection()` runs **before** `create_meeting()` —
the meeting doesn't exist yet at that point, so the run is honestly
`scope_type="company"` (the same category `agent_runs.scope_type=
'company'` already covers "Orchestrator triage" per `DATA_MODEL.md` line
69 — "still a real run, not an exception to the rule"), not
`scope_type="meeting"`. Concretely, inside `run_meeting()`:

```
raw = _select_participants(topic)                          # CEO call, unchanged
run_id = opsdb.start_run(conn, "orchestrator", "company",
                          ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL)
validated, explanation = _validate_selection(conn, raw)     # deterministic
opsdb.end_run(conn, run_id, "ended")
participants = ["ceo"] + validated
meeting_id = opsdb.create_meeting(conn, topic, "founder", participants)
opsdb.send_message(conn, f"meeting-{meeting_id}-orchestrator", "meeting",
                    "orchestrator", explanation, to_agent=None, meeting_id=meeting_id)
```

The `agent_runs` row is honestly company-scoped (work done before the
meeting existed); the *content* a meeting's detail page actually shows —
what Design Conformance round 2 asked for — is the message, written the
moment `meeting_id` exists. New constant needed:
`ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL = "Orchestrator: validating
meeting participant selection"` in `agent_runtime.py`, next to
`MEETING_ACTIVITY_LABEL`. `generate_meetings.py` needs one small
addition to render this message as a distinct workflow note (not a
`render_position_card()` — Orchestrator doesn't have a position on the
topic, it validated who gets one).

Thread-id `meeting-{id}-orchestrator` is deliberately namespaced the
same way item 3's per-participant follow-up threads are (see below) —
and cannot collide with one, since follow-ups only ever address a name
present in `participating_agents`, and `"orchestrator"` is never added
as a participant.

## Item 2 — Mid-meeting "Request another agent's perspective"

**Route**: `POST /api/meetings/<id>/request-perspective`. Body:
`agent_name`.

**Eligibility**: any `MEETING_PARTICIPANT_ALLOWLIST` role not already
present in this meeting's participant list (by name) — same allowlist
as initial selection, no separate/reduced one. Matches the mockup's
affordance text ("e.g. QA" — a plain example, not evidence of a
narrower candidate set) and avoids inventing a second, untracked
"candidates considered but not selected" concept the system has no
record of today.

**Where attribution lives — upgrade `meetings.participating_agents`'
JSON shape, not a new `messages` column.** Design Conformance round 2
correctly flagged that `messages` has no metadata slot for "how/when
this participant joined" and that stuffing it into `body` text would be
exactly the kind of ad hoc, unparseable convention this project's
reviews keep flagging. Weighed against `DATA_MODEL.md`'s "don't
duplicate state" principle: the actual position *text* must stay solely
in `messages` (unchanged — no duplication there), but *provenance*
("selected" vs. "requested", and by whom) is membership metadata, and
`participating_agents` is already the single source of truth for
meeting membership. Extending its existing shape is the smaller change:

- `participating_agents` becomes a JSON array of objects:
  `{"name": "cto", "source": "selected", "requested_by": null}` for the
  initial batch (`create_meeting()` writes this shape from now on), and
  `{"name": "security", "source": "requested", "requested_by":
  "founder"}` for a manual add.
- **Backward compatibility**: every row created before this ships holds
  a flat array of bare strings (confirmed by `create_meeting()`'s
  current implementation, `opsdb.py` lines 470-489). A single shared
  normalization helper — `_normalize_participant(entry) -> dict`,
  belongs in `opsdb.py` next to `create_meeting()` since both the writer
  and every reader (`generate_meetings.py`, the new
  `add_meeting_participant()` below) need it — treats a bare string as
  `{"name": entry, "source": "selected", "requested_by": None}`. No
  migration/backfill needed; old and new shapes are read through the
  same helper indefinitely.
- **"requested by \<name\>"**: this server has no per-person Founder
  identity (`ops/SECURITY.md`'s disclosed limitation — the token proves
  "this server's own page," never "this specific human"; every existing
  write already uses the literal string `"founder"` for
  `initiated_by`/`decide_meeting(by="founder")`). `requested_by` is
  therefore always the literal string `"founder"` in this system today
  — the mockup's "— requested by Alex" is mockup flavor over a named
  persona, not evidence of a stored identity system this project has.
  Consistent with every other attribution already in the schema.

**Does it count against `MAX_MEETING_PARTICIPANTS=6`? No — explicit,
disclosed revision of the first pass's decision.** The first pass stated
plainly: "Capped at 6 total participants... to bound worst-case
orchestration time and cost" (`cto-milestone2b3b-architecture.md` lines
77-79) — with no carve-out for a manual add, because manual add didn't
exist yet. Design Conformance round 2's own citation is the deciding
evidence: the mockup's single depicted example is 6 initial cards *plus*
one requested card, 7 total (`ExecutiveMeeting.dc.html` lines 45-79) —
that is not an edge case Design got wrong, it is the *only* example the
spec ever gave, and it shows the cap not binding a manual add.

Reasoning for the revision, not just the citation:
1. The original cap bounds an *LLM's own unattended nomination* — CEO
   picking up to 5 others with zero further human judgment in the loop
   per invocation. A manual "Request another agent's perspective" click
   is Founder-initiated, one at a time, each one a conscious choice to
   spend the extra ~3-30s and ~$0.50 — a materially different trust and
   cost posture than the batch the original cap was sized around.
2. But not literally unbounded — an unattended-cost argument doesn't
   licence infinite manual adds either, and this milestone's own goal
   (real cost bounds, stated everywhere else in this document) would be
   undermined by leaving the *back half* of a meeting open-ended just
   because a human is clicking instead of an LLM nominating.

**New, smaller secondary bound**: `MAX_REQUESTED_PARTICIPANTS = 2`
(new constant, `agent_runtime.py`, next to `MAX_MEETING_PARTICIPANTS`)
— at most 2 manually-requested additions per meeting, checked inside the
same atomic write as the append (below). Worst-case total participants
per meeting becomes 6 + 2 = 8, a real, closed-form, still-bounded number
— not the unbounded "however many times the Founder wants to click" the
mockup's example alone would otherwise imply.

**This is a revision of a previously-reviewed architecture decision, per
my role doc I am not entitled to make it silently** — flagged in "Open
questions for Red Team" below, and recorded as a proposed decision via
`opsdb.py decision-record --founder-approval` (see end of this
document), not treated as already settled.

**Mechanism**: new `opsdb.add_meeting_participant(conn, meeting_id,
agent_name, requested_by="founder") -> None`. Modeled on
`decide_meeting()`'s `BEGIN IMMEDIATE` pattern (`opsdb.py` lines
508-557) — not `start_ask_agent_run()`'s, because the invariant being
protected is different (a JSON array read-modify-write, not an
open-run-exists check) but the *shape* of the fix is the same one this
codebase already uses for "read this JSON/row, decide, write it back,
atomically, because two concurrent requests could otherwise race on the
read." Inside one transaction: SELECT + normalize `participating_agents`,
reject (`ValueError`) if `agent_name` is already present or if the
number of `source="requested"` entries is already at
`MAX_REQUESTED_PARTICIPANTS`, else append and UPDATE, COMMIT. Server
route calls this atomic check-and-append **only after** a successful
`invoke_agent(agent_name, ..., wait_for_slot=True)` call — same
"never fabricate/never record a member with no real position" discipline
`_gather_position()` already applies: on invocation failure, nothing is
appended, the Founder sees an honest error and may click again (subject
to the same cap, since a failed attempt never got appended and so never
counted against it — the cap only ever counts real, successful
additions, consistent with how `MAX_MEETING_PARTICIPANTS` today only
ever describes real participants, never failed attempts).

On success: real `agent_runs` row (`scope_type="meeting"`,
`scope_id=meeting_id`, `MEETING_ACTIVITY_LABEL` — unchanged constant,
since this genuinely *is* "contributing a position," just later) +
`send_message()` into the **same shared** `f"meeting-{meeting_id}"`
thread every other participant's position already uses (not a new
thread — this is a real position on the topic, unlike item 1's
Orchestrator note or item 3's follow-up) + the atomic
`add_meeting_participant()` append.

**Does synthesis re-run after a manual add? No.** The mockup's own
layout supports this (the requested card sits with the position grid,
set apart by its own accent border, not woven into the "Areas of
agreement/disagreement" text) but the deciding reasons are independent
of that read: (1) auto-re-running synthesis on every manual add silently
doubles the cost/latency of what the Founder experiences as "just adding
one view" — no "synthesizing..." state is depicted anywhere in the
mockup's request flow; (2) silently rewriting `agreements`/
`disagreements`/`recommendation` after the Founder may already have read
or acted on the original synthesis violates the same "never silently
overwrite a Founder-visible record" instinct `decide_meeting()`'s own
`WHERE founder_decision IS NULL` guard exists to enforce elsewhere in
this exact table. A future explicit "re-synthesize" affordance is a real
option — flagged for Red Team, not built here.

## Item 3 — Meeting-scoped follow-up thread

**Route**: `POST /api/meetings/<id>/followup`. Body: `agent_name`,
`message`.

**Validation**: `agent_name` must already be a participant (member of
the normalized `participating_agents`, any source) — the Founder can
only follow up with someone who actually has a position in this
meeting, never an arbitrary allowlisted name. Message length: reuse the
existing bound pattern (`MAX_ASK_MESSAGE_CHARS`-equivalent — same shape
of input as an Ask-Agent message, no new constant needed beyond mirroring
that existing cap).

**Thread-id convention**: `f"meeting-{meeting_id}-{agent_name}"` — one
distinct thread per (meeting, participant) follow-up, separate from the
shared `f"meeting-{meeting_id}"` positions thread every participant's
*original* position already writes to. This is exactly what Design
Conformance round 2 asked for (§1, item 3, "Thread-id collision") and
what `server.py`'s existing `_build_transcript()` already assumes (one
`thread_id` = one participant's whole conversation) — reusing the shared
thread would mix a private back-and-forth into the same query result as
every other participant's one-shot position.

**Context a reply invocation receives — full reconstructed context, not
just the new question.** The mockup's own worked example is the
deciding evidence: CTO's reply ("Import-only also shrinks Security's
parsing-surface concern") references *another* participant's original
position, not just its own — a follow-up invocation given only "topic +
CTO's own position + this thread's prior turns" could not honestly
produce that answer. The transcript built for a follow-up call must
include: (1) the topic, (2) every participant's original position from
the shared `meeting-{id}` thread (all `from_agent` rows, not filtered to
just the addressee), (3) this specific follow-up thread's own prior
turns. Built fresh from `messages` on every call — the same
rebuild-from-scratch discipline `_build_transcript()` already uses for
Ask-Agent, not a new caching mechanism. This is a real, separate
`invoke_agent()` call per follow-up message (cost: same `MAX_BUDGET_USD=
0.50` ceiling as any other call — no different in kind from a normal
invocation, just triggered later and by a smaller prompt-context
rebuild rather than a bigger one). No new round cap: Ask-Agent
conversations already have unlimited back-and-forth rounds today with no
cap of their own — a follow-up thread inheriting that same
unbounded-rounds/bounded-per-call-cost posture is parity with an
existing, already-accepted feature, not a new risk category needing an
asymmetric restriction Ask-Agent itself doesn't have.

**Semaphore mode**: `wait_for_slot=True`, per the rule stated at the top
of this document.

## Item 5 — Manual retry of a failed participant invocation

**Route**: `POST /api/meetings/<id>/retry`. Body: `agent_name`.

**Eligibility**: `agent_name` must be a current participant (normalized
`participating_agents`) with **no existing position message** in the
`meeting-{meeting_id}` thread from that agent — i.e., the slot never
succeeded. This is checked inside the same atomic function as the guard
below (not just at the HTTP layer), closing a TOCTOU gap the same way
`start_ask_agent_run()` closes it for Ask-Agent.

**Exclusivity guard — yes, needed; new, narrowly-scoped mechanism, not a
reuse of `start_ask_agent_run()`'s.** Design Conformance round 2 is
right that the first pass's considered "no exclusivity guard on meeting
`agent_runs`" (`cto-milestone2b3b-architecture.md` lines 130-136) did not
anticipate retry, and is right that this is a genuine new race (a
double-clicked Retry button starting two overlapping invocations for the
same agent+meeting). I am **not** reopening the first pass's decision —
that reasoning ("two different meetings legitimately needing the same
agent concurrently") stays entirely correct and untouched. The new guard
below is scoped to `scope_id=meeting_id` specifically, so
`cto` retrying in meeting #5 still does not block `cto` being invoked
normally in meeting #9 at the same moment — cross-meeting concurrency is
unaffected. This is additive, closing only the race retry itself
introduces, not a loosening or tightening of the earlier guarantee.

**Mechanism**: new `opsdb.start_meeting_retry_run(conn, meeting_id,
agent_name, activity_label) -> int`. `BEGIN IMMEDIATE`, then inside the
transaction: confirm the agent and meeting exist; confirm `agent_name`
is a current participant; confirm no position message from this agent
already exists in `meeting-{meeting_id}` (reject `ValueError`,
"already succeeded" — a 409 at the HTTP layer); confirm no
currently-open `agent_runs` row for `(agent_id, scope_type='meeting',
scope_id=meeting_id, ended_at IS NULL)` (reject `ValueError`, "a retry
for this participant is already in progress" — the actual double-click
guard, same shape as `start_ask_agent_run()`'s open-run check but scoped
to this one meeting instead of globally); count prior `status='failed'`
`agent_runs` rows for this `(agent_id, meeting_id)` pair and reject once
at `MAX_RETRIES_PER_PARTICIPANT` (reject `ValueError`, "retry limit
reached for this participant" — a 409); else `INSERT` the new row,
`COMMIT`. Same `BEGIN IMMEDIATE`-not-in-try/except structure as
`start_ask_agent_run()`/`decide_meeting()` (Red Team's Milestone 2B3A
finding on masking `OperationalError` applies identically here — the
new function must repeat that exact structure, not just its intent).

**Retry cap — yes, `MAX_RETRIES_PER_PARTICIPANT = 2`** (new constant,
`agent_runtime.py`). The first pass's implicit cost ceiling ("at most
`MAX_MEETING_PARTICIPANTS` invocations per meeting") silently stops
holding once any slot can be paid for more than once — Design
Conformance round 2 flagged exactly this. Capping retries restores a
real, closed-form worst case: at most `(participants selected) × (1 +
MAX_RETRIES_PER_PARTICIPANT)` real invocations for the initial batch,
plus up to `MAX_REQUESTED_PARTICIPANTS` more from item 2 (each of those
is retriable too, under the same cap, by the same mechanism — retry and
request-perspective share one exclusivity/eligibility function shape,
not two parallel ones). This is a smaller, additive number the Founder
and Red Team can still reason about, not an open-ended one.

On success: `invoke_agent(agent_name, prompt, wait_for_slot=True)`
using `_gather_position()`'s existing prompt template unchanged, then
`send_message()` into the original shared `meeting-{meeting_id}` thread
(this is the position that was missing, not a new kind of record) +
`end_run(..., "ended")`. On failure: `end_run(..., "failed")`, no
message, Founder may retry again up to the cap. **Synthesis does not
auto-re-run** after a successful retry — same reasoning as item 2, not
repeated here; both share one rule.

## Files touched

- `ops/control-center/agent_runtime.py` — `MAX_REQUESTED_PARTICIPANTS`,
  `MAX_RETRIES_PER_PARTICIPANT`, `ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL`.
  No allowlist changes.
- `ops/control-center/meeting_orchestrator.py` — split
  `_select_participants()`/new `_validate_selection()`; `run_meeting()`
  reordered per item 1; new `gather_requested_position()`,
  `gather_followup_reply()`, `retry_position()` (thin wrappers around
  `invoke_agent()` + the new opsdb functions, same shape as
  `_gather_position()`); a new transcript builder for item 3's full
  meeting-context reconstruction.
- `ops/control-center/server.py` — three new routes:
  `/api/meetings/<id>/request-perspective`,
  `/api/meetings/<id>/followup`, `/api/meetings/<id>/retry`. Same
  token gate, same error-mapping conventions
  (`LookupError`→404, `ValueError`→409, `sqlite3.OperationalError`→503)
  already used by `_handle_meeting_decide`/`_handle_ask`.
- `ops/control-center/generate_meetings.py` — render the Orchestrator
  validation note (distinct from a position card); render a "requested
  by" marker on requested-participant cards; render the follow-up
  thread + its own reply form; render a "Retry" affordance on a
  no-position card, replacing the current unconditional "Selected, but
  no response was recorded" text (`generate_meetings.py` lines 152-159)
  when a token is present.
- `ops/db/opsdb.py` — `_normalize_participant()`, `create_meeting()`
  updated to write the object shape, `add_meeting_participant()`,
  `start_meeting_retry_run()`.
- `ops/DATA_MODEL.md` — document `participating_agents`' new object
  shape (with the backward-compat note for pre-existing flat-string
  rows), the three new thread-id conventions
  (`meeting-{id}`/`meeting-{id}-orchestrator`/`meeting-{id}-{agent}`),
  and the revised participant-cap semantics.

## Open questions for Red Team

1. **Item 2's cap revision is the single biggest item here**: manually-
   requested participants no longer count against
   `MAX_MEETING_PARTICIPANTS=6`, bounded instead by a new, smaller
   `MAX_REQUESTED_PARTICIPANTS=2`. This directly revises a number the
   first pass's architecture explicitly reasoned about and Red Team
   already affirmed (`cto-milestone2b3b-architecture.md` open question
   1; `red-team-milestone2b3b-architecture.md`). I am proposing this
   change, not silently making it — recorded via
   `opsdb.py decision-record --founder-approval` (see below). Is
   `MAX_REQUESTED_PARTICIPANTS=2` (worst case 8 total participants) the
   right number, or should Red Team push back on the mockup-derived
   reasoning itself?
2. **No auto-re-synthesis after either a manual add (item 2) or a
   successful retry (item 5)** — deliberate, but is it the right default
   long-term, or does the Founder need an explicit "re-synthesize" lever
   sooner than a future round?
3. **`participating_agents`' JSON shape upgrade** (flat strings →
   `{"name","source","requested_by"}` objects, with a normalization
   helper carrying old rows forward) — is extending an existing column's
   shape preferable to a new column/table, given `DATA_MODEL.md`'s
   "don't duplicate state" principle, or would Red Team rather see a
   clean new column even at the cost of a second thing to keep in sync?
4. **Item 1's `agent_runs.scope_type="company"` for Orchestrator's
   validation step**, with the actual visible content landing in a
   *meeting-scoped* message once the meeting exists — is that split
   acceptable, or does Red Team want the run itself deferred/re-scoped
   so `scope_type` and the message's `scope` agree?
5. **Item 3's full-context reconstruction** (topic + every original
   position + the one follow-up thread, rebuilt fresh per message) — is
   this the right amount of context, or too much prompt content/cost per
   follow-up turn versus a narrower option?
6. **`MAX_RETRIES_PER_PARTICIPANT=2`** — right number, given each retry
   is a fresh `$0.50`-bounded invocation?
7. **Three new POST routes, same `SESSION_TOKEN` gate as everything
   else** — no new authorization mechanism proposed. These let a holder
   of the token (or anything that can forge a request per the disclosed
   Phase 1 risk, `ops/SECURITY.md`) trigger additional real, costed
   invocations against an *already-completed* meeting, not only at
   creation time. Does the increased number of post-creation write
   surfaces change Red Team's risk read here, even though the trust
   model itself is unchanged?

---

Because item 2's participant-cap semantics is a revision of a
previously-reviewed, Red-Team-affirmed architecture decision — not a new
decision on an open question — it is recorded as a proposed decision
requiring Founder approval, not treated as already settled by this
document alone:

```
python3 ops/db/opsdb.py decision-record \
  --title "Milestone 2B3B round 2: manually-requested meeting participants are not bound by MAX_MEETING_PARTICIPANTS" \
  --problem "The first pass capped total meeting participants (including CEO) at 6 to bound worst-case synchronous cost/time, with no carve-out for a manual add (feature didn't exist yet). Item 2 (mid-meeting 'request another agent's perspective') needs a real answer to whether a manually-requested addition counts against that cap. The mockup's own only example (ExecutiveMeeting.dc.html) shows 6 initial cards plus 1 requested card, 7 total — implying it does not." \
  --options "(a) cap binds end-to-end, 6 total always, mockup's depicted scenario becomes impossible at a full meeting" "(b) cap does not bind manual adds, new smaller secondary bound (MAX_REQUESTED_PARTICIPANTS=2) added instead, worst case 8 total" \
  --decision "(b) — manual adds are not bound by MAX_MEETING_PARTICIPANTS; a new MAX_REQUESTED_PARTICIPANTS=2 bounds them instead." \
  --reason "A manually-requested addition is Founder-initiated and one-at-a-time, a materially different trust/cost posture than an LLM's own unattended batch nomination the original cap was sized around; the mockup's only depicted example is factual evidence the cap was never meant to bind this case." \
  --tradeoffs "Worst-case total participants and cost per meeting rises from 6 to 8; the original cap's stated cost bound no longer describes the true worst case without also reading MAX_REQUESTED_PARTICIPANTS." \
  --by cto \
  --founder-approval
```
