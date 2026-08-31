# CTO architecture — risks.id=3 reduction milestone (TASK-017, Stage 1 of 8)

Authorized scope: Appendix E of `ops/reviews/chief-of-staff-risk3-synthesis.md`
(the Founder-approved authorization prompt), read in full before writing
this document, along with `ops/reviews/cto-risk3-architecture-investigation.md`
(Stage 1 of TASK-016), `ops/reviews/security-risk3-threat-model.md` (Stage 2),
`ops/reviews/red-team-risk3-challenge.md` (Stage 3), `ops/control-center/agent_runtime.py`,
`ops/control-center/automation.py`, `ops/control-center/chief_of_staff.py`,
`ops/control-center/server.py`, `ops/db/schema.sql`, `ops/db/opsdb.py`,
all 14 `.claude/agents/*.md`, `ops/skills/operations/update-config.md`,
`ops/skills/operations/fewer-permission-prompts.md`, and — independently —
the installed Claude Code CLI source
(`/opt/node22/lib/node_modules/@anthropic-ai/claude-code/cli.js`) for the
one open technical question (see §3.4).

This is a **design document only**. Nothing in `ops/` or product code is
touched by writing it. Development builds from it after Security and Red
Team review it. Three named things are explicitly out of this milestone's
authorized scope — QA/CTO/DevOps tool scoping, any Founder-facing
route/auth/CSRF change, any deployment-gating change — and one real
conflict between the letter of the Founder's authorization and that
scope boundary is surfaced explicitly in §2.5 rather than quietly
resolved by expanding scope.

---

## 0. What changed since TASK-016's three-stage review

Nothing about the two-tier *shape* changes. What this document adds,
directly answering the conditions S1–S8 and the three named gaps in
CTO's originally-sketched first step:

1. **The Tier 1 "carve-out" is not a new invocation mode to build — it's
   an existing separation this codebase already has, simply never named
   as the answer.** See §1.2. This resolves Security's S3 and Red Team's
   "not hand-waved" requirement without inventing new machinery.
2. **The per-subagent `hooks:` frontmatter scoping question Red Team
   flagged as unresolved is now resolved, by direct evidence from the
   installed CLI source**, not by further assumption. See §3.4.
3. **The Developer denylist's own configuration is made self-immune to
   Developer**, and the DevOps half of that same requirement is only
   partially closeable within this milestone's scope — disclosed as a
   named scope conflict, not silently narrowed. See §2.5.
4. **The raw-`sqlite3`-bypasses-`opsdb.py` vector** gets the cheap,
   in-scope part of a fix (added to the Developer denylist) and an
   undiluted disclosure of what remains open, matching this project's own
   `risks.id=2`/Phase 3A disclosure convention. See §4.
5. **CSRF/session boundary, audit record, and persona text** — Red Team's
   three named gaps on the synchronous Code Review path — are resolved
   concretely in §1.3–§1.5, and generalized to the Security/Red Team
   synchronous paths added by this milestone.

---

## 1. Part 1 — Reviewer zero-tool rollout, with the carve-out made structural

### 1.1 What Phase 3A actually proved, re-read precisely

