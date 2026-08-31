# CTO architecture investigation — risks.id=3 (TASK-016)

Investigation-only, per the Founder's directive. No product/ops code is
touched by this document. Read before writing: `ops/SECURITY.md`,
`ops/ROADMAP.md`, `ops/reviews/cto-phase3a-architecture.md`,
`ops/reviews/security-phase3a-threat-model.md`, and all 14
`.claude/agents/*.md` subagent definitions. Also verified directly against
this repository: no `settings.json`/`settings.local.json` exists anywhere
in this project today, and no `hooks:` block exists in any of the 14
subagent frontmatter files — this project has never used the harness's own
hook mechanism, in Phase 0 through Phase 3A. That fact matters throughout
this document: it means part of `risks.id=3`'s severity is a gap this
project created by omission, not only a platform ceiling.

`risks.id=3`, live: "Every subagent's Bash tool grant is not scoped below
the tool category — a subagent's role doc may say 'no implementation
tools' but it technically still has shell access beyond `opsdb.py`.
Environment-level limitation, not fixable by Phase 1/2 code alone." Status
`open`, `owner_agent=cto`, `severity=medium`. Mitigation text, appended at
Phase 3A: two new, additive consequences (a background actor that acts
without a request; a data-driven filesystem/subprocess surface), neither
closed by that milestone.

## 0. What this document does NOT do

Per the Founder's directive, this document does not start from "Claude
Code cannot scope Bash below the tool-category level, therefore this is
unsolvable." It starts from the actual security property this project
needs, investigates whether an architecture *built around* Claude Code
(not a change to the platform) can deliver it, and separates genuine
platform limits from this project's own architectural choices throughout.
It also does not manufacture a tidy "problem solved" conclusion where none
exists — see §8 for what remains genuinely open and why.

## 1. What security property do we actually need?

