# CTO — Milestone C Architecture: Company-wide Risks Register (TASK-021)

Date: 2026-09-01
Author: CTO
Directive: DEC-009 (`ops/DECISIONS.md`), `ops/ROADMAP.md`'s "Founder UI
Completeness" section — Founder-approved four-milestone plan, Milestone C.
Milestones A (`ops/reviews/cto-milestone-a-architecture.md`, TASK-019) and
B (`ops/reviews/cto-milestone-b-architecture.md`, TASK-020) are both DONE;
this document extends what they built, not a parallel system.
Scope discipline: **architecture only.** Nothing here is implemented.
Read-only page, zero new write routes, zero change to the Founder
session/CSRF gate, zero change to how a risk is created or resolved
today (`opsdb.py risk-add` / `risk-resolve` stay the only writers).
Does not touch TASK-017's own active investigation, does not resolve or
narrow `risks.id=3`, does not start Milestone D.

---

## Part 0 — What carries over unchanged from Milestones A and B

- **Precedent for a top-level, read-only list page**: `generate_decisions.py`
  (`/decisions.html`), `generate_active_work.py` (`/active-work.html`) —
  `build_html(token=None)` self-connecting via `dbutil.connect()`
  (`mode=ro`), rendered through `layout.page()`, one new `NAV_LINKS` entry.
  `/risks.html` follows this exactly.
- **Precedent for a single shared computed function backing a page**:
  `derived_state.task_progress_row()` (Milestone A), `company_cost_digest()`
  (Milestone B). This milestone adds `risk_register_rows()` to the same
  file, same discipline — computed once, rendered by exactly one page (plus
  reused, unchanged, by the two existing per-agent risk queries in
  `generate_agents.py`, see Part 5).
- **Precedent for honest, disclosed gaps instead of invented data**: every
  "not available" / "—" convention `task_cost_usd()` and
  `company_cost_digest()` established stays in force here — no risk field
  is ever fabricated, and this milestone's own biggest finding (Part 1) is
  itself disclosed on the page, not hidden.
- **The existing per-agent risk rendering** (`generate_agents.py:244-274`,
  `risks_owned`/`risks_raised`) is confirmed, on rereading it for this
  document, to still earn its place: it answers "what is this specific
  agent responsible for / has this agent flagged," a different question
  than "show me every risk in the company," and costs nothing extra to
  keep. It is **not removed**. One small, additive change: both lists gain
  a `→ full Risks register` link to `/risks.html#risk-{id}` (Part 3.4's
  anchor convention), so an agent's page becomes a cross-navigation point
  into the register instead of a dead end — the exact "supersedes the need
  to hunt through 14 agent pages," not "replaces what's already useful
  there," the milestone brief asks for.
- **Task-scoped risk rendering already exists**: `generate_task.py`'s
  `render_risks()` (Task Detail, §Part 3 of this doc). Its current
  "Associated risks" empty-state copy explicitly says company-scoped risks
  stay "visible only via Agent Detail pages until a future company-wide
  Risks register (Milestone C) ships" — that sentence becomes false the
  moment this ships and is updated (Part 5).

---

## Part 1 — Finding: risk mitigation history is overwritten today, not preserved

Checked directly against `opsdb.py`'s actual SQL, not assumed by analogy
to `task_status_history`:

```python
# opsdb.py:536-545 — cmd_risk_resolve(), full body
def cmd_risk_resolve(args: argparse.Namespace) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE risks SET status = ?, mitigation = COALESCE(?, mitigation), "
            "resolved_at = CASE WHEN ? = 'resolved' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "ELSE resolved_at END WHERE id = ?",
            (args.status, args.mitigation, args.status, args.risk_id),
        )
```

