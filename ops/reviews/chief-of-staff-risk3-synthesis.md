# Chief of Staff Synthesis — risks.id=3 Investigation (TASK-016)

**Stage 4 of 4.** Investigation-only, per the Founder's directive — nothing in
this document or the three it synthesizes has been implemented. This is the
Chief of Staff's Founder-facing report, produced by a **real** invocation of
the shipped `POST /api/chief-of-staff/ask` endpoint (Milestone 2B4 session
auth, Phase 3A's zero-tool `claude --agent orchestrator` invocation path),
run against a full isolated clone of this repository at the current branch
tip with a scratch credential and a scratch copy of the live database — the
same safe-testing technique used for the Phase 3A wrap-up. Nothing in the
live repository, live database, or live Founder credential was touched to
produce this. The verbatim exchange (Founder question, Chief of Staff
answer, both with real timestamps from that invocation) is reproduced in
full in Appendix D.

Prior stages: `ops/reviews/cto-risk3-architecture-investigation.md` (Stage
1), `ops/reviews/security-risk3-threat-model.md` (Stage 2),
`ops/reviews/red-team-risk3-challenge.md` (Stage 3).

---

## THE PROBLEM

Every agent in this system that holds Bash access — Developer, QA, CTO,
DevOps, and (today) Code Review/Security/Red Team when run outside Phase
3A's one automated path — runs with what amounts to a master key: full
filesystem and subprocess access under the Founder's own OS user, with no
way today to say "this agent may touch only these files for this task."
`risks.id=3` names this. The question this investigation was asked to
answer: is that actually fixable by something *we* build, or is it a
permanent ceiling of the platform this project is built on?

## WHAT WE FOUND

The risk's own wording overstated the platform limitation. Claude Code's
`PreToolUse` hooks are a real, harness-enforced gate — not a prompt, not an
honor system — and they **can** filter within a tool category (which paths
Read/Write/Edit may touch, which commands Bash may run). This project has
simply never wired one up. That's a gap this project created by omission,
distinct from a genuine platform ceiling.

Once that was established, CTO, Security, and Red Team each independently
evaluated a real design against it — and did not converge cleanly. That
disagreement is the substance of the finding, not a flaw in the process:

- **CTO** proposed splitting agents into two tiers: reviewer roles (Code
  Review, Security, Red Team) go fully tool-less, extending the pattern
  Phase 3A already proved for the one automated handoff; execution roles
  (Developer, QA, CTO, DevOps) get role-scoped hooks narrowing what
  Bash/Write/Edit can touch, rather than losing the tool outright.
- **Security** returned CONCERNS, not PASS: agreed with the direction, but
  found the "reviewers are now zero-tool" claim doesn't hold for Security's
  and Red Team's own broader investigative work (this very review needed
  Bash to verify CTO's claims); found a raw-`sqlite3`-bypasses-`opsdb.py`
  vector worse than CTO's document disclosed; and found the proposed
  per-task path-scoping defaults to allow-broad, risking scoping that looks
  real but isn't.
- **Red Team** returned CONCERNS and surfaced something neither prior stage
  caught: two of the four execution roles (Developer, DevOps) already have
  sanctioned, everyday ways to edit the very `settings.json`/hooks file
  meant to constrain them — native Write/Edit, plus a shipped
  `update-config` skill. A fence with a gate the fenced-in agent can open.
  Red Team also independently confirmed CTO's one open technical question
  (hooks do expose a `file_path` field for Read/Write/Edit, verified by
  reading the installed Claude Code CLI source directly).

All three, independently, landed on the same disposition for `risks.id=3`:
**reduce it, with specifics — not close it, and not leave it exactly as
written.**

## OPTIONS

1. **Do nothing further** — leave `risks.id=3` open exactly as worded today.
   Rejected by all three reviewers: it's now known to be more fixable than
   the current wording claims, and leaving it as-is forfeits a real,
   cheap-to-build reduction.
2. **Ship CTO's full two-tier design as originally scoped** (all of Tier 1 +
   all of Tier 2 — Developer, QA, CTO, and DevOps hooks together). Technically
   coherent, but Security's and Red Team's open findings (S1–S8, Appendix
   C) are not yet resolved — shipping this now would look like progress on
   paper while leaving the self-widening gap and the Security-carve-out gap
   unaddressed.