`agent_runtime._run_claude()` passes `--tools "" --strict-mcp-config`
**unconditionally**, regardless of the target agent's own `.claude/agents/
<name>.md` `tools:` frontmatter. This is not a hedge — it is why
`code-review`'s automated invocation is genuinely zero-tool *today*, even
though `code-review.md`'s `tools:` line still reads `Read, Grep, Glob,
Bash, Skill` unchanged. The zero-tool property has never come from the
frontmatter; it comes entirely from *which invocation mechanism is used*:

- `agent_runtime.invoke_agent()` (used by Ask-Agent, Executive Meetings,
  Chief of Staff, and `automation.py`'s poller) → always `--tools ""`,
  no exceptions, not caller-configurable.
- Native Claude Code Task-tool subagent delegation, invoked inline within
  an interactive session a human is watching (how a human runs the
  `code-review`/`security-review` skill today, and how this very
  architecture document's own review by Security and Red Team will
  happen) → uses the subagent's own `tools:` frontmatter as declared,
  unmodified by anything in this project's Python code.

**This means CTO's Stage-1 §3.1 wording ("drop `Bash, Grep, Glob` from
`code-review`'s `tools:` frontmatter entirely for this path") was
imprecise and should not be built as written.** Stripping tools from the
frontmatter would affect *both* invocation mechanisms at once, because
there is only one `tools:` line per agent identity — which is exactly the
ambiguity Security's S3 and Red Team's own review pushed back on. The
corrected design in this document touches the frontmatter `tools:` line
of `code-review.md`, `security.md`, and `red-team.md` **not at all**.

### 1.2 The carve-out, stated as a structural fact, not a policy

**Security's S3 requirement — "Tier 1's zero-tool scoping for Security
and Red Team must be bounded to diff-scoped gate reviews, not their
investigative/architecture-review work" — is satisfied by construction,
not by a documented norm a model is trusted to honor:**

- The new synchronous gate-review routes (§1.3) call
  `agent_runtime.invoke_agent()` exclusively. They are the *only* new
  code path this milestone adds, and they are zero-tool unconditionally,
  the same way Automated Code Review already is.
- Security's and Red Team's **existing** interactive/Task-tool-delegated
  sessions — used for threat models, adversarial architecture review,
  cross-referencing a claim against installed software or live DB state
  (exactly the work Security's own Stage 2 review of CTO's Stage 1 doc
  did, and exactly the work this document's own upcoming Security/Red
  Team review will do) — are **a different code path that never calls
  `agent_runtime.invoke_agent()`**, and this milestone changes nothing
  about it: no frontmatter edit, no new hook, no new restriction.

There is no flag, mode switch, or "deep investigation" trigger to design
or build. The carve-out is: *the two paths already don't share a
mechanism, so leaving one alone while adding a new use of the other is
not a special case — it's just not touching the first one.* This is
checkable directly: Security and Red Team's next review of this document
will itself be an ordinary interactive/Task-tool session, with the exact
same tool access it has always had, because nothing in this milestone
touches `security.md`/`red-team.md`'s `tools:` line.

### 1.3 The three new synchronous routes

Three new POST routes, added to `server.py`'s existing `do_POST()`
dispatch chain — the *same* chain `/api/automation/stop`/`start` and
`/api/chief-of-staff/ask` already go through:

- `POST /api/tasks/<id>/review/code` — synchronous, zero-tool Code
  Review, human-triggered, at the `CODE_REVIEW` gate.
- `POST /api/tasks/<id>/review/security` — synchronous, zero-tool
  Security review, human-triggered, at the `SECURITY_REVIEW` gate.
- `POST /api/tasks/<id>/review/red-team` — synchronous, zero-tool Red
  Team review, human-triggered, at the `RED_TEAM_REVIEW` gate, against a
  named, already-committed artifact (an architecture doc, not a code
  diff — see §1.3.3).

**Red Team gap (a), resolved — CSRF/session boundary**: these three
routes reuse the **existing** CSRF-token + Founder-session mechanism
**unchanged**. Concretely: they are added into `do_POST()`'s existing
match chain (the same `is_login`/`is_logout`/`m_decide`/... pattern every
route already uses), so they pass through `self._require_csrf_token(fields)`
and `self._authenticated_session() is None` exactly as every other write
route does today — no new auth code, no new session concept, nothing
touching `SESSION_TOKEN`, cookies, or login. This is squarely **in
scope**: it is reuse of an existing, already-reviewed mechanism, not a
change to it. (Had a new auth mechanism been needed, that would have been
a scope conflict per the Founder's explicit "no change to Founder-facing
HTTP routes, session auth, or CSRF" boundary — it is not needed here.)

#### 1.3.1 Code Review and Security — SHA-anchored, reusing the exact hardened primitives

Both reuse the *same* transcript-assembly primitives Phase 3A already
built and Security's Stage 2 §1.1 independently verified line-by-line
(`_SHA_RE`, `_commit_exists`, `_validate_repo_path`, `_git_diff`,
`_git_show_file`) — extracted into a new shared module (see §5, file
list) so "reuse" is a real shared import, not a second, drifting copy.

Both look up the **same** query `automation.py`'s poller already uses:
```sql
SELECT * FROM handoffs WHERE task_id = ? AND from_agent = 'developer'
  AND to_agent = 'code-review' ORDER BY id DESC LIMIT 1
