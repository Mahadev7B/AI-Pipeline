# Chief of Staff Synthesis — TASK-017 Hook-Invocation Gap (Founder Decision Requested)

Produced via a real `POST /api/chief-of-staff/ask` invocation (isolated scratch
clone, scratch credential, nothing live touched — same technique as every
prior synthesis this investigation used). Verbatim exchange in Appendix B.

Prior stages: `ops/reviews/cto-risk3-hook-invocation-investigation.md`
(CTO's investigation), Security's and Red Team's review results on TASK-017
(`opsdb.py query "SELECT * FROM review_results WHERE task_id=17 ORDER BY id"`).

---

## WHAT HAPPENED

QA caught something real: the security hook meant to stop Developer from
running dangerous Bash commands silently never fires in this project's
actual deployment setup, because the workspace isn't marked "trusted" with
Claude Code. Zero warning, zero log — a real Developer session overwrote
the operational database and nothing noticed.

CTO investigated and found a real fix (flip a "trusted" flag in a config
file), but that file sits outside the repo, and Developer — the very role
this is supposed to constrain — can flip it back with one line and leave
no trace. Even fixed, it's not a lock; it's a "please don't" sign the
person it's aimed at can quietly take down.

Security checked CTO's work and agrees completely. Red Team agrees on the
facts but flagged two problems with how it was framed:
1. CTO said "ship it anyway" and "this is your call" in the same breath —
   a contradiction. If it's genuinely the Founder's call, nothing should
   ship as a done deal before that decision is made.
2. A one-time manual fix is the wrong shape for a failure that was
   *silent*. This needs something that keeps checking itself, not a setup
   step done once and forgotten.

The one piece of this milestone that's unambiguously solid: Code Review,
Security, and Red Team now run with zero tools when reviewing code. That
doesn't depend on any of the trust-file mechanics, and QA confirmed it
works. **That part is genuinely done.**

## WHY IT MATTERS

The Developer-side fix, as CTO originally proposed it, would let this
project say "we hardened this" when what actually happened is installing a
lock the person on the other side of the door can pick from inside,
undetected. Red Team was right to push back — shipping it under a
"risk reduction" label without Founder sign-off would overstate what it
actually does.

## MY RECOMMENDATION

Split this into two decisions, not one:

- **Ship regardless, no Founder decision needed**: the two small,
  unrelated bug fixes (a substring-matching boundary bug, a hang-until-
  fail-open bug in the hook's own parsing). Cheap, strictly better than
  what's there now, don't depend on the bigger question.
- **Ship, but relabeled honestly**: the trust-file fix itself. It stops
  accidental/careless commands. It does nothing against a Developer
  session actually trying to get around it. It must not be described as
  closing or durably reducing `risks.id=3`.
- **New, actionable, no Founder decision needed**: an automated
  self-checking monitor (CTO/DevOps, at session start or on a schedule)
  that verifies the trust flag is still set and logs/alerts if it isn't.
  Won't stop a determined adversarial flip-back, but turns "silent
  failure" into "visible failure" — the actual gap QA found. Directly
  answers Red Team's objection.

**The one thing that's genuinely the Founder's call**: whether the
narrowed, non-adversarial-only version of this protection is good enough
to live with — or whether this is the moment to revisit real OS-level
sandboxing/process separation for Developer, which was rejected earlier in
this investigation as disproportionate, but that decision was made before
this project knew the ceiling on a software-only approach was this low.

## WHAT THIS MEANS FOR RISK#3

Stays `open`. The reviewer zero-tool rollout is a real, durable, delivered
reduction. The Developer-denylist half is not a durable reduction against
an adversarial actor — only against carelessness — and the risk register
already reflects this honestly (updated by CTO, independently confirmed by
Security and Red Team).

## WHAT I NEED FROM YOU

One decision: accept the Developer-denylist's narrowed scope (catches
carelessness, not determined bypass) as good enough for now — or have CTO
scope real OS-level/sandboxing separation for Developer, now that this
project knows the software-only approach has a hard ceiling.

Everything else — the two bug fixes, the self-checking monitor, keeping
`risks.id=3` open and accurately labeled — can move forward without
waiting on that decision.

---

## Appendix A — full technical record

- CTO's investigation, with the live-verified adversarial claim and both
  secondary bugs: `ops/reviews/cto-risk3-hook-invocation-investigation.md`
- Security's independent confirmation (PASS on the conclusion, an
  additive `agent_runtime.py` check-and-repair idea, a governance note):
  `opsdb.py query "SELECT * FROM review_results WHERE task_id=17 AND type='security' ORDER BY id DESC LIMIT 1"`
- Red Team's challenge (REJECT on the recommendation's structure, not the
  facts; the "gate #2 behind #4" point; the automated-monitor requirement):
  `opsdb.py query "SELECT * FROM review_results WHERE task_id=17 AND type='code' AND by_agent='red-team' ORDER BY id DESC LIMIT 1"`
- QA's original live reproduction: `opsdb.py query "SELECT * FROM qa_results WHERE task_id=17 ORDER BY id DESC LIMIT 1"`
- `risks.id=3`'s current, fully updated mitigation text:
  `opsdb.py query "SELECT * FROM risks WHERE id=3"`

## Appendix B — the real Chief of Staff exchange (verbatim)

*Founder, 2026-09-01T02:30:09.259Z* (condensed brief, within the 2,000-char
message cap):

> Big finding on TASK-017 (the risk#3 hardening milestone I asked you to
> resume). QA discovered the Developer denylist hook literally never fires
> — Claude Code skips its own security hooks when the workspace is not
> marked "trusted," and this repo is not trusted. A real developer session
> overwrote our database with zero denial, zero log entry. [... condensed
> summary of CTO's investigation, Security's agreement, and Red Team's
> structural challenge, as detailed above ...] As my Chief of Staff: tell
> me plainly what you think I should actually do here, and what you need
> from me.

*Chief of Staff, 2026-09-01T02:30:42.055Z:* (reproduced in full above,
under WHAT HAPPENED / WHY IT MATTERS / MY RECOMMENDATION / WHAT THIS MEANS
FOR RISK#3 / WHAT I NEED FROM YOU)
