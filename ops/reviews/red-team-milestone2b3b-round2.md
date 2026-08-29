# Red Team review — Phase 2, Milestone 2B3B round 2 (TASK-011)

Gate 3 of 8 for TASK-011. Reviewing
`ops/reviews/cto-milestone2b3b-round2-architecture.md` ("CTO round 2")
against `ops/EXECUTIVE_MEETINGS.md`, `ExecutiveMeeting.dc.html`,
`ops/reviews/design-conformance-milestone2b3b-round2.md`, the shipped
first-pass code (`meeting_orchestrator.py`, `agent_runtime.py`,
`opsdb.py`), `ops/SECURITY.md`, and this project's own prior review of
the same feature (`cto-milestone2b3b-architecture.md` +
`red-team-milestone2b3b-architecture.md`, the first-pass reviews this
document is a direct sequel to). Performed directly, not via a spawned
subagent (same disclosure as every Red Team review since 2B3A — the
`Agent` dispatch tool is unavailable this session).

Per my own role doc: authority of the proposer is not evidence a plan
is sound. CTO round 2 is well-reasoned and mostly correct, but "well-
reasoned" and "correct" are not the same thing, and one of its central
moves — revising a number my predecessor already reviewed and affirmed
— gets exactly the scrutiny that revision earns, not a pass because the
reasoning reads convincingly.

## Verdict: PASS WITH CONDITIONS

Items 1 (participant selection), 3 (follow-up thread), and 5 (retry) are
sound and may proceed to Development once the conditions below are met.
**Item 2's participant-cap revision is not affirmed as proposed** — see
finding 1. This does **not** block the other three items. Development
should proceed on items 1, 3, and 5 now; item 2 (request-perspective)
should be built using the *already-approved, unrevised* cap semantics
(a manual add is eligible only while total participants < 6, no new
`MAX_REQUESTED_PARTICIPANTS` constant, no new Founder decision-record
needed) unless and until the Founder is presented with a corrected
options framing and decides otherwise. Section "Disposition of item 2"
below spells this out precisely.

## Findings

### 1. The participant-cap revision — not affirmed. This is the load-bearing finding.

CTO proposes: manual adds via "Request another agent's perspective" no
longer count against `MAX_MEETING_PARTICIPANTS=6`; a new
`MAX_REQUESTED_PARTICIPANTS=2` bounds them instead, worst case 8 total
participants. The stated evidence is a single fact: the mockup's only
depicted example shows 6 grid cards plus 1 requested card, 7 total.

I do not accept this as sufficient grounds to revise a previously
affirmed cost/time bound, for three independent reasons:

**a. The feature isn't in the spec text at all — only in one mockup
panel.** `ops/EXECUTIVE_MEETINGS.md` describes exactly five steps and
never mentions a mid-meeting "request another perspective" affordance.
The entire feature is derived from one static illustration in
`ExecutiveMeeting.dc.html`. Treating a specific card *count* in that
one illustration as authoritative cap arithmetic — rather than as what
a mockup panel usually is, a plausible/typical scenario chosen to look
good in a screenshot, not a boundary-condition spec — is reading more
precision into the artifact than the artifact was built to carry. Design
Conformance round 2 itself only went as far as "this reads as the cap
applying only to initial selection" (§1, item 2) — a hedge, not a
finding. CTO's document converts that hedge into a settled premise and
then reasons forward from it as though it were established fact.

**b. Even granting the mockup as evidence, CTO's own chosen number
isn't supported by it.** The mockup shows **one** requested card, not
two. If "the mockup's example is factual evidence" is the standard being
applied, that standard supports `MAX_REQUESTED_PARTICIPANTS=1`, not `2`
— CTO's own document never explains where the second slot comes from.
This is exactly the "are the stated assumptions actually supported"
question my role doc requires I ask, and here the answer is no: the
document cites evidence for "manual adds exist and can exceed the
original 6," then picks a number one larger than what that evidence
actually shows, with no independent justification for the extra unit.

**c. The revision isn't scoped to just "one more slot" — it compounds
with retry and follow-up into a materially larger aggregate cost than
what was reviewed and affirmed the first time.** See finding 2. The
first pass's cap was reasoned about, tested, and affirmed against a
disclosed ~$4 / 8-invocation worst case. This revision, combined with
`MAX_RETRIES_PER_PARTICIPANT=2` (itself new in this round), pushes the
real worst case to roughly 3x that — a change of that magnitude to a
cost bound that was explicitly the subject of a prior Red Team
affirmance deserves more than "the mockup implies it," especially since
(a) and (b) above mean the mockup doesn't actually imply what CTO reads
into it as cleanly as claimed.

