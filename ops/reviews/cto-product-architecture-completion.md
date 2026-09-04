# CTO — Product Architecture Completion Assessment (TASK-018)

Date: 2026-08-31
Author: CTO
Directive: Founder, "PAUSE SECURITY HARDENING, FINISH PRODUCT ARCHITECTURE
FIRST", 2026-08-31 (`DECISIONS.md` DEC-008)
Scope discipline: **design and inventory only.** Nothing in this document is
implemented. No code was written or changed except the small, surgical
`ops/ROADMAP.md` correction disclosed in Part 6. Production deployment
remains Founder-only in every recommendation below; nothing here proposes
unrestricted autonomous production behavior.

Every claim below is evidence-based: a specific file, table, route, or a
direct query against the live operational database
(`ops/db/operations.sqlite3`, queried read-only via `opsdb.py query`, no
scratch/isolated copy) run while writing this document. Where I could not
verify something directly, I say so rather than assert it.

---

## Part 1 — Current architecture completion status

### 1.1 Remaining Phase 3 orchestration

Per `ROADMAP.md` PHASE 3 and `DECISIONS.md` DEC-007, the target automated
chain is: **Developer complete → Code Review → QA → Security → Release
prep**, with rejection loops routing backward at each gate, and production
deployment always Founder-gated.

What is real today, cited directly:

- **Developer-complete → Code Review (automatic): DONE.** `ops/control-
  center/automation.py` — an in-process `daemon=True` polling thread
  (`POLL_INTERVAL_S=20`) inside `server.py`'s own process, gated by the
  `automation_state` single-row kill switch (currently `enabled=0` — see
  §1.9). On a real Code Review PASS, `tasks.status` is deliberately **not**
  advanced (`reviewer_sync.py` and `automation.py` both comment this
  explicitly: "PASS never auto-advances the task — a human still does
  that"). On REJECT, `opsdb.record_task_status()` performs one mechanical
  `CODE_REVIEW → IN_DEVELOPMENT` rollback — never a new Developer
  invocation.
- **Code Review PASS → QA (automatic): NOT BUILT.** No code path advances
  a `CODE_REVIEW`-status task to `QA` automatically or on any signal.
  Confirmed by reading `automation.py` in full — it only implements the one
  Developer→Code-Review poll — and by `server.py`'s `do_POST()` route table
  (§1.6 below): there is no HTTP write route that changes `tasks.status`
  from `CODE_REVIEW` to `QA` at all, automated or human-triggered.
- **QA → Security (automatic) / QA FAIL → Developer (automatic): NOT
  BUILT.** No poller, route, or CLI shortcut exists for this. QA results
  are recorded via `opsdb.py qa-result` (`cmd_qa_result`), a manual CLI
  write; nothing consumes a `qa_results` row to change `tasks.status`.
- **Security PASS → Release prep (automatic): NOT BUILT.** Same absence —
  `review_results` rows with `review_type='security'` are recorded, but
  nothing reads them to advance status.
- **Rejection/rework loops beyond the one built path: NOT BUILT**, except
  the two that exist — automation.py's Code-Review-REJECT rollback, and
  (paused, unreviewed — see §1.9) `reviewer_sync.py`'s synchronous-reviewer
  REJECT rollback for TASK-017's three human-triggered review routes
  (`POST /api/tasks/<id>/review/{code,security,red-team}`), which exist in
  code, are wired into `.claude/agents/developer.md`'s hook and
  `generate_reviews.py`'s "Run a review now" UI, but per DEC-008 have only
  passed architecture-stage review — never Code Review, QA, a Security-
  adversarial pass, or CTO conformance on the actual implementation.
- **Founder approval boundaries:** real for the one case that exists —
  `deployments` has a DB-enforced `CHECK (founder_authorized = 1)`
  constraint (`schema.sql` line 278), so no `deployments` row can ever be
  inserted without that flag set to 1. No code currently sets it (there is
  no deployment-writing code path at all yet — `cmd_deployment_record` is
  CLI-only, human-invoked). `FOUNDER_APPROVAL` is a real `tasks.status`
  value and the `approvals` table (`decision IN pending/discuss/approve/
  reject`) is the real escalation mechanism, wired into Founder Inbox
  (`/inbox.html`, Milestone 2B1). **What does not exist**: any automated
  system-initiated request that would ever attempt to write
  `founder_authorized=1` itself — that remains entirely human, today, by
  the absence of any code path that could do otherwise, not by an access
  check that blocks an attempt.

**Bottom line**: exactly one of four defined handoffs is automated (1 of
4, ~25%), and that one leaves the human/Founder in control of every
forward advance (PASS never auto-advances). This is the deliberately
narrow slice DEC-007 describes — accurately reflected in `ROADMAP.md`
today.

### 1.2 Task lifecycle model (`tasks.status` + `task_status_history`)

`schema.sql` defines a 16-value `tasks.status` enum (`BACKLOG` →
`PLANNING` → `MOCKUP` → `MOCKUP_REVIEW` → `ARCHITECTURE` →
`RED_TEAM_REVIEW` → `READY_FOR_DEVELOPMENT` → `IN_DEVELOPMENT` →
`CODE_REVIEW` → `QA` → `SECURITY_REVIEW` → `BLOCKED` → `FOUNDER_APPROVAL`
→ `READY_TO_RELEASE` → `DEPLOYED` → `DONE`), and `task_status_history` is
a genuine, append-only audit trail (`from_status`, `to_status`,
`changed_by_agent`, `changed_at`, `note`) written exclusively through
`opsdb.record_task_status()`. I confirmed this is populated with real,
detailed data — `task_status_history` for TASK-017 (queried directly)
shows five real rows with substantive `note` text documenting exactly why
each transition happened, including the Founder-directed pause.

Two real, evidenced limitations, not fixable by adding rows to this table
alone:

1. **`review_results.review_type` only allows `('code','security')`** —
   there is no `'red-team'` or `'architecture'` value. TASK-017's own
   architecture-stage Red Team reviews are recorded with
   `review_type='code'` and `reviewed_by_agent='red-team'` as a workaround
   (verified directly: `review_results` ids 49–51, `task_id=17`). This
   means a query that groups "code review history" by `review_type='code'`
   would today silently include architecture-stage Red Team reviews that
   are not code reviews at all. This is a real, narrow schema gap — not
   hypothetical.
2. **No formal "gate" concept exists anywhere in the schema.** A gate
   (Mockup Review, Architecture, Red Team Review, Code Review, QA,
   Security Review, Founder Approval, Release) is implicit in
   `derived_state.STAGE_MAP`/`PIPELINE_STAGES` (a Python dict, six major
   stages with named substates) but has no first-class row anywhere a
   "how many times did this gate get bounced" or "how long has this gate
   been open" query can be written against directly — it must be computed
   by joining `task_status_history` (when a task entered/left a status)
   against `review_results`/`qa_results` (what happened while it was
   there). See Part 3 for the full design of this.

**Assessment**: `tasks.status` + `task_status_history` is a sufficient
*state machine* — it genuinely captures what happened and when, and I
found no missing lifecycle state in six months of real project history
(13 DONE tasks, one BLOCKED, one BACKLOG, one FOUNDER_APPROVAL as of this
writing). It is **not**, by itself, a sufficient *gate-reporting* model —
that requires the derived/computed layer designed in Part 3, not a new
mutable table.

### 1.3 Agent-to-agent handoffs (`handoffs` table)

Real, but narrow and still substantially human/CLI-mediated. `handoffs`
has exactly **3 rows** in the live database as of this writing. The table
is written exclusively via `opsdb.py handoff` (`cmd_handoff`) — an agent
(or a human on its behalf) runs this CLI command by hand; no code path
writes a `handoffs` row automatically. `automation.py` only ever **reads**
a Developer's own prior handoff row (`base_commit_sha`/`head_commit_sha`/
`files_changed`) to assemble a diff for the automated Code Review — it
never writes one, and no automated QA/Security/Release handoff exists
because those transitions themselves aren't automated (§1.1).

