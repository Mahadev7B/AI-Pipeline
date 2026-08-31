```
Skill name: fewer-permission-prompts
Purpose: Scan transcripts for common read-only Bash/MCP calls and add a prioritized allowlist to reduce permission prompts.
When to invoke: DevOps doing session hygiene on a repo with recurring prompt friction.
Inputs required: Recent session transcripts.
Analysis/checklist: Identifies safe, repeated read-only calls.
Expected output: An updated `.claude/settings.json` allowlist.
Failure conditions: No recurring pattern found.
Limitations: Read-only calls only — never widens write/destructive permissions. Must NOT be used to add, remove, or modify any `hooks:` block in any `.claude/agents/*.md` file, any file under `ops/control-center/hooks/`, or the `hooks` key of any `.claude/settings*.json` — those are protected architecture artifacts (TASK-017, risks.id=3 reduction milestone), changed only via a CTO/Red-Team-reviewed decision-record.
Which agents may use it: Release/DevOps Agent.
Version: as installed in this environment, 2026-08-28.
```
