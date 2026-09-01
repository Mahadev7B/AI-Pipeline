# CTO — Milestone C Post-Implementation Conformance (TASK-021)

Date: 2026-09-01
Gate: final, per DEC-009 (CTO architecture -> Design -> Red Team ->
Development -> Code Review -> QA -> focused Security -> **CTO conformance**,
this document). Reviewing the shipped state against
`ops/reviews/cto-milestone-c-architecture.md`, folding in Design's three
approved refinements (`ops/reviews/design-review-milestone-c.md`) and Red
Team's regex-loosening suggestion (commit `af3873f`).

## Verdict: CONFORMS. Milestone C is ready to be marked DONE.

No drift found. This is architectural conformance only — correctness,
security, and QA were already covered by prior gates and are not
re-litigated here.

---

## 1. Matches the architecture, refinements included

Read `ops/control-center/generate_risks.py`, `ops/db/derived_state.py`'s
`risk_register_rows()`/`related_decisions_for_risk()`, the `/risks.html`
route in `server.py`, the `NAV_LINKS` entry in `layout.py`, and the
cross-link diffs in `generate_decisions.py`/`generate_task.py`/
`generate_agents.py`. Confirmed directly against source (not the review
docs' claims):

- Route, file, and self-connecting `build_html(token=None)` shape match
  §3.1 exactly; `server.py`'s dispatch for `/risks.html` sits after the
  same unconditional `_authenticated_session()` check every other route
  goes through (`server.py:420` gates `do_GET` before the `/risks.html`
  branch at line 474) — no route-specific auth carve-out.
- `risk_register_rows()` and `related_decisions_for_risk()` match Part 2's
  design (open/mitigated/resolved + severity ordering, task/project
  LEFT JOINs, word-boundary regex over a prefiltered decisions scan) —
  additive, no existing function touched, both take an open connection,
  neither opens its own.
- Three-section status-first layout, anchor-pill jump nav, no client-side
  JS, `id="risk-{id}"` anchors, `Risk #{id} — {title}` label convention,
  severity/status color mapping copied from `generate_task.py` — all
  match §3.2/§3.3/§3.4 verbatim.
- Task-scoped risks link to real `tasks/{id}.html`; company-scoped risks
  render a plain pill; project-scoped risks render plain text with no
  link (§4.1/§4.3, no per-project page invented). Related decisions
  render as a compact, wrapped, title-truncated chip row linking to
  `decisions.html#decision-{id}` — Design's refinement 4, correctly
  implemented, and `generate_decisions.py`'s diff is exactly the
  one-line additive `id="decision-{id}"` §4.2 specified, nothing else in
  that file changed.
- Design's three refinements all landed: (1) the "Needs attention" strip
  is present, correctly built from open+high/medium severity rows, and
  indexes into the sections rather than replacing them; (2) the
  mitigation-history disclosure moved to page level, rendered exactly
  once (confirmed by grep against the shipped static file, count = 1),
  not per-card; (3) the mitigation text block uses `max-width:760px`,
  not CTO's original literal `max-width:100%`.
- Red Team's non-blocking suggestion landed: the regex is
  `re.compile(rf"risks\.id\s*=\s*{risk_id}\b")`, the LIKE prefilter
  widened from `'%risks.id=%'` to `'%risks.id%'` to not silently exclude
  the whitespace variant from the candidate set — a correct, coupled
  change (loosening only the regex while leaving the SQL prefilter
  narrow would have been a latent bug; the developer caught the
  dependency).
- Part 5's two cross-link updates (`generate_task.py`'s empty-state copy,
  `generate_agents.py`'s one link per `risks_owned`/`risks_raised`
  section, not per row) are both present and match the specified `../`
  depth-1 prefix.
- Nav placement matches §6.1 exactly, "Risks" immediately after
  "Decisions."

## 2. Mitigation-history disclosure: renders correctly, undiluted

Confirmed against the committed static `ops/control-center/risks.html`:
the exact wording from CTO's Part 1.1 (carried through Design's
placement change) appears once, in a page-level panel below the header,
not per-card. It reads as a plain factual statement about the table, not
buried in a card's visual noise and not watered down in wording. This is
the correct final form of a finding this document's own architecture
pass first surfaced, and it landed the way Design specified.

