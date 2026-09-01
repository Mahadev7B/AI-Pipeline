# CTO Investigation — QA's TASK-017 Finding: the Developer Denylist Hook Never Fires in the Deployed, Non-Interactive Context

**Trigger:** `qa_results.id=70` (task_id=17, result=fail, 2026-09-01). Full
finding text in that row; summarized and re-verified independently below.
Investigation-only, per this project's own convention — nothing here has
been implemented. Nothing in this document changes `risks.id=3`'s
`status` (kept `open`); its `mitigation` text has been updated with a
pointer to this document and a one-paragraph summary (see end of this
file).

## 1. Verifying QA's finding against the harness itself

I did not have Task-tool access in this session to dispatch a
`claude-code-guide` subagent, so I verified this the way Security's
original Stage 2 threat model and QA's own finding both did: reading the
installed CLI's own compiled source directly (`/opt/claude-code/bin/claude`,
v2.1.252), not the earlier Stage-1/2 assumption-based approach this
project's own history explicitly warns against repeating.

Confirmed, directly from the binary:

- The exact function that produces QA's `--debug hooks` error line exists
  and is unconditional: `qxe(e,t,r="hooks")` emits `Skipping frontmatter
  hooks for ${o} '${u}': the folder its definition file came from is not
  trusted (source: ${e.source})` whenever the folder a subagent's own
  frontmatter file (`.claude/agents/developer.md`, in this case) lives in
  is not marked trusted — for ANY main-thread or subagent invocation, not
  a code path scoped to some agent subset.
- `-p`/`--print`'s own `--help` text says outright: *"the workspace trust
  dialog is skipped when Claude is run in non-interactive mode (via -p,
  or when stdout is not a TTY, e.g. piped or redirected output). Only use
  this in directories you trust."* This is not a bug QA found by accident
  — the CLI discloses it as intended behavior, in its own help text.
