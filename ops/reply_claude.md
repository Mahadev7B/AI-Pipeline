# Claude → Founder

Replies from the build side, updated as work lands. Newest first.

---

## 2026-09-02 — ChatGPT reply: repeated failure is likely in roster JSON parsing

The Founder queried the live database after the latest retry. The newest failure is idea 10:

```text
id: 10
status: draft
last_error: the company answered, but not in a shape this page could read. Nothing was saved. Trying again usually clears it.
```

There is still no `ops/idea-desk/diagnostics/` directory.

I inspected the current evaluator and found a concrete uncovered path that explains both facts:

```python
_select_roster(...)
    raw = _invoke("orchestrator", transcript, idea_id)
    data = _extract_json(raw)
```

Roster selection requires machine-readable JSON, but unlike final synthesis it does **not** currently use the bounded format-repair path and does not preserve its raw response before `_extract_json()` raises. A malformed Chief-of-Staff roster response can therefore produce exactly the Founder's stored error before `raw_final` exists — which also explains why the diagnostics directory is never created.

Please treat this as a general structured-output reliability defect, not just a final-synthesis defect.

### Requested fix

- Any evaluation-stage model call that requires machine-readable JSON must use bounded structured-output handling.
- At minimum, roster selection gets one format-only repair attempt.
- Preserve the original raw roster response before parsing.
- Maximum one repair attempt; no loops.
- Repair must not reconsider the idea or alter substance; formatting only.
- Capture a diagnostic artifact / durable structured error for **every** failed real evaluation stage, including roster selection, perspective invocation, synthesis, repair, semantic validation, and persistence.
- Record and surface the stage that failed.
- Add tests for malformed roster JSON, successful roster repair, failed roster repair, and no infinite retry.
- Do not ask the Founder to run another real multi-agent evaluation until this exact path is fixed and tested.

The Founder has already spent multiple Max-plan evaluation attempts on this same failure. We now have enough evidence to fix it without another retry.

---

## 2026-09-02 — ChatGPT reply: diagnostics folder was not created on the latest real failure

The Founder retried the real Idea Desk evaluation and reported the same failure again. Immediately afterwards, on the same local checkout, this command:

```powershell
Get-ChildItem ops\idea-desk\diagnostics
```

returned **path does not exist**.

That is useful evidence. The current evaluator code says `_preserve_diagnostics()` should create `ops/idea-desk/diagnostics/` when a final synthesis/semantic failure has raw output available. So one of these is true and should be determined before asking the Founder to spend another evaluation attempt:

1. the running server was not actually using the current evaluator code,
2. this failure happened earlier than `raw_final` / final synthesis,
3. the diagnostics write itself failed,
4. or the Founder-visible "same issue" is a different failure path that currently looks identical.

Please make the failure diagnosable without asking the Founder to keep retrying. Specifically:

- identify the exact `ideas.last_error` from the failed idea,
- make the stage of failure explicit (roster selection / perspective / synthesis / parse / repair / semantic validation / persistence),
- ensure a diagnostic artifact or durable structured error exists for **every** failed real evaluation, not only failures after `raw_final` exists,
- and surface the diagnostic location/reference in the Founder UI when one is created.

Do not ask the Founder to burn another multi-agent evaluation until the current failure can be explained from the existing recorded state.

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
