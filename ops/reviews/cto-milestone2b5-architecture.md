# CTO Architecture Proposal — Phase 2, Milestone 2B5

## Objective

Ship two new read-only Control Center screens surfacing real, historical
data that already exists in the operational database but has no
Founder-facing view yet:

- **Reviews** — the full `review_results` (Code Review + Security,
  PASS/REJECT, 39 rows today) and `qa_results` (PASS/FAIL, 56 rows
  today) history, grouped by task.
- **Releases** — the real `deployments` history (1 row today) plus a
  computed release-readiness gap: which DONE/READY_TO_RELEASE/DEPLOYED
  tasks have no deployment row at all.

This closes the last two Phase-2-scoped capabilities named in
`ops/ROADMAP.md` ("QA/review failures," "release information") that
aren't yet built. Everything else ROADMAP.md names for Phase 2 has
already shipped (Milestones 2A through 2B4).

## Basis: no dedicated Phase 0 mockup exists for this screen, and that's consistent with existing precedent

Flagged explicitly rather than silently assumed, since my role
constraint is to architect only against an approved mockup. Checked
`ops/mockups/control-center-phase-0/` directly: it contains six
artboards (Main, OverviewLight, Pipeline, Agents, AgentConversation,
ExecutiveMeeting) — there is no `Decisions.dc.html`, `Meetings.dc.html`,
`Reviews.dc.html`, or `Releases.dc.html`. Decisions and Meetings shipped
in Milestone 2A anyway, architected directly against the Founder-approved
**visual system** (CSS tokens, nav shell, card/panel/pill vocabulary in
`layout.py`) rather than a dedicated per-screen artboard — see
`cto-milestone2a-architecture.md`: "Visual tokens are copied verbatim
from the Founder-approved dark mockup... this is that same visual
system, not a reinterpretation."

Reviews and Releases are architecturally the same kind of screen as
Decisions was in 2A: a reverse-chronological/grouped read-only list over
one or two tables, using the exact same card/pill/panel components
already approved and already shipped four times over. No new
interaction pattern, no new visual language. I'm treating Milestone 2A's
precedent as covering this case too, and disclosing that reasoning here
rather than assuming it silently — Red Team and Design conformance
should confirm this reasoning holds, not take it on faith.

## Design Decision 1 — Two pages, not one

**Decision:** `reviews.html` (Code Review + Security + QA history) and
`releases.html` (deployments + release-readiness), as two separate
top-level screens — not one combined screen, not tabs on one page.

**Reasoning:** every existing Control Center screen is one distinct
concern — Pipeline (where is work now), Agents (who's doing it),
Decisions (what was decided), Meetings (what was discussed), Inbox (what
needs a Founder action). ROADMAP.md's own Milestone 2B5 entry names two
separate, independently-answerable Founder questions: "did review/QA
reject this work, and why" versus "is this shippable / what has actually
shipped." These have different natural structure (review/QA is
per-task, multi-row, both-pass-and-fail work-history; release readiness
is per-deployment-event plus a gap-list, not really about individual
QA/review outcomes at all) and different update cadence (review/QA rows
accumulate constantly during active development — this session alone
added ~30; deployment rows are rare, one so far in the company's
history). Forcing them into one page means either an arbitrary tab
split (faking "one page" while still being two views) or a hybrid
grouping that doesn't match either concern cleanly. Two pages matches
the existing one-concern-per-nav-entry convention exactly.

## Design Decision 2 — Scope: full history, grouped by task, no pagination yet

**Decision:** Reviews shows the full 39+56 rows (95 today), grouped by
`task_id` (most-recently-active task first; within a task, review and
QA rows interleaved reverse-chronologically by `created_at`). No `LIMIT`,
no pagination UI, no new query-string parameters.

