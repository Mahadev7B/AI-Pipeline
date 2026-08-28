# CTO Architecture Proposal — Phase 2, Milestone 1

## Objective

Ship the smallest real slice of the Control Center: a single **Overview**
page, matching the Founder-approved refined-dark Command Center mockup
(`ops/mockups/control-center-phase-0/Main.dc.html`, Style A), reading
genuine state from the Phase 1 operational database. Read-only — no
write/interactive actions in this milestone.

## Approach considered and rejected: a live local server

A small Python `http.server` + JSON API was the obvious-seeming choice —
it's what a "Control Center" conjures. Rejected for *this* milestone:
nothing in scope yet is interactive (no Ask-Agent, no Approve/Reject that
actually calls `opsdb.py`), so a running process buys nothing and adds a
port to manage, a process to keep alive, and a pattern that diverges from
the zero-process, generate-on-demand approach `ops/db/report.py` already
established and the Founder already trusts. A live server becomes
justified once a real interactive milestone needs one — not before.

## Chosen approach: a static HTML generator, same shape as report.py

`ops/control-center/generate_overview.py` — stdlib-only, no new
dependencies, run on demand, writes `ops/control-center/overview.html`.

**Shared derived-state logic, not a re-implementation.** Company Health,
agent status, and task progress are computed by report.py today. Rather
than hand-copy those formulas into a second script — which is exactly
the kind of drift the Founder's "never recreate as mocked or hand-
written" rule exists to prevent — I'm extracting them into
`ops/db/derived_state.py`, imported by both `report.py` and
`generate_overview.py`. This is the one non-trivial change to Phase 1
code in this milestone. It changes no schema, no `opsdb.py` behavior,
and no `report.py` output — pure relocation of three pure functions.
Disclosed here explicitly rather than made silently; Red Team should
treat it as in scope to challenge, and QA must prove `report.py`'s
output is byte-identical before and after.

**Visual source of truth.** The generator reuses the CSS custom
properties (color tokens, font stack) verbatim from `Main.dc.html` —
the same system, not a reinterpretation of it from memory.

**Scope — exactly the Overview mockup's sections, nothing more:**
- Company Health (from `derived_state.company_health`)
- Active Now — agents with an open `agent_runs` row
- Pipeline snapshot — real tasks, real status, real progress % (or "not
  yet broken into steps" where that's the honest answer)
- Just Happened — recent `agent_activity`
- Founder Inbox — pending `approvals`

**Founder Inbox items render without live Approve/Reject actions.**
This is a read-only milestone; a clickable-looking button that doesn't
call `opsdb.py` would misrepresent what's actually wired. Inbox items
show the request and its current decision state as text — no button
that isn't real.

**Security consideration flagged for review:** every piece of database
text (task titles, activity summaries, approval requests, risk
descriptions) goes into HTML output and must be escaped
(`html.escape`), not trusted as safe. Flagging this now for Security to
verify, not deferring it.

## Alignment with the Phase 1 foundation

- Read-only connections only — no write path anywhere in this
  milestone's code.
- Never imports or calls anything from `opsdb.py`'s write functions.
- Does not touch `schema.sql`. Does not add a new table. `opsdb.py`
  remains the only writer of operational state.
- Uses `OPSDB_PATH`/the same DB-location convention already established
  — testing this generator must use a scratch database, same rule as
  everything else in `ops/db/README.md`.

## Recommendation

Proceed to Red Team review of this proposal before Development.
