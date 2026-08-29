# Founder-spec conformance review — Phase 2, Milestone 2B3B (TASK-010)

Requested directly by the Founder: Milestone 2B3B is **not** yet
Founder-accepted. This document is a requirement-by-requirement
comparison between what was authorized and what shipped — not a
redesign, and not a decision about what to build next.

## 1. The actual authorizing specification

There is no single dedicated "Founder Master Prompt" file in this
repository — `ops/PROJECT.md` states its own role as that document
("A lightweight, git/markdown-based operating system..."), and the
Founder's own 2B3B kickoff message referred to `ops/PROJECT.md` as "the
original Founder Master Prompt... already preserved in this repository."
Confirmed: no `FOUNDER_PROMPT.md`/`MASTER_PROMPT.md` file exists (checked
by glob across the repo).

The Founder's verbatim 2B3B-authorizing message (this session, prior
turn) said:

> Proceed to Phase 2 Milestone 2B3B — Real Executive Meetings. ... Then
> implement the Real Executive Meetings milestone **as previously
> specified**.

"As previously specified" points to the one pre-existing design document
for this feature, named explicitly in `ops/PROJECT.md`'s own file index:
`ops/EXECUTIVE_MEETINGS.md` — "multi-agent discussion capability design
(Phase 2, not built yet)." The Founder message did not itself restate or
redefine the feature's requirements; it deferred to that document.

`ops/EXECUTIVE_MEETINGS.md` in turn names its own visual reference: "This
exact shape is what the 'Executive Discussion' element in at least one
Phase 0 mockup depicts" — that mockup is
`ops/mockups/control-center-phase-0/ExecutiveMeeting.dc.html`, part of
the approved-direction mockup set (`ROADMAP.md`: "The approved
refined-dark Command Center direction... remains the visual source of
truth"; `DECISIONS.md` DEC-001/DEC-002 approved the Command Center
structure and dark style at that level).

So the authorizing specification, in order of precedence per the
Founder's own instruction (Founder instruction > lower-level CTO scope
decision, absent explicit Founder approval of a change) is:

1. The Founder's 2B3B kickoff message (this session) — process/workflow
   requirements, does not itself redefine feature scope.
2. `ops/EXECUTIVE_MEETINGS.md` — the substantive feature specification.
3. `ExecutiveMeeting.dc.html` — the approved-direction visual reference
   `EXECUTIVE_MEETINGS.md` itself points to.
4. `ops/reviews/cto-milestone2b3b-architecture.md` — CTO's *interpretation*
   of (2) and (3), including three scope-reduction decisions it made
   itself, without a documented round-trip to the Founder for those three
   specific reductions.
