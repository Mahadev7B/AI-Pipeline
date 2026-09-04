# CTO — Product Architecture Completion Assessment, v2 (TASK-018)

Date: 2026-08-31
Author: CTO
Directive: Founder's formal correction to `ops/reviews/cto-product-architecture-completion.md`
and `ops/reviews/chief-of-staff-product-architecture-synthesis.md`, 2026-08-31.
Scope discipline: **design and audit only.** Nothing here is implemented,
no code was written or changed, `ops/ROADMAP.md` is not touched this
round (per the Founder's explicit instruction — a later pass will update
it once this revised plan is approved). Nothing here weakens or
re-litigates the still-standing security pause: `risks.id=3` and
TASK-017 stay exactly as paused per DEC-008.

**The Founder's bar, restated so it governs every judgment below:** the
Founder-facing UI must be 100% feature-complete for the *current*
product before serious testing begins — meaning 100% of the
Founder-facing information and controls needed to operate the current
product are present, coherent, and usable, **through the actual running
Control Center**. Anything reachable only via GitHub, SQLite, a markdown
report, terminal output, or an outside AI does not count as complete,
no matter how real the underlying data is.

Every claim below is evidence-based: a specific file/line citation, or a
direct read-only query against `ops/db/operations.sqlite3`
(`python3 ops/db/opsdb.py query "..."`) run while writing this document.
Where a prior document's account conflicted with what the code actually
does, I re-derived it from the code directly and say so.

---

## Part 1 — The cost-tracking truth table, resolved from code

