#!/usr/bin/env python3
"""ops/control-center/hooks/test_developer_pretooluse.py — TASK-023
regression check for the two secondary bug fixes named in §5 of
ops/reviews/cto-task023-architecture.md (folded in from TASK-017's
remaining cheap-fix list):

1. The leading-space " gdb"/" strace" substring bug — `_check_bash()`
   must catch gdb/strace as the FIRST token on a command line (no leading
   space to match against), and must NOT false-positive on an unrelated
   token that merely contains "gdb"/"strace" as a substring.
2. The `shlex.split()` quadratic-blowup hang — a `command` string over
   `_MAX_BASH_COMMAND_CHARS` must be denied before `shlex.split()` is
   ever called, and the deny reason must say so (not a shlex parse
   failure, since shlex is never reached).

No OS/database dependency — this hook has none (stdlib-only, per its own
module docstring), so this test calls its pure functions directly, no
subprocess, no live daemon, no ai-developer account.

Usage: python3 ops/control-center/hooks/test_developer_pretooluse.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import developer_pretooluse as h  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def bash_result(command: str):
    return h._check_bash({"command": command})


def main() -> int:
    # ---- Bug 1: gdb/strace as the FIRST token (no leading space) ----
    result = bash_result("gdb -p 1234")
    check("'gdb -p 1234' (gdb as first token, no leading space) is denied",
          result is not None and result[0] == "deny", str(result))

    result = bash_result("strace -p 1234")
    check("'strace -p 1234' (strace as first token) is denied",
          result is not None and result[0] == "deny", str(result))

    # ---- Bug 1: gdb/strace mid-command (the case the old " gdb" substring DID catch) ----
    result = bash_result("sudo gdb -p 1234")
    check("'sudo gdb -p 1234' (gdb as a later token) is still denied",
          result is not None and result[0] == "deny", str(result))

    # ---- Bug 1: gdb/strace via an absolute/relative path ----
    result = bash_result("/usr/bin/gdb -p 1234")
    check("'/usr/bin/gdb -p 1234' (gdb via absolute path) is denied",
          result is not None and result[0] == "deny", str(result))

    # ---- Bug 1: no false positive on an unrelated token containing the substring ----
    result = bash_result("echo outgdbstuff strace-like-name-but-not-real")
    check("a token that merely CONTAINS 'gdb'/'strace' as a substring is NOT denied by the token check",
          result is None, str(result))

    # ---- Bug 1: the fix must not weaken the plain-substring checks that
    #      still exist for other protected paths ----
    result = bash_result("cat .claude/agents/developer.md")
    check("unrelated existing denylist behavior (self-protection path) still works",
          result is not None and result[0] == "deny", str(result))

    result = bash_result("echo hello world")
    check("an ordinary, unrelated command is still allowed",
          result is None, str(result))

    # ---- Bug 2: the length ceiling denies BEFORE shlex.split() is reached ----
    huge_command = "echo " + ("a" * (h._MAX_BASH_COMMAND_CHARS + 1))
    result = bash_result(huge_command)
    check("a command over the length ceiling is denied",
          result is not None and result[0] == "deny", str(result))
    check("the deny reason names the length ceiling, not a shlex failure",
          result is not None and "ceiling" in result[1], str(result))

    # ---- Bug 2: a command right at/under the ceiling is unaffected ----
    ok_command = "echo " + ("a" * (h._MAX_BASH_COMMAND_CHARS - 100))
    result = bash_result(ok_command)
    check("a large but under-ceiling command is not denied for its length",
          result is None or "ceiling" not in (result[1] if result else ""), str(result))

    # ---- Bug 2: the adversarial quadratic-blowup input itself must return quickly ----
    # A long run of unbalanced quote characters is the documented
    # pathological shlex.split() input. Before the fix, this could hang;
    # after the fix, the length ceiling denies it long before shlex is
    # ever called. Bounded well under the whole test suite's own
    # reasonable running time.
    adversarial = "'" * (h._MAX_BASH_COMMAND_CHARS + 5000)
    start = time.monotonic()
    result = bash_result(adversarial)
    elapsed = time.monotonic() - start
    check("the pathological shlex.split() input returns quickly (length ceiling short-circuits it)",
          elapsed < 2.0, f"took {elapsed:.3f}s")
    check("the pathological input is denied (not allowed)",
          result is not None and result[0] == "deny", str(result))

    # ---- End-to-end sanity via _evaluate() (both fields' branching still correct) ----
    decision, rule = h._evaluate({"tool_input": {"command": "gdb -p 1"}})
    check("_evaluate() end-to-end: 'gdb -p 1' denies", decision == "deny", rule)

    decision, rule = h._evaluate({"tool_input": {"file_path": "/tmp/whatever.py"}})
    check("_evaluate() end-to-end: an ordinary Write/Edit outside the repo still denies (existing behavior)",
          decision == "deny", rule)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