**`risk-resolve` is a destructive `UPDATE`, not an append.** When
`--mitigation` is supplied, the new string *replaces* `risks.mitigation`
outright — `COALESCE(?, mitigation)` only protects against overwriting
with `NULL` when `--mitigation` is omitted; it does nothing to preserve
the *previous* text when a new value is passed. There is no
`risk_history` table (unlike `task_status_history` for `tasks`), so once
overwritten, the prior mitigation text is gone from the live database
entirely.

**This is not a hypothetical — it has already happened, repeatedly, to
the exact risk this milestone exists to surface.** `risks.id=3`'s
`mitigation` column has been overwritten at least three times on record,
each time discarding the prior text:

1. Phase 3A (DEC-007, `ops/DECISIONS.md`): "`risks.id=3` remains `open`,
   `mitigation` text updated to reflect the two-part consequence
   increase."
2. DEC-008 (pause TASK-017): "its `mitigation` text was updated to record
   the pause and point to the preserved findings, not to claim
   resolution."
3. The current live row (queried directly, 2026-09-01, 2,820 characters):
   the CTO's TASK-017 hook-invocation investigation finding — a
   materially different disclosure than either of the above two.

None of steps 1 or 2's actual mitigation *text* survives in the `risks`
table today — only the current (step 3) snapshot does. The only place
those earlier disclosures still exist verbatim is `ops/DECISIONS.md`'s
prose (itself hand-written summaries, not a verbatim copy of the column
value at the time) and `ops/reviews/*.md` review documents. **This is
exactly the audit-trail gap this project has otherwise been careful to
avoid everywhere else** — `task_status_history` for tasks,
`review_results`/`qa_results` append-only per attempt, `decisions` as an
append-only log, `hook_denials` logging every denial. `risks` is the one
mutable-with-no-history table left in the schema for a field this project
visibly, repeatedly relies on to carry serious, evolving disclosure.

A second, smaller, related gap found while reading the same function:
`risk-resolve` has **no `--by`/`changed_by_agent` argument at all** —
unlike `task-status-change`, a risk update captures no record of *who*
changed it, only the CLI invocation log (outside the database) would
show that.

### 1.1 Recommendation: name it, sketch the fix, do not build it this milestone

**Recommendation: this milestone (a read-only page) explicitly flags the
gap on the page itself (Part 3.5) and in this document, rather than
silently building a history table as an unannounced schema change bolted
onto a "just add a page" milestone.** Concretely, adding real history
requires two things beyond a new table — a new required
`--by`/`changed_by_agent` CLI argument on `risk-resolve` (a CLI
contract/behavior change) and a decision about whether the write itself
becomes two statements (an `INSERT` into history plus the existing
`UPDATE`) inside one transaction. That is write-path and CLI-surface work
of the same shape and proportion as Milestone B's `agent_runs.cost_usd`
column + `end_run()` signature change — real, valuable, but a distinct
unit of work from "give the Founder a page to see risks on," and doing it
silently inside this milestone would repeat exactly the kind of
scope-creep DEC-009's own gate gave every prior milestone a Design review
to catch.

**The schema this milestone recommends, ready for a future pass** (not
created here):

```sql
-- Recommended, NOT part of this milestone's implementation — sketched so
-- a future scoped pass (its own small CTO architecture note, reusing
-- this section, is sufficient — no new design review needed for a table
-- this narrow) can move directly to Red Team without re-deriving the
-- shape. Mirrors task_status_history's proven shape exactly (schema.sql
-- :71-79), extended with the one extra payload risks actually carries
-- that tasks' status alone doesn't: the mitigation text itself.
CREATE TABLE IF NOT EXISTS risk_history (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  risk_id              INTEGER NOT NULL REFERENCES risks(id),
  from_status          TEXT,
  to_status             TEXT NOT NULL,
  mitigation_snapshot  TEXT,     -- risks.mitigation's value AFTER this change
  changed_by_agent     TEXT NOT NULL,
  changed_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  note                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_risk_history_risk ON risk_history(risk_id);
```