**Headline correction:** the prior CTO document's Part 1 §1.7 was
correct in substance. The Chief of Staff's own verbatim quoted answer
(Appendix C of the synthesis document — "Cost tracking is real and
accurate, but only gets saved for 1 of 4 ways work happens in this
system (**Ask-Agent**)") is **wrong, and backwards**. Ask-Agent does
**not** persist cost. The one path of the four that does is the
**automated Code Review poller**, not Ask-Agent. This is not a matter of
interpretation — it is directly falsifiable from the schema and the
call sites, below.

### 1.1 One shared measurement mechanism, for all four paths

Every one of the four invocation paths — Ask-Agent, Executive Meetings,
Chief of Staff, automated Code Review — calls the exact same function,
`agent_runtime.invoke_agent()` → `_run_claude()`
(`ops/control-center/agent_runtime.py:245-355`). There is only one
measurement implementation in this codebase, not four:

- **Tokens**: `_run_claude()` reads `data.get("modelUsage")`, a
  per-model dict of `inputTokens`/`outputTokens`
  (`agent_runtime.py:341-348`) — this is real, captured from the
  `claude` CLI's own `--output-format json` output, not estimated. But
  it is used **only** to pick `model_used` (whichever model produced the
  most output tokens) — the actual token counts are never placed on
  `RuntimeResult` and never persisted anywhere, for any of the four
  paths. `RuntimeResult` (`agent_runtime.py:233-242`) has no token
  fields at all.
- **Cost**: `cost_usd=data.get("total_cost_usd")`
  (`agent_runtime.py:353`) — the CLI's own real, measured total cost for
  that one invocation. Identical for all four callers; there is no
  separate cost-calculation logic anywhere else in this codebase.

So for **"are tokens measured"** and **"is a dollar cost calculated"**,
the answer is **yes, identically, for all four paths** — this part of
the prior document's claim was accurate and needs no correction.

### 1.2 Persistence — verified per path, per table/column

| Path | Where invoked | Run table used | Cost param accepted? | Persisted? |
|---|---|---|---|---|
| Ask-Agent | `server.py:_handle_ask()` (`server.py:693-793`), via `opsdb.start_ask_agent_run()` / `opsdb.end_run()` | `agent_runs` | `end_run(conn, run_id, status)` — **status only** (`opsdb.py:408-428`); `agent_runs` has **no `cost_usd` column** (`schema.sql:95-115`) | **NO.** `server.py:770`, `result = agent_runtime.invoke_agent(...)`; `result.cost_usd` is never read again in that function — discarded. |
| Executive Meetings | `meeting_orchestrator.py`: `_gather_position()` (198-211), `gather_requested_position()` (452-511), `retry_position()` (610-645), plus `_select_participants()`/`_synthesize()` (no run row at all) — all via `opsdb.start_run()`/`opsdb.end_run()` | `agent_runs` | Same `end_run()` — status only | **NO.** Every one of these functions computes `result.cost_usd` (implicitly, inside `RuntimeResult`) and never passes it anywhere. |
| Chief of Staff conversations | `chief_of_staff.py:ask_chief_of_staff()` (340-429), via `opsdb.start_ask_agent_run()`/`opsdb.end_run()` | `agent_runs` | Same `end_run()` — status only | **NO.** `chief_of_staff.py:374` and `:400` both call `invoke_agent()` and use only `result.ok`/`result.response_text`/`result.error_kind` — `result.cost_usd` is never referenced. |
| Automated Code Review (poller) | `automation.py:_invoke_and_record()` (456-542) | `agent_runs` (for the run itself, status only) **and** `automation_events` | `opsdb.end_automation_event(conn, event_id, status, ..., cost_usd=result.cost_usd, ...)` (`automation.py:488,508,527,540`) → `automation_events.cost_usd REAL` (`schema.sql:303`) | **YES.** Confirmed: this is the one and only path in the codebase that carries `result.cost_usd` into a persisted column. |

**Visible in the current Founder UI?**

| Path | Visible? | Evidence |
|---|---|---|
| Ask-Agent | **NOT visible anywhere.** | `generate_agents.py:render_ask_agent_section()` (123-211) renders the chat panel — no cost/$ field anywhere in it, and there is nothing to show even if it wanted to (no persisted number exists). |
| Executive Meetings | **NOT visible anywhere.** | `generate_meetings.py` has zero references to "cost" (`grep` confirms). |
| Chief of Staff | **NOT visible anywhere.** | Same `render_ask_agent_section()` component (reused for `orchestrator`, `generate_agents.py:133-136`) — no cost field. |
| Automated Code Review | **Visible, but automation-only.** | `automation.html` shows a per-event cost (`generate_automation.py:153`, `cost = f' — ${r["cost_usd"]:.2f}'`) and today's aggregate spend against the $10.00 ceiling (`render_spend()`, `generate_automation.py:110-121`) — but this is scoped exclusively to `automation_events` rows, i.e. only what the unattended poller itself has spent. It says nothing about Ask-Agent, Meetings, or Chief of Staff spend. |

### 1.3 One more real fact worth disclosing plainly

A fifth invocation category exists in code — the three synchronous
reviewer routes from TASK-017 (`reviewer_sync.py`, paused,
Development-complete but unreviewed beyond architecture stage per
DEC-008). Those routes **do** pass `cost_usd` into a
`reviewer_invocations.cost_usd` column (`reviewer_sync.py:290-306`,
`schema.sql:344-362`). This is irrelevant to what ships today for two
independent reasons: (1) the whole feature is paused and must not be
treated as shipped; (2) I confirmed directly against the live database
(`sqlite_master`, both `reviewer_invocations` and `hook_denials` absent)
that this table **does not exist in the live `operations.sqlite3`** —
`schema.sql` was edited after the database was last initialized and
`opsdb.py init` has not been rerun. Even if the pause were lifted today,
this code path could not currently write to a table that doesn't exist
live. Not a design defect — `CREATE TABLE IF NOT EXISTS` makes rerunning
`init` safe and idempotent — but a real, current fact.

### 1.4 Conclusion

**Company-wide AI cost visibility does not exist today.** Real, measured
cost is computed on every single invocation of every kind, and then
discarded for 3 of 4 (Ask-Agent, Meetings, Chief of Staff) — persisted
for only 1 of 4 (the automation poller), and even that one is visible to
the Founder only in a page scoped to automation's own spend, not the
company's. This is the same bottom-line severity as the prior CTO
document reached — but the exact mechanism differs from what both prior
documents said, and precisely which path is the "working" one was
previously reported backwards. This correction is the reason the
Founder was right to ask for it to be re-verified from code before any
milestone was designed against it.

---

## Part 2 — Full Founder UI completeness audit

Audited directly against `server.py`'s live route table
(`server.py:393-488`, the only GET routes that exist) and every
`generate_*.py` file. Rule applied throughout: something backed only by
a SQLite query, a markdown file, or a value computed-and-discarded in
Python is not COMPLETE, regardless of how real the underlying mechanism
is.

| Screen / capability | Status | Evidence |
|---|---|---|
| Company Overview | **COMPLETE** | `/overview.html` (`server.py:416-418`), `generate_overview.py` — company health, active-now agents, recent activity, all DB-derived. |
| Active Work / Progress (company-wide) | **MISSING** | No route exists. `pipeline.html` shows a kanban board of current stage/substate + %-complete per task, but no bounce count, no elapsed time, no per-task Founder-action-required flag, no click-through detail. Nothing aggregates "every active task at a glance" the way the Founder's own example shows. |
| Project / Phase Progress | **MISSING** | No `phase` concept exists anywhere in `schema.sql` (confirmed: `tasks`, `decisions`, `projects` — none has a phase/milestone column). Phase 0-3/3A state exists **only as prose** in `ROADMAP.md`, which the Founder would have to open directly — this fails the Founder's own bar by definition. See Part 4. |
| Task Detail | **MISSING** | No `/tasks/<id>.html` route in `server.py`'s route table (confirmed exhaustively — only `/agents/<name>.html` and `/meetings/<id>.html` exist as dynamic detail routes; no `TASK_ID_RE`, no `generate_task.py` file exists). Every card that names a task (`pipeline.html`, `automation.html`, `reviews.html`) links at most to `pipeline.html#task-{id}`, a same-page anchor jump, never a real detail page. |
| Pipeline | **PARTIAL** | `/pipeline.html` real and DB-derived (`generate_pipeline.py`) — shows stage/substate columns, owner, %-complete (`task_progress_fraction()`), a "Needs Attention" panel for BLOCKED/FOUNDER_APPROVAL. Missing: bounce count, elapsed time, click-through to any detail page (cards are dead ends beyond the same page). |
| Agents | **COMPLETE** | `/agents.html`, `generate_agents.py:build_roster_html()`. |
| Agent Detail | **COMPLETE** | `/agents/<name>.html`, `generate_agents.py:build_agent_detail()` (214-311) — status, activity, evaluation/decision history, risks owned/raised **for that one agent**, Ask-Agent panel. |
| Chief of Staff | **COMPLETE (mechanism), reachable, but not top-level nav-discoverable** | Lives on `/agents/orchestrator.html` via the shared `render_ask_agent_section()` component, posting to `POST /api/chief-of-staff/ask` (`generate_agents.py:133-136`). Real, persisted, clickable through the actual UI — this genuinely satisfies the Founder's bar (Agents → Orchestrator). It is not a first-class nav-bar item, which is a minor discoverability nit, not a completeness failure. |
| Ask-Agent | **COMPLETE** | Same `render_ask_agent_section()`, on `/agents/{cto,qa,ceo,financial,project-manager}.html`. |
| Executive Meetings | **COMPLETE** | `/meetings.html` (create-meeting form, `generate_meetings.py:62`) + `/meetings/<id>.html` (positions, synthesis, request-perspective/followup/retry/decide forms — `generate_meetings.py:211,257,328,377`). |
| Founder Inbox | **COMPLETE** | `/inbox.html`, `generate_inbox.py`, `approvals.decision IN (pending,discuss,approve,reject)`. |
| Approvals | **COMPLETE** | Same as Inbox — the `approvals` table is the Inbox's data source; the "risks" text field shown per-approval (`generate_inbox.py:102`) is a free-text field on that one approval row, not the company risk register (see below). |
| Decisions | **COMPLETE** | `/decisions.html`, `generate_decisions.py`. |
| Activity | **PARTIAL** | `agent_activity` (33 live rows) is real, but only ever shown as a capped excerpt: last 8 company-wide on Overview (`generate_overview.py:82-88`), last 10 per-agent on that agent's own detail page (`generate_agents.py:226-230`). No full, filterable, company-wide activity log/page exists. |
| Code Review history | **COMPLETE** | `/reviews.html`, `generate_reviews.py` — full `review_results` (`review_type='code'`) history grouped by task. |
| QA history | **COMPLETE** | Same page — full `qa_results` history, same grouping. |
| Security findings | **PARTIAL** | `review_results` rows with `review_type='security'` render on the same `reviews.html` page (pass/reject, findings text) — this part is real and visible. But the company's actual open security risk (`risks.id=3` — the reason DEC-008 paused work at all) has **zero** Founder-facing page anywhere (see Risks, below), and TASK-017's own audit trail (`hook_denials`) has neither a live table nor any UI. The Founder can see individual security review verdicts but not the standing security risk picture. |
| Risks | **MISSING** | No `/risks.html` or equivalent route exists anywhere. The `risks` table is rendered **only** as a filtered slice on an individual Agent Detail page (`risks_owned`/`risks_raised` scoped to that one agent, `generate_agents.py:244-251`) — there is no company-wide open-risk register a Founder can browse. `risks.id=3`, the specific, named, still-`open` risk this entire pause is about, is not reachable from any Control Center page today — only from `DECISIONS.md`/review documents, which fails the Founder's own stated bar directly. |
| Automation status | **COMPLETE** | `/automation.html`, `generate_automation.py`. |
| Current running automation | **COMPLETE** | `render_running()`, `generate_automation.py:124-135`. |
| STOP/ON/OFF controls | **COMPLETE** | `render_kill_switch()`, `generate_automation.py:71-107`; `POST /api/automation/{stop,start}`. |
| Releases | **COMPLETE** | `/releases.html`, `generate_releases.py`. |
| Release readiness | **COMPLETE** | `derived_state.release_readiness_gap()` (`derived_state.py:321-340`), rendered on `releases.html:106`. |
| AI usage/cost (company-wide) | **MISSING** | See Part 1. Automation-only spend is COMPLETE for its own narrow scope; nothing shows Ask-Agent, Meeting, or Chief-of-Staff spend, individually or aggregated, anywhere. |
| Founder-action-required visibility | **PARTIAL** | Founder Inbox covers `approvals.decision IN (pending,discuss)` fully. Pipeline's "Needs Attention" panel covers `BLOCKED`/`FOUNDER_APPROVAL` tasks. But there is no single, consistent "Founder action required: yes/no" signal rendered per task, and no one page that unifies both sources — a Founder has to check two different pages and mentally combine them. |
| Stuck-work visibility | **MISSING** | No bounce-count anywhere in the UI (only derivable by a direct SQL query — see the prior document's Part 3.2, still valid). No "how long has this gate been open" indicator anywhere. A task silently sitting at `CODE_REVIEW` for a week with no action looks identical, in every page that shows it, to one that just arrived a minute ago. |
| Navigation between all screens | **PARTIAL** | The 9 built top-level pages share one consistent nav bar (`layout.py:39-49,74-112`) — this part is solid. But several real capabilities (Chief of Staff, the risk register, task detail) are either not nav-reachable or don't exist to be reached; several existing links point at same-page anchors (`pipeline.html#task-{id}`) rather than real destinations, which reads as a working link but isn't one. |
| Empty states | **COMPLETE** | Explicit, honest empty-state copy confirmed across pages: "No agent currently has an open run.", "Nothing in backlog.", "No automated events recorded yet.", "No conversation yet.", "No requests yet", "No evaluation or decision history recorded for this agent yet.", "No activity recorded yet." — this codebase's empty-state discipline is real and consistent. |
| Loading states | **PARTIAL** | This is a fully server-rendered, request/response architecture — no client-side JS/AJAX anywhere. A real invocation (Ask-Agent typically 3-13s, a review up to 120s) blocks the HTTP request with no in-page loading indicator; the only feedback is the browser's own native "waiting" state, then a full page reload showing "In progress…" only if the Founder reloads mid-flight (`generate_agents.py:184-186`). Functionally honest (never shows a fake "done" state) but not a designed loading experience — a Founder could reasonably think the page is frozen for up to two minutes on a review call. |
| Error states | **COMPLETE** | `_error_page()` for 400/404/409/500, `setup_required_page()` for the fail-closed 503 credential gate, a login-failure error panel, and honest per-agent "Last request failed" status (`generate_agents.py:188-189`). |

**Headline count**: of the 30 items audited, **16 COMPLETE, 7 PARTIAL,
7 MISSING**. Every MISSING/PARTIAL item traces to one of a small number
of real, closable gaps — not 7+ unrelated problems. See Part 6.

---

## Part 3 — Company-wide Active Work / Progress dashboard (design only)

### 3.1 Governing principle, unchanged from the prior document

The operational database stays the single source of truth. No new
mutable table is proposed. This design is a **computed read**, following
`derived_state.py`'s own existing discipline
(`company_health()`, `STAGE_MAP`, `task_progress_fraction()`,
`release_readiness_gap()`) — extended, not duplicated.

### 3.2 What one row of "Active Work" is, and where each field comes from

One row per task where `status != 'DONE'` (mirrors
`derived_state.active_tasks_digest()`'s own existing filter,
`derived_state.py:158-172`, reused as the base query rather than
reinvented):

| Field | Source | Status today |
|---|---|---|
| Project / Phase / Milestone | `tasks.project_id` → `projects`, plus a phase label | **Gap — see Part 4.** `projects` is real but single-implicit today (1 row, everything else `NULL`); phase has no data source at all yet. Until Part 4's schema addition ships, this column honestly renders "—" rather than a fabricated value. |
| Current gate | `derived_state.stage_and_substate(tasks.status)` | Exists today, unchanged (`derived_state.py:120-139`). |
| Current owner | `tasks.current_owner` | Exists today, already rendered on `pipeline.html`. |
| Gates completed / remaining | `task_progress_fraction(conn, task_id)` | Exists today (`derived_state.py:72-84`), already used by `pipeline.html`'s progress bar. |
| Rejection/bounce count | The exact query from the prior document's §3.2 (`review_results.result='reject'` UNION `qa_results.result='fail'`, grouped by `task_id`) | Real, runnable today, no schema change required. |
| Whether work is stuck | A disclosed, honest definition — proposed: **"no `task_status_history`/`review_results`/`qa_results` row for this task in the last N days while status is not `FOUNDER_APPROVAL`/`BLOCKED`" (both of which already have their own, better-labeled Needs-Attention treatment).** N is a single, disclosed constant (e.g. 3 days), not a vibe — same "one disclosed number" discipline `agent_runtime.MAX_STATE_DIGEST_CHARS` etc. already use. This needs a CTO architecture review of its own threshold, not decided finally here. | New computed logic, no schema change. |
| Last important event | `MAX(created_at)` across `task_status_history`/`review_results`/`qa_results` for this `task_id` | Real, joinable today. |
| Next expected action | `tasks.next_action` | **Already exists as a real column** (`schema.sql:64`) — currently populated inconsistently by agents but real data, not invented. |
| Founder action required | `tasks.status = 'FOUNDER_APPROVAL'` OR an `approvals` row for this `task_id` with `decision IN (pending,discuss)` | Same logic as the prior document's Task Detail design (§3.1 item 4) — reused, not duplicated. |
| Elapsed time | `tasks.created_at` → now, and/or current-gate-entry → now (from `task_status_history`) | Real, computable today. |
| Cost/usage | `SUM(automation_events.cost_usd)` for this task today; everything else reads "not available" until Part 1's `agent_runs.cost_usd` gap is closed | Honest partial data today; complete once the cost-tracking milestone ships (see Part 6). |

### 3.3 Shared implementation, not a duplicate

Every one of these facts is exactly what the prior document's Task
Detail design (Part 3 there) already derives per-task. The Active Work
dashboard is the **same underlying row-builder function, called once per
active task and rendered as a table**, not a second implementation. I
propose the shared function live in `derived_state.py` as
`task_progress_row(conn, task_id) -> dict` (or similar), called by both:
`generate_active_work.py` (new — one row per active task) and
`generate_task.py` (new — one task's full detail, same fields plus
history/handoffs/findings). This is the literal meaning of "extend, don't
duplicate, whatever gate-derivation logic you already sketched for the
task-detail page" — there is now exactly one such function, used twice.

Clicking a task row opens `/tasks/<id>.html` (Part 5). No task in this
list should ever link to a page that doesn't exist — this is exactly why
Part 6 recommends shipping Active Work and Task Detail together (see
point 5).

### 3.4 What this explicitly does not add

No `task_gates` table, no second status enum, no write path this page
itself owns (read-only, same discipline as every other screen in this
codebase). Following this project's established page-generation pattern
exactly: a `generate_active_work.py` with `build_html(conn, token=...)`,
wired into `server.py`'s existing `if path == "..."` dispatch chain the
same way every other top-level page is.

---

## Part 4 — Project / Phase Progress view (design only)

### 4.1 The honest finding first, because it changes the design

**Phase/milestone state does not exist anywhere in the database today.**
I confirmed this directly against `schema.sql`: `tasks`, `decisions`,
and `projects` have no phase, milestone, or phase-status column of any
kind. Phase 0 / 1 / 2 / 3 / 3A state exists **exclusively as prose
headings** in `ops/ROADMAP.md` (`## PHASE 0 — ...`, `## PHASE 1 — ...`,
etc., confirmed by direct grep) and narrative in `DECISIONS.md`. This is
exactly the situation the Founder's own instruction anticipated: this
absence is itself a gap this design needs to close, not a detail to work
around.

### 4.2 Design: a small, explicit, additive `phases` reference table

Proposed — **not implemented here** — a small table, following this
project's existing pattern for small reference/state tables
(`automation_state`, `risks`):

```
phases (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,             -- 'Phase 0', 'Phase 1', ..., 'Phase 3A'
  status        TEXT NOT NULL CHECK (status IN ('not_started','in_progress','complete')),
  decision_id   INTEGER REFERENCES decisions(id),  -- the DEC-00x that approved/closed it
  milestones_total     INTEGER,            -- NULL if not meaningfully countable
  milestones_complete  INTEGER,
  note          TEXT,
  updated_at    TEXT NOT NULL DEFAULT (...)
)
```

Populated and updated the same way `decisions`/`automation_state` are
today — a deliberate, disclosed write by CTO/orchestrator at the moment
a phase's status genuinely changes (mirroring how `ROADMAP.md` is edited
today, just moved into a queryable table instead of prose). This is a
schema change, and — like the `review_type` widening recommendation
from the prior document — is flagged as a recommendation for a future,
separately-reviewed milestone, not something this document authorizes.

**Explicit anti-fabrication rule, per the Founder's own instruction:**
where `milestones_total`/`milestones_complete` are honestly countable
(e.g. Phase 3's four named handoffs from the prior document's Part 1),
show the real fraction. Where they are not (e.g. Phase 2's UI build-out
was not originally decomposed into a fixed, equal-weight milestone
count), show the **status enum only** (`Complete` / `In Progress` / `Not
Started`) — never a computed or estimated percentage. This is a direct,
load-bearing design constraint, not a stylistic preference.

### 4.3 What this view shows once the schema addition ships

```
PROJECT / PHASE PROGRESS
Phase 0 — Complete        (DEC-003)
Phase 1 — Complete        (DEC-004)
Phase 2 — Complete
Phase 3 — In Progress     (1 of 4 defined handoffs automated — see below)
  Phase 3A — Complete     (2 of 2 parts shipped: conversational interface + one automated handoff)
Currently authorized work: TASK-018 (Product Architecture, this task)
```

Each phase row links to its approving `decisions` row (real, existing
data) and, once Part 3 ships, to the Active Work rows currently
associated with it. No page reads `ROADMAP.md` at runtime — the whole
point is that this becomes independently queryable, structured data,
with `ROADMAP.md` staying as the longer-form narrative document it
already is, not a required read for the Founder to know current phase
status.

### 4.4 If the schema addition is deferred

If the `phases` table is not prioritized for the immediate Founder Test
Readiness milestone set, the honest fallback is **not** a page that
silently reads `ROADMAP.md` at runtime (still fails the Founder's bar
identically to today) — it is simply **not building this page yet** and
saying so plainly, which is what I recommend for the initial milestone
set (see Part 6, item 10) given it's lower-frequency information than
Active Work/Task Detail/Cost.

---

## Part 5 — Task Detail page, revised

The prior document's Part 3 design (gate = one `tasks.status` occupancy,
bounded by `task_status_history` rows; bounce-count query; no new
mutable table; the `review_type` widening recommendation) remains
correct and is not re-derived here. This section extends it against the
Founder's fuller list and the additional evidence gathered this round.

