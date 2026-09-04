# Security review — TASK-024 Idea Desk, slices 1 and 2

Reviewer: Security agent
Date: 2026-09-02
Scope: `ops/idea-desk/` (server.py, pages.py, evaluator.py, doctor.py,
seed_founder_idea.py, README.md); the TASK-024 section of `ops/db/opsdb.py`
(lines 1713-1925, 2164-2216) and `ops/db/schema.sql` (lines 455-515); the
TASK-024 additions to `ops/control-center/agent_runtime.py` (lines 113-127,
292-297); `.gitignore`.
Compared against: `ops/control-center/server.py`,
`ops/control-center/founder_auth.py`,
`ops/reviews/cto-milestone2b4-architecture.md`,
`ops/reviews/security-milestone2b4-threat-model.md`, DEC-016, DEC-018.

This code was written by the orchestrator directly, without the normal
Architecture / Code Review / Security gates. This is the first security review
it has had.

---

## Verdict

**REJECT** — six required fixes below.

To be clear about proportion, because it matters more than the verdict:
**I found no exploitable vulnerability in this code.** There is no injection,
no XSS, no path traversal, no SQL string-building, no credential exposure, and
no way for agent-authored or Founder-authored text to execute anything. The
implementation quality of the parts I was asked to attack is genuinely high,
and I say so in detail in §2 and §3.

The reject rests on three things a Security gate exists to catch and that no
amount of care inside a single file would have caught:

* the architectural decision this code cites as its own authority
  (**DEC-018**) says the *opposite* of what the code does, on precisely the
  security question at issue (fix 1);
* the second authentication surface is **materially weaker** than the one it
  claims to reuse, including a regression against a control a previous
  Security review recorded as non-negotiable (fix 2);
* the only action in the system that spends money and sends Founder data to
  an external model API writes **no audit row at all**, using constants
  defined for exactly that purpose and then never called (fix 3).

Fixes 4-6 are small and concrete. None of the six requires redesigning
anything.

---

## Required fixes

### 1. `DEC-018` is cited as authority for an architecture DEC-018 rejects. BLOCKING.

Three files state, as settled fact, that a separate program on a separate port
is the Founder's own instruction:

* `ops/idea-desk/server.py:4-6` — *"Its own program, on its own port... That
  separateness is the Founder's own instruction (DEC-018)"*
* `ops/idea-desk/pages.py:4` — *"the approved mockup (..., DEC-018)"*
* `ops/control-center/agent_runtime.py:113` — *"TASK-024 slice 2 (DEC-015,
  DEC-018)"*

DEC-018 exists only in the operational database (`decisions.id=23`). Its
`decision` field reads:

> "It is ported into the Control Center as its own section — same login, same
> database, opsdb.py still the sole writer — **not a second app and not a
> second auth path, per DEC-016.**"

and its `options_considered` records, as *rejected*:

> "Keep it a standalone page with browser-only storage (rejected — real ideas
> must survive a browser, and **a second path to the database would undo the
> security posture**)"

DEC-016 (`ops/DECISIONS.md:181`) rejected the same option in the same terms:
*"a second app means a second login and a second path to the database, quietly
undoing the security posture."*

So the security rationale in the code is inverted relative to its own citation.
Two compounding problems:

* **DEC-018 is absent from `ops/DECISIONS.md` entirely** — the file jumps
  DEC-017 (line 188) to DEC-019 (line 198). The git-mirrored record a reviewer
  or the Founder actually reads does not contain the decision at all, and
  DEC-019 itself notes the database and git records now diverge permanently.
  The one decision that would have caught this is the one that never made it
  into the durable store.
* DEC-018 slice 2 specifies dispatch *"through the existing chief_of_staff.py
  and meeting_orchestrator.py machinery"*. `evaluator.py:114` calls
  `agent_runtime.invoke_agent` directly instead. That is the mechanical cause
  of fix 3.

**Required:** either (a) get an explicit Founder decision approving a second
HTTP server and a second session store, recorded in `ops/DECISIONS.md`, and
correct the three source citations to point at it; or (b) fold the Idea Desk
back into the Control Center as DEC-018 actually specifies. Do not leave the
current state, where the code's stated justification contradicts its own
citation. Also: write DEC-018 into `ops/DECISIONS.md`, and audit whether other
database-only decisions are missing from it (DEC-019's tradeoffs section says
that check is "still owed" — this is it coming due).

