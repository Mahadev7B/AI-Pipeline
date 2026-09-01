# TASK-026 — Product brief: the factory's own tracking UI

Author: product · 2026-09-01 · Input: TASK-026's sharpened status note
(task_status_history, latest row), which supersedes the task's original
ellipse-centred wording. Design builds from this. No layouts here — form is
Design's call.

---

## 1. Subject and goal

**The factory is the product.** This UI is the tracking interface of an AI
software company. Its subject is **the build** — a thing being made — not the
thing that gets made.

Business goal: a Founder can stand in front of one screen and see what the
factory is making, how far it has got, and what is stopping it — and believe
what it says.

User story: *As the Founder, I want to watch a build move through the factory,
so that I know what is happening and what is stuck without reading thirteen
pages of text.*

"Cool" is a stated requirement, not decoration — this is the showpiece. It is
Design's to deliver and I am not going to constrain it with layout. What I will
constrain: cool must not be bought with numbers the data cannot support.

Scope: **one primary screen (the Build) plus one secondary page (the Team).**
Everything else in today's UI is a record behind one menu.

---

## 2. The data floor (verified today, not assumed)

Every requirement below cites this. Counts are live as of 2026-09-01.

| Fact | Value | Consequence |
|---|---|---|
| `projects` | 1 row: *AI-Pipeline Ops Bootstrap — the ops system building itself* | The factory has never built an app. |
| `tasks.project_id` | NULL on **20 of 24** tasks (only 1–4 linked) | "Which app is this build for" is unanswerable for most tasks. |
| `task_steps` | 4 rows, **all on task 1** | Percent-complete is unavailable for 23 of 24 tasks. |
| `agent_runs` | 13 rows, all seeded 2026-08-28 on task 1, all `ended`, all `cost_usd` NULL; **0 open runs** | No live "agent is working now" signal exists. |
| `automation_events` / `reviewer_invocations` | 0 / 0 rows | No dollar figure has ever been recorded. |
| `meetings` | 0 rows | The Meetings tab is empty as well as buried. |
| `tasks.next_action` / `tasks.blockers` | NULL on **all 24** tasks, always | Neither field may be relied on. |
| `task_status_history` | 222 rows, 2026-08-28 → today | The real spine of build history. |
| `review_results` / `qa_results` / `handoffs` | 82 / 74 / 17 rows | The real evidence of work done. |
| Tasks DONE with zero review, QA **and** handoff rows | tasks **11** and **18** | "DONE" is a claim, not evidence. |

`ops/db/derived_state.py` already computes, honestly and with a tested bug
history, everything the progress model below needs: `effective_gate_status`,
`gates_completed`, `gates_remaining`, `gate_display_label`, `task_bounce_count`,
`task_is_stuck` (3-day threshold), `interrupt_reason`, `task_last_event`,
`elapsed_since`, `task_progress_row`. **Design and Development should treat this
module as the source of truth and add to it rather than recompute.**

---

## 3. What the Build screen must show

Seven items. Each names its source and why it earns a place.

1. **Which app.** `projects.name` + `projects.description`, one line.
   *Earns it:* the Founder's own first question is "which app". Today it can
   only ever say the bootstrap project — see §5 and §9.

2. **How far along — the gate ladder, not a percentage.** The six stages of
   `PIPELINE_STAGES` (Product · Design · Architecture · Development · Review ·
   Release), with the current gate from `effective_gate_status()` labelled by
   `gate_display_label()`, and gates behind/ahead from `gates_completed()` /
   `gates_remaining()`.
   *Earns it:* it is the one progress model this data supports exactly. A
   percentage would be invented for 23 of 24 tasks.

3. **What is happening.** The most recent real event and when — from
   `task_last_event()` (status change, review result, or QA result) plus
   `elapsed_since()`. One line of already-written text, never a summary an agent
   generates on render.
   *Earns it:* "what is happening" was the Founder's second question, and this
   is the only truthful answer available: the last thing that actually happened.

4. **Whose turn it is.** `tasks.current_owner`, linking to that agent on the
   Team page. NULL renders as *unassigned* — it is NULL on 2 of the 5 open
   tasks and must not be guessed.

