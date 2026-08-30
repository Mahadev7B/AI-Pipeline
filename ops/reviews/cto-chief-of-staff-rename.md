# CTO architecture/impact review — rename "Orchestrator" to "Chief of Staff" (display only)

Founder decision: rename the human-facing company role currently called
"Orchestrator" to "Chief of Staff." Display/label clarification only — no
change to authority, permissions, or responsibilities; no second/duplicate
agent; exactly one operating coordination agent remains. Founder directive:
prefer preserving the stable machine identity `orchestrator`; do not rewrite
historical records merely to replace the word; only future UI, current role
documentation, and new human-facing output say "Chief of Staff."

This review verifies every current use of "orchestrator" against the live
codebase and database (not assumed), and recommends the smallest safe
implementation. It does not implement anything — Development acts on the
file list in "Files needing a change," below.

## 1. Every current use of "orchestrator," verified

### 1a. Machine/database identity — stable, NOT renamed

- `ops/db/schema.sql` line 18: `agents.name TEXT NOT NULL UNIQUE` — no
  `display_name` column exists anywhere in the schema. Confirmed by reading
  the full `CREATE TABLE agents` block (lines 17–29).
- Live database (`ops/db/operations.sqlite3`): `agents` row `id=1,
  name='orchestrator', role='Workflow management'` — confirmed by direct
  query. This is the only agent row that will ever need a *display* label
  different from its key; the row itself does not change.
