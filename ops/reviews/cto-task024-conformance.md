# CTO — TASK-024 Idea Desk (slices 1 and 2): architectural conformance review

Date: 2026-09-02
Reviewer: CTO agent
Scope: `ops/idea-desk/` (server.py, pages.py, evaluator.py, seed_founder_idea.py, doctor.py,
README.md), the TASK-024 additions to `ops/db/opsdb.py` and `ops/db/schema.sql`, and the
`ops/control-center/agent_runtime.py` change.
Governing: DEC-013 → DEC-019, `ops/reviews/founder-directive-task024-deciphering-v2.md`,
`ops/reviews/product-task024-brief.md` (Revision 4).

This is a catch-up review. Slices 1 and 2 were built by the orchestrator without an architecture
gate, so this is the first architectural read of the code. It is not a code review; it looks only
at conformance, structure and the properties the decisions claim.

---

## 1. The sole-writer rule — HOLDS

Verified, and it holds cleanly. Nothing in the Idea Desk opens the database for writing.

- `ops/idea-desk/server.py:72-76` — `_connect()` opens `file:...?mode=ro` with `uri=True`. The
  handle physically cannot write. The docstring's claim ("could not write to it even if a bug
  tried") is literally true, not aspirational.
- `ops/idea-desk/server.py:133-142` — `opsdb()` is the single write funnel: `subprocess.run`
  with an argument *list* (no shell), inheriting env so `OPSDB_PATH` propagates. Every write in
  `_dispatch_write()` (server.py:326-414) goes through it — create, edit, close, reopen, approve.
- `ops/idea-desk/evaluator.py:83-88` — `_opsdb()` is the same pattern for the background thread.
  The two writes it performs (`idea-round-add` at 432-446, `idea-evaluation-end` at 456-460) both
  go through it.
- `ops/idea-desk/pages.py` — imports `html`, `json`, `re`, `datetime`. No `sqlite3`, no
  `subprocess`. Read-only by construction, as its docstring claims.
- `ops/idea-desk/seed_founder_idea.py:257` — read-only connect for its idempotency check; every
  write is `run()` → `opsdb.py` (line 248).
- `ops/idea-desk/doctor.py` — only `db.exists()` (line 114). Never opens it.

I looked for a way around it and did not find one. `opsdb.py query` (opsdb.py:129-132) refuses
anything not starting with `SELECT`. `_ensure_schema()` (server.py:417-439) shells out to
`opsdb.py init` rather than executing schema SQL in-process — correct. I checked what that
executes on every start: `schema.sql` contains exactly one non-DDL statement (line 341,
`INSERT OR IGNORE INTO automation_state`) and no `DROP`/`UPDATE`/`DELETE`. Running it on every
start is safe, and the reasoning in the docstring (a restored backup predating a migration) is
sound.

**Finding: PASS on point 1.** One note, not a defect: `server.py:137-138` uses `timeout=30`. A
timeout raises `subprocess.TimeoutExpired`, which is not `WriteError`, so it falls to the generic
handler and returns a 500 — after the write may already have committed. Low impact; worth
catching.

---

## 2. The three artifacts — structural in `opsdb.py`, NOT structural in the database, and I found
two sequences that lose one

The immutability claim (`opsdb.py:1713-1721`, `schema.sql:451-463`) is that there is deliberately
no command that updates `ideas.raw_idea` or any column of `idea_rounds`. That is **true as
written**: I read the whole subparser block (opsdb.py:2130-2200) and there is no such command.
An edit appends to `idea_edits`; a correction appends a round. Approval is terminal and refuses a
second approval (verified: `idea-approve` on an already-approved idea errors, opsdb.py:1833; so
does `idea-edit`, opsdb.py:1763).

But "structural" is doing more work in the comments than it earns. It is structural **within
opsdb.py's current command surface** — a property of one file's argparse table, re-established
by inspection every time someone adds a command. It is not structural in the database: there is
no `AFTER UPDATE`/`AFTER DELETE` trigger on `ideas`, `idea_edits` or `idea_rounds`, and no
`ideas.raw_idea` immutability constraint. Given DEC-019 has now moved the database out of git and
onto a single untracked file on the Founder's machine (§6), the schema is the only place the rule
can be made genuinely structural. Three `RAISE(ABORT)` triggers would do it and would cost
nothing.

