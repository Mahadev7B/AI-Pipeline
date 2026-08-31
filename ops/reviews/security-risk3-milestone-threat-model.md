# Security threat model — risks.id=3 milestone architecture (TASK-017, SECURITY_REVIEW stage)

Reviewing `ops/reviews/cto-risk3-milestone-architecture.md` (CTO's concrete
design for the Founder-authorized narrow slice, Appendix E of
`ops/reviews/chief-of-staff-risk3-synthesis.md`). Read in full before
writing this document: the CTO document; the synthesis/authorization
document; my own prior threat model
(`ops/reviews/security-risk3-threat-model.md`, S1-S7); Red Team's prior
challenge (`ops/reviews/red-team-risk3-challenge.md`, S8);
`ops/control-center/agent_runtime.py`, `ops/control-center/automation.py`,
`ops/control-center/server.py`, `ops/db/opsdb.py`, `ops/db/schema.sql`, all
relevant `.claude/agents/*.md` files, `ops/skills/operations/update-config.md`,
`ops/skills/operations/fewer-permission-prompts.md`, and — independently,
not on CTO's word — the installed Claude Code CLI source
(`/opt/node22/lib/node_modules/@anthropic-ai/claude-code/cli.js`, v2.1.42,
matching the version CTO and I both cite) for the per-subagent `hooks:`
scoping question. Design-review only; nothing in `ops/` or product code is
touched by writing this document.

**Verdict: CONCERNS.** The core mechanism claims are sound and I
independently re-derive the load-bearing ones rather than take CTO's word
— they hold up completely under direct verification. But the document has
one real, material disclosure gap that goes to the exact governance
problem this milestone exists to fix, plus a smaller but concrete
detection-completeness overclaim in the same section. Both are cheap to
fix (disclosure and wording, not new engineering) and should be fixed
before Development builds from this document, not discovered by Red Team
or later found live.

---

## 0. What I independently re-verified, and what I found

### 0.1 Part 1's zero-tool claim — CONFIRMED, not accepted on the document's word

I read `agent_runtime.py` directly rather than trust CTO's framing.
`_run_claude()` (lines 262-332) builds `cmd` with `"--tools", ""` and
`"--strict-mcp-config"` **unconditionally** — the flag list does not
branch on `agent_name` anywhere in the function. `invoke_agent()` is
gated by four explicit, hardcoded allowlists
(`ASK_AGENT_ALLOWLIST`, `MEETING_PARTICIPANT_ALLOWLIST`,
`CHIEF_OF_STAFF_ALLOWLIST`, `AUTOMATED_REVIEW_ALLOWLIST`) — `developer`
is in none of them, and grepping every caller of `invoke_agent(` in
`ops/control-center/` turns up exactly `server.py`, `chief_of_staff.py`,
`automation.py`, `meeting_orchestrator.py` — all Python-only,
HTTP-route-triggered or poller-triggered call sites, never anything a
Task-tool-delegated interactive subagent session touches. CTO's claim
that a human running the `security-review`/`red-team` skill interactively
(via native Task-tool subagent delegation) is a **structurally distinct**
code path from `agent_runtime.invoke_agent()` is correct, and adding
three new callers of `invoke_agent()` genuinely does not touch that
second path at all. **This is the single clearest, best-evidenced claim
in the document, and it holds completely.**

### 0.2 Per-subagent `hooks:` frontmatter scoping — CONFIRMED, independently, not accepted on CTO's citation

This was Red Team's own open question from Stage 3 (TASK-016) and CTO's
document claims to resolve it by reading `cli.js` directly. I did the
same reading independently rather than accept CTO's transcription of the
minified names, and it holds up exactly as claimed:

- The subagent-invocation setup path computes `V=O?.agentId?O.agentId:aR()`
  — a **fresh, per-invocation** id unless one is explicitly threaded
  through (subagent resumption), confirmed by direct inspection of the
  surrounding code (variable `V` feeds both the hook registration call and
  the `toolUseContext`/`agentId` passed to the tool-execution loop that
  follows).