- Workspace trust is stored per absolute path, keyed under
  `projects["<absolute-path>"].hasTrustDialogAccepted` in a single global
  JSON file (`$CLAUDE_CONFIG_DIR/.claude.json`, defaulting to
  `~/.claude.json`) — confirmed by reading the live file in this
  environment: `/root/.claude.json` (this environment's `$HOME`, no
  `CLAUDE_CONFIG_DIR` set) has a `projects` object with one entry per
  distinct working directory this harness has ever been run from,
  including `/home/user/AI-Pipeline` itself (`"hasTrustDialogAccepted":
  false`, matching QA's finding exactly) and every scratch-clone path
  QA/CTO/Security/Red Team have used for isolated testing throughout
  this milestone's history.
- This confirms the finding is not a scratch-clone artifact: the live
  repository's own trust state has never been accepted, in this or any
  session, ever — every `claude --agent developer` (or any other agent)
  invocation against this repo run in non-interactive mode has always
  had this specific gap.

## 2. Can workspace trust be established non-interactively, reliably, as deployment?

**Yes — a real mechanism exists, and it is not a guess.** The CLI's own
error-message generator names it directly. The same code path that
produces the "not trusted" error also calls a helper (`Gfe(e)`) whose
returned guidance text is:

> "Run Claude Code in that folder once and accept the trust dialog, or
> set `projects[<path>].hasTrustDialogAccepted: true` in
> `<the global config file path>`."

That second option is a real, harness-native, non-interactive path: write
`true` into the `hasTrustDialogAccepted` key of the appropriate
`projects["/home/user/AI-Pipeline"]` entry in
`$CLAUDE_CONFIG_DIR/.claude.json` (or `~/.claude.json` if that env var is
unset) before any `claude --agent <role>` invocation runs against this
repo. This is a plain JSON-file edit — buildable as a one-line deployment
step, no interactive TTY required, no undocumented flag needed.

**Status of this mechanism:** it is real and harness-native (it ships
inside the CLI's own source, not folklore), but it is *not* a
publicly-documented, stable CLI flag (there is no `--trust-folder` or
`--dangerously-skip-permissions`-adjacent flag for this specific gate —
I checked; `--dangerously-skip-permissions` bypasses a different check,
tool permission prompts, not this agent-origin-trust gate for
frontmatter hooks). It is only ever surfaced via an error message and a
config-file convention. That means it is an internal implementation
detail the harness happens to expose today, not a contract Anthropic has
committed to keep stable across versions — worth flagging honestly, the
same way this milestone has flagged every other platform-behavior
dependency.

## 3. Does this fix hold up adversarially? (No.)

This is the question the task specifically asked me not to paper over,
and the answer is no — for a concrete, verified reason, not a vague
worry:

**The trust flag lives in a file completely outside this repository, and
every agent role in this system — including Developer — runs under the
exact same OS user with unrestricted Bash.** In this environment:
`/root/.claude.json`, owned by `root`, `rw-------` — the same user every
`claude --agent developer` (or any other role) session runs as. Nothing
in the OS, the harness, or this hook prevents a Developer-role Bash
command from reading and rewriting that file directly (e.g. `python3 -c
"import json,pathlib; ..."`, or `sed`, or a heredoc) to flip
`hasTrustDialogAccepted` back to `false` for this repo's path. The next
`claude --agent developer` invocation against this repo would then
silently lose all hook enforcement again — exactly QA's original
finding, self-reinflicted, with the same zero-audit-trail property (no
`hook_denials` row, because the hook that would write one isn't running).

Two compounding points make this worse than a normal disclosed
Bash-string bypass:

1. **It is not even a bypass of an existing check today.** The hook's
   `_BASH_SUBSTRINGS` and `_BASH_ANCHORED_PATHS` lists do not mention
   `.claude.json`, `hasTrustDialogAccepted`, or any home-directory path
   at all. A Developer session could revert trust today, if this fix
   shipped, in one plain, un-obfuscated command — no base64, no heredoc,
   no indirection required. Adding those strings to the denylist would
   only be as strong as every other Bash-string check here already
   admits to being (§2.3 of the original architecture doc): defeated by
   the same disclosed encoding/indirection techniques.
2. **Once the hook *is* active, Write/Edit-based reversion is genuinely
   blocked** — `_check_write_edit()`'s "outside repo root → deny" rule
   is typed-field-based and would correctly deny a `Write`/`Edit` call
   targeting `~/.claude.json` (it resolves outside `REPO_ROOT`). So the
   only live channel for self-reversion is Bash, and Bash protection here
   was always explicitly disclosed, from this hook's own first line of
   documentation, as "raises the bar... not a sandbox, does not claim to
   be one." Reverting the trust flag via Bash is not a new *class* of
   gap this fix introduces — it is the *same*, already-disclosed,
   already-accepted ceiling (full OS-user-level Bash access) resurfacing
   one layer up, now able to disable the entire mechanism at once rather
   than bypass one check at a time.

This is the same shape of problem as Red Team's Stage 3 S8 finding
(a fence with a gate the fenced-in agent can open) — except here the gate
is the mechanism that lets the fence be checked *at all*, not one of the
fence's individual panels.

**Conclusion on the fix:** real, cheap, and worth deploying — it restores
the hook to functioning as originally designed and reviewed, which is
strictly better than the current state (zero enforcement, zero audit
trail, permanently). But it does not deliver a durable guarantee against
a genuinely adversarial or compromised Developer session. It only
restores the hook to protecting against *non-adversarial* scope creep —
exactly the modest claim the hook's own docstring always made, no more,
no less. Framing it as closing or meaningfully reducing the Bash
master-key problem for an adversarial actor would be the overclaim this
project's Founder-set discipline exists to prevent.

## 4. The two secondary bugs — real, cheap, worth fixing regardless

Both are genuine code defects, independent of the invocation-context
finding, and both are worth fixing as defense-in-depth even though
neither is the primary issue:

- **`" gdb"`/`" strace"` leading-space boundary bug**: trivial,
  zero-evasion-technique-required bypass (`strace -p 1` as the literal
  first token is silently allowed). One-line fix: check with
  `command.split()[0] in {"gdb","strace", ...}` or move these two into
  `_BASH_ANCHOR_TOKENS`/token-based matching instead of raw substring
  matching, consistent with how the anchored-path check already works.
  Recommend fixing regardless of section 3's outcome — it costs almost
  nothing and closes a gap reachable without any of the already-disclosed
  adversarial techniques.
- **`shlex.split()` quadratic blowup → hang-induced fail-open near the
  600s hook timeout**: also real, also cheap to fix (reject/deny any
  `command` string above a fixed, generous length ceiling — e.g. 50KB —
  before calling `shlex.split()` at all, rather than trying to make
  `shlex.split()` itself faster). This compounds with the already-
  disclosed large-payload base64/heredoc bypass technique, so it is not
  a hypothetical scenario invented for this review. Recommend fixing
  regardless of section 3's outcome.

Both are moot as *primary* protection if the hook never runs at all (the
main finding) — but they are not moot in an absolute sense: if the
deployment fix in section 2 ships, both bugs become live, reachable
issues again, and should be fixed in the same pass as that fix, not
treated as optional polish.

## 5. Reassessing `risks.id=3`

The Chief of Staff's synthesis (`ops/reviews/chief-of-staff-risk3-synthesis.md`)
concluded "reduced, not closed," and rested that specifically on this claim:

> "Developer would have real, harness-enforced narrowing that Developer
> itself cannot quietly undo."

That claim does not hold, on two independent counts now confirmed:

1. **Today, in the actual deployed non-interactive invocation pattern
   this project uses, the Developer denylist provides zero protection.**
   QA live-reproduced this against the real repo's own persisted trust
   state, not a synthetic scenario. This is not "reduced" — it is
   "designed but not actually in effect."
2. **Even in the best case — the fix in section 2 is deployed and the
   hook starts firing — the "Developer itself cannot quietly undo it"
   half of the claim is specifically false.** Developer's own Bash access
   can silently revert the trust flag that makes the hook fire at all,
   with zero audit signal, in a single unobfuscated command that isn't
   even covered by the existing denylist. This is a stronger, more
   complete undo than any single disclosed bypass technique in the
   original design (those defeat one check on one call; this defeats the
   entire mechanism for every future call).

**What is actually, durably delivered today:** only the reviewer
zero-tool rollout (Code Review/Security/Red Team's synchronous invocation
routes). QA confirmed this independently and it does not depend on
workspace trust or `PreToolUse` hooks at all — `agent_runtime.py`'s
`_run_claude()` passes `--tools ""` unconditionally, a CLI flag honored
regardless of trust state, so there is nothing for a Developer-shaped
self-reversion problem to attach to. That piece is real, complete, and
should be treated as the actual delivered reduction from this milestone.

**What is not delivered:** the Developer-denylist half of the reduction
does not exist in practice today, and would not durably exist even if
the invocation-context bug were fixed, against the actual threat model
`risks.id=3` was written to describe (an agent with unscoped Bash access
under the Founder's own OS user — which includes the possibility of that
same agent acting adversarially, whether through a compromised
instruction, a bug, or bad judgment). "Reduced, not closed" was
premature specifically on the execution-role half of the reduction. It
was accurate only for the reviewer-role half.

## 6. Recommendation

Do not manufacture a stronger conclusion than the evidence supports. My
honest recommendation:

1. **Keep and rely on the reviewer zero-tool rollout** — it is real,
   verified working by QA, and does not share this weakness. No change
   needed there.
2. **Ship the trust-establishment deployment fix (section 2) and the two
   secondary bug fixes (section 4) anyway** — they are net-positive,
   cheap, and restore the Developer denylist to its originally-disclosed,
   modest purpose (raising the bar against *non-adversarial* scope creep
   — an accidental bad Bash command, a misreading of a task, not a
   compromised or deliberately adversarial agent). That is a real,
   worthwhile improvement over the current silent-zero-enforcement state,
   and there is no reason to leave a known, live gap unpatched just
   because it isn't the whole answer.
3. **Do not record the Developer denylist, even after that fix ships, as
   a meaningful reduction to `risks.id=3`'s actual threat model.** The
   risk register entry should say plainly: this milestone delivered a
   full, durable closure for Code Review/Security/Red Team's Bash
   exposure (reviewer roles), and a soft, non-adversarial-only,
   self-revertible speed bump for Developer — not a second durable
   reduction alongside the first. `risks.id=3` should stay `open` (not
   move to a stronger "mitigated"/"reduced" status on the strength of the
   Developer-denylist half), with its mitigation text naming precisely
   this scope.
4. **This is a Founder-level tradeoff decision, not something for CTO to
   resolve unilaterally**: if the real threat model behind `risks.id=3`
   includes a deliberately adversarial or compromised Developer session
   (not just an honest mistake), then no `PreToolUse`-hook-based approach
   under a single shared OS user can ever durably close it — the trust
   flag is simply the latest instance of "any file reachable by Bash is
   reachable by Bash." Durably closing that requires OS-level separation
   or containerized sandboxing per role — exactly the option CTO's
   original Stage-1 investigation evaluated and rejected as
   disproportionate for a single-operator, no-external-traffic,
   medium-severity risk, and neither Security nor Red Team pushed back on
   that call at the time. This finding does not automatically overturn
   that judgment — but it does mean the judgment was made without knowing
   the "cheaper" hook-based alternative would turn out to have this
   ceiling. Whether to accept that ceiling explicitly (document it,
   ship the soft version, move on) or revisit the sandboxing question is
   the Founder's call to make with full disclosure, not mine to make for
   them by quietly shipping the fix and calling it done.

Per the task's own instruction, this goes back through Security and Red
Team before any Development work resumes — the recommendation above is
mine, not a final disposition.

---

**`risks.id=3` mitigation text update** (applied via `opsdb.py
risk-resolve --risk-id 3 --status open`, status unchanged): points to
this document; states plainly that the Developer-denylist half of the
milestone's claimed reduction does not hold today and would remain only
a non-adversarial-scope speed bump even after the invocation-context fix
ships, self-revertible by Developer's own Bash access to the harness's
global trust-state file with zero audit trail; states that the reviewer
zero-tool rollout remains the one durable, delivered reduction from this
milestone.
