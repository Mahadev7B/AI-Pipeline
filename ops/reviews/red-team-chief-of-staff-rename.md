# Red Team review — "Orchestrator" → "Chief of Staff" display rename

Reviewing `ops/reviews/cto-chief-of-staff-rename.md` before Development
acts on it, per the standard Architecture → Red Team → Development
workflow. No `Agent` dispatch tool needed for this review — performed
directly, and every material claim below was independently verified
against the live repository (file reads, greps, and one live Python
import test), not accepted on the CTO doc's word.

## Verdict: REJECT

The core design (one `display_name()` function in `ops/db/derived_state.py`,
applied at Founder-facing render sites, machine identity/subagent_type/
schema untouched) is sound and appropriately minimal — this is not an
overengineering or unnecessary-complexity problem. The reject is narrower:
the plan's own central claims — "every current use... verified against the
live codebase," "a full-repo sweep," "no new cross-directory sys.path
wiring needed beyond what each already has" — are demonstrably incomplete
or wrong in specific, checkable ways, and Development is instructed to work
strictly off section 4's file list. That list must be corrected before this
is safe to hand to Development, or Development will either hit a real
`ImportError` or ship a partially-renamed, inconsistent doc set.

## Findings

### 1. REQUIRED FIX — `generate_decisions.py` and `generate_inbox.py` cannot import `derived_state` as currently written

Verified live:

```
$ cd ops/control-center && python3 -c "
import sys; from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
from derived_state import company_health"
ImportError: No module named 'derived_state'
```

Only `generate_overview.py`, `generate_pipeline.py`, `generate_agents.py`,
and `generate_meetings.py` currently carry the second `sys.path.insert(0,
str(Path(__file__).resolve().parent.parent / "db"))` line needed to reach
`ops/db/derived_state.py`. `generate_decisions.py` and `generate_inbox.py`
do not (confirmed by reading their full import blocks) — they only insert
their own directory, for `dbutil`/`layout`.

The CTO doc's §1c/§2 claim — "both `report.py` and every Control Center
generator reach it through an import path that already exists today, with
no new cross-directory `sys.path` wiring needed beyond what each already
has" — is false for these two of the six listed generators. If Development
follows §4's "Wrap 'Requested by' label" / "Wrap 'Recommended by' label"
instructions literally without independently noticing this, the code will
crash on import. **Fix**: §4's rows for `generate_decisions.py` and
`generate_inbox.py` must explicitly say to add the same
`sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))`
line that `generate_pipeline.py`/`generate_overview.py` already use, before
`from derived_state import display_name`.

### 2. REQUIRED FIX — `ops/ARCHITECTURE.md` (root-level) is live current documentation naming "Orchestrator" as a role, and is entirely absent from the plan

Not mentioned anywhere in the CTO doc's §1h sweep or §4 file list. Verified
live:

```
ops/ARCHITECTURE.md:10: 2. **Orchestrator** — the only thing that decides what happens next and
ops/ARCHITECTURE.md:11:    assigns work. Talks to Task State and to Agent Execution; the UI never
ops/ARCHITECTURE.md:39: - The Orchestrator is the only writer of Task State. The UI reads Task
ops/ARCHITECTURE.md:41:   Orchestrator — it does not mutate rows directly.
```

This is core, current architecture documentation describing the role's
authority and coupling rules — the same category of file as
`ops/AGENT_ARCHITECTURE.md` (whose template line the CTO doc *did* catch
and include) and arguably more central. The doc explicitly claims "This
review verifies every current use of 'orchestrator'... confirmed by direct
grep of every file the brief named, plus a full-repo sweep" (§1h) — that
claim is not accurate; this file was missed. **Fix**: add
`ops/ARCHITECTURE.md` (both hits) to §4's file list with the same
"live/current documentation → update the word" treatment given to
`AGENT_ARCHITECTURE.md`, `DATA_MODEL.md`, `EXECUTIVE_MEETINGS.md`.

### 3. REQUIRED FIX — other agents' own current role docs name "Orchestrator" by name and are omitted

Verified live, all four are current (non-historical) role documentation,
same category the CTO doc itself uses to justify updating
`AGENT_ARCHITECTURE.md`/`DATA_MODEL.md`/`EXECUTIVE_MEETINGS.md`:

- `.claude/agents/ceo.md:31`: "Orchestrator — select who participates in an Executive Meeting."
- `ops/agents/ceo.md:52`: "With Orchestrator, select which agents participate..."
- `.claude/agents/project-manager.md:18`: "(that's Orchestrator's job)"
- `ops/agents/project-manager.md:24`: "Not permitted: changing a task's status or owner (that's Orchestrator's..."

If these are left unchanged while `.claude/agents/orchestrator.md` and
`ops/agents/orchestrator.md` are updated to introduce the entity as "Chief
of Staff" (per the plan's own §1f/§4), the result is a directly
inconsistent doc set: CEO's and Project Manager's own role docs — which a
Founder or engineer reads to understand cross-agent process — will keep
calling the same entity "Orchestrator" while its own doc calls itself
"Chief of Staff." This is exactly the "two different names, one entity,
visible in the same reading session" failure mode the plan is at pains to
avoid elsewhere (§2's reasoning for wrapping all four dashboard screens
instead of just Agents). **Fix**: add these four files to §4 (prose word
update only, same treatment as the other current-role-doc entries).

### 4. Lower-priority same-category omission — skill registry docs