5. **What is stuck.** Three distinct signals, never merged:
   - **Blocked / awaiting Founder** — from status, with the real reason text
     from `interrupt_reason()` (the note on the transition row). `tasks.blockers`
     must not be used; it has never been written.
   - **Stalled** — `task_is_stuck()` true (no event in >3 days), shown with the
     date of the last real event.
   - **Founder action required** — `task_progress_row()["founder_action_required"]`.
   *Earns it:* "what is stuck" is the third of the Founder's own three questions.

6. **Rework.** `task_bounce_count()` — rejected reviews plus failed QA. Backed by
   82 `review_results` and 74 `qa_results` rows.
   *Earns it:* it is the most factory-like number this system honestly has. A
   thing being made twice is what a factory looks like. It is also the number
   that makes the screen not a status board.

7. **One level down, per stage.** Selecting a stage reveals what that stage
   actually produced: `handoffs.work_completed` / `files_changed`,
   `review_results.findings` and `returned_to_agent`, `qa_results.defect_summary`
   / `reproduction_steps`. On demand only — never expanded by default.
   *Earns it:* it replaces every "detail" tab with one gesture, and it is where
   the density that killed the old UI is allowed to live.

**Unit of a build.** Today a build = one task; a project groups tasks via
`tasks.project_id`. Design should treat "build" as the project-level object with
its current task in view. Because `project_id` is NULL on 20 of 24 tasks, see
§9 item 1 — this is new work, not an existing capability.

**If more than one build is live**, the screen shows one at a time with a plain
switch between them. It does not become a list, a grid, or a board. Those were
rejected and, at a real count of one, they are also dishonest theatre.

---

## 4. What it must NOT show

The old UI failed by inclusiveness. This is the aggressive cut.

**Deleted as destinations** (their content lives on the Build screen or one
level down from it): Overview, Active Work, Pipeline.

**Moved behind one menu**, reachable in one click from anywhere, never in the
primary chrome: Decisions, Risks, **Meetings**, Inbox, Reviews, Releases,
Automation, Costs, Progress (phases), and the archive of completed tasks.
The menu is a flat list of named records — not nested, not categorised.

**Meetings specifically must stay reachable.** It is currently 8th of 13 tabs
and the Founder could not find it. Requirement: reachable in at most two clicks
from the Build screen, and named "Meetings" in the menu. It has 0 rows today, so
it must render *"No meetings have been held"* — not an empty page.

**Never rendered anywhere:**
- Any percent-complete figure. The data does not exist (§2).
- Any dollar amount. No cost has ever been recorded; a `$0.00` would be a lie.
- Any live/online/working-now indicator for an agent that has no open
  `agent_runs` row. Today that is all 14 agents.
- Raw prose dumped from `tasks.requirements`, `architecture_notes`,
  `implementation_notes`, etc. Those fields are paragraphs; the screen shows one
  line and a way in. This *is* the "so much verbose" failure.
- Achievement framing built on counts of DONE tasks.
- Anything about the built app's own content, users, uptime, quality, or look
  (§6).
- `tasks.next_action` and `tasks.blockers` — never written, in 24 tasks.

---

## 5. The never-run state (first-class)

This factory has produced zero apps. This is the state the UI will be in on the
day it ships, so it is a primary state, not a fallback.

Requirements:

- **It says so plainly.** The screen states that no app has been built yet.
  Zero. Not "getting started", not a skeleton with grey placeholder bars implying
  a build in flight.
- **The apps-built count excludes the factory's own bootstrap project.** It reads
  0 today and must never read 1 by counting `projects` naively.
- **The factory's own work is shown, and labelled as exactly that.** The one true
  build in the system is the factory building itself (22 tasks, 222 status
  transitions, real reviews and QA). Showing it is honest and gives the screen
  real content on day one. Showing it *as an app build* is not. It carries an
  explicit label distinguishing self-build from an app build, and it never
  counts toward apps built.
- **The one true next action.** The empty state offers how a build actually gets
  started. Today that is the command line; TASK-024 (Founder Idea Intake) would
  make it a button and is still in PLANNING — the empty state must describe
  whichever is true when this ships, and must not link to a route that does not
  exist.
