# Chief of Staff — recommendations at the end of the session

Written 2026-09-01, alongside `founder-session-2026-08-30_2026-09-01.md`.
The Founder asked for these after being handed a status board without an opinion.

These are positions, not options. Where I am recommending against work the
Founder has already directed, I say so plainly rather than burying it.

---

## 1. Build one small thing before building any more tooling

**Everything currently queued is tooling for activity that has never happened.**

- TASK-024 is a front door and a deciphering stage for ideas that have never been submitted.
- TASK-026 is a tracking screen for builds that have never run.
- TASK-023 is a cage for a Developer that has never built a product.

All three are being designed against imagined activity. That is exactly the
failure that produced a full day of work aimed at the wrong subject, and it
will keep producing it. The `projects` table has one row and it is the ops
system itself.

**Recommendation:** point the factory at one small app, end to end, and watch
what actually happens. Not because the app matters — it does not, and the
Founder has correctly said they have no app idea and do not need one. Because
until one real build exists, every screen is a guess and every requirement is
speculation.

The cost of being wrong here is asymmetric. A throwaway build costs an hour.
Another day of tooling designed against imagined activity costs a day, and we
have already spent one.

## 2. Leave TASK-023 parked

Eight rounds. Each round closed one route and revealed another — the last
Red Team review found the fix had opened a shorter path than the one it closed.
The findings were all real; the work is not wasted; the architecture and the
whole trail are committed and resumable.

But it is a security cage around a factory with no output, and it is unbounded
in a way nothing else here is. Resume it when the factory is producing something
worth protecting, or when someone other than the Founder will run it.

**This contradicts nothing the Founder decided** — DEC-012 already sequenced it
ahead of Phase 3 automation, and Phase 3 automation should also stay parked.

## 3. Cut the pipeline down for product work

Nine gates — Product, Design, CTO, Red Team, Developer, Code Review, QA,
Security, conformance — were built for a factory modifying **itself**, where a
mistake corrupts the machine. Pointed at a small app, most of them are ceremony.
Nine reviews to build a page is theatre, and this session's own evidence supports
that: CTO earned its place on the security architecture and added little to the
four dashboard milestones.

**Recommendation:** for product work, keep three roles — something to pin down
what is wanted, something to build it, something independent to check it works.
Add the rest only where the stakes justify it. Keep the full sequence for changes
to the factory itself.

## 4. Sweep for other things that are documented but do not work

Three found so far, all by accident:

1. TASK-017's `PreToolUse` hook never fired in the deployed context (QA).
2. `developer.md` claimed a defence-in-depth layer that structurally could not
   fire inside the sandbox (CTO, under QA pressure).
3. Eight agents carry a `Skill` tool grant that is **inert on the runtime path** —
   `agent_runtime._run_claude()` passes `--tools ""` — and `product.md` documents
   a skill that is user-account-synced, not in this repo, and does the wrong job
   anyway (Product, this session).

Three is a pattern, not a coincidence: this project writes capability claims into
role documents and never tests that they fire.

**Recommendation:** one deliberate pass over every claim in `.claude/agents/*.md`
and every "the system does X" line in `SECURITY.md` and the architecture
documents, checking each against what actually executes. Cheap, and it is finding
real defects at a rate of one per look.

## 5. Two integrity findings that should not sit unaddressed

From Product's TASK-026 brief, found while reading the data rather than looked for:

- **Tasks 11 and 18 are `DONE` with zero review, QA and handoff rows between
  them.** Either work shipped without its gates, or the record is wrong. Both are
  worth knowing, and the second is worse for a company whose whole claim is its
  review discipline.
- **`review_transcripts.py` and `launch_developer_session.py` feed
  `business_goal` — the raw Founder idea — into agent transcripts.** Once
  TASK-024 exists, that is precisely the field that must *not* go downstream, and
  nothing about those call sites looks wrong.

## 6. On the record itself

The session log is committed unedited, including the parts where this company was
corrected. That was deliberate and I would keep it that way. The most useful
single line in it is the Founder's:

> *"We successfully built much of the factory, but we accidentally treated the
> factory-control dashboard as the final product."*

That is the whole lesson of the session, and it was the Founder who said it, not
the company.