3. **Ship the narrowest slice all three reviewers actually converge on as
   safe today** (detailed below) — reviewer zero-tool rollout with the
   Security-carve-out fixed first, plus one self-immune Developer denylist,
   holding QA/CTO/DevOps tiering and the sqlite3-bypass fix as explicit
   follow-on work.
4. **Go further now — OS-user separation or containerized sandboxing.**
   CTO explicitly evaluated and rejected this as disproportionate for a
   single-operator, no-external-traffic, medium-severity risk; Security and
   Red Team did not push back on that call.

## MY RECOMMENDATION

Option 3. Authorize the narrowest slice, not the full build:

1. Move Code Review, Security, and Red Team's own reviewer-role invocations
   to zero-tool wherever they aren't already (Phase 3A already proved this
   pattern works) — **with Security's caveat resolved first**: explicitly
   carve out or re-scope whatever residual tool access Security and Red
   Team genuinely need for their own broader investigative work, so
   "zero-tool" doesn't quietly break their ability to do this very kind of
   review again.
2. As the first and only execution-side step this milestone, ship **just**
   the Developer denylist (Red Team's narrower suggestion, taken literally)
   — and make the denylist/hook configuration itself **read-only to
   Developer and DevOps**, closing the self-widening gap Red Team found
   before any hook-based scoping goes live for anyone.
3. Explicitly hold DevOps/QA/CTO's broader tiering, and the raw-`sqlite3`-
   bypass fix, as separate, later, separately-reviewed follow-on work — not
   bundled into this milestone.

## WHY

This gives a real, verifiable reduction — reviewers narrowed, one denylist
shipped, the one self-widening hole closed for the case we know about —
without booking Security's and Red Team's still-open concerns as solved
when they aren't. Shipping the full design now would create a *worse*
governance state than shipping nothing: a risk register entry that says
"reduced" while a fence gate stands open. A smaller, honest first step is
worth more than a bigger step that overclaims.

## WHAT THIS MEANS FOR THE BASH MASTER-KEY PROBLEM

**Reduced, not closed.** After this milestone: Code Review/Security/Red
Team would have zero Bash exposure in normal operation (a genuine, complete
closure for those three roles specifically). Developer would have real,
harness-enforced narrowing that Developer itself cannot quietly undo. QA,
CTO, and DevOps would remain exactly as they are today — full tool-category
access, no scoping — until a separate, later milestone addresses them. The
raw-`sqlite3`-bypass-of-`opsdb.py` vector remains open and undiminished by
anything in this milestone. `risks.id=3` should move from `open` to a
`mitigated`-with-explicit-residual-scope status, not `resolved` — the same
undiluted-disclosure discipline this project already applied to `risks.id=2`
and to Phase 3A's own consequence-increase disclosure.

## WHAT I NEED FROM YOU

Authorization to have CTO scope a follow-on milestone along exactly these
lines — (1) reviewer zero-tool rollout with the Security/Red-Team own-work
carve-out, and (2) a Developer denylist that is structurally immune to
edit-by-the-agent-it-restricts — rather than the full two-tier design as
originally proposed. Also requested: your explicit sign-off that
`risks.id=3` moves to "reduced with named residual scope," not "closed," in
the risk register until DevOps/QA/CTO tiering and the sqlite3-bypass fix
each get their own separate architecture → security → red-team pass.

A copy-paste-ready authorization prompt for exactly this scope is in
Appendix E.

---

## Appendix A — CTO's headline finding (Stage 1)

Confidence: high on the analysis and option comparison; medium on the
`file_path`/`PreToolUse` claim (since resolved — see Appendix B).
Full document: `ops/reviews/cto-risk3-architecture-investigation.md`.

CTO's own words (from the completion summary): *"risks.id=3's literal
wording ('cannot be scoped below the tool-category level') is technically
false — PreToolUse hooks do allow sub-category scoping — this project has
just never used them... That's a real, low-cost gap this project created
by omission, distinct from genuine platform ceilings."* Pattern-matching
hooks were explicitly acknowledged as *not* kernel-level confinement:
subprocess indirection/encoding remains a genuine bypass against a
deliberately adversarial agent, a limit CTO disclosed rather than papered
over.

## Appendix B — Security's threat analysis (Stage 2)

Verdict: **CONCERNS** (recorded in the operational database as
`review_results` reject/returned-to-cto, the same pattern used for an
architecture-stage review). Full document:
`ops/reviews/security-risk3-threat-model.md`.

Seven required conditions before the design should ship (S1–S7):

- **S1–S3**: fix the raw-`sqlite3`-bypasses-`opsdb.py` disclosure gap,
  name `operations.sqlite3` explicitly in any denylist, and resolve the
  Tier 1 "full closure" claim for Security's/Red Team's own broader
  investigative work (not just scoped diff review).
- **S4–S7**: default-narrow (not default-broad) per-task path scoping;
  Read/Write/Edit-scoped protection alongside Bash-scoped protection (a
  Bash-only hook is bypassed by write-then-execute); sufficient audit
  logging to detect a violation after the fact; and a concrete answer to
  whether the Founder's originally-floated "system judges normalcy" flow
  is safe (Security's direct answer: not as floated, but CTO's static-
  policy replacement genuinely fixes it).

Security independently confirmed, by reading the installed Claude Code CLI
source directly, that `PreToolUse` hooks expose a `file_path` field for
Read/Write/Edit — resolving CTO's one open question.

## Appendix C — Red Team's adversarial challenge (Stage 3)

Verdict: **CONCERNS**, same posture as Security's. Full document:
`ops/reviews/red-team-risk3-challenge.md`.

New finding, condition **S8**, not caught by either prior stage: Developer
and CTO's own subagent definitions hold native Write/Edit; the shipped
`ops/skills/operations/update-config.md` skill explicitly authorizes DevOps
to configure `settings.json`/hooks via Bash alone; and
`ops/skills/operations/fewer-permission-prompts.md` is concrete evidence
this project already has a designed pattern for self-widening permissions
under friction. Two of Tier 2's four target roles can edit the mechanism
meant to constrain them, today, through sanctioned paths. Red Team also
flagged one further open technical question for Development to confirm
before building: whether `hooks:` scoping in a subagent's frontmatter is
genuinely per-subagent or a global mechanism that only appears scoped.

Red Team endorsed CTO's named first step (synchronous human-triggered Code
Review path) as right-sized, with three concrete gaps to close first: an
unspecified CSRF/session authorization boundary on the new route, no
audit-record analog to `automation_events` for it, and reused "AUTOMATED
mode" persona text that would be factually wrong for a human-triggered
invocation.