### 5.1 Gate lane states, defined precisely

- **DONE** — a gate the task has fully passed (occupied, then exited via
  a forward `task_status_history` transition).
- **CURRENT** — the gate matching `tasks.status` right now.
- **WAITING** — a gate later in the pipeline order than the current one,
  not yet reached.
- **REJECTED** is not a fourth lane state (a task is never "at" a
  rejected gate as its current position) — it is an **outcome recorded
  inline within a DONE gate's own history**, exactly as the prior
  document's TASK-017 worked example already showed: `[DONE] Architecture
  1 pass (after 1 Security CONCERNS, 2 Red Team REJECTs)`. This section
  makes that convention explicit rather than implicit.

### 5.2 CTO final conformance — a real, evidenced pattern, not invented

The Founder's own list names "CTO final conformance" as a distinct thing
to show. I confirmed this is a real, existing, if informally-labeled,
practice: `review_results` rows with `reviewed_by_agent='cto'` exist
today (5 live rows — ids 16, 21, 25, 29, 32 — every one a `review_type='code'`,
`result='pass'` row for a CTO-performed conformance pass on a completed
task). No schema change is needed to show this — the Task Detail page's
History section already renders `reviewed_by_agent` per row; it should
simply label a `reviewed_by_agent='cto'` row distinctly (e.g. "CTO
Conformance") in the rendered gate history, the same way it already
must special-case `reviewed_by_agent='red-team'` today (per the prior
document's §3.1 workaround note).

### 5.3 Sections, complete list

Following the prior document's precedent exactly (`GET /tasks/<id>.html`,
`generate_task.py:build_task_detail(conn, task_row, token=...)`, same
shape as `build_agent_detail()`/`build_meeting_detail()`):

1. **Header** — title, status, owner, elapsed time (created_at → now).
2. **Gate timeline** — DONE/CURRENT/WAITING lanes per §5.1, each DONE
   lane's inline reject/pass history per §5.1/§5.2.
3. **Bounce count** — the prior document's §3.2 query, surfaced as a
   single number plus the events it's built from.
4. **Status history** — full `task_status_history`, most recent first
   (already designed in the prior document).
5. **Handoffs** — the `handoffs` table, currently invisible anywhere in
   the product (§ Part 2 of this document) — belongs here, per-task.
6. **Code Review / QA / Security findings** — `review_results`/`qa_results`
   filtered to this task, with the `review_type` widening
   recommendation (prior doc §3.1) so Red Team/CTO-conformance rows are
   cleanly labeled rather than lumped under `'code'` by convention alone.
7. **Founder decisions/approvals** — any `approvals` row for this task,
   any linked `decisions` row.
8. **Associated risks** — `risks` rows scoped to this task
   (`scope_type='task', scope_id=<id>`) — this is new relative to the
   prior document's design, and directly closes part of the company-wide
   Risks gap from Part 2 (a task-scoped risk becomes visible the moment
   its task has a detail page, even before a company-wide risk register
   exists).
9. **Activity timeline** — `agent_activity` rows for this task
   (`task_id` column already exists on that table), currently only
   visible in capped form on Overview/Agent-Detail — a task-scoped view
   is a real, additive improvement.
10. **Next expected action** — `tasks.next_action`, real column, today
    unused in any UI.
11. **Cost/usage** — honest "not available" until Part 1's `agent_runs.cost_usd`
    gap closes; a real per-task rollup once it does.

### 5.4 Acceptance test — TASK-017, unchanged

TASK-017's real, messy, three-round review history (1 Security CONCERNS
+ 2 Red Team REJECTs, final PASS, then paused mid-Development by
explicit Founder directive) remains the design's own best real test
case, exactly as the prior document used it — nothing about this
revision weakens that; if anything, §5.2's CTO-conformance labeling and
§5.3 item 8's risk linkage make the rendered TASK-017 page more complete
than the prior sketch, since TASK-017's own driving risk (`risks.id=3`)
is `scope_type='company'` and would appropriately NOT show under item 8
— visibly correct behavior, not a gap in this specific case.

---

## Part 6 — The revised recommendation

### 1. What UI is truly complete today (with evidence)

16 of 30 audited items: Company Overview, Agents, Agent Detail, Chief of
Staff (mechanism), Ask-Agent, Executive Meetings, Founder Inbox,
Approvals, Decisions, Code Review history, QA history, Automation
status, Current running automation, STOP/ON/OFF controls, Releases,
Release readiness, Empty states, Error states (18, counting Empty/Error
states separately from the 16 feature screens — see Part 2's table for
the literal count and every citation). The underlying mechanisms behind
all of these are real, DB-derived, and exercised through the actual
running Control Center — not narrated substitutes.

### 2. What UI is partial

Pipeline, Activity, Security findings, Founder-action-required
visibility, Navigation, Loading states — 6-7 items, each partial for a
specific, named reason in Part 2's table, not a vague "mostly done."

### 3. What UI is missing

Active Work / company-wide Progress, Project/Phase Progress, Task
Detail, Risks (company-wide register), company-wide AI usage/cost,
Stuck-work visibility — 6 items. Every one of these is either fully
designed in Parts 3-5 of this document, or (Risks, company-wide) closed
incrementally the moment Task Detail's per-task risk section (§5.3 item
8) ships, even before a standalone risk register exists.

### 4. Exact milestones required to reach Founder UI Feature Complete

Following this project's own narrow-slice discipline (Phase 3A's own
precedent: separately gated, separately reviewable, not one giant
build):

- **Milestone A — Task Detail + company-wide Active Work.** One
  milestone (see point 5, below, for why these are combined). Ships:
  `/tasks/<id>.html`, `/active-work.html`, the shared
  `task_progress_row()` computed function, click-through links replacing
  every dead `pipeline.html#task-{id}` anchor across `pipeline.html`,
  `automation.html`, `reviews.html`. Closes: Task Detail (MISSING →
  COMPLETE), Active Work (MISSING → COMPLETE), Pipeline (PARTIAL →
  COMPLETE, once cards link out), Stuck-work visibility (MISSING →
  COMPLETE, via the disclosed staleness threshold), most of
  Founder-action-required visibility (PARTIAL → COMPLETE, unified into
  one column instead of two separate pages), and closes the per-task
  slice of Risks (MISSING → PARTIAL, task-scoped risks visible; a
  company-wide register is still a separate, smaller follow-up).