- `if(A.hooks)Oe7(K.setAppState,V,A.hooks,`agent '${A.agentType}'`,!0)` —
  hook registration is keyed by that same per-invocation `V`, and this
  call happens in the subagent's setup sequence, **before** MCP client
  setup (`ByY(...)`) and before the tool-execution loop begins for that
  invocation — there is no window in which a tool call for that
  invocation could fire before its own hooks are registered.
- The read path, `NH6(A,q,K){let Y=A.sessionHooks[q];if(!Y)return new Map;...}`,
  reads `sessionHooks[q]` keyed by the exact same id passed at
  registration time. Two different subagent invocations (e.g. `developer`
  and `qa`, or two `developer` invocations moments apart with no explicit
  `agentId` threaded through) get **distinct** map keys, confirmed by the
  `aR()` fresh-id-generation on the write side.

**Conclusion: CONFIRMED, not "likely."** A `hooks:` block declared in
`.claude/agents/developer.md`'s frontmatter is genuinely registered
against, and enforced against, that specific Developer invocation's own
session identity, and there is no code path here that would apply it
globally or to a differently-typed subagent invocation. CTO's §3 is
accurate. This closes Red Team's Stage 3 open technical question for
real, not by further assumption.

**What I did not fully resolve, matching CTO's own honest flag**: the
exact matcher-string syntax for combining multiple tool names in one hook
entry (e.g. whether `"Write|Edit"` is valid alternation syntax) is not
something I could pin down from a further, time-bounded read of the
matcher-application code — the module is large and the specific
tool-name-to-matcher comparison function is not adjacent to the
registration/lookup functions I traced above. CTO's own document already
treats this as open and requires Development to empirically confirm it
(§2.1/§3.3) before relying on it. Given the deliberately conservative
choice already made (three separate single-tool-name matcher entries,
not one combined pattern), I have nothing to add here beyond endorsing
that Development's planned empirical test happen before the hook is
trusted in a real Developer session, exactly as specified.

### 0.3 CSRF/session-gate reuse — CONFIRMED as genuine reuse, not a new mechanism

I read `server.py`'s `do_POST()` directly (lines 489-553). The existing
match chain is a literal, growing sequence of
`is_X = not (is_A or is_B or ... ) and path == X_PATH` checks, all
falling through to the same `_require_csrf_token(fields)` call and then
the same `_authenticated_session() is None` check, before any
`_handle_*` dispatch. Three new routes added to this exact chain (as
`/api/automation/stop`/`/start` and `/api/chief-of-staff/ask` were
previously added to it) genuinely inherit the same CSRF+session gate with
zero new code in that gate itself. This is real reuse, not an assertion.

### 0.4 `reviewer_invocations` vs. `automation_events` — CTO's reasoning holds, and I checked for a reintroduced race

I read `automation_events`'s schema definition directly:
`trigger_status_history_id INTEGER NOT NULL UNIQUE REFERENCES
task_status_history(id)` is a real, load-bearing idempotency constraint
tied to a specific status-transition row — there genuinely is no
equivalent row to key a repeatable, human-triggered action against.
CTO's decision to use a distinct table rather than force a human-repeatable
action through that UNIQUE constraint (or silently drop it, which would
be "the same table wearing the same name," not the same guarantee) is
correct.