CTO's document itself recognizes this is a revision it isn't entitled
to make unilaterally and routes it to a Founder-approval decision-record
— that process discipline is correct and I have no objection to it. My
disagreement is with the *content* being proposed for that decision, not
the process wrapping it. **My recommendation for the Founder's actual
choice, if and when this is put to them: keep option (a) — the cap
binds end-to-end, 6 total always** — the conservative, already-reviewed
default, over option (b) as currently specified. If the Founder wants
a manual-add carve-out despite this, `MAX_REQUESTED_PARTICIPANTS=1` (not
2) is the number CTO's own cited evidence actually supports.

**Disposition of item 2**: this finding blocks *only* the cap-revision
question, not the request-perspective feature itself. Development should
build `/api/meetings/<id>/request-perspective` now, exactly as CTO
specifies (route, eligibility-by-allowlist, `add_meeting_participant()`,
attribution via the `participating_agents` shape upgrade — see finding
5), with one change: the atomic eligibility check in
`add_meeting_participant()` should reject when **total current
participants (selected + requested) is already at
`MAX_MEETING_PARTICIPANTS`**, using the existing, already-affirmed
constant, and should not introduce `MAX_REQUESTED_PARTICIPANTS` at all.
This requires no new Founder decision-record (it's consistent with
already-approved architecture) and doesn't block the other three items
or the rest of item 2's mechanism. If the Founder later wants the cap
loosened, that is a small, separable follow-on change gated by their
own decision on the corrected framing above — it should not gate
TASK-011 as a whole.

### 2. Aggregate cost surface — real, bounded per-mechanism, but never summed and disclosed as one number; "parity" is true per-thread but not in aggregate

The first pass disclosed one clean number: worst case ~8 real
invocations per meeting (1 select + up to 6 positions + 1 synthesis),
~$4. That framing let a reader reason about the whole feature's cost at
a glance. CTO round 2 introduces three more cost-multiplying mechanisms
but never re-does that arithmetic:

- `MAX_RETRIES_PER_PARTICIPANT=2` — CTO's own formula, "(participants
  selected) × (1 + MAX_RETRIES_PER_PARTICIPANT)," means the *initial
  batch alone* has a worst case of up to 6 × 3 = 18 invocations, not 6.
- Item 2's requested participants are "retriable too, under the same
  cap" — up to 2 (or, per finding 1, 1) requested participants × 3 =
  up to 6 more.
- Selection (1) + synthesis (1).

Summed, the real worst-case invocation count per meeting is on the order
of **25+ real, $0.50-bounded invocations (~$12+)** — roughly 3x the
previously disclosed and affirmed figure — and that's *before* item 3's
follow-up threads, which have no cap at all. This number appears nowhere
in CTO's document; each mechanism is bounded and disclosed individually,
but the compounded total is not computed anywhere, unlike the first
pass's explicit single figure. This is a real "hidden cost" in the
literal sense my role doc asks about: not hidden because it's secret,
hidden because no one added it up.

**On item 3's follow-up threads and the "parity, not a new risk
category" argument**: this is partially a rationalization, not a full
answer. It's true *per thread* — a meeting follow-up thread has the same
unbounded-rounds behavior as an Ask-Agent thread, no worse. But it
elides the multiplying factor: Ask-Agent's unbounded-rounds risk is
structurally capped at exactly 5 possible threads (one per
`ASK_AGENT_ALLOWLIST` entry, ever). A meeting follow-up thread exists
per `(meeting, participant)` — the number of threads that can each carry
unbounded, real-money rounds grows without bound as meetings accumulate,
something Ask-Agent's fixed-5-thread design never permitted. "Parity"
holds for the shape of the risk; it does not hold for the size of the
surface it now applies to, and CTO's document states the parity framing
without naming that distinction.

**Condition**: before Development starts, CTO (or Development, as part
of implementation) must compute and disclose the real closed-form
worst-case-cost figure for the four items combined (selection + initial
batch with retries + requested participants with retries + synthesis),
the way the first pass did, and must explicitly disclose that follow-up
threads make the true per-meeting ceiling open-ended rather than folding
that fact silently into "parity." This is a disclosure requirement, not
a redesign — none of the individual mechanisms need to change size to
satisfy it. As a cheap, optional hardening (not required to pass this
gate): a generous soft cap on follow-up rounds per thread (e.g. 20)
would close the one genuinely unbounded piece of this surface at near-
zero implementation cost, consistent with how every other input in this
codebase (`MAX_ASK_MESSAGE_CHARS`, `MAX_DECISION_CHARS`, `MAX_TOPIC_CHARS`)
already gets a generous-but-finite bound rather than none.