**Two sequences of legitimate commands that lose an artifact:**

**(a) Approving during an in-flight evaluation destroys the paid round.** `cmd_idea_approve`
(opsdb.py:1817-1852) does not consult `evaluating_since`. `cmd_idea_round_add` (opsdb.py:1790-1793)
refuses when `status IN ('approved','dropped')`. So:

1. Round 1 returns `Proceed`.
2. Founder clicks *Correct us*. `evaluator.start()` marks it running and a thread begins spending
   money on up to six model calls.
3. Founder (second tab, or impatience) approves round 1.
4. The evaluation completes. `idea-round-add` is refused. `run_evaluation`'s handler
   (evaluator.py:449-463) turns that into `last_error` and clears the marker.

Round 2 was fully paid for and is **never written anywhere** — the perspectives and the synthesis
exist only in a dead thread's locals. Artifact 2 for that round is gone, irrecoverably. Verified
the refusal directly against a scratch database.

`idea-close --how dropped` has the same shape (opsdb.py:1854-1870, no `evaluating_since` check).

**(b) The internal debate is never persisted at all.** `evaluator.py:422-427` collects each
role's perspective into a local list, passes it to `_synthesise()`, and drops it. No `messages`
row, no `meetings` row, no file. Product's Revision 4 §6 required the opposite — *"the round links
to that record; the screen shows only roster, depth and synthesis; the debate is one click away"*
— and called it "nearly free" because `meeting_orchestrator.py` already persists exactly this.
What is stored is the roster's *names and reasons* (`roster_json`), not what anyone actually said.
The evidence chain behind Artifact 2 does not exist. See §9.

---

## 3. The approve gate — defeated on paper, and then in practice

The gate is enforced in `opsdb.py`, not only in the page — `cmd_idea_approve` (opsdb.py:1839-1843)
refuses any recommendation outside `("Proceed", "Proceed with narrowed scope")`, and requires
`--confirm-founder-decision` (opsdb.py:1828). The page agrees (`pages.py:43`, `pages.py:652-663`).
That much is right, and the error message is well written.

**The hole: nothing requires the approved round to be the *current* round.** The check reads the
recommendation of whatever `--round-id` was passed, and the only other constraint is that the
round belongs to the idea (opsdb.py:1836-1838). `round_id` arrives from a hidden form field
(`pages.py:723`) and is passed through unvalidated except for `isdigit()` (server.py:376-381).

I ran it:

```
round recorded: idea=2 round=1 id=1 recommendation=Proceed
round recorded: idea=2 round=2 id=2 recommendation=Reconsider
$ opsdb.py idea-approve --idea-id 2 --round-id 1 --confirm-founder-decision
brief approved: idea=2 round=1 — frozen. No work has started.
```

The company's current position is **Reconsider**. A superseded `Proceed` from before the
correction was frozen as the authoritative downstream instruction. That is precisely the
"approve-anyway path" the Founder said must not exist — it just requires naming an older round
instead of clicking a button. It is reachable from the CLI by any agent, and from the browser by
one hand-edited form field.

Required: `cmd_idea_approve` must additionally require that `--round-id` is the round with
`MAX(round_no)` for that idea, and must refuse while `evaluating_since` is set.

Two smaller gate defects:

- `server.py:263-269` renders `approve_panel` for `GET /approve/<id>` after checking only that
  rounds exist. On a `Reconsider` idea the Founder is shown a full "Approve round N as the brief"
  panel with a green Approve button that will always 409. The bottom bar correctly hides Approve
  (pages.py:658-663); the direct URL does not. A gate that renders a button it will refuse teaches
  the Founder that the refusal is a bug.
- The gate lives entirely in the writer. `ideas.approved_round_id` (schema.sql:474) is a bare
  `REFERENCES idea_rounds(id)` — no constraint that the round belongs to the same idea, none on
  its recommendation. Consistent with the project's sole-writer posture, so not a blocker, but
  worth saying plainly: it is enforced in `opsdb.py`, not by the database.

---

## 4. The `agent_runtime.py` change — correct, and safe for the other callers

The diff is `pathlib` import, `_REPO_ROOT` (line 246), the sixth allowlist block (113-127), one
clause in the allowlist union (line 297), and `cwd=` + `stdin=` on the Popen (lines 337-350).

