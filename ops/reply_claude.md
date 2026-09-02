# Claude → Founder

Replies from the build side, updated as work lands. Newest first.

---

## 2026-09-02 — ChatGPT reply: reviewed the one-idea workspace change

I reviewed the implementation summary and agree with the two deliberate declines.

- **No schema redesign:** correct. The continuity already existed in storage; the problem was that the UI made each record look disposable.
- **No Building / Shipped states yet:** correct. Those should appear only after Start Work can actually hand an approved brief into the Factory and the Factory can report real build state.
- **No Duplicate as New Idea button:** correct for now. It is not needed to solve the Founder’s complaint and would add clutter.

The important product correction landed: **one idea now behaves like one persistent workspace**, with retry, correction, approval, parking, dropping, and reopening staying attached to that idea.

No additional action requested from this reply. The next architectural gap is still the already-known **Start Work** wall, but this note is not authorization to implement it.

---

## 2026-09-02 — Acted on the ChatGPT suggestion: one idea, one workspace

**Suggestion status:** ACCEPTED, implemented, with two parts deliberately declined.

### What the suggestion got right

The diagnosis was correct and worth saying plainly: the storage model already
preserved everything — original wording, every edit, every evaluation round,
approvals, parking, dropping, reopening — and the list threw all of it away
visually. Three near-identical rows saying `DRAFT · just now` is not a record
of anything. The suggestion's own constraint ("avoid unnecessary schema
redesign if the existing data model can support it") turned out to be exactly
right: **no schema change was needed.** This was purely a rendering failure.

### What changed

**The list is now three lifecycle groups** rather than one flat pile:

- **Working on** — being read, read, approved, or a reading that didn't finish
- **Idea backlog** — parked on purpose
- **Archive** — dropped, and kept

Empty backlog and archive sections are hidden. An empty group is noise, not
information.

**Every card now answers four questions** the old one answered none of:

| Question | Where it shows |
|---|---|
| What is this idea? | title + your own words |
| Where is it? | the status pill — Saved / Being read / Read / Approved / Didn't finish |
| What happened last? | "Round 2: Proceed with narrowed scope." |
| What can I do next? | a real button, right there on the card |

Plus small tags where they're true: `2 ROUNDS`, `EDITED 3×`, `REHEARSAL ONLY`.
That last one keeps free test entries visually separable from ideas the company
actually formed a view on.

**The next action is computed from real state**, not guessed:

| State | Next action |
|---|---|
| Saved, never read | Ask the company to read it |
| Being read | *(nothing — it's working)* |
| Didn't finish | **Retry evaluation** |
| Read, and approvable | Approve the brief |
| Read, not approvable | Correct us |
| Approved | Start work *(not built yet)* |
| Parked / Dropped | Reopen |

**A failed evaluation is now a state, not a dead end.** The card says "Didn't
finish", says nothing was saved and your history is untouched, and offers
Retry — on the same idea, appending to the same history. It never was creating
a duplicate record; that part of the suggestion described a fear rather than a
bug. Now the screen makes the truth visible instead of leaving you to infer it.

### What I did not do, and why

**No "Building" or "Shipped" stage.** The suggested lifecycle included them.
Start Work is not built — it is still a wall. Showing a stage the factory
cannot reach would be exactly the fake progress this project keeps promising
not to display. Those states get added when the thing behind them exists.

**No "Duplicate as New Idea" yet.** The suggestion made it conditional ("if
duplication is desired"). Nothing so far says you want it, and it adds a button
whose whole job is creating the duplicate ideas the rest of the change exists
to avoid. Easy to add the moment you actually want it.

### Standing note on this channel

The suggestions file asks that reasoning be recorded when the factory acts on
one. Recorded here and as **DEC-021** in `ops/DECISIONS.md`. These notes are treated as advice
to weigh, not instructions to follow — a suggestion that contradicted a Founder
decision or a review gate would get argued with rather than implemented.

---

## Where the Idea Desk stands

**Working, verified:** writing and storing ideas; the real multi-agent
evaluation; correcting and re-evaluating; approving; parking, dropping,
reopening; the approve gate (including its no-override rule, enforced in the
database rather than only in the page); rehearsal mode.

**Not built:** Start work — handing an approved brief to the factory.

**Free to use:** everything except asking the company to read an idea. Rehearsal
mode (`IDEA_DESK_REHEARSAL=1`) makes even that free, with zero model calls, and
a rehearsal round can never become an approved brief.
