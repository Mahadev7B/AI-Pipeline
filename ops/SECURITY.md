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

## Founder write authorization (Milestone 2B1)

`ops/control-center/server.py` is the first process that lets a browser
action become a database write. Full design in
`ops/reviews/cto-milestone2b1-architecture.md`; summarized here so it's
findable without a review doc.

**Technically enforced now:**
- The server binds `127.0.0.1` only — never reachable from outside this
  machine.
- Every write goes through exactly one function, `opsdb.decide_approval()`
  — no SQL endpoint, no shell endpoint, no other write path exists.
- A `POST /api/approvals/<id>/decide` is rejected (403) unless it carries
  the exact session token the currently-running server process generated
  at startup (`secrets.token_urlsafe(32)`, in-memory only, regenerated
  every restart, never written to disk or logged).
- The write itself is atomic and conditional (`UPDATE ... WHERE decision
  IN (...)`) — a decision on an approval not currently in a decidable
  state affects zero rows and is rejected cleanly, closing the
  double-submit / re-decide-a-resolved-approval gap that existed in the
  original CLI-only path.

**Still relies on local/single-user trust — not solved:**
- The session token proves a request came from a page this server
  process rendered this run. It does **not** prove a human, specifically
  the Founder, sent it. Any process on this machine that can make an
  HTTP request to `127.0.0.1` and first read the served page (to extract
  the token) can forge the same POST — including an agent invoked with
  Bash tool access, per the still-open risk below. This is the same
  category of limitation as Phase 1's `--confirm-founder-decision` flag,
  just narrower in scope (no network exposure, no replay of a stale
  request, no blind trust of a client-asserted value) — not a different
  kind of guarantee.
- There is no login, no session/cookie system, no user identity at all.
  "Founder" is not a modeled identity anywhere in the schema.

**What would need to change before any internet-facing deployment:**
real authentication (not a bearer token generated per-process), TLS,
CSRF protection independent of the loopback assumption, and almost
certainly abandoning the "single trusted local machine" model this whole
system is built on — see `DATA_MODEL.md`'s "Known limitation" on the
committed-SQLite-file approach, which has the same single-machine
assumption baked in at the data layer, not just the write boundary.

**Both Phase 1 risks remain open, unchanged by this milestone** — track
via `python3 ops/db/opsdb.py query "SELECT id,title,status FROM risks"`:
- `risks.id=2` — Founder approval is not identity-authenticated (this
  milestone narrows the *how* without closing the underlying gap).
- `risks.id=3` — Bash tool access cannot be scoped below the
  tool-category level (this is exactly what makes "an agent could forge
  a request" a real, not hypothetical, limitation above).
