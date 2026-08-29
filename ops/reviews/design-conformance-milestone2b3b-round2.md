# Design conformance — Phase 2, Milestone 2B3B correction round 2 (TASK-011)

Gate 1 of 8 for TASK-011. Scope: the four items the Founder authorized
building from `ops/reviews/founder-conformance-review-milestone2b3b.md`
§4 — items 1, 2, 3, 5 (participant selection, mid-meeting "request
another perspective," meeting-scoped follow-up thread, manual retry of a
failed participant). Items 4 (preset decision buttons) and 6 (Round 2 /
fixed decision-enum) are **out of scope for this pass** — see §3.

Grounded in a fresh read of `ops/EXECUTIVE_MEETINGS.md`,
`ExecutiveMeeting.dc.html`, the founder-conformance review, and the
actual shipped code (`meeting_orchestrator.py`, `agent_runtime.py`,
`generate_meetings.py`, `server.py`, `opsdb.py`, `DATA_MODEL.md`) — not
a restatement of the conformance review's own framing.

## 1. Item-by-item: what's required, and what CTO Architecture must resolve

### Item 1 — Participant selection: "Orchestrator + CEO Agent"

**Required**: `EXECUTIVE_MEETINGS.md` line 20 — "**Orchestrator + CEO
Agent** select participants." Parallel construction to step 4's "The
record preserves... a synthesized recommendation (produced by CEO...)"
(line 38-39), which names one actor. Step 2 names two.

**Shipped**: `meeting_orchestrator._select_participants()` (lines 66-88)
invokes only `agent_runtime.invoke_agent("ceo", ...)`. Grepped every
call site in `agent_runtime.py`, `server.py`, `meeting_orchestrator.py`,
`generate_meetings.py` — the string `"orchestrator"` never appears as an
`agent_name` argument anywhere. The CTO's first-pass proposal
(`cto-milestone2b3b-architecture.md` lines 69-71) states its own
interpretation plainly: "'Orchestrator' in the doc's phrase maps to this
server's own code enforcing the allowlist and validating CEO's output"
— i.e., unlabeled validation logic, not a second actor with any
independent footprint in the persisted record.

**Does a real Orchestrator identity exist?** Yes, as a persona — both
`.claude/agents/orchestrator.md` and `ops/agents/orchestrator.md` define
a full role doc, and `ops/agents/orchestrator.md` lines 18-20 and 45
explicitly list "Meeting-participant selection checklist (with CEO)" /
"Select Executive Meeting participants (with CEO)" as a named
responsibility. But **the runtime cannot invoke it today**:
`agent_runtime.invoke_agent()` (lines 140-142) rejects any `agent_name`
not present in `ASK_AGENT_ALLOWLIST` (line 55: cto/qa/ceo/financial/
project-manager) or `MEETING_PARTICIPANT_ALLOWLIST` (line 78: ceo/
product/cto/financial/marketing/qa/security/red-team). "orchestrator" is
in neither. So there is a documented role with no invokable identity —
a real gap, not a naming quibble.