- **Milestone B — Company-wide AI cost visibility.** One additive
  `agent_runs.cost_usd` column, three known call sites (Ask-Agent,
  Meetings, Chief of Staff — all discovered exactly in Part 1) updated
  to pass the value they already compute, plus a rendered aggregate
  (company-wide, and per-task once Milestone A's cost rollup can read
  it). Closes: AI usage/cost (MISSING → COMPLETE).
- **Milestone C — Company-wide Risks register.** A small, dedicated
  `/risks.html` (all `risks` rows, open/mitigated/resolved, company- and
  task-scoped, linking to the relevant task's detail page from Milestone
  A). Closes: Risks (PARTIAL → COMPLETE), the last piece of Security
  findings (PARTIAL → COMPLETE, once the open risk picture and the
  review-verdict picture are both reachable).
- **Milestone D (recommended, not strictly required for testing — see
  point 10) — Project/Phase Progress.** Requires the `phases` table
  addition from Part 4 first; a smaller, later milestone once A-C are
  proven.

Each of A/B/C should get its own CTO architecture review, Red Team
challenge, and Security pass before Development — same discipline every
Phase 3A/TASK-017 milestone already used — not authorized by this
document.

### 5. Active Work and Task Detail: one milestone or two — my recommendation

**One milestone (Milestone A above).** Reasoning: both are literally the
same underlying computed function (`task_progress_row()`), so splitting
them doesn't reduce shared design risk the way Phase 3A's Part A/Part B
split genuinely did (those were sequential, independently valuable
capabilities). More importantly, an Active Work list whose rows link to
a task-detail page that doesn't exist yet is a **broken product surface**
— a link that looks real but 404s is exactly the kind of thing that
fails the Founder's "coherent and usable" bar, arguably worse than not
having the list at all. Shipping them together also lets one Red
Team/Security review cover the one new read surface both screens expose,
rather than two reviews of overlapping code.

