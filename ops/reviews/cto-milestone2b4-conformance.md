# CTO Post-Implementation Conformance Review — Phase 2, Milestone 2B4 (TASK-013)

Final gate before `risks.id=2` status can move. Verified independently
against the shipped code (`git diff 4332168^..7bdd040`), not against any
prior gate's description — Code Review (`ops/reviews/code-review-milestone2b4.md`,
PASS), QA (`ops/reviews/qa-milestone2b4.md`, PASS), and Security's
post-implementation adversarial pass (`ops/reviews/security-adversarial-milestone2b4.md`,
PASS) all already passed; this pass checks architectural conformance
against my own original proposal (`ops/reviews/cto-milestone2b4-architecture.md`,
incl. §13's C1–C3 corrections), Security's threat-model review, and Red
Team's architecture review.

## 1. No second operational state store

Confirmed. Grepped `founder_auth.py` and the new `server.py` auth code
(`_handle_login`/`_handle_logout`/`_authenticated_session`/`_check_credential_gate`
and helpers) for `opsdb`/`sqlite3`/`conn.execute` — zero matches. The only
new state is `.founder_credential.json` (file, outside git) and `SESSIONS`
(in-memory dict). `operations.sqlite3` remains the sole operational source
of truth; `git diff 4332168^..7bdd040 -- ops/db/opsdb.py ops/db/schema.sql`
is empty. **Conforms.**

## 2. No duplicate auth system

Confirmed exactly one new mechanism: the Founder-session cookie
(`fc_session`). The pre-existing `SESSION_TOKEN` CSRF check is unchanged
in its own logic and composes with the new check as designed — in
`do_POST()`, `_require_csrf_token()` runs first (now covering `/api/login`
and `/api/logout` too, per C2), then `_authenticated_session()` runs
second, for the 7 pre-2B4 write routes only (correctly excluded for
`/api/login`, which creates the session, and `/api/logout`, which must
work from an already-expired session). Not two competing systems — two
checks answering different questions, exactly as §6 specifies. **Conforms.**

## 3. No Agent Runtime contamination

`git diff 4332168^..7bdd040 -- ops/control-center/agent_runtime.py` is
empty — zero diff. Grepped `founder_auth.py` and all login/logout code in
`server.py` for `invoke_agent`/`run_meeting`/`gather_requested_position`/
`gather_followup_reply`/`retry_position` — zero references. The only two
`agent_runtime.invoke_agent()`/`meeting_orchestrator.run_meeting()` call
sites in the file are `_handle_ask()`/`_handle_meeting_create()`, both
pre-existing routes now additionally gated by the Founder-session check,
never touched by the auth code itself. **Conforms.**

## 4. No model-dependent auth

`founder_auth.derive_hash()`/`verify_passphrase()` is pure `hashlib.scrypt`
+ `secrets.compare_digest()` — deterministic stdlib, no subprocess, no
model call, no network call. **Conforms.**

## 5. No provider coupling / stdlib-only

Grepped every import in `founder_auth.py` (`argparse`, `base64`,
`getpass`, `hashlib`, `json`, `os`, `secrets`, `sys`, `time`, `pathlib`)
and the new imports in `server.py`/`layout.py` (`threading`, `time`,
already-present `re`/`secrets`/`sqlite3`/`http.server`/`urllib.parse`;
`layout.py` adds nothing beyond its existing `html`) — all stdlib, zero
third-party packages, zero SaaS dependency. **Conforms.**

## 6. Founder UX

Read `login_page()` and `setup_required_page()` in `layout.py` directly.
Both are coherent: `setup_required_page()` states the problem plainly and
gives the exact command to run, in a monospace block, with no other
content to distract from it. `login_page()` has a single password field,
a clear error slot, and a footer line stating the session's actual
lifetime (12h / 30min idle) so the Founder isn't surprised by a later
forced re-auth. `_bare_page()` correctly omits all nav links so a locked
visitor can't see any gated destination even as a link. One rough edge,
non-blocking: there is no "forgot my passphrase" guidance on the login
page itself (the only recovery path is `founder_auth.py change`, which
itself requires knowing the current passphrase, or manually deleting the
credential file and re-running `setup` — this is implied by the
architecture but not surfaced anywhere in the UI). For a sole Founder who
set this up minutes prior, this is a minor and acceptable gap, not a
defect Development should have caught — flagging only for awareness if a
future milestone touches this page again. **Conforms**, with a
non-blocking UX note.

## 7. Centralized authorization boundary — all 9 write routes, all GET routes

Enumerated all 9 `do_POST()` routes directly in the code:
`/api/login`, `/api/logout`, `/api/approvals/<id>/decide`,
`/api/agents/<name>/ask`, `POST /api/meetings`,
`/api/meetings/<id>/decide`, `/api/meetings/<id>/request-perspective`,
`/api/meetings/<id>/followup`, `/api/meetings/<id>/retry`. All 9 pass
through the identical `_check_credential_gate()` → path-match →
`MAX_BODY_BYTES`/decode/parse → `_require_csrf_token()` sequence in one
function, before any dispatch; the 7 pre-2B4 routes additionally pass
through `_authenticated_session()` at one single call site, still before
dispatch. No per-handler auth check exists anywhere — verified by reading
every `_handle_*` method body, none of which re-checks CSRF or session
state. `do_GET()` gates identically: `_check_credential_gate()` first,
`/login` allowlisted, then `_authenticated_session()` before the entire
path if/elif chain — no GET branch is reachable without a session except
`/login` and the setup-required 503. Independently corroborated by
Security's adversarial pass hitting all 9 routes directly with `curl`
(all fail closed) and by Code Review's direct diff-hunk-location check.
**Conforms.**

## 8. Historical auditability

All designed log lines are present verbatim in `server.py`: `"founder
login succeeded"`, `"founder login FAILED (n/N)"`, `"login lockout
triggered"`, `"login attempt rejected — currently locked"`, `"founder
session ended (logout)"`, `"session expired (idle)"` / `"session expired
(absolute)"`, `"rejected {method} {path} — no authenticated Founder
session"` — matches §9 exactly, none omitted, none logging secret
material (grepped every `log_message`/`stderr.write` call site touching
this feature).

Pre-existing auditability unaffected: `git diff` on `opsdb.py`/`schema.sql`
is empty, so `agent_runs`/`task_status_history`/`review_results`/
`qa_results` are structurally untouched. Spot-checked directly:
`review_results` has 4 rows for `task_id=13` (red-team/pass, code-review/pass,
security/reject [architecture-stage], security/pass [post-implementation
adversarial]) and `qa_results` has 1 row, both queried and fully readable
via `opsdb.py query`. **Conforms.**

## 9. Risk disposition — the load-bearing check

Security's post-implementation adversarial pass is now PASS (the
condition both my original §13 and Security's own threat-model draft set
for moving `risks.id=2`). Re-read Security's draft language
(`security-milestone2b4-threat-model.md`, "Draft `risks.id=2` language")
against what actually shipped: every claim in it is still accurate —
C1 (full serialization) shipped and was independently reproduced three
times (Code Review, QA, Security-adversarial, plus a 45,820-request
40-second sustained flood); C2 (CSRF on `/api/login`) shipped and was
verified live; the full-app-lock, cookie flags, timeouts, and the
`risks.id=3`/Bash-agent/PTRACE_ATTACH carve-out all match the shipped
code exactly. Nothing overclaims (the description still explicitly names
what remains open) and nothing underclaims (every closed gap it names is
genuinely closed, independently re-verified three separate times by three
separate reviewers under adversarial conditions, not just claimed).

