# Red Team adversarial review — risks.id=3 (TASK-016, Stage 3 of 4)

Reviewing `ops/reviews/cto-risk3-architecture-investigation.md` (Stage 1)
and `ops/reviews/security-risk3-threat-model.md` (Stage 2), read in full,
plus `ops/SECURITY.md`, `ops/reviews/security-phase3a-threat-model.md`,
`ops/reviews/red-team-phase3a-architecture.md`, all 14 `.claude/agents/*.md`
files, and — independently, not cited by either prior stage —
`ops/control-center/automation.py` (the actual assembly/parsing code both
documents reason about), `ops/db/schema.sql`, and
`ops/skills/operations/update-config.md` /
`ops/skills/operations/fewer-permission-prompts.md`. Investigation-only;
nothing in `ops/` or product code is touched by this document.

**Verdict on the combined CTO+Security proposal (post S1–S7): CONCERNS —
same posture as Security's own verdict, not a harder REJECT and not a
clean PASS.** The two-tier direction is right and I do not reopen it. But
the combined document, even with S1–S7 folded in, has one real,
previously-unexamined structural gap (a self-referential trust problem in
Tier 2's own governance model — §3 below) that neither CTO nor Security
found, plus several smaller, concrete gaps in the specific first
implementation step CTO names. None of this requires reworking the
two-tier decision itself. It does mean "S1–S7 resolved" is necessary but
not sufficient before Tier 2's first hook ships, and it changes what I
recommend as the actual first Tier 2 milestone.

---

## 1. Where I agree, without hedging

- **The two-tier shape is correct**: zero-tool for the three
  structurally read-and-judge roles, harness-enforced `PreToolUse` hooks
  plus a static, human-authored policy for the four roles that need live
  execution. I re-derived this independently rather than accept it on
  either document's word, and it holds up.
- **CTO's rejection of OS-user separation and full sandboxing as a first
  step is correct.** Real, kernel-enforced isolation is the only thing
  that closes the adversarial-agent gap for good (§4 below explains why),
  but it is genuinely disproportionate machinery for a `severity=medium`,
  single-operator, no-external-traffic risk. Agree without reservation.
- **Security's correction of the Founder's original policy flow (static,
  human-authored table + deterministic hook check, never an LLM inferring
  "normal") is right, and Security's independent re-derivation of why
  it's gameable as originally floated is correct** — I checked the same
  mechanism (a task description is same-OS-user-writable,
  attacker-influenceable content per `SECURITY.md`'s own Phase 3A
  disclosure) and reach the same conclusion.
- **Security's file_path confirmation (§0 of Stage 2) is real and
  well-evidenced** — reading the actual dispatch code and Read/Write/Edit
  schemas rather than trusting the docs is exactly the right method, and
  I did not find anything in `cli.js` that contradicts it.
- **S1, S2, S6, S7 are all correct, cheap, and necessary.** I have nothing
  to add to S1 (Bash-only hooks are trivially defeated by write-then-
  execute) or S7 (absolute paths for hook-internal subprocess calls).
- **S3 and S4 (Tier 1 scoped to diff-bound gate reviews, not Security's/
  Red Team's own investigative work; the human-triggered Code Review path
  is SHA-anchored, not a live-diff reviewer) are both correct** — I
  independently verified the code Security cites (`_SHA_RE`,
  `_commit_exists`, `_validate_repo_path`, `git show <sha>:<path>` never
  touching a working-tree read) and confirm the hardening is real, not
  merely asserted. This TASK-016 chain is itself further evidence for
  S3's point: I needed Bash to do this review (grep the installed CLI,
  read `automation.py`, query `schema.sql`) exactly as Security did for
  Stage 2 — a zero-tool Red Team could not have produced this document.

Where I diverge, below, is not a rejection of any of the above — it is
what both documents, working carefully within their own lenses, still did
not surface.

---

## 2. Stress-testing S1–S7: sufficient, but not closing what they sound like they close