I checked specifically for a race CTO's design might reintroduce: a
human double-clicking "run security review" (or a browser retry) firing
two concurrent `POST /api/tasks/<id>/review/security` requests. CTO's
design reuses `opsdb.start_ask_agent_run(conn, agent_name,
activity_label, activity_like)` for the `agent_runs` row — I read this
function directly (`opsdb.py` lines 327-378): it opens `BEGIN IMMEDIATE`,
checks for an existing open run matching `(agent_id, activity_like)`, and
raises `ValueError` if one exists, all inside one atomic transaction. If
`REVIEWER_SYNC_ACTIVITY_LIKE` is a single shared pattern (matching this
file's own established one-pattern-per-category convention), reusing this
function means **at most one reviewer-sync invocation of a given role can
be running system-wide at a time** — a genuine, already-hardened guard
against exactly the double-submission race I was checking for. This is a
positive finding: CTO's design does not reintroduce the race Phase 3A's
own Milestone 2B3A review already closed once (the SELECT-then-INSERT
race `start_ask_agent_run` itself was built to fix) — it inherits the fix
by reusing the same hardened function, correctly.

### 0.5 Red Team artifact-path route — checked for credential/DB exposure

I checked whether `POST /api/tasks/<id>/review/red-team`'s
human-supplied `artifact_paths` could be pointed at something sensitive.
`.founder_credential.json` is confirmed gitignored
(`ops/control-center/.founder_credential*` in `.gitignore`) — never
committed, so `_git_show_file(head_sha, path)` against it returns nothing
at any real commit, and the route fails closed with a 400 exactly as
designed, by construction, not by a special-case check. `ops/db/operations.sqlite3`
**is** git-tracked (confirmed via `git ls-files`), so a Founder pointing
this route at it would successfully retrieve the DB file's binary content
into a review transcript — not a security exposure (the Founder already
has full filesystem access, and this is not attacker-reachable, since the
route only accepts input from an authenticated Founder session), but a
minor robustness gap worth a cheap, non-blocking fix: `_git_show_file`
has no "is this decodable as UTF-8 text" check, so a binary artifact path
produces garbled review-transcript content and wasted invocation cost
rather than a clean failure. Not required before ship; worth a one-line
guard if Development has the room.

### 0.6 Part 3 (sqlite3 bypass) disclosure — checked against the schema directly, accurate

I confirmed directly in `ops/db/schema.sql` that `tasks.status` has only
a flat enum `CHECK (status IN (...))`, with no `CHECK`/trigger
constraining which `from_status -> to_status` transitions are legal —
that logic lives only in `opsdb.record_task_status()`'s Python body,
exactly as CTO's §4 discloses. The example given (a raw `sqlite3` write
could set `tasks.status` to any enum value in any order, skipping the
state machine) is accurate, not overstated. The disclosure that this is
"Developer-only, pattern-bypassable, doesn't cover Python-only
invariants" matches what I independently found. I don't think the partial
fix creates a false sense of security **as disclosed** — CTO's own §4
text is explicit and undiluted about what remains open, in the same style
already established for `risks.id=2`.

---

## 1. Required before Development builds — the material gap

### 1.1 CTO's own native Write/Edit is the same self-widening gap S8 named, and it is completely undisclosed here

I read `.claude/agents/cto.md` directly:
`tools: Read, Grep, Glob, Write, Edit, Bash, Skill`. CTO's role carries
native, unrestricted `Write`/`Edit` today, and nothing in this milestone's
file-by-file change list (§5) adds any hook to `.claude/agents/cto.md`'s
own frontmatter or to any CTO-scoped invocation. Part 2's hook is scoped
**only** to `.claude/agents/developer.md`'s own frontmatter — per §0.2
above (confirmed independently), that means a `cto`-typed subagent
invocation gets **no `sessionHooks` entry at all** from this design; it is
watched by nothing.

This means: in an ordinary, unremarkable supervised session, a `cto`
subagent invocation can `Edit(file_path=".claude/agents/developer.md",
old_string="hooks:\n  PreToolUse:\n...", new_string="")` — removing
Developer's own denylist entirely — or `Write` a modified
`ops/control-center/hooks/developer_pretooluse.py` with the deny checks
stripped out, using its own **native, sanctioned tool grant**, no Bash
trick, no encoding indirection, no shell-parsing evasion required. This
is strictly more direct than the DevOps vector CTO's own §2.5 spends
several paragraphs disclosing (which requires DevOps to use Bash
creatively, since DevOps has no `Write`/`Edit` at all) — and it is the
**exact same finding** Red Team's Stage 3 §3 already made, in these exact
words: *"Developer and CTO are two of the four roles Tier 2 is built to
constrain, and both have a native, unrestricted tool grant capable of
editing the file that constrains them."* CTO's own document quotes this
same Red Team review elsewhere (crediting it for the DevOps half) but
never restates or addresses the CTO half of the identical finding
anywhere in §2.5, §4, or the recommended `risks.id=3` disclosure text.