**`cwd=str(_REPO_ROOT)`** is correct and I would have required it independently. Previously the
`claude` child inherited the parent's cwd, so `--agent <name>` resolved only when the server
happened to be launched from the repo root — an undocumented, unenforced precondition on every
existing caller (Ask-Agent, meetings, Chief of Staff, reviewer sync, the automated Code Review
poller). Pinning it makes agent resolution deterministic instead of dependent on how the Founder
started the process. It is not a widening: `--tools ""` and `--strict-mcp-config` are still
unconditional (lines 325-326), so the child has no filesystem or MCP access from that directory —
cwd affects only which `.claude/agents/*.md` definitions are discovered, and repo root is where
they are meant to be found. There is no `.claude/settings.json` in this repo, so no hook or
permission resolution changes with it.

For the other callers this is a behaviour change only in the case where it was previously
*broken*. If the Control Center was already started from the repo root — which is how every
runbook in this project launches it — nothing about Ask-Agent, meetings, reviewer sync or the
automated Code Review changes at all. If it was started from anywhere else, those callers were
already failing with "agent not found" and now work. I could not construct a case where it makes
a previously-working invocation behave differently.

**`stdin=subprocess.DEVNULL`** is also correct. Nothing on this path ever wrote to the child's
stdin — the prompt goes in via `-p` (line 330) and `proc.communicate()` is called with no input.
Previously stdin was inherited, so the CLI waited on a descriptor that would never produce data.
DEVNULL gives it an immediate EOF. Safe for all five other callers; strictly removes a per-
invocation delay.

**Plainly: neither change breaks anything else.** Both should arguably have been separate commits
with their own note, since they touch a module every agent invocation in the system passes
through, but the changes themselves are right.

---

## 5. The new allowlist — an idea evaluation cannot over-reach, and meetings cannot borrow

**Can an idea evaluation invoke an unintended agent?** No, and for a reason independent of the
allowlist. `evaluator._select_roster` (evaluator.py:209-222) filters every model-proposed role
through `SELECTABLE` (evaluator.py:57) and caps at `MAX_PERSPECTIVES = 4`; the only other name it
can pass is the hard-coded `"orchestrator"` (206, 374). The model's roster output is treated as
untrusted, which is right. `IDEA_EVALUATION_ALLOWLIST` is a second, redundant wall behind that —
fine.

**Can a meeting borrow `design` from it?** No. Every meeting path filters independently before
reaching the runtime: `meeting_orchestrator.CONSULT_CANDIDATE_ROLES` (line 54) is derived from
`MEETING_PARTICIPANT_ALLOWLIST` and `_parse_selection` (57-72) can only regex-match a name from
that tuple; `server.py:983`, `:1049` and `:1116` each re-check `MEETING_PARTICIPANT_ALLOWLIST` on
the request. Ask-Agent checks its own at `server.py:775`. `chief_of_staff.py` uses a module
constant. `automation.py:473` hard-codes `"code-review"`. `reviewer_sync.py:105` maps kind → agent
through a fixed dict. Every caller constrains its own set.

So point 5 passes on the facts. But say the structural weakness out loud, because it is one bad
commit away from mattering: `invoke_agent` (agent_runtime.py:292-299) enforces only the **union**
of six allowlists. The category separation those six constants describe is enforced nowhere in
this module — it is a naming convention plus six independent checks at six call sites. Adding
`design` to any one of them grants `design` at the runtime boundary for every caller that forgets
to filter. The comment at 113-119 claims "an idea evaluation must never be able to widen what a
meeting can invoke," and that is true today only because of code in a different file.
`invoke_agent(agent_name, transcript, *, category)` checking one tuple would make the claim
structural. Non-blocking, but it should be a recorded item.

---

## 6. DEC-019's stated debt — the audit, and it is already overdue

DEC-019 says the audit of what lives only in the database "is still owed." Doing it now surfaces
that the debt is not hypothetical — **it has already been incurred, in this very decision log.**

`ops/DECISIONS.md` declares itself "the git-readable mirror of the `decisions` table." When this
review began it was two entries behind:

| decisions.id | Title | In DECISIONS.md? |
|---|---|---|
| 20 | Five-voice visual grammar for the Founder idea journey (TASK-024) | **No** |
| 23 | **DEC-018** — Founder approves the standalone idea-evaluation mockup; the real build begins, in three slices | No → **restored mid-review**, commit `47b73d1` |