- `agents.name` = `'orchestrator'` is also stored, as plain TEXT (not an
  FK), in every one of these columns, confirmed present with real
  `'orchestrator'` values in the live DB today:
  - `tasks.current_owner` — **4 currently open tasks** are owned by
    `orchestrator` right now (confirmed via `pipeline.html`, not just a
    hypothetical).
  - `decisions.recommending_agent` — 3 of 7 decision rows.
  - `approvals.requested_by_agent` — present (`inbox.html` shows "Requested
    by orchestrator").
  - `messages.from_agent`/`to_agent`, via `meeting_orchestrator.py`'s
    `opsdb.send_message(conn, ..., "orchestrator", ...)` (validation notes)
    and `opsdb.start_run(conn, "orchestrator", ...)` (agent_runs
    attribution).
  - `agent_activity.agent_id` (FK to `agents.id`, not the string — no
    rename impact) but rendered today with the joined `agents.name` string
    (`overview.html`'s Recent Activity feed, confirmed live: "**orchestrator**
    — Removing TASK-003...").
  - Schema also defines `task_status_history.changed_by_agent`,
    `risks.raised_by_agent`/`owner_agent`, `handoffs.from_agent`/`to_agent`,
    `qa_results.tested_by_agent`/`returned_to_agent`,
    `review_results.reviewed_by_agent`/`returned_to_agent`,
    `meetings.participating_agents` (JSON array of the string) as the same
    class of plain-TEXT identity column. None of these currently render the
    raw agent key as a standalone Founder-facing label in the Control
    Center beyond what's listed in 1b below (confirmed by reading every
    `generate_*.py`) — several print prose like "Risk raised by **this
    agent**" instead of the key.
- None of the above changes. `agents.name` stays `'orchestrator'`;
  `WHERE from_agent = 'orchestrator'` queries, `opsdb.start_run(conn,
  "orchestrator", ...)` calls, and every stored TEXT value keep reading and
  writing that literal string, unchanged, forever (including for meetings
  and messages created after this rename ships).

### 1b. Where the raw key is rendered as a Founder-facing label today

Every Control Center generator was read directly (not assumed). The raw,
unstyled, lowercase `agents.name` value is printed as-is in these places —
confirmed with the actual generated HTML, not just the generator source:

| Site | File | Confirmed live output |
|---|---|---|
| Agent roster card | `generate_agents.py` `render_roster()` | `agents.html`: `<div ...>orchestrator</div>` |
| Agent detail `<h1>` | `generate_agents.py` `build_agent_detail()` | `agents/orchestrator.html`: `<h1>orchestrator </h1>` |
| Agent detail `<title>` | `generate_agents.py` → `layout.page()` | `<title>orchestrator — Agent Detail — Command Center</title>` |
| Pipeline task-owner label | `generate_pipeline.py` `render_stage_column()` | `pipeline.html`: `orchestrator` on 4 open task cards right now |
| Overview → Pipeline mini-list | `generate_overview.py` `render_pipeline()` | same `current_owner` field, same page |
| Overview → Recent Activity | `generate_overview.py` `render_activity()` | `overview.html`: `<b>orchestrator</b> — Removing TASK-003...` |
| Overview → Founder Inbox summary | `generate_overview.py` `render_inbox()` | "Requested by orchestrator" |
| Inbox → full approval list | `generate_inbox.py` | `inbox.html`: "Requested by orchestrator" |
| Decisions → byline | `generate_decisions.py` | `decisions.html`: "Recommended by orchestrator" (3 of 5 visible rows) |
| Meetings → Orchestrator validation note | `generate_meetings.py` `render_orchestrator_note()` | hardcoded string literal `"Orchestrator — participant selection validated"` (label text is NOT derived from `agents.name` at all — it's typed directly in the function; the `WHERE from_agent = 'orchestrator'` query beside it is a stored-value lookup, unaffected) |
| Meeting position card | `generate_meetings.py` `render_position_card()` | not reachable for orchestrator today — see 1d |
| Ask-Agent bubble/placeholder | `generate_agents.py` `render_ask_agent_section()` | not reachable for orchestrator today — see 1d |
| `ops/db/report.py` → `CURRENT_STATUS.md` | project-manager-generated status doc | `ops/reports/CURRENT_STATUS.md`: `- orchestrator: available` |

This confirms the task brief's framing exactly: **every one of the 14
agents** gets this same raw-key treatment everywhere its identity is shown
— this is a systemic pattern, not something special-cased for orchestrator.
The rename doesn't need to fix that pattern for the other 13; it needs one
row in a lookup table applied at each of these call sites.

### 1c. `dbutil.py` / `derived_state.py` — two different "shared" modules, only one is actually the right home

- `ops/control-center/dbutil.py` (read myself, full file) is imported by
  every `ops/control-center/generate_*.py` for DB connection/output-path
  handling. It has **no** display-name concept today. It is **not**,
  however, imported by `ops/db/report.py` — `report.py` lives in a
  different directory and opens its own connection.
- `ops/db/derived_state.py` (read myself, full file) is the module the
  project's own docstring already describes as "imported by both
  `ops/db/report.py` and `ops/control-center/generate_overview.py`... so
  ... never a second hand-typed copy that could drift" — it is the
  project's existing, established pattern for exactly this kind of
  cross-cutting, both-sides-of-the-tree shared logic (`agent_status_rows`,
  `scope_label`, `company_health`, `task_progress_pct`). `report.py`'s
  "orchestrator: available" line in `CURRENT_STATUS.md` (1b, last row)
  means the fix needs to reach `ops/db/report.py` too, and `dbutil.py`
  cannot do that — it isn't on `report.py`'s import path.
- **Recommendation: put `display_name()` in `ops/db/derived_state.py`**,
  not a new file and not `dbutil.py`. This is a refinement of the brief's
  candidate design, not a rejection of it — same one-function, one-mapping
  shape, just placed where the codebase's own existing DRY convention
  already puts identically-shaped shared logic, so both `report.py` and
  every Control Center generator reach it through an import path that
  already exists today, with no new cross-directory `sys.path` wiring
  needed beyond what each already has.

### 1d. `agent_runtime.py` — allowlists and the validation activity label

- `ASK_AGENT_ALLOWLIST = ("cto", "qa", "ceo", "financial",
  "project-manager")` and `MEETING_PARTICIPANT_ALLOWLIST = ("ceo",
  "product", "cto", "financial", "marketing", "qa", "security",
  "red-team")` — confirmed by reading the file directly: **neither tuple
  contains `"orchestrator"`**, and `server.py` never checks it against
  either. Orchestrator/Chief of Staff is not Ask-Agent-invokable and is not
  a meeting position-holder in this milestone. This meaningfully bounds the
  blast radius: `render_ask_agent_section()`'s and
  `render_position_card()`'s `e(name)` renders are simply never reached for
  this agent today, so they need no code change for this rename to be
  complete (see 1b table) — worth changing anyway for defensive
  completeness/consistency, but not required.
- `ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL = "Orchestrator: validating
  meeting participant selection"` and `ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE
  = "Orchestrator:%"` — confirmed real, paired LABEL/LIKE constants.
  `LABEL` is written to `agent_runs.current_activity` by
  `meeting_orchestrator.py`'s `opsdb.start_run(conn, "orchestrator",
  "company", agent_runtime.ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL)`, and
  would appear in the "Current activity" field on `agents/orchestrator.html`
  for the few seconds a meeting's participant-selection validation is
  in flight (a deterministic Python step, not an LLM call — genuinely
  brief). `LIKE` is used only by `opsdb.reconcile_orphaned_runs()` at
  server startup, matching against **stored** `current_activity` text to
  find and fail orphaned runs left open by a prior server process.
  **Recommendation: leave both unchanged.** Three independent reasons: (1)
  this is a runtime-matching predicate, not a rendered label the Founder
  reads in the way an agent-card or task-owner field is — it is visible
  only for the few seconds a validation run is genuinely in flight; (2)
  `LABEL` and `LIKE` must always change together and the change is only
  correct for *newly started* runs — any run already open (or, ended but
  historically stored) with the old `"Orchestrator:..."` prefix stops
  matching a new `"Chief of Staff:..."` `LIKE` pattern, which is exactly
  the kind of narrow-window orphan-reconciliation gap this constant exists
  to prevent, for a purely cosmetic few-seconds-of-visibility gain; (3) the
  Founder's own directive to avoid unnecessary migration risk applies here
  by the same logic as the DB schema — this is semi-durable runtime state,
  not just transient UI text. Flagged as a residual, deliberately-not-changed
  item in section 5, not silently dropped.

### 1e. `meeting_orchestrator.py` — module name

- `ops/control-center/meeting_orchestrator.py` is a Python module
  implementing the meeting engine, used by both the CEO agent's
  participant-selection step and the orchestrator/Chief-of-Staff agent's
  validation step (`_validate_selection()`, confirmed by reading the file).
  Its name is a legacy/coincidental naming choice from Milestone 2B3B, not
  a synonym for "the Orchestrator agent role" — many of its internal
  comments use "Orchestrator" descriptively (e.g. "Orchestrator validates
  → positions gathered concurrently") to describe *what the code does*, not
  to label anything a Founder sees.
- **Recommendation: leave the filename and module name unchanged.**
  Renaming it would touch every importer (`server.py`,
  `generate_meetings.py`) for zero Founder-visible benefit — nothing in
  this module's name is ever rendered to the Founder — and is explicitly
  out of scope for a "display/label clarification only" directive. Not
  required, not recommended.

### 1f. The Claude Code subagent alias (`.claude/agents/orchestrator.md`)

- Confirmed: this file's frontmatter (`name: orchestrator`) is the literal
  `subagent_type` string every invocation of this agent uses. Renaming this
  *file* (or its `name:` field) to `chief-of-staff` would change the
  invocable identifier itself — every caller/reference across the
  operating system would need updating in lockstep, and a careless version
  of this change (e.g. leaving the old file in place too, "just in case")
  is exactly the failure mode the Founder explicitly forbade: it would read
  as *two* agents (`orchestrator` and `chief-of-staff`) both nominally
  active, when the Founder's directive requires exactly one operating
  coordination agent, unambiguously.
- **Recommendation: keep the filename and `name:`/`subagent_type` field
  `orchestrator`, unchanged.** Change only the human-facing prose *inside*
  the file — its role-title heading and the sentence introducing it — to
  read "Chief of Staff" while keeping "orchestrator" visible as the stable
  internal identity, e.g.:
  - `.claude/agents/orchestrator.md` line 7: `You are the Orchestrator
    agent...` → `You are the Chief of Staff (internal identity:
    orchestrator)...` — same pattern, new label, old key still legible
    right next to it so nobody misreads this as a second agent.
  - `ops/agents/orchestrator.md` line 1: `# Orchestrator Agent` → `#
    Chief of Staff (Orchestrator)` — filename stays `orchestrator.md`
    (this is documentation content, not an invocable identifier, so the
    filename itself carries no functional risk, but renaming *the file*
    would still cost every doc cross-reference in the repo for no
    functional gain — content-only change recommended here too, same
    "smallest safe change" reasoning).
- This is the same shape of caution the brief already flagged for
  `meeting_orchestrator.py` (1e) — file/identifier stability trumps a
  cosmetic win. Genuinely the highest-risk item on this list if handled
  carelessly, and the smallest-scope item if handled as recommended (prose
  only, inside the file).

### 1g. `server.py` allowlists — confirmed empty of "orchestrator"

- `ASK_AGENT_ALLOWLIST` and `MEETING_PARTICIPANT_ALLOWLIST`, defined in
  `agent_runtime.py` and consumed by `server.py`, do not contain
  `"orchestrator"` (confirmed by direct read, 1d). This constrains blast
  radius: no write route, no authorization check, and no invocation path
  changes as part of this rename.

### 1h. Documentation referencing "Orchestrator" as a role name

Confirmed by direct grep of every file the brief named, plus a full-repo
sweep:

- **Update (current role documentation → should say Chief of Staff):**
  `ops/agents/orchestrator.md`, `.claude/agents/orchestrator.md` (prose
  only, per 1f) — these ARE the current role documentation the Founder's
  directive names explicitly.
- **`ops/AGENT_ARCHITECTURE.md`** line 23: `Escalation Rules: <when it
  hands to Orchestrator / raises FOUNDER_APPROVAL>` — this is the
  *template* every other agent's `AGENT_ARCHITECTURE.md` entry is written
  against (confirmed: it's inside a fill-in-the-blanks template block, not
  a specific agent's live entry). Update the word here too — it is live,
  current, reusable documentation, not a historical record of a past
  decision.
- **`ops/DATA_MODEL.md`** — 4 hits (lines 69, 194, 245, 273), all live,
  current schema/behavior documentation (e.g. "The Orchestrator is the only
  writer of `tasks.status`," the `meeting-{id}-orchestrator` thread-naming
  rule). Update the prose word "Orchestrator" → "Chief of Staff" in these;
  the `meeting-{id}-orchestrator` thread-id string itself is a stored
  value/naming convention, not a display label — leave that string alone
  (matches 1a's rule for stored identifiers).
- **`ops/EXECUTIVE_MEETINGS.md`** line 20: "**Orchestrator** + CEO Agent
  select participants." Live functional spec — update the word.
- **`ops/reports/CURRENT_STATUS.md`** line 47 (`- orchestrator: available`):
  this is a *generated* file (`ops/db/report.py`), not hand-edited — see
  1c/2 for the code fix; the committed file itself gets refreshed by
  re-running the generator, same as every other generated artifact (5).
- **`ops/PROJECT.md`**: confirmed no direct mention (grep returned no hit)
  — nothing to change here.
- **`ops/ROADMAP.md`**: confirmed no hit — nothing to change here (the
  brief anticipated a mention that, on inspection, isn't there; noted so
  Red Team doesn't waste time re-checking).
- **Do NOT touch (historical, by the Founder's explicit rule):**
  `ops/DECISIONS.md` (generated mirror of the `decisions` table —
  `recommending_agent = 'orchestrator'` on DEC-003/004/005 stays exactly as
  recorded; never hand-edited per this repo's own rule, and never
  retroactively relabeled), every `ops/reviews/*.md` file that mentions
  "Orchestrator" (23 files, confirmed by grep — these are dated review/
  decision records, not living documentation), `prompts/phase-0-architecture-
  proposal.md` (historical prompt record), and the three
  `ops/mockups/control-center-phase-0/*.dc.html` files (`Agents.dc.html`,
  `Main.dc.html`, `OverviewLight.dc.html`) — the Founder-approved mockup
  artifact itself, which is a historical design record, not live UI.
  (Incidental note, not an action item: those approved mockups already show
  capitalized "**Orchestrator**" as the intended display label, which the
  implementation never actually matched — today's code shows the raw
  lowercase key everywhere, per 1b. This rename happens to close that small
  pre-existing mockup-conformance gap for this one agent as a side effect;
  it is not, itself, the reason to do the rename, and does not extend to
  fixing the same gap for the other 13 agents, which is out of scope.)

## 1i. Correction (Red Team round 1, ops/reviews/red-team-chief-of-staff-rename.md) — verification gaps in this document

Red Team's round-1 review rejected the original version of this document for
demonstrably incomplete verification, despite this document's own claim of a
"full-repo sweep." Every point below is independently re-verified, folded in
here so the file list in section 4 is now actually complete:

- **`generate_decisions.py` and `generate_inbox.py` cannot reach
  `ops/db/derived_state.py` as currently written.** Verified: only
  `generate_overview.py`, `generate_pipeline.py`, `generate_agents.py`, and
  `generate_meetings.py` carry the second `sys.path.insert(0,
  str(Path(__file__).resolve().parent.parent / "db"))` line needed to import
  `derived_state`; `generate_decisions.py` and `generate_inbox.py` only
  insert their own directory (for `dbutil`/`layout`). The original claim "no
  new cross-directory sys.path wiring needed beyond what each already has"
  was false for 2 of 6 generators. **Fix, now reflected in section 4**:
  Development must add the same `sys.path.insert(0,
  str(Path(__file__).resolve().parent.parent / "db"))` line to both files,
  before `from derived_state import display_name`.
- **`ops/ARCHITECTURE.md` (root-level) was missed entirely.** Verified live,
  it names "Orchestrator" as a role with real authority, twice: line 10
  ("2. **Orchestrator** — the only thing that decides what happens next and
  assigns work...") and lines 39/41 ("The Orchestrator is the only writer of
  Task State... Orchestrator — it does not mutate rows directly."). This is
  the same class of live, current documentation as `AGENT_ARCHITECTURE.md`
  (already included) — now added to section 4.
- **Other agents' own current role docs name "Orchestrator" and were
  omitted**, which would leave a directly inconsistent doc set (Orchestrator's
  own doc says "Chief of Staff," CEO's and Project Manager's docs keep
  calling the same entity "Orchestrator"). Verified live:
  `.claude/agents/ceo.md:31` ("Orchestrator — select who participates in an
  Executive Meeting."), `ops/agents/ceo.md:52` ("With Orchestrator, select
  which agents participate..."), `.claude/agents/project-manager.md:18`
  ("(that's Orchestrator's job)"), `ops/agents/project-manager.md:24` ("that's
  Orchestrator's..."). Now added to section 4, same prose-only treatment as
  Orchestrator's own docs.
- **Lower-priority: four `ops/skills/**` docs** (`ops/skills/README.md`,
  `ops/skills/operations/loop.md`, `ops/skills/operations/skill-creator.md`,
  `ops/skills/product/prompt-master.md`) reference "Orchestrator Agent" as a
  named skill user/owner — same "current documentation" bucket, lower
  material weight (internal skill registry, not Founder-facing). Added to
  section 4 for completeness.
- **Accuracy correction**: section 4's original note that `ops/db/opsdb.py`
  has "no `orchestrator` literal found in it at all" was imprecise — a grep
  returns six hits, all in comments/docstrings describing
  `meeting_orchestrator.py`'s behavior, none a Founder-rendered string or a
  code literal needing change. The conclusion (no code change needed) still
  holds; the stated justification was wrong. Corrected below.
- **`ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL`/`_LIKE`** (1d): Red Team
  affirmed "leave unchanged" as reasonable — every render site showing
  `current_activity` is a static, regenerate-on-demand page, not a
  live-polling dashboard, making the real exposure window lower than even
  this document's own original reasoning suggested. Red Team also confirmed
  a *display-only* decoupling (substituting "Orchestrator:" → "Chief of
  Staff:" at exactly the four render sites, never touching the stored
  `LABEL`/`LIKE` constants) is technically feasible if the Founder later
  wants it — noted as an optional, cheap future follow-up in section 5, not
  required now.

## 2. Recommended design: smallest safe change

Adopt the brief's candidate design, refined per 1c:

**Add one function, `display_name(machine_key: str) -> str`, in
`ops/db/derived_state.py`** (not `dbutil.py`, not a new file — see 1c for
why this specific module is the correct shared home):

```python
_DISPLAY_NAMES = {"orchestrator": "Chief of Staff"}

def display_name(machine_key: str) -> str:
    """Founder-facing label for an agents.name value. Out of scope for
    every agent except 'orchestrator' by explicit Founder instruction —
    do not add entries for the other 13; the default fallback (the key
    itself, unchanged) is correct for all of them. Never apply this to a
    stored DB value, a query predicate, a thread_id, or historical
    message/decision/review body text — only to a label rendered for the
    Founder to read. See ops/reviews/cto-chief-of-staff-rename.md."""
    return _DISPLAY_NAMES.get(machine_key, machine_key)
```

**Apply it at every Founder-facing render site identified in 1b** — the
full set, not just the four the brief's candidate design named, because
1b's live evidence shows Pipeline, Overview, Inbox, and Decisions all
render this exact same raw key, several of them *right now* for real open
tasks/decisions, on the same dashboard as the Agents screens the narrower
candidate design would have fixed. Wrapping only the Agents screens would
leave the Founder seeing "Chief of Staff" on one screen and "orchestrator"
on four others for the identical entity in the same session — a worse,
inconsistent outcome, not a smaller-risk one. Concretely:

- `generate_agents.py`: roster card label, agent detail `<h1>`, `<title>`
  (via the `name` argument passed into `page()`), and (defensively, though
  unreachable today per 1d) the Ask-Agent sender label/placeholder.
- `generate_pipeline.py`: the task-owner label (`t["current_owner"] or
  "unassigned"` — wrap only the non-`None` branch; `"unassigned"` is not an
  agent key).
- `generate_overview.py`: `render_active_now()`'s name label, `render_pipeline()`'s
  owner field (same column as Pipeline, same rule), `render_activity()`'s
  agent label, `render_inbox()`'s "Requested by" label.
- `generate_inbox.py`: add `sys.path.insert(0,
  str(Path(__file__).resolve().parent.parent / "db"))` (missing today —
  Red Team finding, 1i) before importing `display_name`; wrap "Requested by"
  label.
- `generate_decisions.py`: add the same `sys.path.insert(...)` line (missing
  today — Red Team finding, 1i); wrap "Recommended by" label.
- `generate_meetings.py`: `render_orchestrator_note()`'s label — this one
  is a hardcoded string literal today (1b), not derived from `agents.name`
  at render time; replace the literal `"Orchestrator"` with
  `display_name("orchestrator")` so the mapping has one source of truth
  instead of a second, independently-typed copy of the same word that
  could drift out of sync later. `render_position_card()`'s `e(agent_name)`
  label — defensively wrapped though unreachable today per 1d (orchestrator
  is not in `MEETING_PARTICIPANT_ALLOWLIST`).
- `ops/db/report.py`: the `## Agents` section's `f"- {row['name']}: ..."`
  lines, importing `display_name` alongside the `agent_status_rows` it
  already imports from `derived_state.py`.

Every one of these sites already escapes with `layout.e()` (Control Center)
or writes plain text (`report.py`) — `display_name()` is applied *before*
`e()`/string interpolation, changing nothing about the existing escaping
discipline.

## 3. Explicitly out of scope — no migration

- No DB schema migration. No new `agents` table row. No `display_name`
  column.
- No renamed `agents.name` value — the row stays `id=1, name='orchestrator'`.
- No renamed `.claude/agents/orchestrator.md` file or `subagent_type`
  string — internal machine identity, and the invocable identifier every
  caller uses, both stay `orchestrator`, permanently, per 1f.
- No change to `ASK_AGENT_ALLOWLIST` / `MEETING_PARTICIPANT_ALLOWLIST`
  (orchestrator is in neither today and this rename doesn't add it — that
  would be a scope/authority change, not a label change, and is explicitly
  not requested).
- No change to `ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL` /
  `ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE` (1d) or to
  `meeting_orchestrator.py`'s module name (1e).
- No rewriting of any stored `from_agent`/`to_agent`/`recommending_agent`/
  `requested_by_agent`/`current_owner`/`participating_agents` value, no
  rewriting of any message/decision/review/meeting body text, and no
  hand-editing of `DECISIONS.md` or any `ops/reviews/*.md` file.

## 4. Files needing a code or doc change (for Red Team and Development)

| File | Change | Reason |
|---|---|---|
| `ops/db/derived_state.py` | Add `display_name()` + `_DISPLAY_NAMES` | New shared mapping, single source of truth (1c, 2) |
| `ops/control-center/generate_agents.py` | Wrap roster label, detail `<h1>`, `<title>` name; Ask-Agent sender label/placeholder | Founder-facing agent identity renders (1b, 2) |
| `ops/control-center/generate_pipeline.py` | Wrap non-`None` `current_owner` label | Live today — 4 open tasks show raw key (1b) |
| `ops/control-center/generate_overview.py` | Wrap `render_active_now()`, `render_pipeline()`, `render_activity()`, `render_inbox()` labels | Same entity rendered raw on the landing screen (1b) |
| `ops/control-center/generate_inbox.py` | Wrap "Requested by" label | Live today (1b) |
| `ops/control-center/generate_decisions.py` | Wrap "Recommended by" label | Live today, 3 of 5 visible rows (1b) |
| `ops/control-center/generate_meetings.py` | `render_orchestrator_note()` label via `display_name("orchestrator")`; defensively wrap `render_position_card()`'s `agent_name` | Single source of truth for the hardcoded literal (2); defensive completeness (1d) |
| `ops/db/report.py` | Wrap the `## Agents` line's name | `CURRENT_STATUS.md` is Founder-facing generated status text (1b, 1h) |
| `.claude/agents/orchestrator.md` | Prose only: role-title/intro line reads "Chief of Staff," `name:`/`subagent_type` unchanged | Current role documentation (1f) |
| `ops/agents/orchestrator.md` | Prose only: `# Orchestrator Agent` heading and intro reads "Chief of Staff (Orchestrator)," filename unchanged | Current role documentation (1f) |
| `ops/AGENT_ARCHITECTURE.md` | Update the template line (line 23) | Live, reusable documentation, not a historical record (1h) |
| `ops/DATA_MODEL.md` | Update the 4 prose mentions; leave the `meeting-{id}-orchestrator` thread-id string itself unchanged | Live schema/behavior documentation vs. a stored identifier (1h) |
| `ops/EXECUTIVE_MEETINGS.md` | Update the "Orchestrator + CEO Agent select participants" line | Live functional spec (1h) |
| `ops/ARCHITECTURE.md` | Update the 2 live mentions (lines 10, 39, 41) | Live, current architecture documentation naming the role's authority — Red Team finding, 1i |
| `.claude/agents/ceo.md`, `ops/agents/ceo.md` | Prose-only: "Orchestrator" → "Chief of Staff" | Current role doc naming the entity — Red Team finding, 1i |
| `.claude/agents/project-manager.md`, `ops/agents/project-manager.md` | Prose-only: "Orchestrator" → "Chief of Staff" | Current role doc naming the entity — Red Team finding, 1i |
| `ops/skills/README.md`, `ops/skills/operations/loop.md`, `ops/skills/operations/skill-creator.md`, `ops/skills/product/prompt-master.md` | Prose-only: "Orchestrator Agent" → "Chief of Staff" | Current skill-registry documentation, lower priority — Red Team finding, 1i |

Not in this list, deliberately: `ops/db/schema.sql`, `ops/db/opsdb.py` (6
grep hits, all in comments/docstrings describing `meeting_orchestrator.py`'s
behavior, none a Founder-rendered string or a code literal needing change —
corrected per 1i from the original, imprecise "no literal found" claim),
`ops/control-center/agent_runtime.py` (1d), `ops/control-center/
meeting_orchestrator.py` (1e), `ops/control-center/server.py` (1g),
`ops/DECISIONS.md`, every `ops/reviews/*.md`, `prompts/phase-0-
architecture-proposal.md`, and the three `.dc.html` mockup files (1h).

## 5. Residual risk / intentionally not changed

- **Generated static HTML needs regeneration.** `agents.html`,
  `agents/*.html`, `overview.html`, `pipeline.html`, `decisions.html`,
  `inbox.html`, and `meetings.html` (+ `meetings/*.html`) are all
  build artifacts of their respective `generate_*.py` scripts (confirmed:
  every one carries a "Generated ... Not hand-edited; re-run ... to
  refresh" note). After Development lands the code change, these must be
  regenerated by running `generate_agents.py`, `generate_overview.py`,
  `generate_pipeline.py`, `generate_decisions.py`, `generate_inbox.py`, and
  `generate_meetings.py` (in any order — they don't depend on each other's
  output) — otherwise the committed HTML keeps showing the raw key until
  the next regen, which is a stale-artifact risk, not a code-correctness
  one. `ops/reports/CURRENT_STATUS.md` needs the same treatment via
  `ops/db/report.py` (and its own `--check` mode will correctly flag it as
  stale if the regen is forgotten).
- **`ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL`/`_LIKE` are deliberately left
  showing "Orchestrator:"** for the brief window a meeting's
  participant-selection validation is in flight. See 1d for the full
  reasoning (orphan-reconciliation risk vs. a few-seconds-of-visibility
  cosmetic gain). If the Founder later decides this specific text must
  change too, it is a small, separate, well-scoped follow-up (change
  `LABEL` and `LIKE` together, atomically, in the same commit as the code
  that starts new runs) — not bundled into this rename. A cheaper
  alternative, confirmed feasible by Red Team's round-1 review (1i), also
  exists if ever wanted: a display-only substitution ("Orchestrator:" to
  "Chief of Staff:") applied only at the four render sites that show
  `current_activity`, never touching the stored `LABEL`/`LIKE` constants —
  lower risk than changing the constants themselves, still not required now.
- **`meeting_orchestrator.py`'s module name is unchanged** (1e) — a
  legacy/coincidental name, never Founder-visible, not worth the
  cross-file churn for zero display benefit.
- **The Claude Code subagent file/identifier stays `orchestrator`** (1f) —
  the highest-leverage place to get this rename wrong (see 1f for why);
  recommended path only touches prose inside the file.
- **Historical text is genuinely left saying "Orchestrator"/"orchestrator"
  forever** — `DECISIONS.md`, every dated `ops/reviews/*.md`, the approved
  mockups, and every stored message/decision/review body — by explicit
  Founder instruction. This means the Founder will, correctly, keep seeing
  "Orchestrator" when reading old decision records and reviews even after
  this ships; that is the intended, honest behavior (a record reflects the
  name that existed when it was created), not a bug or an incomplete
  rename.
- **The other 13 agents' identical raw-key rendering pattern (1b) is not
  fixed by this change** — `display_name()`'s fallback returns every other
  key unchanged, by design, per the Founder's explicit "out of scope"
  instruction. If the Founder later wants friendlier display names for
  other roles, that is a separate, explicitly-scoped follow-up decision,
  not an incidental expansion of this one.