I am not asserting that a second loopback listener is unacceptable. I am
asserting that it is a security-posture change that has never been decided,
and that the code says it has been.

### 2. The second authentication surface is weaker than the one it reuses. BLOCKING.

`founder_auth` genuinely is imported and not reimplemented
(`server.py:44`, `216`, `288`, `298`) — one scrypt path, one credential file,
one verification function. That part is correct and complete. **Everything
above `founder_auth`, however, was rewritten, and every difference is in the
weaker direction.** Point by point against `ops/control-center/server.py`:

| Control | Control Center | Idea Desk | Verdict |
|---|---|---|---|
| Login throttle | `_LOGIN_LOCK` held across check→verify→increment; 5 attempts then 30s lockout (`server.py:250-254, 683-723`) | **none** (`server.py:296-301`) | **regression** |
| Logout | `POST /api/logout` + `_clear_session_cookie` (`server.py:387, 726-739`) | **none** | **regression** |
| Idle timeout | 1800s | **3600s** (`server.py:54`) | 2× weaker |
| Absolute timeout | 43200s | 43200s | parity |
| `CredentialError` on verify | caught → 503 setup-required (`server.py:695-702`) | **uncaught** (`server.py:298`) | regression |
| Credential tamper detection | mtime baseline + WARNING (`server.py:290-311`) | **none** | regression |
| Socket timeout | `Handler.timeout = 10` (`server.py:316`) | **none** | regression |
| Cookie flags | `HttpOnly; SameSite=Strict; Path=/` | identical (`server.py:307`) | parity |
| CSRF | per-process `SESSION_TOKEN`, `compare_digest` | identical (`server.py:201`) | parity |
| Fail-closed ordering | credential gate first, then session | identical (`server.py:216-224, 288-314`) | parity |
| `X-Content-Type-Options`, `Referrer-Policy` | absent | **present** (`server.py:158-159`) | **better** |

The two I consider blocking:

**2a. No login throttle.** `ops/reviews/security-milestone2b4-threat-model.md`
condition C1 required `_LOGIN_LOCK` across the whole critical section and was
recorded as non-negotiable; `ops/control-center/server.py:666-679` documents it
as such. Port 8421 reintroduces the exact condition C1 closed: unlimited
passphrase attempts against the same credential, and unbounded concurrent
~128 MiB scrypt derivations (`founder_auth.py:60-67`), on a
`ThreadingHTTPServer` with no bound. Against a same-UID attacker this adds
nothing — they can read the credential file directly. Against a *different*
local UID it is the whole control. I checked the obvious candidate:
`launch_developer_sandboxed.sh:242` uses `--unshare-all`, so the sandboxed
`ai-developer` process has no network namespace and cannot reach 8421 —
credit where due. But that is one containment path, not a general one, and a
control a Security review called non-negotiable should not be silently dropped
by a second copy of the same login route.
**Fix:** hoist the throttle into a shared module (it does not belong in either
`server.py`) and use it in both, or import the Control Center's directly.

**2b. No logout, and two independent session stores.** `SESSIONS` in
`ops/idea-desk/server.py:66` is a different dict from `SESSIONS` in
`ops/control-center/server.py:245`. One passphrase, two sessions, and only one
of them can be ended. Signing out of the Control Center leaves a valid Idea
Desk session alive for up to 12 hours with no way to revoke it short of
killing the process — and the Idea Desk never tells the Founder that. For a
Founder who reasonably believes "one passphrase, one sign-out", that is a
session-management defect, not a cosmetic gap.
**Fix:** add `POST /api/logout` mirroring `_handle_logout`, and say plainly in
`ops/idea-desk/README.md` that the two sessions are independent.

**2c (fold into 2, non-blocking on its own):** catch `CredentialError` around
`verify_passphrase` and return 503 as the Control Center does; set
`Handler.timeout`; bring `IDLE_TIMEOUT_S` to 1800; add the credential-mtime
check.

