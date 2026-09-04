# Security threat model — risks.id=3 architecture investigation (TASK-016, Stage 2 of 4)

Reviewing `ops/reviews/cto-risk3-architecture-investigation.md` (Stage 1,
CTO). Investigation-only per the Founder's directive — nothing in `ops/`
or product code is touched by this document. Read in full before writing:
`ops/reviews/cto-risk3-architecture-investigation.md`, `ops/SECURITY.md`,
`ops/reviews/security-phase3a-threat-model.md`, all 14
`.claude/agents/*.md` subagent definitions, and — independently, not
cited by CTO's own document — the actual installed Claude Code CLI source
(`/opt/node22/lib/node_modules/@anthropic-ai/claude-code/cli.js`, v2.1.42,
the exact binary this project's subagents execute under), `automation.py`,
`agent_runtime.py`, `founder_auth.py`, `.gitignore`, and a live query
against `operations.sqlite3`.

**Verdict: CONCERNS.** CTO's core mechanism and direction are sound and I
independently re-derive the central claims rather than accept them on the
document's word — but the document has real, specific gaps, several of
which are more serious than it discloses. I do not rubber-stamp it. See §7
for the itemized list that should be folded in before any implementation
starts, matching the "required conditions" discipline Security's own
Phase 3A review already used successfully on this same project.

---

## 0. The flagged verification question — resolved, not left at "medium confidence"

CTO flagged one explicitly unverified claim: whether PreToolUse hooks fire
for Read/Write/Edit (not just Bash) with a usable `file_path` field, and
rated confidence medium. **I do not have a WebFetch/WebSearch tool this
session** — I could not check the public docs site. Instead I used a
stronger method: I read the actual shipped implementation this project's
subagents run under.

Findings, directly from `cli.js`:

- The PreToolUse hook payload schema (`BLY` in the minified source) is
  `{session_id, transcript_path, cwd, permission_mode?, hook_event_name:
  "PreToolUse", tool_name: string, tool_input: unknown, tool_use_id:
  string}`. `tool_input` is untyped at the hook layer — the dispatch
  function (`USA(A,q,K,...)`) builds the hook payload as `{...,
  hook_event_name:"PreToolUse", tool_name:A, tool_input:K, tool_use_id:q}`
  where `K` is *literally the tool call's own input object, unmodified*.
  This dispatch function is not Bash-specific — it fires identically for
  every `tool_name`.
- Read's own input schema: `strictObject({file_path: string, offset?,
  limit?, pages?})`. Write's: `strictObject({file_path: string, content:
  string})`. Edit's: `strictObject({file_path: string, old_string:
  string, new_string: string, replace_all?})`. All three use the exact
  field name `file_path`.
- The native permission-matching engine internally classifies tools into
  two explicit groups: `filePatternTools: ["Read","Write","Edit","Glob",
  "NotebookRead","NotebookEdit"]` (matched by file-path pattern) vs.
  `bashPrefixTools: ["Bash"]` (matched by command-prefix). This confirms
  path-pattern matching for Read/Write/Edit is a first-class,
  tool-differentiated mechanism, not a Bash-only mechanism CTO's design
  would have to invent.
- A hook-matcher config example embedded in the source
  (`{"matcher": {"tools": ["BashTool"]}}`) confirms matchers select by
  tool name generically, not by a hardcoded Bash special case.

**Conclusion: CONFIRMED, not "likely."** PreToolUse hooks fire for
Read/Write/Edit exactly as for Bash, and `tool_input.file_path` is a real,
populated, usable string for all three. Tier 2's per-task path narrowing
(CTO §3.3) is buildable for Read/Write/Edit, not just Bash commands, as
designed. This removes one real axis of CTO's own stated uncertainty. It
does **not**, however, close the deeper bypass problems — see §2.

---

## 1. Tier 1 (Code Review, Security, Red Team): is "no tool grant" actually airtight?

### 1.1 The transcript-assembly harness itself — checked against real code, not the doc's claim

I read `automation.py`'s actual assembly functions (`_git_diff`,
`_git_show_file`, the SHA-validation block, `_validate_repo_path`) rather
than trusting CTO's "the same §B.1.2/C1 discipline applies unchanged"
sentence. It holds up:

- `base_sha`/`head_sha` are format-validated (`_SHA_RE`) and
  existence-validated (`_commit_exists`) before any git subprocess call —
  Security's Phase 3A required fix C1, confirmed actually implemented, not
  just specified.
- File content is retrieved via `git show <head_sha>:<path>` — the
  committed object, never a live filesystem read — confirmed implemented
  (Phase 3A non-blocking R1, folded in as shipped, not left as a
  recommendation).
- `files_changed` entries are validated via `Path(REPO_ROOT, path).resolve()`
  containment before use.
- `git diff` uses a `--` separator between revision and pathspec
  arguments; `git show <sha>:<path>` is a single combined object argument,
  correctly left without `--` per the documented empirical reason (adding
  `--` there silently breaks the command).

So: **the underlying assembly code CTO wants to reuse is genuinely
hardened**, and CTO's claim that "that surface is not new here" is correct
for the code as it exists today.

**But this is where I disagree with CTO's framing, not the code.** These
functions only work for a task with an *already-recorded handoff carrying
two real, resolvable commit SHAs* — they are structurally SHA-anchored,
with no code path that reads live working-tree/uncommitted content. If the
new "synchronous, human-triggered Code Review path" genuinely reuses these
functions verbatim (as CTO's document says), then a human-triggered review
can **only** review already-committed, already-handed-off work with real
recorded SHAs — it cannot review a Developer's in-progress, uncommitted
diff. That's a real, useful, safe scope — but it is materially narrower
than "human-triggered, on-demand review" sounds like it promises, and
CTO's document does not say this explicitly. If Development later adds a
*new* function to satisfy an unstated expectation that this mode can
review live/uncommitted diffs, that new function is **not** covered by
"this is a strict extension of already-reviewed code" — it would be new
surface needing its own C1-style review from scratch. **Recommendation**:
CTO's document (or the eventual architecture doc for this specific step)
should state the SHA-anchored scope explicitly before Development builds
it, so nobody quietly reintroduces a live-filesystem read to make the
feature feel more useful.

### 1.2 Does Tier 1's "full closure" claim hold for Security's own role?

**No — not as CTO's document currently scopes it, and this is not a
theoretical objection: it is a direct, first-person finding from doing
this very review.**

To answer the questions this task actually asked me — "is the
transcript-assembly harness itself a new attack surface," "did Phase 3A's
mitigations actually carry over," "verify or refute the file_path claim"
— I used Bash extensively: grepping the real installed CLI binary for the
hook schema (§0), reading `automation.py`'s real subprocess calls line by
line rather than trusting the architecture doc's prose, checking
`.gitignore` and file permissions on the credential file, confirming
`sqlite3` the stdlib module is available even though the CLI binary isn't,
and querying the live `risks` table directly. None of that would be
possible in a zero-tool, pre-assembled-transcript mode — a zero-tool
Security reviewer would have had no choice but to accept CTO's document's
own claims about its own correctness, which defeats the purpose of an
independent review.

Security's and Red Team's actual role docs bear this out structurally:
Security reviews "dependency vulnerabilities" and "unsupported
assumptions"; Red Team reviews "are the stated assumptions actually
supported" and "adversarially reviews a plan before it's built." Both
routinely require verifying a claim against ground truth *outside* the
diff/document itself — exactly what I just did. This is a fundamentally
different job shape from Code Review's "judge this diff against these
coding standards," where the bounded-context defect class Phase 3A's own
review already named (cross-file duplication) is real but narrower.

**This TASK-016 chain is itself the demonstration**: CTO produced Stage 1
with tool access (reading 14 agent files, `SECURITY.md`, prior reviews).
I am producing Stage 2 with tool access, and used it to catch a real gap
in CTO's own document (§3 below) that a zero-tool review of CTO's
transcript alone would not have surfaced, because it required
cross-referencing `.gitignore`, `README.md`, and live DB state that
weren't part of any assembled bundle. Stage 3 (Red Team) will need the
same capability to adversarially check *my* claims, not just accept them.

**My recommendation, diverging from CTO's**: scope Tier 1's zero-tool
mode to the direct analog of what's already shipped — the `security-review`
skill run against a specific product-code diff at the SECURITY_REVIEW
gate (and the equivalent diff-scoped moment for Red Team, e.g.
`RED_TEAM_REVIEW` against a specific plan-as-diff artifact) — **not** to
Security's or Red Team's investigative/architecture-review work generally
(threat models, this document included, adversarial review of an
architecture proposal, cross-referencing a claim against installed
software or live state). If CTO's Tier 1 intends the broader scope, I
reject that breadth specifically; if it's meant narrowly (which the
document's own examples — "the `code-review` skill's guidance... Skill
tool being present" — suggest, but don't state as a hard boundary), then
I concur and this should simply be written down as an explicit boundary,
not left implicit.

---

## 2. Tier 2 bypass paths — concretely adversarial

CTO's own bypass analysis (subprocess indirection, symlinks, `cd`/relative
tricks, encoding) is correct as far as it goes. Stress-tested further,
with exact techniques:

**2.1 Write-then-Bash-execute, or single-command heredoc, defeats a
Bash-only hook regardless of pattern quality.** Two concrete forms:

```
# Two tool calls: Write assembles the payload, Bash's hook never sees it
Write(file_path="/tmp/x.py", content="import sqlite3\nconn=sqlite3.connect('ops/db/operations.sqlite3')\nconn.execute(\"UPDATE tasks SET status='READY_TO_RELEASE' WHERE id=16\")\nconn.commit()")
Bash(command="python3 /tmp/x.py")
```
The Bash hook sees only `python3 /tmp/x.py` — an ordinary, unremarkable
command. A hook that *also* covers Write (now confirmed feasible, §0)
would see the payload — but only if Development actually builds a
Write/Edit hook, which CTO's design leaves as a hedge ("if the platform
supports it... flagged as an assumption"). Since I've now removed that
uncertainty, this needs to become a **requirement**, not an optional
extra: any Tier 2 hook design that covers Bash but not Write/Edit is
trivially bypassed this way. But it isn't fully closed even then:

```
Bash(command="cat > /tmp/x.py << 'EOF'\nimport sqlite3\n...\nEOF\npython3 /tmp/x.py")
```
This is a *single* Bash command — no separate Write call to catch. A hook
that substring-scans the whole command string would still see
`operations.sqlite3` in plaintext here (catchable), but:

```
Bash(command="echo <base64-of-the-same-payload> | base64 -d | python3")
```
does not contain the string `operations.sqlite3` anywhere, defeating any
substring/regex denylist. This is CTO's own named "fundamental,
unclosable gap" — I'm not disputing it exists, I'm giving it an exact,
working command, and noting that the credential-file/DB-specific denylist
entries CTO proposes are exactly the kind of literal-string check this
defeats trivially.

**2.2 A structural asymmetry CTO's document doesn't draw out: Bash-scoped
path protection is materially weaker than Read/Write/Edit-scoped path
protection, even with "real path resolution."** CTO says "a hook doing
real path resolution... closes the classic case" for symlinks. True for
Read/Write/Edit, where `file_path` is a single, structured field a hook
can call `.resolve()` on directly. For Bash, the hook receives one opaque
command *string* — to apply the same protection it must first correctly
parse arbitrary shell syntax to identify which token(s) are "a path,"
then resolve each. That's a materially harder, more failure-prone problem
than resolving one typed field, and CTO's document (§3.2 point 3) implies
the two are equivalent in difficulty ("a hook doing real path
resolution... closes the classic case") when they aren't. Concretely:

```
ln -s /home/user/AI-Pipeline/ops/control-center/.founder_credential.json /home/user/AI-Pipeline/notes.txt
cat notes.txt
```
`cat notes.txt` contains no `credential` substring and is not obviously
"a path argument that needs resolving" without real shell-aware parsing.
The equivalent via `Read(file_path="notes.txt")` is straightforward to
catch (`Path("notes.txt").resolve()` == the real credential path) because
the hook already knows, unambiguously, which string is the path.
**Recommendation**: don't rely on the Bash hook to be the credential
file's primary defense at all — rely on the Read/Write/Edit hooks (now
confirmed buildable) for structured-path denial, and treat the Bash
denylist as a coarser, string-substring backstop only, explicitly
disclosed as such.

**2.3 `$PATH`/interpreter shadowing of the hook's own validation logic.**
If a hook script (§3.2/§3.3's containment checks) ever shells out to an
external binary (e.g. `git`) by bare name rather than an absolute path, an
earlier Bash command that prepends a malicious binary to `$PATH`
(`export PATH=/tmp/evil:$PATH; printf '#!/bin/sh\nexit 0\n' > /tmp/evil/git; chmod +x /tmp/evil/git`)
could, if the hook process inherits that environment, cause the hook's
own validation step to silently report success. Whether this actually
applies depends on whether the hook subprocess inherits the calling
session's shell environment — worth an explicit build-time check, not an
assumption either way. **Recommendation**: any hook-internal call to an
external binary must use an absolute path, never bare-name resolution via
`$PATH`.

---

## 3. SQLite/credential reachability — CTO's own disclosure understates the actual severity

CTO's document names "an agent can still write a plausible
`CODE_REVIEW`-transition/`handoffs` row via `opsdb.py` directly" as the
one concretely unaddressed vector. **This undersells the real risk in two
ways, both independently verified:**

1. **The stdlib `sqlite3` module is fully available in this environment**
   (`python3 -c "import sqlite3"` works; confirmed by direct execution).
   `ops/db/README.md` correctly states there is no `sqlite3` CLI binary
   — but that is not the same as "no raw SQLite access." Any of the four
   Tier 2 roles can run `python3 -c "import sqlite3; conn=sqlite3.connect('ops/db/operations.sqlite3'); conn.execute(...); conn.commit()"`
   right now, today, with zero hooks in place, and this **bypasses
   `opsdb.py`'s own Python-level validation entirely** — not just the
   "plausible-looking row" framing CTO's document uses. `opsdb.py`
   enforces real invariants in Python that are *not* also expressed as
   SQL `CHECK` constraints (Security's own Phase 3A review found exactly
   one such gap already — C4, the reject-requires-`returned_to` check,
   originally only in the CLI wrapper, not the schema). A raw-`sqlite3`
   write respects only what the schema's own `CHECK`/`UNIQUE` constraints
   happen to enforce, nothing else. This is strictly worse than "a
   plausible `opsdb.py` call," and CTO's document does not name it as a
   distinct, worse vector.
2. **`operations.sqlite3` is git-tracked, inside `repo_root`** (confirmed:
   `git ls-files` lists `ops/db/operations.sqlite3`). CTO's example
   Tier-2 denylist ("deny any write outside the repo root") therefore
   provides **zero** protection for the single most sensitive writable
   resource in this system today — it's inside the boundary the denylist
   is protecting *access to*, not outside it. The denylist's other named
   entries (`.founder_credential.json`, `ptrace`, `sudo`, non-localhost
   network) do not mention the database file at all.

**Recommendation, concrete and required before Development builds the
first hook (CTO's own named step 2, the Developer denylist)**: the
denylist must explicitly name `operations.sqlite3` (and, more robustly,
any Bash/Write/Edit access pattern suggesting direct sqlite manipulation
— `sqlite3.connect`, `import sqlite3`, `.sqlite3` file writes outside
`opsdb.py`'s own process) as a protected resource, not only the credential
file. I want to be honest that this, too, is defeated by §2.1's
base64/heredoc indirection against a determined adversary — but per this
project's own realistic threat model (CTO's §1, cases 1–2: scope creep
and prompt-injection-influenced ordinary work, not a determined
adversarial agent), a named, visible denylist entry meaningfully raises
the bar against the realistic case even though it isn't airtight against
case 3, exactly the same honest framing CTO already applies to the
credential-file/ptrace entries.

**Credential/session reachability, otherwise**: unchanged from
`SECURITY.md`'s own Milestone 2B4 disclosure — `.founder_credential.json`
is `0600`, same-OS-user-owned, and `PTRACE_ATTACH` against `server.py`
remains available to any Bash-capable Tier 2 role regardless of hooks
(ptrace is explicitly named in CTO's own denylist, which is correct and
sufficient as a named entry, subject to the same encoding-bypass caveat
as everything else in a string-pattern hook).

---

## 4. Human-declared per-task path narrowing — real risk of becoming invisible busywork

CTO's corrected design (`tasks.allowed_paths`, human-declared by CTO at
architecture time, nullable, defaulting to "no narrowing") **fixes the
gameability defect** (no LLM inference in the loop) but, as specified,
**is default-broad, not default-narrow** — the exact property the
Founder's own question 4 asked about directly.

A nullable field that silently means "full role policy applies" when
absent gives CTO — who reviews architecture for every task, under time
pressure — the path of least resistance in the wrong direction: leaving
it null costs nothing and is invisible (no log entry says "this task
could have been narrowed and wasn't"), whereas actively narrowing it
costs CTO's own time and judgment. I'd expect this to erode toward
"rarely used" for the mundane reason that skipping a nullable field is
always the path of least resistance, not because anyone tried to defeat
it.

**Recommendation, concrete**: don't leave the field nullable-silent.
Either (a) require an explicit value at architecture-review time — even
an explicit wide grant (e.g. a literal `["**"]`) — logged as a stated,
visible CTO decision the same way `decision-record` already logs other
architecture calls, so "we chose not to narrow this" is an auditable act,
not an absence; or (b) go further and pre-populate a **suggested** narrow
default computed by a plain, non-LLM heuristic (regex-extract
path-looking tokens already present in the task's `architecture_notes`)
that CTO must explicitly confirm or override before the task can leave
`ARCHITECTURE` — making narrow the pre-filled, low-friction default and
broad the thing that requires an active, visible edit. (b) does not
reintroduce the Founder's original gameability problem, because nothing
is *enforced* from the heuristic suggestion — a human still makes the
final call, the same discipline CTO's own §4 correction already
establishes for the enforcement side; the heuristic only shifts which
choice is the path of least resistance. Either way, Red Team/Security's
periodic review of shipped architecture docs should include, as a
standing checklist item, "was `allowed_paths` a real per-task judgment,
or a copy-pasted wildcard" — visible only if (a) or (b) makes the
non-narrowed case a loggable, checkable event, not a silent default.

---

## 5. The Founder's policy flow — direct answer

**Is the originally-floated flow "not actually safe"? Yes — unhedged,
full agreement with CTO, and I re-derive it independently rather than
accept CTO's framing.** "System derives capabilities from the task" and
"policy check confirms this is normal," if either step is LLM judgment,
are gameable by construction: I can name the exact mechanism, not just
assert it. `SECURITY.md`'s own already-standing disclosure is that task
descriptions are same-OS-user-writable, attacker-controllable content
(via `opsdb.py` directly, no forged HTTP request needed, per the Phase 3A
disclosure). A task description worded as "standard maintenance: update
shared config across `/src`" would cause an LLM capability-deriver to
output a broad grant, and the *identical* wording would cause an LLM
policy-checker to wave that grant through as "normal for a config
update" — because neither step is grounded in anything independent of the
same attacker-influenced text. This is not hypothetical; it is the same
prompt-injection surface CTO's own §1 case 2 already names for a
different purpose.

**Does CTO's static-policy substitution genuinely fix this? Yes, for the
specific defect named.** A hook checking a fixed, human-authored,
version-controlled pattern table is a deterministic string/pattern
operation with no model judgment in the loop — I independently verified
the underlying mechanism (§0) is real and harness-enforced, not merely
asserted in CTO's document. I agree this closes the *specific* gameability
the Founder's question raised.

**Does it introduce a new problem? Yes, two, and CTO's document only
partly names them:**

1. **Coverage lags behind the system's own growth.** A static table only
   protects what someone remembered to list. `operations.sqlite3` — the
   single most sensitive resource this system's own architecture makes
   directly reachable from Bash — isn't in CTO's own example denylist
   (§3, above). That's not a hypothetical maintenance risk; it already
   happened, in this very document's own draft policy.
2. **The corrected flow fixes safety, not adoption.** Per §4, a
   human-declared, default-broad narrowing field doesn't, by itself,
   deliver the Founder's original goal (genuine per-task scoping) — it
   makes that goal *possible* without making it *likely*. CTO's document
   doesn't distinguish these two outcomes; I think that distinction
   matters enough to state as its own finding, not fold into "not
   gameable, therefore solved."

---

## 6. What's audited, and is it enough to detect a violation after the fact?

**Today: nothing.** No `settings.json`/`hooks:` block exists anywhere in
this repository (confirmed, matching CTO's own finding), so there is
currently no durable record of any tool call a supervised agent makes
beyond whatever a human happens to be watching live.

**Under CTO's proposed design**: denials, and "ask" outcomes answered
yes, would be logged (not yet built). This is necessary but **not
sufficient** to detect an actual violation after the fact, and I want to
be precise about why: a genuinely successful bypass, by definition, never
triggers a denial — there is nothing distinguishing it in the log from
ordinary allowed activity, because CTO's design does not propose logging
every *allowed* tool call (a reasonable cost tradeoff, but one with this
specific consequence). The denial log tells you what the hook
successfully blocked; it tells you nothing about what got through that
shouldn't have.

**Recommendation**: (1) build denial/ask-yes logging as CTO proposes —
necessary, cheap, should ship with the first hook; (2) state explicitly in
`SECURITY.md`, once this ships, that this logging detects *attempted and
blocked* activity only, not bypasses; (3) the closest available
after-the-fact detection mechanism for something a hook didn't catch is
periodic (not per-session, not automated) Security/Red Team sampling of
full Claude Code session transcript files — these already exist on disk
per session (`transcript_path`, confirmed present in the PreToolUse hook
input schema itself, §0) and are not currently reviewed by anyone
systematically. This is a spot-check, not comprehensive coverage, and
costs real review time — consistent with this project's own established
pattern of accepting a standing periodic-review burden for gaps that can't
be closed cheaply (the same shape as the credential-file mtime
tamper-detection's own "detection, not prevention" framing in
`SECURITY.md`).

---

## 7. Required conditions before this design is implemented

Matching the discipline Security's own Phase 3A review already used on
this project — concrete, cheap, none requiring new infrastructure beyond
what CTO already proposes:

- **S1** — Any Tier 2 hook covering Bash must also cover Write/Edit via
  `file_path` (now confirmed buildable, §0) — a Bash-only hook is
  trivially bypassed by write-then-execute (§2.1).
- **S2** — The Developer/CTO denylist (CTO's named first hook,
  recommendation step 2) must explicitly name `operations.sqlite3` and
  raw-sqlite-access patterns as protected, not only
  `.founder_credential.json`/`ptrace`/`sudo`/network — §3's finding that
  raw stdlib `sqlite3` access is a *worse*, currently-unnamed vector, not
  the same one CTO's document already discloses.
- **S3** — Tier 1's zero-tool scoping for Security and Red Team must be
  written down as bounded to diff-scoped gate reviews (SECURITY_REVIEW /
  RED_TEAM_REVIEW against a specific artifact), not their
  investigative/architecture-review work — §1.2. If the Founder wants the
  broader scope anyway, that should be a deliberate, named decision, not
  an implicit consequence of extending Phase 3A's pattern uncritically.
- **S4** — The synchronous, human-triggered Code Review path's SHA-anchored
  scope (§1.1) — it can only review already-handed-off work with real
  recorded commit SHAs, not live/uncommitted diffs — must be stated
  explicitly in whatever architecture doc actually specs that step, so a
  later "make it more useful" change doesn't quietly reintroduce a
  live-filesystem read outside review.
- **S5** — `tasks.allowed_paths` should not be a silent-default-broad
  nullable field (§4) — require an explicit, logged value (even a wide
  one) or a suggest-then-confirm heuristic default, so "not narrowed" is
  a visible, auditable decision, not an absence.
- **S6** — Hook denial (and ask-yes) logging must ship with the first
  hook, and `SECURITY.md` must state plainly that this logging detects
  blocked attempts only, not bypasses (§6).
- **S7** — Any hook-internal call to an external binary (for its own
  path/SHA validation) must use an absolute path, never bare-name
  `$PATH` resolution (§2.3).

None of S1–S7 require new infrastructure beyond what CTO's document
already proposes building, and none change CTO's central two-tier
decision — they are fixes to the design as specified, the same posture
Security's Phase 3A review took toward CTO's Phase 3A architecture.

---

## 8. Recommendation for risks.id=3's disposition

**REDUCE-with-specifics — I agree with CTO's disposition, not CLOSE, not
REMAIN-OPEN-unchanged, but I do not agree the specifics are complete as
written.**

CTO is right that the risk's current wording ("Bash permissions cannot be
scoped below the tool-category level") is, narrowly, false — PreToolUse
hooks genuinely scope access below the tool-category level, for Bash *and*
Read/Write/Edit (§0, now confirmed rather than assumed), and this project
has simply never used that mechanism. The wording should be corrected via
`decision-record`, as CTO proposes, not silently edited.

I agree the two-tier direction is the right shape: zero-tool for
structurally read-and-judge roles, harness-enforced hooks plus a static,
human-authored policy for roles that genuinely need live execution, and
CTO's rejection of OS-user separation/bubblewrap sandboxing as
disproportionate for a first step, given this risk's own `medium`
severity and this system's single-operator, no-external-traffic scope, is
correct and I concur with it directly, without hedging.

Where I diverge from CTO, stated plainly per the Founder's own
instruction that disagreement should survive, not be smoothed into
consensus:

- CTO's document treats the `opsdb.py`-write vector and Tier 1's
  "full closure" claim as more settled than they are. The raw-`sqlite3`
  bypass (§3) is a materially worse, currently-unnamed vector, and Tier
  1's closure claim does not hold for Security's/Red Team's own
  investigative work (§1.2) the way it holds for Code Review's diff-bound
  work — this document (and this very review) is the evidence.
- CTO's `allowed_paths` design (§3.3) fixes gameability but is
  default-broad; without §4's correction it risks becoming exactly the
  "appearance of scoping without the substance" the Founder's own
  question anticipated.

**My recommendation**: keep `risks.id=3` `open` (not `mitigated`) until
at minimum S1–S3 above are addressed in the design — not necessarily
fully implemented, but resolved as explicit, written architecture
decisions the way CTO's own document already resolves the Founder's
policy-flow question in §4 of that document. Once S1–S7 are folded in,
this becomes exactly the kind of `REDUCE`, not `CLOSE`, status change
CTO recommends: a real, harness-enforced narrowing of a genuinely
`medium`-severity, single-operator risk, with its residual gaps (a
determined adversarial bypass via encoding indirection; coverage that
will always lag what anyone remembered to name) disclosed honestly rather
than claimed away — the same standard this project has already held
itself to at every prior milestone.

This document is written for Red Team's adversarial review next (Stage 3)
and Chief of Staff's synthesis after that (Stage 4) — both CTO's and my
own conclusions above should be treated as open to challenge, not as a
settled recommendation.