**My own recommendation** (not just restating the two options the
founder-conformance review listed): build a real, distinct
Orchestrator-owned step, but scope its *content* narrowly rather than
duplicating CEO's judgment call. The design doc's ordering and
`orchestrator.md`'s own boundary ("Not permitted: ... making a
Founder-only decision"; role is "Manages workflow only... Never builds,
approves, or tests anything itself") both point the same direction:
Orchestrator's real, distinct contribution should be *enforcement* —
taking CEO's raw nomination text and being the actor whose real,
attributed work validates it against the fixed allowlist and applies
the deterministic cap — not a second creative judgment about *which*
roles are relevant (that stays CEO's call, matching the doc's own
"Typical participants and their lens" framing, which is written from
CEO's strategic vantage). Concretely this means: a real
`agent_runs` row (`scope_type='meeting'`, a new activity label distinct
from `MEETING_ACTIVITY_LABEL`, e.g. "Orchestrator: validating
selection") and a real record of what it approved/rejected and why —
something a meeting's detail page can actually show, the same standard
every other participant already meets — rather than a docstring comment
attributing code to a name nobody sees in the UI. This turns "Orchestrator"
from a metaphor into a second, real, auditable actor, which is what the
spec's plain wording asks for and what the shipped v1 does not do.

**Open question for CTO** (do not resolve here): is Orchestrator's
"real, attributed work" a second LLM invocation (cost/latency: another
~3-8s call added to the already ~2-minute synchronous worst case,
`cto-milestone2b3b-architecture.md` lines 180-194), or a deterministic
code step that still writes a real `agent_runs`/attributed record
without shelling out to `claude --agent orchestrator`? Both are
defensible; the choice changes the timing budget and which allowlist
(if any) needs a new entry. I flag this rather than pick it — it is a
genuine architecture call, not a design one.

### Item 2 — Mid-meeting "Request another agent's perspective"

**Required**: `ExecutiveMeeting.dc.html` lines 72-79 — a distinct
"requested perspective" position-card style (accent border, no dashed/
red treatment) carrying an explicit `"— requested by Alex"` marker
(line 76) next to the participant label. Lines 81-84 — a separate dashed
affordance row ("+" icon, "Request another agent's perspective — e.g.
QA") that triggers the addition. Both appear *after* the six-card
initial grid (lines 45-70) and *before* the agreement/disagreement
section (lines 95-104) — i.e., this is depicted as happening once the
meeting's initial round is already complete, not as part of the
original selection batch.

**Shipped**: nothing. `generate_meetings.render_position_card()` (lines
117-134) takes only `(agent_name, body_text)` — no parameter exists for
a "requested by" marker. The grid in `build_meeting_detail()` (lines
147-161) renders exactly `meeting["participating_agents"]`, the fixed
JSON array `opsdb.create_meeting()` writes once and never mutates
(`create_meeting()` docstring, `opsdb.py` lines 470-489, is explicit
that nothing else touches this after creation). No POST route for
"add a participant" exists in `server.py`.

**What's genuinely ambiguous, for CTO**:
- Where does "requested by \<name\>" live? The mockup's own visual
  distinction (a different card style from every other participant)
  argues this needs a structured field, not a UI-string prefix stuffed
  into `messages.body` — but `messages` has no such column today, and
  `meetings.participating_agents` is a flat name list with no metadata
  slot for "how/when this one joined." CTO needs to pick where this
  attribution is actually stored.
- Is the newly-requested participant's position gathered synchronously
  (another blocking POST against an already-complete meeting) — and if
  so, does CEO's existing synthesis (`agreements`/`disagreements`/
  `unresolved_questions`/`recommendation`) get re-run to account for the
  new position, or does it stand as originally written, with the new
  card simply appended underneath (which is literally what the mockup
  shows — the requested SECURITY card sits below the synthesis-adjacent
  material, not folded back into it)?
- Who is eligible to be requested — any of the 7 non-CEO allowlisted
  roles, or specifically ones the original selection (CEO, and now
  Orchestrator per item 1) did *not* already pick? The system doesn't
  currently track "candidates considered but not selected" as a
  distinct set anywhere.
- Does a manually-requested addition count against
  `MAX_MEETING_PARTICIPANTS = 6`? The mockup's own example shows 6
  grid cards *plus* one requested card — 7 total — which reads as the
  cap applying only to the initial CEO/Orchestrator selection, not to a
  Founder-driven manual add. CTO and Red Team both need to take a
  position on this explicitly; it directly affects the worst-case
  synchronous-request cost/time budget the first pass sized around.

### Item 3 — Meeting-scoped follow-up thread

**Required**: `ExecutiveMeeting.dc.html` lines 86-93 — a "Follow-up"
labeled section with a Founder message bubble and a named participant's
reply bubble ("**CTO:** Yes — cuts it to about 4 days..."), styled
identically to the existing Ask-Agent chat bubbles (violet Founder /
neutral agent), but explicitly meeting-scoped, not the separate
Ask-Agent feature (`messages.scope='agent'`).

**Shipped**: nothing. `meeting_orchestrator._gather_position()` writes
exactly one message per participant (`opsdb.send_message(..., "meeting",
agent_name, ..., to_agent=None, meeting_id=meeting_id)`, lines 106-107)
using `thread_id = f"meeting-{meeting_id}"` — a single shared thread_id
for *every* participant's position in a given meeting. No follow-up
write route exists in `server.py`.

**Schema is already ready, mostly**: `DATA_MODEL.md` lines 102-105
confirm `messages.scope='meeting'` already supports a nullable
`to_agent` ("null = broadcast/founder") — no new column is structurally
required to record a Founder→participant follow-up message or a
participant's reply. This is a real, usable foundation; the gap is
entirely in the write path and thread-scoping convention, not the
schema.

**What's genuinely ambiguous, for CTO**:
- **Thread-id collision.** All six-plus participants' *original*
  positions currently share one `thread_id`
  (`f"meeting-{meeting_id}"`). A follow-up conversation is inherently
  per-participant (the mockup shows one Founder↔CTO exchange, not a
  broadcast). Reusing the same shared `thread_id` for a follow-up would
  mix an individual back-and-forth into the same query result as every
  other participant's one-shot position — `server.py`'s existing
  `_build_transcript()` helper (built for Ask-Agent) already assumes
  one thread_id = one participant's whole conversation. CTO needs a
  distinct thread-id convention per (meeting, participant) follow-up
  — e.g. `f"meeting-{meeting_id}-{agent_name}"` — separate from the
  positions thread, or the position grid and the follow-up thread will
  render from the same noisy query.
- **What context does a reply see?** Does a follow-up invocation get
  only the Founder's new question, or does it need the full meeting
  context (topic, the participant's own original position, others'
  disagreements) re-injected each time — effectively a new
  `invoke_agent()` call per follow-up message, built on a real
  transcript the way Ask-Agent's `_build_transcript()` already works?
  This is a real design decision with real cost/latency implications,
  not obvious from the mockup's one static example.
- **Synchronous mode.** Is a follow-up reply invoked directly from an
  HTTP handler thread (Ask-Agent's pattern: non-blocking semaphore
  acquire, fails fast at capacity) or does it reuse
  `wait_for_slot=True` the way meeting-participant gathering does? Both
  precedents exist in the codebase today for different reasons — CTO
  needs to pick one for this new call site, not inherit one by
  accident.

## 2. Tensions with decisions already shipped in the first pass

These are raised now, before CTO designs around them, not caught after:

- **New POST routes, not an extended `run_meeting()`.** Items 2, 3, and
  5 each imply a new write against an *already-completed* meeting —
  structurally closer to `POST /api/meetings/<id>/decide` (a second,
  later, independently-token-gated write) than to the original
  all-at-once `POST /api/meetings`. Flagging explicitly so CTO doesn't
  try to fold "add one participant" or "retry one participant" into a
  modified `run_meeting()` that still gathers/synthesizes as one
  monolithic flow — that would silently change the "why synchronous"
  latency budget (`cto-milestone2b3b-architecture.md` lines 180-194)
  that was sized around exactly six participants, once.

- **`MAX_MEETING_PARTICIPANTS = 6` and item 2.** As noted in §1, the
  mockup's own example implies a manually-requested addition is *not*
  bounded by the same cap that bounds initial selection (6 cards +
  1 requested = 7). If CTO/Red Team decide the cap should still apply
  end-to-end, the mockup's own depicted scenario becomes impossible at
  a full meeting — a real conflict between the visual spec and the
  already-reviewed concurrency/cost bound, not resolvable by silent
  interpretation.

- **No exclusivity guard on `agent_runs`, and item 5 (retry).** The
  first pass deliberately chose no "one open run per agent" guard for
  meeting-participant runs (`cto-milestone2b3b-architecture.md` lines
  130-136) — a considered omission, reasoned around two *different*
  meetings legitimately needing the same agent concurrently. Retry
  introduces a new case that reasoning didn't cover: the *same* agent,
  the *same* meeting, invoked a second time after the first attempt's
  row is already `ended_at`-set with `status='failed'`. Nothing in the
  no-exclusivity-guard design prevents a double-click on "Retry" from
  starting two overlapping retry invocations for the same
  (meeting, agent) pair — this is exactly the race
  `opsdb.start_ask_agent_run()`'s `BEGIN IMMEDIATE` machinery
  (`opsdb.py` lines 278-329) was built to close for Ask-Agent in 2B3A,
  and the meeting flow never inherited it (by design, for an unrelated
  reason). CTO/Red Team need to decide whether retry needs its own
  narrow exclusivity check (e.g. "no second retry while one is already
  in flight for this agent+meeting"), not assume the first pass's
  reasoning already covers it.

- **`meetings.positions` left unwritten, and the new "requested by"
  attribution.** The first pass's rule — one conversation store
  (`messages`), no duplicated JSON blob — was reasoned around plain
  positions. Item 2 needs to record *how* a position was obtained
  (selected vs. requested, and by whom), which is new structured
  metadata `messages` doesn't carry today and `meetings.positions`
  (deliberately unwritten) wasn't designed to carry either. CTO needs
  to decide where this small piece of new structure lives without
  reopening the "duplicated state" problem the first pass closed.

- **`wait_for_slot` and cost bounds.** A retry (item 5) presumably
  reuses `_gather_position()`'s existing `wait_for_slot=True` path —
  low risk, no new mechanism. But every retry is a fresh, separately
  billed `claude` invocation (`MAX_BUDGET_USD="0.50"` per call,
  `agent_runtime.py` line 85) — the first pass's implicit cost ceiling
  ("at most `MAX_MEETING_PARTICIPANTS` invocations per meeting") no
  longer holds once any participant slot can be paid for more than
  once. Flag for CTO/Red Team: should retry be capped (e.g., once per
  participant per meeting) so a meeting's real worst-case cost stays
  bounded, the same way participant count was originally bounded for
  exactly this reason?

## 3. Explicit scope boundary

Per the Founder's decision this session, only items 1, 2, 3, and 5 from
`founder-conformance-review-milestone2b3b.md` §4 are in scope for
TASK-011. **Item 4** (topic-specific preset decision buttons vs. the
shipped free-text decision field) and **item 6** (a "Round 2" review
round / a fixed lifecycle decision-enum) are **out of scope for this
pass** and are not designed, discussed, or recommended anywhere in this
document. Their status is unchanged from the founder-conformance
review: item 4 remains a disclosed, undecided deviation from the
mockup; item 6 remains unconfirmed as ever having been specified at
all. Both should be revisited only if the Founder explicitly reopens
them in a future round.

## Verdict

Not a conformance pass/fail in the usual sense — this document exists
to hand CTO Architecture a grounded, line-cited account of what each of
the four items actually requires and where the real ambiguity is,
before architecture gets designed around an assumption nobody checked.
None of the four items' open questions above are resolved here by
design — they are Architecture's and, where a real product tradeoff is
involved (the item-2 participant cap in particular), possibly the
Founder's to make, not Design's to pick unilaterally.
