# TASK-024 mockups — Founder Idea Intake

Canvas: https://claude.ai/code/artifact/6eb8e58e-4ef8-4201-8f7c-e92aad45c612
Review: `ops/reviews/design-review-task024.md`

| File | What it is |
|---|---|
| `Main.dc.html` | **Concept A — recommended.** Ideas page (first-run, just-saved) + TASK-025's Task Detail with the Start panel. Save and Start never share a screen. |
| `StartFlow.dc.html` | The Start action, every state: why Save and Start can't look alike, the confirm screen, the started after-state, the failure state and the double-click lock. |
| `Receipt.dc.html` | Concept B — one surface, staged. Counted-nothings receipt that also offers Start. Rejected; its receipt block is worth keeping. |
| `Inline.dc.html` | Concept C — capture and start from Active Work, with a receded "Not started" zone. Rejected; its receded BACKLOG row treatment is worth keeping. |
| `Closeups.dc.html` | Nav placement, validation/error states, per-field caps from real data, the priority control, the BACKLOG stuck-badge question. |

All content is real, queried from the live database on 2026-09-01: TASK-025
(the one genuine BACKLOG row, with its actual title, business_goal and
creation time), TASK-023/024 on Active Work, the real `priority` distribution,
the real title/business_goal length statistics, and the fact that 0 of 13
`agent_runs` rows carries a cost figure.

Note: these were drafted against Product's brief and then revised after a
Founder scope correction added a UI Start action mid-design — see §0 of the
review.