## Appendix D — the real Chief of Staff exchange (verbatim)

*Founder, 2026-08-31T18:03:56.886Z* (condensed brief of the three stages'
findings, within the Chief of Staff's 2,000-character message cap):

> Give me your synthesis of the risk #3 (Bash cannot be scoped below
> tool-category) investigation. TASK-016: CTO, Security, Red Team each
> reviewed independently. [... condensed summary of all three stages'
> verdicts and disagreements, as detailed above ...] All three agree:
> REDUCE-with-specifics, not CLOSE, not unchanged REMAIN-OPEN. In your own
> words, as my Chief of Staff: what should I actually do, and what do you
> recommend as the one authorization I should consider giving?

*Chief of Staff, 2026-08-31T18:04:19.324Z:*

> **WHAT HAPPENED** — Three independent reviews of TASK-016 landed in the
> same place: risk #3 (can't scope Bash below "you either have the whole
> tool or none of it") is real but was described a bit too pessimistically
> — CTO found that PreToolUse hooks actually can filter *within* a tool
> category, we just never built that. CTO proposed splitting agents into
> two tiers: reviewers (Code Review, Security, Red Team) go fully
> tool-less like the Phase 3A automation already does — no debate there,
> that's a clean win. Execution-needing agents (Developer, QA, CTO,
> DevOps) would instead get hooks that narrow what Bash/Write/Edit can
> touch, rather than removing the tool outright.
>
> Security signed off on the direction but flagged real holes in the
> specifics: the "reviewers are now zero-tool" claim doesn't cover
> Security's or Red Team's *own* day-to-day work (which sometimes needs
> more than zero tools); there's a raw-sqlite3 bypass of the opsdb.py
> guardrail that's worse than what's written down; and the hook-based
> path-scoping as sketched defaults to "allow broad unless denied," which
> is an easy way to end up with scoping that looks real but isn't.
>
> Red Team found something nobody else caught: Developer and DevOps
> already have sanctioned, everyday ways (normal file edit tools, plus a
> shipped "update config" skill) to edit the very hook/settings file
> that's supposed to constrain them. That's a self-widening gap baked
> into the current design — a fence with a gate the fenced-in animal can
> open.
>
> All three agree on the verdict: this should move from "open" to
> "reduced, with named specifics still outstanding" — not fully closed,
> and not left exactly as-is either.
>
> **WHY IT MATTERS** — Right now the honest state is: every agent with
> Bash runs with a master key — full filesystem and subprocess access
> under the Founder's own OS user, no exceptions. This review found a
> real, partial way to shrink that (reviewer tooling can go to zero,
> execution tooling can be narrowed) but also found a way the narrowing
> itself could be quietly undone by the very agents it's meant to
> restrict. Shipping the CTO's plan as originally scoped, without fixing
> that self-widening hole, would look like progress on paper while
> leaving a hole nobody closed.
>
> **MY RECOMMENDATION** — Don't authorize the full two-tier build yet.
> Authorize the narrowest slice all three reviewers actually converge on
> as safe *today*:
> 1. Move Code Review, Security, and Red Team's own reviewer-role
>    invocations to zero-tool where they aren't already (Phase 3A already
>    proved this pattern works for automation) — with Security's caveat
>    resolved first: carve out or explicitly scope whatever residual tool
>    access Security/Red Team genuinely need for their own broader
>    investigative work, so "zero-tool" doesn't quietly break their job.
> 2. As the very first execution-side step, take Red Team's narrower
>    suggestion literally: ship just the Developer denylist, and make it
>    read-only to Developer/DevOps themselves — i.e., close the
>    self-widening gap (no sanctioned path for the constrained agent to
>    edit its own constraint file) before any hook-based scoping goes
>    live for anyone.
> 3. Explicitly hold DevOps, QA, and CTO's broader tiering, plus the
>    raw-sqlite3-bypass fix, as follow-on work — not this milestone.
>
> That gives you a real, verifiable reduction (reviewers narrowed, one
> denylist shipped, self-widening hole closed for that one case) without
> accepting Security's and Red Team's open concerns as solved when they
> aren't.
>
> **WHAT I NEED FROM YOU** — Authorization to have CTO scope a follow-on
> milestone along those lines — narrowed to (1) reviewer zero-tool
> rollout with Security's own-work carve-out, and (2) the Developer
> denylist made self-immune to edit-by-the-agent-it-restricts — rather
> than the full two-tier design as originally proposed. I'd also ask you
> to explicitly bless keeping risk #3 at "reduced," not "closed," in the
> risk register until the remaining items (DevOps/QA/CTO tiering,
> sqlite3 bypass) get their own pass.

