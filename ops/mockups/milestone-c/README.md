# Milestone C Design Review — Company-wide Risks Register

Design-review mockups for TASK-021 (DEC-009 Milestone C), reviewing
CTO's architecture in `ops/reviews/cto-milestone-c-architecture.md`.
Static mockups (not a clickable prototype) — matches CTO's own
zero-client-side-JS constraint and every prior Control Center screen,
same discipline as `ops/mockups/milestone-a/` and `ops/mockups/milestone-b/`.

Visual language copied verbatim from
`ops/mockups/control-center-phase-0/Main.dc.html` / `ops/control-center/layout.py`
(Style A, dark) — no new visual system introduced.

Content is **real, current data** from the live `operations.sqlite3`,
queried 2026-09-01: all 4 rows in `risks` (including `risks.id=3`'s
full, real, 2,820-character mitigation text — not truncated or
paraphrased) and the 5 real `decisions` rows whose text literally
names `risks.id=3` (ids 9, 10, 11, 12, 13). Not placeholder/lorem-ipsum
content.

## Three artboards, published as one canvas

- `Main.dc.html` — **Concept A, recommended.** CTO's status-first
  section layout (Open/Mitigated/Resolved, severity-desc within each)
  plus one addition: a "Needs attention" strip surfacing open,
  medium/high-severity risks at the very top (reusing the phase-0
  "Needs You" strip pattern already established for exactly this kind
  of cross-cutting callout), and the mitigation-history disclosure
  moved to page level (shown once) rather than repeated on every card.
- `FlatSeverityFirst.dc.html` — **Concept B, alternate, not
  recommended.** A single flat list, sorted severity-first, status
  shown only as an inline pill — the structural alternative CTO's own
  §6.3.1 asked Design to weigh against. Same real 4 rows, restructured.
- `Risk3Detail.dc.html` — closeup on `risks.id=3` specifically: three
  renderings of the identical real card, testing (1) CTO's literal
  spec, (2) the recommended text-width cap + page-level-only
  disclosure, (3) a rejected "related decisions as a full list"
  alternative.

Published as one multi-artboard canvas — an Artifact, not application
code: https://claude.ai/code/artifact/f99f9edd-aa31-4253-bb70-381f49c98978

See `ops/reviews/design-review-milestone-c.md` for the full review,
verdict, and specific recommendations relative to CTO's architecture.