**On attack surface:** a second loopback listener roughly doubles the
pre-authentication reachable surface for any local process that is not the
Founder — one more port, one more login route, one more unauthenticated
`GET /login` that hands out `SESSION_TOKEN`. Serving the CSRF token
pre-authentication is parity with the Control Center and is not itself a hole
(`SameSite=Strict` plus the same-origin read barrier close the browser-driven
paths, including framing/clickjacking of the money-spending button). The
increment is real but modest; the throttle regression is what makes it matter.

### 3. The one action that spends money writes no audit row. BLOCKING.

`agent_runtime.py:122-123` defines `IDEA_EVALUATION_ACTIVITY_LABEL` and
`IDEA_EVALUATION_ACTIVITY_LIKE` in the file's own established LABEL/LIKE-pair
convention. **Neither is referenced anywhere in the repository.** `evaluator.py`
never calls `start_run`/`run-start`/`run-end`, and creates no `agent_runs` row.

Consequence: up to six real `claude` invocations per evaluation — each capped
at `MAX_BUDGET_USD` individually, none of them counted — are invisible to
`/costs.html`, to the per-path breakdown, and to startup reconciliation. The
one action in the Idea Desk that spends real money and ships the Founder's
idea text to an external model API is the one action with no record that it
happened. Every other invocation category in this system
(Ask-Agent, meetings, Chief of Staff, automated review, synchronous review)
writes one.
**Fix:** wrap `evaluator._invoke` in the same `start_run`/`end_run` pairing the
other categories use, with `IDEA_EVALUATION_ACTIVITY_LABEL`, so the constants
that were written for this are actually used.

### 4. Founder-supplied and agent-supplied argv values break on a leading dash. Required, low severity.

I confirmed what I was asked to confirm: **there is no shell anywhere.** Every
invocation is `subprocess.run([sys.executable, str(OPSDB), *args])` with a list
argv and no `shell=True` — `server.py:137`, `evaluator.py:84`,
`server.py:432`, `seed_founder_idea.py:248`. `agent_runtime._run_claude`
(`agent_runtime.py:322-351`) likewise builds a list, passes the transcript as
a single `-p` element, and adds `cwd=_REPO_ROOT` and `stdin=DEVNULL` — neither
introduces any new injection surface; `cwd` is a fixed constant and `DEVNULL`
removes a stdin path rather than adding one.

**There is also no argument injection.** I traced every dashed value:
argparse classifies a token that begins with `-`, contains no space, and is not
a negative number as an *option*, so `--raw` followed by `--confirm-founder-decision`
raises "expected one argument" — it never slides into a different flag. Values
that could be attacker-influenced are all either validated
(`--how` against `("parked","dropped")`, `--round-id`/`--idea-id` via
`isdigit()` and `type=int`, `--recommendation` via argparse `choices`) or are
single argv elements that argparse refuses rather than reinterprets.

But the same behaviour is a real defect. A Founder idea beginning with a dash —
`"-simplify the UI"`, `"--the dashboard is too verbose"` — makes
`idea-create` fail with a raw argparse usage string rendered as a 409
(`server.py:333, 337`). Worse, on the evaluation path the model-authored
`--depth-reason` / `--title` / `--changed-note` values (`evaluator.py:432-445`)
hit the same rule, so a value starting with `--` discards a completed
evaluation **after the money has been spent**. A prompt-injected idea could
aim for exactly that.
**Fix:** use the `--flag=value` form (`f"--title={title}"`), which argparse
parses as a value regardless of leading dashes, at every one of these call
sites in `server.py:333-336, 353-356, 365-367` and `evaluator.py:432-445`.

### 5. Unvalidated value reaches a `Location:` header. Required, low severity.

`server.py:338-339`:

```python
new_id = out.rsplit("id=", 1)[-1].strip()
self._redirect(f"/idea/{new_id}")
```

`http.server`'s `send_header` performs **no CRLF validation** (unlike
`http.client.putheader`), so this is a live response-splitting sink. It is not
currently reachable: `cmd_idea_create` prints exactly `idea created: id=<N>`
(`opsdb.py:1753`) and `.strip()` handles the trailing newline. It becomes
reachable the moment that print format changes or `opsdb.py` emits a warning
line without `id=`. That is one line away.
**Fix:** `if not new_id.isdigit(): raise WriteError(...)` before redirecting.

### 6. Repository hygiene around the operational database. Required, low severity.

The credential itself is clean — see §4 below. The database is not:

