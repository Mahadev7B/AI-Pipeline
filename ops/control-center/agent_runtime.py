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
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
from dataclasses import dataclass

# The only agents Ask-Agent may invoke in Milestone 2B2 — deliberately
# conservative, read-oriented roles only, per the Founder's brief. Every
# one of these agents' NORMAL (non-Ask-Agent) tool configuration in
# .claude/agents/*.md includes Bash (cto also Write/Edit) — this
# allowlist does not mean these are read-only agents by nature, only
# that Ask-Agent invokes them with zero tool access regardless of their
# native configuration. See ops/SECURITY.md.
ASK_AGENT_ALLOWLIST = ("cto", "qa", "ceo", "financial", "project-manager")

DEFAULT_TIMEOUT_S = 30.0  # measured real latency in testing was ~3-13s; see Red Team condition 5 —
                          # the whole single-threaded server blocks for the duration of this call
MAX_BUDGET_USD = "0.50"
MAX_RESPONSE_CHARS = 16_000  # cap on what gets persisted, independent of any model-side output limit
_MAX_CAPTURED_BYTES = 512_000  # hard ceiling on subprocess stdout we will ever read into memory

CLAUDE_BIN = "claude"


@dataclass
class RuntimeResult:
    ok: bool
    response_text: str | None = None
    model_used: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    error: str | None = None
    # invalid_agent | runtime_unavailable | timeout | runtime_error
    error_kind: str | None = None


def invoke_agent(agent_name: str, transcript: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> RuntimeResult:
    if agent_name not in ASK_AGENT_ALLOWLIST:
        return RuntimeResult(ok=False, error=f"'{agent_name}' is not enabled for Ask-Agent conversation.",
                              error_kind="invalid_agent")

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

    model_used = None
    model_usage = data.get("modelUsage") or {}
    for _, usage in model_usage.items():
        # the substantive completion is whichever entry actually produced output tokens;
        # a cheap classifier pass (if any) shows up with a much smaller share
        if usage.get("outputTokens"):
            model_used = usage.get("canonicalModel") or model_used

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
