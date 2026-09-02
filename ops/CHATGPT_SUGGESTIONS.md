# ChatGPT Suggestions

This file is an advisory handoff channel for product, UX, architecture, reliability, and workflow observations from ChatGPT to the AI Factory team.

These notes are **not Founder authorization** and should not bypass normal role separation or review gates. Claude / the Factory may accept, refine, or reject a suggestion, but should record the reasoning when it acts on one.

---

## 2026-09-02 — Treat each saved idea as one persistent workspace

**Status:** OPEN  
**Area:** Idea Desk / Founder UX  
**Priority:** High

### Observed problem

The Idea Desk currently leaves the Founder with many items that look and feel like disposable drafts. When an evaluation fails, or when the Founder edits/retries an idea, the accumulated records do not feel useful. The Founder’s reaction is effectively: **“There are lots of drafts, but what is the point?”**

The underlying storage model already preserves raw ideas, edits, evaluation rounds, approvals, parking/dropping, and reopening. The product problem is that the UI does not make that continuity obvious or useful.

### Product principle

**One idea = one continuing workspace.**

A saved idea should become the permanent home for that idea from first thought through evaluation, refinement, approval, build, or archive. Editing, retrying, brainstorming, correcting, or reevaluating should continue on the same idea record rather than making the Founder feel like another disposable draft was created.

### Recommended lifecycle

```text
DRAFT
  ↓
EVALUATING
  ↓
EVALUATED
  ↓
REFINING
  ↓
FOUNDER APPROVED
  ↓
BUILDING
  ↓
SHIPPED
```

Interrupt / alternate outcomes can include:

```text
EVALUATION FAILED → Retry on the same idea
PARKED            → Reopen the same idea later
DROPPED            → Archive, without deleting history
```

### Failed-evaluation UX

A failed evaluation should **not** make the idea feel abandoned or force the Founder to start over.

Example:

```text
Game-based Python learning for kids

Status: Evaluation failed

Your original idea:
"game based learning for kids to learn python and design a game while learning."

Last attempt:
Company evaluation failed during synthesis.

[ Retry Evaluation ]
[ Edit Idea ]
[ Brainstorm ]
[ Park for Later ]
```

Retry should operate on the **same idea** and append a new attempt/round to its history.

### Idea Desk organization

Instead of presenting a long flat list of drafts, organize ideas into three useful buckets:

1. **Working on** — ideas being evaluated, refined, awaiting Founder review, approved, or building.
2. **Idea backlog** — ideas intentionally saved for later.
3. **Archive** — dropped ideas, abandoned experiments, failed test entries, and old rehearsal-only items.

The Founder should immediately understand why each saved idea exists and what can happen next.

### New Idea behavior

- Clicking **New Idea** creates one idea record.
- Subsequent Edit / Evaluate / Retry / Brainstorm actions continue on that record.
- Do not create another idea merely because an evaluation failed or the Founder changed wording.
- If duplication is desired, make it an explicit action such as **Duplicate as New Idea**.

### What the Founder should be able to do from one idea workspace

- Edit the raw idea while preserving the original
- Evaluate it
- Retry a failed evaluation
- Brainstorm / decipher further
- Answer material clarifying questions
- Review prior evaluation rounds
- Refine the interpreted brief
- Approve the brief
- Start work
- Park it for later
- Drop it
- Reopen it
- Later, see the build that resulted from it

### Why this matters

Saving is valuable only if the saved record becomes a durable project memory. The Idea Desk should feel like the front door to the Factory, not a stack of forms.

The intended mental model for the Founder is:

> “This is one idea in my company. Everything the company learns, recommends, changes, approves, and eventually builds stays attached to it.”

### Constraints

- Preserve the original Founder wording and audit trail.
- Do not delete historical evaluation rounds.
- Do not merge genuinely distinct ideas automatically.
- Do not make retries create confusing duplicate idea cards.
- Rehearsal/test entries should be clearly separable from genuine Founder ideas.
- This is a UX/product correction; avoid unnecessary schema redesign if the existing data model can support it.

### Acceptance direction

A successful redesign should make it difficult for the Founder to ask “why are all these drafts here?” because every idea card clearly shows:

- what the idea is
- where it is in its lifecycle
- what happened last
- what the next useful action is
- whether it is active, backlog, or archived

