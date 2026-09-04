# QA — Chief of Staff rename (TASK-012)

Testing performed against `ops/reviews/cto-chief-of-staff-rename.md` +
`ops/reviews/red-team-chief-of-staff-rename.md` (design) and
`ops/reviews/code-review-chief-of-staff-rename.md` (PASS at re-review),
commit `2a9041e` (tip of the branch at test time). Tested from a
Founder-perspective, driving the actual app, not reading source only.

## Verdict: PASS

## 1. Every render site — live DB (read-only server) + scratch-DB fabricated data

Started `ops/control-center/server.py` on scratch port 8765 against the
live database (server.py's GET routes are read-only) and curled every
site:

- `agents/orchestrator.html`: `<title>Chief of Staff — Agent Detail —
  Command Center</title>`, `<h1>Chief of Staff </h1>`.
- `agents.html`: roster card reads "Chief of Staff", `href` still points
  at `agents/orchestrator.html` (machine key untouched in the URL).
- `overview.html`: no live current-owner/inbox rows to show for
  orchestrator at test time (0 pending approvals, "Active Now" empty) —
  expected-empty, not a defect. Task-title text and activity-log message
  bodies containing the literal string "Chief of Staff" are stored task
  titles / commit-style prose, not `display_name()` output — correctly
  unaffected either way.
- `pipeline.html`: 4 live open tasks owned by `orchestrator`
  (TASK-005/006/007/009) all render the owner label as "Chief of Staff".
- `inbox.html`: 1 live (already-decided) approval requested by
  `orchestrator` (id 3) renders "Requested by Chief of Staff" — inbox.html
  renders resolved approvals too, not just pending, so this was live and
  checkable.
- `decisions.html`: 3 live decisions recommended by `orchestrator` (ids
  2, 3, 5) all render "Recommended by Chief of Staff".
- `meetings.html` / meeting detail pages: 0 meetings exist in the live DB
  — expected-empty.

Independently verified rendering-when-data-IS-present via a scratch
`OPSDB_PATH` database (never touched `operations.sqlite3`): seeded a fake
`orchestrator`-owned task (IN_DEVELOPMENT), a fake decision
(`recommending_agent=orchestrator`), a fake approval
(`requested_by_agent=orchestrator`), and — for the meetings gap — a fake
meeting plus a `messages` row on thread `meeting-{id}-orchestrator` with
`from_agent='orchestrator'` (mirrors what `meeting_orchestrator.py` writes
for the real validation note). Reran `generate_agents/pipeline/overview/
decisions/inbox/meetings.py` against the scratch DB:
- Pipeline card, inbox "Requested by", decisions "Recommended by", agent
  roster card, agent detail `<h1>`/`<title>` all show "Chief of Staff".
- Meeting detail page renders `Chief of Staff — participant selection
  validated` for the fabricated validation note — confirms
  `render_orchestrator_note()`'s `display_name("orchestrator")` call is
  correct and was reachable, closing the "0 live meetings" gap the live
  smoke test alone couldn't cover.

Stopped the server (confirmed process killed, port unreachable) when
done.

## 2. Ordering regression — re-verified live, not trusted from the report

`agents.html`'s roster and `ops/reports/CURRENT_STATUS.md`'s `## Agents`
section both show `ceo, Chief of Staff, code-review, cto, design, ...` —
"Chief of Staff" sits between "ceo" and "code-review" as required, not in
orchestrator's old alphabetical slot between "marketing" and "product".
Confirmed directly against the live-served HTML and the live markdown
file, not by re-reading Code Review's report.

## 3. Historical records untouched

Queried the live DB directly:
- `tasks.current_owner = 'orchestrator'` on 4 rows (ids 5, 6, 7, 9).
- `decisions.recommending_agent = 'orchestrator'` on 3 rows (ids 2, 3, 5).
- `approvals.requested_by_agent = 'orchestrator'` on 1 row (id 3).
- `agents` row id=1 still `name='orchestrator'`.

All literal, unrewritten — these are current/live fields (correctly
re-rendered as "Chief of Staff" going forward on every render site above),
not immutable historical text, so `display_name()` applying to them is the
intended behavior, not a violation of "don't rewrite history."

Checked prose body text: `ops/DECISIONS.md` still reads "Orchestrator"
verbatim in 3 places (lines 34, 54, 64 — "Agent recommending it:
Orchestrator."). `messages` table is empty in the live DB (0 rows), so the
`from_agent='orchestrator'` message-body spot-check the brief asked for
had nothing live to check directly — same gap Code Review's report
already disclosed; the scratch-DB meeting-message test in section 1
exercises the equivalent code path with fabricated data instead.

## 4. No second agent created

`agents` table: exactly 14 rows, exactly one row with `name='orchestrator'`
(id=1), no `chief-of-staff` row or variant. Confirmed by direct query.

## 5. Subagent identity unaffected

`.claude/agents/orchestrator.md` line 2: `name: orchestrator` — unchanged.

## 6. Other 13 agents unaffected

Spot-checked `ceo`, `qa`, `cto` detail pages: `<h1>ceo <span ... >AI
ADVISOR — NOT THE FOUNDER</span></h1>`, `<h1>qa </h1>`, `<h1>cto </h1>` —
all render their raw machine key unchanged, exactly as before; `ceo`'s AI
ADVISOR badge is intact. `display_name()`'s fallback is a no-op for every
key except `orchestrator`, confirmed.

## 7. report.py --check

`python3 ops/db/report.py --check` → `OK: ... matches the live database.`
exit code 0. (Note: `python3 ops/db/report.py --help` is not a real flag —
`report.py` has no argparse `--help` handling and silently falls through
to its default "regenerate the report" behavior instead, which
regenerated the live `CURRENT_STATUS.md` in place with only the
timestamp line changed; reverted via `git checkout --` immediately after
confirming this. Unrelated to the rename — pre-existing CLI-ergonomics
gap in `report.py`, not a defect of TASK-012's diff. Its real
staleness-check invocation is `--check`, confirmed from the file's own
usage docstring and its `sys.argv` handling.)

## 8. Edge/adversarial

- **Idempotency**: reran `generate_agents/pipeline/overview/decisions/
  inbox/meetings.py` twice in a row against the live DB; diffed run 1 vs.
  run 2 output — zero byte differences (including the timestamp line, both
  runs landed in the same UTC minute). No accumulating diffs. Restored the
  working tree with `git checkout --` afterward (read-only exercise, no
  intended commit).
- **ImportError not silently swallowed**: copied the tree into a scratch
  directory (`ops/control-center` + `ops/db` siblings, matching the real
  layout) and renamed the scratch copy's `ops/db/derived_state.py` to
  `derived_state_renamed.py`. Ran the scratch copies of `generate_inbox.py`
  and `generate_decisions.py` against a scratch DB: both crashed with a
  full traceback (`ModuleNotFoundError: No module named 'derived_state'`)
  and non-zero exit code — loud, correct failure, not a silent no-op.

## Non-blocking observations (not TASK-012 regressions, noted for completeness)

1. **`generate_overview.py`'s `render_pipeline()` never actually renders
   `current_owner`** — it selects the column in SQL but the HTML template
   only uses `title`/`status`/progress. This predates this rename
   (confirmed via `git show 8013d5c:ops/control-center/generate_overview.py`,
   the commit immediately before this task's diff — identical, already
   dead SQL column back then). The CTO plan's §1b/§4 table describes this
   as a render site needing a `display_name()` wrap ("Overview → Pipeline
   mini-list ... same `current_owner` field, same page"), which slipped
   through CTO, Red Team (3 rounds), and Code Review without being
   caught — but since the field was never rendered before or after this
   diff, there is no live "orchestrator" leak here and no functional
   defect; it's a plan-accuracy footnote, not a QA fail.
2. **`python3 ops/db/opsdb.py --help` crashes** with an argparse
   `ValueError: incomplete format` (some subcommand's `help=` string
   contains a stray `%`). Pre-existing, unrelated to this rename,
   confirmed out of scope of the diff (`opsdb.py` is not in TASK-012's
   file list per the CTO plan §4, and Code Review already confirmed no
   `opsdb.py` code changes shipped). Flagging for whoever owns
   `opsdb.py` CLI ergonomics next, not a TASK-012 defect.

## Cleanup

Live `operations.sqlite3` was never written to (14 agents / 11 tasks / 0
meetings before and after). All scratch databases, seeded meeting/task/
decision/approval rows, and the scratch-directory ImportError repro live
only under this session's scratchpad and have been deleted. Working tree
restored to clean for every file this QA pass touched
(`ops/control-center/*.html`, `ops/reports/CURRENT_STATUS.md`).