- **No demo data, ever.** The 13 seeded `agent_runs` rows from 2026-08-28 are
  demo fixtures for task 1. They must not be presented as factory history.

Design must deliver this state and the populated state as two designed states of
one screen. The never-run state is the one that gets reviewed first.

---

## 6. The factory ↔ app boundary

The factory UI (ours) tracks **apps being built**. The app UI is a child, is
entirely separate, and is never styled by us.

**About a child app, the factory UI shows exactly:** its name, one line of what
it is, its build state (the seven items in §3), and — once it genuinely exists —
a single link out.

**The link out:** one plainly-labelled outbound link, sitting beside the app's
name on the Build screen. It renders **only** when a real destination is
recorded. There is no such field today (§9 item 2), so until that ships, no link
renders at all. A speculative or placeholder link is a defect.

**The factory UI must never:** embed, iframe, screenshot, preview, or restyle the
app; show the app's users, traffic, revenue, uptime, errors, or content; adopt
the app's branding, or push ours onto it; or present any judgement of whether
the app is good. "How is my app doing" is not a question this UI answers.
The fair test stays: standing at a factory, watching a thing get made.

---

## 7. The Team view

**A page, not a panel.** It is the second and last top-level destination.

*What it answers that the Build screen doesn't:* who this company employs, what
each one is permitted to do, and what each has actually done. That is roster and
record — a different cadence from a build in motion, and folding it into the
Build screen would rebuild the density that was rejected.

Must show, per agent (14 rows in `agents`):
- Name (via `display_name()` — `orchestrator` renders as *Chief of Staff*) and
  role.
- Model and `model_status`. All 14 are `experimental` today; that word ships
  visibly. It is a real caveat about this company.
- What they are permitted and forbidden to do — `permissions_allow` /
  `permissions_deny`.
- What they have actually done: their authored transitions
  (`task_status_history.changed_by_agent`), their review and QA verdicts
  (`review_results` / `qa_results` by agent), their handoffs, and
  `agent_activity` (41 rows). Real rows, counted, not a synthesised biography.

Must not show: presence dots, availability, utilisation, throughput, ranking,
cost per agent, or "currently working on" derived from a closed `agent_runs`
row. Live status appears **only** where `agent_runs.ended_at IS NULL`. Today
that is nowhere; the honest label for all 14 is *not running*.

Link: the Build screen's current owner links here; a Team entry links back to
the builds that agent touched.

---

## 8. Honest states

This company has twice shipped things that reported success while doing nothing,
and QA caught both. These rules exist because of that.

1. **Status is a claim; rows are evidence.** The headline state of a build is
   derived from evidence rows (`review_results`, `qa_results`, `handoffs`,
   `deployments`), not from `tasks.status` alone, which any agent can set.
2. **A stage with no record says so.** If a task has passed a gate but no
   handoff, review, or QA row exists for it, the UI renders *no record kept* —
   a visible gap, not a silent pass. `tasks.11` and `tasks.18` are DONE with zero
   review, QA and handoff rows between them; both must render as gaps.
3. **Failure is visible.** A `result='reject'` or `result='fail'` shows as a real
   event with its own `findings` / `defect_summary` text and the agent it was
   returned to. It is never smoothed into "in progress".
4. **Stall is not progress.** `task_is_stuck()` true renders as stalled with the
   date of the last real event — never as a moving build.
5. **Zero is not "never measured".** Where nothing has ever been recorded (cost,
   percentage, live runs), the UI says nothing was recorded. It never prints 0.
   `derived_state.cost_coverage()` already encodes this distinction; follow it.
6. **No invented text.** Every sentence on the screen is either a UI label or
   text a person or agent already wrote into the database.

---

## 9. New work — things the data cannot support today

Named explicitly rather than assumed. Each is a dependency, not a decoration.
Whether and how to build these is CTO's call; Design must not assume any of
them exist.

