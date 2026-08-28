# Security Review — Phase 1 (TASK-002)

## Scope

`ops/db/schema.sql`, `ops/db/opsdb.py`, `ops/db/report.py`,
`.claude/agents/*.md` (14 subagent configs), and the committed
`ops/db/operations.sqlite3` file.

## Findings

1. **No credentials, secrets, or PII anywhere in the schema or code.**
   Confirmed by grep across all reviewed files — the only matches are
   documentation prose about the *concept* of credentials (e.g. "must not
   access real credentials"), not an actual value. **PASS.**
2. **SQL injection: not present.** Every write goes through a
   parameterized query (`?` placeholders). The one place that previously
   built a SQL fragment with an f-string (`task-step-status`) used a
   hardcoded constant, not user input, but was rewritten to a fully
   parameterized `CASE` expression during Code Review regardless —
   confirmed clean on re-inspection. **PASS.**
3. **Foreign keys are actually enforced.** `connect()` sets `PRAGMA
   foreign_keys = ON` on every connection, matching the Red Team
   requirement. **PASS.**
4. **Approval decisions had no guard at all — REJECTED, then fixed.**
   `approval-decide` let any caller record a Founder decision, including
   an agent deciding its own request — directly contradicting
   `DATA_MODEL.md`'s rule that only the Founder ever sets
   `approvals.decision`. Fixed: `approval-decide` now requires an
   explicit `--confirm-founder-decision` flag and refuses otherwise. This
   is **not real authentication** — anything running the CLI can still
   pass the flag — but it makes deciding a Founder-only action a
   deliberate, visible, separately-typed step rather than something an
   agent's normal workflow could do by accident. Real enforcement
   requires an identity layer, which is Phase 2/3 (Control Center)
   scope, not Phase 1. **Flagged as a known gap, not a blocker** — see
   the Founder-facing functional-vs-mocked summary.
5. **`deployment-record` correctly enforces founder authorization at the
   schema level** (`CHECK (founder_authorized = 1)`), not just in the
   CLI — this one can't be bypassed by skipping a flag the way #4 could
   before its fix, since the database itself refuses the row. **PASS.**
6. **File permissions.** `ops/db/operations.sqlite3` was `rw-r--r--`
   (world-readable) after `init`; tightened to `rw-------` (owner only).
   Low severity given nothing sensitive is stored, but no reason not to
   default it correctly. **Fixed.**
7. **Bash is not scoped to `opsdb.py` subcommands.** Every subagent's
   `tools:` frontmatter grants the `Bash` tool category (needed to run
   `opsdb.py`), but Claude Code's subagent tool restriction operates at
   the tool-category level, not the shell-command level — a `red-team`
   or `qa` subagent invocation technically *could* run an arbitrary
   shell command, not just the CLI its role doc describes. This is an
   environment-level limitation, not a bug in this Phase 1 code, and
   matches what was already disclosed in `ops/reviews/red-team-schema.md`
   territory. **Flagged as a known gap, not a blocker.**

## Verdict

**PASS**, with findings #4 and #7 flagged as known, disclosed gaps (not
blockers) for the Founder-facing summary — #4 was mitigated with a
speed-bump flag; #7 has no Phase-1-appropriate fix (real enforcement
needs an identity/permission layer that doesn't exist until the Control
Center or a future Claude Code permission-scoping feature).