`cmd_risk_resolve()` would `INSERT` one row here (capturing the
pre-change `mitigation` as `from_status`'s counterpart context, and the
new value as `mitigation_snapshot`) inside the same transaction as its
existing `UPDATE`, exactly mirroring how `task_status_history` rows are
written alongside every `tasks.status` change — same append-only
discipline, no new mechanism invented.

**Until that ships, the register page (Part 3.5) shows a small, honest
disclosure inline wherever a risk's mitigation text is rendered**: *"Only
the current mitigation text is stored — prior versions are not preserved
in the database. See `ops/DECISIONS.md` and linked decisions/reviews
below for this risk's documented history."* This is not a workaround
that hides the gap; it is the gap, stated plainly, exactly where a
Founder reading `risks.id=3`'s current text would otherwise reasonably
assume they're seeing the whole story.

---

## Part 2 — Shared computed function (`ops/db/derived_state.py`)

Additive; no existing function changed. `open_risks_digest()`
(`derived_state.py:769-784`, Phase 3A's Chief-of-Staff state-digest
helper) is **not** reused for the register page — it is capped at
`limit=10`, omits `scope_type`/`scope_id`/`owner_agent`/`raised_by_agent`/
`created_at`/`resolved_at`, and exists specifically to feed a bounded
conversational digest, not a complete register. Widening it in place
would risk silently changing what the Chief of Staff sees in every
Founder conversation — a second, purpose-built function is the smaller,
safer change, matching Milestone B's own reasoning for adding
`company_cost_digest()` alongside (not instead of) existing cost helpers.

```python
def risk_register_rows(conn: sqlite3.Connection) -> list[dict]:
    """Every row in `risks`, newest first within each status group,
    highest severity first within each group — the single shared
    computation /risks.html and (optionally) any other consumer read
    from. For scope_type='task' rows, resolves the real task title via a
    LEFT JOIN so the register can render 'TASK-017 — <title>' without a
    second query per row; for scope_type='project', resolves the real
    project name the same way (no per-project detail page exists in the
    product yet — see Part 4.3 — so this is display-only, not a link
    target). Returns one plain dict per risk:
    {"id", "scope_type", "scope_id", "scope_task_title",
     "scope_project_name", "raised_by_agent", "title", "description",
     "severity", "status", "mitigation", "owner_agent", "created_at",
     "resolved_at"}. No fabricated field — every key is a real column or
     a real LEFT JOIN result, NULL rendered honestly by the caller."""
    rows = conn.execute(
        """
        SELECT r.id, r.scope_type, r.scope_id, r.raised_by_agent, r.title,
               r.description, r.severity, r.status, r.mitigation,
               r.owner_agent, r.created_at, r.resolved_at,
               t.title AS scope_task_title,
               p.name  AS scope_project_name
        FROM risks r
        LEFT JOIN tasks t ON r.scope_type = 'task' AND t.id = r.scope_id
        LEFT JOIN projects p ON r.scope_type = 'project' AND p.id = r.scope_id
        ORDER BY
          CASE r.status WHEN 'open' THEN 0 WHEN 'mitigated' THEN 1 ELSE 2 END,
          CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
          COALESCE(r.resolved_at, r.created_at) DESC,
          r.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def related_decisions_for_risk(conn: sqlite3.Connection, risk_id: int) -> list[dict]:
    """Decisions whose recorded text literally names this risk, using the
    literal-string convention this project has already, consistently
    used in every relevant DECISIONS.md entry to date (confirmed by
    direct grep: 'risks.id=3', 'risks.id=2' etc. appear verbatim in
    DEC-004, DEC-006, DEC-007, DEC-008, DEC-009, DEC-010's `decisions`
    table rows — this is real, already-established authorial practice,
    not a convention invented for this milestone). A prefilter LIKE
    query keeps the candidate set small and cheap (this table has
    dozens of rows, not thousands); the exact match is then done in
    Python with a word-boundary regex so 'risks.id=3' does not
    false-match 'risks.id=30' or 'risks.id=3' immediately followed by
    more digits, which a bare SQL LIKE '%risks.id=3%' would risk once
    more than 9 risks exist. Returns [] (never fabricates a relation)
    when no decision names this risk_id explicitly."""
    import re
    pattern = re.compile(rf"risks\.id={risk_id}\b")
    candidates = conn.execute(
        "SELECT id, title, date, problem, decision, reason, tradeoffs "
        "FROM decisions WHERE problem LIKE '%risks.id=%' OR decision LIKE '%risks.id=%' "
        "OR reason LIKE '%risks.id=%' OR tradeoffs LIKE '%risks.id=%' ORDER BY id"
    ).fetchall()
    out = []
    for d in candidates:
        blob = " ".join(filter(None, (d["problem"], d["decision"], d["reason"], d["tradeoffs"])))
        if pattern.search(blob):
            out.append({"id": d["id"], "title": d["title"], "date": d["date"]})
    return out
```