`risks.id=3` is not really about Bash in the abstract — it is about seven
specific, real, tool-bearing subagent roles (`developer`, `code-review`,
`qa`, `security`, `cto`, `red-team`, `devops`) that run under the
Founder's own OS user, with real Read/Write/Edit/Bash access, invoked
either interactively (a human watching tool calls in real time) or via
Chief-of-Staff-relayed instruction. `agent_runtime.py`'s zero-tool
guarantee already, correctly, closes the *unsupervised* path (Ask-Agent,
Executive Meetings, Chief of Staff, Phase 3A's automated Code Review) —
this document does not revisit that; it is already sound and independently
verified twice (Security's and Red Team's Phase 3A reviews).

For the *supervised, tool-bearing* roles, the realistic threat this
project actually faces is not a sophisticated external attacker — it is a
single local machine, single trusted human, no external users. The
realistic failure modes are:

1. **Scope creep / mistakes** — an agent doing legitimate work touches
   something outside the task it was actually given (e.g. a Developer
   session, mid-debugging, reads or edits a file with no relationship to
   the task).
2. **Prompt injection via attacker-controlled content** — Phase 3A's own
   automated Code Review already reads Developer-supplied diff/file
   content into a model's context; a human-triggered Code Review or QA
   session reads the same kind of content. Content in a diff, a task
   description, or `handoffs.files_changed` is data this project's own
   `SECURITY.md` already calls "attacker-writable, same-OS-user-
   controlled." An agent whose next action is influenced by that content
   is not a hypothetical.
3. **A deliberately adversarial agent** — the least realistic case for
   this single-operator system, but the one every option below must be
   judged against too, because "would a determined bypass work" is a
   different, harder question than "would ordinary supervised work stay
   in its lane."

The property we actually want: **a real, technically enforced ceiling on
what a given supervised invocation can touch — narrower than "this whole
tool category," ideally narrower than "this whole role" — that holds
against (1) and (2) unconditionally, and against (3) as far as is
achievable without disproportionate cost for a single-operator, no-
external-traffic system.** Not "a better-worded instruction the model is
trusted to honor."

## 2. Platform limits vs. this project's own choices — stated explicitly, throughout

**(A) Genuine Claude Code platform limitations, unavoidable by any
architecture this project builds around it:**

- No native mechanism to grant a subagent fine-grained *operation*-level
  capabilities (e.g. "read `/src/payments/**`, run `pytest`, nothing
  else") directly in `tools:` frontmatter — that field is category-level
  by design (`Bash` is on or off, not "these commands").
- PreToolUse hooks and the `permissions.allow`/`deny` engine both operate
  on the **presented tool input** (a command string, a file path) — not
  on the runtime behavior of whatever process tree that command spawns.
  Prefix/pattern matching is documented as imperfect (option reordering,
  redirects, variable indirection, protocol tricks).
- The built-in sandbox (Seatbelt/bubblewrap) has documented, real gaps:
  TLS-inspection/domain-fronting, Unix-socket escalation, `$PATH`/
  `.bashrc` write-escalation, and subprocess isolation limited to Bash's
  own children.
- No known mechanism for Claude Code's native Task-tool subagent
  delegation (a subagent invoked inline, within the same interactive
  session a human is watching) to run under a different OS UID than the
  parent session. (Flagged as an assumption based on current
  understanding of the platform, not one of the six given ground-truth
  facts — Security/Red Team should treat this specific claim as needing
  independent verification, not as settled.)

**(B) This project's own architectural choices, which it could change:**

- **Zero use of hooks anywhere, ever, in this codebase.** The harness-
  enforced, per-subagent-scopable mechanism ground-truth facts #1–#2
  describe has never been configured. This is the single largest gap
  between "what's technically available" and "what's actually built" —
  and it is entirely this project's own omission, not a platform ceiling.
- **All seven tool-bearing roles get an identical, undifferentiated tool
  shape** (`Read, Grep, Glob, Bash[, Write, Edit], Skill`), even though
  three of them (`code-review`, `security`, `red-team`) are structurally
  "read the content, render a verdict" roles, and this project has
  *already built and independently reviewed* a zero-tool,
  Python-assembled-transcript pattern that serves exactly that job for
  one of the three (Phase 3A's automated Code Review) — and simply never
  extended it to the other two roles or to that role's own human-
  triggered invocation.
- **No task-level structured scope exists in the schema.** `tasks` has no
  `allowed_paths` or comparable field; `architecture_notes`/
  `acceptance_criteria` are free text. Even if hooks existed today, there
  is no *data* to drive a task-level policy from.
- **No git-worktree-per-task convention.** Developer works directly in the
  one shared working tree — there is no natural, pre-existing "this task's
  own directory" a hook could contain access to even if one were built.
- **Single-OS-user-for-everything** is a foundational assumption this
  system has carried since Phase 1 (`SECURITY.md`'s repeated "local/
  single-user trust — not solved" language) — not something Phase 3A
  introduced, but squarely a choice this project made, at real cost to
  reverse.

Every option below is judged against this same (A)/(B) split.

## 3. Options investigated

For each option taken seriously enough to write up: the boundary, what
enforces it, adversarial bypass attempts, whether it protects the
credential/session/DB surface, whether it's uniform across roles, cost to
legitimate work, implementation cost, elevation/revocation mechanism,
audit, and failure-mode behavior.

### 3.1 Extend the already-built zero-tool pattern to Code Review, Security, and Red Team's *human-triggered* invocations

**The single strongest, cheapest option found — because it isn't a new
control, it's finishing a design this project already shipped and
reviewed once.**

Phase 3A's automated Code Review (`ops/reviews/cto-phase3a-architecture.md`
§B.1) already proved, and both Security and Red Team independently
confirmed, that Code Review's real job — correctness, maintainability,
architecture consistency, security, test coverage, judged against a diff,
task metadata, and coding standards — is fully judgeable from
deterministically-Python-assembled content (git-object-database diff/file
content, `handoffs` record, `CODING_STANDARDS.md`), with **zero** Bash/
Read/Grep/Glob grant to the model itself. The `code-review` skill's
guidance is already folded into a persona note for that mode
(`.claude/agents/code-review.md`, "Automated-invocation mode") rather than
invoked live — proof this doesn't depend on the Skill tool being present
at model-invocation time either.

**What's proposed**: build the equivalent *human-triggered, on-demand*
path — reusing the exact transcript-assembly functions Phase 3A already
wrote for `automation.py` — for `code-review`, and extend the same pattern
to `security` and `red-team` (both are structurally identical "read
content, render PASS/REJECT" jobs; `red-team.md` already states "you have
no implementation tools on purpose — your only output is a verdict," which
is precisely the zero-tool philosophy, just not yet fully applied to Bash).
Their `tools:` frontmatter drops `Bash, Grep, Glob` (and `Read`, since the
model never touches the filesystem directly — everything it needs arrives
pre-assembled in the transcript) entirely for this invocation path.

1. **Boundary**: none — there is no filesystem/subprocess boundary to
   define, because the model has no tool that could touch either.
2. **Enforcement**: the same mechanism already verified twice for Phase
   3A — `agent_runtime._run_claude()`'s `--tools ""` / `--strict-mcp-config`
   are unconditional, caller-independent. Harness-enforced, not prompt-
   trusted.
3. **Bypass**: none available *to the model* — there is no subprocess to
   spawn, no symlink to follow, no `cd` to escape, because no tool exists
   that could initiate any of those. (The Python code doing the assembly
   is real, trusted, reviewed code — the same §B.1.2/C1 path-and-SHA
   validation discipline applies unchanged; that surface is not new here.)
4. **Credential/DB reach**: none, directly or indirectly — no tool call
   this invocation could make ever executes.
5. **Uniform across roles?** Uniform for exactly the three "read + judge"
   roles (`code-review`, `security`, `red-team`) — and *only* those three.
   Does not apply to `developer`, `qa`, `cto`, `devops`, whose jobs
   structurally require live execution (see §3.2).
6. **Cost to legitimate work**: real, but narrow. Loses genuine
   exploratory review (following curiosity into an unrelated file,
   checking whether a helper is used inconsistently elsewhere, running the
   test suite live) — the same, already-honestly-disclosed limitation
   Phase 3A's automated mode already carries (§B.1.1's named defect class:
   cross-file consistency/duplication defects it structurally cannot
   catch). This is not a new cost — it is extending a cost this project
   already accepted for the automated case to the human-triggered case
   too.
7. **Implementation cost**: low. No new infrastructure — reuse
   `automation.py`'s diff/file-content assembly, add one new HTTP route or
   CLI entry point that runs it synchronously instead of on a poll cycle,
   update three `tools:` frontmatter lines, fold each skill's guidance
   into the corresponding persona note (same pattern
   `code-review.md`'s automated-mode section already establishes).
8. **Elevation/revocation**: not applicable in the traditional sense — if
   a specific review genuinely needs exploratory access (the disclosed
   limitation above), the honest answer, matching this project's own
   established discipline, is a human runs a *different*, explicitly
   tool-bearing session for that one case, the same way a human already
   can today. Not built as an in-band "ask for more" flow, because
   granting more mid-review inside a zero-tool invocation isn't possible
   by construction — that's the whole point.
9. **Audit**: identical to every existing invocation — `agent_runs`,
   `review_results`/`qa_results` (unchanged shape), `messages`
   (if surfaced via Ask-Agent-style persistence). No new logging concept.
10. **Wrong-scope failure mode**: doesn't apply — there's no scope to get
    wrong, only a disclosed capability ceiling. If a human decides a
    specific review genuinely needs exploration this mode can't provide,
    they run a supervised session instead — a deliberate escape hatch,
    not a silent gap.

**This closes `risks.id=3`'s exposure completely — not narrows it — for
three of the seven roles.** No hook, no OS change, no new data model. This
is real, not a hedge, and it is the cheapest genuine win available.

### 3.2 PreToolUse hooks, scoped per role — for `developer`, `qa`, `cto`, `devops`

The four roles that cannot be reduced to a static assembled transcript
without losing their actual function: Developer writes/executes/iterates,
QA drives the running application, DevOps verifies build/environment
state, CTO reads live, evolving repository state (and writes/edits durable
docs). For these, §3.1's approach doesn't apply — some real tool grant is
unavoidable. This is where ground-truth facts #1–#4 (PreToolUse hooks,
per-subagent scoping, shell-operator-aware permission matching, absolute
deny rules) become the actual lever.

**Design**: each of the four roles' `.claude/agents/<name>.md` gains a
`hooks:` block defining a `PreToolUse` hook for `Bash` (and, if the
platform supports it for these tools too — flagged as an assumption
needing verification, not a given fact — `Read`/`Write`/`Edit` via their
`file_path` input) that runs a small, deterministic, project-owned
Python/shell script before every tool call:

- A **hard denylist**, identical across all four roles, authored once by
  CTO/Security and version-controlled like any other architecture
  artifact: deny any command/path touching `.founder_credential.json` (or
  anything matching `*credential*`), deny `ptrace`/`gdb`/`strace`
  targeting `server.py` or any PID, deny `sudo`, deny outbound network
  access beyond `127.0.0.1`/localhost, deny any write outside the repo
  root (or the task's worktree — see §3.3).
- A **role-specific allow/deny shape** layered on top: `qa`/`devops` (no
  `Write`/`Edit` today) get a narrower Bash allowlist (run the app, run
  tests, inspect state) since their job doesn't need broad file mutation;
  `developer`/`cto` (have `Write`/`Edit`) get the denylist only, not a
  strict allowlist, because their legitimate work is genuinely open-ended
  (iterative debugging, ad hoc one-off commands, `pip install` for a
  justified new dependency).

1. **Boundary**: a fixed, version-controlled pattern list (path globs +
   command-prefix patterns), evaluated per invocation against the literal
   `tool_input.command`/`file_path` string the harness passes the hook.
2. **Enforcement**: real — harness-level, fires before the tool executes,
   independent of what the model "wants," per ground-truth fact #1. Not a
   prompt convention.
3. **Bypass — adversarially stress-tested**:
   - *Subprocess indirection*: `python3 -c "..."` invoked via Bash is
     itself just a Bash command string the hook inspects — the hook can
     deny `python3 -c` outright, but the underlying problem generalizes:
     any interpreter capable of doing file I/O or making a socket
     connection, invoked as the *first* command, is visible to the hook
     as a string; what that interpreter does *at runtime* (a second
     `subprocess.Popen` inside a Python one-liner, base64-decoded and
     `exec`'d) is invisible to a hook that only ever inspects the initial
     command string once, before execution. **This is the fundamental,
     unclosable gap of string-pattern hooks**: they gate the command they
     see, not the process tree it spawns.
   - *Symlinks*: a hook doing real path resolution (`Path(...).resolve()`,
     the same primitive Phase 3A's own `git show` mitigation already
     established as the correct one) closes the classic case. A hook that
     only does substring matching on the raw string does not.
   - *`cd` and relative-path tricks*: per ground-truth fact #3, the engine
     splits on `&&`/`;`/`|`/newlines and evaluates each subcommand
     independently — `cd /tmp && cat secret` is not a single opaque match,
     `cat secret` (now relative to `/tmp`) is itself checked. A hook that
     tracks cwd state across a chained command is buildable but adds real
     complexity; one that doesn't can be fooled by a sufficiently
     deliberate multi-step `cd` sequence.
   - *Encoding/obfuscation*: base64, `$(...)` command substitution,
     variable indirection (`X=/etc/passwd; cat $X`) — pattern lists can be
     extended to catch known instances, never all instances. This is an
     open-ended arms race against a *deliberately adversarial* agent — see
     §1's realistic-threat-model framing: this is a real, honestly-
     disclosed residual gap against (3), not against (1)/(2).
4. **Credential/DB reach**: the denylist directly blocks the two concretely
   named vectors (`SECURITY.md`'s own Milestone 2B4 disclosure) — reading
   `.founder_credential.json` and `ptrace`-ing `server.py` — as long as the
   pattern actually matches what's attempted. It does **not** close the
   third: an agent can still write a plausible `CODE_REVIEW`-transition/
   `handoffs` row via `opsdb.py` directly, because `opsdb.py` invocations
   are legitimate, expected commands every role is supposed to be able to
   run (this is `risks.id=3`'s own Phase 3A-disclosed consequence #1 — a
   hook restricting *which files/commands* are touched does not restrict
   *what data* a permitted, legitimate-looking `opsdb.py` call writes).
5. **Uniform across roles?** No, deliberately — see the role-specific
   shape above. This is a feature, not a gap: `qa`/`devops` can be held to
   a tighter allowlist at low cost; `developer`/`cto` cannot without
   breaking real work, so they get the (weaker, but still real) denylist
   shape instead.
6. **Cost to legitimate work**: real for the allowlisted roles (anything
   not anticipated in the allowlist fails and must be added, a real
   friction cost); low for the denylisted roles (only the specifically
   named dangerous operations are blocked; everything else proceeds
   exactly as today).
7. **Implementation cost**: low-to-moderate. No new infrastructure beyond
   writing and testing the hook scripts and the four frontmatter blocks;
   this is exactly the kind of small, reviewable artifact this project's
   existing gate sequence (CTO → Red Team → Development → Code Review →
   QA → Security) already knows how to ship.
8. **Elevation/revocation**: this is where Claude Code's own native
   permission "ask" outcome is a real, already-available mechanism —
   ground-truth facts describe hooks denying via exit code 2 or a JSON
   `permissionDecision`; the platform's existing behavior for a command
   matching neither an explicit allow nor an explicit deny rule is an
   interactive prompt to whoever is at the terminal. Because these are, by
   this document's own scoping (§1), *supervised* sessions — a human is
   watching — "ask" genuinely reaches a live human, in real time, without
   this project inventing anything new. This mechanism structurally
   cannot work for `automation.py`'s unsupervised poller (no one is there
   to answer), which is exactly why that path is correctly zero-tool
   instead, not "ask"-gated.
9. **Audit**: does not exist today and must be built — every hook
   denial (and, worth doing at the same time, every "ask" that was
   answered yes) should be written to a durable log, not just left on the
   terminal. A new table (same shape as `automation_events`) or a
   dedicated log file is a small, cheap addition; not built as part of
   this investigation.
10. **Wrong-scope failure mode**: fails toward *more restrictive* by
    construction — a too-narrow pattern list produces a visible denial the
    supervising human sees immediately and can override live via "ask,"
    or fix by editing the (version-controlled, reviewed) hook script. A
    too-broad pattern list produces no visible signal at all — this is a
    real, standing risk that requires the same periodic Red Team/Security
    review discipline this project already applies to everything else;
    it is not self-correcting.

**Net assessment**: real, harness-enforced, meaningfully shrinks blast
radius against the realistic threat model (§1, cases 1–2) for all four
remaining roles — but does **not** achieve airtight confinement against a
deliberately adversarial agent (§1, case 3), and does **not** close the
"legitimate-looking `opsdb.py` write" vector Phase 3A's own disclosure
already names. This is a genuine reduction, not a closure.

### 3.3 Task-level structured scope — the Founder's proposed narrowing, corrected

The Founder's floated design ("task-level: only `/src/payments/**`...")
is directionally sound but, as stated, has one load-bearing gap: **"the
system derives the required capabilities from the task" cannot itself be
an LLM inferring intent from a free-text task description and feeding
that inference directly into an enforcement decision.** That is not a
security boundary — it is a second model's guess, exposed to the exact
same prompt-injection surface (§1, case 2) the boundary is supposed to
defend against, and gameable by construction: a task description crafted
to make a broad request look ordinary ("standard maintenance task,
touches shared config across the app") will make an LLM-derived capability
list look "normal" too, because the LLM has no independent way to verify
the description is accurate.

**The corrected version**: task-level narrowing is real only when it is
**structured data, declared by a human (or a reviewed CTO architecture
step) at task-creation time, never inferred at invocation time**. Concretely:
a new nullable `tasks.allowed_paths` (JSON array) column, filled in by CTO
during architecture review for tasks where a narrower scope than the
role's default is warranted, defaulting to "no narrowing — full role
policy applies" when absent. §3.2's hook, when present, reads this field
and intersects it with the role-level policy — the hook script does the
comparison (a plain, deterministic subset check, the same shape every
other `opsdb.py` write-path validation in this codebase already uses), not
a model judgment call.

1. **Boundary**: a specific, human-declared path list per task, layered
   under the role-level hook from §3.2.
2. **Enforcement**: the same hook mechanism as §3.2 — real, harness-level
   — reading a real database column, not an inferred value.
3. **Bypass**: identical to §3.2's own bypass analysis (subprocess
   indirection, encoding) — narrowing the *paths* considered doesn't
   change *how* the check is evaded, only what it's checking against.
4. **Credential/DB reach**: same as §3.2 — narrower paths don't touch the
   `opsdb.py`-write vector at all.
5. **Uniform across roles?** Applies most naturally to `developer` (whose
   work is genuinely file-scoped); less naturally to `qa` (needs to run
   the whole app, not just a file subset) or `cto` (needs broad read
   access to reason about architecture); optional/absent by default for
   all, narrowing applied only where CTO judges it adds real value.
6. **Cost to legitimate work**: real if the declared scope is wrong (see
   below) — this is the direct answer to the Founder's own question 10.
7. **Implementation cost**: one schema column + hook logic to read/compare
   it — small, additive to §3.2, not a separate system.
8. **Elevation/revocation**: same "ask" mechanism as §3.2 for an in-session
   need; a genuinely wrong or too-narrow declared scope is fixed by a
   human editing the task's `allowed_paths` field, an explicit, auditable
   act (the same discipline every other structured-data write in this
   schema already follows) — never a model requesting its own scope
   widened.
9. **Audit**: the task record itself is the audit trail for what scope was
   declared and by whom/when (same convention `decisions`/`task_status_
   history` already use); hook denials logged per §3.2.
10. **Wrong-scope failure mode — the Founder's own required question,
    answered directly**: too narrow → visible denial, human either widens
    the declared scope or grants a live "ask" exception, no silent
    failure. Too broad → no different from having no narrowing at all;
    same standing "needs periodic review" risk as §3.2's own pattern list.
    Task changes mid-flight → the declared scope does not auto-update; it
    fails toward *more* restrictive (the agent hits denials for the newly
    needed path until a human updates the record) — the correct failure
    direction, and the same one QA-fail/reject-and-return-to-development
    already uses elsewhere in this project's workflow.

**Does this answer the Founder's "can it be gamed" question?** As
originally floated (LLM-derived, per-task, invocation-time) — yes,
gameable, and I do not recommend building it that way. As corrected here
(human-declared, structured, defaulting to role policy) — no more gameable
than any other structured write in this schema, because it is one.

### 3.4 Git worktree per task — real, but only as a *component*, not alone

A dedicated worktree checked out per task gives Developer a distinct
working directory. **On its own this provides zero security boundary**:
the agent runs as the same OS user regardless of which directory it
started in, and nothing stops `cd ..` (or an absolute path) from reaching
anything else that user can read/write — including
`.founder_credential.json`. Worktrees solve a *different*, real problem
(parallel Developer sessions not colliding on working-tree state) and are
easily mistaken for an access-control mechanism when they are not one.

**Only useful in combination**: paired with §3.2's hook doing real,
`.resolve()`-based path containment against the worktree's own directory,
a worktree gives the hook a clean, natural boundary to express
"contained to this task" against, and gives §3.3's `allowed_paths` a
concrete filesystem location to mean. Recommended as the natural
expression of task-level containment for `developer` specifically — not
as a standalone control, and not claimed as one.

### 3.5 Broker / wrapper-script pattern (no raw Bash)

Replace Bash for a role with a small, fixed set of parameterized,
project-owned wrapper scripts (`run_project_tests.sh`, `safe_git_commit.sh`,
`git_diff_scoped.sh`) invoked either via an MCP tool grant or via a hook
that denies every Bash invocation *except* the literal wrapper-script
call. This is the strongest available control that still requires a real
tool grant, because the wrapper itself is fixed, non-agent-authored code
doing its own internal, typed validation (exactly the pattern
`agent_runtime.py`'s `Popen`/`automation.py`'s `git` calls already
establish: fixed argv, `subprocess.run` never a shell string, paths
validated before use) — the model cannot compose an arbitrary command,
only invoke one of a fixed set of pre-reviewed operations with validated
parameters.

1. **Boundary**: a fixed, finite set of named operations, each internally
   validating its own inputs before touching the filesystem/subprocess.
2. **Enforcement**: real, two layers — the hook denying anything but the
   wrapper invocation itself, plus the wrapper's own internal Python
   validation (not string-pattern matching, actual `Path.resolve()`/
   allowlist checks, the same discipline Phase 3A's C1 fix already
   established for SHA/path validation).
3. **Bypass**: closes the subprocess-indirection gap named in §3.2 point
   3, *for the operations the wrapper covers* — since the agent literally
   cannot invoke anything else via Bash, there is no `python3 -c` escape
   hatch left open. Does **not** close it for anything the agent's other
   granted tools (`Read`/`Write`/`Edit`, if still present) can still do
   directly — a broker only closes the Bash surface, not the whole tool
   category.
4. **Credential/DB reach**: same as §3.2 — narrows *how* files/subprocesses
   are touched, does not touch the `opsdb.py`-legitimate-write vector.
5. **Uniform across roles?** Natural fit for `qa`/`devops` (their
   legitimate operations are genuinely enumerable: run tests, run the app,
   check build state, record a deployment). Poor fit for `developer`/`cto`
   — see cost, below.
6. **Cost to legitimate work**: **high for `developer` specifically.**
   Real iterative development needs arbitrary debugging commands, ad hoc
   one-liners, exploring the filesystem, installing a justified new
   dependency — none of which map to a small, fixed operation set without
   either (a) an unreasonably large wrapper library that becomes its own
   maintenance burden, or (b) crippling Developer's actual job. Not
   recommended as Developer's primary interface; reasonable as a
   *convenience* layer alongside general Bash (a blessed
   `safe_git_commit.sh` a Developer is *encouraged*, not *forced*, to use)
   rather than a replacement for it.
7. **Implementation cost**: moderate — each wrapper is a small, reviewable
   script, but a broker covering enough operations to not cripple a role
   is real, ongoing work as that role's needs evolve.
8–10. Same shape as §3.2 for elevation/audit/failure-mode, with the
   caveat that "elevation" for a broker-restricted role genuinely means
   "a human runs a different, fully tool-bearing session for the one-off
   need" more often than §3.2's live "ask" — because a fixed operation set
   has less room for an in-band exception.

**Recommended scope**: `qa`/`devops`, as their primary interface where
practical; `developer`/`cto`, only as an optional convenience layer, never
a replacement for general (hook-gated) Bash.

### 3.6 OS-level user separation (a distinct OS user per role)

The one option that would close the subprocess/symlink/encoding bypass
gap every hook-based option above genuinely has, because it is kernel-
enforced, not pattern-matched. Real `useradd` per role, real `chown`/
`chmod` on `.founder_credential.json` and anything else Founder-only,
subagent invocation via `sudo -u <role-user> claude --agent <role> ...`.

**Named, but not recommended as a first step, for a concrete, structural
reason**: this system's *supervised* invocations (the ones this whole
document is scoped to) run as Claude Code's native Task-tool subagent
delegation — inline, within the same interactive session a human is
watching, which (per §2(A)'s flagged, unverified-but-likely platform
limit) runs in-process, same OS user as the parent session. Real OS-user
separation would require abandoning that live, inline delegation pattern
entirely for these seven roles, in favor of the out-of-process,
CLI-subprocess pattern `agent_runtime.py` already uses for the
*unsupervised* paths — which changes what "a human watching tool calls in
real time" structurally means (watching subprocess output/logs, not
directly interacting inline), needs passwordless `sudo` configured for the
Founder's own account (itself a new, security-relevant surface), and needs
real file-ownership engineering across every path every role legitimately
needs shared access to (the git repository, `operations.sqlite3`). This is
the single largest architecture change on this list — genuinely the
strongest available guarantee, but disproportionate as a first move for a
`severity=medium`, local-only, no-external-traffic risk. Worth a real
proposal later if the Founder decides the residual gap in §3.2/§3.5 is
unacceptable; not proposed here as the first implementation step.

### 3.7 Bubblewrap/namespace sandboxing, invoked directly by this project

A lighter-weight version of §3.6 — wrap the `claude` subprocess launch in
a project-controlled `bwrap` invocation (new mount/PID/user namespace,
explicit `--ro-bind`/`--bind` for only what the role needs) rather than
relying on Claude Code's own built-in, documented-imperfect sandbox flag.
Kernel-enforced, immune to symlink tricks within its own namespace (the
path simply doesn't exist there), and fits this project's existing
"fixed-argv subprocess invocation" convention (`bwrap` prepended to the
same `Popen` call `agent_runtime.py` already makes).

**One specific, load-bearing gap, worth naming precisely rather than
glossing over**: for the system to keep functioning, `operations.sqlite3`
must be bind-mounted read-write into every sandboxed role's namespace —
which means sandboxing the *filesystem* does nothing to stop the exact
vector `SECURITY.md`'s own Phase 3A disclosure already names: a role
writing a plausible `CODE_REVIEW`-transition or `handoffs` row via
`opsdb.py` directly. Closing *that* requires brokering database writes
through `opsdb.py`'s own validated functions only (never raw
`sqlite3`-CLI or file access) — a separate control this option does not
provide by itself. Also flagged: unprivileged user-namespace creation may
be restricted by kernel configuration on the actual host this runs on —
this needs a feasibility spike before being taken further, not a
committed first step given that unresolved uncertainty.

### 3.8 The native `permissions.allow`/`deny` engine (settings.json), as a complement to hooks

Distinct from hooks, and worth naming: ground-truth facts #3–#4 describe a
real, harness-enforced, shell-operator-aware allow/deny engine, with
absolute deny rules evaluated first. This is a lower-effort complement to
§3.2's hooks for the simplest, highest-confidence deny rules (e.g., a flat
`deny: Bash(*credential*)`) — cheaper to write than a hook script for
static patterns, though it inherits the exact same prefix-matching
fragility (fact #3's own documented caveats) and the same subprocess-
indirection gap. Recommended as a first, cheap layer underneath the
richer hook logic in §3.2, not a replacement for it — hooks are needed for
anything requiring real path resolution (symlink-safe checks) or
per-task data lookups (§3.3), which a static `settings.json` pattern list
cannot do.

## 4. The Founder's proposed policy flow — assessed directly

*"Founder authorizes a policy (once) → Chief of Staff understands the task
→ system derives required capabilities → policy check confirms this is
normal for role/task → agent gets a bounded workspace/toolset → work
proceeds → unusual escalation goes to the Founder live."*

**Is this actually safe? Does "normal" have a well-defined, enforceable
meaning? Who/what computes it? Can it be gamed by a crafted task
description?**

As literally stated — with an LLM (Chief of Staff or any model) performing
the "derives the required capabilities" and "policy check confirms this is
normal" steps — **no, it is not safe, and yes, it can be gamed.** Both
steps are model judgment calls, not enforcement. A "policy check" that is
itself an LLM inference is advisory text with an official-sounding name,
not a technical boundary — it is exactly the "ask the agent nicely" outcome
this document was asked not to manufacture around. A task description can
be worded (by a human mistake, or by content an attacker with
`opsdb.py`-write access already controls, per `SECURITY.md`'s own Phase 3A
disclosure) to make a broad request read as ordinary, and neither "the
Chief of Staff understood the task" nor "the policy check confirmed this
is normal" would catch that, because neither step is grounded in anything
that couldn't itself be the thing being manipulated.

**The flow becomes real once two substitutions are made**, both already
implicit in §3.2/§3.3 above:

1. **"System derives the required capabilities" → replaced by "the
   role-level policy is static, pre-authored, version-controlled, and
   changed only through this project's own existing architecture-review
   process (CTO → Red Team), exactly like any other architecture
   decision."** There is no per-task derivation step for the common case
   at all — "normal for this role" is a fixed table, not a fresh
   inference.
2. **"Policy check confirms this is normal" → replaced by "a deterministic
   hook script performs a real subset/pattern check against that fixed
   table (plus, optionally, a human-declared `allowed_paths` narrowing,
   §3.3) — never a model judging plausibility."** This is what a hook
   already is natively; nothing new needs inventing here, only building
   the hook itself.

With those two substitutions, the remainder of the Founder's flow survives
intact and becomes genuinely enforceable: "Founder authorizes a policy
once" = CTO/Security author the hook and get Founder sign-off, the same
way every other architecture artifact in this project already ships.
"Agent gets a bounded toolset" = the hook's real, harness-checked outcome.
"Unusual escalation → Founder for a real-time decision" = Claude Code's
own native interactive "ask" permission outcome, already available for
free in a supervised session, per §3.2 point 8 — nothing needs to be built
for this specific piece.

**What this correction does NOT solve**: it does not make "normal" mean
anything for the case where the *static* policy itself was authored too
broadly, or where a human declaring a task's `allowed_paths` gets it wrong
— those remain real, standing risks requiring the same periodic review
discipline (Red Team/Security) this project already applies to every other
artifact it ships, not a self-correcting mechanism.

## 5. What remains genuinely open — stated plainly, not softened

- **A deliberately adversarial supervised agent** (§1, case 3) can still,
  with enough deliberate effort, evade any pattern-based hook via
  subprocess indirection, encoding, or a novel syntax the pattern list
  didn't anticipate — for the four roles that genuinely need general Bash
  (`developer`, `qa`, `cto`, `devops`). This is not closed by anything in
  this document, and cannot be closed by anything short of §3.6/§3.7's
  real kernel-level isolation, which this document does not recommend as
  a first step given cost/uncertainty relative to this risk's own
  `severity=medium` rating.
- **The `opsdb.py`-legitimate-write vector** — an agent (or any same-OS-
  user actor) writing a plausible, well-formed row directly via
  `opsdb.py` to influence downstream automated or human behavior — is not
  closed by any filesystem/subprocess-scoping option in §3. `SECURITY.md`
  already discloses this for Phase 3A's automation specifically; nothing
  here changes that disclosure. Closing it would require brokering
  database writes themselves (a materially different, separate
  investigation from Bash scoping) — named in §3.7, not designed here.
- **`.founder_credential.json` read + `PTRACE_ATTACH` to `server.py`** are
  concretely, directly closed by §3.2's denylist *as long as the pattern
  actually matches the attempted command* — real, harness-enforced
  narrowing, genuinely better than today's nothing, but not a kernel-level
  guarantee against a determined, adversarial bypass attempt.

**Is this "ask the agent nicely, and hope"?** No — for three of seven
roles (§3.1), the answer is a real, structural elimination of the Bash
attack surface using code this project already built and reviewed once.
For the other four (§3.2/§3.3), the answer is real, harness-enforced
narrowing — genuinely stronger than today's "whole tool category" default,
genuinely closes the two concretely-named credential/session vectors — but
it is honestly, not merely as a hedge, **not** airtight against a
determined adversarial bypass, and it does **not** touch the
`opsdb.py`-write vector at all. That gap is real and this document does
not manufacture a fix for it.

## 6. Recommendation

**Disposition: REDUCE-with-specifics — not CLOSE, not REMAIN-OPEN
unchanged.**

`risks.id=3`'s own current wording ("Bash permissions cannot be scoped
below the tool-category level") is, in the narrow technical sense,
**false** — PreToolUse hooks, per ground-truth facts #1–#2, do let this
project scope access below the tool-category level, per role and
optionally per task. This project has simply never used that capability.
The risk's description should be corrected to reflect this precisely (not
by me — this is exactly the kind of major-decision language change that
goes through `python3 ops/db/opsdb.py decision-record`, not a silent edit),
while its practical open status is preserved for the residual gaps named
in §5, which are real.

**Recommended course, in priority order**:

1. **Extend Phase 3A's already-built zero-tool, Python-assembled-
   transcript pattern to `code-review`'s human-triggered invocation, and
   to `security` and `red-team`'s normal invocations (§3.1).** This closes
   `risks.id=3`'s exposure completely, not narrows it, for three of seven
   roles, using code and a pattern this project has already designed,
   built, and had independently reviewed twice. Zero new infrastructure.
2. **Author the first PreToolUse hook — a role-level Bash denylist for
   `developer`** (the highest-flexibility-need, highest-risk role) per
   §3.2, covering the two concretely-named vectors
   (`.founder_credential.json`, `ptrace` against `server.py`) plus repo-
   root containment. Extend to `qa`, `cto`, `devops` next, tuning
   allowlist-vs-denylist shape per role as described.
3. **Add `tasks.allowed_paths` and wire it into the same hook (§3.3),
   human-declared only, never LLM-inferred** — as a later refinement, not
   a prerequisite for step 2's own value.
4. **Do not pursue §3.6 (OS-user separation) or the full §3.5 broker
   pattern for `developer`/`cto` as a next step** — named, real, and
   available if the Founder later judges the residual gap in §5
   unacceptable, but disproportionate cost/uncertainty relative to this
   risk's current `medium` severity and this project's single-operator,
   no-external-traffic scope.

**Smallest concrete first implementation step** (not implemented here —
named only, per the Founder's directive): build the human-triggered,
on-demand Code Review path described in §3.1 — reusing `automation.py`'s
existing diff/file-content assembly functions verbatim, adding one new
synchronous invocation path (HTTP route or CLI entry point), removing
`Bash, Grep, Glob` from `code-review`'s `tools:` frontmatter, and folding
the `code-review` skill's guidance into the persona note the same way the
existing "Automated-invocation mode" section already does. This requires
no hooks, no `settings.json`, no OS changes, and no new data model — it is
a strict extension of code this project has already shipped and had PASS
twice.
