```
Skill name: skill-creator
Purpose: Create, modify, optimize, and benchmark Claude Code skills.
When to invoke: Orchestrator adding, updating, or evaluating an entry in the Skill Registry as the real installed-skills set changes.
Inputs required: The skill to create/edit, or the skill to benchmark.
Analysis/checklist: Skill triggering accuracy, eval/benchmark support.
Expected output: A new or updated skill definition, or a benchmark report.
Failure conditions: N/A.
Limitations: Manages skills themselves — does not decide which agent should use one; that stays in `/ops/skills/README.md`'s agent map.
Which agents may use it: Orchestrator Agent.
Version: as installed in this environment, 2026-08-28.
```