None of S1–S7 are redundant with each other — each targets a distinct,
real defect. But taken together and fully satisfied, they still leave a
gap neither document names as a condition, because it sits outside both
documents' respective lenses (Security's lens was bypass technique and
data reachability; CTO's was mechanism design) the same way RT1–RT3 sat
outside CTO's and Security's Phase 3A lenses in the precedent both
documents cite.

**The gap: nothing in S1–S7 requires the hook's own configuration surface
to be protected against the roles it constrains.** See §3 — this is
concrete, not hypothetical, and it is the headline finding of this
review.

A second, smaller gap: **S5 is correctly scoped as "before `allowed_paths`
ships," not "before the first hook ships"** — CTO's own step 3 already
frames `allowed_paths` as a later refinement, not a step-2 prerequisite,
and Security's "at minimum S1–S3" framing (§8 of Stage 2) already reflects
this ordering correctly. I want to make this explicit rather than leave it
implied: **S1, S2, S3, S4, S6, S7 gate the first hook and the first
synchronous Code Review path. S5 gates `allowed_paths` specifically and
does not need to block either of those two nearer-term deliverables.**
This is a clarification, not a disagreement.

---

## 3. The gap both prior stages missed: Tier 2's policy is not self-protecting, and this project has already shipped tooling that proves the risk is real

CTO's design (Stage 1 §3.2) states the hard denylist is "authored once by
CTO/Security... version-controlled like any other architecture artifact"
and that a too-broad pattern list is "a real, standing risk that requires
the same periodic Red Team/Security review discipline" — treating drift
as a *process* problem, to be caught later by review. Security's §4
raises a closely related but distinct concern (the *default* on
`allowed_paths`). **Neither document asks the sharper question: who can
write the hook's own definition, right now, in the middle of an ordinary
supervised session, before any later review happens at all?**

The answer, checked against this repository's actual, already-shipped
files, is uncomfortable:

- `.claude/agents/developer.md` and `.claude/agents/cto.md` both carry
  `Write, Edit` in their `tools:` frontmatter today. Under CTO's own
  design, a hook's definition lives in exactly the kind of file these two
  roles can already touch: a `hooks:` block in `.claude/agents/<name>.md`
  frontmatter, a hook script somewhere in the repo, and/or
  `.claude/settings.json`. **Developer and CTO are two of the four roles
  Tier 2 is built to constrain, and both have a native, unrestricted tool
  grant capable of editing the file that constrains them.**
