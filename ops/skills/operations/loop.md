```
Skill name: loop
Purpose: Run a prompt or slash command on a recurring interval, self-paced or fixed.
When to invoke: Phase 3 — Chief of Staff running a recurring status/orchestration check; DevOps polling a recurring deploy/CI check.
Inputs required: The prompt/command to repeat and an interval (or self-pacing).
Analysis/checklist: N/A — scheduling tool.
Expected output: The wrapped prompt/command executed on schedule.
Failure conditions: One-off task (not recurring) — do not invoke.
Limitations: Not used in Phase 0/1 — this system has no automation to schedule yet.
Which agents may use it: Chief of Staff (Phase 3), Release/DevOps Agent.
Version: as installed in this environment, 2026-08-28.
```
