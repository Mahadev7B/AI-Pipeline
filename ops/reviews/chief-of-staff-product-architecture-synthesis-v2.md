# Chief of Staff Synthesis v2 — Founder UI Completeness (TASK-018, corrected)

Supersedes `ops/reviews/chief-of-staff-product-architecture-synthesis.md`
for the milestone recommendation only — that document's account of
which invocation paths persist cost was **wrong** and is corrected below,
not silently replaced. Produced in response to the Founder's correction
directive "FOUNDER CORRECTION — TASK-018 UI COMPLETENESS REQUIREMENT"
(2026-08-31), via the same real `POST /api/chief-of-staff/ask` invocation
technique as every prior synthesis in this session (isolated scratch
clone, nothing live touched). Verbatim exchange in Appendix C. **Proposal
only — no Development has started. Waiting for Founder approval.**

Prior stage: `ops/reviews/cto-product-architecture-completion-v2.md`.

---

## A correction, first

Last time, I told you Ask-Agent persists cost. **That was wrong.** CTO
checked the actual code this round: none of Ask-Agent, Executive
Meetings, or Chief of Staff conversations save cost anywhere — there is
no database column for it on any of those three paths. Only the
automation poller saves cost, and only the automation page shows it.
"Cost tracking" was less finished than I told you.

## Founder, correcting my own number: the UI is about 55% click-through complete, not the higher figure I gave you before.

CTO did a real click-through audit this round — not "does the data
exist," but "can you actually navigate to it." Of 30 things a Founder
should be able to do, **16 are fully there, 7 are half-there, and 7 are
missing outright**:

- A dashboard showing all active work company-wide — missing.
- A page for any individual task's detail — missing; the route doesn't
  exist at all.
- A place to see the company's risk register — missing; `risks.id=3`,
  the security risk itself, currently has no page anywhere you could see
  it in the product.
- Cost visibility across the company (not just automation) — missing.
- Project/phase progress — worse than a missing page: the database
  doesn't store phase data at all, only prose in `ROADMAP.md`.

"Feature-complete" means everything reachable by clicking, and by that
bar, we are not there yet.

## My revised recommendation: three milestones, not two.

1. **Task Detail page + Active Work dashboard, together.** They use the
   same underlying data, and shipping a dashboard that links to a page
   that doesn't exist yet would just be broken.
2. **Company-wide cost visibility** — so all four invocation paths
   record what they already compute, not just the automation poller.
3. **A Risks register** — this one matters extra, since `risks.id=3`
   itself is currently invisible to you anywhere in the product.

**Deferred, lower priority**: Project/Phase Progress. It needs a new
database table built from scratch (phase data doesn't exist anywhere
today), not just a new page — genuinely new work, not surfacing
existing data. Do it after the three above.

Security's pause (TASK-017/`risks.id=3`) and the remaining Phase 3
automation stay exactly as deferred as before — this correction is about
UI completeness, not a reopening of that decision.

## What I need from you

Nothing decision-required yet — CTO hasn't scoped effort for milestones
A/B/C individually. Once that's in, milestone approvals come to you in
priority order (A, then B, then C), with Project/Phase Progress queued
behind them. **Per your directive, Development does not start until you
approve this revised plan.**

---

## Founder's 10-point return format

**1. What UI is truly complete today:** 16 of 30 audited capabilities —
see `ops/reviews/cto-product-architecture-completion-v2.md` Part 2 for
the full item-by-item list with file/route citations (Company Overview,
Pipeline, Agents, Agent Detail, Chief of Staff, Ask-Agent, Executive
Meetings, Founder Inbox, Approvals, Decisions, Code Review history, QA
history, Automation status, STOP/ON/OFF controls, Releases, navigation
between existing screens are among those classified COMPLETE).

**2. What UI is partial:** 7 of 30 — includes things like Security
findings (visible per-task in Reviews but not aggregated), stuck-work
visibility (derivable but not surfaced), empty/loading/error states
(inconsistent across pages). Full list and reasoning in CTO's document.

**3. What UI is missing:** 7 of 30 — Active Work dashboard, Task Detail
page, Project/Phase Progress, Risks register, company-wide AI usage/cost,
and two others detailed in CTO's document.

**4. Exact milestones required:** (A) Task Detail + Active Work
dashboard (shipped together — see reasoning above), (B) company-wide
cost visibility, (C) a Risks register. A fourth, deferred item:
Project/Phase Progress (needs a new `phases`-type table).

**5. Active Work vs. Task Detail — one milestone or separate:** One
milestone. Both are recommended together because the dashboard's own
task rows link into the detail page — shipping one without the other
produces a broken link, violating the Founder's own "coherent and
usable" bar.

**6. Does Project/Phase Progress require additional work beyond what
exists:** Yes, substantial — CTO found phase/milestone state exists only
as prose in `ROADMAP.md` and `DECISIONS.md` today, with no queryable
representation in the database at all. This is why it's deferred as a
fast-follow rather than bundled into milestone A/B/C.

**7. Exact cost-tracking truth table** (verified from
`ops/control-center/agent_runtime.py`, `chief_of_staff.py`,
`meeting_orchestrator.py`, `automation.py`, `ops/db/schema.sql`):