**Recommended final `risks.id=2` language** (orchestrator to apply via
`opsdb.py risk-resolve` — not applied by this review):

> **Status**: `mitigated` (not `resolved`)
> **Description**: "Founder-facing actions — all 9 write/auth routes
> (`/api/login`, `/api/logout`, and the 7 pre-existing write routes) and
> every GET read — require a locally authenticated Founder session: a
> 16+ character passphrase known only to the Founder, verified via a
> salted `hashlib.scrypt` hash (`N=2**17, r=8, p=1`) stored outside git
> (`ops/control-center/.founder_credential.json`, 0600, atomic writes,
> never touching `operations.sqlite3`, logs, or generated HTML), gated by
> a server-side session cookie (`HttpOnly`, `SameSite=Strict`, 30-minute
> idle / 12-hour absolute timeout, in-memory only, wiped on restart), and
> rate-limited against brute force via fully serialized login verification
> (closes both the stated 5-attempt cap and a concurrent-scrypt
> memory-exhaustion DoS — independently verified under a 60-simultaneous
> and a 45,820-request sustained flood). This closes the gap for any
> local actor that does not already share the Founder's own OS-user
> filesystem/process principal — a real, previously-open gap, now shipped
> and independently verified three times (Code Review, QA, Security
> post-implementation adversarial pass, all PASS). It does **not** close
> the case where an agent runs with Bash tool access under the Founder's
> own OS user (risk `id=3`): such an agent can read or overwrite the
> credential file directly, run `founder_auth.py` itself, or
> `PTRACE_ATTACH` the running server process and read session state out
> of memory — exactly as it could already read a served page's CSRF
> token before this milestone. Also disclosed and unresolved: the shared,
> non-identity-scoped lockout can be flooded by an actor already inside
> this design's own threat class to deny the Founder's own genuine logins
> (Red Team's Milestone 2B4 finding F1) — no cheap in-scope fix exists
> without touching `risks.id=3`. Closing either gap requires resolving
> risk `id=3` first, or a different class of infrastructure this
> milestone's scope deliberately excludes. See
> `ops/reviews/cto-milestone2b4-architecture.md`,
> `ops/reviews/security-milestone2b4-threat-model.md`,
> `ops/reviews/red-team-milestone2b4-architecture.md`,
> `ops/reviews/code-review-milestone2b4.md`, `ops/reviews/qa-milestone2b4.md`,
> `ops/reviews/security-adversarial-milestone2b4.md`."

This is a light refinement of Security's architecture-stage draft, not a
substantive rewrite: added the F1 self-DoS disclosure explicitly (present
in `SECURITY.md` and both post-implementation reviews but not in
Security's original draft, which predated Red Team's F1 finding), named
the independent post-implementation verification, and cited the two new
post-implementation review documents.

## 10. Phase 3 has not begun

Grepped the diff for automatic-routing/autonomous-execution signatures
(`auto.?rout`, `autonomous`, `auto.?assign`, `auto.?execut`,
`self.?initiat`) across `server.py`/`founder_auth.py`/`layout.py` — zero
matches. This milestone adds exactly one thing: an auth boundary in front
of routes that already existed. No new route initiates any downstream
agent action, no code path routes a task between agent roles, nothing
executes without the same human-in-the-loop pattern (Founder clicks
Approve/Reject/Ask/etc.) that predates this milestone. **Stays in lane.**

## 11. Bash-scoping risk (id=3) untouched

Queried `risks` directly: `id=3` — status `open`, `resolved_at` `NULL`,
`mitigation` `NULL`, description unchanged from the pre-milestone text.
Zero rows in the diff touch the `risks` table for `id=3`, and no code in
this milestone claims to address it (§11/`SECURITY.md`'s own language
explicitly carves it out as unaddressed). **Untouched, confirmed.**

## 12. `report.py --check`

Ran at current HEAD: `OK: /home/user/AI-Pipeline/ops/reports/CURRENT_STATUS.md
matches the live database.` Exit code 0. **Passes.**

## Verdict: CONFORMS

No architectural drift from the approved design (incl. C1–C3 and F1/F2
corrections). All 12 checks pass. One non-blocking UX note (§6, "forgot
passphrase" guidance) — not a defect requiring routing back to any agent,
noted for awareness only. Recommend the orchestrator apply the §9 language
above to `risks.id=2` via `opsdb.py risk-resolve`, and separately move
TASK-013's task status forward (currently `BACKLOG`, per Code Review's own
non-blocking note) — neither of which this review performs.
