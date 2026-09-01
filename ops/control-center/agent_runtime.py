"""ops/control-center/agent_runtime.py — Phase 2, Milestone 2B2.

The Agent Runtime boundary. `invoke_agent()` is the ONLY function
server.py calls to turn a registered agent identity + a conversation
transcript into a real model response. This module knows nothing about
SQLite, HTTP, or the browser — that separation is what keeps the
application-facing interface (RuntimeResult, invoke_agent) provider/
model-neutral in practice: a future different runtime adapter only has
to implement the same signature, and nothing in server.py, generate_agents.py,
or the schema would need to change.

The only implementation today shells out to the Claude Code CLI's own
`--agent` mechanism — sanctioned as the "smallest correct" first adapter
(see ops/reviews/cto-milestone2b2-architecture.md). It runs with ZERO
tool access (`--tools ""`) and zero MCP servers (`--strict-mcp-config`,
no --mcp-config passed) — verified adversarially before this was written
(asked the cto agent to run a shell command, fetch a URL, and read a
file; every attempt was denied or self-refused, nothing executed). See
ops/reviews/red-team-milestone2b2-architecture.md, condition 1, for why
`--restricted` was considered and rejected (it disables the project's
own `.claude/agents/*.md` definitions, breaking the requirement that the
agent receive its own real configuration).

The browser never influences any of these flags — it only ever sends an
agent *name* and a message; server.py validates the name against
ASK_AGENT_ALLOWLIST before this module is ever called.

CONCURRENCY (Milestone 2B3A): server.py is now multi-threaded
(http.server.ThreadingHTTPServer), so invoke_agent() can genuinely be
called from several threads at once. The number of real `claude`
subprocesses that may run simultaneously is bounded by
MAX_CONCURRENT_INVOCATIONS via a non-blocking threading.BoundedSemaphore
— HTTP/read traffic is not bounded at all, only this expensive resource
is. A caller that can't get a slot gets error_kind="capacity_exceeded"
immediately, never a silent wait. This module still knows nothing about
threads beyond the semaphore itself — no shared mutable state exists
here besides it, and BoundedSemaphore is thread-safe by construction.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass

# The only agents Ask-Agent may invoke in Milestone 2B2 — deliberately
# conservative, read-oriented roles only, per the Founder's brief. Every
# one of these agents' NORMAL (non-Ask-Agent) tool configuration in
# .claude/agents/*.md includes Bash (cto also Write/Edit) — this
# allowlist does not mean these are read-only agents by nature, only
# that Ask-Agent invokes them with zero tool access regardless of their
# native configuration. See ops/SECURITY.md.
ASK_AGENT_ALLOWLIST = ("cto", "qa", "ceo", "financial", "project-manager")

# The single source of truth for "this agent_runs row is Ask-Agent's."
# server.py's start_run() call uses the label; every place that needs to
# find/scope Ask-Agent runs (the UI status query, the 409 guard, startup
# reconciliation) uses the LIKE pattern — one constant, not four
# hand-typed copies. CTO's Milestone 2B2 post-implementation review
# flagged that exact category of drift (a scoping predicate copied
# inline in multiple places) as the root cause of Code Review's earlier
# blocking finding; centralizing it here closes that risk structurally.
ASK_AGENT_ACTIVITY_LABEL = "Ask-Agent: answering a Founder question"
ASK_AGENT_ACTIVITY_LIKE = "Ask-Agent:%"

# Milestone 2B3B: Executive Meetings. Every one of these eight roles is
# exactly what ops/EXECUTIVE_MEETINGS.md names as a typical participant.
# The four not already in ASK_AGENT_ALLOWLIST (product, marketing,
# security, red-team) each have Bash in their NORMAL configuration
# (.claude/agents/*.md) — same risk profile the other five had before
# zero-tool invocation neutralized it. The same restriction applies
# here, for the same reason — not a new safety model, the existing one
# extended to more role names. CEO is always a participant (added by
# meeting_orchestrator.py, not by this allowlist alone) — it also
# performs the meeting's synthesis, a role none of the others play.
MEETING_PARTICIPANT_ALLOWLIST = ("ceo", "product", "cto", "financial", "marketing", "qa", "security", "red-team")
MEETING_ACTIVITY_LABEL = "Meeting: contributing a position"
MEETING_ACTIVITY_LIKE = "Meeting:%"
MAX_MEETING_PARTICIPANTS = 6  # CEO + up to 5 others — see cto-milestone2b3b-architecture.md

# TASK-020 (Milestone B), CTO's architecture doc §2.4: three CEO/agent
# invocations inside meeting_orchestrator.py that previously had NO
# agent_runs row at all (_select_participants(), _synthesize(),
# gather_followup_reply()) — needed so a meeting's per-invocation cost
# total isn't silently missing its most expensive call (CEO's synthesis
# processes every participant's full position text). All three labels
# deliberately start with "Meeting:" so they match the existing
# MEETING_ACTIVITY_LIKE = "Meeting:%" grouping pattern already used
# everywhere runs are scoped/grouped by path (startup reconciliation,
# /costs.html's by-path breakdown) — no new LIKE pattern needed.
MEETING_SELECT_PARTICIPANTS_ACTIVITY_LABEL = "Meeting: selecting participants"
MEETING_SYNTHESIS_ACTIVITY_LABEL = "Meeting: synthesizing"
MEETING_FOLLOWUP_ACTIVITY_LABEL = "Meeting: follow-up reply"

# Phase 3A Part A (TASK-015): the Chief of Staff Founder Interface. A
# third, distinct invocation category — Founder-typed, not meeting-
# selected, not Ask-Agent's five-role allowlist — for exactly one agent
# identity. This is the first-ever real `claude --agent orchestrator`
# invocation in this system's history: every prior appearance of
# `orchestrator` in agent_runs/task_status_history (e.g.
# ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL below) is a deterministic Python
# step wearing that identity's name for attribution, never a subprocess.
# `orchestrator` is deliberately NOT added to ASK_AGENT_ALLOWLIST — see
# ops/reviews/cto-phase3a-architecture.md §A.1 for why this gets its own
# route (POST /api/chief-of-staff/ask) and its own allowlist rather than
# a silent special case bolted onto Ask-Agent's existing route.
CHIEF_OF_STAFF_ALLOWLIST = ("orchestrator",)
CHIEF_OF_STAFF_ACTIVITY_LABEL = "Chief of Staff: answering a Founder question"
CHIEF_OF_STAFF_ACTIVITY_LIKE = "Chief of Staff:%"

# Phase 3A Part B (TASK-015): the automation poller's single automated
# invocation category — a background actor, not a Founder-typed message or
# a meeting selection, so it gets its own allowlist too, per this file's
# own convention (a fourth distinct category, same reasoning as
# CHIEF_OF_STAFF_ALLOWLIST above). `code-review`'s NORMAL configuration
# (.claude/agents/code-review.md) includes Bash/filesystem access — this
# allowlist means the automated mode invokes it with zero tools regardless
# of that, exactly the same restriction every other allowlist here already
# applies, extended to an invocation not even triggered by a Founder
# action. See ops/reviews/cto-phase3a-architecture.md §B.1.
AUTOMATED_REVIEW_ALLOWLIST = ("code-review",)
AUTOMATED_CODE_REVIEW_ACTIVITY_LABEL = "Automated Code Review: reviewing a completed Developer handoff"
AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE = "Automated Code Review:%"
# §B.1.1 (Phase 3A): real code review plausibly needs longer than a short
# Ask-Agent exchange. TASK-017 (risks.id=3 reduction milestone) renames
# this from AUTOMATED_REVIEW_TIMEOUT_S — it is no longer only the
# poller's own timeout: the three new synchronous reviewer routes
# (reviewer_sync.py) need the identical "real review plausibly takes
# longer" allowance, since a genuine review is genuine work regardless of
# whether a background poller or a human's click triggered it. A
# synchronous HTTP request blocking the handling thread for up to 120s is
# the same disclosed tradeoff Ask-Agent's own DEFAULT_TIMEOUT_S design
# already accepted, just a larger number for a genuinely longer real task
# (ops/reviews/cto-risk3-milestone-architecture.md §1.3.2).
REVIEW_TIMEOUT_S = 120.0

# TASK-017 (risks.id=3 reduction milestone), §1: the three new
# synchronous, zero-tool reviewer routes (POST /api/tasks/<id>/review/
# {code,security,red-team}) — a fifth distinct invocation category, same
# reasoning as CHIEF_OF_STAFF_ALLOWLIST/AUTOMATED_REVIEW_ALLOWLIST above.
# `security`/`red-team`'s NORMAL configuration (.claude/agents/*.md)
# includes Bash — this allowlist means a synchronous review invokes them
# zero-tool regardless of that, the same restriction every other
# allowlist here already applies. Distinct from AUTOMATED_REVIEW_ALLOWLIST
# (poller-only, code-review-only) — a human-triggered invocation of any
# of the three reviewer roles, not an unattended background process.
REVIEWER_SYNC_ALLOWLIST = ("code-review", "security", "red-team")
REVIEWER_SYNC_ACTIVITY_LABEL = "Synchronous review: reviewing a Founder-triggered gate review"
REVIEWER_SYNC_ACTIVITY_LIKE = "Synchronous review:%"

# Milestone 2B3B round 2 (TASK-011): request-perspective, follow-up, and
# retry. ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL is Orchestrator's real,
# attributed agent_runs row for validating CEO's participant nomination
# (item 1) — a deterministic Python step, never a `claude --agent
# orchestrator` invocation, so it needs no allowlist entry.
ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL = "Orchestrator: validating meeting participant selection"
# TASK-011 QA round 2, defect 1: server.py's startup reconciliation only
# ever scanned ASK_AGENT_ACTIVITY_LIKE and MEETING_ACTIVITY_LIKE, so an
# orphaned Orchestrator-validation run (current_activity starting with
# "Orchestrator:") matched neither pattern and was never cleaned up on
# restart — same LABEL/LIKE-pair convention as the two constants above,
# so _reconcile_orphaned_runs() can cover this run type too.
ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE = "Orchestrator:%"

# Item 5 (manual retry of a failed participant). Affirmed as reasonable by
# Red Team's Milestone 2B3B round 2 review (a retry re-attempts a slot
# already counted in MAX_MEETING_PARTICIPANTS, it doesn't add headcount —
# a materially different case from item 2's rejected cap revision, see
# below). Enforced atomically by opsdb.start_meeting_retry_run().
MAX_RETRIES_PER_PARTICIPANT = 2

# Deliberately NOT defined here: MAX_REQUESTED_PARTICIPANTS. CTO's
# Milestone 2B3B round 2 proposal introduced one to let a manually-
# requested participant (item 2, request-perspective) exceed
# MAX_MEETING_PARTICIPANTS. Red Team's review of that round (finding 1)
# did not affirm it — the mockup evidence cited for the revision didn't
# support the specific number proposed, and the revision compounded with
# retries into a materially larger cost bound than what was previously
# reviewed. Per Red Team's disposition, a manually-requested participant
# counts against the SAME MAX_MEETING_PARTICIPANTS total cap as everyone
# else (enforced in opsdb.add_meeting_participant()) — there is no second,
# larger allowance. If the Founder later authorizes a carve-out on a
# corrected framing, that is a separate, future change, not this one.

# Aggregate worst-case cost — disclosed once, here, per Red Team's
# Milestone 2B3B round 2 review (condition 2): the first pass disclosed a
# single closed-form number for its own scope (~8 invocations, ~$4) and
# this round must too, rather than leaving each new mechanism's bound
# individually true but never summed.
#
#   1                                              CEO's selection call
# + MAX_MEETING_PARTICIPANTS * (1 + MAX_RETRIES_PER_PARTICIPANT)  [6*3=18]
#                   every one of the up to 6 total participant slots —
#                   CEO-selected or manually-requested, in any mix, since
#                   both draw from the one shared cap — gathered once,
#                   then retried up to MAX_RETRIES_PER_PARTICIPANT times
# + 1                                              CEO's synthesis call
# = 20 real, MAX_BUDGET_USD-capped `claude` invocations per meeting,
#   worst case — roughly $10.00 at $0.50/invocation.
#
# Orchestrator's own validation step (above) adds zero invocations to
# this figure — it's pure Python, never a subprocess. This total does
# NOT include POST /api/meetings/<id>/followup: that route has no per-
# thread round cap (deliberate parity with Ask-Agent's own unbounded-
# rounds design — see meeting_orchestrator.py), but unlike Ask-Agent's
# fixed 5 possible threads, a follow-up thread exists per (meeting,
# participant) and that number grows without bound as meetings
# accumulate — so no single closed-form ceiling covers it; each
# individual follow-up call is still bounded at $0.50. See
# ops/SECURITY.md, "Executive Meetings round 2," for the disclosure.

DEFAULT_TIMEOUT_S = 30.0  # measured real latency in testing was ~3-13s; see Red Team condition 5 —
                          # the whole single-threaded server blocks for the duration of this call
MAX_BUDGET_USD = "0.50"
MAX_RESPONSE_CHARS = 16_000  # cap on what gets persisted, independent of any model-side output limit
_MAX_CAPTURED_BYTES = 512_000  # cap on what we parse/use from stdout, not a true read-time ceiling —
                                # proc.communicate() reads all of stdout before this slice is applied.
                                # Accepted (Code Review, TASK-007): --output-format json bounds a real
                                # claude invocation's output to the model's own max-output-tokens
                                # (tens of KB in practice), so this is a defensive cap against a
                                # malformed/oversized response, not primary protection against an
                                # untrusted runtime — if the `claude` binary itself were compromised,
                                # this cap would not be the relevant safeguard.

CLAUDE_BIN = "claude"

# Milestone 2B3A: bounds the number of `claude` subprocesses that may run
# at once, regardless of how many HTTP threads exist — GET/read traffic
# is not bounded at all (SQLite handles concurrent readers cheaply; a
# single trusted local Founder can't realistically generate enough of it
# to matter). Only the expensive resource (a real, costed model
# invocation) is bounded. 3 gives headroom for this milestone's own
# 2-concurrent-agent acceptance test without inviting real resource/cost
# exposure on a single local machine, and anticipates a future Executive
# Meeting's likely participant count without pre-committing to that
# milestone's still-unreviewed design. Not configurable from the browser
# — a module constant, never derived from any request. See
# ops/reviews/cto-milestone2b3a-architecture.md and
# ops/reviews/red-team-milestone2b3a-architecture.md (both affirm this
# value).
MAX_CONCURRENT_INVOCATIONS = 3
_INVOCATION_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_INVOCATIONS)


@dataclass
class RuntimeResult:
    ok: bool
    response_text: str | None = None
    model_used: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    error: str | None = None
    # invalid_agent | capacity_exceeded | runtime_unavailable | timeout | runtime_error
    error_kind: str | None = None


def invoke_agent(agent_name: str, transcript: str, timeout_s: float = DEFAULT_TIMEOUT_S,
                  wait_for_slot: bool = False) -> RuntimeResult:
    """wait_for_slot (Milestone 2B3B, default False): the Ask-Agent HTTP
    route never sets this — an ad-hoc single request still fails fast
    and honestly on capacity_exceeded, exactly the 2B3A behavior,
    unchanged. Only ops/control-center/meeting_orchestrator.py passes
    True, because a meeting needs a real position from every selected
    participant, not "whichever 3 happened to win the race." True means
    the semaphore acquire blocks (bounded by timeout_s, same as any
    other wait in this function) instead of failing immediately — the
    semaphore's total capacity (MAX_CONCURRENT_INVOCATIONS) is not
    touched either way; this only changes what happens when it's full."""
    if (agent_name not in ASK_AGENT_ALLOWLIST
            and agent_name not in MEETING_PARTICIPANT_ALLOWLIST
            and agent_name not in CHIEF_OF_STAFF_ALLOWLIST
            and agent_name not in AUTOMATED_REVIEW_ALLOWLIST
            and agent_name not in REVIEWER_SYNC_ALLOWLIST):
        return RuntimeResult(ok=False, error=f"'{agent_name}' is not enabled for agent invocation.",
                              error_kind="invalid_agent")

    if wait_for_slot:
        acquired = _INVOCATION_SEMAPHORE.acquire(blocking=True, timeout=timeout_s)
    else:
        # Non-blocking acquire, never a wait queue — an honest, immediate
        # "at capacity" signal is simpler and more predictable than a second
        # timeout-within-a-timeout (Red Team's Milestone 2B3A review,
        # question 4).
        acquired = _INVOCATION_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        return RuntimeResult(
            ok=False,
            error=f"at capacity — {MAX_CONCURRENT_INVOCATIONS} agent invocation(s) already running. Try again shortly.",
            error_kind="capacity_exceeded",
        )
    try:
        return _run_claude(agent_name, transcript, timeout_s)
    finally:
        _INVOCATION_SEMAPHORE.release()