Both functions take an open `sqlite3.Connection` (row_factory =
`sqlite3.Row`), matching every existing function in this module. Neither
opens its own connection — same discipline as `task_progress_row()` /
`company_cost_digest()`.

---

## Part 3 — The page: `/risks.html`

### 3.1 Route and file

`GET /risks.html` — top-level, same shape as `/decisions.html`,
`/active-work.html`. New file `ops/control-center/generate_risks.py`,
`build_html(token=None)`. New `server.py` GET route, same dispatch
pattern as every other top-level page (`self._send_html(200,
generate_risks.build_html(token=SESSION_TOKEN).encode("utf-8"))`).

**Naming**: `/risks.html`, not `/risk-register.html` — matches this
project's existing one-word-per-concern convention
(`decisions.html`, `agents.html`, `costs.html`), and is the exact noun
`ROADMAP.md`'s own DEC-009 text already uses ("Risks register").

### 3.2 Filterable/sortable without client-side JS: grouped sections, not query-string filtering

Two structural options were considered:

- **Query-string GET filtering** (`/risks.html?status=open`), server-
  rendering a different subset per request — rejected: no existing
  top-level GET route in this codebase reads `self.path`'s query string
  at all (`server.py` only ever splits it off and discards it,
  `path = self.path.split("?", 1)[0]`, confirmed at `server.py:402/532`);
  introducing the first such route for this milestone would be a new
  server-side mechanism, not a reuse of an established one, for a
  benefit (a slightly smaller single-request payload) this project's own
  actual row count (4 risks today, plausibly dozens at real scale — not
  thousands) does not need.
- **One page, all risks, grouped into three sections with a jump-nav row**
  (adopted) — reuses the exact anchor-pill pattern `generate_task.py`
  already established (`#findings`, `#risks`, etc.) and requires no new
  mechanism at all: `risk_register_rows()`'s own `ORDER BY` (Part 2)
  already produces open-first, severity-desc-within-group ordering;
  the page renders three `<div id="open">` / `id="mitigated">` /
  `id="resolved">` sections in that order, each internally sorted by
  severity, with three small pill links at the top of the page
  (`Open (N)`, `Mitigated (N)`, `Resolved (N)`) jumping to each section —
  "filterable" in the sense of "the Founder can jump straight to what
  matters," "sortable" in the sense of "severity-first ordering is
  already the default, not a per-click toggle." This is the same
  no-JS, anchor-based interaction model every other multi-section page
  in this Control Center already uses.

### 3.3 One row = one risk card

Following `generate_task.py`'s `render_risks()` visual pattern exactly
(same `.card`, same severity color mapping) rather than inventing a new
card shape:

```python
_SEV_COLOR = {"high": "var(--red)", "medium": "var(--accent)", "low": "var(--text2)"}
_STATUS_COLOR = {"open": "var(--red)", "mitigated": "var(--accent)", "resolved": "var(--green)"}
```

Rendered fields, every one required by the milestone brief:

