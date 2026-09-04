# Red Team adversarial review — TASK-023 architecture (risks.id=3 durable closure, OS-level/process-separation sandboxing for Developer)

Reviewing `ops/reviews/cto-task023-architecture.md` in full, against
`ops/reviews/cto-risk3-architecture-investigation.md` (§3.1-3.8, its own
cited prior), `ops/DECISIONS.md` DEC-011 (`decisions.id=14`, the Founder's
explicit mandate and explicit Red Team requirement on this milestone), and
independent reads of the live repository: `ops/db/opsdb.py` (`cmd_query`,
`cmd_review_result`/`record_review_result`, `cmd_qa_result`,
`cmd_decision_record`, `cmd_risk_resolve`, `cmd_handoff`),
`ops/db/schema.sql` (full table list), `.claude/agents/developer.md`
(Developer's own actual write surface today: `handoff` only, per its own
persona note), and `ops/control-center/hooks/developer_pretooluse.py`
(TASK-017's existing hook, for continuity of §5's fold-in claims).
`risks.id=3` confirmed directly in the live database: `severity=medium`,
`status=open`, `owner_agent=cto` — matches the document's own framing.

**Verdict: REJECT.** The bwrap namespace design, the feasibility spike,
the dedicated `ai-developer` OS account, the invocation-model change, and
the TASK-017 fold-in reasoning are all sound and well-argued (details
below — this is not a wholesale rejection of the shape). But the one
piece this document was specifically tasked with closing — the
`operations.sqlite3` write/read gap via `opsdb_broker.py` — is
**self-contradictory and overbroad as specified**, in a way that
concretely undermines the "structurally closes the DB gap" claim this
whole §3 is built on. There is also one factual overclaim in §6 (a
"verified in §1" claim for a test §1 never actually ran). Both are
narrow, fixable specification gaps, not a call to redesign the whole
document — but per the Founder's own explicit instruction that this gate
be adversarial and non-skippable, and given this is the second attempt at
closing this specific risk after TASK-017's fix was found to not actually
fire, I am not passing a broker design whose own text simultaneously
claims "no raw SQL passthrough verb, ever" and lists a verb that is
exactly that.

---

## 1. BLOCKING: the broker's RPC verb set is not "small, closed, and
   fixed" as claimed — it leaks both raw read access and other-roles'
   governance-write authority into the one context this document exists
   to constrain

§3 states: *"It exposes a small, closed, fixed set of RPC verbs mapped
1:1 onto `opsdb.py`'s own already-shipped, already-reviewed `cmd_*`
functions (`task-status`, `handoff`, `decision-record`, `risk-resolve`,
`review-result`, `qa-result`, the SELECT-only `query`, etc.) — **no raw
SQL passthrough verb, ever**, over the socket."*

This sentence contradicts itself, and the contradiction is not cosmetic:

