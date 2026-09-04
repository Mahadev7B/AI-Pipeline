# Code Review — Chief of Staff rename (TASK-012)

Reviewing commit `79343f8` against `ops/reviews/cto-chief-of-staff-rename.md`
(section 4 file list, including the "1i. Correction" fold-in) and
`ops/reviews/red-team-chief-of-staff-rename.md` (PASS at Round 3).
Performed directly against the actual diff (`git show 79343f8`), the
live DB, and re-generated output — not the commit message or
Development's own report.

## Verdict: REJECT

## Scope conformance (confirmed good)

- `git show --stat 79343f8`: all 44 changed files are accounted for by
  section 4's list plus the generated-artifact regenerations section 5
  calls for. Spot-checked 8 of ~17 section-4 files in full diff form:
  `ops/db/derived_state.py`, `generate_inbox.py`, `generate_decisions.py`
  (sys.path fix present, matches Red Team's required fix exactly),
  `generate_pipeline.py`, `generate_agents.py`, `generate_overview.py`,
  `.claude/agents/orchestrator.md`, `ops/agents/orchestrator.md`,
  `ops/DATA_MODEL.md`, `ops/ARCHITECTURE.md` — all match the plan's
  prescribed change exactly, nothing extra.
- Confirmed absent from the diff (grep over `git show --stat`):
  `ops/db/schema.sql`, `ops/db/opsdb.py`, `ops/control-center/
  agent_runtime.py`, `ops/control-center/meeting_orchestrator.py`,
  `ops/control-center/server.py`, `ops/DECISIONS.md`, every
  `ops/reviews/*.md`, and the `.dc.html` mockups.
- `.claude/agents/orchestrator.md` and `ops/agents/orchestrator.md`:
  `name:`/frontmatter and filenames unchanged, prose-only, "(internal
  identity: orchestrator)" annotation preserved as recommended.
- `ops/DATA_MODEL.md`'s `meeting-{id}-orchestrator` thread-id string is
  untouched (only the surrounding prose word changed) — correct per 1h.
- `decisions.html`'s unexpectedly large +38/-4 diff was investigated:
  decisions #6 and #7 were created in the DB on 2026-08-29/30, before
  this commit, but `decisions.html` was already stale (previous commit
  `8013d5c` only shows 5 cards). The full regen this task requires
  legitimately caught up that pre-existing staleness as a byproduct —
  not scope creep, no fabricated content.
- Historical stored values confirmed untouched: `tasks.current_owner`
  and `decisions.recommending_agent` still contain the literal string
  `'orchestrator'` for pre-existing rows (verified via direct query);
  `agents` row `id=1` still has `name='orchestrator'`. (The `messages`
  table is currently empty in this DB instance, so the specific
  `from_agent='orchestrator'` spot-check the brief requested returned no
  rows — not a rename defect, just empty history in this DB snapshot;
  the equivalent check via `tasks`/`decisions` confirms the same
  invariant.)
- `python3 -c "import generate_inbox, generate_decisions"` succeeds
  cleanly — the two previously-broken imports (Red Team round 1 finding)
  are fixed.
- Every `display_name()` call site passes through the existing `e()`
  escaping before interpolation — no new XSS surface (verified across
  all 7 touched files).
- Live re-run of `generate_agents.py` against the (now slightly
  advanced, shared/live) DB reproduces the committed output except for
  the timestamp line and one new activity-log row from unrelated
  concurrent work (TASK-013) — confirms the generator is deterministic
  and the committed artifacts are not stale relative to the code.

## Blocking finding

### 1. `agent_status_rows()` sorts by machine key, not display name — "Chief of Staff" renders out of alphabetical order on both render sites that use it

`ops/db/derived_state.py`'s `agent_status_rows()` does `ORDER BY a.name`
(the machine key), and `display_name()` is applied only afterward, at
render time. Confirmed live in the committed artifacts themselves:

- `ops/control-center/agents.html` (roster): "Chief of Staff" appears
  between "marketing" and "product" — orchestrator's alphabetical slot —
  instead of between "ceo" and "code-review", where "Chief of Staff"
  actually belongs.
- `ops/reports/CURRENT_STATUS.md`'s `## Agents` section shows the
  identical mis-ordering.

Every other row in both lists is correctly alphabetized; "Chief of
Staff" is now visibly the one out-of-order entry on the exact two render
sites (Agent roster, CURRENT_STATUS.md) this feature was built to fix.
This is a real, currently-shipped correctness defect on the flagship
render site named in the CTO plan's own section 4/1b table ("Agent
roster card"), not a hypothetical edge case — worth blocking on.
`generate_overview.py`'s `render_active_now()` (also driven by
`agent_status_rows()`) has the same latent ordering exposure, currently
unobserved only because it isn't alphabetized in the UI.

**Required fix**: sort on the *displayed* label, not the raw key —
either re-sort the fetched rows in Python by `display_name(row["name"])`
before returning from `agent_status_rows()`, or equivalent. This is a
small, local fix; does not require re-litigating the design.

## Non-blocking findings (recommend fixing in the same pass since these files are already open)

### 2. `ops/db/report.py`'s "Founder decisions required" section renders `requested_by_agent` raw