| Field | Source |
|---|---|
| Title | `risks.title` |
| Description | `risks.description`, or "—" if NULL |
| Severity | `risks.severity`, colored pill |
| Status | `risks.status`, colored pill |
| Owner | `display_name(risks.owner_agent)`, or "unassigned" if NULL |
| Raised by | `display_name(risks.raised_by_agent)` |
| Scope | Part 4 |
| Mitigation | `risks.mitigation`, Part 3.5's rendering treatment, or "No mitigation recorded yet." if NULL |
| Resolved at | `risks.resolved_at`, or omitted entirely (not "—") when `status != 'resolved'` — an unresolved risk showing a blank "Resolved at" field reads as a missing fact; omitting the row entirely for the two-thirds of risks it doesn't apply to is more honest than a placeholder |
| Related decisions | Part 4.2, when any exist |

Each card carries `id="risk-{id}"` (Part 0's cross-link target from
Agent Detail) and an `id="risk-N — title"` mono label matching the
`"Risk #{id} — {title}"` label `generate_task.py` already uses for the
identical data, for visual consistency between the two places a risk can
be seen.

### 3.4 Header and counts

Top of page: `<h1>Risks</h1>`, a one-line summary
(`"{open_n} open ({high_n} high-severity) · {mitigated_n} mitigated ·
{resolved_n} resolved"`), and the three jump-nav pills from §3.2. This
mirrors `generate_decisions.py`'s existing `"{count} record(s)"` header
convention.

### 3.5 Mitigation text: preformatted plain text, not a rich-text renderer

**Concrete recommendation, matching the milestone brief's own steer**: no
new rendering engine, no markdown parser, no paragraph-splitting logic.
`risks.mitigation` is plain `TEXT` today (confirmed: `risks.id=3`'s
current 2,820-character value contains zero literal newlines — it is one
long paragraph, not multiple `\n\n`-separated ones, despite reading as
"multi-paragraph" in substance). The correct, smallest treatment:

```html
<div style="font-size:11.5px; color:var(--text2); line-height:1.6; white-space:pre-wrap; max-width:100%;">{e(r["mitigation"])}</div>
```

