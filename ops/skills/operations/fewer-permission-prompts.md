```
Skill name: fewer-permission-prompts
Purpose: Scan transcripts for common read-only Bash/MCP calls and add a prioritized allowlist to reduce permission prompts.
When to invoke: DevOps doing session hygiene on a repo with recurring prompt friction.
Inputs required: Recent session transcripts.
Analysis/checklist: Identifies safe, repeated read-only calls.
Expected output: An updated `.claude/settings.json` allowlist.
Failure conditions: No recurring pattern found.
Limitations: Read-only calls only — never widens write/destructive permissions.
Which agents may use it: Release/DevOps Agent.
Version: as installed in this environment, 2026-08-28.
```