### 6. Does Project/Phase Progress require additional work beyond what exists?

**Yes, fully — nothing today captures phase state as structured data.**
Confirmed directly (Part 4.1): no phase column exists on any table;
Phase 0-3A state is prose-only in `ROADMAP.md`/`DECISIONS.md`. This is
the one item in this whole audit that requires new schema, not just new
read-side rendering — flagged plainly per the Founder's own instruction
not to paper over that with an invented percentage or a runtime read of
the markdown file.

### 7. The cost-tracking truth table

Reproduced in full in Part 1.2 above. Summary: tokens measured and cost
calculated identically for all four paths (Ask-Agent, Meetings, Chief of
Staff, automated Code Review); cost **persisted for exactly 1 of 4** —
the automated Code Review poller (`automation_events.cost_usd`), **not**
Ask-Agent as the Chief of Staff's prior verbatim answer stated; visible
to the Founder in exactly that same 1 of 4 case, scoped to automation
spend only, not company-wide.

### 8. Recommended build order

1. Milestone A (Task Detail + Active Work) — highest leverage, closes
   the most MISSING items, and every other milestone's UI benefits from
   having a real detail page to link into.
2. Milestone B (company-wide cost visibility) — small, additive, closes
   a real blind spot before the Founder commits real budget to testing.