* `ops/db/operations.sqlite3` is correctly untracked and gitignored now
  (`.gitignore:10-13`, DEC-019) and is `0600` on disk, re-asserted by
  `cmd_init`'s `chmod` (`opsdb.py:216`) on every Idea Desk start
  (`server.py:432`). Good.
* But it was tracked across **205 commits** and pushed to
  `github.com/Mahadev7B/AI-Pipeline`. `git rm --cached` does not remove the
  historical blobs; the ~1 MB database — including `ideas.raw_idea`, the
  Founder's verbatim words — remains retrievable from every one of those
  commits on the remote. DEC-019 does not mention this.
  **Fix:** confirm the repository's visibility. If it is public, treat the
  history as disclosed and decide explicitly whether that is acceptable; if
  private, record the decision to leave history as-is rather than leaving it
  unexamined.
* `ops/db/ops.db` is a tracked, 0-byte, world-readable file that no code
  writes. **Fix:** delete it and add `ops/db/*.db` to `.gitignore`, so a
  future stray write there is not committed the way `operations.sqlite3` was.
* `opsdb.py:216`'s comment — *"nothing sensitive is stored"* — is now false;
  Artifact 1 is the Founder's own words. **Fix:** correct the comment.

---

## What I attacked and could not break

### §1. `pages.py::safe_html` — sound.

I could not get script execution, an attribute, an event handler, or a URL
through it. Tested directly against the implementation, 23 payloads including
`<script>`, `<img src=x onerror=>`, `<b onclick=>`, `javascript:` URLs,
`<style>`, entity double-encoding (`&lt;script&gt;`), attribute-breakout via
`class="sk&quot; onmouseover=&quot;..."`, unquoted `class=sk`, uppercase
`<BR>`, comment and CDATA openers, and stray-close-tag breakout
(`</div></div></div></main><script>`). Every one came back escaped.

The design is right: `html.escape` runs first over the whole string, and the
only way a `<` reaches the output afterwards is through one of four
*rewrite* rules whose replacement strings are constants — `<b>`, `</b>`,
`<div class="sk">`, `<span class="lab unk">`, `<div>`, `</div>`, `</span>`.
Attacker text can never appear inside a tag, only between tags. The regexes
are correctly bounded (`\s*/?&gt;` after the tag name; the entity-quoted class
name pinned on both sides), so no partial or overlapping match escapes. Input
already containing `&lt;` becomes `&amp;lt;` and cannot be revived. The
div-balancing loop then makes structural breakout impossible: excess `</div>`
at depth 0 are dropped, and unclosed `<div>`s are closed at the end. Both
call sites (`pages.py:517, 520`) place the output in element content, never in
an attribute.

Two residual issues, **hardening only, not blocking**:

* `<b>`, `<i>`, `<em>`, `<strong>` are **not** balanced — only `<div>` is.
  `<b/>` normalises to `<b>`, so agent text can leave bold or italic leaking
  into the rest of the page. Cosmetic defacement by our own agent; no script.
  Apply the same balancing to the inline tags.
* `</span>` is unescaped but no `<span>`-without-class can be produced, so a
  stray `</span>` could close a container span the fragment did not open. At
  both current call sites the container is a `<div>`, so nothing breaks today.
  Drop the `</span>` rewrite unless a matching opener is actually emitted.

### §2. The Founder's own idea text — escaped everywhere. Confirmed.

I checked every surface that renders `raw_idea`, `current_raw`,
`idea_edits.raw_idea`, `audience`, `trigger_note`, `title`, `close_reason`,
`founder_note` and `last_error`:

* list (`list_page:330-333`) — escaped, including the truncated preview;
* new/edit form (`new_page:356-358`) — escaped, and `audience`/`trigger` land
  in `value="..."` attributes where `html.escape`'s `quote=True` correctly
  handles `"` and `'`;
* idea detail (`idea_page:542, 547, 555, 558-560, 568-570, 579`) — escaped;
* **history** (`_history:397-417`) — escaped, every branch including edits,
  corrections and close reasons;
* **evaluating page** (`evaluating_page:448-464`) — escaped, including the
  crumb and the in-memory progress steps;
* draft page (`_draft_page:606, 619-627`) — escaped.