```
— i.e., Security's synchronous review reviews the identical diff Code
Review most recently reviewed for that task, not a new handoff type.
**This is a deliberate, disclosed scope narrowing**: if a later QA-fix
cycle produces new committed work Security should review separately, that
needs a new handoff type — not built here, not silently assumed away.

**Security's own S4 condition, restated as a hard boundary, not an
implication**: this mode can only review already-committed,
already-handed-off work with real recorded `base_commit_sha`/
`head_commit_sha`. It cannot review a Developer's in-progress,
uncommitted diff. If Development is later tempted to add a live-working-
tree read to make this "more useful," that is **new** surface requiring
its own from-scratch review — not covered by "this is a strict extension
of already-reviewed code."

#### 1.3.2 Concurrency, timeout, cost

Reuses `agent_runtime.MAX_CONCURRENT_INVOCATIONS`'s existing semaphore
(no change) and a renamed constant — `agent_runtime.AUTOMATED_REVIEW_TIMEOUT_S`
becomes `agent_runtime.REVIEW_TIMEOUT_S` (120s), used by *both* the poller
and these new routes, since both need the same "real review plausibly
takes longer than a short Ask-Agent exchange" allowance CTO's Stage 1
already argued for the poller. A synchronous HTTP request blocks the
handling thread for up to 120s — the same disclosed tradeoff Ask-Agent's
own `DEFAULT_TIMEOUT_S` design already accepted, just a larger number for
a genuinely longer real task.

#### 1.3.3 Red Team — artifact-scoped, not diff-scoped

Red Team's actual job at `RED_TEAM_REVIEW` is reviewing a plan/architecture
document (this document, for example), not a code diff between two
commits of application code — there is no `handoffs` row for this stage
today, and inventing a new handoff-with-SHAs convention for CTO's
architecture output is more than this narrow milestone needs.

**Design**: the human triggering `POST /api/tasks/<id>/review/red-team`
supplies one or more repo-relative file paths (form field
`artifact_paths`, comma-separated, capped at 5 entries) — e.g.
`ops/reviews/cto-risk3-milestone-architecture.md`. Each path is validated
with the same `_validate_repo_path()` used everywhere else in this
codebase. The server — never the client — computes
`head_sha = git rev-parse HEAD` at request time (matching this codebase's
own "server computes trusted values, never trusts client input for
anything security-relevant" convention), then retrieves each file's
*committed* content via `_git_show_file(head_sha, path)` — the same
git-object-database read Code Review/Security use, never a working-tree
read. This is human-declared, structured, and computed server-side —
never LLM-inferred — matching the same discipline Security's own §4/§5
review required of `tasks.allowed_paths`.

If the named path doesn't exist at HEAD (not yet committed, or a typo),
the route fails closed with a 400 before any model invocation — no
silent partial review.

### 1.4 Red Team gap (b), resolved — a real audit record for the synchronous path

**Not** a new column on `automation_events`. That table's
`trigger_status_history_id UNIQUE` constraint is a deliberate,
load-bearing *idempotency* guarantee for the poller's "claim exactly once,
unattended" model (RT3's fix in Phase 3A) — a human clicking "run this
review again" after a small fix is a legitimate, repeatable action with
no new `task_status_history` row to key off, so forcing the synchronous
path through the same UNIQUE constraint would either block a legitimate
re-run or require weakening a guarantee Red Team's own Phase 3A review
required be strict. Reusing the table's *shape* while dropping its one
load-bearing constraint is not "the same audit record" — it is a
different table wearing the same name. So: a new, small, structurally
distinct table, matching Red Team's own "an equivalent" framing:

```sql
CREATE TABLE IF NOT EXISTS reviewer_invocations (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id           INTEGER NOT NULL REFERENCES tasks(id),
  review_kind       TEXT NOT NULL CHECK (review_kind IN ('code','security','red-team')),
  reviewed_by_agent TEXT NOT NULL,             -- 'code-review' | 'security' | 'red-team'
  triggered_by      TEXT NOT NULL DEFAULT 'founder',
  status            TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
  outcome           TEXT CHECK (outcome IN ('pass','reject','error',NULL)),
  review_result_id  INTEGER REFERENCES review_results(id),
  agent_run_id      INTEGER REFERENCES agent_runs(id),
  cost_usd          REAL,
  truncated         INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0,1)),
  base_commit_sha   TEXT,        -- code/security kind only
  head_commit_sha   TEXT,        -- all kinds
  artifact_paths    TEXT,        -- json array; red-team kind: the file(s) reviewed
  skip_reason       TEXT,
  started_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviewer_invocations_task ON reviewer_invocations(task_id);
CREATE INDEX IF NOT EXISTS idx_reviewer_invocations_status ON reviewer_invocations(status);
```

`opsdb.py` gets two new functions mirroring `create_automation_event()`/
`end_automation_event()`'s shape exactly (same rowcount-guard,
one-time-only-terminal-write discipline) but without the atomic-claim
logic — `start_reviewer_invocation()` is a plain `INSERT`, not a
`BEGIN IMMEDIATE` claim, because there is nothing to claim against.
This gives Security's S6 periodic-transcript-review discipline one
additional, consistent table to sample for the human-triggered path,
alongside `automation_events` for the poller — the human-triggered path
is no longer invisible to that accounting.

An `agent_runs` row is still started via `opsdb.start_ask_agent_run(conn,
agent_name, agent_runtime.REVIEWER_SYNC_ACTIVITY_LABEL,
agent_runtime.REVIEWER_SYNC_ACTIVITY_LIKE)` — the same generic,
already-hardened function Ask-Agent uses, reused directly, not
reimplemented — so the "one open run" guard and derived-status display
work identically to every other invocation category. **This requires
`server.py`'s `_reconcile_orphaned_runs()` to gain a fourth `LIKE`-pattern
call** (`agent_runtime.REVIEWER_SYNC_ACTIVITY_LIKE`), matching the
existing pattern for `ASK_AGENT_ACTIVITY_LIKE`/`MEETING_ACTIVITY_LIKE`/
`ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE`/`CHIEF_OF_STAFF_ACTIVITY_LIKE`/
`AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE` — omitting this would reproduce the
exact defect TASK-011 QA round 2 already found and fixed once for
Orchestrator's validation runs (a crashed mid-flight invocation staying
permanently "Working" until a fifth-call pattern was added). Naming this
explicitly here so Development doesn't have to rediscover it.

### 1.5 Red Team gap (c), resolved — accurate persona text for a human-triggered invocation

`automation.py._assemble_transcript()`'s instructions block currently
reads *"You are reviewing this in AUTOMATED mode — a narrower context
than a human-supervised session..."* — factually wrong for a route a
human just clicked a button to trigger. The shared assembly module (§5)
gets a second, distinct instruction-block builder:

> "You are reviewing this in SYNCHRONOUS mode — invoked directly, on
> demand, by a human clicking 'run this review now,' not by an unattended
> background process. Like the automated poller's invocation, you have
> **no** Bash/Read/Grep/Glob access in this mode — everything you need
> has been assembled below, deterministically, by this project's own
> Python code. If you find you need to explore beyond what's provided to
> render a real verdict, say so explicitly in your findings and end with
> the same REJECT/incomplete-context handling below — the human who
> triggered this can then run a separate, fully tool-bearing interactive
> session for that specific need, the same way they always could."

Both `_assemble_transcript()` (poller) and the new synchronous assembly
path call the SAME underlying content-gathering functions; only the
instruction-block text differs by trigger kind, passed as a parameter —
one implementation, two accurate instruction variants, not a
copy-pasted-and-forgotten second version. `code-review.md` keeps its
existing "Automated-invocation mode" section unchanged and gains a new
"Synchronous-invocation mode" section with this text; `security.md` and
`red-team.md` — which have never had either — gain the synchronous
section only (they have no automated/poller mode to speak of in this
milestone).

The truncation-forces-REJECT persona rule, the strictly-last-non-blank-
line `VERDICT:` parsing (`_parse_verdict()`), and the "PASS never
auto-advances, REJECT is a mechanical status rollback only, never a new
Developer invocation" rules all carry over unchanged to all three
synchronous routes — same hardened, already-reviewed logic, reused, not
reimplemented per kind.

---

## 2. Part 2 — the self-immune Developer denylist

### 2.1 Where the hook lives, and why

**`.claude/agents/developer.md`'s own frontmatter — a new `hooks:` block
— and nowhere else.** Not `.claude/settings.json` (doesn't exist today,
and per §3.4's now-confirmed evidence, adding a project-wide
`settings.json` `hooks:` block risks a genuinely *global* mechanism
rather than the per-role one this milestone needs — deliberately avoided,
not merely undiscussed). `Developer`'s `tools:` line is **not** changed —
Developer keeps `Read, Edit, Write, Bash, Grep, Glob, Skill` exactly as
today; the hook narrows what those tools may *do*, it does not remove
any of them.

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "python3 ops/control-center/hooks/developer_pretooluse.py"
    - matcher: "Write"
      hooks:
        - type: command
          command: "python3 ops/control-center/hooks/developer_pretooluse.py"
    - matcher: "Edit"
      hooks:
        - type: command
          command: "python3 ops/control-center/hooks/developer_pretooluse.py"
```