## 3. Static-snapshot disclosure question — my own view, not just Security's

Security's non-blocking note is accurate but understates how uniform the
precedent already is. Checked directly: `ops/control-center/decisions.html`
(already git-committed since Milestones A/B, unrelated to this milestone)
contains the literal string `risks.id=3` **nine times** today, because six
real `decisions` rows already narrate `risks.id=3`'s history in prose —
the exact same sensitive disclosure Security is flagging now appears in a
second static, git-committed file that predates this milestone entirely.
`active-work.html`, `costs.html`, and every other top-level page follow
the identical pattern: real live data, committed as a static snapshot,
on every regeneration. `/risks.html` committing `risks.id=3`'s current
mitigation text is not a new category of exposure this milestone
introduces — it is the same convention, applied to a table this project
had simply not yet built a dedicated page for. Treating `risks.html`
differently (e.g., gitignoring only this one static file) would be an
inconsistent, ad hoc carve-out for one page while eight other pages keep
committing real operational data including this exact string, and it
would not actually reduce exposure, since `decisions.html` already
carries the same text via the six decisions that quote it. Security's
"non-blocking" call was correct; my own view is it's not a hard call at
all given the existing precedent — no change needed here or elsewhere as
part of this milestone. If the project ever decides committed static
snapshots are the wrong pattern for sensitive content, that is a
project-wide static-generation architecture question spanning every page,
not a `/risks.html`-specific fix, and is out of this milestone's scope.

## 4. Test coverage — `ops/db/test_risk_register.py`

Well organized. Uses the established scratch-DB harness
(`testing_guard`, `OPSDB_PATH` override, never the live DB), the same
`check()`/`FAILURES` pattern this project's other `test_*.py` files use.
Two clearly labeled cases map directly onto the two things this
milestone's reviews actually cared about: (1) `related_decisions_for_risk()`'s
regex — exact match, Red Team's whitespace variant, the `risks.id=30`
non-match (word boundary), the no-match-returns-`[]` case, and an exact
count assertion so a false positive elsewhere in the candidate set
wouldn't silently pass; (2) `risk_register_rows()`'s status/severity
ordering and the task-title LEFT JOIN, including an explicit check that a
company-scoped risk's `scope_task_title` stays honestly `None` rather
than fabricated. Good coverage for what a future maintainer touching
either function would need to not regress silently.

## 5. Scope boundary — held end to end

- `git diff` across the full TASK-021 commit range (`93f9cb4..HEAD`)
  touches zero lines of `ops/db/opsdb.py` or `ops/db/schema.sql` —
  confirmed by an empty `git log`/`git diff --stat` for both paths over
  that range.
- No new write route: `/risks.html` is the only new server route, GET
  only; `server.py`'s diff adds exactly the one dispatch branch.
- File list matches Part 7 of the architecture doc exactly, plus the
  expected regenerated static snapshots (every `agents/*.html`,
  `tasks/*.html`, `decisions.html`, `overview.html` — all touched only
  because `render_risks()`'s cross-link additions and the new page
  regenerate on every build, not because any of their own generators
  gained new logic beyond the two named, additive changes).
- No Milestone D creep: no project detail page was added;
  project-scoped risks still render as plain text, matching §4.3.
- `risks.id=3` queried directly against the live `operations.sqlite3`
  post-ship: `status='open'`, `mitigation` still 2,820 characters,
  unchanged by this milestone. The page renders this row's current state
  honestly (it appears in the Open section and in the Needs-attention
  strip, as any open medium/high-severity risk would) without narrowing,
  resolving, or editorializing on TASK-017's still-open Founder decision.

---

## Summary

Milestone C shipped exactly what was architected, with Design's three
refinements and Red Team's one suggestion correctly folded in — not just
claimed in commit messages, verified directly against the shipped code
and the committed static output. The one notable finding from the
architecture phase (mitigation-history loss) is disclosed on the page
exactly as specified, once, undiluted. Security's static-snapshot note
is non-blocking and, on inspection, is already fully consistent with how
every other top-level page in this product has behaved since Milestone A
— including `decisions.html`, which already commits the same sensitive
string nine times over. No drift. **CONFORMS.**