## Appendix E — copy-paste-ready Founder authorization prompt

If you want to authorize exactly the milestone the Chief of Staff
recommends (and nothing broader), the following is ready to send as-is:

> FOUNDER DIRECTIVE — AUTHORIZE RISK #3 REDUCTION MILESTONE (NARROW SCOPE)
>
> I authorize CTO to scope, and Development to build, the following and
> only the following, gated through the same Architecture → Security →
> Red Team → Development → Code Review → QA → Security-adversarial → CTO
> conformance sequence as every prior milestone:
>
> 1. Move Code Review, Security, and Red Team's own normal (human-
>    triggered) invocations to zero-tool, extending Phase 3A's existing
>    pattern — with an explicit, documented carve-out for whatever
>    residual tool access Security and Red Team demonstrably need for
>    their own broader investigative work (not just scoped diff review),
>    so this change does not silently break their ability to do reviews
>    like this one.
> 2. Ship a Developer-role Bash/Write/Edit denylist via Claude Code
>    PreToolUse hooks, scoped so that the denylist/hook configuration
>    itself is read-only to Developer and DevOps — no sanctioned path
>    (native tool grant or skill) for either role to edit its own
>    constraint.
> 3. Resolve, or explicitly and separately re-disclose as still-open, the
>    raw-`sqlite3`-bypasses-`opsdb.py` vector Security and Red Team both
>    flagged — do not silently drop it.
>
> Explicitly NOT authorized in this milestone: QA, CTO, or DevOps tool
> scoping; any change to Founder-facing routes or authentication; any
> change to production deployment gating. `risks.id=3` moves from `open`
> to `mitigated` with an explicit, undiluted disclosure of everything this
> milestone does *not* cover — the same disclosure discipline already
> used for `risks.id=2` and Phase 3A's own consequence-increase notes.
>
> Report back before touching any DevOps/QA/CTO tooling or the sqlite3-
> bypass vector — those remain separately gated, future Founder decisions.