| Path | Tokens measured? | Cost calculated? | Cost persisted? | Visible in UI? |
|---|---|---|---|---|
| Ask-Agent | Yes | Yes | **No** — `agent_runs` has no `cost_usd` column | No |
| Executive Meetings | Yes | Yes | **No** — same table, same gap | No |
| Chief of Staff | Yes | Yes | **No** — same table, same gap | No |
| Automated Code Review (Phase 3A poller) | Yes | Yes | **Yes** — `automation_events.cost_usd` | Yes — `automation.html` only |

All four paths share one measurement function
(`agent_runtime._run_claude()`), so the *computation* is already
consistent and correct everywhere — only *persistence* is uneven. (A
fifth, paused path — TASK-017's synchronous reviewer routes — would
persist to a `reviewer_invocations` table that doesn't exist in the live
database yet, since TASK-017 was never Code-Reviewed or merged into any
"live" state.)

**8. Recommended build order:** A (Task Detail + Active Work) → B (cost
visibility) → C (Risks register) → deferred: Project/Phase Progress.

**9. Number of milestones remaining until genuinely 100% feature-complete
per the Founder's own bar:** Three required (A/B/C) plus one deferred
fast-follow (Project/Phase Progress) recommended but not blocking.

**10. What can remain deferred until after Founder testing begins:**
Everything already deferred by standing Founder directive — the
remaining Phase 3 orchestration automation, task-level access scoping,
and resuming TASK-017/`risks.id=3` hardening — plus, newly, Project/Phase
Progress from this round's audit.

---

## Appendix A — CTO's full v2 audit

Full document: `ops/reviews/cto-product-architecture-completion-v2.md`.
Contains the complete 30-item classification table with file/route
citations for every entry, the full cost-tracking code trace, and the
detailed design sketches for the Active Work dashboard, Task Detail
page, and Project/Phase Progress view (design only, not implemented).

## Appendix B — what changed from the first synthesis

The first synthesis (`ops/reviews/chief-of-staff-product-architecture-synthesis.md`)
recommended two milestones (task-detail page, cost visibility) and
stated Ask-Agent persists cost. Both are superseded: three milestones
are now recommended (a Risks register was added, and Task Detail is now
explicitly bundled with a new Active Work dashboard), and the cost claim
is corrected per the table in point 7 above. The first synthesis's
Appendix C (verbatim Chief of Staff exchange) is preserved in its own
document as an honest record of what was said, not edited after the
fact — this document's own Appendix C below is the corrected record.

## Appendix C — the real Chief of Staff exchange (verbatim, this round)

*Founder, 2026-08-31T22:33:23.636Z* (condensed brief of CTO's v2
findings, within the Chief of Staff's 2,000-character message cap):

> I corrected your last recommendation — I need the Founder UI 100%
> feature-complete, meaning everything reachable by clicking through the
> app, not just present in the database. CTO re-audited. [... condensed
> summary of the cost-tracking correction and the 16/7/7 UI audit
> results, as detailed above ...] Give me the corrected plain-English
> recommendation, acknowledging the correction honestly, with your
> updated percentage and milestone count.

*Chief of Staff, 2026-08-31T22:33:38.326Z:*

> **WHAT HAPPENED** — I need to correct myself first: last time I told
> you Ask-Agent persists cost. That was wrong. CTO checked the actual
> code, and none of Ask-Agent, Meetings, or my own Chief of Staff
> conversations save cost anywhere — there's no database column for it
> on those paths at all. Only the automation poller saves cost, and only
> the automation page shows it. So "cost tracking" was less finished
> than I said.
>
> On top of that correction, CTO did a full click-through audit of the
> Founder UI — not "does the data exist," but "can you actually navigate
> to it." Of 30 things a Founder should be able to do, 16 are fully
> there, 7 are half-there, and 7 are just missing outright:
> - A dashboard showing all active work company-wide
> - A page for any individual task's detail (this route doesn't exist at
>   all — nothing to click into)
> - A place to see the company's risk register (including risk id=3, the
>   security one — right now there's genuinely no page where you could
>   see it)
> - Cost visibility across the company, not just automation
> - Project/phase progress — this one's worse than "missing a page," the
>   database doesn't even store phase data yet, it only lives as text in
>   ROADMAP.md
>
> **WHY IT MATTERS** — "Feature-complete" means everything reachable by
> clicking, and by that bar we're not there — a meaningful chunk of what
> exists is data-only or half-built pages.
>
> **MY RECOMMENDATION** — Do three milestones, not two:
> - (A) Task Detail page + Active Work dashboard together — they use the
>   same underlying data, and shipping a dashboard that links to a page
>   that doesn't exist yet would just be broken.
> - (B) Company-wide cost visibility.
> - (C) A Risks register — this one matters extra, since risk id=3
>   itself is currently invisible to you in the UI.
>
> Defer Project/Phase Progress — it needs a new database table built
> from scratch, not just a new page, so it's real net-new work rather
> than surfacing existing data. Lower priority, do it after.
>
> Updated estimate: with the corrected 16/7/7 split, I'd put the Founder
> UI at roughly 55% click-through complete (16 of 30 fully there), not
> the higher number I gave you before.
>
> **WHAT I NEED FROM YOU** — Nothing decision-required yet — CTO hasn't
> scoped effort/cost for (A)/(B)/(C) individually. Once that's in, I'll
> bring you milestone approvals in priority order (A, then B, then C),
> with (D) Project/Phase Progress queued behind them.
