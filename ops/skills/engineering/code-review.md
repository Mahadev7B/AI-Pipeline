```
Skill name: code-review
Purpose: Review a diff (or PR/branch/path) for correctness bugs and reuse/simplification/efficiency issues.
When to invoke: Before a task leaves CODE_REVIEW status.
Inputs required: A diff, PR number, branch, or path target; optional effort level (low/medium/high/max).
Analysis/checklist: Correctness bugs; reuse/simplification/efficiency opportunities.
Expected output: A findings list, most-severe first; optionally posted as inline PR comments (--comment) or auto-fixed (--fix).
Failure conditions: No diff/target resolvable; effort level too low to catch a real bug.
Limitations: Does not test running behavior — pair with QA's `run`-based testing for that.
Which agents may use it: Code Review Agent.
Version: as installed in this environment, 2026-08-28.
```
