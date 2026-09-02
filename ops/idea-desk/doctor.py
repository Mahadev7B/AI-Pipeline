#!/usr/bin/env python3
"""ops/idea-desk/doctor.py — answers "why am I not seeing the new version?"

Run it and paste the output. It checks, in one go, every reason the Idea Desk
can show you something other than the code you just pulled:

  * you are in a different folder than the one you pulled into
  * you are on a different branch than the one the work was pushed to
  * the pull did not actually bring the commits down
  * the files on disk are older than the feature you expect
  * an OLD server is still holding the port, so restarting appeared to work
    while the browser kept talking to the process from before
  * the `claude` command is missing, so evaluation cannot run

    python3 ops/idea-desk/doctor.py        (macOS/Linux)
    python ops\\idea-desk\\doctor.py         (Windows)
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PORT = 8421


def line(label: str, value: str, ok: bool | None = None) -> None:
    mark = "  " if ok is None else ("OK" if ok else "!!")
    print(f"{mark} {label:<34} {value}")


def git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip()
    except Exception as exc:  # git missing, or not a repo
        return f"(could not run git: {exc})"


def main() -> None:
    print("\nIdea Desk — what is actually running here\n" + "=" * 52)

    print("\nWHERE")
    line("this file is in", str(HERE))
    line("project folder", str(REPO))

    print("\nGIT")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    line("current branch", branch, ok=(branch == "claude/orchestrator-chief-of-staff-f35grl"))
    if branch != "claude/orchestrator-chief-of-staff-f35grl":
        print("     ^ the work is pushed to claude/orchestrator-chief-of-staff-f35grl.")
        print("       On any other branch, `git pull` brings you none of it. Fix with:")
        print("         git checkout claude/orchestrator-chief-of-staff-f35grl")
        print("         git pull")
    line("last commit here", git("log", "-1", "--format=%h %s")[:78])
    dirty = git("status", "--porcelain")
    line("uncommitted changes", "none" if not dirty else f"{len(dirty.splitlines())} file(s)")

    print("\nFILES ON DISK")
    server_py = HERE / "server.py"
    evaluator_py = HERE / "evaluator.py"
    line("server.py present", "yes" if server_py.exists() else "NO", ok=server_py.exists())
    line("evaluator.py present", "yes" if evaluator_py.exists() else "NO — slice 2 was not pulled",
         ok=evaluator_py.exists())
    if server_py.exists():
        text = server_py.read_text(encoding="utf-8", errors="replace")
        has_eval = "evaluator.start(" in text
        line("evaluate is wired in the file", "yes" if has_eval else "NO — this file is the old one",
             ok=has_eval)
        stamp = next((ln.split("=", 1)[1].strip().strip('"')
                      for ln in text.splitlines() if ln.startswith("BUILD =")), "(no build stamp)")
        line("build stamp in the file", stamp)

    print("\nTHE PORT")
    probe = socket.socket()
    probe.settimeout(1.5)
    in_use = probe.connect_ex(("127.0.0.1", PORT)) == 0
    probe.close()
    line(f"something listening on {PORT}", "yes" if in_use else "no")
    if in_use:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/login", timeout=5) as resp:
                served = resp.read().decode("utf-8", errors="replace")
            running_old = "Idea Desk" in served
            line("it answers as the Idea Desk", "yes" if running_old else "no — something else",
                 ok=running_old)
        except urllib.error.URLError as exc:
            line("could not talk to it", str(exc))
        print("\n     A server is ALREADY RUNNING on this port. Starting a second one does not")
        print("     replace it — the new one fails to take the port and your browser keeps")
        print("     talking to the OLD process, which is still running the OLD code.")
        print("     Stop every one of them first:")
        print("       Windows      :  Get-Process python | Stop-Process")
        print("       macOS/Linux  :  pkill -f idea-desk/server.py")
        print("     then start it once, and watch for the startup line.")
    else:
        print("\n     Nothing is holding the port, so a fresh start will be the one you reach.")

    print("\nEVALUATION REQUIREMENTS")
    claude = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    line("`claude` command", claude or "NOT FOUND — evaluation cannot run", ok=bool(claude))
    if os.environ.get("CLAUDE_BIN"):
        line("  (from CLAUDE_BIN)", os.environ["CLAUDE_BIN"])
    if not claude:
        print("     Everything else works without it: writing ideas, reading past evaluations,")
        print("     approving, parking. Only evaluation needs it. To install:")
        print("       npm install -g @anthropic-ai/claude-code")
        print("     then run `claude` once to sign in, and restart the Idea Desk.")
        print("     If your TERMINAL finds claude but this does not, they are looking at")
        print("     different PATHs — a terminal opened before the install still has the old")
        print("     one. Open a new terminal, or point us at it directly:")
        print("       Windows      :  $env:CLAUDE_BIN = 'C:\\full\\path\\to\\claude.cmd'")
        print("       macOS/Linux  :  export CLAUDE_BIN=/full/path/to/claude")
    cred = REPO / "ops" / "control-center" / ".founder_credential.json"
    line("your passphrase is set up", "yes" if cred.exists() else "NO — run founder_auth.py setup",
         ok=cred.exists())
    db = REPO / "ops" / "db" / "operations.sqlite3"
    line("database present", "yes" if db.exists() else "NO — run opsdb.py init", ok=db.exists())

    print("\nCAN IT ACTUALLY ASK AN AGENT?")
    if not claude:
        line("live check", "skipped — no claude command to try")
    else:
        # Existing on disk and WORKING are different questions, and only this
        # one matters. Checking the first and reporting the second is how the
        # Founder ends up staring at a failure the doctor called healthy.
        # One tiny call, a few cents at most.
        sys.stdout.write("   asking the Chief of Staff to reply 'OK' (up to 2 min)... ")
        sys.stdout.flush()
        try:
            sys.path.insert(0, str(REPO / "ops" / "control-center"))
            import agent_runtime
            result = agent_runtime.invoke_agent("orchestrator", "Reply with exactly: OK",
                                                timeout_s=120)
            print()
            if result.ok:
                line("agent replied", repr((result.response_text or "")[:40]), ok=True)
                line("model", result.model_used or "(not reported)")
                # Deliberately NOT called "cost". The runtime reports the token
                # value of the call; whether that is a charge depends on how the
                # account is billed. On a subscription nothing is billed per
                # call — it draws down usage limits instead. Printing "$0.02
                # cost" to someone on a subscription is simply untrue.
                line("token value of this call",
                     f"${result.cost_usd:.4f}" if result.cost_usd is not None else "(not reported)")
                print("\n     Evaluation will work. That figure is the token value of ONE call;")
                print("     an evaluation is four to six. Whether it is an actual charge depends")
                print("     on your account: with no ANTHROPIC_API_KEY set, Claude Code uses the")
                print("     account you signed into, and usage draws on that plan rather than")
                print("     being billed per call. Check with /status inside `claude`.")
            else:
                line("agent FAILED", f"[{result.error_kind}] {result.error}"[:200], ok=False)
                if result.error_kind == "runtime_unavailable":
                    print("     claude is on PATH but could not be launched.")
                elif result.error_kind == "timeout":
                    print("     It did not answer in 120s. Usually a sign-in prompt waiting")
                    print("     unseen, or a slow first run. Try `claude` in a terminal first.")
                else:
                    print("\n     This is the real reason evaluation fails. The most common causes:")
                    print("       * not signed in — run `claude` then /login, and check /status")
                    print("       * no billing set up on the account it signed in as")
                    print("       * the agent files are missing — this repo needs .claude/agents/")
        except Exception as exc:
            print()
            line("live check crashed", f"{type(exc).__name__}: {exc}"[:160], ok=False)

    print("\n" + "=" * 52)
    print("Paste all of the above if it still misbehaves.\n")


if __name__ == "__main__":
    main()