`ops/skills/README.md:28`, `ops/skills/operations/loop.md:4,10`,
`ops/skills/operations/skill-creator.md:4,10`,
`ops/skills/product/prompt-master.md:4,10` all reference "Orchestrator
Agent" as a named user/owner of a skill — also live, current documentation,
also omitted. Lower material weight than findings 1–3 (internal skill
registry, not a Founder-facing role description), but still inside the
same "current role documentation" bucket the plan claims to have fully
swept. Recommend adding to §4 for completeness, but would not by itself
block a PASS.

### 5. Minor accuracy note — `ops/db/opsdb.py` audit claim is imprecise

§4's "Not in this list" note says `ops/db/opsdb.py` has "no `orchestrator`
literal found in it at all, confirmed by grep." A grep in fact returns six
hits (lines 529, 530, 563, 569, 612, 621) — all in comments/docstrings
describing `meeting_orchestrator.py`'s behavior, none of them a
Founder-rendered string or a code literal needing change, so the
*conclusion* (no code change needed here) is still correct. But the stated
justification is factually wrong, which matters because it's used
repeatedly elsewhere in this doc as evidence of grep-verified rigor. Not
blocking on its own; flagged because it's part of the same pattern as
findings 1–4 (claims of exhaustive verification that don't hold up when
re-checked).

### 6. `ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL`/`_LIKE` — CTO's "leave unchanged" call is reasonable; the underlying reasoning could be tighter, but this is not a blocking finding

Verified: `current_activity` is rendered raw at `generate_agents.py:80`,
`generate_agents.py:283`, `generate_overview.py:49`, and `report.py:163`,
so leaving `LABEL` unchanged does mean "Orchestrator: validating meeting
participant selection" would appear next to a "Chief of Staff" header for
the duration of that run. I confirmed it *is* technically feasible to
decouple the stored value from the displayed one without touching the
LIKE-matching risk the CTO doc is worried about — e.g. a display-time-only
prefix substitution (`"Orchestrator:" → "Chief of Staff:"`) applied at
exactly those four render sites, never touching
`ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL`/`_LIKE` or any stored row. So the
CTO doc's framing ("LABEL and LIKE must always change together") is true
of the *stored* constant but doesn't actually foreclose a display-only
fix — the doc slightly overstates the coupling.

That said, I do not think this rises to a blocking finding: the validation
step is a deterministic Python step (no LLM call) with a genuinely small
real window, and — more importantly than the CTO doc's own "few seconds"
argument — every one of these render sites is a *static, regenerate-on-demand*
HTML page (confirmed: every `generate_*.py` output carries a "Generated...
not hand-edited" banner), not a live-polling dashboard. The odds a Founder's
browser is showing a page regenerated during the exact sub-second window a
validation run is open are very low in practice, lower than the CTO doc's
own stated reasoning suggests. Leaving it as deliberately-not-changed
residual risk (as §5 already does) is an acceptable, correctly-disclosed
call. Recommend (not require) Development note in §5-style residual-risk
language that a display-only decoupling is possible as a future follow-up
if the Founder wants it, since it is cheap and low-risk if ever wanted.

### 7. `.claude/agents/orchestrator.md` / subagent_type handling — affirmed sound

Verified the frontmatter (`name: orchestrator`) is real and is what every
invocation's `subagent_type` uses. The plan's recommendation — keep
filename/`name:` unchanged, prose-only content change inside the file,
explicit "(internal identity: orchestrator)" annotation — is the correct,
minimal-risk choice and directly avoids the "two agents" failure mode the
Founder's directive forbids. No change requested here.

### 8. `display_name()` module placement — affirmed correct in principle

`ops/db/derived_state.py` is confirmed (by reading the file) to already be
the project's established shared-logic home for exactly this
both-`report.py`-and-Control-Center shape (`agent_status_rows`,
`scope_label`, `company_health`, etc.), and `report.py`'s own
`sys.path.insert` + import block already reaches it today. The module
choice itself is right; only the completeness of which generator files
also need their `sys.path` extended (finding 1) is wrong.

### 9. Overengineering / unnecessary complexity / security / hidden costs

- No overengineering found: one dict + one function with a documented
  fallback is the minimal correct shape; no new file, no new dependency,
  no schema/migration.
- No security/privacy concern: pure label substitution, still passed
  through the existing `e()`/escaping discipline at every render site
  (verified: every listed Control Center site already calls `e(...)`
  around the raw value today).
- Hidden costs are correctly scoped: 6 generator regenerations + 1 report
  regeneration is an accurate, non-inflated accounting of what changes;
  not an unreasonable burden for Development.

## What must change for re-review to PASS

1. Add explicit `sys.path.insert(...)` instruction to §4's rows for
   `generate_decisions.py` and `generate_inbox.py` (finding 1).
2. Add `ops/ARCHITECTURE.md` to §4 (finding 2).
3. Add `.claude/agents/ceo.md`, `ops/agents/ceo.md`,
   `.claude/agents/project-manager.md`, `ops/agents/project-manager.md` to
   §4 (finding 3).
4. Recommended: add the four `ops/skills/**` files to §4 for completeness
   (finding 4); not independently blocking.
5. Recommended: correct or soften the `ops/db/opsdb.py` "no literal found"
   claim (finding 5); not independently blocking.
6. No code change required for finding 6, but recommend the residual-risk
   section note that a display-only decoupling is possible later if wanted.

None of these require rethinking the design — they are completeness fixes
to the file list and two accuracy corrections to the verification
narrative. Once folded in, this plan is implementation-ready.