- This is not a hypothetical bypass I am constructing — **this project
  already has a shipped, named, DevOps-scoped skill whose stated purpose
  is exactly this.** `ops/skills/operations/update-config.md`: *"Purpose:
  Configure the Claude Code harness via settings.json — permissions, env
  vars, hooks... Which agents may use it: Release/DevOps Agent."*
  `.claude/agents/devops.md`'s own persona note instructs the agent to
  *"Use `update-config`... for environment/session hygiene."* DevOps is
  the fourth of Tier 2's four constrained roles. **The role Tier 2 is
  designed to restrict is simultaneously the role this project has
  already designated, in writing, as the authorized editor of the exact
  mechanism that restricts it** — and DevOps doesn't even need `Write`
  (its `tools:` grant is `Read, Grep, Glob, Bash, Skill`, no
  `Write`/`Edit`) to do this: `Bash` alone (`cat >`, `sed -i`, the
  `update-config` skill's own described output of "an updated
  `.claude/settings.json`") is sufficient.
- A related, second existing skill compounds this:
  `ops/skills/operations/fewer-permission-prompts.md` — *"Scan
  transcripts for common read-only Bash/MCP calls and add a prioritized
  allowlist to reduce permission prompts... Expected output: An updated
  `.claude/settings.json` allowlist... Which agents may use it:
  Release/DevOps Agent."* This one is scoped more narrowly by its own
  stated limitation ("Read-only calls only — never widens write/
  destructive permissions"), so it is not itself a hook-defeat mechanism —
  but it is concrete, pre-existing, in-repo proof that this project
  already has a designed, sanctioned pattern where a role widens its own
  effective permission surface over time in response to friction, with no
  CTO/Red Team review gate mentioned anywhere in either skill's own
  documentation. This is exactly the abstract "static policy erodes
  toward stale/overbroad" failure mode the task brief asked me to test
  for (§6, below) — except it is not a risk this project might develop;
  it is a mechanism this project has already built.

**Why this is worse than "a too-broad pattern list, caught eventually by
periodic review" (CTO's own framing)**: a periodic review catches a badly
*authored* policy. It does not catch a policy that was correctly authored
and then *quietly edited* by one of the roles it constrains, inside an
ordinary, plausible-looking supervised session — "tightened the allowlist
for a new test command," "added a legitimate env var for the new build
step" — the same kind of small, unremarkable diff this project's whole
review pipeline is built to nod through quickly, not scrutinize as a
security-relevant change unless someone is specifically looking for it.
CTO's own document treats hook authorship as an architecture artifact
"changed only through this project's own existing architecture-review
process" — that is a *norm*, stated in prose, identical in kind to the
"ask the agent nicely" pattern this whole investigation was explicitly
asked not to manufacture around. Nothing technical stops Developer or CTO
(via `Write`/`Edit`) or DevOps (via `Bash`, using its own sanctioned
`update-config` skill) from making that edit directly, in the same turn,
without going through `decision-record` first — no different in kind from
the Founder's originally-floated "policy check confirms this is normal,"
except the check being bypassed here is the mechanism itself, not a
downstream judgment about it.

**Required, before any Tier 2 hook ships (a new condition, building on
S1/S2's own logic, not replacing it) — call it S8**: the hook's own
definition surface — `.claude/settings.json`, any `hooks:` block in
`.claude/agents/*.md`, and any hook script file(s) themselves — must be
on **every constrained role's own denylist**, enforced by the hook that
is already running for that role (a Bash/Write/Edit pattern denying
writes to those specific paths), so that widening one's own restriction
requires either (a) a role not covered by Tier 2 at all (a human, or a
Tier-1 zero-tool role, neither of which can touch it anyway), or (b) an
explicit, logged escalation via the "ask" mechanism CTO's own design
already relies on elsewhere. **`update-config` and `fewer-permission-
prompts` must be re-scoped at the same time** — either restricted to a
role Tier 2 doesn't constrain, or explicitly gated behind a human-visible
approval step before whatever they produce takes effect, since as
currently documented they hand exactly the role Tier 2 most needs to
constrain (DevOps, given its Bash-only, no-Write/Edit-but-still-
config-capable position) a sanctioned tool for self-widening.

I want to be precise about severity here: this does not undermine Tier
1's zero-tool closure (Code Review/Security/Red Team have no `Write` in
this design and nothing to edit `.claude/settings.json` with in the
zero-tool path either way). It is specific to Tier 2, and specific to the
two roles (`developer`, `cto`) with native `Write`/`Edit` plus the one
role (`devops`) with a documented, sanctioned config-editing skill. `qa`
has neither `Write`/`Edit` nor a config skill reference in its persona
note, so this finding does not currently apply to `qa` as sharply — worth
confirming that stays true as this design is built, not assuming it.

---

## 4. Adversarial-agent stress test of Tier 2 hooks — the ceiling, stated plainly

Both prior stages already established the core technical bypasses
(subprocess indirection, base64/heredoc encoding, `$PATH` shadowing,
Bash-string-vs-typed-`file_path` asymmetry). I re-derived these
independently against the actual mechanism and don't dispute any of them.
The question this stage was specifically asked to answer is the ceiling
question: against a truly adversarial agent with a full turn to reason
about bypasses, is a pattern-matching `PreToolUse` hook a security
boundary, or a best-effort control?

**It is a best-effort control, and this project should say so exactly
that plainly wherever this design gets written down for real — not as a
hedge, as a precise engineering fact.** A `PreToolUse` hook, even with
real `file_path`/`command` fields and real path resolution, evaluates a
presented string once, before execution, against a finite pattern list
authored by someone who had to anticipate the bypass in advance. An
adversarial agent with a full turn does not have to find a bypass the
hook's authors failed to imagine in the abstract — per §3, it may not
need a bypass at all, because it may have a legitimate, documented path to
edit the constraint directly. Where a real bypass is needed, the
attacker's search space (any interpreter, any encoding, any indirection
through a legitimate-looking intermediate file) is categorically larger
than the defender's pattern list, for the structural reason CTO's own
document already names correctly (§3.2 point 3): the hook gates the
command it sees, not the process tree it spawns. This is not a defect in
CTO's specific design — it is true of PreToolUse hooks as a mechanism,
on any project, and both prior stages are honest about it. My addition is
narrower and more concrete: for **this** project, the ceiling is lower
than "a determined bypass via base64" makes it sound, because the
self-referential gap in §3 means the ceiling for two-of-four roles may be
"edit the policy directly," which requires no cleverness at all.

**One more verification gap, in the same spirit as Security's file_path
check, that I could not fully resolve and flag rather than assume**:
CTO's design assumes `hooks:` can be declared per-subagent, in each
`.claude/agents/<name>.md`'s own frontmatter, and that this produces
role-differentiated enforcement (a tighter allowlist for `qa`/`devops`, a
denylist only for `developer`/`cto`). I found hook-configuration
references in the installed CLI (`hooks.json`, a `/hooks` command
described as "Manage hook configurations for tool events") but did not
find, in the time available, conclusive evidence that a `hooks:` key in
subagent frontmatter is itself a supported, role-scoped mechanism as
opposed to a single global `.claude/settings.json`/`hooks.json`
configuration that would need its own logic to determine which subagent
identity is currently active. **This should be confirmed directly,
before Development builds the first hook** — the same due-diligence
standard Security applied to `file_path`, not assumed correct because it
appears in both prior documents. If it turns out hooks are global rather
than per-subagent-frontmatter-scoped, CTO's "role-specific allow/deny
shape" (denylist for `developer`/`cto`, allowlist for `qa`/`devops`)
becomes one hook that must itself determine, from context available in
the hook payload, which role is currently invoking it — a real, if small,
design change, not a blocking one.

---

## 5. Is there a simpler solution? Yes — for Tier 2's *scope*, not its shape

The task brief asks directly whether Tier 2 is needed at all in the near
term, or whether audit logging plus after-the-fact human review gets most
of the value more cheaply. My answer: **build Tier 1 now, in full, per
CTO's step 1 and Security's S3/S4. For Tier 2, do not commit to all four
roles as the first milestone — build the smallest real slice (Developer's
denylist, per CTO's own step 2), ship S6's logging *as load-bearing, not
as an afterthought appended later*, and treat extending to `qa`/`cto`/
`devops` as a separate, later decision, not a foregone next step.**

Reasoning, concrete:

- Both prior stages agree Tier 2 does not close the adversarial-agent gap
  (§4) or the `opsdb.py`-write vector, and my own §3 finding shows the
  *policy itself* is editable by two of the four roles it targets today.
  Given that, Tier 2's actual, defensible value for this system right now
  is narrowing the **realistic** cases (§1, cases 1–2 in CTO's own
  framing: scope creep, prompt-injection-influenced ordinary work) — not
  providing a security boundary against a determined adversary. Audit
  logging plus periodic human/Security review (already recommended in
  Security's §6, using the `transcript_path` field CTO's own document
  confirms is real) is a genuinely comparable control for exactly that
  realistic threat class, at a fraction of the engineering cost, because
  neither approach is airtight against case 3 anyway.
- Where Tier 2 clearly earns its cost over logging-alone is the two
  concretely named vectors (`.founder_credential.json`,
  `PTRACE_ATTACH` against `server.py`) — a real-time deny is
  meaningfully better than a log entry a human reads later, for a
  same-session, in-progress mistake. That argues for building the
  Developer denylist (the highest-flexibility, highest-risk role) now.
  It does not, on its own, argue for building the same machinery three
  more times (`qa`, `cto`, `devops`) before there is any operating
  experience with the first one, or before S8 is resolved for the two
  roles (`developer`, `cto`) it applies to most sharply.
- This is not "don't build Tier 2" — it's "build one real hook, ship
  logging with it, and let a decision-record after real usage (not a
  document written before any hook exists) determine whether `qa`/`cto`/
  `devops` need the same treatment or whether logging-plus-spot-check is
  sufficient for those three." This directly answers the "hidden costs"
  lens too: CTO's step 2 as written ("author the first hook... extend to
  `qa`, `cto`, `devops` next") already reads as a four-role commitment,
  not a one-role experiment — I'd make that explicit as a one-role
  experiment instead.

---

## 6. Governance drift of the static policy — confirmed, not hypothetical

Security's §4/§5 concern (a static, human-authored policy can drift
stale/overbroad, the same shape as `allowed_paths`'s default-broad
concern generalized) is correct, and §3 above is direct, in-repo evidence
it is not a hypothetical risk for this project specifically — this
project has already shipped two skills whose entire purpose is to modify
the permission surface in response to friction, one of them (`update-
config`) explicitly including "hooks" in its stated scope, with no review
gate named in either skill's own documentation. **Neither prior stage's
review-cadence recommendation (Security's "periodic Red Team/Security
sampling," CTO's "the same periodic review discipline this project
already applies") is wrong, but neither specifies a concrete cadence,
trigger, or owner** — "periodic" with no interval or triggering event is
exactly the kind of loosely-specified governance mechanism that, per this
same section's own logic, erodes for the mundane reason that nothing
forces it to happen. **Recommendation**: name a concrete review trigger
tied to something this project's schema already tracks — e.g., any commit
touching `.claude/settings.json`, `.claude/agents/*.md`'s `hooks:` block,
or a hook script file requires a `CODE_REVIEW` handoff naming the change
explicitly (not folded silently into an unrelated diff) and a
`decisions` row, the same discipline `cto.md`'s own role doc already
requires for "silently changing a major architecture decision." This
turns "periodic review" from a standing intention into a structural
trigger tied to the one class of change that matters most here.

---

## 7. Overengineering check

**Tier 1: proportionate, cheap, real. Build it now, no changes
recommended to its scope beyond S3/S4.**

**Tier 2 as fully specified across both documents (four roles, denylist +
allowlist shapes, `allowed_paths`, worktree-per-task) is more machinery
than this risk's own `severity=medium`, single-operator framing currently
justifies as a *first* milestone** — not because the mechanism is wrong,
but because §4/§5 above show its marginal value over a much cheaper
logging-first approach is concentrated in one role (`developer`) and one
class of vector (the two concretely-named ones), while the rest of the
specified machinery (per-role allowlist tuning for `qa`/`devops`, human-
declared `allowed_paths`, worktree containment) adds real, ongoing
maintenance cost (§4/§6's drift risk) for roles and cases where audit-
logging-plus-review would likely deliver comparable practical protection
today. This is the one place I recommend doing *less* than either prior
document's roadmap, not more — shrink the committed first Tier 2 scope to
one role, gate the rest on a real decision-record made after that one
hook has actual operating history.

---

## 8. Recommendation for risks.id=3's disposition

**REDUCE-with-specifics — same top-level disposition as CTO and Security,
genuine agreement, not manufactured.** The risk's own wording is narrowly
false (hooks do scope below tool-category level) and should be corrected
via `decision-record`, as both prior stages recommend. The practical open
status should be preserved — this document adds real, unclosed gaps to
the list, it does not shorten it.

**Required conditions before Tier 2 implementation starts**: S1, S2, S3,
S4, S6, S7 (endorsed as written) **plus S8** (§3 above: the hook's own
configuration surface — `.claude/settings.json`, `hooks:` frontmatter
blocks, hook scripts — must be on the denylist of every role Tier 2
constrains that can reach it, and `update-config`/`fewer-permission-
prompts` must be re-scoped or gated accordingly) **plus verification of
the per-subagent hook-scoping mechanism itself** (§4, the open question
about frontmatter-scoped vs. global hooks) before Development commits to
CTO's role-differentiated allow/deny design specifically. S5 remains
correctly scoped to gate `allowed_paths` only, not the first hook.

**On CTO's named smallest first step (the synchronous, human-triggered
Code Review path)**: **right instinct, right size, ship it — with three
small, concrete additions CTO's document does not currently specify**:

1. **State the new invocation's authorization boundary explicitly before
   Development builds it.** If it's a new HTTP route, it must carry the
   same `SESSION_TOKEN` CSRF + Founder-session gate every other write
   route in this system requires (`ops/SECURITY.md`'s own established,
   unbroken pattern) — the document doesn't currently say this, and it
   is exactly the kind of omission RT1 caught in Phase 3A's own
   file-list. If it's a CLI entry point instead, say that explicitly and
   note it inherits terminal-level trust, not HTTP-route trust.
2. **Give this new synchronous invocation its own audit record** (reuse
   `automation_events`' shape with a distinct `trigger_kind`, or an
   equivalent), so Security's §6/S6 periodic-transcript-review discipline
   has one consistent table to look at for both automated and
   human-triggered zero-tool reviews, rather than the human-triggered
   path being invisible to the accounting this project already built.
3. **Do not reuse the "AUTOMATED mode" persona instruction text
   verbatim** for this new path — `_assemble_transcript()`'s literal
   wording ("You are reviewing this in AUTOMATED mode — a narrower
   context than a human-supervised session") is inaccurate for a
   human-triggered, on-demand invocation and should get its own short,
   accurate variant. Small, but the kind of small inconsistency this
   project's own precedent (Phase 3A's RT1/NB1) treats as worth fixing
   before Development builds from the document, not after.

Non-blocking, worth stating for completeness: `_assemble_transcript()`'s
truncation-forces-REJECT rule is a persona instruction, not a Python-
enforced one (`_invoke_and_record()` never overrides a PASS verdict based
on the `truncated` flag) — this is a known, previously-disclosed,
non-blocking residual from Red Team's own Phase 3A review (RT2's
non-blocking note), not a new finding, and it carries over unchanged to
the new synchronous path along with everything else that's hardened. I
note it only so "the code this project already built and reviewed is
hardened" (CTO's framing, which I confirm is true for the SHA/path
validation) is not read as "every mitigation in this path is Python-
enforced" — one specific one, already known, still isn't.

**For Tier 2's first milestone, my recommendation differs in scope from
CTO's own step 2 as written**: build the Developer denylist only,
including S8's self-protection requirement, with S6's logging shipping in
the same change — not committed, in the same milestone, to `qa`/`cto`/
`devops` next. Extend further only via a decision-record made after this
one hook has real operating history, informed by whether logging-plus-
review alone would have been sufficient for the cases it actually catches.

This document is written for Chief of Staff's synthesis (Stage 4).
Genuine points of disagreement preserved above, per the Founder's stated
intent, are: (1) S8 and the self-referential trust finding (§3) — a real
gap neither CTO nor Security identified; (2) a narrower recommended scope
for Tier 2's first milestone than CTO's own step 2 commits to; (3) three
concrete, currently-unspecified details in CTO's named first step that
should be resolved before Development builds it. None of these reopen the
two-tier decision itself, and none require new infrastructure beyond what
CTO's document already proposes.
