```
Skill name: simplify
Purpose: Review changed code for reuse, simplification, efficiency, and altitude cleanups, then apply the fixes.
When to invoke: After Developer's implementation passes its own tests, before handoff to Code Review — a quality pass, not a bug hunt.
Inputs required: The changed code (current diff).
Analysis/checklist: Reuse opportunities, unnecessary complexity, efficiency.
Expected output: Applied cleanup edits to the working tree.
Failure conditions: No diff present.
Limitations: Quality only — does not hunt for correctness bugs; use `code-review` for that.
Which agents may use it: Developer Agent.
Version: as installed in this environment, 2026-08-28.
```
