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


def invoke_agent(agent_name: str, transcript: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> RuntimeResult:
    if agent_name not in ASK_AGENT_ALLOWLIST:
        return RuntimeResult(ok=False, error=f"'{agent_name}' is not enabled for Ask-Agent conversation.",
                              error_kind="invalid_agent")

    # Non-blocking acquire, never a wait queue — an honest, immediate
    # "at capacity" signal is simpler and more predictable than a second
    # timeout-within-a-timeout (Red Team's Milestone 2B3A review,
    # question 4). Released in the finally below on every exit path.
    if not _INVOCATION_SEMAPHORE.acquire(blocking=False):
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


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