3. Milestone C (Risks register) — smaller than A/B, but genuinely closes
   the gap that this whole correction started from (`risks.id=3` being
   invisible in the product).
4. Milestone D (Project/Phase Progress) — deferred until after A-C, per
   point 10.

### 9. Number of milestones remaining until Founder UI is genuinely 100% feature-complete

**Three (A, B, C)** — not the prior document's two. Milestone D (phase
progress) is deferred per point 10 below and is not counted against the
"100% feature-complete for the current product" bar, since phase/roadmap
narrative is lower-frequency information than watching active work, and
it requires a schema addition the other three don't. If the Founder
wants Project/Phase Progress included in the "100%" bar rather than
treated as a fast-follow, the honest count is **four**.

### 10. What stays deferred until after Founder testing begins

Unchanged from the prior document, per the Founder's still-standing
directive — not re-litigated here: the remaining Phase 3 automation
(Milestones 3B/3C/3D from the prior document's Part 2), task-level
access scoping, and TASK-017's resumption (`risks.id=3` stays `open`).
Additionally, from this document: **Milestone D (Project/Phase
Progress)** can reasonably wait until after A-C ship and the Founder has
started testing — it is real, valuable, and lower-urgency than watching
active work or understanding cost, and it is the one item that needs a
schema change first, which argues for letting it follow, not lead.

---

## What changed from the prior round, stated plainly

The prior CTO document and the Chief of Staff synthesis were not lying —
every individual fact either document stated was traceable to something
real. But two things were wrong in a way that mattered: (1) the Chief of
Staff's own verbatim answer inverted which invocation path persists
cost, an error that would have led the Founder to approve the wrong
mental model of "what's tracked and what isn't"; (2) both documents
under-scoped what "Founder UI feature-complete" means — a task-detail
page and a cost fix are necessary but leave real, load-bearing gaps
(company-wide Active Work, the Risks register, Project/Phase Progress)
that the Founder would still have had to ask an outside AI, read a
markdown file, or run SQL to see. This document corrects both, with
the exact file/line evidence needed to check it.