DEC-018 is cited by name in `schema.sql:452`, `opsdb.py:1714`, `agent_runtime.py:113` and
`pages.py:3` as the decision authorising this entire build, and for the duration of slices 1 and 2
a fresh clone contained four references to a decision whose text did not exist in the repository.
It was restored while this review was in progress (commit `47b73d1`, *"Restore DEC-018 to the
decision log — it existed only in the database"*). **`decisions.id=20` is still missing.**

That it took a conformance review to notice is the point. The mirror is maintained by hand, with
no check that it matches the table, so it will keep drifting — and now that the database has left
git, drift is no longer recoverable by reading a diff.

**What is at risk, by name:**

1. **`ideas` / `idea_edits` / `idea_rounds`** — Artifacts 1, 2 and 3. Highest risk, and new. The
   approved brief is declared by DEC-015 to be the authoritative instruction for every downstream
   agent. It now exists in exactly one untracked, unbacked-up file, on one laptop, with no export
   path. `seed_founder_idea.py` reseeds one specific historical idea and nothing else. Before
   DEC-019, git tracking was an accidental backup; DEC-019 correctly removed it and did not
   replace it.
2. **`decisions` (24 rows)** — mirror already stale, above.
3. **`approvals` (2 rows)** — the Founder's own identity-confirmed decisions. Mirrored into
   DECISIONS.md only when someone remembers to.
4. **`risks` (4 rows)** — `risks.id=3` and `risks.id=4` are referenced by name in DECISIONS.md,
   SECURITY.md and code comments. Their *status* now lives only in whichever database you happen
   to be looking at, and the two will never agree again.
5. **`tasks` (24) + `task_status_history` (236)** — pipeline state. Commit `e45ae25` is literally
   *"ops db: TASK-024 -> IN_DEVELOPMENT after slice 1"* — a commit that can no longer be made.
   There are now two divergent answers to "where is every task."
6. **`agent_runs` (13) + `cost_usd`** — the only spend record anywhere. Money spent on the
   Founder's machine is invisible here, and vice versa. Compounded by §7 below, where idea
   evaluations write no run row at all.
7. **`review_results` (82) / `qa_results` (74) / `handoffs` (18)** — the rows the gates are
   computed from. `ops/reviews/*.md` mirrors the prose, never the pass/reject rows.
8. **`phases` (11)** — roadmap progress. `ROADMAP.md` is hand-written prose, not generated.
9. **`deployments` (1), `hook_denials` (6)** — security-relevant audit trail, single copy.
10. **`ops/reports/CURRENT_STATUS.md`** — the one genuinely generated mirror in the repo, and it
    is frozen at commit `a6451dd`, before slice 1. Nothing regenerates it.

**Recommendation:** one `opsdb.py export` command writing deterministic, diffable snapshots of
`decisions`, `approvals`, `risks`, `tasks` + status, and `ideas`/`idea_edits`/`idea_rounds` into
git-tracked files, run on the same discipline DECISIONS.md already claims to follow. That is the
"anything else that must cross machine boundaries has to be written to a file in git" sentence in
DEC-019, made real. Without it, item 1 means the Founder's approved brief has no backup.

---

## 7. Cost, runs and concurrency — the disclosure convention was skipped

Not on the list of questions, but it falls squarely in scope and is concrete.

`IDEA_EVALUATION_ACTIVITY_LABEL` and `IDEA_EVALUATION_ACTIVITY_LIKE` (agent_runtime.py:122-123)
are **defined and never used** — I grepped the whole tree. Every other invocation category in this
system opens an `agent_runs` row before invoking (`automation.py:467`, `reviewer_sync.py:236`,
`meeting_orchestrator.py:108`). The Idea Desk is the only one that does not, so:

- `idea_rounds.agent_run_id` (schema.sql:511) — a column added for exactly this — is always NULL.
- The spend on an idea evaluation appears in no cost total, on either machine.
- Nothing reconciles a crashed evaluation, because there is no run row to reconcile.

`opsdb.py run-start` / `run-end` already exist as CLI commands, so the Idea Desk can do this
without violating the sole-writer rule.

Two related bounds that moved and were not disclosed:

- `MAX_CONCURRENT_INVOCATIONS = 3` and its semaphore (agent_runtime.py:264-265) are **per
  process**. The Idea Desk is a separate process (DEC-018), so running it alongside the Control
  Center permits **6** concurrent `claude` subprocesses, not 3. The aggregate-cost disclosure at
  agent_runtime.py:205-230 — written as a Red Team condition requiring each new mechanism to state
  a closed-form worst case — no longer holds across processes and was not updated.
- A single round is 1 roster call + up to 4 perspectives + 1 synthesis = **6 invocations, ~$3.00**
  at the `MAX_BUDGET_USD = "0.50"` ceiling, with unbounded rounds via *Correct us*. The directive
  permits saying "no cost estimate is available," and the UI does (pages.py:480-485) — that is
  about the Founder-facing screen. It does not excuse the engineering disclosure the module's own
  convention requires.

---

## 8. A stuck evaluation is unrecoverable from the UI

`evaluating_since` is set before the thread starts (evaluator.py:470) and cleared in a `finally`
(evaluator.py:455-463). If the process is killed mid-evaluation — which the Founder is told to do
by name, `pkill -f idea-desk/server.py`, in `server.py:463` and `doctor.py:100` — the `finally`
never runs.

The result: `evaluating_since` stays set forever. `pages.idea_page` (pages.py:498-499) then routes
every view of that idea to `evaluating_page`, which renders only "Back to your ideas" — no action
bar, no Correct, no Approve, no Park. `POST /api/evaluate` is refused by
`cmd_idea_evaluation_start` (opsdb.py:1898-1900) with "an evaluation is already running." The idea
is permanently frozen with no escape from the product; recovery requires the Founder to run
`opsdb.py idea-evaluation-end` at a command line, which `doctor.py` does not mention and nothing
tells them.

The Control Center reconciles exactly this class of orphaned state on every start
(`server.py:1297-1360`, five LIKE patterns). The Idea Desk's `_ensure_schema()` reconciles
nothing. This is the same failure shape DEC-019 was written about: a restart that looks like it
worked, while the thing the Founder wants stays broken.

---

## 9. Deviations from the approved inputs, built without a recorded decision

Three, all traceable to the missing DEC-018 text (§6):

1. **A parallel orchestration engine.** Product Revision 4 §8.2 was explicit that
   `chief_of_staff.py` + `meeting_orchestrator.py` "already implement most of this" and that
   specifying a parallel system "would be the wrong call." `evaluator.py` is a parallel system:
   its own roster selection, its own gathering loop, its own synthesis, its own progress store —
   and, unlike the engine it declined to reuse, it persists no `meetings` row, no `messages`, no
   `agent_runs`, and discards the perspectives (§2b, §7). There may be a good reason (the Idea
   Desk is a separate process and cannot call `opsdb`'s Python API). That reason is not written
   down anywhere, and the cost of the choice — no debate record, no cost record — is real.
2. **"Edit / Correct" was redefined.** Product §8.1: *"The Founder edits the brief's text
   directly → vN+1, authored by the Founder, no model spend."* Shipped: *Edit my idea* edits the
   raw idea's wording (appends `idea_edits`), and *Correct us* is a paid re-evaluation. There is
   no Founder-authored brief version at all. The Founder approved the mockup that behaves this
   way, so the mockup governs — but the deviation from a Revision-4 requirement is unrecorded.
3. **Governing docs were not updated.** `ops/DATA_MODEL.md` has **zero** mentions of `ideas`,
   `idea_edits`, `idea_rounds` or TASK-024. `ops/SECURITY.md` has zero mentions of the Idea Desk,
   port 8421, the second session store or `IDEA_EVALUATION_ALLOWLIST` — despite having a dedicated
   section for every prior milestone that added a surface or an allowlist (Ask-Agent 2B2, meetings
   2B3B, Chief of Staff 3A/A, automation 3A/B, reviewer sync TASK-017). `ops/ARCHITECTURE.md` does
   not mention the Idea Desk. A whole second HTTP server on the Founder's machine entered the
   system with no entry in the file that documents the security posture.

---

## 10. The second front door weakened the credential it says it did not duplicate

This is the most serious finding and it is a direct contradiction of the Idea Desk's own stated
design. `server.py:8-15` and the README claim the credential is shared "because duplicating it
would quietly weaken the security posture." The *credential* is indeed shared —
`founder_auth.verify_passphrase` is imported, not copied. **The protection around it was not.**

The brute-force lockout is not in `founder_auth.py`. It is in `ops/control-center/server.py`:
`MAX_FAILED_ATTEMPTS = 5`, `LOCKOUT_SECONDS = 30` (lines 251-254), the 429 path (680-691), the
counter (718-723), and — per Security's required fix C1, quoted at server.py:107-111 — the entire
check-verify-increment sequence serialized under `_LOGIN_LOCK`.

`ops/idea-desk/server.py:296-308` reimplements the login route with **none of it**. No counter, no
lockout, no lock. It is a `ThreadingHTTPServer` (server.py:450), so:

- Port 8421 is an **unthrottled brute-force door** against the same passphrase port 8420 throttles.
  Whatever guarantee `MAX_FAILED_ATTEMPTS` provided is now bounded by the weaker door.
- `scrypt` at `N=2**17` is ~128 MB per verification. Concurrent unauthenticated POSTs to
  `/api/login` each spawn one on their own thread with no serialization — the **concurrent-scrypt
  memory-exhaustion DoS that Security's fix C1 explicitly closed**, reopened by a new door.

Also unmatched, less serious: `IDLE_TIMEOUT_S = 60 * 60` (server.py:54) against the Control
Center's 30 minutes. Two session policies on one identity, for no stated reason.

---

## 11. Slice 3 readiness — the schema does not yet support Start Work or SOT-1

Three things must change before slice 3 can be built, none of them large:

1. **No idea ↔ task link exists.** `tasks` has no `idea_id`; `ideas` has no `task_id`
   (schema.sql:14-45, 465-480). Start Work has nowhere to record what it started, and nothing
   downstream can find the approved brief from a task. Additive column plus an `opsdb.py` command.
2. **There is no brief *text*.** Artifact 3 is a pointer to a round (`approved_round_id`), and
   a round is ten `[concise, expanded]` pairs plus a six-field view (schema.sql:497-514). That is
   the right storage shape — Product §6 preferred a pointer over a copy precisely because a copy
   drifts — but nothing renders it into the instruction a downstream agent receives. Slice 3 needs
   one deterministic `render_approved_brief(idea_id) -> str` used by *every* downstream call site,
   and it must be the only such function.
3. **SOT-1's call sites are unchanged.** `business_goal` still feeds agent transcripts at
   `ops/control-center/review_transcripts.py:203-204` and `:261-262`, and is in the field list at
   `launch_developer_session.py:129`. DEC-015's hard requirement and Product §7.1 both say the
   approved brief goes downstream and the raw idea is historical context only. Nothing has moved
   yet. Product §6 also requires `business_goal` never be overwritten by any agent — `task-update`
   can still write it (opsdb.py `TASK_UPDATE_FIELDS`), which needs closing at the same time.

Fixing §3's approve gate first matters here: SOT-1 asserts that downstream receives *the approved
brief*. If a superseded `Proceed` round can be frozen after the company said `Reconsider`, SOT-1
can pass while the factory builds from a reading the company withdrew.

---

## Verdict

**REJECT.**

To be fair to what was built: the sole-writer rule genuinely holds and I could not get around it;
the `agent_runtime.py` change is correct and safe for the existing callers; the roster is
correctly treated as untrusted model output; the allowlist does not leak into meetings; and the
copy the Founder reads is honest in a way most of this codebase's UI is not. This is good work
that skipped its gates and accumulated the specific debts a gate would have caught.

### Must change

1. **Restore login protection on port 8421.** Port the Control Center's `MAX_FAILED_ATTEMPTS` /
   `LOCKOUT_SECONDS` lockout **and** the `_LOGIN_LOCK` serialization to
   `ops/idea-desk/server.py:296-308`. Extract both into `founder_auth.py` so the next door cannot
   omit them. Security's fix C1 is currently reopened. (§10)
2. **Close the approve gate.** `cmd_idea_approve` (opsdb.py:1817) must require `--round-id` to be
   the round with `MAX(round_no)` for that idea, and must refuse while `evaluating_since` is set.
   A superseded `Proceed` is currently approvable after the company said `Reconsider`. (§3)
3. **Stop losing paid rounds.** Add an `evaluating_since` guard to `idea-approve` and
   `idea-close`, so an in-flight evaluation cannot be orphaned by a concurrent state change and
   have its result refused at write time. (§2a)
4. **Make a stuck evaluation recoverable.** Reconcile stale `evaluating_since` on Idea Desk
   startup, the way the Control Center reconciles orphaned runs — and give `doctor.py` a line for
   it. Today a killed process freezes an idea permanently with no path out of the product. (§8)
5. **Record `agent_runs` rows for idea evaluations.** Use the already-defined
   `IDEA_EVALUATION_ACTIVITY_LABEL` via `opsdb.py run-start`/`run-end`, and populate
   `idea_rounds.agent_run_id`. Evaluation spend is currently invisible to every cost view. (§7)
6. **Disclose the moved bounds.** State the per-round worst case (6 invocations, ~$3.00) and that
   two processes means `MAX_CONCURRENT_INVOCATIONS` now permits 6 concurrent invocations, not 3 —
   in `agent_runtime.py`'s aggregate-cost block and in SECURITY.md. (§7)
7. **Write decision id=20 into `ops/DECISIONS.md`, and add a mirror check.** DEC-018 was
   restored mid-review (commit `47b73d1`); id=20 ("Five-voice visual grammar") is still
   database-only. A hand-maintained mirror with no consistency check will drift again — have
   `opsdb.py` verify every `decisions` row appears in the file. (§6)
8. **Perform DEC-019's owed export.** Add `opsdb.py export` writing deterministic, diffable
   snapshots of `decisions`, `approvals`, `risks`, `tasks` + status and
   `ideas`/`idea_edits`/`idea_rounds` to git-tracked files. The Founder's approved brief — the
   declared source of truth for all downstream work — currently has no backup and no export. (§6)
9. **Document the new surface.** `ops/DATA_MODEL.md` gets the three idea tables;
   `ops/SECURITY.md` gets a TASK-024 section covering the second HTTP server, the second session
   store, the sixth allowlist and the two moved bounds; `ops/ARCHITECTURE.md` gets the Idea Desk.
   Every prior milestone that added a surface did this. (§9.3)
10. **Make immutability structural in the database, not only in one file's command table.** Three
    `RAISE(ABORT)` triggers: no `UPDATE` of `ideas.raw_idea`, no `UPDATE`/`DELETE` on
    `idea_rounds` or `idea_edits`. The comments already claim this property; the schema should
    hold it. (§2)
11. **Record the deviations from Product Revision 4 as a decision, or change the code back.**
    Specifically: the parallel orchestration engine instead of `meeting_orchestrator.py` reuse,
    with the perspectives discarded and never persisted (§2b, §9.1); and the redefinition of
    Edit/Correct (§9.2). Either is defensible; neither is written down.
12. **Before slice 3:** add the idea↔task link, add one shared `render_approved_brief()`, move the
    `review_transcripts.py:203/261` and `launch_developer_session.py:129` call sites onto it, and
    close `task-update`'s ability to overwrite `business_goal`. SOT-1 cannot be run against the
    current schema. Sequence item 2 before this — otherwise SOT-1 can pass while the factory
    builds from a withdrawn reading. (§11)

### Non-blocking, worth fixing while nearby

13. `server.py:263-269` renders an Approve button on a non-approvable round via direct URL; the
    bottom bar correctly hides it. Make the GET check the recommendation too. (§3)
14. `server.py:137` — a subprocess timeout escapes as a 500 rather than a `WriteError`, after the
    write may have committed.
15. `seed_founder_idea.py:27` hardcodes the database path and ignores `OPSDB_PATH`, unlike every
    other component; its writes (via `opsdb.py`) do honour it. Test isolation is inconsistent.
16. An idea whose entire text is a single token starting with `-` (e.g. `-verbose`) is rejected by
    argparse and surfaces to the Founder as "That was refused" with a usage dump. Use `--raw=` or
    a `--` separator. Multi-word text is unaffected.
17. `invoke_agent` (agent_runtime.py:292-299) enforces only the union of six allowlists. Add a
    `category` parameter so the separation the six constants describe is enforced in the module
    that claims it, not in six other files. (§5)
18. Idea Desk `IDLE_TIMEOUT_S` is 60 minutes against the Control Center's 30. One identity, two
    session policies, no stated reason. (§10)
