# QA Report — Phase 2, Milestone 2B5 (TASK-014)

Reviewing shipped commit (`generate_reviews.py`, `generate_releases.py`,
`derived_state.release_readiness_gap()`, `generate_pipeline.py` id=
additions, `layout.py` NAV_LINKS, `server.py` GET routes) against
`ops/reviews/cto-milestone2b5-architecture.md` and
`ops/reviews/red-team-milestone2b5-architecture.md`, from the Founder's
perspective, using both direct `build_html()` calls against the live
(read-only) `operations.sqlite3` and a full HTTP end-to-end pass in an
isolated scratch copy of the whole `ops/control-center` + `ops/db` tree
(own `.founder_credential.json`, own `OPSDB_PATH`, port 8621 — deleted
after use).

## Verdict: PASS

## 1. reviews.html against real data
Live-queried `operations.sqlite3` directly (not trusting the docs'
numbers): `review_results`=40, `qa_results`=56 today (grown from the
39/56 cited in Code Review — the code-review row for TASK-014 itself was
added after that review ran; expected drift, not a bug, since
`server.py` renders `build_html()` fresh on every GET, never a stale
static file — confirmed by reading `do_GET()`).
- 11 task groups render (TASK-001,002,004,005,006,007,009,010,012,013,014).
- TASK-007's group: confirmed live combined-row count is 21 (5 review +
  16 QA), matching Red Team's corrected worst case. Confirmed the shipped
  HTML wraps exactly 21 `.card` elements inside `<details><summary>show
  all 21</summary>`, collapsed by default. Also confirmed TASK-006 (18,
  "show all 18"), TASK-010 (17, "show all 17"), TASK-009 (12, "show all
  12") each collapse correctly; groups at/under 10 rows render flat with
  no `<details>` wrapper.
- Pill styling confirmed correct: `pass`→green, `reject`→red, `fail`→red,
  using the existing `--green`/`--red` tokens, no new colors.
- `display_name()`: **could not find a real review/QA row currently
  attributed to `orchestrator`** — live-queried all four
  distinct-agent columns (`review_results.reviewed_by_agent`,
  `.returned_to_agent`, `qa_results.tested_by_agent`,
  `.returned_to_agent`) and none contain `orchestrator` today (matches
  Code Review's own disclosed non-blocking gap: "No orchestrator-
  attributed rows exist yet to visually confirm end-to-end"). Verified
  the mechanism directly instead: `display_name('orchestrator')` →
  `"Chief of Staff"` at the Python level, and confirmed by reading the
  generator source that every agent-name field is piped through
  `e(display_name(...))`, the same pattern already shipped and exercised
  elsewhere (e.g. Pipeline's task-card owner field, which does render
  "Chief of Staff" live for tasks 5/6/7/etc. — confirmed in
  `pipeline.html`). Not a defect; noting as an untested-with-real-data
  edge rather than a pass/fail claim I can't back with real data.

## 2. releases.html against real data
1 real `deployments` row (TASK-001) renders with all real fields
(version `v0.0.1-demo`, environment `sandbox`, release notes, rollback
plan, "Deployed by devops", "Founder authorized" green pill,
`deployed_at`). Gap-list section: recomputed the count independently by
direct query rather than trusting the last session's number — **10 of
11 DONE tasks still have no deployments row today**, matching the
shipped copy exactly. Read the actual shipped copy: "10 of 11 DONE tasks
have no `deployments` row — this may reflect internal/tooling work with
no discrete production release step, not necessarily a process gap." —
neutral, non-accusatory, matches Red Team's required correction
verbatim.

## 3. Nav links
Grepped every existing page (`overview.html`, `pipeline.html`,
`agents.html`, all 14 `agents/*.html` detail pages, `decisions.html`,
`meetings.html`, `inbox.html`, plus `reviews.html`/`releases.html`
themselves) — "Reviews" and "Releases" present on all of them, correct
`href`, and correctly depth-adjusted (`../reviews.html`,
`../releases.html`) on the one-level-down `agents/*.html` pages.

## 4. Task-anchor links
Confirmed via a full HTTP round trip and direct `build_html()` calls:
every task-group header link (`pipeline.html#task-{id}`) on
`reviews.html`/`releases.html` targets a real `id="task-{id}"` anchor
that exists exactly once per task on `pipeline.html`. Spot-checked
TASK-014 (status BACKLOG) — its anchor sits correctly inside the
Backlog panel, not a stage column, matching its real current status.
12 anchor ids found on `pipeline.html`, one per real task, no
duplicates.

## 5. Empty/edge states
- Found a real mid-pipeline case: **TASK-014 itself** (status
  `BACKLOG`) already has one `review_results` row (this milestone's own
  passing code review) — renders correctly as a normal, uncollapsed
  single-card group on `reviews.html`, confirming the "not-DONE task
  with review/QA history" case works.
- No task currently sits at exactly 10 or 11 combined rows (real max
  distribution today: 21/18/17/12/7/5/...), so the exact collapse
  boundary wasn't exercisable against real data. Read the code instead:
  `if len(rows) > COLLAPSE_THRESHOLD` with `COLLAPSE_THRESHOLD = 10` —
  10 rows renders flat, 11 collapses, sensible "more than ~10" behavior
  as specified. Given QA discretion on this being a minor UI threshold,
  this code-level confirmation is sufficient.

## 6. Regression check (pipeline.html)
Called `generate_pipeline.build_html()` directly: 6 stage columns
(Product/Design/Architecture/Development/Review/Release) all render,
Release stage correctly holds all 11 DONE tasks with title/owner/
progress-bar unchanged, Backlog correctly holds TASK-014, Needs
Attention correctly renders empty (no BLOCKED/FOUNDER_APPROVAL tasks
today) — no structural or visual regression from the added `id=`
attributes. `python3 ops/db/report.py --check` → `OK` (exit 0).

## 7. XSS / malformed-data resilience
No new user-input path (read-only). Checked real DB content for
special-character rows: 30 `review_results.findings` rows and 14
`qa_results.scenario` rows contain quotes/apostrophes/arrows in real
text. Verified in the rendered HTML that these render safely escaped
(e.g. `->` → `-&gt;`, apostrophe → `&#x27;`) — confirmed `e()`'s
existing `html.escape()` is applied at every interpolation site, no raw
`<`/`>`/`&`/`"` reaches the page outside recognized tags (checked every
distinct tag name present in the rendered output — all are legitimate
markup, none injected from data).

## 8. report.py --check
`OK: .../CURRENT_STATUS.md matches the live database.` — exit 0.

## 9. Live DB contamination
`git status --porcelain` and `git diff --stat -- ops/db/operations.sqlite3`
both empty after all testing. All read-only calls used `dbutil.connect()`'s
`mode=ro` connection (verified this refuses writes, per Code Review's own
already-verified claim). The one full HTTP end-to-end test ran entirely
against an isolated scratch copy of the whole tree
(`/tmp/.../scratchpad/e2e/`) with its own `.founder_credential.json` and
its own copy of `operations.sqlite3` (`OPSDB_PATH` env override) —
deleted in full afterward, confirmed via `find` for `.founder_credential*`
(no matches) and directory listing (no `e2e*` artifacts remain). No test
server process left listening (port 8621 confirmed free).

## Summary
No defects found. Real-data verification confirms every claim in Code
Review's PASS. One caveat, not a defect: the `orchestrator` →
"Chief of Staff" `display_name()` path for review/QA/deployment rows has
no real row to exercise it against yet (no `orchestrator`-attributed
review/QA/deployment row exists in the live DB today) — verified
correct via direct function call and code-path inspection instead, same
gap Code Review itself already disclosed as non-blocking.