**Is this a scope violation?** No — CTO tool scoping (building a hook for
`cto.md`) is explicitly out of this milestone's authorized scope, exactly
like DevOps's. I am not asking for a CTO-scoped hook to be built. **Is it
a disclosure gap?** Yes, and a significant one: the Founder's
authorization text (Appendix E, item 2) reads "read-only to Developer
**and DevOps**" — CTO's document treats this as the complete list of
roles with a residual capability and discloses accordingly. But the
authorized text's own goal (closing the self-widening gap S8 found) is
not achieved for a third role with an *even more direct* version of the
identical capability, and that residual gap is currently invisible to
anyone reading this document, `ops/SECURITY.md`, or the eventual
`risks.id=3` mitigation text — none of which mention CTO. This is exactly
the kind of "reads as more closed on paper than it actually is" outcome
this project's own governance discipline (undiluted disclosure,
`risks.id=2`'s precedent, Phase 3A's consequence-increase notes) exists
to prevent, and it is happening inside the very document meant to
demonstrate that discipline.

**Required, before Development builds**: §2.5 and the §4 disclosure text
must name CTO's own native `Write`/`Edit` capability explicitly, alongside
DevOps's Bash capability, as a residual, undisclosed-until-now path to
edit the Developer denylist's own definition — not to fix it (out of
scope), but so the shipped disclosure is honest about who can still
widen the gap. Concretely: the recommended `risks.id=3` mitigation text
in §4 should read "...NOT technically closed against DevOps **or CTO**,
both of whose unrestricted native tool grants (Bash for DevOps, Write/Edit
for CTO) remain sanctioned-by-capability paths to the same files" rather
than naming DevOps alone.

### 1.2 §2.3's "self-immune... completely" framing overclaims relative to §2.2's own disclosed bypass, specifically for the self-protection paths

§2.3 states the hook "closes the loop for Developer specifically,
completely, not merely 'until Developer finds a workaround this review
didn't think of.'" This is true for exactly one property — **registration
timing** (confirmed independently in §0.2 above: no tool call can precede
hook registration within a single invocation) — but §2.2's own text two
paragraphs earlier discloses the Bash check is "explicitly, honestly
disclosed as bypassable... via the exact techniques Security's Stage 2
§2.1 demonstrated." §2.3's "completely" is not reconciled with that
disclosure, and the gap is concretely worse for the self-protection
entries than for the credential/DB entries, for a specific, checkable
reason:

