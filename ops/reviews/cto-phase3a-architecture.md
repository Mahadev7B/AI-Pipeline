# CTO architecture proposal — Phase 3A

TASK-015: "Chief of Staff Founder Interface + Limited Automated
Orchestration." Authorized by the Founder's Phase 3A directive (verbatim
quoted in the task; accepted head for this proposal: the current branch,
which is Phase 2 complete through TASK-014/Milestone 2B5). Do not
implement — this is the proposal Security's threat model and Red Team
review before Development builds it, per the Founder's stated gate
sequence: CTO Architecture -> Security Threat Model -> Red Team ->
Development -> Code Review -> QA -> Security Adversarial Review -> CTO
Post-Implementation Conformance.

**Scope discipline, stated up front**: `risks.id=3` ("Bash permissions
cannot be scoped below the tool-category level") is not resolved,
narrowed, or reduced by anything in this document. Where Phase 3A's own
automation increases that risk's practical consequence — per the
Founder's explicit instruction to examine this — that is called out
directly, not minimized. No mockup exists for Phase 3A, and the
Founder's own stated gate sequence for this milestone omits
MOCKUP/MOCKUP_REVIEW entirely — this document is written accordingly: it
deliberately reuses existing, already-approved UI patterns (the
agent-detail chat form, the approvals-style action button) rather than
inventing new visual/UX surfaces, which stays within the CTO's proper
scope (architecture, not design) and avoids architecting ahead of an
approved mockup for anything genuinely new-looking. If the Founder wants
a more prominent, purpose-built "talk to your Chief of Staff" surface
later, that is a Design/Product-owned mockup for a follow-up round, not
something decided here.

## Verified facts this design is built on

Confirmed by reading the actual code/docs before writing anything below,
not assumed:

- `ops/control-center/agent_runtime.py`'s `invoke_agent()` is the only
  function that turns an agent identity + a transcript into a real model
  response. Every existing call site — Ask-Agent, every Executive
  Meeting participant/selection/synthesis call — invokes with
  `--tools ""` and `--strict-mcp-config`: zero built-in tools, zero MCP
  servers, always, no exceptions, no parameter to request more. This has
  held since Milestone 2B2.
- `.claude/agents/code-review.md` / `ops/agents/code-review.md` describe
  Code Review's *normal* tools as repo filesystem read, the `code-review`
  skill, and `git diff` — real repository access a zero-tool invocation
  cannot provide natively.
- `ops/control-center/server.py` runs `http.server.ThreadingHTTPServer` —
  one process, request-scoped SQLite connections, **no existing
  background thread, poller, or scheduler of any kind**. There is no
  precedent anywhere in this codebase for "something happens without a
  browser request triggering it."
- `ops/control-center/founder_auth.py` + the Milestone 2B4 session system
  is the one authorization boundary (`_authenticated_session()` +
  `_require_csrf_token()`, both applied in `do_GET()`/`do_POST()`). Every
  route added below reuses it; nothing here introduces a second gate.
- `messages` already supports `scope='agent'` threads
  (`thread_id = f"agent-{name}-company"`); `agent_runtime.ASK_AGENT_ALLOWLIST`
  does **not** include `orchestrator` today — `orchestrator` has never
  been the subject of a real `claude --agent orchestrator` invocation in
  this system's history. `ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL`'s own
  docstring is explicit that Orchestrator's participant-validation step
  is "a deterministic Python step, never a `claude --agent orchestrator`
  invocation" — this project already draws exactly the distinction Phase
  3A needs between "Chief of Staff as a role attribution on a Python
  step" and "Chief of Staff as a real model turn."
- `opsdb.py` is the sole DB writer, stdlib-only, zero third-party
  dependencies. `dbutil.connect()` (used by every `generate_*.py` page
  renderer) opens the database `mode=ro` at the SQLite/OS level — a
  read-only connection cannot write even by accident. Every write in this
  codebase goes through `opsdb.connect()` plus an `opsdb.py` function.
  Confirmed both files directly.
- `risks` table, confirmed live: id=1 `mitigated`, id=2 `mitigated`
  (Milestone 2B4), id=3 `open` — "Bash permissions cannot be scoped below
  the tool-category level," unchanged, `owner_agent=cto`.
- `tasks.status` includes `CODE_REVIEW` as a real enum value (confirmed
  in `ops/db/schema.sql`'s `CHECK` constraint); `AGENT_STATUS.md`
  confirms the pipeline `IN_DEVELOPMENT → CODE_REVIEW → QA` and "Failed
  QA returns the task to `IN_DEVELOPMENT`... A significant fix must go
  through `CODE_REVIEW` again." A `task_status_history` row with
  `to_status='CODE_REVIEW'` is the real, existing, single-source-of-truth
  signal for "a task entered Code Review" — confirmed by reading
  `cmd_task_status()`: every status change writes exactly one such row,
  unconditionally, and nothing else in the schema records this fact.
- `opsdb.py`'s write functions follow one consistent shape throughout —
  a plain, directly-callable, `conn`-taking function (`decide_approval()`,
  `start_run()`, `end_run()`, `send_message()`, `record_decision()`,
  `reconcile_orphaned_runs()`) plus a thin `cmd_*` CLI wrapper around it.
  **`cmd_review_result` is the one write path that does not yet follow
  this shape** — it operates directly on `args: argparse.Namespace` with
  no plain function underneath. This needs a small refactor (§B.6, files
  list) for Phase 3A's automation to call it the same way every other
  in-process caller in this codebase already calls a write — never a
  subprocess shelling out to `opsdb.py` itself, which would be new,
  unjustified indirection for an in-process caller (`meeting_orchestrator.py`
  already establishes the precedent: import `opsdb`, call its functions
  directly).
- `agent_runtime.RuntimeResult.cost_usd` is computed on every invocation
  (`data.get("total_cost_usd")`) but **is never persisted anywhere** —
  confirmed by grep; no caller in `server.py` or `meeting_orchestrator.py`
  writes it to any table. This is a real, pre-existing gap Phase 3A's
  spend-guard control must close for automation's own invocations (it
  does not need to retroactively fix every other invocation path — that
  would be its own, separate decision, out of scope here).
- `ops/PROJECT.md`'s Founder approval rules and `ops/agents/orchestrator.md` /
  `.claude/agents/orchestrator.md` confirm the Chief of Staff's authority
  boundary the Founder's directive restates: workflow-management only;
  cannot write/approve code, perform QA, override Code Review/Security,
  or make a Founder-only decision. Nothing in this design changes that —
  every new capability below is either (a) a real-but-bounded
  conversational answer, (b) a Python-only mechanical routing/bookkeeping
  step attributed to `orchestrator` (same category as the existing
  `ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL` precedent), or (c) a
  Code-Review verdict recorded by `code-review`, never by `orchestrator`
  itself.

---

# PART A — Chief of Staff Founder Interface

## A.1 Route and invocation mechanism

**New, dedicated route: `POST /api/chief-of-staff/ask`.** Not a
generalization of `/api/agents/<name>/ask`, and `orchestrator` is **not**
added to `ASK_AGENT_ALLOWLIST`. Reasoning:

- Ask-Agent's `_build_transcript()` replays the `messages` thread
  verbatim, nothing more. Part A requires assembling real company state
  into context before every answer (§A.2) — a materially different,
  larger responsibility that deserves its own code path, not a silent
  behavior change bolted onto an already-reviewed route depending on
  which agent name happens to be requested.
- Ask-Agent has no concept of gathering other agents' perspectives
  (§A.3). Silently overloading one route to sometimes do a lot more work
  than its name implies, only for one specific agent name, is exactly
  the kind of implicit special-casing this codebase's own conventions
  avoid (see `agent_runtime.py`'s comment on centralizing scoping
  predicates after Code Review flagged copy-pasted logic as a root
  cause, Milestone 2B2).
- Each invocation category in this system has its own allowlist
  documenting exactly why it exists (`ASK_AGENT_ALLOWLIST`,
  `MEETING_PARTICIPANT_ALLOWLIST`). Chief of Staff conversation is a
  third, distinct category — Founder-typed, not meeting-selected, not
  automation-triggered — and gets its own:

```python
# agent_runtime.py — new constant
CHIEF_OF_STAFF_ALLOWLIST = ("orchestrator",)
CHIEF_OF_STAFF_ACTIVITY_LABEL = "Chief of Staff: answering a Founder question"
CHIEF_OF_STAFF_ACTIVITY_LIKE = "Chief of Staff:%"
```

`invoke_agent()`'s validity check widens from
`if agent_name not in ASK_AGENT_ALLOWLIST and agent_name not in MEETING_PARTICIPANT_ALLOWLIST`
to also accept `CHIEF_OF_STAFF_ALLOWLIST` — the browser still never
influences tool/model/system-prompt flags; it only ever sends a message.
`--tools ""` / `--strict-mcp-config` are unconditional in `_run_claude()`
already — nothing about this route changes that. This is, and must
remain, the first and only real model invocation of the `orchestrator`
identity in this system's history; every other appearance of
`orchestrator` in `agent_runs`/`task_status_history` to date is a
deterministic Python step wearing that identity's name for attribution,
never a subprocess.

**Session/CSRF**: identical to every other write route — `do_POST()`'s
existing dispatch gains one more branch, gated by the same
`_require_csrf_token()` then `_authenticated_session()` checks, in the
same order, before any handler runs. No second boundary.

**Persistence/thread scheme**: reuses the exact existing convention,
unchanged formula — `thread_id = f"agent-{agent_name}-company"` with
`agent_name = "orchestrator"`, `scope='agent'`. This is not a new schema
concept; it is Ask-Agent's own "company/general" thread shape (confirmed
in `DATA_MODEL.md`) applied to a new agent name, which the schema already
supports with zero changes. `opsdb.start_ask_agent_run()` is already
generic over `(agent_name, activity_label, activity_like)` — no signature
change needed; the new handler calls it with the
`CHIEF_OF_STAFF_ACTIVITY_*` constants, giving the Founder<->Chief-of-Staff
conversation the same "one open exchange at a time" atomicity guard
Ask-Agent already has, and the same orphan-reconciliation coverage once
its LIKE pattern is added to `_reconcile_orphaned_runs()` (§ files list).

