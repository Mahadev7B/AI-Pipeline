# CTO Architecture Proposal — Phase 2, Milestone 2A

## Objective
Ship Pipeline, Agents (roster), Agent Detail (×14), Decisions, and
Meetings as static, read-only pages, with shared navigation, extending
Milestone 1's pattern rather than replacing it.

## Still no live server
Nothing in this milestone is interactive (explicitly excluded by scope
boundary: no Ask-Agent, no Approve/Reject, no meeting creation). The
static-generator pattern from Milestone 1 applies unchanged. A live
server remains unjustified until a real write/interactive feature needs
one — not this milestone.

## Multi-page navigation, no JavaScript
Six top-level pages (Overview, Pipeline, Agents, Decisions, Meetings)
plus 14 agent-detail pages need to link to each other. Rather than one
big page with client-side show/hide (which would need JS, and Milestone
1 set a zero-JS precedent), each screen is a real static file with real
`<a href>` navigation:

```
ops/control-center/
  overview.html, pipeline.html, agents.html, decisions.html, meetings.html
  agents/<agent-name>.html   (14 files, one per agent)
```

A shared nav bar (same five links, current page highlighted) appears on
every page, including the 14 detail pages (relative paths adjusted for
the one extra directory level). This is real navigation — no anchor
tricks, no `:target` CSS hacks, no JS — clicking a link loads a real
file. It works identically whether the founder opens these via
`file://` or a future server.

**Shared layout module** (avoiding six copies of the same nav/CSS/
escape-helper boilerplate — the same DRY reasoning as Milestone 1's
`derived_state.py`): `ops/control-center/layout.py` provides the CSS
token block, the nav shell, and the `e()` HTML-escape helper. Every
generator imports it; `generate_overview.py` is refactored onto it too
(disclosed here, not silent — no behavior change to its content, only
where the boilerplate lives).

## Pipeline: stage mapping is derived logic, not per-screen invention
`AGENT_STATUS.md` already defines which of the 16 `tasks.status` values
belong to which of the 6 major stages and which substate within it. That
mapping is a deterministic function of real data (`tasks.status`), not
invented structure — same category as `company_health()`. It goes in
`derived_state.py` as `STAGE_MAP` + `stage_and_substate(status)`, not
hand-coded inside `generate_pipeline.py`, so any future screen needing
"what stage is this task in" reuses it instead of re-deriving it.
`BLOCKED`/`FOUNDER_APPROVAL` render as a "Needs Attention" callout, not
a 7th column — matches `AGENT_STATUS.md`'s "interrupt state, not a
pipeline stage."

## Agents: the functional-grouping gap, resolved

Flagged by Design conformance: the Phase 0 mockup's five functional
groups (Executive/Product/Engineering/Operations/Oversight) have no
backing column in `agents`. Three options considered:

1. Add a real `agents.group_name` column now. Rejected for this
   milestone — a schema change needs its own Red Team review under
   `DATA_MODEL.md`'s existing discipline, and Milestone 2A's scope
   boundary doesn't call for one. Not "casual," but also not justified
   by what this milestone actually needs.
2. Hand-code a group lookup table in the generator (agent name →
   group), not stored in the database. Rejected — this is exactly
   "inventing structure the schema doesn't back," the thing the
   Founder's data rules exist to prevent, even though it's UI
   categorization rather than fake activity data.
3. **Group and sort by real state instead** — `Working` / `Blocked` /
   `Waiting` / `Available`, from `agent_runs`, exactly like Milestone
   1's Overview already does for "Active Now." Chosen. It's real,
   it's queryable, and it answers the Founder's actual question
   ("what is each agent doing") better than a static org-chart label
   would for a company that's still one founder and 14 agents.

Recorded as a disclosed deviation from the Phase 0 mockup's illustrative
grouping, not a silent one. A future milestone can revisit option 1 if
the Founder wants the org-chart view back, through its own schema-change
gate.

## Agent Detail: field-by-field data source

| Field | Source |
|---|---|
| Role, Model, Model status | `agents` |
| Skills, Frameworks, Tools, Permissions | `agents` (JSON columns, parsed) |
| Current status / activity / scope | latest open `agent_runs` row (`ended_at IS NULL`) |
| Recent activity | last 10 `agent_activity` rows for this agent |
| Blockers | open run's `blocked_reason`, plus open `risks` where `owner_agent` = this agent |
| Evaluation/review history | `qa_results`/`review_results` where this agent is `tested_by_agent`/`reviewed_by_agent` (reviews it performed); `decisions` where `recommending_agent` = this agent; `risks` where `raised_by_agent` = this agent |

All real columns already in the Phase 1 schema. No new table, no new
column.

## Decisions and Meetings: honest about what's really in the database

`decisions` currently has 2 rows; `DECISIONS.md` has 4 hand-written
`DEC-NNN` entries (a different, independent record — see
`ops/DATA_MODEL.md`'s clarification from the Milestone 1 conformance
review). The Decisions screen shows only the 2 real rows, with a visible
note pointing to `DECISIONS.md` for the fuller durable narrative — not
silently fewer entries than the Founder might expect unexplained.

`meetings` currently has **zero** rows. The Meetings screen is still
built and still gets its own nav entry (Founder's explicit instruction)
— it renders a real, honest empty state, not a placeholder meeting
invented to make the screen "look right." This is the clearest
application of "empty states are better than fake data" in this
milestone.

## Alignment with Phase 1

Read-only throughout (same `mode=ro` pattern as Milestone 1, verified
by an actual write-refusal test, not just asserted). No schema change.
No `opsdb.py` behavior change. `opsdb.py` remains the only writer.

## Recommendation
Proceed to Red Team review.