There is also **no Founder-facing view of handoffs at all** — not on
`pipeline.html`, not as its own page, not referenced in
`server.py`'s route table. The data is real; it is currently invisible
to the Founder in the Control Center.

### 1.4 Agent communication (`messages`, Ask-Agent, Executive Meetings)

The mechanisms are real and shipped:

- **Ask-Agent** (`POST /api/agents/<name>/ask`, Milestone 2B2) — real,
  persistent, per-agent-thread conversations via `agent_runtime.invoke_agent()`
  against `agent_runtime.ASK_AGENT_ALLOWLIST`.
- **Executive Meetings** (`meeting_orchestrator.py`, Milestone 2B3B +
  round 2) — CEO-led participant selection, bounded-concurrent
  position-gathering, synthesis, Founder decision recording,
  request-perspective/follow-up/retry.
- **Chief of Staff conversational interface** (`POST /api/chief-of-
  staff/ask`, Phase 3A Part A) — the first-ever real
  `claude --agent orchestrator` invocation in this system, grounded in a
  fresh `_build_state_digest()` every turn, able to trigger a real
  Executive Meeting via `CONSULT:` parsing and narrate the result.

One concrete, verified fact worth disclosing plainly: **the live
operational database currently has 0 rows in `messages` and 0 rows in
`meetings`.** I queried both directly. Every "real, unmocked" invocation
cited in `DECISIONS.md` (e.g. the measured $0.0838 cost in
`security-adversarial-phase3a.md`, the risk-3 synthesis's real Chief of
Staff exchange) was run against an isolated clone with a scratch copy of
the database, by explicit design (`chief-of-staff-risk3-synthesis.md`:
"Nothing in the live repository, live database, or live Founder
credential was touched to produce this"). That is the correct, safe
testing discipline — but it means the capabilities are proven, not yet
*exercised against the company's own persistent record* the Founder will
actually browse. This is a fact about the current state, not a defect in
the mechanism.

### 1.5 Role-level responsibilities (`.claude/agents/*.md`)

All 14 files exist and are real, live Claude Code subagent configs (not
aspirational documentation) — each has a `tools:` frontmatter list that is
the agent's actual tool grant. Sampled directly: `developer.md` (42
lines, `tools: Read, Edit, Write, Bash, Grep, Glob, Skill`, plus the only
`hooks:` block in any of the 14 — TASK-017's `PreToolUse` denylist hook,
wired but unreviewed beyond architecture stage, see §1.9),
`orchestrator.md` (124 lines — by far the most detailed, correctly so,
since it now carries the Chief of Staff Founder-conversation persona
rules from Phase 3A), `qa.md` (19 lines, `tools: Read, Bash, Grep, Glob,
Skill` — deliberately no Write/Edit, matching "never fixes its own
findings").

These do **not** need a rewrite for Phase 3 completion — they already
correctly describe today's real tool grants and role boundaries. They
**will** need small, additive updates (not rewrites) at two specific
future points, both already anticipated by their own text: (1) if any
further Phase 3 milestone changes what Code Review/QA/Security do when
invoked automatically vs. interactively (already partly true —
`code-review.md`, at 100 lines, is the only reviewer doc I did not fully
read but is longer than the others, consistent with carrying both an
interactive and an automated-invocation persona note per Phase 3A); (2)
when role-level/task-level access narrowing (Part 5) resumes, every
execution-role doc (`developer.md`, `qa.md`, `cto.md`, `devops.md`) gains
a `hooks:` block the same way `developer.md` already has one. Neither is
needed for Founder testing to begin.

### 1.6 Task-level access model

**Explicitly a target, not built.** Confirmed by direct inspection: no
route, hook, or table anywhere in `ops/control-center/` or
`ops/db/schema.sql` narrows any agent's tool access to a specific task's
file paths (the Founder's own `/src/payments/**` example). What exists
today, from the paused TASK-016/017 work, is **role-level** scoping only
— a single Developer-wide denylist (`developer_pretooluse.py`, a fixed
pattern list: cannot touch `operations.sqlite3`, cannot self-edit
`developer.md`/hooks, etc.), not per-task path allow-lists. The
risks.id=3 synthesis (`chief-of-staff-risk3-synthesis.md`) explicitly
proposed per-task path-scoping as a further step and flagged it with
unresolved CONCERNS from Security ("defaults to allow-broad, risking
scoping that looks real but isn't") — it was never built, and TASK-017's
narrower, actually-authorized scope did not include it. See Part 5 for
the full restatement; I am not re-deriving this from scratch here.

### 1.7 Cost/token tracking architecture

Real, but narrower than it may appear. Directly verified in
`agent_runtime.py`'s `_run_claude()`: `cost_usd=data.get("total_cost_usd")`
— this is the `claude` CLI's own reported real cost from its JSON output
(`--output-format json`), not an estimate, not a static per-call
constant. The $0.0838 figure in `security-adversarial-phase3a.md` ("one
zero-tool `code-review` invocation, cost $0.0838") is that exact real,
measured field from one real invocation — **measured, not estimated.**

But persistence of that real number is inconsistent across invocation
types:

- **Persisted**: `automation_events.cost_usd` (the Phase 3A poller) and
  `reviewer_invocations.cost_usd` (TASK-017, paused — see below on
  whether this table even exists live).
- **NOT persisted anywhere**: Ask-Agent invocations, Executive Meeting
  participant invocations, and Chief of Staff conversation invocations.
  `agent_runtime.invoke_agent()` computes a real `RuntimeResult.cost_usd`
  for every one of these calls, but `agent_runs` (the table backing all
  three) has **no `cost_usd` column at all** — I confirmed this directly
  against `schema.sql`. The real number is computed, then discarded,
  every single time a human asks an agent a question or an Executive
  Meeting runs.
- **No company-wide cost aggregate exists anywhere.** `automation.py`'s
  spend guard (`MAX_AUTOMATION_SPEND_USD_PER_DAY = 10.00`,
  `_RESERVED_COST_PER_RUNNING_USD = 0.50`, matching
  `agent_runtime.MAX_BUDGET_USD = "0.50"` per-call cap) and
  `automation.html`'s "spend today" figure are both scoped **only** to
  the automation poller's own `automation_events` rows — they say nothing
  about what Ask-Agent, Executive Meetings, or Chief of Staff
  conversations have cost, because that data was never captured.
- A further, concrete, currently-live gap: `reviewer_invocations` and
  `hook_denials` — both defined in the committed `schema.sql` for
  TASK-017 — **do not exist as tables in the live
  `operations.sqlite3`** (confirmed via `sqlite_master`). `schema.sql`
  was edited after the database file's last write; `opsdb.py init` was
  never rerun to apply the addition. This is a small, mechanical,
  additive fact (running `init` again is safe and idempotent by design —
  `CREATE TABLE IF NOT EXISTS`), not a design defect, but it means
  TASK-017's own audit trail literally cannot be written to today even
  if a route reached it.

**Assessment**: real per-invocation cost measurement exists and is
trustworthy where it's captured. Company-wide cost visibility — what the
Founder actually needs to "understand AI cost" — does not exist, because
three of four invocation types (Ask-Agent, Meetings, Chief of Staff)
never persist the number they already compute. This is a small, additive
fix (one nullable column, `agent_runs.cost_usd`, plus three call sites
already holding the value) — design only, see Part 2/Part 3.

### 1.8 Project/user separation

`projects` exists (Phase 1 data model) and has exactly **1 row**
("AI-Pipeline Ops Bootstrap," created only for TASK-001's fake sample
walkthrough). Every other real task's `project_id` is `NULL` — confirmed
directly (`SELECT DISTINCT project_id FROM tasks` returns `NULL` and
`1`). There is no multi-project UI, no project switcher, no project-
scoped filtering anywhere in the Control Center. This is honestly
single-project-implicit today; the table exists structurally for a
future need that has not yet materialized and is explicitly out of scope
for Founder testing (the Founder is testing one company's pipeline, not
project isolation).

### 1.9 TASK-017 status, restated precisely for this document

TASK-017's Development pass is complete and committed
(`fdaf253 TASK-017: Development pass complete, PAUSED per Founder
directive (DEC-008)`), including `.claude/agents/developer.md`'s hook
wiring, `ops/control-center/hooks/developer_pretooluse.py`,
`reviewer_sync.py`, the three new HTTP routes in `server.py`, and
`schema.sql`'s `reviewer_invocations`/`hook_denials` tables. **None of
this has passed Code Review, QA, a Security-adversarial pass, or CTO
conformance** — only the pre-Development architecture passed those gates
(one Security CONCERNS fixed; two Red Team REJECTs fixed, final PASS —
verified directly against `review_results` rows 48–51 for TASK-017). Per
`task_status_history` row 132, the task sits at `BLOCKED`, explicitly not
representing acceptance that risks.id=3 is solved. I treat this
consistently with DEC-008 throughout this document: **preserved, not
validated, not shipped.**

---

## Part 2 — Proposed remaining Phase 3 milestones

Following Phase 3A's own precedent (narrow, disclosed, separately
Founder-gated slices — not one large automation build), and explicitly
NOT authorizing any of these by writing them down:

**Milestone 3B — Code Review PASS → QA automatic handoff.**
Same shape as Phase 3A Part B: extend `automation.py`'s poller (or a
second, equally narrow poller using the identical zero-tool/
`automation_events`-idempotency pattern) to recognize a `CODE_REVIEW`
task with a real `review_results` PASS row and advance it to `QA`
(status only — no automated QA invocation). REJECT path: none new needed
(Code Review's own REJECT already rolls back to `IN_DEVELOPMENT`).
Requires its own CTO architecture review, Red Team challenge, Security
threat model (specifically: does auto-advancing to QA change risks.id=3's
practical consequence the way Phase 3A's background actor did — almost
certainly yes, must be disclosed the same way).

**Milestone 3C — QA PASS → Security automatic handoff, QA FAIL →
Developer automatic rollback.**
Same pattern, one gate further. QA is currently 100% human/CLI-recorded
(`opsdb.py qa-result`) — this milestone does **not** propose automating
QA *testing* itself (an agent invocation actually running the app), only
automating the *status transition* once a QA result already exists,
identical in spirit to how Milestone 3B only automates the transition,
not a new invocation. If QA testing invocation is later proposed, that
is a materially different, larger milestone and should be scoped
separately, not bundled here.

**Milestone 3D — Security PASS → Release prep (`READY_TO_RELEASE`).**
Same pattern, final gate before release. Explicitly **not** automated
deployment — the `deployments.founder_authorized` DB-enforced `CHECK`
constraint already makes autonomous deployment structurally impossible
regardless of any Phase 3 milestone; this stays true after 3B/3C/3D ship,
by design, forever, and should be reaffirmed rather than touched by any
future milestone.

**Explicitly NOT proposed, and should stay unauthorized:**
any code path that writes `deployments.founder_authorized=1` itself;
any automated re-invocation of Developer on REJECT (Phase 3A's own
precedent — REJECT is always a mechanical status rollback, never a new
agent invocation, and every milestone above should keep that discipline);
automated QA *testing* invocation (see 3C above); any expansion of
`risks.id=3`'s mitigation scope — that stays TASK-017's job, paused,
resumed separately per DEC-008's own resume condition.

Each of 3B/3C/3D should ship and be reviewed independently, in that
order, the same discipline Phase 3A itself used (Part A, then Part B,
per Red Team's own recommendation at the time). None of the three is a
prerequisite for Founder testing to begin — see Part 4.

---

## Part 3 — Founder Work Progress / Task Progress capability (design only)

This is the most concrete, testable item in the Founder's directive, so
it gets the most design depth. **Core principle, stated first because it
governs every choice below: the existing operational database is the
source of truth. No new table is proposed that would create a second,
parallel notion of "gate" or "progress" that could drift from
`task_status_history`/`review_results`/`qa_results`/`approvals`. Every
number this design produces is a computed read, the same discipline
`derived_state.py` already uses for `company_health()`, `STAGE_MAP`, and
`task_progress_fraction()`.**

### 3.1 What "gate" means, formally

A gate = one occupancy of a `tasks.status` value, bounded by two
`task_status_history` rows (the row that entered it, and either the next
row for that task, or "still open" if it's the task's current status).
The six-stage/named-substate structure already exists —
`derived_state.STAGE_MAP` maps every status to `(major_stage, substate)`;
no new stage taxonomy is needed. A gate's real-world label is exactly
that substate (`"Architecture"`, `"Red Team Review"`, `"Code Review"`,
`"QA"`, `"Security"`, etc.).

For each gate occupancy, four facts are derivable, all from data that
already exists:

1. **Entered / exited** — `task_status_history.changed_at` for the entry
   row, and the next row's `changed_at` (or "now," if still open).
2. **Verdict while occupied** — any `review_results`/`qa_results` row for
   that `task_id` whose `created_at` falls between entry and exit. A
   `pass` (or a `reject`/`fail` immediately followed by a rollback
   `task_status_history` row) tells you whether this occupancy ended in
   success or was bounced.
3. **Who acted** — `changed_by_agent` on the entry row, or (more
   precisely, for review-type gates) `reviewed_by_agent`/
   `tested_by_agent` on the matching `review_results`/`qa_results` row.
4. **Founder action needed** — `tasks.status = 'FOUNDER_APPROVAL'`, OR an
   `approvals` row for this `task_id` with `decision IN ('pending',
   'discuss')`.

**One real schema fix this design depends on, flagged as a recommendation,
not implemented here**: widen `review_results.review_type`'s `CHECK`
constraint from `('code','security')` to `('code','security','red-team')`
— a one-line, additive, backward-compatible constraint change (existing
`'code'`-mislabeled Red Team rows would need a one-time data correction
UPDATE, or could be left as historical artifacts and only the constraint
widened going forward — a Developer-stage decision, not an architecture
one). Without this fix, a gate-derivation query cannot cleanly
distinguish "Code Review rejected this" from "Red Team rejected this
architecture" by `review_type` alone; it currently has to fall back to
`reviewed_by_agent = 'red-team'`, which works today only because no other
reviewer happens to share that name — a fragile coincidence, not a
guarantee.

I am **not** proposing a `task_gates` table. Every fact above is a join,
not new state — persisting it separately would create exactly the
"second project-management system" the Founder explicitly forbade, and
would need its own write discipline to stay correct, which is strictly
more risk than a read-only computed view for zero added value.

### 3.2 Rejection-bounce-count query (real, runnable against today's schema)

```sql
-- Total times a task's work was sent backward by a reviewer or QA,
-- across its whole lifetime. Real example: TASK-017 = 3
-- (1 Security CONCERNS-as-reject + 2 Red Team REJECTs), verified
-- directly against review_results ids 48-51 while writing this document.
SELECT task_id, COUNT(*) AS bounce_count
FROM (
    SELECT task_id, created_at FROM review_results WHERE result = 'reject'
    UNION ALL
    SELECT task_id, created_at FROM qa_results     WHERE result = 'fail'
)
WHERE task_id = ?
GROUP BY task_id;
```

This is exactly derivable today, no schema change required (the
`review_type` widening in §3.1 improves *labeling* of a bounce, e.g.
"bounced by Red Team" vs. "bounced by Code Review" — it does not change
whether the bounce is countable).

### 3.3 Sketch: what the actual page would show

Precedent: `/agents/<name>.html` and `/meetings/<id>.html` are already
real, per-entity dynamic detail routes in `server.py` — matched by regex
(`AGENT_NAME_RE`, an equivalent `TASK_ID_RE` here), 404'd on a missing
row, rendered by a `build_*_detail(conn, row, token=...)` function shared
between `server.py`'s live GET handler and a batch `generate_*.py`
script, the exact pattern `generate_agents.py`'s `build_agent_detail()`
already establishes. The proposed page follows this precedent directly:
a new `ops/control-center/generate_task.py` with `build_task_detail(conn,
task_row, token=...)`, wired into `server.py` as `GET /tasks/<id>.html`
(next to the existing `/agents/<id>.html`/`/meetings/<id>.html` pattern),
plus a link from every existing task card (`pipeline.html`,
`reviews.html`'s task-group headers, the Founder Inbox) that currently
only anchors to `pipeline.html#task-{id}` — those become real links to
this new page.

Rendered sections, using TASK-017 as the worked real example (this
session's own history is genuinely the best available test case, per the
Founder's own suggestion):

```
TASK-017 — Risk id=3 reduction milestone: reviewer zero-tool rollout
+ self-immune Developer denylist
Status: BLOCKED (paused by Founder directive — not a technical block)
Owner: orchestrator     Elapsed since created: ~2h26m     Bounces: 3

Gates:
  [DONE]      Architecture           1 pass  (after 1 Security CONCERNS,
                                               2 Red Team REJECTs — see below)
  [CURRENT]   Development            waiting — paused mid-Development,
                                               Founder-directed, DEC-008
  [not reached] Code Review
  [not reached] QA
  [not reached] Security Review
  [not reached] Founder Approval / Release

History (most recent first):
  2026-08-31 22:00  IN_DEVELOPMENT -> BLOCKED   by orchestrator
    "Founder directive ... paused mid-Development by explicit Founder
    prioritization decision, not a technical blocker..."
  2026-08-31 21:42  Red Team: PASS   (review_results #51)
  2026-08-31 20:26  Red Team: REJECT (review_results #50) -- sys.exit()
    ordering bug in pseudocode
  2026-08-31 20:12  Red Team: REJECT (review_results #49) -- fail-open
    exit-code contract gap
  2026-08-31 20:03  Security: CONCERNS (review_results #48) -- CTO
    self-edit capability undisclosed
  2026-08-31 19:53  RED_TEAM_REVIEW -> IN_DEVELOPMENT  by orchestrator
  2026-08-31 19:38  ARCHITECTURE -> RED_TEAM_REVIEW     by orchestrator
  2026-08-31 19:38  BACKLOG -> ARCHITECTURE             by orchestrator

Founder action required: No (this task is BLOCKED by Founder direction,
not waiting on a pending decision -- see risks.id=3 for the open,
company-scoped risk this task addresses).

Estimated AI cost this task: not available -- Architecture-stage Security
and Red Team reviews for this task were interactive (human-supervised)
sessions, not captured by any cost-tracking table this codebase currently
persists. (See Part 1 §1.7 -- this gap is real and applies to every task's
interactive-review cost, not just TASK-017's.)
```

Data sources for each line, none new: `tasks` (title, status, owner,
created_at), `task_status_history` (the History section, and gate
entry/exit timestamps), `review_results`/`qa_results` (verdicts, the
bounce count per §3.2), `approvals` (Founder-action-required check),
`handoffs` (a "Handoffs" section, currently invisible anywhere else in
the product — see §1.3 — belongs naturally on this page), and, once the
§1.7 `agent_runs.cost_usd` gap is closed, a real per-task cost rollup
(`SUM(cost_usd)` across every `agent_runs`/`automation_events`/
`reviewer_invocations` row scoped to this `task_id`).

### 3.4 What this design explicitly does not add

No new mutable table. No second status enum. No write path this page
itself owns (it is read-only, same discipline as `pipeline.html`/
`reviews.html`/`decisions.html` today). The one recommended schema change
(`review_type` widening, §3.1) is additive and backward-compatible, not a
redesign. The one recommended cost-tracking addition (`agent_runs.
cost_usd`, §1.7/§3.3) is a single nullable column with three known call
sites already holding the value — small enough to fold into this same
milestone rather than needing its own separate one, but that is a
Developer/CTO sequencing call at implementation time, not decided here.

---

## Part 4 — Founder Test Readiness: technical assessment

**On the exact list**: I do not have verbatim access to the Founder's
original 13-point directive text beyond this task's own paraphrase, which
names 11 distinct capabilities explicitly. I reconstruct against those 11
and flag two additional plausible items consistent with the rest of the
directive and this document's own Part 1 findings, clearly marked as
reconstruction rather than verbatim. If the actual list differs, Chief of
Staff should reconcile against the source text directly — this table is
not to be treated as authoritative phrasing, only as an evidence-based
readiness check against the capabilities named.

| # | Capability (Founder's own framing) | Status | Evidence |
|---|---|---|---|
| 1 | Start a real idea with Chief of Staff | **PARTIAL** | `POST /api/chief-of-staff/ask` is real and conversational (§1.4), but it is zero-tool by design and cannot itself create a `tasks` row — task creation remains CLI-only (`opsdb.py task-create`), with no Founder-facing write path from a conversation into a real task. |
| 2 | Watch agents structure it (decomposition into steps) | **MISSING** | `task_steps` has 4 rows total, ever, all from TASK-001's fake walkthrough (§1.2). No automated or guided decomposition step exists for a new idea. |
| 3 | See task ownership | **DONE** | `tasks.current_owner`, rendered on every `pipeline.html` card (`generate_pipeline.py` line 79, via `display_name()`). |
| 4 | Watch handoffs | **MISSING** | `handoffs` table is real (3 rows) but has zero Founder-facing visibility anywhere in the Control Center today (§1.3). |
| 5 | See rejections and fixes | **DONE** | `reviews.html` (Milestone 2B5) — full `review_results`/`qa_results` history grouped by task, including "Returned to X." |
| 6 | Talk naturally with Chief of Staff | **DONE (proven, not yet exercised live)** | The mechanism is real and shipped (§1.4); the live database currently has 0 `messages` rows — every real exchange to date ran against a scratch/isolated database by deliberate safe-testing design, not the persistent record. |
| 7 | Ask any agent's perspective | **DONE, bounded** | Ask-Agent + Executive Meetings + Chief of Staff's `CONSULT:` mechanism all real; "any agent" is bounded by `agent_runtime`'s allowlists, not literally all 14. |
| 8 | See overall project status | **DONE** | `overview.html` (Milestone 1) + `CURRENT_STATUS.md`, both DB-derived. |
| 9 | See what needs a Founder decision | **DONE** | Founder Inbox (`/inbox.html`, Milestone 2B1), backed by `approvals.decision IN ('pending','discuss')`. |
| 10 | Understand AI cost | **PARTIAL** | Real per-call cost is measured (§1.7) but only persisted for the automation poller; `automation.html` shows automation-only spend, not company-wide spend. Ask-Agent/Meeting/Chief-of-Staff costs are computed and discarded. |
| 11 | Stop automation at will | **DONE** | `automation.html`'s kill switch, `POST /api/automation/{stop,start}`, `automation_state` table (currently `enabled=0` — off by default; confirmed live). |
| 12 *(reconstructed)* | See individual agent status/availability | **DONE** | `agents.html` (Milestone 2A) + per-agent detail pages. |
| 13 *(reconstructed)* | Understand what's automated vs. still human-mediated | **PARTIAL** | `automation.html` + Chief of Staff's digest narrate the one automated path accurately, but there is no single page stating "here is everything that is and isn't automated right now" — the Founder would need to read `ROADMAP.md`/this document to get the full picture. |

**Smallest milestone set before serious Founder testing can begin** (not
"complete the architecture," per the Founder's own explicit instruction
against postponing testing for that):

1. **The Founder Work Progress / task detail page (Part 3), including the
   Handoffs section.** Read-only, zero new write paths, zero new
   automation risk, directly closes gaps #2 (visible, even if not
   automated, decomposition — the page can honestly show "not broken into
   steps" the same way `task_progress_pct()` already does), #4 (handoffs),
   and materially improves #13.
2. **Company-wide AI cost visibility** (`agent_runs.cost_usd` column +
   a simple aggregate view/section, §1.7/§3.3). Additive, low-risk,
   closes #10 for real rather than partially.
3. **Nothing from Part 2's Milestone 3B/3C/3D is required before testing
   begins.** The Founder can already watch a real Developer→Code-Review
   handoff happen automatically (Phase 3A, shipped), talk to Chief of
   Staff, ask any agent, see status/ownership/rejections, and stop
   automation — a genuine, working, narrow product surface exists today.
   Further orchestration automation adds coverage, not a missing
   precondition for testing to start.

Item #1 (task creation from a Chief-of-Staff conversation) is the one
gap I do not recommend closing before testing: it requires a new write
path (a chat-originated task-create action), which is exactly the kind
of scope-creep the Founder warned against enabling without deliberate,
separate review. The Founder can begin testing today by having Chief of
Staff discuss an idea, then creating the resulting task via the existing
CLI — a real, if less polished, path — while #1's UI gap is assessed
later on its own merits.

---

## Part 5 — Role-level + task-level security: target architecture (restated, not re-derived)

This section restates, it does not re-derive, TASK-016/017's already-
completed investigation (`ops/reviews/cto-risk3-architecture-
investigation.md`, `chief-of-staff-risk3-synthesis.md`,
`cto-risk3-milestone-architecture.md`) and DEC-008's pause.

**Target architecture, unchanged by this document:**
- **Role-level**: every execution-role agent (Developer, QA, CTO, DevOps)
  gets a `PreToolUse` hook narrowing its normal Bash/Write/Edit access to
  what that role legitimately needs, rather than the current unscoped
  Bash-tool-category grant every subagent frontmatter implies but does
  not enforce.
- **Task-level**: a further narrowing, per active task, to only the paths
  that specific task needs (the Founder's own `/src/payments/**`
  example) — proposed in the TASK-016 synthesis, explicitly flagged with
  unresolved Security CONCERNS ("defaults to allow-broad, risking scoping
  that looks real but isn't"), never built.

**What is technically enforced today, stated plainly, with no
overclaiming**: exactly what TASK-017 already built — a single,
role-level Developer denylist hook (`developer_pretooluse.py`), wired
into `.claude/agents/developer.md`. This code exists, is committed, and
has passed **only** its pre-Development architecture review (one
Security CONCERNS fixed, two Red Team REJECTs fixed, final PASS). It has
**not** passed Code Review, QA, a Security-adversarial pass, or CTO
conformance on the actual implementation — per DEC-008, it must not be
treated as validated, safe, or shipped. Every other agent (CTO, QA,
DevOps, and all seven review/executive roles) has **zero** technical
tool-access enforcement beyond the frontmatter `tools:` list itself,
which the harness enforces at the tool-category level only (Bash is
Bash — no path or command scoping) — exactly `risks.id=3`'s original,
still-`open` finding.

Task-level narrowing (the `/src/payments/**` example) does not exist in
any form, built or paused — it is further out than TASK-017's own scope
ever reached. This remains a pure target for when security work resumes,
per DEC-008's own stated resume condition (before any broader unattended
automation, external users, production credentials, production
deployment automation, or multi-user access).

---

## Part 6 — Review and correction of `ROADMAP.md`'s just-added section

### 6.1 Phase-count fix: found an error, corrected

`ROADMAP.md` line 3 (before my edit) read: *"Three phases are currently
defined and gated (Phase 0-3 below...)"*. This is internally
inconsistent: Phase 0, Phase 1, Phase 2, and Phase 3 are four distinct,
separately gated phases (each with its own heading, its own DEC-00x
approval, and its own scope) — "Phase 0-3" inclusive is four items, not
three. The surrounding correction note explains this line was rewritten
to fix a *different*, already-resolved inconsistency (the file
previously promised "Four phases" numbered 1–4 while sections were
actually labeled 0–3) — but the rewrite introduced a new, smaller
off-by-one error in the total count. I corrected this: **"Three phases"
→ "Four phases."** No other part of that sentence or the surrounding
correction note needed to change — the note's own explanation of what
was wrong before remains accurate history and was left as-is.

### 6.2 PROPOSED PHASE 4 section: reviewed, no correction needed

Checked against everything found in Parts 1–5: the section correctly
states it is "NOT STARTED, NOT APPROVED," correctly scopes itself as
avatar/voice/identity work with no overlap with the remaining Phase 3
orchestration or Founder Work Progress work this document designs, and
correctly restates the phase-gate Rule ("a phase that is technically easy
to start early is still not started early"). No factual claim in it
conflicts with anything verified in this document. No edit made.

### 6.3 One addition: a pointer to this document

Added one sentence at the end of the "Remaining Phase 3 /
Founder-testability architecture" paragraph (Phase 3 section) pointing to
this document by filename, matching this file's own established
convention of citing the actual review document once produced (every
other milestone in `ROADMAP.md` does this). This does not mark Phase 3B/
3C/3D, the Founder Work Progress page, or any other proposal in this
document as approved or shipped — it only makes the now-existing document
findable from the roadmap, the same as every prior `ops/reviews/*.md`
citation in this file.

---

## Summary of evidence gaps disclosed (for Chief of Staff's synthesis)

Restated once, plainly, so nothing here is buried: `risks.id=3` remains
`open`. TASK-017's implementation is unreviewed beyond architecture stage
and must not be treated as shipped. The live operational database has
zero `messages`/`meetings`/`automation_events` rows despite the
underlying mechanisms being real and independently tested — Founder
testing will be the first time these are exercised against the company's
actual persistent record. Company-wide AI cost visibility does not exist
today despite real per-call cost data being computed and then discarded
for three of four invocation types. No part of this document claims
otherwise anywhere above.