**UI surface**: `/agents/orchestrator.html` (the existing agent-detail
page, already rendered for every agent) gains a chat form — visually the
same component Ask-Agent-allowlisted agents already render, so no new
visual pattern is invented. Its form `action` is
`/api/chief-of-staff/ask`, not `/api/agents/orchestrator/ask` (that route
still 404s for `orchestrator` — it stays out of
`ASK_AGENT_ALLOWLIST` — so there is exactly one way to talk to the Chief
of Staff, not two). The thread display itself needs no new code: it
already reads `messages WHERE thread_id = ?` for whatever agent's page is
open, and `agent-orchestrator-company` follows the identical naming
formula.

## A.2 Assembling real company state into context — never "everything, always"

**New module: `ops/control-center/chief_of_staff.py`** (mirrors
`meeting_orchestrator.py`'s separation from `server.py` — pure
orchestration glue, imports `opsdb`/`agent_runtime`/`derived_state`,
never touches `sqlite3` directly except through `opsdb.py` functions,
never invokes the runtime except through `agent_runtime.invoke_agent()`).

Before every single Founder message is sent to the model, this module
assembles a **state digest** — a deterministic, bounded block of text,
built fresh on every turn (never cached across turns, so staleness
within one conversation is structurally impossible: whatever the digest
says is true as of the millisecond this specific call was made). New
read-only helper functions live in `ops/db/derived_state.py` (the
existing, explicitly-designated home for "the single, shared
implementation of every deterministic-state formula," already imported
by both `report.py` and `generate_overview.py` — Phase 3A's digest
follows the same DRY rule, not a second hand-typed copy of company
health/agent-status logic):

- `company_health(conn)` — reused verbatim, unchanged.
- `agent_status_rows(conn)` — reused verbatim, unchanged.
- New: `open_risks_digest(conn, limit=10)` — id/title/severity/status/
  mitigation for open + recently-changed risks.
- New: `active_tasks_digest(conn, limit=15)` — id/title/status/
  current_owner/blockers for tasks not in `DONE`, most-recently-updated
  first.
- New: `pending_approvals_digest(conn, limit=10)` — `decision IN
  ('pending','discuss')` rows.
- New: `recent_decisions_digest(conn, limit=10)`,
  `recent_status_transitions_digest(conn, limit=20)`,
  `recent_review_qa_digest(conn, limit=10)`,
  `recent_deployments_digest(conn, limit=5)`.
- New: `automation_status_digest(conn)` — reads `automation_state` +
  any `automation_events` with `status='running'` + the most recent N
  terminal ones (§B.9's single source of truth, reused here so Part A's
  "what is running right now" answers and Part B's `/automation.html`
  page read the *same* query, matching this codebase's own established
  rule that two screens showing the same fact must read one query layer,
  never two hand-typed copies — `ARCHITECTURE.md`, "Derived UI state must
  be deterministic").

Each section is capped (`limit=` above) and each section's rendered text
is truncated to a fixed character budget; the whole digest is capped at
`MAX_STATE_DIGEST_CHARS = 6_000` (a new module constant in
`chief_of_staff.py`, same "one disclosed number, not a vibe" convention
as `MAX_ASK_MESSAGE_CHARS`/`MAX_RESPONSE_CHARS`). This is a deliberate,
justified content-selection strategy, not "everything, always": recent +
open + actionable state, not the full historical row count of every
table. If the Founder asks about something outside this window (an old,
resolved risk from months ago, say), the persona instructions (§A.4)
require the model to say plainly that it doesn't have that in view rather
than guess — the digest's own boundedness is what makes "say you don't
know" an honest, achievable instruction instead of wishful thinking.

The digest is prepended to the transcript as a clearly labeled block
(e.g. `CURRENT COMPANY STATE (as of <ISO timestamp>):\n...`), followed by
the persisted `agent-orchestrator-company` thread's prior turns
(read the same way `_build_transcript()` already reads Ask-Agent's
thread — reused directly, not reimplemented), followed by the Founder's
new message. The persona (§A.4) is instructed to treat the state block as
authoritative over anything it said in an earlier turn of this same
thread, and to say so explicitly when its answer differs from what it
said before because the state has since changed — this is the concrete
mechanism satisfying the Founder's "must recognize when stored
information is stale" requirement; it works by construction (fresh
digest, every turn) rather than by asking the model to somehow detect
staleness in something it's never shown twice.

## A.3 "Ask CTO and Financial what they think" — reusing Executive Meetings, not reinventing them

**Decision: this reuses `meeting_orchestrator.py`'s existing
concurrent-gathering machinery via one new, narrow wrapper function,
not a second orchestration system.**

**How intent crosses from natural language to a deterministic action**:
the Chief of Staff's own persona (§A.4) is instructed that when a
Founder message asks it to consult specific other agents, its reply
should end with one fixed-format line:
`CONSULT: <comma-separated role names>` (omitted entirely when no
consultation is needed — which is the common case). This is the exact
same trust pattern `meeting_orchestrator._select_participants()` /
`_parse_selection()` already use for CEO's participant nomination: the
model's output is *never* trusted as an instruction to execute — it is
parsed leniently (case-insensitive, word-boundary regex, matched only
against the fixed candidate list) by deterministic Python, which alone
decides whether and how to act. A Founder message (or a prompt-injected
one) cannot make the Chief of Staff itself execute anything; it can only
produce text that Python may or may not act on, identical in kind to
every other model output already trusted this way in this codebase.

`chief_of_staff.py` parses `CONSULT:` out of the model's raw reply
before anything is persisted or shown — the Founder never sees the raw
control line. Candidates are filtered to
`agent_runtime.MEETING_PARTICIPANT_ALLOWLIST` minus `ceo`/`orchestrator`
(CEO is always eligible for consultation too — allowed through
unchanged, same list) and deduplicated/capped exactly the way
`_validate_selection()` already caps CEO's own nomination — that
dedup+cap logic is extracted into a small shared helper (`_cap_participants()`
or equivalent) callable from both call sites, so there is exactly one
implementation of "at most `MAX_MEETING_PARTICIPANTS - 1` others,
deduped" in the codebase, not two.