1. **A build cannot be attributed to an app.** `tasks.project_id` is NULL on 20
   of 24 tasks. Either it gets backfilled and written going forward, or the Build
   screen shows builds without an app name. *Interim assumption for Design:*
   project id 1 is the factory's own bootstrap. There is no column that marks
   this — distinguishing self-build from a child app needs a real field.
2. **No link-out destination exists.** Neither `projects` nor `deployments` has a
   URL column. The §6 link cannot render until one exists.
3. **Percent-complete is out of scope.** `task_steps` covers 1 of 24 tasks.
   Populating steps per task is a separate decision; this brief chooses the gate
   ladder instead and does not require steps.
4. **No live agent signal.** Pipeline agents (product, design, developer)
   invoked through the orchestrator write no `agent_runs` row at all — only six
   non-pipeline paths do, and none has ever run. "Who is working right now" is
   not buildable today.
5. **No cost data.** `automation_events` and `reviewer_invocations` are both
   empty and every `agent_runs.cost_usd` is NULL.
6. **Starting a build from the UI** depends on TASK-024, currently PLANNING.

---

## 10. Assumptions and open questions

- *Assumption:* a "build" is project-scoped, with one task in view at a time.
  If CTO decides a build is task-scoped instead, item 1 of §9 becomes moot and
  §3's unit changes — flagging rather than deciding, as that is an architecture
  call.
- *Assumption:* the single menu is acceptable to the Founder as the home for
  nine records. If not, the alternative is deleting some outright — not
  restoring tabs.
- *Open:* should DONE builds remain on the Build screen at all, or only in the
  archive? Recommend archive; 19 of 24 tasks are DONE and they would swamp it.
- *Open (for CTO, pre-existing):* `task_is_stuck()` does not exclude BACKLOG, so
  a never-started task can flag as stalled. Disclosed in that function's own
  docstring. It affects what the Build screen shows; it is not this brief's to
  resolve.

---

## 11. Acceptance criteria

Binary, testable by QA against the live database.

1. The primary chrome offers exactly two destinations: the Build screen and the
   Team page. Every other former tab is reachable from a single menu.
2. Meetings is present in that menu and reachable in ≤2 clicks from the Build
   screen; with `meetings` empty it renders an explicit "no meetings have been
   held" message, not a blank page.
3. No rendered page contains a percent-complete figure for any task, for any
   task lacking `task_steps` rows (i.e. 23 of 24 today).
4. No rendered page contains a currency figure while `automation_events`,
   `reviewer_invocations` are empty and every `agent_runs.cost_usd` is NULL.
5. No agent shows a live/working indicator while `SELECT COUNT(*) FROM
   agent_runs WHERE ended_at IS NULL` returns 0.
6. With no child-app project present, the Build screen states that zero apps
   have been built, and any apps-built count reads 0 — not 1.
7. The factory's own bootstrap work, where shown, carries a label distinguishing
   it from an app build, and is excluded from the apps-built count.
8. No outbound app link renders while no URL field/value exists.
9. For tasks 11 and 18 (DONE, zero review/QA/handoff rows), the UI renders a
   visible "no record" state and does not present them as verified.
10. For task 17 (BLOCKED), the UI shows the blocked state and the real reason
    text from the corresponding `task_status_history` note — while
    `tasks.blockers` is NULL.
11. For any task with `task_is_stuck()` true, the UI shows stalled plus the last
    real event date, and does not show it as progressing.
12. Every rejected review and failed QA row for a build in view is reachable
    with its own findings/defect text and its `returned_to_agent` value.
13. The Build screen shows a task's gate position, gates completed and gates
    remaining identical to `derived_state.effective_gate_status()`,
    `gates_completed()` and `gates_remaining()` for that task — no second
    implementation.
14. `tasks.current_owner` NULL renders as "unassigned"; no owner is inferred.
15. No page renders text from `tasks.next_action` or `tasks.blockers`.
16. The Team page lists all 14 agents with role, model, `model_status`
    (visible, currently `experimental` for all), permissions, and counts of
    their real recorded work.
17. No string on any screen is generated at render time by a model; all content
    is a static UI label or database text.
18. Neither screen embeds, previews, screenshots, or restyles a child app, and
    neither shows any app-usage metric.
