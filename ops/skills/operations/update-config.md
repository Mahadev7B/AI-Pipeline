```
Skill name: update-config
Purpose: Configure the Claude Code harness via settings.json — permissions, env vars, hooks.
When to invoke: DevOps needs to change environment configuration or permission allowlists.
Inputs required: The desired setting/permission/env-var change.
Analysis/checklist: N/A — configuration tool.
Expected output: Updated settings.json / settings.local.json.
Failure conditions: Ambiguous target file (project vs. user settings) — asks first.
Limitations: Configures the harness, not the product's own runtime config. Must NOT be used to add, remove, or modify any `hooks:` block in any `.claude/agents/*.md` file, any file under `ops/control-center/hooks/`, or the `hooks` key of any `.claude/settings*.json` — those are protected architecture artifacts (TASK-017, risks.id=3 reduction milestone), changed only via a CTO/Red-Team-reviewed decision-record.
Which agents may use it: Release/DevOps Agent.
Version: as installed in this environment, 2026-08-28.
```