def _run_claude(agent_name: str, transcript: str, timeout_s: float) -> RuntimeResult:
    cmd = [
        CLAUDE_BIN,
        "--agent", agent_name,
        "--tools", "",                 # zero built-in tools — see module docstring
        "--strict-mcp-config",         # zero MCP-provided tools (no --mcp-config passed)
        "--no-session-persistence",    # messages/agent_runs must be the only conversation store
        "--output-format", "json",
        "--max-budget-usd", MAX_BUDGET_USD,
        "-p", transcript,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),       # explicit, reviewable — not implicit inheritance
            start_new_session=True,      # own process group, so a timeout can kill the whole tree
        )
    except FileNotFoundError:
        return RuntimeResult(ok=False, error=f"the '{CLAUDE_BIN}' runtime is not available on this machine.",
                              error_kind="runtime_unavailable")

    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        proc.communicate()  # reap
        return RuntimeResult(ok=False, error=f"the agent did not respond within {timeout_s:g}s.",
                              error_kind="timeout")

    if proc.returncode != 0:
        stderr_text = stderr_bytes[:2000].decode("utf-8", errors="replace").strip()
        return RuntimeResult(ok=False, error=stderr_text or f"runtime exited with code {proc.returncode}.",
                              error_kind="runtime_error")

    stdout_bytes = stdout_bytes[:_MAX_CAPTURED_BYTES]
    try:
        data = json.loads(stdout_bytes.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return RuntimeResult(ok=False, error="the runtime returned output that could not be parsed.",
                              error_kind="runtime_error")

    if data.get("is_error"):
        return RuntimeResult(ok=False, error=str(data.get("result") or "the runtime reported an error."),
                              error_kind="runtime_error")

    response_text = data.get("result") or ""
    truncated = len(response_text) > MAX_RESPONSE_CHARS
    if truncated:
        response_text = response_text[:MAX_RESPONSE_CHARS] + "\n\n[response truncated at 16,000 characters]"

    # The substantive completion is whichever entry produced the most output
    # tokens; a cheap classifier pass (if any) shows up with a much smaller
    # share and must not win over the real answer.
    model_used = None
    best_output_tokens = 0
    for usage in (data.get("modelUsage") or {}).values():
        output_tokens = usage.get("outputTokens") or 0
        if output_tokens > best_output_tokens:
            best_output_tokens = output_tokens
            model_used = usage.get("canonicalModel")

    return RuntimeResult(
        ok=True,
        response_text=response_text,
        model_used=model_used,
        cost_usd=data.get("total_cost_usd"),
        duration_ms=data.get("duration_ms"),
    )


def _kill_process_group(proc: subprocess.Popen) -> bool:
    """SIGKILL the child's whole process group. Returns True if the group is
    gone (killed, or already dead), False if this process was NOT PERMITTED
    to signal it — a real outcome the caller must handle, not swallow.

    Existing callers may ignore the return value (nothing changes for them);
    launch_developer_session.py's timeout backstop uses it.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return True
    except ProcessLookupError:
        return True  # already gone — the desired end state either way
    except PermissionError:
        # TASK-023 B2.4 backstop: when this function is reused by
        # launch_developer_session.py, the process group can contain
        # root-owned `sudo` and `ai-developer`-owned `bwrap`/`claude`
        # processes this (Founder-UID) caller is not permitted to signal —
        # os.killpg then raises PermissionError. The PRIMARY wall-clock
        # enforcement for a sandboxed session is an inner
        # `timeout --signal=KILL` running as `ai-developer` against its own
        # process (launch_developer_sandboxed.sh), plus bwrap
        # `--die-with-parent`; this outer kill is only a backstop, so a
        # cross-UID permission failure must degrade gracefully rather than
        # throw in a timer thread and be lost.
        #
        # CODE REVIEW R3: "degrade gracefully" must not mean "silently".
        # This is exactly the case the branch exists for, so it is LOUD —
        # it says what failed and what the caller must now do about it. The
        # caller (see launch_developer_session.py's `_on_timeout` /
        # `_stream_process_output`) is responsible for not blocking forever
        # on a stream belonging to a process nobody could kill.
        sys.stderr.write(
            f"[agent_runtime] WARNING: not permitted to SIGKILL process group "
            f"{_safe_pgid(proc)} (pid {proc.pid}) — a cross-UID kill was refused. "
            "The outer timeout backstop could NOT enforce the wall clock; the "
            "sandbox's own inner `timeout --signal=KILL` and bwrap "
            "--die-with-parent are now the only enforcement.\n"
        )
        sys.stderr.flush()
        return False


def _safe_pgid(proc: subprocess.Popen) -> object:
    """Process-group id for a log line, never raising in an error path."""
    try:
        return os.getpgid(proc.pid)
    except OSError:
        return "unknown"
