# TASK-024 mockups — the Founder idea journey (DEC-015 revision)

Canvas: https://claude.ai/code/artifact/cb4151f6-1fa2-4d17-ab71-981e13d629de
Review: `ops/reviews/design-review-task024.md` (Revision 2)

**A clickable prototype with working navigation and no backend.** Nothing here
dispatches an agent, invokes a model or spends money.

## The walkable shell

| File | What it is |
|---|---|
| `Main.dc.html` | **Start here.** The app window: nav chrome, a clickable ten-stage journey rail, the five-voice legend, and the active stage mounted via `dc-import`. Back/Next plus each stage's own forward control. |

## The journey, left to right

| File | Stage |
|---|---|
| `S1RawIdea.dc.html` | 1 · Raw idea — Save Idea / Refine·Interpret…, the disclosure, the "saved, not started" ledger |
| `S2Interpreting.dc.html` | 2 · Factory interpreting — roster with reasons and omissions, depth + reason, no fake progress |
| `S3Understanding.dc.html` | 3 · Factory understanding — your words beside our reading, concise Q1–3 |
| `S4Evaluation.dc.html` | 4 · Idea evaluation — concise Q4–10 and the Company View |
| `S5Review.dc.html` | 5 · Founder review — Edit/Correct · Reconsider · Approve Brief; questions, and the honest zero |
| `S6Reconsider.dc.html` | 6 · Correction / reconsideration — feedback captured, round 2's delta, the free Founder edit |
| `S7Approval.dc.html` | 7 · Founder approval — what it does and does not do |
| `S8ApprovedBrief.dc.html` | 8 · Approved brief — WHAT I APPROVED as a distinct artifact, the three artifacts, the version ladder |
| `S9StartWork.dc.html` | 9 · Start work — arm → confirm → started, plus the failure and double-click states |
| `S10Running.dc.html` | 10 · Factory begins execution — what was written, what will not be shown and why |

## Reference sheets

| File | What it is |
|---|---|
| `Distinctions.dc.html` | The five-voice grammar that solves the central problem, and the same subject rendered in all five |
| `HonestStates.dc.html` | Ten honest states drawn, several beside the tempting wrong version |
| `FullDepth.dc.html` | The Full-depth expanded layer — every label slot, every value a marked structural placeholder |

## Content provenance

The idea walked is the Founder's real one for TASK-026, byte-for-byte, and the
Reconsider feedback is the Founder's real later correction. Every database figure
quoted (0 of 13 `agent_runs` with a cost; `task_steps` on 1 of 24; `project_id` NULL
on 20 of 24; one row in `projects`; `design` absent from the participant allowlist)
was queried this session. **No competitor, price, market number, duration or cost
estimate is invented anywhere** — where the product cannot know something honestly,
the slot is drawn as a bracketed placeholder. See §8 of the review.

## Superseded

`superseded/` holds Revision 1's artboards (Concept A `Main`, `StartFlow`, `Receipt`,
`Inline`, `Closeups`, and the flat HTML export). They are kept, not deleted —
review §9 records what survived from them and what was dropped.