**New, narrow addition to `meeting_orchestrator.py`**: `run_meeting()`'s
existing body (CEO selects -> Orchestrator validates -> gather
concurrently -> CEO synthesizes) is **not** rewritten. Its "gather
concurrently, bounded by `MAX_CONCURRENT_INVOCATIONS`, then have CEO
synthesize" middle section is extracted into an internal helper (e.g.
`_gather_and_synthesize(meeting_id, participants, topic)`) that
`run_meeting()` calls, unchanged in behavior, after its own
CEO-selection/Orchestrator-validation steps. A new, thin sibling function,
`run_consult_meeting(topic, participants, initiated_by="founder")`, skips
CEO-driven selection entirely (the Founder, via the Chief of Staff,
already named the participants — running a second CEO "who should
attend" call on top would waste a real invocation and could select
*different* agents than the Founder explicitly asked for) and calls the
same extracted helper directly with the Chief-of-Staff-parsed,
already-capped participant list. Everything downstream — the real
`meetings` row, `MAX_MEETING_PARTICIPANTS`/`MAX_CONCURRENT_INVOCATIONS`
bounds, the `$0.50`-capped concurrent gathers, CEO's own real synthesis
call, the full `meetings.html`/`meetings/<id>.html` audit trail — is
100% the existing, already-reviewed mechanism, unchanged. This is a real
Executive Meeting, not a meeting-shaped imitation: it shows up on
`/meetings.html` exactly like a Founder-initiated one, `initiated_by`
recorded as `"founder"` (the same string this schema already uses for
every Founder-attributed write where there is no per-person identity —
`DATA_MODEL.md` already documents this convention).

**Why the Chief of Staff still does its own synthesis on top, not just
CEO's**: the meeting's own `finalize_meeting_synthesis()` output (CEO's
agreements/disagreements/unresolved/recommendation) is real and
persisted, but it is written in CEO's voice for CEO's own synthesis
role — not in the plain-English, Founder-addressed, recommendation-first
style §A.4 requires for *every* Chief of Staff reply. Once the consult
meeting completes, `chief_of_staff.py` reads the real, persisted
`meetings`/`messages(scope='meeting')` rows (the same data anyone
browsing `/meetings/<id>.html` sees) and makes a **second** Chief of
Staff invocation whose transcript includes those real gathered
positions plus CEO's synthesis, and asks it to narrate a final,
Founder-addressed answer in its own voice, per the Founder's own example
("Product likes X, CTO says Y... my recommendation is..."). This second
turn's reply is what gets persisted to `agent-orchestrator-company` and
shown to the Founder as the answer to their question — the underlying
per-agent positions and any disagreement are never lost; they live in
the real meeting record, linked by a plain-text reference in the
Chief of Staff's reply (e.g. "(see Meeting #12)"), satisfying "preserve
the underlying agent positions and disagreements in the audit history"
without inventing a second storage mechanism for them.

**Disclosed UX consequence**: because `run_consult_meeting()` reuses the
existing fully-synchronous meeting flow, a consult-triggering chat
message can genuinely take the same tens-of-seconds-to-low-minutes a
today's `POST /api/meetings` already legitimately takes — this is not a
new limitation, it is the same accepted behavior Milestone 2B3B already
shipped and Milestone 2B3A's threading already makes safe (other pages
stay responsive; only this one request is slow).