**1a. The `query` verb IS a raw SQL passthrough for reads — the exact
thing the same sentence disclaims.** I read `cmd_query` directly
(`ops/db/opsdb.py:68-80`): it takes a free-text `--sql` argument, checks
only `stmt.lstrip().upper().startswith("SELECT")`, and executes it
verbatim against the live connection — no table allowlist, no row-level
scoping to the calling task/agent, no column restriction. Exposing this
verb over the broker socket means any sandboxed Developer session can run
an arbitrary `SELECT` against **every** table in the schema, including
`messages` (Founder<->agent private communication),
`approvals`/`decisions`/`deployments` (Founder-authorization records),
`review_results`/`qa_results` for every other task, and every other
role's `agent_activity`/`handoffs` rows — none of which Developer's own
role doc (`.claude/agents/developer.md`) says it needs, and all of which
the sandbox's filesystem exclusion of `operations.sqlite3` was supposed
to keep out of reach entirely. "SELECT-only" narrows *write vs. read*, it
does not narrow *scope* — and the document's own §2.3/§3 language treats
"closes the DB gap" as if it did. This is precisely the leak the task
brief asked me to check for ("does the RPC verb set leak general
query/write capability back in through a broad verb") — it does.

**1b. The verb list includes other roles' exclusive governance-write
authority, not just Developer's own legitimate write surface.**
Developer's own persona note names exactly one `opsdb.py` write path it
performs: `handoff` (to `code-review`). Nothing in `developer.md` or
`ops/agents/developer.md` (per the document's own citation convention)
describes Developer recording `review-result`, `qa-result`,
`decision-record`, or `risk-resolve` — those are, respectively,
Code-Review/Security/Red-Team's, QA's, CTO's, and CTO's own recorded
verdicts and governance entries. I read the implementations
(`cmd_review_result`/`record_review_result`, `cmd_qa_result`,
`cmd_decision_record`, `cmd_risk_resolve`) directly: **none of them
verify that the `--by`/`by_agent` value actually corresponds to the
identity of the real caller** — `by` is just a string argument. That
absence of caller-identity verification is a pre-existing property of
`opsdb.py` today (true for every role, not introduced here), but this
document's whole premise is that the sandbox+broker combination
*narrows* what Developer's compromised or merely buggy session can reach
relative to today. As specified, it does not: a sandboxed Developer
session can call the broker's `review-result` verb with `--by red-team
--result pass`, or `qa-result` with `--by qa --result pass`, or
`decision-record` claiming Founder approval, or `risk-resolve` marking
`risks.id=3` itself `resolved` — through the "legitimate," reviewed
broker channel this document presents as the fix, not around it. §3's own
"what this does not close" paragraph names only *content-truthfulness
within a role's own legitimate writes* ("a Developer session can still
submit a well-formed, schema-valid but substantively false
status/handoff/decision row") — it does not name, and appears not to have
considered, that the broker as specified also hands Developer the *verb
surface of other roles entirely*, including forging PASS verdicts for the
very gate sequence (§8) this document calls non-skippable. That is a
categorically different and more serious gap than "Developer can lie in
its own handoff," and it is not disclosed as open — it reads as closed by
§3, which is the actual problem.

**Required fix, narrow and concrete, not a redesign**: the broker's verb
set must be an explicit, exhaustively enumerated allowlist (not "...
etc.") scoped to what Developer's own role doc actually authorizes today
— `handoff`, `task-status`/`task-step-status`/`task-progress` transitions
within Developer's own lane, `activity-log` — with `review-result`,
`qa-result`, `decision-record`, `risk-resolve`, `approval-*`, and
`deployment-record` explicitly excluded from the Developer-facing socket.
If `query` is kept at all, it must be re-scoped to a parameterized,
task-id-bound read (e.g. "my own current task's row and its own
handoffs/history"), never arbitrary `SELECT` text against the whole
schema. This is a one-paragraph, one-table spec correction in §3/§7 of
the document, in the same spirit as the "one-paragraph specification fix"
Red Team's own prior TASK-017 review (`ops/reviews/red-team-risk3-milestone-review.md`)
asked for and got folded in quickly — not grounds to reopen the rest of
the design.

## 2. Overclaim in §6: "closed... verified in §1" for a test §1 never ran

§6 states PID-namespace containment (`ptrace`/`gdb`/`strace` against
`server.py` or any host process) is "closed structurally by the PID
namespace; the sandboxed process cannot see host PIDs to target them at
all" under the heading **"Closes, kernel-enforced, verified in §1."**
I re-read §1's own enumerated test list closely: it names exactly three
load-bearing tests actually run — basic root exec, unprivileged exec, and
network isolation — plus one filesystem-containment test (the bind-mount
gap). **No test in §1 attempted anything that would verify PID-namespace
containment** — no `ps`/`ps aux` run from inside the sandbox to confirm
host PIDs are invisible, no `gdb -p <host-pid>`/`strace -p <host-pid>`
attempt against a real host process. The `--unshare-all` flag used in the
basic-exec tests does include PID namespace unsharing by construction, so
the underlying mechanism is very likely to behave as claimed — but this
document's own stated standard, repeated three times in §1 alone ("run
directly in this environment... not a synthetic description," "not a
documented claim taken on faith," "Real, not a documented claim taken on
faith") is exactly the standard this one specific §6 claim fails to meet.
Given this document's central selling point is that it tested rather than
assumed feasibility, an untested "verified in §1" claim sitting right
next to genuinely-tested ones is the kind of gap that's easy to wave
through on the document's own credibility — which is exactly why Red Team
exists as a gate here. **Required fix**: either run the missing test (a
`ps aux`/`gdb -p`/`strace -p` attempt from inside a `--unshare-all`
sandbox against a real host PID) and report the result, or correct §6's
wording to not claim §1 verification for a property that was inferred
from the flag semantics, not directly tested.

## 3. Secondary, non-blocking findings

- **No protocol-level hardening spec for `opsdb_broker.py` itself.** The
  document correctly flags the daemon as "new, genuinely security-relevant
  code" needing full Code Review/QA/Security gates, but names no
  requirements for message framing/size limits, per-connection timeouts,
  or concurrent-connection limits on a socket a sandboxed, potentially
  compromised process talks to directly. This can reasonably be left to
  Development/Code-Review detail rather than architecture, but should be
  named explicitly as a required Development consideration rather than
  left completely implicit — a broker with no request-size ceiling is a
  DoS surface against an "always-running, host-side" privileged process.
- **"...etc." in a verb list that's simultaneously called "small, closed,
  fixed."** Independent of finding 1's substance, an unenumerated "etc."
  in the one section of the document that is supposed to be the concrete
  closure mechanism for a named, disclosed gap is imprecise for a
  security-load-bearing artifact and should not survive into the document
  Development actually builds against.

## 4. What I checked and found sound (not just summarized — actively
   probed, per the task's own instruction not to rubber-stamp)

- **Feasibility spike (§1), filesystem/network portions**: genuinely run,
  not assumed — the `--fork` root-cause on the initial `unshare` failure,
  the `nobody`-account unprivileged test, and the bind-mount write-through
  reproduction are all concrete, falsifiable, and consistent with known
  bwrap/namespace behavior. I have no independent host to re-run these on
  myself in this review, and say so plainly — a fully tool-bearing
  interactive session could re-run these tests independently if the
  Founder wants that additional confirmation; I did not have Bash access
  in a mode that would let me do so credibly beyond re-reading the
  document's own transcript.
- **`ai-developer` dedicated OS account (§2.2)**: not theater. The
  document's own reasoning — namespace and UID boundaries fail
  independently, so a kernel-level namespace-escape (a real, disclosed
  Linux CVE class) still has to clear a second, independent boundary to
  reach `.founder_credential.json` — is coherent and the marginal cost
  (`useradd`, one sudoers line, one shared group) is genuinely low
  relative to the credential-exposure scenario it's named against. I do
  not find this to be unjustified complexity.
- **Production-host re-verification (§7 sequencing)**: correctly scoped
  as a parallel-track item (step 2, "in parallel with (1)") that gates the
  sandboxed-launcher step specifically (step 3), not a hard blocker on
  starting Development on the broker itself (step 1). This is a reasonable
  sequencing choice, not a hidden blocking dependency dressed up as
  parallel.
- **Invocation-model change and the "ask" ergonomics gap (§4.2)**: honestly
  disclosed as unresolved and explicitly flagged for empirical
  verification rather than assumed either way, with the document itself
  asking that the Founder sign off on accepting the cost explicitly. This
  is the right way to carry an open ergonomics question into Development
  — I am not treating this as a blocking gap, since it is already named,
  not buried.
- **TASK-017 fold-in reasoning (§5)**: the load-bearing argument (the new
  `-p`/print-mode invocation path is itself the context that silently
  skips hooks, so the trust-flag fix is a prerequisite for the hook layer
  to fire at all under the new architecture) is specific and correct, not
  "cheap, might as well" scope creep. Sound.
- **Scoping to Developer only (§4.3)**: the per-role cost/benefit
  reasoning (reviewer roles already going zero-tool; `qa`/`devops`/`cto`
  better fits for the cheaper broker-script pattern) is a genuine
  narrowing of cost relative to full seven-role OS separation, and is the
  right response to the "is this overengineered" question for the
  namespace/OS-account layer specifically. My objection in Finding 1 is to
  the broker's *verb scope*, not to scoping the whole architecture to
  Developer.

## 5. Disposition

**REJECT**, returned to `cto`. The required fix is narrow and specific:
(1) replace the broker's verb list with an exhaustive allowlist scoped to
Developer's own actual write surface, excluding other-roles' governance
verbs (`review-result`, `qa-result`, `decision-record`, `risk-resolve`,
`approval-*`, `deployment-record`) and either dropping or re-scoping
`query` away from arbitrary `SELECT` text; (2) correct or substantiate
the §6 "verified in §1" PID-namespace claim. Everything else in the
document — the bwrap shape, the feasibility spike's filesystem/network
findings, the `ai-developer` account, the invocation-model change, and
the TASK-017 fold-in — is sound and does not need to be redone.