Line 151: `f"- Approval #{a['id']} — {a['request']} (requested by
{a['requested_by_agent']})"` is not wrapped in `display_name()`, unlike
every other `requested_by_agent`/`recommending_agent` render site
touched by this diff (`generate_inbox.py`, `generate_overview.py`). Not
currently visible (no pending approvals in the live DB right now), but
`approvals.requested_by_agent` can hold `'orchestrator'` per the CTO
plan's own §1a inventory, and would then read "orchestrator" here while
`inbox.html`/`overview.html` say "Chief of Staff" for the identical
value — the exact "two names, one entity, same session" inconsistency
the plan explicitly designed around at every other site. This render
site was not enumerated in either the CTO plan's §1b table or §4's file
list, so this is a plan-level completeness gap Development inherited
rather than introduced — still worth a one-line fix since the file is
already open for this task.

### 3. `generate_meetings.py`'s `render_position_card()` doesn't wrap `requested_by_display`'s else-branch

Line 143: `requested_by_display = "Founder" if requested_by == "founder"
else requested_by` — unlike the adjacent `agent_name` label on line 151,
which was defensively wrapped in `display_name()` for the same
"unreachable today" reason (orchestrator is not in
`MEETING_PARTICIPANT_ALLOWLIST`). Currently dead code (confirmed no
caller passes a non-`"founder"` `requested_by` today), so no live
impact; flagged only because the same function already applies the
defensive-completeness treatment one line away and this is an easy
oversight to fix while the file is open.

## Disposition

Returning to Developer for finding 1 (blocking). Findings 2 and 3 are
recommended, non-blocking cleanups Development should fold into the same
fix pass. Once finding 1 is fixed, re-review the fix (not the whole diff
again) before this proceeds — do not move TASK-012 to QA in the
meantime. Task status itself is not mine to move; that stays with the
Chief-of-Staff/orchestrator per `ops/DATA_MODEL.md`.

---

# Re-review — fix for blocking finding 1 + non-blocking 2/3 (commits 3a4f47d, 2a9041e)

Re-reviewing only the fix, not the whole diff again. Read `git show
3a4f47d` and `git show 2a9041e` directly.

## Verdict: PASS

## Finding 1 (blocking) — verified fixed

`ops/db/derived_state.py`'s `agent_status_rows()` (commit `3a4f47d`) now
fetches rows with the `ORDER BY a.name` clause removed from SQL, and
re-sorts in Python: `sorted(rows, key=lambda row:
display_name(row["name"]).lower())`. Verified the `.lower()` is not
decorative but load-bearing: `display_name()` maps only `orchestrator`
to `"Chief of Staff"` (capital C); every other machine key is already
lowercase. Simulated both variants —

- without `.lower()`: `['Chief of Staff', 'ceo', 'code-review', 'cto',
  ...]` — "Chief of Staff" sorts *first*, before every other agent
  (ASCII `'C'` (67) < `'c'` (99)), which is a *different*, arguably worse
  bug than the one originally rejected.
- with `.lower()`: `['ceo', 'Chief of Staff', 'code-review', 'cto',
  ...]` — correct.

Confirmed live against the real DB (read-only, working tree left clean
afterward): ran `python3 ops/control-center/generate_agents.py` and
`python3 ops/db/report.py`. `agents.html`'s "Available" grid and
`CURRENT_STATUS.md`'s `## Agents` section both show `ceo`, `Chief of
Staff`, `code-review`, `cto`, `design`, ... in that order — "Chief of
Staff" sits between "ceo" and "code-review" as required, not in
orchestrator's old alphabetical slot between "marketing" and "product."

## Findings 2/3 (non-blocking) — verified fixed

Commit `2a9041e`: `ops/db/report.py` line 151 now wraps
`a['requested_by_agent']` in `display_name(...)`; `display_name` is
imported at the top of the file (confirmed). `generate_meetings.py`
line 143's `render_position_card()` else-branch now does
`display_name(requested_by)` instead of the raw string; `display_name`
is imported. Both match the pattern used at every other
requested-by/recommending-agent render site in the codebase.

## Scope check — no creep

- `git show --stat 3a4f47d`: touches only `ops/db/derived_state.py`
  (+8/-2). Matches the blocking finding exactly.
- `git show --stat 2a9041e`: touches the two one-line fixes
  (`report.py`, `generate_meetings.py`) plus regenerated artifacts the
  commit message says it regenerates (`agents.html`, `agents/*.html`,
  `overview.html`, `meetings.html`, `CURRENT_STATUS.md`) and
  `operations.sqlite3` (binary, DB state — not a code change). No files
  outside this footprint.

## Artifact freshness — verified, not stale

Ran `generate_agents.py`, `generate_meetings.py`, and `report.py` live
against the current DB and diffed the result against the committed
artifacts. Every diff line was the "Generated ... UTC" timestamp
string only (regenerated ~2 min after the committed run) — no content or
ordering differences. `overview.html`'s larger diff in the commit
itself (new Pipeline Snapshot/Just Happened rows) reflects legitimate
DB state that changed between generator runs (new tasks/events), not
stale or fabricated content. Working tree restored to clean
(`git checkout --`) after the live verification run.

## Disposition

Both the blocking finding and the two non-blocking recommended cleanups
are correctly fixed, with no unresolved carry-over and no new scope
creep. TASK-012 is ready for QA next. Task status itself is not mine to
move; that stays with the Chief-of-Staff/orchestrator per
`ops/DATA_MODEL.md`.