Deliberately three separate `matcher` entries (one exact tool name each)
rather than a single combined pattern (e.g. a `Write|Edit` regex
alternation) — the safer, unambiguous choice given that the *exact*
matcher-string syntax for combining tool names in a frontmatter hook is
not something either this document or Security's Stage 2 review directly
tested (only the underlying `tool_input.file_path` field and the
per-agent `sessionHooks` scoping mechanism were directly verified — see
§3.4). **Before relying on this YAML shape, Development must empirically
confirm it fires correctly for a Write/Edit call** — the same
"flag-and-verify" discipline this whole risk's own investigation has used
throughout (CTO's Stage-1 `file_path` claim → Security's Stage-2 direct
CLI-source verification is the precedent). A concrete, cheap test: add
the hook, have a real Developer session attempt `Write(file_path="/tmp/
canary.txt", ...)` and `Bash(command="echo canary")`, confirm both are
inspected by the hook script (check `hook_denials`/stderr for evidence
the script actually ran, even for allowed calls, during this one manual
test only — not left as permanent logging, see §2.4) before trusting it
in real Developer sessions.

### 2.2 The denylist, concretely — every pattern named, nothing left as "a denylist" in the abstract

`ops/control-center/hooks/developer_pretooluse.py` — pure Python, stdlib
only, **no subprocess calls of its own** (a deliberate design choice that
satisfies Security's S7 "always use absolute paths for hook-internal
external-binary calls" *by construction*, not by discipline — there is no
external binary to bare-name-resolve via `$PATH` in the first place,
closing §2.3 of Security's review entirely for this specific hook, not
just mitigating it).

