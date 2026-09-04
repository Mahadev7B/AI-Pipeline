# Code Review — Phase 2, Milestone 2B5 (TASK-014)

Reviewing commit `6763b7d` against `ops/reviews/cto-milestone2b5-architecture.md`
(authoritative "File-by-file change list, for Development") and the three
required conditions in `ops/reviews/red-team-milestone2b5-architecture.md`.
All findings below were independently re-derived from `git show 6763b7d`,
the live `ops/db/operations.sqlite3`, and a live `report.py --check` run —
not taken from the developer's commit message.

## Verdict: PASS

## Scope conformance (item 1)
`git show --stat 6763b7d` source changes exactly match the file-by-file
list: new `generate_reviews.py`, `generate_releases.py`, `reviews.html`,
`releases.html`; edited `derived_state.py` (+`release_readiness_gap`),
`generate_pipeline.py` (id= only), `layout.py` (NAV_LINKS append only),
`server.py` (two GET branches + two imports only, modeled on
`/decisions.html`). The remaining changed paths (`agents.html`,
`agents/*.html`, `decisions.html`, `inbox.html`, `meetings.html`,
`overview.html`, `pipeline.html`, `CURRENT_STATUS.md`,
`operations.sqlite3`) are all regenerated build artifacts / normal DB
state, not source changes: nav bar reflects the new `NAV_LINKS` entries
everywhere (expected fan-out of the one-line `layout.py` edit),
timestamps updated, `pipeline.html`/`overview.html` reflect TASK-014
itself now existing in `tasks` (BACKLOG) and real new activity/review
rows — confirmed by inspecting several of these diffs directly, not
assumed. `report.py`, `opsdb.py`, `schema.sql`, `agent_runtime.py`,
`meeting_orchestrator.py`, `founder_auth.py`, `ROADMAP.md` do not appear
in `--stat` at all — genuinely untouched.

## The three Red Team conditions — verified shipped, not just claimed
- **(a) `<details>` collapse**: `generate_reviews.py` defines
  `COLLAPSE_THRESHOLD = 10`, applied as `if len(rows) > COLLAPSE_THRESHOLD`.
  Live-queried `operations.sqlite3` directly: TASK-007 has 21 combined
  review+QA rows (5 review + 16 QA), matching Red Team's corrected number
  exactly. Read the actual shipped `reviews.html`: TASK-007's group is
  rendered inside `<details><summary>...show all 21</summary>`, collapsed
  by default. Real, not just claimed.
- **(b) Scope label**: `reviews.html`'s subhead reads "Full historical
  record — 39 code/security review result(s) and 56 QA result(s), ...
  including resolved failures on now-DONE tasks. For what needs
  attention right now, see the Founder Inbox or `CURRENT_STATUS.md`."
  Substantive, not a token gesture — it names both the "what" (full
  history including resolved-on-DONE) and points to the complementary
  narrower view.
- **(c) Neutral gap framing**: shipped `releases.html` copy is exactly
  "10 of 11 DONE tasks have no `deployments` row — this may reflect
  internal/tooling work with no discrete production release step, not
  necessarily a process gap." This matches Red Team's required correction
  verbatim and avoids the rejected "pre-existing gap in this project's
  own process discipline" framing entirely.

## generate_pipeline.py diff minimality (item 3)
`git show 6763b7d -- ops/control-center/generate_pipeline.py` — exactly
three lines changed, each adding only `id="task-{t["id"]}"` (or
`id="task-{id}"`) to an existing `<div class="card"...>` in
`render_needs_attention`, `render_backlog`, `render_stage_column`. No
other line touched.

## Auth (item 4)
`server.py` diff is two `import` lines plus two `if path ==` branches,
each a single `self._send_html(...)` call using the existing
`SESSION_TOKEN`, structurally identical to the pre-existing
`/decisions.html` branch. No new session/cookie/CSRF/credential code
anywhere in the diff.

## display_name() (item 5)
Confirmed in source: `generate_reviews.py` wraps `row["agent"]`
(`reviewed_by_agent`/`tested_by_agent`) and `row["returned_to_agent"]`
in `display_name()`; `generate_releases.py` wraps
`d["deployed_by_agent"]`. `derived_state.py`'s `_DISPLAY_NAMES = {"orchestrator": "Chief of Staff"}`
is unchanged and applies automatically. No orchestrator-attributed rows
exist yet in `review_results`/`qa_results`/`deployments` to visually
confirm end-to-end, but every render site that displays an agent-name
field is confirmed routed through `display_name()`, matching the
established pattern from every other screen.

## Credential hygiene (item 6)
`find ... -name ".founder_credential*"` — no matches anywhere in the
real checkout. `git show --stat 6763b7d` contains no such file. Working
tree is clean (`git status --porcelain` empty).

## XSS/escaping (item 7)
Checked every interpolation site in both new generators against
`layout.e()` (`html.escape`). All free-text fields —
`findings`, `scenario`, `defect_summary`, `created_at`, `title`,
`status`, `review_type`, `version`, `environment`, `release_notes`,
`rollback_plan`, `deployed_at` — pass through `e()`; agent-name fields
pass through `e(display_name(...))`. No raw interpolation found. (Minor,
non-blocking: `qa_results.reproduction_steps` is selected in
`generate_reviews.py`'s `_task_rows` query but never rendered — dead
column fetch, not a bug or security issue.)

## Maintainability (item 8)
`generate_reviews.py`/`generate_releases.py` follow
`generate_decisions.py`'s established shape exactly: same imports
(`connect`/`out_path`/`write_output` from `dbutil`; `e`/`page` from
`layout`; `display_name` from `derived_state`), same
`render_*()` → `build_html()` → `main()` structure, same `OUT_PATH`
convention. No unnecessary abstraction; `release_readiness_gap()`
correctly lives in `derived_state.py` per Decision 3 rather than
hand-coded locally.

## report.py --check (item 9)
`python3 ops/db/report.py --check` → `OK: ... matches the live
database.` (exit 0), confirming `CURRENT_STATUS.md`'s regenerated state
is consistent and `report.py` itself is genuinely unmodified in behavior.

## Conclusion
No unresolved findings. Implementation matches the corrected CTO
architecture doc and all three Red Team conditions are verifiably
shipped, not merely asserted. PASS.
