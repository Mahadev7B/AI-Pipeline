# Red Team review — Phase 2, Milestone 2B2 architecture

TASK-007. Reviewing `ops/reviews/cto-milestone2b2-architecture.md` before
any code is written. Full findings recorded via `opsdb.py review-result
--task-id 7 --type code --by red-team`. This file mirrors that record.

## Verdict: PASS with conditions

Core design is sound and not overengineered: the `agent_runtime.py`
boundary, server-side-only allowlist, argv-list `subprocess.run` (no
shell-injection surface), additive-only schema migration, and
`--no-session-persistence` keeping `messages`/`agent_runs` as the sole
store all correctly target the brief. No simpler design was found that
still satisfies every hard requirement. Confirmed: zero-tools-for-v1 is
the right call (stronger reasoning than the proposal itself gave — every
one of the five allowlisted agents' *normal* configured toolset in
`.claude/agents/*.md` includes Bash, `cto` also Write/Edit, so these are
not "read-oriented" agents by native configuration, only by this
milestone's runtime-level restriction). No rename of `messages.scope`
needed. `queued` folded into `active` is acceptable once disclosed.

## Conditions Development must close

1. **Tool-restriction gap: `--tools ""` alone doesn't address WebFetch/
   MCP-provided tools with the same rigor as built-in Bash/Write/Edit.**
   Red Team's own testing of `claude --help` found a purpose-built
   `--restricted` flag that additionally strips WebFetch. **Correction
   found during Development's own follow-up verification, recorded here
   rather than silently substituted:** `--restricted` cannot actually be
   used — it "ignores user, project and local settings files," which
   includes the project's own `.claude/agents/*.md` definitions.
   Confirmed empirically: `claude --agent cto --restricted ...` fails
   with `--agent 'cto' not found`, since `--restricted` disables exactly
   the mechanism that loads a custom project agent. Using it would
   directly violate the brief's "the agent must actually receive its own
   role/configuration" requirement. **Resolution:** `--tools ""` (zero
   built-in tools, stronger than `--restricted`'s "confined file tools" —
   there are no tools at all) plus `--strict-mcp-config` with no
   `--mcp-config` passed (zero MCP servers loaded, closing the gap
   `--restricted` would have addressed via a different mechanism).
   Verified empirically: with this combo, `--agent cto` still loads the
   real persona; a prompt explicitly asking for WebFetch got either a
   clean text refusal or (in the Bash/Grep case tested earlier) an
   actual attempted-and-denied tool call with an empty `permission_denials`
   showing no successful invocation. Security must independently
   re-verify this holds — this is exactly the kind of self-correction
   that needs adversarial re-checking, not just trusting Development's
   own test.
2. **Subprocess hardening**: use `subprocess.Popen` with
   `start_new_session=True` so a timeout can kill the whole process
   group (`os.killpg`), not just the immediate child, in case `claude`
   spawns anything; pass an explicit `env=os.environ.copy()` (deliberate,
   reviewable, not implicit inheritance); cap captured stdout at a fixed
   byte ceiling rather than reading unbounded output.
3. **Cap the agent's stored response size** — only an inbound 8KB
   Founder-message cap was proposed; the outbound side has no cap and
   could grow unbounded.
4. **Explicit stored-XSS test** on the new conversation thread — `e()`
   must be applied to both Founder and agent message bodies; QA must run
   a seeded `<script>` payload test, mirroring the one already run for
   Milestone 2B1's Decisions/Meetings screens.
5. **Single-threaded blocking is broader than the proposal disclosed.**
   `HTTPServer` is sequential — while `do_POST` is blocked inside
   `subprocess.run()` for one Ask-Agent call, *every other request*
   (a different agent's Ask-Agent call, or just someone loading
   `/overview.html`) waits behind it, not only same-agent requests.
   Must be explicitly disclosed in `SECURITY.md`/the founder report, and
   the default timeout lowered well below the proposed 90s — measured
   real latency in testing was ~3-13s, so 90s is an unnecessarily long
   worst-case block for the entire Control Center.
6. **Orphaned open-run recovery.** If the server process crashes or is
   killed mid-request, the `agent_runs` row it created stays open
   (`ended_at IS NULL`) forever, and the "one open run per agent → 409"
   guard would then permanently block all future requests to that agent.
   Require a startup reconciliation pass that marks any pre-existing
   open Ask-Agent run as `failed` before serving traffic — scoped
   specifically to Ask-Agent-created runs (not every `agent_runs` row
   system-wide, which would incorrectly touch legitimate long-running
   rows created by other means, e.g. this project's own review-gate
   tracking).
7. **`SECURITY.md` must disclose the reused token now gates two write
   routes with different blast radii**, and must state plainly that the
   five allowlisted agents' *normal* tool access (outside Ask-Agent)
   includes Bash (`cto` also Write/Edit) — Ask-Agent's zero-tool
   restriction is specific to this one invocation path, not a change to
   the agents' underlying role definitions.

## Non-blocking notes

- Migration technique is sound — no FK references `agent_runs`, all 13
  live rows are `'ended'`, nothing needs reinterpretation. Must
  re-`CREATE INDEX idx_runs_agent_open` after the rebuild-and-copy (SQLite
  drops indexes with the table).
- `cmd_run_end` should gain the same atomic `WHERE ended_at IS NULL`
  guard `decide_approval()` already has, so a run can't be double-ended
  or have its `ended_at` overwritten by a second call.
- The single deterministic per-agent thread (`agent-<name>-company`) has
  no reset mechanism — acceptable for this milestone, a near-term
  follow-up, not a blocker.
- Pin an actual `--max-budget-usd` value (e.g. $0.50, matching what
  Development already tested successfully) and document the assumed
  failure mapping if a call ever exceeds it (non-zero exit / `is_error`,
  caught as `runtime_error`).
- Confirmed: no agent named `'founder'` exists in the live `agents`
  table — no collision risk between the literal string `'founder'` and
  a real registered agent.
