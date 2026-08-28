# SECURITY.md

## Scope of this document

This covers the security/privacy posture of the *operating system itself*
(Phase 0–3 of `/ops`), not the founder's eventual product — that gets its
own security review once product work starts, per the workflow's
`SECURITY_REVIEW` stage.

## Principles

- **Least privilege.** Every agent's `/ops/agents/*.md` file has an
  explicit Tools + Permissions section with a "Not permitted" list. No
  agent gets a tool or permission it doesn't need for its stated role.
- **No credentials in Git.** Nothing in `/ops` ever contains a real API
  key, password, token, or connection string. Founder approval templates
  reference services by name/cost, never by credential.
- **No real financial or personal data.** The Financial Agent's frameworks
  (`/ops/agents/financial.md`) operate on approved project-cost data only,
  never real external financial accounts, in Phase 0.
- **No production access from documentation-phase agents.** Nothing built
  in Phase 0 can deploy, purchase, or move money — those permissions don't
  exist yet for any agent (see each agent's Permissions section).
- **Auditability.** Every decision, handoff, and approval is written down
  (`DECISIONS.md`, `/ops/templates/handoff.md`, `/ops/approvals/`) — not
  left as unrecorded conversation.

## Review gate

Once real product code exists, the Security/Privacy Agent
(`/ops/agents/security.md`) is the required gate before `READY_TO_RELEASE`
— see `AGENT_STATUS.md`. It reviews auth, secrets, permissions, user data,
logging, file handling, dependency risk, injection risk, and sensitive-data
exposure, and outputs PASS or REJECT.

## Open items for Phase 1+

- Where SQLite (`DATA_MODEL.md`) lives on disk, its file permissions, and
  whether any table ever needs encryption at rest, is a Phase 1 decision —
  not decided here.
- Model Registry entries (`/ops/models/`) must record privacy
  considerations and licensing per model before a model is approved for
  use — see `/ops/models/MODEL_TEMPLATE.md`.