Reads the standard `PreToolUse` JSON payload from stdin (confirmed real
shape, §3 of this document / Security's Stage 2 §0: `{tool_name,
tool_input, session_id, transcript_path, cwd, ...}`). Two check paths:

**Write/Edit (`tool_input.file_path`) — structured, `.resolve()`-based,
the primary defense** (per Security's §2.2 finding that Bash-string
matching is structurally weaker than typed-field matching — Write/Edit
protection is not a backstop here, it's the main line):

- Deny if `Path(file_path).resolve()` equals, or is a descendant of, any
  of:
  - `ops/control-center/.founder_credential.json` — the credential file
    (S-baseline, CTO's original design).
  - `ops/db/operations.sqlite3` — the operational database file itself
    (Security's **S2**, named explicitly, not folded into a generic
    "outside repo root" rule that doesn't cover it — this file is
    git-tracked, inside `repo_root`, exactly as Security's Stage 2 §3
    finding #2 established).
  - `.claude/agents/developer.md` — **this hook's own defining file**
    (Red Team's **S8**).
  - `ops/control-center/hooks/developer_pretooluse.py` — **this hook's
    own script** (Red Team's **S8** — the config isn't just the YAML
    block, it's also the code the YAML block points at).
  - `.claude/settings.json` / `.claude/settings.local.json` — pre-emptive
    protection in case a future change introduces either (neither exists
    today, per this project's own repeated verification across three
    prior reviews).
- Deny if `Path(file_path).resolve()` is **not** a descendant of
  `REPO_ROOT` (the pre-existing baseline containment rule, unchanged from
  CTO's Stage-1 design).

**Bash (`tool_input.command`) — string/substring matching, explicitly
disclosed as a coarser backstop, not the primary defense** (directly
adopting Security's §2.2 recommendation rather than treating the two hook
types as equivalent-strength, which CTO's Stage-1 document incorrectly
implied):

- Deny if the command string contains, as a substring: `founder_credential`,
  `operations.sqlite3`, `import sqlite3`, `sqlite3.connect`, `ptrace`,
  ` gdb`, ` strace`, `sudo `.
- Deny if the command string, after a cheap `shlex`-based best-effort
  tokenization, references `.claude/agents/developer.md`,
  `ops/control-center/hooks/developer_pretooluse.py`, `.claude/settings.json`,
  or `.claude/settings.local.json` as an apparent path argument (e.g. to
  `cat >`, `sed -i`, `>`, `>>`, `cp`, `mv`, `rm`) — best-effort, not a
  claim of completeness.
- **Explicitly not attempted**: reliable detection of non-`127.0.0.1`
  network access via Bash string matching. CTO's Stage-1 design implied
  this was achievable; it is not, without a much larger allowlist-shaped
  redesign out of this milestone's scope. Not included in the denylist,
  and not claimed as covered — an honest omission, not a silent gap.

**Both check paths are explicitly, honestly disclosed as bypassable by a
deliberately adversarial agent** via the exact techniques Security's
Stage 2 §2.1 demonstrated with working commands (base64/heredoc
indirection defeats substring matching; a symlink plus an unrelated-
looking Bash command defeats naive path detection). This is not new
information — it is the same residual gap CTO's Stage 1 and Security's
Stage 2 already named for the realistic threat model (scope creep,
prompt-injection-influenced ordinary work) this system actually faces,
restated here rather than re-litigated.

### 2.3 Why this hook self-protects continuously, not just after the fact

Per §3.4's direct evidence from the installed CLI source: a subagent's
`hooks:` frontmatter is registered into a per-invocation `sessionHooks`
map keyed by that specific agent invocation's own session id, and this
registration happens **before** the tool-execution loop begins for that
invocation — including its first tool call. There is no window, within
any single Developer invocation, where a tool call can execute before the
hook is active. The only way Developer could remove its own constraint is
by successfully editing `.claude/agents/developer.md` or the hook script
in a **future** invocation — which the hook itself denies from the very
first tool call of that future invocation onward, per the self-protection
rules in §2.2. This closes the loop for Developer specifically, completely,
not merely "until Developer finds a workaround this review didn't think
of" — the self-referential structure is what makes it durable, not a
one-time check.

### 2.4 Audit — hook denials, a new small table

```sql
CREATE TABLE IF NOT EXISTS hook_denials (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  role               TEXT NOT NULL,           -- 'developer' (only role hooked this milestone)
  tool_name          TEXT NOT NULL,           -- 'Bash' | 'Write' | 'Edit'
  matched_rule       TEXT NOT NULL,           -- which specific pattern fired, e.g. 'operations.sqlite3'
  tool_input_summary TEXT NOT NULL,           -- truncated (2,000 chars), the command or file_path
  session_id         TEXT,
  transcript_path    TEXT,
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_hook_denials_role ON hook_denials(role);
CREATE INDEX IF NOT EXISTS idx_hook_denials_created ON hook_denials(created_at);
```

`opsdb.record_hook_denial(conn, role, tool_name, matched_rule,
tool_input_summary, session_id=None, transcript_path=None)` — a new,
small, unconditional-INSERT function, called by
`developer_pretooluse.py` itself via its own `opsdb.connect()` (the hook
script is a standalone subprocess the harness spawns per tool call; it
opens its own short-lived connection, the same pattern every other
one-shot script in this codebase already uses).

**Scope, matching Security's S6 exactly, not overclaiming**: this logs
**denied** attempts only. It does not log every allowed tool call — the
same disclosed tradeoff Security's Stage 2 §6 accepted as reasonable-cost
for CTO's original design, restated here rather than silently expanded.
A genuinely successful bypass, by definition, produces no denial and
therefore no row here. The after-the-fact detection mechanism for that
case remains what Security's Stage 2 §6 already recommended and this
milestone does not build further: periodic (not automated, not
per-session) human/Security sampling of full session transcript files,
using the real `transcript_path` field this hook payload already
confirms exists. This milestone does not introduce an "ask"-outcome log
either — because a pure denylist (not an allowlist) never produces
Claude Code's native interactive "ask" outcome; every tool call not
matching a denied pattern is simply allowed, with nothing new for this
hook to log. (CTO's Stage-1 §3.2 point 8 discussion of "ask" logging was
written for a broader QA/DevOps allowlist-shaped hook — out of scope this
milestone — and does not apply to a denylist-only design.)

### 2.5 SCOPE CONFLICT — the DevOps half of "read-only to Developer and DevOps," named and only partly closeable here

The Founder's authorization text (Appendix E, item 2) reads: *"...scoped
so that the denylist/hook configuration itself is read-only to Developer
**and DevOps** — no sanctioned path (native tool grant or skill) for
either role to edit its own constraint."* Section §2.1–§2.3 above fully
closes the **Developer** half, technically, via the hook itself. The
**DevOps** half cannot be fully closed within this milestone's own
explicitly-stated boundaries, and this is a real conflict in the brief,
not an oversight on my part:

- DevOps does not get a `PreToolUse` hook in this milestone — DevOps tool
  scoping is explicitly, separately listed as **out of scope**
  ("Explicitly OUT of scope — do not design or touch: QA, CTO, or DevOps
  tool scoping...").
- DevOps's own native tool grant (`.claude/agents/devops.md`: `Read,
  Grep, Glob, Bash, Skill`) already includes unrestricted Bash today.
  Bash alone — with no hook watching it — is sufficient to
  `cat > .claude/agents/developer.md <<EOF ...` or `sed -i` the hook
  script directly, regardless of anything any skill's documentation says
  is or isn't sanctioned. **This is Red Team's own S8 finding, restated
  precisely**: DevOps doesn't need `Write`/`Edit` to defeat this — Bash
  alone already does, and Bash is DevOps's unrestricted native grant,
  unaffected by anything in this milestone.
- Genuinely closing this — technically, not just on paper — requires a
  DevOps-scoped `PreToolUse` hook denying DevOps's Bash from touching
  these same protected paths. That is DevOps tool scoping, which this
  same authorization explicitly forbids touching this milestone.

**What this document does about it, within the boundary it's actually
given**: the *skill-level sanction* Red Team's own review named as the
concrete evidence for this gap — `ops/skills/operations/update-config.md`
and `ops/skills/operations/fewer-permission-prompts.md` explicitly
documenting "hooks"/`settings.json` as things DevOps may configure — is
re-scoped (§5, file list) to explicitly exclude these specific protected
paths, closing the **documented-sanction** half of the gap completely. It
does **not**, and cannot, close DevOps's underlying **technical
capability** to do it anyway via raw Bash, because that capability comes
from DevOps's tool grant itself, not from the skill documentation, and
touching that grant is exactly what this milestone is told not to do.

**Disclosure, matching this project's own established discipline for a
gap it cannot close within scope**: after this milestone ships, DevOps
remains technically able to edit `.claude/agents/developer.md`'s `hooks:`
block, the hook script, or (if one is ever created) `.claude/settings.json`,
via ordinary Bash, with no hook watching it and no sanctioned
skill instructing it to. This is unchanged by anything in this document.
Closing it requires a future, separately-reviewed DevOps-tiering
milestone that is explicitly not this one. This should be named
explicitly in the disclosure text appended to `risks.id=3`'s mitigation
(§4) rather than folded silently into "Developer and DevOps are both now
excluded" language that would overclaim what actually shipped.

---

## 3. Verification — is `hooks:` frontmatter scoping genuinely per-subagent, or global?

Red Team's Stage 3 flagged this as unresolved and load-bearing for
whether the Developer denylist can actually be Developer-only. This
document resolves it with direct evidence, not further assumption —
using the same method Security's Stage 2 used for the `file_path`
question (reading the installed CLI source directly, not the public docs
site).

### 3.1 The registration path, read directly from `cli.js`

The subagent-invocation function (the code path that runs a Task-tool
subagent, `.claude/agents/<name>.md`'s own definition included) generates
a **fresh, per-invocation agent id** for every subagent call
(`V=O?.agentId?O.agentId:aR()`), and — before the model's own
tool-execution loop begins for that invocation — calls
`Oe7(setAppState, V, A.hooks, 'agent '+A.agentType, true)` if (and only
if) that agent's own definition (`A.hooks`, sourced from its frontmatter's
`hooks:` key) is non-empty.

`Oe7()` iterates the hook-event list and, for each declared hook, calls a
registration function that writes into application state at
`sessionHooks[q]` — where `q` is that same per-invocation agent id `V`,
**not** a global key and **not** the top-level interactive session's own
id.

### 3.2 The lookup path — confirms scoping is enforced at check time too, not just at registration

A separate function (`NH6(A,q,K)`) — used to resolve which hooks apply
for a given hook-event check — reads `A.sessionHooks[q]`, keyed by the
**same** per-invocation agent id. If no entry exists for that id, it
returns an empty result. This confirms the scoping isn't merely
registered narrowly and then checked broadly — the read path is keyed
identically to the write path.

### 3.3 What this confirms, and what it doesn't

**Confirmed, directly, not assumed**: a `hooks:` block declared in
`.claude/agents/developer.md`'s own frontmatter is registered against,
and enforced against, that specific Developer invocation's own session
identity — not the interactive top-level session, and not every subagent
invocation regardless of role. Two different subagent invocations (e.g. a
Developer session and a QA session running concurrently, or launched
moments apart, within the same top-level interactive session) get
distinct `sessionHooks` entries. A hook declared in `developer.md`'s
frontmatter has no code path in `cli.js` that would apply it to a `qa` or
`cto` invocation's own `sessionHooks[qa-agent-id]`/`sessionHooks[cto-
agent-id]` entry — they're different map keys entirely.

**What this does not resolve** (flagged honestly, not overclaimed,
matching this project's own established discipline): the *exact* matcher
string syntax for combining multiple tool names in one hook entry (§2.1)
is not independently confirmed by this reading — only that per-tool-name
matching and per-agent scoping are both real, harness-enforced mechanisms.
Development's empirical test (§2.1) closes this specific remaining gap
before the hook is relied upon in real sessions — this is the smallest
remaining unverified detail, not the load-bearing question Red Team
flagged, which this section resolves with direct evidence.

---

## 4. Part 3 — the raw-`sqlite3`-bypasses-`opsdb.py` vector: partial fix, undiluted disclosure of the rest

**What's fixed, in scope, cheap**: `operations.sqlite3` and the specific
raw-access patterns (`import sqlite3`, `sqlite3.connect`, and the literal
filename) are named explicitly in the Developer denylist (§2.2),
satisfying Security's **S2** exactly. This is a real, harness-enforced
narrowing **for Developer specifically** — the same honest "raises the
bar for the realistic case, does not close the adversarial case"
framing CTO's Stage 1 and Security's Stage 2 already established for
every other denylist entry, not overclaimed here either.

**What is not fixed, and is not fixable within this milestone's own
stated boundaries** — stated plainly, matching the discipline this
project already applied to `risks.id=2` and to Phase 3A's own
consequence-increase disclosure in `ops/SECURITY.md`:

1. **This protection applies to Developer only.** QA, CTO, and DevOps —
   three of the four roles with real Bash access today — remain
   completely unprotected against this vector, exactly as they were
   before this milestone, because their tool scoping is explicitly out of
   scope here.
2. **Even for Developer, this is a string-pattern mitigation, not a
   closure.** Security's Stage 2 §2.1 demonstrated a working base64/
   heredoc command that defeats substring matching entirely, and §2.2
   showed Bash-string path detection is structurally weaker than
   Write/Edit's typed `file_path` field. A deliberately adversarial
   Developer session can still reach `operations.sqlite3` via raw
   `sqlite3` this milestone does not close.
3. **The deeper structural gap Security's Stage 2 §3 named — that
   `opsdb.py` enforces real invariants in Python that are not all also
   expressed as SQL `CHECK` constraints, so a raw write respects only
   what the schema happens to enforce — is untouched by anything in this
   document.** One example already resolved before this milestone: the
   reject-requires-`returned_to_agent` invariant is now a real `CHECK`
   constraint on both `qa_results` and `review_results` (confirmed by
   direct read of `ops/db/schema.sql` for this document — Security's own
   Phase 3A C4 fix). Others are not confirmed to be — task status
   transition validity (which `from_status → to_status` pairs are legal)
   is enforced only in `opsdb.record_task_status()`'s own Python logic,
   with no equivalent SQL `CHECK`/trigger, meaning a raw `sqlite3` write
   could set `tasks.status` to any value the column's own (permissive)
   `CHECK (status IN (...))` allows, in any order, skipping the state
   machine entirely. Closing this genuinely requires either a full
   DB-write broker (CTO's Stage-1 §3.5, a materially larger, separate
   architecture investigation) or exhaustive `CHECK`/trigger coverage
   auditing every Python-only invariant in `opsdb.py` against the schema
   (a real, non-trivial schema-wide project of its own) — neither is
   "cheap and in-scope" for this narrow milestone, and neither is
   attempted here.

**Recommended disclosure text**, to be appended to `risks.id=3`'s
mitigation via `python3 ops/db/opsdb.py risk-resolve --risk-id 3
--status mitigated --mitigation "..."` **once Development has shipped
this milestone and it has passed the full gate sequence through CTO
conformance** — not executed by this document, per the Founder's own
instruction that the status change happens after the milestone ships,
and matching this project's convention that a major risk-register change
goes through the review chain before the CLI call, not before it:

> TASK-017 (risks.id=3 reduction milestone) shipped three things: (1)
> Code Review, Security, and Red Team's normal invocations are now
> zero-tool via new synchronous, human-triggered routes reusing Phase
> 3A's existing pattern — their interactive/investigative sessions are
> completely unaffected, a structurally separate code path, not merely a
> documented carve-out. (2) A Developer-role `PreToolUse` denylist
> (Bash + Write/Edit, covering the credential file, `operations.sqlite3`
> and raw-sqlite access patterns, `ptrace`/`sudo`, and its own
> configuration files) is live and self-protecting against Developer
> specifically — confirmed, not assumed, to be scoped to Developer's own
> per-invocation session only (see `ops/reviews/cto-risk3-milestone-
> architecture.md` §3). It is NOT technically closed against DevOps,
> whose unrestricted Bash grant remains a sanctioned-by-capability (if no
> longer sanctioned-by-documentation) path to the same files — a named,
> disclosed scope conflict in this milestone's own authorization, not an
> oversight (§2.5). (3) QA, CTO, and DevOps remain completely unscoped —
> exactly as before this milestone. (4) The raw-`sqlite3`-bypasses-
> `opsdb.py` vector is narrowed for Developer only, via string-pattern
> denial, itself disclosed as bypassable by a deliberately adversarial
> session (base64/heredoc indirection) — the deeper gap (Python-only
> invariants, e.g. task status transition validity, not mirrored as SQL
> `CHECK`/trigger constraints) is completely untouched and would require
> a separate, materially larger architecture investigation (a DB-write
> broker, or exhaustive constraint auditing) neither attempted nor
> in-scope here. `risks.id=3` remains a live master-key exposure for
> three of seven tool-bearing roles and a real, disclosed residual gap
> for the fourth. See `ops/reviews/cto-risk3-milestone-architecture.md`,
> `ops/reviews/security-risk3-threat-model.md`,
> `ops/reviews/red-team-risk3-challenge.md`.

---

## 5. File-by-file change list

**New files:**

- `ops/control-center/review_transcripts.py` — extracted from
  `automation.py`: `_SHA_RE`/`_commit_exists`/`_validate_repo_path`/
  `_git_diff`/`_git_show_file`/`_read_coding_standards`, unchanged
  internals (no behavior change, pure move). Adds a red-team-specific
  artifact assembly helper (§1.3.3) and a parameterized instruction-block
  builder (automated vs. synchronous text, §1.5).
- `ops/control-center/reviewer_sync.py` — orchestration glue for the
  three new synchronous routes, mirroring `automation.py`/
  `chief_of_staff.py`'s existing separation from `server.py`. Exposes
  `run_code_review_sync(task_id)`, `run_security_review_sync(task_id)`,
  `run_red_team_review_sync(task_id, artifact_paths)`.
- `ops/control-center/hooks/developer_pretooluse.py` — the Developer
  denylist hook script (§2.2–§2.4).

**Modified files:**

- `ops/control-center/automation.py` — remove the six private functions
  now living in `review_transcripts.py`; import them instead. No
  behavior change.
- `ops/control-center/agent_runtime.py` — rename
  `AUTOMATED_REVIEW_TIMEOUT_S` → `REVIEW_TIMEOUT_S` (shared, §1.3.2); add
  `REVIEWER_SYNC_ALLOWLIST = ("code-review", "security", "red-team")`,
  `REVIEWER_SYNC_ACTIVITY_LABEL`, `REVIEWER_SYNC_ACTIVITY_LIKE`,
  following the file's own established four-allowlist convention exactly;
  add the new allowlist to `invoke_agent()`'s membership check.
- `ops/control-center/server.py` — three new routes added to the
  existing `do_POST()` match chain (§1.3), reusing
  `_require_csrf_token()`/`_authenticated_session()` unchanged; three new
  `_handle_*` methods calling `reviewer_sync.py`; a fourth `LIKE`-pattern
  call added to `_reconcile_orphaned_runs()` (§1.4).
- `ops/db/schema.sql` — two new tables, `reviewer_invocations` (§1.4) and
  `hook_denials` (§2.4). Both brand-new (`CREATE TABLE IF NOT EXISTS`),
  no migration complexity.
- `ops/db/opsdb.py` — `start_reviewer_invocation()`,
  `end_reviewer_invocation()` (mirroring
  `create_automation_event()`/`end_automation_event()`'s shape, minus the
  atomic-claim logic), `record_hook_denial()`.
- `.claude/agents/developer.md` — new `hooks:` frontmatter block (§2.1).
  `tools:` line unchanged.
- `.claude/agents/code-review.md` — new "Synchronous-invocation mode"
  persona section (§1.5), alongside the existing "Automated-invocation
  mode" section, unchanged. `tools:` line unchanged.
- `.claude/agents/security.md` — new "Synchronous-invocation mode"
  persona section (§1.5). `tools:` line unchanged.
- `.claude/agents/red-team.md` — new "Synchronous-invocation mode"
  persona section (§1.5), describing the artifact-path form (§1.3.3).
  `tools:` line unchanged.
- `ops/skills/operations/update-config.md` — "Limitations" line gains an
  explicit exclusion: must not be used to add, remove, or modify any
  `hooks:` block in any `.claude/agents/*.md` file, any file under
  `ops/control-center/hooks/`, or the `hooks` key of any
  `.claude/settings*.json` — those are protected architecture artifacts,
  changed only via a CTO/Red-Team-reviewed `decision-record`. (§2.5 —
  closes the documented-sanction half of the DevOps gap; does not close
  the underlying Bash capability, disclosed as such.)
- `ops/skills/operations/fewer-permission-prompts.md` — same exclusion
  added to its "Limitations" line.
- `ops/SECURITY.md` — new section documenting this milestone, following
  the exact Phase 3A section convention, using the disclosure text in §4
  as its `risks.id=3` paragraph. Written once Development has shipped and
  the design is confirmed working, not by this document.
- UI: `/reviews.html` (via `generate_reviews.py`, unlisted here in detail
  — not touched by this document) needs three small forms ("run this
  review now") posting to the new routes with the existing hidden
  `token` field, the same pattern every other button in this application
  already uses. Named here so Development doesn't have to rediscover
  that a route with no UI entry point is dead code; not itself a
  Founder-facing route/auth change (it's the same session-gated app
  surface, a new button in it).

**Not created by this document**: no `decision-record` entry, no
`risk-resolve` call. Per this milestone's own gate sequence (Architecture
→ Security → Red Team → Development → Code Review → QA →
Security-adversarial → CTO conformance), those are executed once the
design below has been reviewed and shipped — the same ordering `DEC-007`
followed for Phase 3A (recorded citing all three review-stage documents
together, not at the Architecture stage alone).

---

## 6. What Security and Red Team should specifically check next

- Whether §1.2's "the carve-out is structural, not a new mode" framing
  actually holds once the concrete route/module list in §5 is read
  end-to-end — is there any path by which the new synchronous routes
  could be invoked with tools attached, or by which an interactive
  session could accidentally route through `agent_runtime.invoke_agent()`?
- Whether §2.1's three-separate-matcher YAML shape is correct, once
  Development's empirical test (§2.1) runs — and whether the test itself
  is sufficient evidence, or needs to be broader.
- Whether §2.5's scope-conflict resolution (re-scope the two DevOps
  skills' documentation; disclose the remaining Bash-capability gap
  rather than close it) is the right call, or whether the Founder should
  instead be asked to either loosen the DevOps-out-of-scope boundary or
  accept the gap explicitly before this ships.
- Whether §4's disclosure text is itself undiluted enough — this is
  exactly the kind of judgment call this project's own process treats as
  requiring independent verification, not author sign-off.