No stored XSS. Agent-authored view/roster fields go through `e()` rather than
`safe_html` (`_company_view:431-437`, `idea_page:526-535`), which is stricter
than necessary and correct.

One footgun worth closing as hardening: `error_page`'s `detail` parameter
(`pages.py:311`), `idea_page`/`_draft_page`'s `flash` (`494, 539, 602`) and
`shell`'s `crumb` (`273`) are interpolated **unescaped**. Every current caller
passes either a literal or `pages.e(str(exc))` — I checked all 17 in
`server.py` — so nothing is wrong today. Rename them (`detail_html`,
`flash_html`, `crumb_html`) so the contract is visible at the call site.

### §3. Subprocess handling — clean.

Covered under fix 4. Summary: no shell, no argument injection, no way for
Founder or agent text to become a flag. The transcripts to `claude` are passed
as one `-p` argv element and are never shell-interpreted.

### §4. The credential — untouched. Confirmed.

* Nothing in `ops/idea-desk/` reads, opens, copies or logs
  `.founder_credential.json`. The only references are
  `founder_auth.credential_exists()` (`server.py:216, 288, 445`), which is a
  bare `Path.exists()` (`founder_auth.py:109-110`), and
  `verify_passphrase()` (`server.py:298`), which returns a bool and never
  echoes its input.
* `doctor.py:111-113` reports the credential's **existence only** — `"yes"` or
  `"NO — run founder_auth.py setup"`. It never opens the file.
* Gitignored by `ops/control-center/.founder_credential*` (`.gitignore:30`),
  which also covers `_write_credential_atomic_replace`'s temp-file stem.
  Confirmed: `git ls-files` matches nothing.

**The failed-login path specifically** (`server.py:296-301`):

```python
passphrase = fields.get("passphrase", [""])[0]
if not passphrase or not founder_auth.verify_passphrase(passphrase):
    self.log_message("failed sign-in attempt")
```

The passphrase is bound to a local, passed to `verify_passphrase`, and the log
line is a fixed string containing no interpolation. No passphrase can reach a
log. The one uncaught exception on this path (`CredentialError`, fix 2c) would
print a traceback naming the *file path*, never its contents or the submitted
passphrase — `founder_auth.py:125` interpolates only the exception. Confirmed
safe, and it still fails closed: no session is created.

### §5. Prompt injection via idea text — honestly, very little. One thing to watch.

Founder idea text is interpolated into three prompts through `_idea_block`
(`evaluator.py:127-147`). The ceiling is genuinely low, and for the right
reasons:

* `--tools ""` and `--strict-mcp-config` with no `--mcp-config`
  (`agent_runtime.py:325-327`) mean the agent has no Bash, no Read, no Write,
  no Fetch and no MCP. It can only emit text. The Idea Desk adds no flags to
  this and inherits it unchanged.
* **The model cannot widen its own roster.** `_select_roster:214` filters every
  model-returned role name against the hardcoded `SELECTABLE` tuple before it
  is ever used, then truncates to `MAX_PERSPECTIVES`. `_perspective` is only
  ever called with a survivor of that filter, and the two Chief-of-Staff calls
  pass a literal `"orchestrator"`. So model-controlled strings never reach
  `invoke_agent` as an agent name. This is the single most important thing to
  have got right here, and it is right.
* Output is validated: `rec` against `VALID_RECS`, `opp` against four values,
  all ten answers required, JSON parsed rather than eval'd
  (`_validate:383-407`). Rendering is `safe_html`, which holds (§1).
* Cost is bounded per call by `MAX_BUDGET_USD` and concurrency by
  `MAX_CONCURRENT_INVOCATIONS`.

So the honest answer is "very little" — **today**. Two paths worth naming:

* **Worth closing now:** an injected instruction that makes the model emit a
  `--`-prefixed `title`/`depth_reason`/`changed` value destroys the completed
  evaluation at the `opsdb.py` boundary, after payment. Fix 4 closes it.