### 3. Security/trust surface — no new authorization risk, but the followup route is a genuine (if modest) new magnitude of the disclosed cost-amplification risk, and SECURITY.md should say so

Agreed with CTO: three new write routes under the same `SESSION_TOKEN`
gate do not cross into a *new kind* of authorization risk.
`ops/SECURITY.md` already discloses (Milestone 2B1/2B2 sections,
`risks.id=2` and `risks.id=3`) that the token proves "a page this server
rendered," not a specific human, and that an agent with Bash tool access
could already forge a costed Ask-Agent or meeting-creation request. Three
more routes gated the same way is "more of the same disclosed risk," not
a qualitative escalation — I don't think Red Team should manufacture a
new authorization concern where the trust model genuinely hasn't
changed.

Where I do want a disclosure update: `/api/meetings/<id>/followup`
specifically has no rate limit or round cap of any kind (finding 2). If
the session token leaks or is forged, an attacker (or an agent with Bash
access, the already-disclosed vector) could drive unlimited real,
$0.50-bounded invocations against a single meeting with no ceiling — a
larger real-dollar blast radius through this one route than any existing
route currently permits from a single forged request. This doesn't
change the *authentication* story SECURITY.md already discloses, but it
does change the *magnitude* of what a single successful forgery can cost,
and SECURITY.md's "Ask-Agent runtime authorization" section currently
only describes a bounded-per-request cost. **Condition**: extend
`ops/SECURITY.md` with a short paragraph under a new "Executive Meetings
round 2" heading disclosing this specific unbounded-cost surface, the
same way every prior milestone's write-path additions got their own
disclosure paragraph there. Retry and request-perspective, being bounded
(finding 1's revision notwithstanding), don't need special new
disclosure beyond what's already there — this condition is about
followup specifically.

### 4. Retry's exclusivity guard (`start_meeting_retry_run`) — mechanism verified correct; one specific implementation trap flagged

Walked through this independently rather than trusting CTO's
description. `BEGIN IMMEDIATE` acquires SQLite's write lock immediately
on transaction start, so a second concurrent call to
`start_meeting_retry_run()` for the same `(agent, meeting)` genuinely
blocks until the first transaction commits or rolls back — this is the
same mechanism 2B3A's Red Team review verified empirically for
`start_ask_agent_run()` (5 concurrent threads, zero lost writes, full
serialization), and nothing about narrowing the scope to
`scope_id=meeting_id` changes that guarantee. Traced the specific race
this is meant to close (a double-clicked Retry button) and it closes
correctly: the second call's `BEGIN IMMEDIATE` blocks, then its own
open-run SELECT (post-commit-of-the-first) correctly finds the row the
first call just inserted and rejects with `ValueError`.

I also checked a case CTO's document doesn't explicitly call out: does
the same guard correctly prevent a Retry from racing the **original,
still-in-flight** `_gather_position()` invocation for that participant
(not just racing another Retry)? Per CTO's stated open-run check —
`(agent_id, scope_type='meeting', scope_id=meeting_id, ended_at IS
NULL)`, with **no** `current_activity LIKE`-pattern filter — yes: the
original gather's own `agent_runs` row (label
`MEETING_ACTIVITY_LABEL`) matches this same scope and would correctly
block a premature Retry attempt while it's still running. This is
correct as specified, but it is a real trap for Development to fall
into: `start_ask_agent_run()`, the function this is explicitly modeled
on, *does* filter by an `activity_like` pattern (`ASK_AGENT_ACTIVITY_LIKE`)
as one of its parameters, because Ask-Agent's guard needs to ignore this
project's own unrelated task-scoped runs against the same agent name
(Code Review, TASK-007's finding). A developer pattern-matching the
precedent too literally could add an equivalent `activity_like`
parameter to `start_meeting_retry_run()` "for consistency" — which would
silently reopen exactly the race this function exists to close, by
letting a Retry-labeled check ignore the still-open original-gather row.
**Condition**: `start_meeting_retry_run()`'s open-run check must match
on scope alone (`agent_id` + `scope_type='meeting'` + `scope_id`), with
no activity-label filtering of any kind — Code Review must verify this
by reading the actual query, not by confirming a parameter list looks
similar to the precedent.

No other gap found in the TOCTOU handling. The retry-count check (count
of prior `status='failed'` rows for `(agent_id, meeting_id)`, capped at
`MAX_RETRIES_PER_PARTICIPANT`) is correctly performed inside the same
`BEGIN IMMEDIATE` transaction, so it can't race a concurrent retry
either.

### 5. `participating_agents` shape upgrade — not overengineered, but accepts permanent technical debt that a trivial one-time backfill would avoid; and the migration is undertested against existing readers

The shape upgrade itself (flat string → `{"name","source","requested_by"}`
object) is a reasonable, minimal-diff choice compared to a new
`meeting_participants` table — it doesn't add a dependency, doesn't
touch the schema, and correctly keeps position *text* solely in
`messages`. I don't think this is overengineering. But two real problems:

**a. The "no migration/backfill" choice is asserted, not weighed.**
CTO's document states "No migration/backfill needed... old and new
shapes are read through the same helper indefinitely" as though that's
obviously the right call, without ever considering the alternative: a
one-time `UPDATE meetings SET participating_agents = ...` converting
every existing flat-string row to the new object shape at deploy time.
Given this is an early-stage feature (Milestone 2B3B has been live for
one prior round; the row count is small), a one-time backfill is a
cheap, low-risk operation that would let `_normalize_participant()`
eventually be deleted rather than being a permanently-required parsing
layer every future reader must remember to call, forever. Choosing
indefinite dual-shape state over a near-free one-time fix, without
weighing the tradeoff at all, is exactly the "unnecessary technical
debt" question my role doc asks. **Condition**: either add the one-time
backfill (converting existing rows, then treating the flat-string case
in `_normalize_participant()` as legacy-only / removable later), or, if
CTO still prefers to skip it, the document should say why the backfill
was considered and rejected, not omit it as an option entirely.

**b. Concrete, verified regression risk in an existing reader.** Grepped
every call site: `generate_meetings.py` reads `participating_agents` in
two places today (`json_list(meeting["participating_agents"])` at line
139, and again in the list view at line 86) and **neither goes through
any normalization**. Specifically, `build_meeting_detail()` (line 139)
does `for name in participants: if name in positions_by_agent: ...` —
if `participants` becomes a list of dicts, `name in positions_by_agent`
raises `TypeError: unhashable type: 'dict'` on the very first meeting
whose row was created (or, per (a), backfilled) in the new shape. This
isn't a hypothetical — it's the exact, verifiable shape of the crash
CTO's own "Files touched" list gestures at fixing ("render a 'requested
by' marker on requested-participant cards") without actually stating
"replace the raw read at line 139 with `_normalize_participant()` for
every entry, and the same at line 86." **Condition**: Code Review must
independently grep every existing read of `meeting["participating_agents"]`
(not just the new call sites CTO's document enumerates) and confirm each
one is updated to normalize — this is exactly the "verify by grep, don't
trust the design doc's own claim" standard 2B3A's Red Team review
already established for this project, applied to a new case.

### 6. Item 3's full-context reconstruction — independently verified as genuinely necessary, not hidden cost

Checked CTO's claim against the mockup directly rather than accepting
it. The mockup's follow-up reply reads: *"CTO: Yes — cuts it to about 4
days. Import-only also shrinks Security's parsing-surface concern."*
This explicitly references another participant's original position —
the requested SECURITY card's text ("A PDF parser is a common injection
surface... flag as a Security Review item") — which CTO's own position
never mentioned. A follow-up invocation given only "topic + CTO's own
original position + this thread's own prior turns" could not honestly
produce that sentence; it requires visibility into Security's position,
which lives only in the shared `meeting-{id}` thread. CTO's claim is
correct, and I confirm it independently rather than taking it on faith.

The proposed mechanism (pull all `from_agent` rows from the shared
`meeting-{id}` thread + this one follow-up thread's own prior turns,
rebuilt fresh per call, same discipline `_build_transcript()` already
uses) is appropriately scoped — not more context than the mockup's own
example demands, and reuses an existing, already-reviewed pattern rather
than inventing a new caching mechanism. No objection.

### 7. A gap CTO's document does not flag: follow-up eligibility doesn't require the participant to have an actual recorded position

CTO's eligibility rule for `/api/meetings/<id>/followup` is "`agent_name`
must already be a participant (member of the normalized
`participating_agents`, any source)." This is weaker than it needs to be:
membership in `participating_agents` is set at selection/request time
and is **not** revoked or altered when a participant's real invocation
fails (item 5's own eligibility check for Retry — "no existing position
message... the slot never succeeded" — depends on exactly this fact,
that a failed participant is still "present"). That means a Founder
could open a follow-up thread with a participant who never actually said
anything — clicking "Follow up" instead of "Retry" on a card that reads
"Selected, but no response was recorded." The resulting invocation would
run with a transcript containing no original position for that agent to
follow up on, producing a confusing, low-value exchange and spending a
real `$0.50`-bounded call on an ill-formed interaction. This is the
inverse problem of finding 1: not a missing bound on cost, but a missing
correctness check that lets the Founder trigger the feature in a state
it wasn't designed to handle. **Condition**: `/api/meetings/<id>/followup`'s
eligibility check should additionally require a real position message
from that agent already exists in the shared `meeting-{id}` thread — the
same "has a real, successful position" test Retry's eligibility already
performs from the opposite direction. Cheap to add (one more query
predicate in the same eligibility function), should be included in this
round rather than deferred.

### 8. Items affirmed without reservation (CTO's remaining open questions)

- **No auto-re-synthesis after a manual add or a successful retry**
  (CTO open question 2): affirmed. Consistent with the "never silently
  overwrite a Founder-visible record" principle `decide_meeting()`'s own
  `WHERE founder_decision IS NULL` guard already enforces elsewhere in
  this table; a future explicit re-synthesize affordance is a reasonable
  follow-up, not a gap in this round.
- **Orchestrator's `agent_runs.scope_type='company'` for the validation
  step, with the visible content in a meeting-scoped message** (CTO open
  question 4): affirmed. The run genuinely happens before
  `create_meeting()` — `opsdb.start_run()` itself would reject a
  meeting-scoped run with no `scope_id` to give it, since the meeting
  doesn't exist yet. Deferring or re-scoping the run to force agreement
  with the message's scope would require restructuring `create_meeting()`
  to accept participants after row creation, a materially bigger change
  for no real benefit — honest attribution (a real, findable company-
  scoped run) is preferable to a forced-but-fictional meeting scope.
- **`MAX_RETRIES_PER_PARTICIPANT=2`** (CTO open question 6): affirmed as
  a reasonable number on its own terms — unlike the participant-cap
  revision (finding 1), a retry doesn't add a new headcount, it re-
  attempts a slot already counted in the original cap, so the "Founder-
  initiated, one-at-a-time, materially different trust/cost posture"
  argument genuinely applies here without the same evidentiary weakness.
  It must, however, be included in the aggregate cost disclosure per
  finding 2.

## Conditions Development must satisfy before/during this work

1. Item 2 ships using `MAX_MEETING_PARTICIPANTS=6` as the binding total
   cap (selected + requested), with **no** `MAX_REQUESTED_PARTICIPANTS`
   constant, unless and until the Founder has been presented with the
   corrected framing in finding 1 and explicitly decides otherwise. If
   the Founder does authorize a carve-out, the supported number per the
   mockup's own evidence is 1, not 2.
2. Before or alongside implementation, compute and disclose the real
   closed-form worst-case invocation/cost figure across selection +
   initial batch with retries + requested participants with retries +
   synthesis (finding 2) — a single number, the way the first pass
   disclosed one. Explicitly disclose that follow-up threads make the
   true per-meeting ceiling open-ended. A generous soft round-cap per
   follow-up thread is recommended but not required to pass this gate.
3. Add a short "Executive Meetings round 2" disclosure to
   `ops/SECURITY.md` covering the followup route's uncapped-cost surface
   specifically (finding 3).
4. `start_meeting_retry_run()`'s open-run check must scope by
   `(agent_id, scope_type='meeting', scope_id)` only — no
   `current_activity LIKE` filtering of any kind. Code Review must
   verify this by reading the actual query (finding 4).
5. Either add a one-time backfill converting existing flat-string
   `participating_agents` rows to the new object shape, or explicitly
   document why that option was rejected (finding 5a). Either way, Code
   Review must grep every existing reader of
   `meeting["participating_agents"]` (confirmed: `generate_meetings.py`
   lines 86 and 139, both unnormalized today) and verify each is updated
   to go through `_normalize_participant()` — not just the new call
   sites CTO's document lists (finding 5b). This is a concrete, verified
   crash risk, not a hypothetical one.
6. `/api/meetings/<id>/followup` eligibility must additionally require
   a real, already-recorded position message from that agent in the
   shared `meeting-{id}` thread (finding 7).

None of these conditions require re-architecting items 1, 3, or 5 as
designed. Conditions 1 and 2 are the only ones that touch item 2's
mechanism, and per "Disposition of item 2" above, item 2 can and should
proceed now under condition 1's conservative default rather than waiting
on a Founder round-trip.