**Reasoning:**
- Checked Overview's cap pattern directly: `render_activity()` caps
  "Just Happened" at `LIMIT 8`, and `render_inbox()` shows 4 rows plus a
  "+N more in Inbox" link — but both of those are *summary tiles* that
  hand off to a dedicated full-history screen (Inbox, or nothing yet for
  activity). Reviews and Releases **are** that dedicated full-history
  screen for this data — there's nowhere further to link a "+N more" to.
  `Decisions.html` is the closer analog: it renders every row with no
  cap, because it already is the full-history screen. Same pattern here.
- 95 rows is not yet a real scale problem for a single page load. This
  session added roughly 30 rows across ~2 tasks; even projecting the
  same rate across many more tasks, we're talking low hundreds over the
  life of the project before pagination genuinely matters — and adding
  a `LIMIT`/`OFFSET` GET parameter later is a small, additive change to
  one file whenever that day comes. Building pagination infrastructure
  now, for 95 rows, would be solving a problem that doesn't exist yet.
- What **does** matter at 95 rows: a flat, ungrouped chronological list
  (Decisions' rendering style, one `<div class="card">` per row) would
  be a very long, low-signal scroll. Grouping by `task_id` (a real
  column, not invented structure — same category of decision as
  `STAGE_MAP` in 2A) turns 95 rows into ~10 task sections, each
  answering "how did this task's review/QA history go," which is the
  question a Founder actually has. This is an honest structural choice,
  not a way to hide volume — every row still renders, just organized by
  the column that already exists to organize it by.

**Correction (Red Team's Milestone 2B5 review)**: this document
originally cited "12 QA rows for TASK-006" as its illustrative worst
case. Red Team live-verified the actual current maximum is **TASK-007,
21 combined review+QA rows** (5 review + 16 QA), not 12 — TASK-006 (18)
and TASK-010 (17) are also both above the original example. 21
interleaved rows under one header is not broken, but it's real enough
that Development must verify rendering against TASK-007 specifically,
not the smaller original example, and must add a lightweight per-group
affordance: a native `<details>` "show all N" collapse once a
task-group exceeds ~10 rows. This is a few lines, not pagination
infrastructure — folded into the file-by-file list below as a
requirement, not deferred.

## Design Decision 3 — What "release readiness" means for this milestone

**Decision:** `releases.html` shows two things, both real:
1. The `deployments` table's actual rows (1 today) — the real, honest
   deployment log.
2. A computed **release-readiness gap** list: tasks whose `status` is
   `READY_TO_RELEASE`, `DEPLOYED`, or `DONE` (per `AGENT_STATUS.md`'s
   status list) that have **zero** matching `deployments` row.

**Reasoning:** I checked this against the live database rather than
assuming. Of the 11 tasks currently `DONE`, only **one** (TASK-001, the
Phase 1 walkthrough demo) has a `deployments` row. The other ten do not.
Showing only the 1 real deployment row, with no further comment, would
materially mislead the Founder about what "release information" this
screen covers — it would look like the company has shipped once, ever,
when in fact ten more tasks reached DONE with no deployment record. The
gap list makes that visible instead of hiding it, the same "empty states
are better than fake data" instinct 2A applied to `meetings.html` when
that table had zero rows — here the honest thing to show isn't an empty
state, it's a *count of what's missing*.

**Correction (Red Team's Milestone 2B5 review, blocking finding)**: this
document originally characterized the 10-task gap as "a real,
pre-existing gap in this project's own process discipline around the
`deployments` table." Red Team checked this against the project's own
actual rules and found it unsupported: `ops/AGENT_STATUS.md`'s real
DONE-readiness checklist never mentions the `deployments` table;
`ops/PROJECT.md`/`ops/ROADMAP.md` both frame production deployment as a
rare, Founder-gated, explicitly-authorized event, not something every
completed task is expected to produce a row for; the one existing
`deployments` row (TASK-001) is itself labeled "Phase 1 pipeline
validation only," not a real release; and all 10 "gap" tasks are this
project's own internal Control Center tooling milestones with
`tasks.deployment_result` empty (consistent with "not applicable," not
"skipped"). Asserting a process-discipline failure here — when this
project's own actual DONE checklist never required a deployment row —
risks the Founder concluding there's a real problem where the evidence
doesn't support one. **Corrected disposition**: the computed gap list
itself ships unchanged (it's an honest, real query) — only the
copy/interpretation changes. `releases.html` and `generate_releases.py`
present the list as a neutral data observation, e.g. "N of M DONE tasks
have no `deployments` row — this may reflect internal/tooling work with
no discrete production release step, not necessarily a process gap,"
never as an assertion of a pre-existing discipline failure.

This is a computed fact from two real columns (`tasks.status`,
`deployments.task_id`), not invented structure — same category as
`company_health()` and `STAGE_MAP`. It belongs in `derived_state.py` as
a new function (e.g. `release_readiness_gap(conn)` returning tasks in
the three statuses above with no matching deployment row), not
hand-coded inside `generate_releases.py`, in case a future screen needs
the same fact (e.g. if `report.py` ever wants a "shipped without a
deployment record" section — not proposed this milestone, just noting
why the function lives in the shared module).

I am not proposing any change to what counts as "release-ready" in the
schema or workflow itself (no new `tasks.status`, no new column) — this
is purely a read-only visibility computation over columns that already
exist.

## Design Decision 4 — Data linkage: group headers, plus a small anchor addition to Pipeline

**Decision:** Both screens group content under a task header (`TASK-NNN
— <title>`, current `status`). No new per-task detail page. As a small,
disclosed addition: `generate_pipeline.py`'s task cards get an
`id="task-{id}"` HTML anchor (a few characters, no new file, no new
route), so each task-group header on `reviews.html`/`releases.html` can
link to `pipeline.html#task-{id}` — landing the Founder on that task's
real position in the pipeline, not just a bare label.

**Reasoning:** I checked whether a per-task detail page already exists
via the generator file list (`ops/control-center/generate_*.py`) — it
does not; Pipeline's task cards are inert `<div>`s today, not `<a>`
links. Building a full per-task detail page (aggregating steps,
history, handoffs, messages, reviews, QA, deployment status, etc., all
in one place) is a materially larger, separate architecture problem —
its own screen, its own data-aggregation design, arguably its own future
milestone — and is not what this milestone's brief asks for. Rather
than either (a) silently providing no way to get from a review/QA/release
row back to the task, or (b) scope-creeping into a full detail page to
solve it, the middle path is: the task-grouping itself (Decision 2) is
already most of a lightweight "detail view" for this data, and a tiny,
purely-additive anchor-id change to an existing generator gives real
navigation back to Pipeline for free. This is disclosed as an edit to
an existing file, not treated as free of scope — Red Team should treat
it as an in-scope, in-review change alongside the two new generators.

## Design Decision 5 — Naming and nav integration

| What | Value |
|---|---|
| New generator | `ops/control-center/generate_reviews.py` |
| New generator | `ops/control-center/generate_releases.py` |
| New page | `reviews.html` |
| New page | `releases.html` |
| Nav label | "Reviews" |
| Nav label | "Releases" |
| `OUT_PATH` env override | `OPSDB_REVIEWS_PATH`, `OPSDB_RELEASES_PATH` (matches `OPSDB_DECISIONS_PATH`/`OPSDB_MEETINGS_PATH` convention in `dbutil.out_path()`) |

Follows the existing `generate_<noun>.py` → `<noun>.html` convention
exactly (`generate_decisions.py` → `decisions.html`,
`generate_meetings.py` → `meetings.html`).

`NAV_LINKS` in `layout.py` is currently a fixed, hand-ordered 6-entry
list ending in Inbox. I'm proposing to **append** both new entries at
the end, not interleave them earlier in the list:

```python
NAV_LINKS = [
    ("overview.html", "Overview"),
    ("pipeline.html", "Pipeline"),
    ("agents.html", "Agents"),
    ("decisions.html", "Decisions"),
    ("meetings.html", "Meetings"),
    ("inbox.html", "Inbox"),
    ("reviews.html", "Reviews"),
    ("releases.html", "Releases"),
]
```

Appending, not reordering, is the smaller and more consistent diff —
every existing screen's nav rendering is driven by iterating this same
list, so reordering it would shift where every other link renders on
every existing page for no functional reason. This mirrors how 2A
itself extended a shorter nav set from Milestone 1 without reshuffling
it.

## Design Decision 6 — Read-only, zero new write routes, zero new auth code

Stated explicitly to bound Security/Red Team's review surface: this
milestone adds **two new GET routes and nothing else**. No new POST
route, no new form, no new session/cookie/CSRF logic. I read
`server.py`'s `do_GET()` in full to confirm rather than assume: the
Milestone 2B4 session-authentication gate
(`_check_credential_gate()` → `/login` allowlist check →
`self._authenticated_session() is None` → redirect) runs unconditionally
**before** the per-path `if path == ...` dispatch block. Adding
`reviews.html`/`releases.html` as two more branches in that same
`try:` block means they inherit full-app-lock session gating with
literally zero new authentication code — the same "every GET route
after the gate is already covered" property Decisions and Meetings rely
on today. No change to `SESSION_TOKEN`, `SESSIONS`, `founder_auth.py`,
or any cookie/CSRF logic is proposed or needed.

Both new generators open only `mode=ro` connections via `dbutil.connect()`
— the same write-refusal-tested pattern every other generator uses.
Neither queries nor renders anything from `agent_runtime.py` or
`meeting_orchestrator.py`.

## Design Decision 7 — `report.py`: no change

**Decision:** `ops/db/report.py`'s existing "QA failures (unresolved)"
section (`CURRENT_STATUS.md`) is left as-is. This milestone does not
touch `report.py`.

**Reasoning:** I read the existing section — it already surfaces a
narrow, deliberately-scoped slice: the *latest* `qa_results` row per
task, filtered to `result = 'fail' AND task.status != 'DONE'` (i.e.
"unresolved failures someone should act on right now," for anyone
reading the committed markdown snapshot). That serves a different
purpose and audience than this milestone's Control Center screen, which
is the **full** pass-and-fail, resolved-and-unresolved, Code-Review-and-
Security-and-QA history for a Founder browsing interactively. The two
are additive, not duplicative, by design — a person reading
`CURRENT_STATUS.md` gets "what needs attention right now"; a Founder on
`reviews.html` gets "the whole story." Extending `report.py`'s section
to be richer here would blur that boundary and isn't something this
milestone's brief (Control Center visibility) actually calls for. If a
future milestone wants `CURRENT_STATUS.md` itself to carry more detail,
that's a separate, explicit decision — not a side effect of this one.

## Out of scope (explicitly, matching the brief's constraints)

No change to `opsdb.py`, `schema.sql`, `agent_runtime.py`,
`meeting_orchestrator.py`, or any write route. `risks.id=3` stays out of
scope, unaffected. No new per-task detail page (Decision 4). No
pagination infrastructure (Decision 2). `ops/ROADMAP.md`'s Milestone 2B5
entry is not edited by this document — it moves from "current, not yet
started" to "DONE" at closeout, per existing project convention (see how
2A through 2B4's entries were finalized), not as part of the
architecture proposal itself.

## File-by-file change list, for Development

1. **New** `ops/control-center/generate_reviews.py` — `build_html(token=None)`,
   following `generate_decisions.py`'s exact shape (imports `connect`,
   `out_path`, `write_output` from `dbutil`; `e`, `page` from `layout`;
   `display_name` from `derived_state`). Query: `review_results` JOIN
   `tasks`, and `qa_results` JOIN `tasks`, grouped/sorted by
   `task_id` (most recent task activity first), rows within a task
   interleaved by `created_at DESC`. Pill styling for `pass`/`reject`/
   `fail` reuses the existing `--green`/`--red` CSS tokens already
   defined in `layout.py` (same tokens Pipeline's "Needs Attention" and
   Decisions' approval-note pills use — no new color introduced). Each
   task-group header links to `pipeline.html#task-{id}` (Decision 4).
   A task-group with more than ~10 combined rows renders inside a native
   `<details>` element, collapsed by default with a "show all N" summary
   — required per Red Team's Milestone 2B5 review, verified against the
   real worst case (TASK-007, 21 combined rows), not the smaller
   originally-cited example. The page carries a short, explicit label
   distinguishing its scope ("full historical record, including
   resolved failures on now-DONE tasks") from `CURRENT_STATUS.md`'s
   "unresolved right now" scope — required per Red Team's review, so
   the two screens read as complementary, not contradictory, on first
   glance. `OUT_PATH = out_path("reviews.html", "OPSDB_REVIEWS_PATH")`.
2. **New** `ops/control-center/generate_releases.py` — same shape.
   Renders the real `deployments` rows (version, environment,
   release_notes, rollback_plan, deployed_by_agent, deployed_at,
   founder_authorized) plus the `release_readiness_gap()` list (Decision
   3), each gap-list task linking to `pipeline.html#task-{id}`. The
   gap-list copy is a neutral data observation ("N of M DONE tasks have
   no `deployments` row — this may reflect internal/tooling work with no
   discrete production release step, not necessarily a process gap"),
   never an assertion of a process-discipline failure — required per
   Red Team's blocking finding on Decision 3.
   `OUT_PATH = out_path("releases.html", "OPSDB_RELEASES_PATH")`.
3. **Edit** `ops/db/derived_state.py` — add `release_readiness_gap(conn)`,
   returning tasks with `status IN ('READY_TO_RELEASE','DEPLOYED','DONE')`
   and no matching `deployments.task_id`. Pure read, same
   `sqlite3.Connection`-in / rows-out shape as every other function in
   this module.
4. **Edit** `ops/control-center/generate_pipeline.py` — add
   `id="task-{t['id']}"` to the task-card `<div>` in
   `render_stage_column()` (and, for consistency, to the Needs
   Attention and Backlog cards too, since a gap-list or review-history
   task could be in any of those three states) so the new anchors
   (Decision 4) resolve wherever the task actually is.
5. **Edit** `ops/control-center/layout.py` — append
   `("reviews.html", "Reviews")` and `("releases.html", "Releases")` to
   `NAV_LINKS` (Decision 5). No other change to `layout.py`.
6. **Edit** `ops/control-center/server.py` — `import generate_reviews`
   and `import generate_releases` alongside the existing generator
   imports; add two branches to `do_GET()`'s existing `try:` block,
   directly modeled on the `/decisions.html` branch:
   ```python
   if path == "/reviews.html":
       self._send_html(200, generate_reviews.build_html(token=SESSION_TOKEN).encode("utf-8"))
       return
   if path == "/releases.html":
       self._send_html(200, generate_releases.build_html(token=SESSION_TOKEN).encode("utf-8"))
       return
   ```
   No change anywhere else in `server.py` — no new regex, no new
   `do_POST()` branch, no new session/CSRF logic (Decision 6).
7. **No change**: `ops/db/report.py` (Decision 7), `ops/db/opsdb.py`,
   `ops/db/schema.sql`, `ops/control-center/agent_runtime.py`,
   `ops/control-center/meeting_orchestrator.py`, `ops/control-center/founder_auth.py`.
8. **No change now**: `ops/ROADMAP.md` — updated at closeout, not here.

## Recommendation

Red Team PASSed, conditional on the three corrections above (all folded
into this document — worst-case row count corrected, the collapse
affordance and explicit scope-labeling requirements added to the
file-by-file list, Decision 3's framing softened to a neutral data
observation). See `ops/reviews/red-team-milestone2b5-architecture.md`.
No re-review required per Red Team's own disposition — proceed to
Development against this corrected document.