`white-space:pre-wrap` is the one new CSS declaration this milestone
introduces (no existing page currently needs it, since no other long-text
field in this product has ever contained embedded newlines) — it
preserves paragraph breaks *if and when* a future `risk-resolve
--mitigation` call includes them (e.g., a future agent writing `\n\n`
between paragraphs, which nothing prevents today), while degrading
gracefully to normal word-wrap for today's actual single-paragraph value.
`e()` (the existing, mandatory HTML-escape helper) is still called first,
exactly as every other rendered text field in this product requires —
`pre-wrap` only changes whitespace handling, not escaping; a malicious or
malformed mitigation string is exactly as safe here as anywhere else.
This is the "render mitigation text as preformatted/wrapped plain text
with paragraph breaks preserved" the brief asks for, done with one CSS
property and zero new logic — not a rich-text renderer, not a Markdown
engine, not a truncation/expand-on-click affordance (the brief's own
instruction not to over-engineer for one risk's current situation).

Directly below the mitigation text, **only when `related_decisions_for_risk()`
returns rows or the mitigation text is non-empty**, the Part 1.1 disclosure
line renders once per card: *"Only the current mitigation text is stored
— prior versions are not preserved in the database."* This is not shown
on every card if it would be misleading noise for a risk whose mitigation
has genuinely never been updated (i.e., a risk with `created_at ==` its
only known state) — but Part 1's finding is real project-wide (the table
itself never preserves history, whether or not a given risk has been
edited yet), so the simpler, honest choice is to show it on **every**
card with non-empty mitigation text, not attempt to detect per-risk
whether an overwrite has actually happened (the database cannot answer
that question — that's the whole finding). **Recommendation: show it
unconditionally wherever mitigation text is rendered**, worded once,
consistently.

---

## Part 4 — Linking risks to their real context

### 4.1 Task-scoped risks → real Task Detail pages (Milestone A)

`risk_register_rows()`'s `scope_task_title` LEFT JOIN (Part 2) makes this
a plain link, no extra query: `scope_type='task'` renders `Scope:
<a href="tasks/{scope_id}.html">TASK-{scope_id:03d} — {scope_task_title}</a>`
(top-level page, so no `../` prefix — matches Milestone A §6.2's
established top-level-to-`/tasks/<id>.html` link shape exactly, e.g.
`generate_releases.py`'s existing `tasks/{id}.html` links). Real
example against live data: `risks.id=1` (`scope_type='task',
scope_id=1`) renders `Scope: TASK-001 — Verify Agent Pipeline` as a real
link to `tasks/1.html` (task id=1 confirmed to exist, `status='DONE'`,
queried directly while writing this document).

### 4.2 Company-scoped risks → related decisions, sourced from the `decisions` table itself

For `scope_type='company'` risks (all of `risks.id=2/3/4` today),
`related_decisions_for_risk()` (Part 2) renders a small "Related
decisions" list under the mitigation text: `#{d["id"]} — {d["title"]}
({d["date"]})`, linking to `decisions.html#decision-{id}`. This requires
one small, additive change to `generate_decisions.py`: its existing card
`<div>` (currently no `id` attribute at all, confirmed by rereading the
file) gains `id="decision-{d['id']}"`, the identical anchor pattern
`generate_task.py` already uses for `#findings`/`#risks` — a one-line
addition to an existing element, not a new page or new data source.

**Why the `decisions` table and its already-established
`"risks.id=N"`-in-text convention, not a new schema column or a
filesystem scan of `ops/reviews/*.md`**, concretely:

- A new `risks.related_decision_ids` column (JSON array) was considered
  and rejected: it would require every future `risk-add`/`risk-resolve`
  call to *remember* to also maintain a second, redundant list by hand,
  with no enforcement that it stays accurate — exactly the kind of
  manually-synchronized, driftable data this project's schema has
  consistently avoided (real joins and computed queries over existing
  columns, not a second hand-maintained cross-reference, is the pattern
  every prior derived-state function in this file already follows).
- A filesystem scan of `ops/reviews/*.md` for the same literal string was
  considered and rejected for this milestone: no GET route in this
  product reads any file other than `operations.sqlite3` today; adding
  the first such route is new capability/attack-surface (path handling,
  performance, staleness relative to the DB) disproportionate to what
  this milestone needs, and — critically — **those filenames are already
  visible to the Founder without a new mechanism**: `risks.id=3`'s own
  `mitigation` text already names
  `ops/reviews/cto-risk3-hook-invocation-investigation.md` inline, in
  plain prose, exactly the way `ops/DECISIONS.md` does. Part 3.5's
  preformatted rendering of `mitigation`/`description` already surfaces
  every such reference verbatim as readable (if non-clickable, since
  this Control Center serves no path under `ops/reviews/`) text — no
  additional design is needed to make those references *visible*, only
  to make the *decisions* clickable, which the `decisions` table query
  above does with real, already-structured data.
- The `decisions` table's own text columns already, consistently, use
  the literal `"risks.id=N"` string whenever a decision concerns a risk
  (confirmed: DEC-004, DEC-006, DEC-007, DEC-008, DEC-009, DEC-010 all
  do this for `risks.id=2`/`risks.id=3`) — this is real, structured,
  query-time-fresh data (every future decision that follows the same
  authorial convention is picked up automatically, no code change
  needed), not a fabricated relationship.

**Disclosed limitation of this approach**: it depends on a *prose
convention*, not a schema-enforced relationship — a future decision that
concerns `risks.id=3` but doesn't literally write `"risks.id=3"` in its
`problem`/`decision`/`reason`/`tradeoffs` text would not be picked up.
This is named here explicitly rather than presented as complete; the
convention has held with 100% consistency across six decisions to date,
which is why it's the recommended approach for this milestone rather
than a schema change, but it is a soft, not hard, guarantee.

### 4.3 Project-scoped risks — plain text, no link (honest, not a gap)

No `risks` rows are currently `scope_type='project'` (all 4 live rows are
`task` or `company`), but the schema allows it. `risk_register_rows()`'s
`scope_project_name` LEFT JOIN resolves the real project name for
display (`Scope: Project — {scope_project_name}`), rendered as **plain
text, not a link** — this product has no per-project detail page today
(confirmed: "this project has one implicit single project" per Milestone
A's own architecture doc; a dedicated project page is explicitly
Milestone D's job). Linking to a page that doesn't exist would repeat the
exact "broken pipeline card" mistake Milestone A's own motivating problem
already named and fixed — this design does not reintroduce it for a
scope type that happens to have zero live rows today.

---

## Part 5 — Updating the one place this milestone's absence is currently disclosed

`generate_task.py`'s `render_risks()` empty-state copy (line 444-447)
currently reads: *"...stays visible only via Agent Detail pages until a
future company-wide Risks register (Milestone C) ships."* Updated to:
*"...stays visible via the company-wide Risks register
(<a href="../risks.html">risks.html</a>), not here — this section is
scoped to risks raised specifically against this task."* (`../` prefix:
Task Detail is a depth-1 page, matching every other outbound link from
`generate_task.py` to a top-level page — same convention Part 4.1 uses
in reverse.)

`generate_agents.py`'s `risks_owned`/`risks_raised` sections (Part 0)
each gain one line: `<a href="../risks.html#risk-{id}" class="accentlink">→
full Risks register</a>` appended once per section (not once per row) —
`/agents/<name>.html` is also depth-1, same `../` convention.

---

## Part 6 — Navigation and gates

### 6.1 `layout.py`

```python
NAV_LINKS = [
    ("overview.html", "Overview"),
    ("active-work.html", "Active Work"),
    ("pipeline.html", "Pipeline"),
    ("agents.html", "Agents"),
    ("decisions.html", "Decisions"),
    ("risks.html", "Risks"),        # NEW — Milestone C (TASK-021)
    ("meetings.html", "Meetings"),
    ("inbox.html", "Inbox"),
    ("reviews.html", "Reviews"),
    ("releases.html", "Releases"),
    ("automation.html", "Automation"),
    ("costs.html", "Costs"),
]
```

Placed immediately after "Decisions": both are company-governance,
read-only registers of durable record-keeping (one of choices made, one
of risks tracked) — a natural adjacent pair, and `risks.id=3` itself is
already cross-referenced from six `Decisions` entries (Part 4.2),
reinforcing the adjacency. `/risks.html` is a nav-bar item (unlike
`/tasks/<id>.html`/`/agents/<name>.html`) because it is a genuine
top-level list page, matching `/decisions.html`'s and `/active-work.html`'s
precedent exactly, not a dynamic per-entity detail page.

### 6.2 Gates (per DEC-009)

CTO architecture (this document) → Design review (a real, if small,
Founder-facing UI surface — applies, same as both prior milestones) →
Red Team → Development → Code Review → QA → a focused Security review
scoped to newly introduced risk only → CTO final conformance.

### 6.3 What the Design review gate should specifically weigh in on

1. The three-section (Open/Mitigated/Resolved) layout vs. a single flat
   list with inline status pills — confirm or override §3.2.
2. Whether the "only current mitigation text is stored" disclosure
   (§3.5) reads as informative or alarmist at this length/placement,
   matching the same "informative not alarmist" bar Milestone A's
   staleness badge and Milestone B's "not available" disclosures were
   already held to.
3. Card density for a risk with `risks.id=3`'s actual 2,820-character
   mitigation text — confirm the plain `pre-wrap` treatment (no
   truncate/expand) reads acceptably at that length, or recommend a
   `<details>`-style native HTML disclosure (still zero JS) if it
   doesn't.
4. Nav placement (§6.1) — confirm "Risks" belongs next to "Decisions,"
   or propose a different position.
5. Consistency with the existing dark visual system (`layout.py` CSS
   tokens) — a check, not an open design brief.

### 6.4 The focused Security review

Same framing as both prior milestones — this is a **read-only** page,
reusing the existing Founder session/CSRF gate exactly as every other GET
route does, zero new write routes. Concretely, Security should verify:

- No new HTTP write route anywhere in this design (true by construction
  — `/risks.html` is GET-only; `risk-add`/`risk-resolve` remain CLI-only,
  unchanged).
- `dbutil.connect()` read-only (`mode=ro`) is used throughout
  `generate_risks.py`, same discipline as every other generator.
- No data rendered on `/risks.html` is more sensitive than what's already
  Founder-visible today via `generate_agents.py`'s existing
  `risks_owned`/`risks_raised` sections or `ops/DECISIONS.md` itself —
  this milestone changes *reachability*, not *what data exists in the
  product* (the same framing Milestone A's Security review already
  applied to Task Detail).
- `related_decisions_for_risk()`'s regex (`re.compile(rf"risks\.id={risk_id}\b")`)
  is confirmed to only ever receive a real integer `risk_id` sourced from
  `risks.id` (never raw user/request input) — no injection surface, since
  the value being interpolated into the regex pattern is always an
  `int`, not a string from an HTTP request.

---

## Part 7 — Files this milestone touches (complete list)

**New:**
- `ops/control-center/generate_risks.py` — `/risks.html`.

**Modified:**
- `ops/db/derived_state.py` — `risk_register_rows()`,
  `related_decisions_for_risk()`, both additive.
- `ops/control-center/layout.py` — one new `NAV_LINKS` entry
  (`risks.html`, after `decisions.html`).
- `ops/control-center/server.py` — one new top-level GET route
  (`/risks.html`), same dispatch pattern as every other top-level page.
- `ops/control-center/generate_decisions.py` — one attribute added to an
  existing element (`id="decision-{id}"` on each decision card) — no
  structural change, no new query.
- `ops/control-center/generate_task.py` — `render_risks()`'s empty-state
  copy updated (Part 5); no structural change.
- `ops/control-center/generate_agents.py` — one link line appended to
  each of `risks_owned`'s and `risks_raised`'s rendered sections (Part 5);
  the existing queries and list rendering are otherwise unchanged.

**Explicitly not touched:** `ops/db/opsdb.py` (`risk-add`/`risk-resolve`
stay exactly as they are — Part 1's `risk_history` recommendation is
sketched, not implemented, this milestone), `ops/db/schema.sql` (no
schema change — `risk_history` is future work, not this milestone's),
any write route, any auth mechanism, TASK-017, `risks.id=3`'s own
disposition, Milestone D.

---

## Part 8 — What this design explicitly does not add

No new write route, no Founder-facing risk-create/edit UI (risks stay
CLI-only via `opsdb.py risk-add`/`risk-resolve`, per the milestone's own
constraint). No `risk_history` table (recommended, schema sketched in
Part 1.1, explicitly deferred as its own scoped follow-up — a CLI
contract change, not a page). No `risks.related_decision_ids` column
(Part 4.2 — a real query over existing, already-consistent text data is
preferred over a second hand-maintained list). No filesystem scan of
`ops/reviews/*.md` (Part 4.2 — those references are already visible as
plain text inside `mitigation`/`description`, surfaced by Part 3.5's
rendering with zero new mechanism). No project detail page (Part 4.3 —
Milestone D's job; project-scoped risks render honestly as plain text,
not a link to a page that doesn't exist). No client-side JS anywhere on
`/risks.html` (Part 3.2's anchor-based grouping is the entire
interaction model). No change to the Founder session/CSRF gate, no
change to any of Milestones A or B's shipped pages beyond the two small,
additive cross-links named in Part 5.