5. Shipped functionality (this milestone's actual code).

## 2. Requirement-by-requirement conformance matrix

| # | Requirement | Source | Classification | Evidence |
|---|---|---|---|---|
| 1 | Founder raises a question, free text | EXECUTIVE_MEETINGS.md §1 | **IMPLEMENTED AS REQUIRED** | `POST /api/meetings`, `topic` field, `meeting_orchestrator.run_meeting()` |
| 2 | **Orchestrator + CEO Agent** jointly select participants | EXECUTIVE_MEETINGS.md §2 ("Orchestrator + CEO Agent select participants") | **IMPLEMENTED DIFFERENTLY — NO FOUNDER APPROVAL FOUND** | `meeting_orchestrator._select_participants()` invokes only `ceo`. No `orchestrator` agent identity is invoked anywhere in the meeting flow. The *enforcement* half (fixed candidate list, deterministic cap) exists in code, but that is validation logic, not a second judging participant named "Orchestrator" per the spec's own wording. CTO's architecture proposal (`cto-milestone2b3b-architecture.md`) resolved this as "genuinely CEO-driven selection" without flagging that the spec names two actors, not one, and without a recorded Founder round-trip on that specific point. |
| 3 | Only agents with real relevant expertise join, not every agent every time | EXECUTIVE_MEETINGS.md §2 | **IMPLEMENTED AS REQUIRED** | Live-verified: a rate-limiting topic selected `product, cto, security, qa, red-team`; a marketing-spend topic selected `financial, marketing, red-team` only — not all 8 every time. |
| 4 | Typical participant set: CEO, Product, CTO, Financial, Marketing, QA, Security, Red Team, each contributing their own named lens | EXECUTIVE_MEETINGS.md §2 (explicit list) | **IMPLEMENTED AS REQUIRED** | `MEETING_PARTICIPANT_ALLOWLIST = ("ceo","product","cto","financial","marketing","qa","security","red-team")` — exact match, all 8. |
| 5 | QA, Security, Red Team are intended as **ordinary meeting participants**, not only review-gate agents | EXECUTIVE_MEETINGS.md §2 (all three named with a described discussion lens, not a review-gate role) | **IMPLEMENTED AS REQUIRED** | All three are in the allowlist and were live-invoked as ordinary participants (e.g. QA gave a real position in the live 6-participant test: "I haven't been able to run a direct-call repro against rate limiting yet..."). |
| 6 | Each participant states its position independently, from its own responsibilities/frameworks, with evidence/assumptions stated, not left implicit | EXECUTIVE_MEETINGS.md §3 | **IMPLEMENTED AS REQUIRED** | Real, concurrent `invoke_agent()` calls — no participant's prompt includes another's answer. QA live-verified genuine independence (participants ran concurrently, not sequentially with visibility into each other). "Evidence/assumptions stated" is prompted for but not structurally enforced beyond what each agent's own real response contains — this is a soft requirement the model output itself satisfies or doesn't; not something code can force. |
| 7 | The record preserves, per meeting: each agent's position, evidence/assumptions, agreements, disagreements, unresolved questions, and a CEO-synthesized (not voted) recommendation | EXECUTIVE_MEETINGS.md §4, DATA_MODEL.md `meetings` table | **IMPLEMENTED AS REQUIRED** | Positions in `messages` (scope='meeting'); agreements/disagreements/unresolved_questions/recommendation columns on `meetings`, populated by a real CEO synthesis call, never averaged/voted. |
| 8 | Founder decides; the meeting produces a recommendation, never a binding decision; for an important question the decision is written to `DECISIONS.md` via the `decisions` table, linked to the meeting | EXECUTIVE_MEETINGS.md §5 | **IMPLEMENTED AS REQUIRED** | `decide_meeting()` — separate Founder-only write, atomically linked (`meetings.linked_decision_id` → `decisions.id`); `recommendation` is never auto-applied to `founder_decision`. |
| 9 | Not a vote; disagreement preserved and shown, not resolved by majority | EXECUTIVE_MEETINGS.md "What this is not" | **IMPLEMENTED AS REQUIRED** | No vote-counting/averaging code exists anywhere in `meeting_orchestrator.py`; `disagreements` is a free-text CEO output, rendered honestly including "Not available" if absent. |
| 10 | Not a way to bypass a review gate | EXECUTIVE_MEETINGS.md "What this is not" | **IMPLEMENTED AS REQUIRED** | A meeting recommendation carries no code path that skips Red Team/Code Review/QA/Security for any resulting work — meetings are advisory only, no automation attaches to a recommendation. |
| 11 | Mid-meeting **"Request another agent's perspective"** affordance | `ExecutiveMeeting.dc.html` line 81-84 (explicit UI element in the approved-direction mockup) | **INTENTIONALLY DEFERRED — NO FOUNDER APPROVAL FOUND** | CTO's proposal explicitly defers this ("Design Conformance... routed... mid-meeting perspective request... deferral"), Red Team affirmed the *proposal*, but neither is a recorded Founder decision — no `DECISIONS.md`/`decisions` table entry, no explicit Founder message accepting this specific reduction. |
| 12 | **Follow-up thread** with a specific participant, scoped to the meeting | `ExecutiveMeeting.dc.html` lines 86-93 (explicit UI element, shown mid-document with a real CTO reply) | **INTENTIONALLY DEFERRED — NO FOUNDER APPROVAL FOUND** | Same as #11 — deferred by CTO's own proposal, affirmed by Red Team, never put to the Founder as a specific yes/no. |
| 13 | Meeting-scoped follow-up (distinct from unrelated Ask-Agent chat) | Implied by #12 (the mockup's follow-up is meeting-scoped, not a redirect to the separate Ask-Agent feature) | **MISSING** (consequence of #12) | No code path exists for this at all, scoped or otherwise. |
| 14 | Founder decision as **preset options specific to the topic** (mockup shows 3 dynamically-worded buttons, e.g. "Import-only, in MVP" / "Defer to v1.1" / "Gather more signal first"), not raw free text | `ExecutiveMeeting.dc.html` lines 107-118 | **IMPLEMENTED DIFFERENTLY — NO FOUNDER APPROVAL FOUND** | CTO's proposal chose free-text decision input over presets ("Design Conformance... preset-buttons vs free-text decision... resolved to free text"), Red Team affirmed the *proposal*, but this is a visible deviation from the approved mockup's own depicted UI, never put to the Founder as a specific yes/no. |
| 15 | A fixed lifecycle enum (APPROVE/PROCEED, REJECT, DEFER, REQUEST MORE ANALYSIS, CLOSE WITHOUT DECISION) | *(asked to verify — not found anywhere)* | **NOT ACTUALLY REQUIRED** | Neither `EXECUTIVE_MEETINGS.md` nor the mockup specifies this exact enum. The mockup's buttons are topic-specific ad hoc labels (see #14), a different concept from a fixed universal enum. No other repository document defines such an enum for meetings. If the Founder intended this from a source not yet in the repository, that source needs to be identified — flagged as a genuine open question, not assumed absent. |
| 16 | Founder ability to leave a meeting open, without deciding | Not explicit in EXECUTIVE_MEETINGS.md; implied by "the meeting produces a recommendation, never a binding decision" | **IMPLEMENTED AS REQUIRED** (passively) | Nothing forces a decision — a meeting with `founder_decision IS NULL` renders as "Open" indefinitely (`generate_meetings.py`'s pill state) — this is already true by omission, not by a deliberate "Close without decision" action, which does not exist as its own affordance. |
| 17 | Retry of a failed participant | Not specified anywhere in EXECUTIVE_MEETINGS.md or the mockup | **NOT ACTUALLY REQUIRED** per repository evidence, but flagged for Founder attention — see §4 | Live-demonstrated during QA: a real CEO invocation failure during the milestone's own live testing left that meeting with **no CEO position and no synthesis, permanently** — there is no retry mechanism, manual or automatic. Not a spec violation, but a real, observed design gap worth the Founder's awareness. |
| 18 | Crash/restart or partial-meeting recovery | Not specified in EXECUTIVE_MEETINGS.md; **is** an established pattern this project already built for the analogous Ask-Agent feature (2B2/2B3A: `_reconcile_orphaned_ask_agent_runs()`) | **MISSING — OBJECTIVE DEFECT, IN SCOPE, NO FOUNDER APPROVAL NEEDED TO FIX** | Confirmed by direct code read: `server.py`'s startup reconciliation calls `opsdb.reconcile_orphaned_runs(conn, agent_runtime.ASK_AGENT_ACTIVITY_LIKE, ...)` only — `agent_runtime.MEETING_ACTIVITY_LIKE` is never passed anywhere. A server crash mid-meeting leaves that participant's `agent_runs` row open (`ended_at IS NULL`) **forever**, corrupting that agent's derived "Working"/"Available" status permanently. Never disclosed as this specific gap in any 2B3B review document. Grepped all five: `cto-milestone2b3b-architecture.md` and `red-team-milestone2b3b-architecture.md` have zero mentions of "reconcile"/"orphan" at all; `qa-milestone2b3b.md` has one mention, but it is a different, unrelated claim ("zero orphaned `agent_runs`" observed during a normal, non-crash concurrent-load test — it verifies clean completion, not crash-recovery scope, and does not address startup reconciliation at all); `code-review-milestone2b3b.md` and `cto-milestone2b3b-post-implementation.md` have zero mentions. No document anywhere disclosed that startup reconciliation is scoped to Ask-Agent runs only. This is a drift CTO's own post-implementation conformance review should have caught and did not. **Corrected in this pass — see §3.** |
| 19 | 5-other-participants-max / 3-concurrent-invocation behavior | 2B3A's own already-approved `MAX_CONCURRENT_INVOCATIONS=3`; 2B3B's own Red Team-affirmed `MAX_MEETING_PARTICIPANTS=6` | **IMPLEMENTED AS REQUIRED** | Not a 2B3B-specific deviation — reuses prior, already-reviewed limits consistently. |
| 20 | Genuine Round 1 independence, no fake consensus, Founder remains final authority | EXECUTIVE_MEETINGS.md throughout | **IMPLEMENTED AS REQUIRED** | Covered by #6, #9, #10 above. |
| 21 | A bounded "Round 2" cross-perspective review round, with disagreement preserved after Round 2 | *(asked to verify — not found anywhere)* | **NOT ACTUALLY REQUIRED** per repository evidence | `EXECUTIVE_MEETINGS.md` describes exactly one round (§3, "Each participant states its position") followed directly by synthesis (§4) and Founder decision (§5) — no second round of cross-perspective review is described in the spec, the mockup, or any other repository document found. This is the same class of item as #15 — flagged, not assumed, in case the Founder has a source not yet in this repository. |

## 3. Objective defect corrected in this pass (no Founder approval needed — engineering gap, not a scope decision)

**Item #18 — meeting-scoped `agent_runs` are never reconciled after a
server crash/restart.** This is not a product-scope question; it is the
same category of bug 2B3A's own review process was built specifically to
catch (an established pattern silently not extended to a new,
structurally identical case). Per the Founder's Correction Rule, this
routed through the full required workflow before TASK-010 could return
to `DONE`:

- **CTO architecture update**: `ops/reviews/cto-milestone2b3b-correction-architecture.md`
- **Red Team challenge**: `ops/reviews/red-team-milestone2b3b-correction.md`
- **Development**: `server.py`'s startup reconciliation now covers both
  `ASK_AGENT_ACTIVITY_LIKE` and `MEETING_ACTIVITY_LIKE`.
- **Code Review, QA, Security, CTO post-implementation**: see
  `ops/reviews/code-review-milestone2b3b-correction.md`,
  `ops/reviews/qa-milestone2b3b-correction.md`,
  `ops/reviews/security-milestone2b3b-correction.md`,
  `ops/reviews/cto-milestone2b3b-post-correction.md`.

## 4. Items requiring an explicit Founder decision — NOT implemented in this pass

Per the Founder's own Correction Rule ("If true ambiguity exists...
STOP and present the conflict to Founder. Do not choose whichever
specification is easier to implement."), the following are **not**
implemented, corrected, or reduced further in this pass. They are
presented for an explicit Founder decision:

1. **Participant selection: CEO-only (shipped) vs. Orchestrator + CEO
   jointly (spec's literal wording).** Options: (a) accept CEO-only as
   the Founder-approved interpretation going forward — this would be the
   first explicit Founder sign-off on that specific reduction; (b) add a
   deterministic Orchestrator-owned validation/bounding step as a
   distinct, attributed actor in the flow (not just unlabeled code); (c)
   something else the Founder specifies.
2. **Mid-meeting "request another perspective."** Options: (a) accept as
   deferred indefinitely; (b) authorize it as a follow-up milestone; (c)
   require it before 2B3B can be considered complete.
3. **Meeting-scoped follow-up thread with a specific participant.** Same
   three options as #2.
4. **Free-text Founder decision (shipped) vs. topic-specific preset
   buttons (mockup).** Options: (a) accept free text as sufficient — it
   is strictly more expressive, just not what the mockup visually shows;
   (b) require CEO to also propose 2-3 topic-specific preset options
   alongside free text, matching the mockup exactly; (c) something else.
5. **Retry of a failed participant invocation.** Not a spec violation,
   but real live testing this pass showed a permanent, unrecoverable
   loss when a single real invocation fails transiently. Options: (a)
   accept this as a disclosed v1 limitation (a Founder can always raise
   the question again as a brand-new meeting); (b) authorize a manual
   "retry this participant" affordance as a follow-up; (c) something
   else.
6. **The "Round 2" / fixed decision-enum items (#15, #21).** No evidence
   found in this repository that either was ever specified. If the
   Founder has a source not currently in the repository (a message
   outside this session, a document not yet committed), please point to
   it — otherwise these are treated as not required.

None of the above six items block TASK-010's engineering completeness —
the objective defect (§3) is the only thing that was blocking a return
to `DONE`. They block **full Founder acceptance** of 2B3B's scope as
originally specified, per the Correction Rule.
