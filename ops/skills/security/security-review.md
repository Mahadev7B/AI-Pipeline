```
Skill name: security-review
Purpose: Complete a security review of the pending changes on the current branch.
When to invoke: Before a task leaves SECURITY_REVIEW status.
Inputs required: The pending diff on the current branch.
Analysis/checklist: Auth, secrets, permissions, user data, logging, file handling, dependency risk, injection, sensitive-data exposure.
Expected output: A PASS or REJECT verdict with findings.
Failure conditions: No pending diff to review.
Limitations: Reviews this repo's changes — does not audit third-party services or infrastructure the founder hasn't built here yet.
Which agents may use it: Security/Privacy Agent.
Version: as installed in this environment, 2026-08-28.
```