Re-reading §2.2 closely, the Bash check has **two separate mechanisms**:
a **plain substring list** (`founder_credential`, `operations.sqlite3`,
`import sqlite3`, `sqlite3.connect`, `ptrace`, ` gdb`, ` strace`, `sudo `)
and a **narrower, command-anchored path-token check** ("references
`.claude/agents/developer.md`, `ops/control-center/hooks/developer_pretooluse.py`,
`.claude/settings.json`, or `.claude/settings.local.json` as an apparent
path argument (e.g. to `cat >`, `sed -i`, `>`, `>>`, `cp`, `mv`, `rm`)").
**The four self-protection paths are only covered by the second,
narrower mechanism — they are not in the plain substring list at all.**
That narrower mechanism is explicitly anchored to specific known
write/redirect commands. A command that reaches the same file through a
different interpreter is not "an apparent path argument to `cat >`,
`sed -i`, `>`, `>>`, `cp`, `mv`, `rm`" in any sense a pattern check
anchored to those specific commands would recognize — for example:

```
Bash(command="python3 -c \"p='.claude/agents/developer.md'; d=open(p).read(); open(p,'w').write(d.split('hooks:')[0]+'---\n'+d.split('---',2)[2])\"")
```

This is a plain `python3 -c` invocation using `open()`/`write()` — not
`cat`, `sed`, `cp`, `mv`, or `rm` — that reads and rewrites
`.claude/agents/developer.md` to strip its own `hooks:` block. It
requires no base64/heredoc encoding at all (the simpler bypass class
CTO's document already discloses) — it only requires **not typing one of
six specific command names** the path-token check is anchored to. This
is a strictly cheaper bypass than the encoding-indirection class already
disclosed, and it is not currently named anywhere in the document as
applying specifically to the four self-protection paths.

I want to be precise about why this matters more here than it would for,
say, the credential-file entry: Security's own prior Stage 2 finding
(§2.2, which CTO's document correctly cites and adopts) is that
Write/Edit's typed `file_path` field is the *strong* defense and Bash's
string matching is the *weak* backstop. A rational adversarial Developer
choosing how to edit its own denylist would not use `Edit`/`Write`
(caught reliably by `.resolve()`-based containment) — it would
deliberately route through Bash specifically **because** the design's own
disclosed asymmetry makes Bash the weaker check, and the self-protection
paths are exactly where an adversarial Developer's only goal (remove the
constraint on itself) would concentrate. §2.3's "completely" framing,
read next to this, risks leaving a reader with the impression that the
self-protection is closed to the same degree the registration-timing
argument is — when it is not.

**Required, before Development builds**: (a) reword §2.3 to state plainly
that continuous self-protection is proven for **registration timing**
only (a real, harness-enforced, independently-verified property), not for
**detection completeness** against a Bash-routed edit of the same four
files, which remains exactly as bypassable as every other Bash-string
check in this design, and give the concrete example above (or an
equivalent) so this isn't left as an abstract caveat contradicted by the
section's own wording two paragraphs earlier; (b) add the four
self-protection paths to the plain-substring list (§2.2's first bullet),
not only the narrower command-anchored check — cheap, and it closes the
"just don't type `cat`/`sed`/`cp`/`mv`/`rm`" case specifically, while
still (honestly) remaining bypassable by the same base64/heredoc
indirection already disclosed for everything else in this hook. This
doesn't change the design's shape, only its completeness and its own
internal honesty about what it actually closes.

---

## 2. Where the document is correct and should ship as designed

- **Part 1's structural carve-out** (§1.2 of CTO's doc): confirmed by
  independent code+CLI-source reading (§0.1-§0.2 above), not merely
  plausible. Security's own S3 condition from the prior investigation
  stage is genuinely satisfied by construction here, not by a documented
  norm.
- **CSRF/session reuse** (Red Team's prior gap (a)): confirmed genuine
  reuse of the existing, already-hardened mechanism (§0.3). This fully
  closes gap (a) for the design as written, contingent only on
  Development actually extending the existing `do_POST()` chain rather
  than inventing a parallel dispatch path — a build-fidelity point for
  Code Review to verify, not a design flaw.
- **`reviewer_invocations` as a distinct table** (Red Team's prior gap
  (b)): the reasoning holds, and reuse of `start_ask_agent_run()` means
  no double-submission race is reintroduced (§0.4) — a genuine
  improvement over leaving this unaddressed, not a superficial one.
- **Persona-text correction** (Red Team's prior gap (c)): the proposed
  SYNCHRONOUS-mode text is accurate and appropriately scoped; no issue.
- **Part 3's disclosure** (the sqlite3/`opsdb.py` bypass): checked
  directly against `schema.sql` and confirmed accurate and undiluted, not
  overstated. The partial fix (naming `operations.sqlite3` and raw-sqlite
  patterns in the Developer denylist) is worth shipping — it measurably
  raises the bar for the realistic case (scope creep, non-adversarial
  mistake) this project's own threat model already treats as the primary
  target, and the disclosure of what remains open is honest, not
  overclaimed.
- **Red Team artifact-path route**: fails closed correctly against the
  one sensitive path that matters (the credential file, confirmed
  gitignored); the `operations.sqlite3` binary-content case (§0.5) is a
  minor robustness note, not a security finding, and not blocking.

---

## 3. Scope discipline — checked against Appendix E

I checked the design against the Founder's exact authorization text
(Appendix E) line by line:

- **Item 1** (reviewer zero-tool rollout with a Security/Red-Team
  own-work carve-out): matches, and the carve-out is structurally real
  (§0.1-§0.2).
- **Item 2** (Developer denylist, read-only to Developer and DevOps):
  matches for Developer (confirmed self-protecting, modulo §1.2's
  detection-completeness note); the DevOps half is honestly disclosed as
  only partially closeable, which is itself squarely what the
  authorization's own "explicitly NOT authorized: ...DevOps tool
  scoping" text requires — CTO correctly threads this needle (closes the
  *documented*-sanction half via the two skill-doc edits, discloses
  rather than claims to close the *technical*-capability half). §1.1
  above is about this same item's disclosure being incomplete for a third
  role, not about the DevOps handling itself being wrong.
- **Item 3** (resolve or re-disclose the sqlite3 vector): matches, per
  §0.6 above.
- **Explicitly-excluded scope** (QA/CTO/DevOps tool *scoping*; any change
  to Founder-facing routes/authentication/CSRF; deployment gating): no
  QA/CTO/DevOps tool scoping is proposed anywhere in this document — the
  two skill-doc edits are documentation-only, not a tool-grant or hook
  change, and are consistent with the authorization's own "no sanctioned
  path... to edit its own constraint" wording for item 2. No deployment-
  gating change appears anywhere in the design.

**One genuine interpretive question worth an explicit sentence, not a
blocking redesign**: the authorization's exclusion list also reads "any
change to Founder-facing routes or authentication" as not authorized, and
this design adds three brand-new Founder-facing HTTP routes plus new
`/reviews.html` form entry points. CTO's document (§1.3) argues this is
reuse of the existing auth/CSRF *mechanism*, not a change *to* it, and I
find that reading persuasive — Phase 3A's own precedent
(`/api/chief-of-staff/ask`, `/api/automation/stop`/`start`) added new
routes under the identical framing without anyone treating that as
"changing Founder-facing routes," and item 1's own text ("human-triggered
invocations") requires *some* mechanism for a human to trigger this,
which in this codebase's existing architecture is necessarily an HTTP
route. I am not requiring a redesign here, but Red Team and, if either of
us remains unsure, the Founder should see one explicit confirming
sentence that "new route, same mechanism" was the intended reading of
that exclusion before Development builds three new routes against it.

---

## 4. Summary of required changes before Development builds

1. **(Required)** §2.5 and the §4 `risks.id=3` disclosure text must name
   CTO's own native `Write`/`Edit` grant, not only DevOps's Bash grant, as
   a residual, sanctioned-by-tool-grant path to edit the Developer
   denylist's own definition (`.claude/agents/developer.md`'s `hooks:`
   block or `developer_pretooluse.py` itself) — disclosure only, no new
   hook required, staying within scope (§1.1).
2. **(Required)** Reconcile §2.3's "closes the loop... completely"
   framing with §2.2's own disclosed Bash-bypass limitation, specifically
   for the four self-protection paths: state plainly that only
   registration *timing* is fully closed, not bypass *detection*: add the
   four self-protection paths to the plain-substring Bash check (§2.2
   first bullet), not only the narrower command-anchored check, and note
   the `python3 -c` bypass class explicitly (§1.2).
3. **(Non-blocking, worth doing if cheap)** A minimal "fails closed on
   non-UTF-8 content" guard for the Red Team artifact-path route, so a
   `operations.sqlite3`-as-artifact-path request produces a clean error
   rather than binary garbage in a review transcript (§0.5).
4. **(Non-blocking, worth one sentence)** Explicit confirmation — from
   Red Team and/or the Founder — that "reuse of the existing CSRF/session
   mechanism via new routes" was the intended reading of the
   authorization's "no change to Founder-facing routes" exclusion (§3).

None of these require reworking the two-tier shape, the reviewer
zero-tool rollout, or the Developer-denylist mechanism itself. Items 1-2
are disclosure/wording fixes plus one cheap denylist addition — not new
engineering, not a scope expansion, and squarely achievable before
Development starts building. This document is written for Red Team's
next review; both my endorsements above (§2) and my required changes
(§1, §4) should be treated as open to Red Team's own challenge, not as
settled.
