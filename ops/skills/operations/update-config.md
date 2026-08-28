```
Skill name: update-config
Purpose: Configure the Claude Code harness via settings.json — permissions, env vars, hooks.
When to invoke: DevOps needs to change environment configuration or permission allowlists.
Inputs required: The desired setting/permission/env-var change.
Analysis/checklist: N/A — configuration tool.
Expected output: Updated settings.json / settings.local.json.
Failure conditions: Ambiguous target file (project vs. user settings) — asks first.
Limitations: Configures the harness, not the product's own runtime config.
Which agents may use it: Release/DevOps Agent.
Version: as installed in this environment, 2026-08-28.
```