* **Worth watching, not blocking:** the Founder's own rule is that there is no
  approve-anyway path — Approve appears only when the company's recommendation
  is Proceed (`opsdb.py:1839-1843`, enforced in the database, correctly, not
  just in the page). That recommendation is a model output derived from text
  the Founder typed. An idea that instructs the evaluation to return "Proceed"
  can unlock its own Approve button. Today that is self-inflicted and the
  Founder still has to click. **When slice 3 lands `Start work`
  (`server.py:402-411`, currently a deliberate 501), this becomes a path from
  "text the Founder pasted" to "real work created", and the Founder's click is
  the only remaining gate.** Slice 3 needs its own review with this
  specifically in scope; it does not block slices 1 and 2.

### §6. Data at rest and in transit.

* **Database file:** `0600`, owner-only, re-asserted on every start
  (`opsdb.py:216` via `server.py:432`). The Idea Desk opens it strictly
  read-only (`server.py:74`, `mode=ro` URI) and every write goes through
  `opsdb.py` — the sole-writer claim in the docstring is true and I verified
  it: there is no `sqlite3.connect` in `ops/idea-desk/` without `mode=ro`.
  All SQL in the TASK-024 section is parameterized; the one f-string
  (`opsdb.py:1812`) interpolates only fixed literals from a constant list,
  with the title bound as a parameter. No SQL injection.
  *Hardening:* `journal_mode` is `delete`, and the transient
  `operations.sqlite3-journal` is created at umask default (0644), not 0600 —
  it holds pre-image pages including idea text. Negligible on a single-user
  box; worth one line if the threat model ever includes a second local user.
* **In transit:** plain HTTP on 127.0.0.1. Correct for this tool — TLS on
  loopback would add a certificate-management burden and no real confidentiality
  against an attacker who can already read loopback traffic (they can read the
  process memory too). Not a finding. Neither server validates the `Host`
  header, so a DNS-rebinding page can reach `GET /login`; it cannot obtain a
  session, because cookies are keyed to `127.0.0.1` and the rebound document
  is not. Parity with the Control Center, worth adding to both as hardening,
  blocking on neither.
* **`doctor.py`:** discloses nothing it should not. It prints absolute paths,
  branch name, commit subject, a count of dirty files, the build stamp,
  `shutil.which("claude")`, and three existence booleans. It fetches
  `/login` (`doctor.py:88`) but only substring-matches the response and never
  prints the body. No credential content, no database content, no idea text.
  The Founder is told to paste the output, which discloses their username via
  the absolute paths — acceptable for a diagnostic; note it in the script's
  docstring so the Founder knows what they are pasting.
  *Separate defect:* the target branch is hardcoded at `doctor.py:55-59` and
  will mislead on any other branch.

---

## Non-blocking hardening (no fix required to pass, but recommended)

1. Balance inline tags in `safe_html`, and drop the unmatched `</span>` rewrite (§1).
2. Rename `error_page(detail)`, `flash`, and `shell(crumb)` to `*_html` so the unescaped contract is visible (§2).
3. Validate the `Host` header on both servers; add `Content-Security-Policy: default-src 'self'; script-src 'none'` — the pages contain no JavaScript at all, so this costs nothing.
4. Add startup reconciliation for `ideas.evaluating_since`. `run_evaluation` clears it in a `finally` (`evaluator.py:455-463`), but the thread is a daemon: Ctrl-C or a crash mid-evaluation leaves the idea permanently displaying "the company is considering your idea", with no route in the UI to clear it. The Control Center has `_reconcile_orphaned_runs()` (`server.py:1297, 1389`) for exactly this class; the Idea Desk has nothing. This wedges the money-spending gate in a state the Founder cannot exit — the same category of "restart appears to work but nothing changed" confusion DEC-019 was written about.
5. `agent_runtime.py:116-119`'s comment claims a separate allowlist means "an idea evaluation must never be able to widen what a meeting can invoke". `invoke_agent:292-297` actually tests the **union** of all six allowlists, so adding `design` did widen that gate. The property still holds — but because `server.py:983, 1049, 1116` re-check `MEETING_PARTICIPANT_ALLOWLIST` at each call site, not because of anything `invoke_agent` does. Correct the comment to describe the mechanism that is actually load-bearing, or move the enforcement into `invoke_agent` via a category parameter.
6. Chmod the SQLite journal sidecar, or switch to WAL and chmod both (§6).
7. Fix `doctor.py`'s hardcoded branch name.

---

## Recording

Recorded as `review-result --type security --by security --result reject
--returned-to developer` against task id=24.