**Disclosed worst-case cost, stated once, closed-form, per this
project's own convention** (`agent_runtime.py`'s existing ~20-invocation
comment): one consult-triggering Founder question can cost up to 1
(Chief of Staff's first reply, which already contains the answer or the
`CONSULT:` line — no separate "interpret intent" call) + up to 5
(`MAX_MEETING_PARTICIPANTS - 1` gathered positions) + 1 (CEO's real
synthesis call) + 1 (Chief of Staff's final narrated answer) = **8 real,
`$0.50`-capped invocations, ~$4.00 worst case**, on top of whatever a
non-consulting question already costs (1 invocation, ~$0.50). This must
be disclosed in `ops/SECURITY.md`'s Phase 3A section alongside the
existing meeting-cost disclosure, not left implicit.

## A.4 Plain-English persona — a durable instruction, not a per-call prompt trick

Lives in both `.claude/agents/orchestrator.md` (the front matter/body a
real `claude --agent orchestrator` invocation actually reads) and
`ops/agents/orchestrator.md` (the durable role-doc mirror), consistent
with how every other agent's communication style is already encoded in
its own persona doc, not injected ad hoc by the calling code. New
content, in both files, in substance (Development finalizes exact
wording):

- Plain English first; short and conversational unless the Founder asks
  for detail; translate any necessary jargon immediately, using a
  company/office/worker/factory/traffic/lock-key/physical-world analogy
  when it genuinely clarifies (the Founder's own three worked examples —
  idempotency, orphaned runs, `risks.id=3` — are the calibration bar).
- Structure: **WHAT HAPPENED / WHY IT MATTERS / MY RECOMMENDATION / WHAT
  I NEED FROM YOU** — the last section present only when a real
  Founder-only decision is actually required; state plainly when none is
  needed rather than manufacturing one.
- Make a recommendation when the evidence in the state digest supports
  one — never "here are three options, you decide" as a default
  deflection — while never asserting the recommendation *is* the
  decision: the Founder-only decision boundary (`ops/PROJECT.md`,
  "Founder approval rules") is unchanged; the Chief of Staff recommends,
  it does not decide, approve, or execute.
- When asked to consult other agents: end the reply with
  `CONSULT: <names>` per §A.3 — a hard format requirement, since
  Python's parser depends on it; the persona doc states the exact
  format and the exact allowed candidate names (mirrors
  `_select_participants()`'s own prompt, which already states its
  candidate list and required output format explicitly to CEO).
- Never fabricate state or memory; if the state digest doesn't cover
  what's asked, say so plainly rather than guessing.
- Do not treat a chat instruction (e.g. "stop it," "approve this") as an
  executable command — those remain explicit, separately-gated Founder
  actions (§B.9's kill switch, the existing approvals form) that the
  Chief of Staff can explain and point to, never trigger itself. This is
  a durable persona instruction *and* an architectural fact (§A.1, §B.9):
  the Chief of Staff's own invocation has no tool that could execute a
  write even if it tried — this instruction is defense in depth on top
  of that structural fact, not the only thing preventing it.

## A.5 Auditability

- Every Founder message and every Chief of Staff reply — including the
  final narrated answer after a consult — is a real `messages` row on
  `agent-orchestrator-company`, `scope='agent'`, exactly like every other
  persisted conversation in this system. No new table.
- A consult's underlying per-agent positions, evidence, and any
  disagreement are the real, existing `meetings`/`messages(scope='meeting')`
  rows the reused Executive Meeting machinery already writes — nothing
  new to build for this, only to read.
- Nothing beyond the model's own final `result` text is ever persisted —
  identical to every existing invocation path (`--output-format json`
  never surfaces internal reasoning tokens to this system); there is no
  hidden-chain-of-thought log to accidentally create, and this design
  adds none.
- `agent_runs` rows (via `start_ask_agent_run()`/`end_run()`, reused
  unchanged) give every Chief of Staff turn — and every consult's
  meeting-participant gather, via the existing meeting machinery — the
  same real, queryable "who was Working/Waiting and for how long" record
  every other agent already has, via `derived_state.agent_status_rows()`,
  unchanged.

---

# PART B — Limited Automated Orchestration

## B.1 The central decision: how the automated Code Review invocation gets real repository content

**Decision: zero-tool invocation (`--tools ""`, `--strict-mcp-config`,
unchanged from every existing invocation), with the diff and file
content assembled by deterministic Python and fed directly into the
transcript — never real Bash/Read/Grep tool grants for an unsupervised
invocation.** This is the single most consequential decision in this
document and is deliberately not sidestepped.

**Why this is viable, not a token gesture** — reasoning through the
actual content, not just asserting "safer":

Code Review's real job (`ops/agents/code-review.md`): correctness,
maintainability, architecture consistency, readability, error handling,
dependency usage, security, test coverage, complexity, unnecessary
refactoring — judged against a diff, the approved architecture, and the
task's acceptance criteria. All of that is judgeable from *content*, not
from the *ability to go exploring* — a human reviewer looking at a GitHub
pull request diff, with the ability to click into full changed files for
surrounding context, is doing essentially the same task with essentially
the same information; they are not routinely grepping the entire
repository for every review. Deterministic Python (running inside the
already-trusted, already-reviewed `automation.py` poller — see §B.2 —
not inside any LLM invocation) can assemble a transcript containing:

- the task's `title`, `business_goal`, `acceptance_criteria`,
  `architecture_notes`, `tests_required` (from `tasks`);
- the Developer's actual structured handoff record — `work_completed`,
  `files_changed`, `tests_added`, `expected_behavior`,
  `known_limitations` (from `handoffs`) — Code Review's own frameworks
  section already treats a handoff as real input, not an incidental one;
- a real `git diff` between two explicit commits (§B.7 — a new,
  explicit `handoffs.base_commit_sha` / `head_commit_sha` pair, not a
  timestamp heuristic — see rationale there) scoped to exactly the paths
  in `files_changed`;
- the **full final content** of every changed/added file, not diff
  hunks alone — closing the specific gap a bare diff has (limited
  surrounding context) without granting exploratory access;
- `CODING_STANDARDS.md`'s content, verbatim (small, always relevant,
  and exactly what a human-supervised Code Review session already reads
  as part of its normal configuration).

This produces a real, evidence-based transcript a model can genuinely
review and reach a defensible PASS/REJECT verdict from — for the
overwhelmingly common case this project's own rules already select for
("Developer... keep changes small," `ops/agents/developer.md`). It is
**not** equivalent to a human-supervised Code Review session that can
follow its own curiosity into an unrelated file, check whether a helper
is used inconsistently elsewhere in the repository, or run a test
suite — that is a real, disclosed limitation of the automated mode, not
hidden. See §B.1.1 for exactly how this limitation is disclosed and
bounded.

**Why option (b) — real tool grants for an unsupervised invocation — is
rejected**: it would be the first invocation in this system's history to
run with genuine Bash/filesystem access with no human watching in real
time, under the identical OS-user principal `risks.id=3` already flags
as unscoped. This is precisely the scenario the Founder's own directive
names as the reason `risks.id=3`'s *consequence* increases under
autonomous operation — Phase 3A is explicitly a "limited automation"
milestone, not a mandate to take the single largest step available
toward larger blast radius. Every existing invocation in this codebase's
history — five allowlisted Ask-Agent roles, eight meeting-participant
roles, all of whose *normal* configurations include Bash — has been
deliberately, consistently restricted to zero tools specifically
*because* no human is watching a given call in real time; that
reasoning applies with equal or greater force to an invocation that is
not even triggered by a Founder action, but by a background poller
noticing DB state on its own. Option (a) is not merely "the more
conservative choice that happens to also work" — it is the option this
project's own established, repeatedly-reaffirmed pattern already
predicts, and it produces a real verdict. There is no case for option
(b) that isn't "it would let Code Review explore more" — real, but not
worth the first unsupervised-Bash precedent in this system's history for
a Phase explicitly scoped as limited.

**This is exactly the kind of major, non-reversible-without-review
architecture decision this project records formally** — recommend
Development/whoever runs the CLI after Founder sign-off record it via
`python3 ops/db/opsdb.py decision-record --title "Phase 3A: automated Code
Review invoked zero-tool with Python-assembled diff context, not native
tool grants" ...`, not merely left implicit in this document.

### B.1.1 Disclosing the limitation honestly

The automated Code Review mode is a **distinct, narrower-context mode**
of the same `code-review` agent identity, not "the same Code Review,
automated." `ops/agents/code-review.md` / `.claude/agents/code-review.md`
gain a short, explicit note describing this second mode: what content it
receives (exactly the bullet list above), what it cannot do that a
human-supervised session can (explore beyond the assembled bundle, run
anything, consult files not listed in `files_changed`), and the required
fixed-format output line for this mode specifically:
`VERDICT: PASS` or `VERDICT: REJECT`, followed by findings in the same
free-text shape a human-supervised review already produces — parsed the
same deterministic, label-anchored way `meeting_orchestrator._parse_synthesis()`
already parses CEO's synthesis output. `review_results.reviewed_by_agent`
is recorded as `code-review` either way — same mechanism, same table,
same column, per the Founder's own explicit instruction — but the linked
`automation_events` row (§B.3) is what lets anyone later distinguish "a
human ran this session" from "the automation ran this session" without
touching the shared table's shape at all.

`MAX_REVIEW_TRANSCRIPT_CHARS = 60_000` (new constant, `automation.py`) —
generous for real code content, far above `MAX_ASK_MESSAGE_CHARS`'s 8,000
because this transcript's job is fundamentally larger; graceful,
disclosed truncation (an appended note, and the persisted
`automation_events` row marked `truncated=1`) if exceeded, never silent.
`AUTOMATED_REVIEW_TIMEOUT_S = 120` (new constant, passed as
`invoke_agent()`'s existing `timeout_s` override) — real code review
plausibly needs longer than a short Ask-Agent exchange; this only blocks
the poller's own background thread, never a Founder-facing HTTP request
(GET/read traffic is unaffected either way, per the existing threading
model).

### B.1.2 A new, necessary filesystem-touching surface — and its concrete mitigation

Assembling `git diff`/file content from `handoffs.files_changed` (a JSON
array Developer wrote) is genuinely new: deterministic Python, running as
the same OS user as everything else in this system, reading real
repository paths **driven by data pulled from the database**, not by a
fixed argv the way `agent_runtime.py`'s `Popen` call already is. This is
a real, new attack surface worth naming directly, not glossing over: a
malformed or malicious `files_changed` entry (e.g. `"../../../etc/passwd"`
or an absolute path) must not let this Python code read or diff
something outside the repository. **Mitigation, required, not
optional**: every path in `files_changed` is validated before use —
rejected if it is absolute, rejected if `Path(repo_root, path).resolve()`
does not remain inside `repo_root`, rejected if it contains a `..`
component after normalization. Any path failing validation causes the
whole candidate to be skipped (fail-closed, §B.10 scenario 6, flagged for
Founder attention), never silently dropped from the list while
proceeding with the rest. `git diff`/`git show` are invoked via a fixed
argv list (`subprocess.run([...], cwd=repo_root)`), never a shell string —
the same injection-safety convention `agent_runtime.py`'s own `Popen`
call already established.

## B.2 Detection mechanism: an in-process daemon thread inside `server.py`

**Decision: option (i)** — a `threading.Thread(daemon=True)` started in
`server.py`'s `main()`, living inside the existing single server
process, polling on an interval. Rejected: a separate standalone script
(option ii) — a second process the Founder has to remember to start,
monitor, and stop independently contradicts the Founder's own "preserve
existing architecture unless genuinely justified" instruction, and this
system has exactly one process today by design. A background poller
inside the process that's already running is the smaller addition:

- the Founder never needs to run or remember a second command;
- the kill switch (§B.9) and "what is running right now" (§B.11/B.12)
  naturally live in the same database the HTTP server already reads —
  no second status channel to keep in sync;
- Ctrl+C on the one process the Founder already runs stops everything,
  matching the existing mental model exactly, rather than requiring a
  second Ctrl+C somewhere else.

A background poller is not avoidable *in some form* — "the system
recognizes completion automatically," per the Founder's own words,
structurally requires either a background loop or requiring the Founder
to manually trigger a check on every page load (which is not
"automatic"). A daemon thread inside the existing process is the
smallest addition that satisfies the requirement without adding a new
process to the Founder's own operational surface — this genuinely is
the "preserve existing architecture" answer, not a rationalization for
adding complexity.

**Concretely** (new module, `ops/control-center/automation.py`):

```python
POLL_INTERVAL_S = 20            # Red Team should confirm/adjust this number
_stop_event = threading.Event()

def run_poll_loop():
    while not _stop_event.is_set():
        try:
            _poll_once()
        except Exception as exc:  # noqa: BLE001 — one bad cycle must not kill the whole loop
            sys.stderr.write(f"[automation] unhandled error in poll cycle: {type(exc).__name__}: {exc}\n")
        _stop_event.wait(POLL_INTERVAL_S)
```

Started in `server.py`'s `main()`, right after the existing startup
reconciliation calls, before `serve_forever()`. `_stop_event.set()` on
shutdown (`KeyboardInterrupt`/`finally`), with a short `join(timeout=...)`
so the process doesn't exit mid-cycle in the common case — belt-and-
suspenders on top of `httpd.daemon_threads = True`, which already
guarantees the thread can't block process exit even if not joined,
consistent with this codebase's preference for explicit over implicit.

Every poll cycle opens **its own** `opsdb.connect()` (a writable
connection — the cycle both reads candidate state and writes, exactly
like `meeting_orchestrator.py` already does throughout; never
`dbutil.connect()`'s read-only connection, which cannot write) and
closes it before sleeping — same per-cycle-scoped-connection discipline
every HTTP request already follows; no connection is ever held across
the sleep interval.

**This is, structurally, the same category of thing as
`ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL`'s existing precedent**:
"Chief of Staff decided to route this to Code Review" is a mechanical,
rule-based determination (is this task in `CODE_REVIEW` with a real,
unprocessed Developer handoff?) — not a judgment call requiring a real
model turn. The poller's own bookkeeping writes (`task_status_history`
notes, `automation_events` rows) are attributed to `orchestrator`
exactly the way the existing validation step already is, without ever
becoming a `claude --agent orchestrator` invocation. Only the Code
Review verdict itself is a real model call, to `code-review` — the
routing decision around it is not.

## B.3 New table: `automation_events` — the single automatic-audit record

```sql
CREATE TABLE IF NOT EXISTS automation_events (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id                   INTEGER NOT NULL REFERENCES tasks(id),
  trigger_status_history_id INTEGER NOT NULL UNIQUE
                             REFERENCES task_status_history(id),
  status        TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','completed','failed','skipped')),
  outcome       TEXT CHECK (outcome IN ('pass','reject','error','interrupted','capped',NULL)),
  review_result_id INTEGER REFERENCES review_results(id),
  agent_run_id      INTEGER REFERENCES agent_runs(id),
  cost_usd          REAL,
  truncated         INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0,1)),
  skip_reason       TEXT,
  started_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_automation_events_task ON automation_events(task_id);
```

**`trigger_status_history_id UNIQUE` is the load-bearing idempotency
mechanism** (Founder's control #5): the specific `task_status_history`
row recording "this task entered `CODE_REVIEW`" can be claimed by
exactly one `automation_events` row, ever, enforced by SQLite itself —
not merely by application-level checking. The poller inserts this row
**before** invoking anything (claim-then-act, the exact discipline
`gather_requested_position()`'s own TASK-011 QA-round-2 fix already
established for the identical class of "reserve exclusivity before
spending a real invocation" problem), inside its own transaction — a
second cycle, or a hypothetical second poller, attempting the same
insert gets a clean `IntegrityError`/pre-check rejection, never a second
real invocation. This is also the answer to "how do we tell an automated
review apart from a human-supervised one without touching the shared
`review_results` table's shape": a `review_results` row referenced by
some `automation_events.review_result_id` is automated; every other
`review_results` row is human-supervised. No new column on the shared
table.

**Why a new table, not overloading `agent_runs`**: `agent_runs` already
has a real, specific job (Working/Waiting/Blocked/Available derivation)
that this design still uses unchanged (§B.3.1) — automation's own
bookkeeping (invocation caps, spend, trigger-event linkage, skip
reasons) is a genuinely different shape of fact that doesn't fit that
table's existing columns without distorting it. This is the same
reasoning `qa_results`/`review_results` already being separate,
purpose-shaped tables from `agent_runs` demonstrates — reuse the
existing pattern of "one small table per distinct kind of fact," not
"cram a new concept into an existing table because a table already
exists."

### B.3.1 `agent_runs` still gets a row, for consistency

```python
AUTOMATED_CODE_REVIEW_ACTIVITY_LABEL = "Automated Code Review: reviewing a completed Developer handoff"
AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE = "Automated Code Review:%"
```

Same fixed-label-plus-`scope_id`-carries-specifics convention
`MEETING_ACTIVITY_LABEL` already uses (not an f-string baked into the
label — the specific task is `scope_id`, `scope_type='task'`). Created
via `opsdb.start_run(conn, "code-review", "task", AUTOMATED_CODE_REVIEW_ACTIVITY_LABEL, scope_id=task_id)`
(the plain, already-existing, non-Ask-Agent-specific `start_run()` —
reused unchanged, no new opsdb function needed for this part), ended via
`end_run()`. `automation_events.agent_run_id` links the two records.
This means the Agents view correctly shows `code-review` as "Working"
during an automated review, exactly like every other invocation.

## B.4 Single-row kill-switch state: `automation_state`

```sql
CREATE TABLE IF NOT EXISTS automation_state (
  id           INTEGER PRIMARY KEY CHECK (id = 1),   -- exactly one row, ever
  enabled      INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0,1)),
  changed_by   TEXT NOT NULL DEFAULT 'system',
  reason       TEXT,
  changed_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
INSERT OR IGNORE INTO automation_state (id, enabled, changed_by, reason)
  VALUES (1, 0, 'system', 'Phase 3A shipped disabled by default — Founder must explicitly enable it.');
```

**`enabled=0` by default, seeded at schema-apply time — automation does
not run until the Founder deliberately turns it on once.** This is the
same fail-closed-by-default discipline `founder_auth.py`'s
"setup required" 503 already established for Milestone 2B4: a brand-new
capability defaults to *off*, and turning it on is a real, visible,
attributed action, not an implicit consequence of upgrading the code.

`opsdb.set_automation_enabled(conn, enabled: bool, reason: str | None,
by: str = "founder")` — new plain function, same shape as every other
opsdb.py write. `changed_by` is always `"founder"` for this table (the
same string every other Founder-attributed write already uses — there is
no per-person Founder identity in this schema, per `ops/SECURITY.md`) —
this row can only ever be written by the two new session+CSRF-gated
routes below, never by the poller itself, never by any agent invocation.

## B.5 New Founder-facing routes — same auth boundary as every other write

- `GET /automation.html` — session-gated like every other page (new
  `generate_automation.py`, reusing `dbutil.connect()` read-only, same
  shape as `generate_reviews.py`/`generate_releases.py`). Shows: current
  kill-switch state (with a big, unambiguous STOP/START form, styled
  like the existing approvals Approve/Reject buttons — no new visual
  pattern), any `automation_events` currently `status='running'`, the
  most recent N terminal ones with links to their tasks/review results,
  and today's running total against `MAX_AUTOMATION_SPEND_USD_PER_DAY`
  (§B.6).
- `POST /api/automation/stop` — CSRF + session gated, same as every
  other write route, calls `opsdb.set_automation_enabled(conn, False,
  reason=<optional form field>)`.
- `POST /api/automation/start` — same gating, calls
  `opsdb.set_automation_enabled(conn, True, reason=<optional form field>)`.

**Honest STOP semantics, stated explicitly, not overclaimed**: flipping
the switch off prevents any **new** automatic action from starting on
the poller's very next check of the flag (checked once at the top of
each cycle, and again immediately before claiming a candidate, closing
the narrow window where a cycle is already mid-flight when the Founder
clicks Stop). It does **not** forcibly kill an already-in-flight
`code-review` subprocess — the same accepted, previously-reviewed
behavior Ctrl+C already has for Ask-Agent (Milestone 2B3A: "a
process-tracking/kill-on-shutdown mechanism was considered and rejected
as unnecessary complexity," Red Team's 2B3A review). Because Phase 3A's
automation makes at most one bounded invocation per triggering event
(`AUTOMATED_REVIEW_TIMEOUT_S=120`, `$0.50`-capped), the worst case after
clicking Stop is bounded and small — this must be stated to the Founder
plainly in `/automation.html`'s own copy and in the Chief of Staff's
answer to "stop it," not left implicit.

**Why the Chief of Staff cannot itself execute Stop (§A.4 revisited)**:
this route is a real, consequential write. Letting a natural-language
chat instruction trigger it would open a new write path *outside* the
one reviewed CSRF+session-gated form boundary this entire system has
maintained since Milestone 2B1 — and would mean a write decision is made
by interpreting free text, exactly the class of thing this system
already treats cautiously (CEO's participant nomination is parsed, never
trusted as an instruction; the same applies here, with higher stakes).
The Chief of Staff's answer to "stop it" is a clear explanation plus a
direct pointer to the real STOP action on `/automation.html` — the
Founder still clicks it themselves, same as they still click
Approve/Reject on an approval today after reading the Chief of Staff's
recommendation.

## B.6 Spend guard

`MAX_AUTOMATION_SPEND_USD_PER_DAY = 10.00` (new constant,
`automation.py` — same order of magnitude as the existing disclosed
Executive-Meeting worst case, a reasonable starting ceiling for Red Team
to confirm or revise). Before claiming any new candidate, the poller
sums `automation_events.cost_usd` for rows `started_at` within the
current UTC day, **plus** a worst-case `$0.50` reservation for every row
currently `status='running'` (so concurrent/near-simultaneous cycles
can't slip past the check before their own cost is known) — if adding
one more worst-case `$0.50` would exceed the ceiling, the candidate is
skipped (`status='skipped'`, `skip_reason='daily automation spend
ceiling reached'`), not silently dropped. `automation_events.cost_usd`
is populated from `RuntimeResult.cost_usd` once the real invocation
completes — this closes the pre-existing gap (§ "Verified facts") where
that value was computed but never persisted; it does not retroactively
add cost tracking to any other invocation path, which is a separate,
future decision if the Founder wants it.

## B.7 Loop prevention and per-task caps

```python
MAX_AUTOMATED_INVOCATIONS_PER_TASK = 3   # lifetime, across repeated CODE_REVIEW re-entries
MAX_AUTOMATED_TRANSITIONS_PER_TASK  = 3   # currently identical in effect to the above — see below
MAX_CANDIDATES_PER_CYCLE            = 5
MAX_AUTOMATED_INVOCATIONS_PER_DAY   = 20
```

- **Per-task lifetime cap**: before claiming a new candidate for a task,
  count existing `automation_events` rows for that `task_id`. A task
  legitimately re-enters `CODE_REVIEW` after a Founder-resumed fix
  (reject -> Founder decides to resume -> Developer fixes -> new,
  distinct `task_status_history` row -> `CODE_REVIEW` again) — each such
  re-entry is a genuinely new trigger event with its own row, so the
  per-event UNIQUE constraint (§B.3) alone would let this repeat
  indefinitely. The lifetime cap is the actual defense-in-depth answer
  to "loop prevention" for that legitimate-but-repeatable case: a 4th
  automatic attempt on the same task is skipped
  (`skip_reason='per-task automated-invocation cap reached — needs
  manual review'`), surfaced on `/automation.html`, never silently
  retried forever.
- **Why #2 (max invocations) and #3 (max transitions) collapse to one
  enforced number in Phase 3A specifically**: this milestone's only
  automatic transition is the REJECT -> `IN_DEVELOPMENT` status
  rollback (§B.8), and it happens at most once per `automation_events`
  row — so today, one cap enforces both. They are kept as textually
  distinct constants because a future phase could plausibly decouple
  them (e.g. more automatic transitions per invocation); this is stated
  explicitly rather than silently relying on today's coincidence.
- **Per-cycle batch cap**: bounds worst-case work in any single poll
  cycle even if many tasks somehow became eligible at once (a bug
  elsewhere creating many `CODE_REVIEW` transitions in a short window) —
  candidates beyond the 5th in one cycle are simply picked up on a later
  cycle, not skipped/lost (no state is destroyed by hitting this cap,
  unlike the other caps above).
- **Company-wide daily cap**: final defense-in-depth ceiling
  independent of and in addition to the spend ceiling (a cheap
  invocation hitting a count-based loop before it ever gets expensive
  enough to trip the dollar ceiling is still worth catching).

## B.8 What happens on PASS vs. REJECT — asymmetric, per the Founder's own instruction

- **PASS**: `opsdb.record_review_result(conn, task_id, "code", "code-review", "pass", findings=[...])`
  is called (the new plain function — §B.3's refactor). **`tasks.status`
  is left unchanged, at `CODE_REVIEW`.** The Founder's directive is
  explicit — "NO automatic Code Review PASS -> QA" — so nothing advances
  the pipeline automatically; a human, via a normal supervised session,
  moves the task to `QA` next, exactly as today. `automation_events`
  marked `status='completed', outcome='pass'`.
- **REJECT**: `record_review_result(..., "reject", findings=[...],
  returned_to="developer")` (the schema's own `CHECK` constraint already
  requires a reject to name a destination — unchanged). The directive
  explicitly *does* want the task "routed toward Developer" — this is a
  single, mechanical `tasks.status` transition, `CODE_REVIEW ->
  IN_DEVELOPMENT`, via `opsdb.task_status`-equivalent (the plain
  function backing `cmd_task_status`, called with
  `changed_by_agent="orchestrator"` and a note prefixed
  `AUTOMATION_NOTE_PREFIX` — §B.9) — pure bookkeeping, not a new
  Developer invocation. This satisfies "move/route the task toward
  Developer" without violating "DO NOT automatically start another
  Developer model invocation": the task simply becomes visible,
  unblocked, sitting in `IN_DEVELOPMENT` for a human-directed Developer
  session to pick up next, identical in shape to how a QA-failed task
  already returns to `IN_DEVELOPMENT` today (`AGENT_STATUS.md`'s
  existing rule, extended to name this automated case explicitly).
  `automation_events` marked `status='completed', outcome='reject'`.
- **Invocation failure** (`error_kind` set — timeout, capacity_exceeded,
  runtime_error): **no `review_results` row is fabricated** (never
  invent a PASS/REJECT from a call that didn't actually produce one — the
  same "never fabricate" discipline `_gather_position()` etc. already
  follow on failure). `automation_events` marked `status='failed',
  outcome='error'`. Because the triggering `task_status_history` row is
  already permanently claimed (UNIQUE constraint), this specific trigger
  event is never automatically retried — it becomes a Founder-visible
  "automated review did not complete for TASK-XXX, needs a look" state,
  answerable via `/automation.html` and the Chief of Staff. This is
  fail-closed by construction, not a special case to remember to build.

## B.9 Clear automatic-vs-Founder-triggered audit history

```python
AUTOMATION_NOTE_PREFIX = "[Automated, Phase 3A]"
```

Every `task_status_history.note` this design writes carries this prefix
(e.g. `"[Automated, Phase 3A] Code Review rejected — routed back to
Developer (automation_events id=42)."`). Combined with `automation_events`
being a table nothing but this automation ever writes to, and
`automation_events.review_result_id` being the sole distinguishing link
for an otherwise-identical `review_results` row, the audit trail answers
"was this automatic or Founder-triggered" unambiguously from real,
persisted data at every layer — never from a label that could drift out
of sync with what actually happened.

## B.10 Fail-closed behavior — the concrete ambiguous-state scenarios this must handle

1. A trigger row already has an `automation_events` row (any status) —
   not ambiguous, it's the idempotency case: skip, no action (§B.3's
   UNIQUE constraint is the actual enforcement; this is the app-level
   pre-check that avoids even attempting the doomed insert).
2. A `task_status_history` row says `to_status='CODE_REVIEW'` but **no**
   `handoffs` row exists with `from_agent='developer',
   to_agent='code-review', task_id=<task>` — this is genuinely
   ambiguous: was this really "Developer completed work," or did a human
   move the status for some other reason (re-opening, correcting an
   error, testing)? **Fail closed: do not auto-trigger.** Logged as
   `skipped`, `skip_reason='no completed Developer handoff found'`,
   surfaced for manual attention — never guessed at.
3. A matching handoff exists but is missing `base_commit_sha` or
   `head_commit_sha` (§B.1, §B.13 — older handoffs predating this
   milestone, or a Developer session that didn't record them) — cannot
   assemble a real diff. **Fail closed: skip**,
   `skip_reason='handoff missing base/head commit — cannot assemble a
   diff automatically'`.
4. `tasks.status` has already moved on (no longer `CODE_REVIEW`) by the
   time the candidate is actually processed — a human acted on it
   between the poller's read and its claim attempt. **Fail closed:
   re-check immediately before claiming, inside the same transaction as
   the insert; skip if it no longer matches.**
5. `automation_state` is unreadable (a DB error mid-read) — **treat as
   disabled, never default to enabled.** The same fail-closed instinct
   `founder_auth.py`'s credential-read error handling already
   establishes for this codebase (a `CredentialError` is treated
   identically to "setup required," never surfaced as a crash that
   might accidentally fall through to an insecure default).
6. A `files_changed` path fails validation (§B.1.2) — **skip the whole
   candidate**, never silently proceed with a partial file set while
   dropping the bad entry unremarked; `skip_reason='invalid file path in
   handoff — see server log'`.
7. An `automation_events` row is found `status='running'` at server
   **startup** (§B.11) — the prior process crashed mid-cycle. **Never
   silently mark it complete or resumed** — startup reconciliation marks
   it `status='failed', outcome='interrupted'` once, and (per the UNIQUE
   constraint) its trigger event is never automatically retried; it
   becomes exactly the same Founder-visible "needs a look" state as any
   other failure above.

## B.11 Crash/restart recovery and orphaned-run reconciliation

`server.py`'s existing `_reconcile_orphaned_runs()` (already covering
Ask-Agent and meeting-participant runs, extended once before for
Orchestrator's own validation-step runs) gains:

```python
opsdb.reconcile_orphaned_runs(conn, automation.AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE, status="failed")
```

— the same generic function, a fourth LIKE pattern, zero new mechanism
for the `agent_runs` side. A new, small opsdb.py function,
`reconcile_stuck_automation_events(conn)`, does the equivalent for the
new table:

```sql
UPDATE automation_events SET status='failed', outcome='interrupted',
  ended_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE status='running'
```

Both run once at server startup, before the poller thread starts and
before `serve_forever()`, exactly where every existing reconciliation
call already runs — no new startup-ordering concept.

## B.12 "What is running right now" — Founder-visible, from real state

`/automation.html` (§B.5) and the Chief of Staff's state digest (§A.2,
`automation_status_digest()`) read the **same** query:
`SELECT * FROM automation_events WHERE status='running'`, joined to
`tasks`/`agent_runs` for display. "Why did this start" traces to the
real `task_status_history` row (`changed_by_agent`, `changed_at`, `note`)
the triggering transition already recorded, plus the `handoffs` row it
validated against — a complete, honest provenance chain built from data
that already exists for an entirely different reason (recording the
original human-supervised handoff), not a synthetic explanation
generated after the fact. "How much has this used" reads
`automation_events.cost_usd` summed against `MAX_AUTOMATION_SPEND_USD_PER_DAY`
(§B.6) — the same number the spend guard itself enforces, not a second,
possibly-inconsistent estimate. "What happens next" is answerable
directly from `automation_events.status`/`outcome`: `running` -> "still
reviewing, ends automatically either way"; `completed/pass` -> "sitting
at Code Review, PASSED — a human needs to move it to QA when ready" (per
the Founder's own explicit no-auto-advance rule); `completed/reject` ->
"already routed back to Development — a human needs to decide when
Development resumes it" (per the Founder's own explicit
no-auto-Developer-invocation rule); `failed/skipped` -> "did not run
automatically — needs a look," with the concrete `skip_reason`.

## B.13 A necessary, small schema addition: `handoffs.base_commit_sha` / `head_commit_sha`

The current schema has no explicit "which two commits does this task's
diff span" concept. A timestamp-based heuristic (infer a base commit
from `task_status_history`'s `IN_DEVELOPMENT`-entry timestamp) was
considered and rejected: it is approximate, depends on assumptions about
this project's actual git/branch usage that were not independently
verified for every workflow shape this system might run under, and a
wrong base commit produces a *misleading* diff fed to an automated
reviewer — an honesty/correctness risk, not merely a security one, and
directly undermines §B.1's central claim that the assembled transcript
is real and useful.

**Decision: two new, nullable `TEXT` columns on `handoffs`** —
`base_commit_sha`, `head_commit_sha` — populated by Developer at handoff
time (`opsdb.py handoff --base-commit-sha <sha> --head-commit-sha <sha>`,
new optional CLI flags on the existing `handoff` command; nullable for
backward compatibility with every pre-Phase-3A handoff row, and for
non-code handoffs where the concept doesn't apply). This is a plain,
additive `ALTER TABLE handoffs ADD COLUMN ...` — **not** the
rebuild-and-copy technique Milestone 2B2 needed for `agent_runs.status`;
that technique was required specifically because a `CHECK` constraint
was changing, which SQLite cannot `ALTER`. A new nullable column with no
`CHECK` constraint is a direct, safe `ADD COLUMN` — Development should
not over-engineer this migration.

`.claude/agents/developer.md` / `ops/agents/developer.md` gain a short
note: when handing off to Code Review, record the real base/head commit
SHAs the diff should span (`git rev-parse HEAD` before and after the
task's own work) — a small, concrete addition to an already-existing
step (Developer already runs `opsdb.py handoff ...`), not a new
workflow concept.

---

# Phase 3A acceptance test — how Development should demonstrate this

Directly mapped to the Founder's own stated acceptance bar; this is a
test plan for Development/QA to execute, not a claim that it has been
executed:

- **Exactly one automatic Code Review run, Founder did not manually
  initiate it**: move a real test task to `CODE_REVIEW` with a real
  Developer handoff (base/head commits recorded) while `automation_state.enabled=1`;
  observe exactly one new `automation_events` row and one `review_results`
  row appear within one `POLL_INTERVAL_S` cycle, with no Founder click
  triggering it.
- **Duplicate completion signals do not create duplicate Code
  Reviews**: attempt to force a second claim of the same
  `task_status_history` row (e.g. by racing two manual pool cycles in a
  test harness) — confirm the `UNIQUE` constraint rejects the second
  attempt and exactly one real invocation occurred.
- **Restart/crash behavior**: kill the server process mid-invocation
  (`status='running'`); restart it; confirm `reconcile_stuck_automation_events()`
  and the extended `reconcile_orphaned_runs()` both mark the interrupted
  rows `failed`/`interrupted`, and confirm the specific trigger event is
  never automatically retried afterward.
- **Loop/spend limits tested**: seed more than `MAX_AUTOMATED_INVOCATIONS_PER_TASK`
  trigger events for one task and confirm the excess are skipped with a
  clear reason; seed enough `automation_events.cost_usd` to approach
  `MAX_AUTOMATION_SPEND_USD_PER_DAY` and confirm the next candidate is
  skipped, not processed.
- **Emergency STOP tested**: click Stop mid-cycle (or immediately before
  one); confirm no new `automation_events` row is created afterward,
  and confirm any already-in-flight invocation still completes/times out
  on its own bounded schedule (per §B.5's disclosed honest semantics —
  this is the expected, not a failing, result).
- **All automatic actions visibly auditable**: every row this milestone's
  automation writes carries the `AUTOMATION_NOTE_PREFIX`/`automation_events`
  linkage described in §B.9; confirm `/automation.html` and a real
  Chief of Staff chat question ("what is running right now," "why did
  this start," "how much has this used," "what happens next") each
  produce answers traceable to those exact rows, not prewritten text.
- **Chief of Staff conversational experience tested with real
  questions** against real database/company state — not scripted demo
  text — per the Founder's own explicit instruction; this should be
  QA's job once Development ships Part A, using the project's own
  scratch-`OPSDB_PATH` convention (`ops/db/README.md`) so this never
  touches the live database.

---

# What Phase 3A explicitly does NOT do (recap, so it isn't lost in the detail above)

- Does not resolve, narrow, or claim progress on `risks.id=3`.
- No automatic Code Review PASS -> QA; no automatic QA -> Security; no
  automatic Security -> Release; no automatic production deployment.
  Production deployment continues to always require explicit Founder
  approval, unchanged, via the existing `deployments.founder_authorized`
  `CHECK` constraint and approvals flow.
- No automatic re-invocation of Developer after a REJECT — only a
  mechanical status transition, never a new model call.
- No autonomous initiation of unrelated work — the poller only ever acts
  on a task already, genuinely, in `CODE_REVIEW` with a real Developer
  handoff; it does not decide what work should start.
- No chat-triggered writes — the Chief of Staff conversational interface
  is read/recommend-only with respect to every consequential action; all
  of those remain explicit, separately-gated Founder clicks.
- No new paid external service, no new third-party dependency, no change
  to SQLite as the operational store.

---

# File-by-file change list

**New files:**
- `ops/control-center/chief_of_staff.py` — state-digest assembly
  (composing `derived_state.py` helpers), transcript building, `CONSULT:`
  parsing, consult-meeting triggering (calls `meeting_orchestrator.run_consult_meeting()`),
  final-synthesis invocation, response persistence. Mirrors
  `meeting_orchestrator.py`'s separation from `server.py`.
- `ops/control-center/automation.py` — the poll loop, candidate
  detection, path validation, `git diff`/file-content transcript
  assembly, invocation, result persistence, cap/spend/kill-switch
  enforcement. Mirrors `meeting_orchestrator.py`'s separation from
  `server.py` and its "never touch sqlite3 directly except through
  opsdb.py functions" rule.
- `ops/control-center/generate_automation.py` — renders
  `/automation.html`, same shape as `generate_reviews.py`/
  `generate_releases.py` (read-only `dbutil.connect()`, `build_html(token=...)`).

**Modified files:**
- `ops/db/schema.sql` — new `automation_events` table, new
  `automation_state` single-row table (seeded disabled), new nullable
  `handoffs.base_commit_sha`/`head_commit_sha` columns (plain
  `ADD COLUMN`, not the rebuild-and-copy technique — no `CHECK` change).
- `ops/db/opsdb.py` — refactor `cmd_review_result` into a plain
  `record_review_result(conn, task_id, review_type, by, result,
  findings=None, returned_to=None)` function plus its existing thin CLI
  wrapper (matches every other write function's shape); new
  `set_automation_enabled(conn, enabled, reason=None, by="founder")`;
  new `create_automation_event(conn, task_id, trigger_status_history_id)`
  (atomic claim) and `end_automation_event(conn, event_id, status,
  outcome=None, review_result_id=None, cost_usd=None, truncated=False,
  skip_reason=None)`; new `reconcile_stuck_automation_events(conn)`; new
  `--base-commit-sha`/`--head-commit-sha` optional flags on the existing
  `handoff` CLI command.
- `ops/db/derived_state.py` — new read-only digest helpers:
  `open_risks_digest()`, `active_tasks_digest()`,
  `pending_approvals_digest()`, `recent_decisions_digest()`,
  `recent_status_transitions_digest()`, `recent_review_qa_digest()`,
  `recent_deployments_digest()`, `automation_status_digest()`.
- `ops/control-center/agent_runtime.py` — new constants
  `CHIEF_OF_STAFF_ALLOWLIST`, `CHIEF_OF_STAFF_ACTIVITY_LABEL`/`_LIKE`,
  `AUTOMATED_REVIEW_ALLOWLIST = ("code-review",)`,
  `AUTOMATED_CODE_REVIEW_ACTIVITY_LABEL`/`_LIKE`,
  `AUTOMATED_REVIEW_TIMEOUT_S`; widen `invoke_agent()`'s validity check
  to include the two new allowlists.
- `ops/control-center/meeting_orchestrator.py` — extract `run_meeting()`'s
  gather+synthesize body into an internal `_gather_and_synthesize()`
  helper; add `run_consult_meeting(topic, participants,
  initiated_by="founder")`; extract `_validate_selection()`'s dedup/cap
  logic into a small shared helper callable from both CEO-nominated and
  Chief-of-Staff-parsed participant lists.
- `ops/control-center/server.py` — new routes: `POST
  /api/chief-of-staff/ask`, `GET /automation.html`, `POST
  /api/automation/stop`, `POST /api/automation/start` (all through the
  existing `do_GET()`/`do_POST()` dispatch, existing CSRF+session gate,
  no new auth mechanism); `main()` starts/stops the `automation.py` poll
  thread; `_reconcile_orphaned_runs()` extended with the new
  `AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE` pattern and a call to
  `reconcile_stuck_automation_events()`.
- `ops/control-center/generate_agents.py` — `/agents/orchestrator.html`
  gains a chat form (existing visual component) posting to
  `/api/chief-of-staff/ask` instead of `/api/agents/<name>/ask`.
- `.claude/agents/orchestrator.md` / `ops/agents/orchestrator.md` —
  plain-English/recommendation-first persona instructions, the
  `CONSULT:` marker convention, and the "never treat a chat instruction
  as an executable command" instruction (§A.4).
- `.claude/agents/code-review.md` / `ops/agents/code-review.md` — new
  note describing the automated-invocation mode: content received,
  limitations versus a human-supervised session, required `VERDICT:
  PASS|REJECT` output line for this mode only (§B.1.1).
- `.claude/agents/developer.md` / `ops/agents/developer.md` — note to
  record `base_commit_sha`/`head_commit_sha` at handoff time (§B.13).
- `ops/DATA_MODEL.md` — document `automation_events`, `automation_state`,
  and the two new `handoffs` columns, same convention as every existing
  table's section.
- `ops/AGENT_STATUS.md` — note that a `CODE_REVIEW`-stage task may now
  additionally be reviewed by Phase 3A's automation, and that the
  existing "failed review/QA returns to `IN_DEVELOPMENT`" rule now has a
  documented automated case alongside the existing human one.
- `ops/SECURITY.md` — new "Phase 3A: Chief of Staff Founder Interface +
  Limited Automated Orchestration" section, same disclosure discipline
  as every prior milestone: the new allowlist widenings and exactly why
  each is bounded; the new filesystem-touching poller surface and its
  path-validation mitigation (§B.1.2); the honest STOP semantics
  (§B.5); the explicit statement that `risks.id=3`'s practical
  consequence increases under autonomous operation, per the Founder's
  own instruction, and is not mitigated by anything in this design; the
  Part A consult-meeting worst-case cost disclosure (§A.3).
- `risks` table — no status change to `id=3` (stays `open`). Recommend
  Security append (not overwrite) a note to its `description` once this
  ships, along the lines of: "Phase 3A (TASK-015) introduced limited
  automated orchestration; this risk's practical consequence increased
  as a result (an unsupervised, though zero-tool, invocation now occurs
  without a human directly initiating it) — see
  `ops/reviews/cto-phase3a-architecture.md`, §B.1." This is a
  description update, not a resolution, and should go through whatever
  mechanism Security judges preserves the audit trail correctly, not a
  direct edit.

---

# Open questions for Security and Red Team

1. Is `POLL_INTERVAL_S = 20`, `MAX_AUTOMATED_INVOCATIONS_PER_TASK = 3`,
   `MAX_CANDIDATES_PER_CYCLE = 5`, `MAX_AUTOMATED_INVOCATIONS_PER_DAY = 20`,
   and `MAX_AUTOMATION_SPEND_USD_PER_DAY = 10.00` the right set of
   numbers, or does Red Team want them tuned differently given the
   actual deployment target?
2. Is the zero-tool, Python-assembled-transcript design for automated
   Code Review (§B.1) actually sufficient in practice, or does Red Team
   find a realistic class of real defect this bounded context would
   plausibly miss that a human-supervised session would have caught —
   and if so, is that an acceptable, disclosed limitation for Phase 3A,
   or does it change the recommendation?
3. Is the `base_commit_sha`/`head_commit_sha` handoff-time recording
   (§B.13) reliable given this project's actual git/branch usage in
   practice, or does Red Team want it verified against a real multi-task
   sequence before Development builds on it?
4. Does Security want the `automation_events`/`automation_state` tables'
   contents (task titles, review findings, cost) treated as
   Founder-sensitive in any way beyond the existing session gate already
   applied to every other page?
5. Is skipping (not erroring loudly to the Founder in real time) the
   right behavior for every §B.10 fail-closed scenario, or does Red Team
   want a subset of them to instead raise a real `approvals`-style
   Founder-visible flag immediately, rather than only being discoverable
   via `/automation.html`/the Chief of Staff on request?
6. Does Security want the honest "STOP doesn't kill an in-flight
   subprocess" semantics (§B.5) tightened for Phase 3A given the
   Founder's explicit "emergency STOP" framing, even though this project
   previously reviewed and accepted the identical limitation for
   Ask-Agent (Milestone 2B3A)?
