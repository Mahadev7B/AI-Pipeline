#!/usr/bin/env python3
"""ops/idea-desk/incidents.py — send a failed evaluation's evidence to GitHub.

When an evaluation fails, `evaluator._preserve_diagnostics` writes everything
the company actually said to `ops/idea-desk/diagnostics/`. That folder is
gitignored on purpose: it holds the Founder's idea in their own words and every
agent's full reading, and those are theirs to publish or not.

The cost of that privacy was that the evidence could only be moved by the
Founder finding a file path in a folder and pasting it somewhere — the exact
"the Founder is the defect router" problem. This module makes it one click
instead, by copying the diagnostic into `ops/incidents/` (which IS tracked) and
committing and pushing it.

Deliberately NOT automatic on failure. Two reasons, and neither is laziness:

  * Pushing publishes the Founder's idea text to GitHub permanently. Git history
    does not forget. That is a decision, and decisions belong to the Founder.
  * This project's standing rule is that nothing reaches outside the machine
    without the Founder starting it.

So the app offers the button and shows exactly what would be published first.
Making it automatic afterwards is a small change; making a push un-happen is not.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DIAGNOSTICS = HERE / "diagnostics"
INCIDENTS = REPO / "ops" / "incidents"

# Credentials can appear inside a remote URL in git's own error output. Never
# echo that back to a page.
_CREDS = re.compile(r"(https?://)[^/\s@]+@")


class ShareError(Exception):
    """Something stopped the share, said in words the Founder can act on."""


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          timeout=timeout)


def _clean(text: str) -> str:
    return _CREDS.sub(r"\1", (text or "").strip())[:600]


def latest_for(idea_id: int) -> Path | None:
    """The most recent diagnostic for this idea, or None if it has none."""
    if not DIAGNOSTICS.is_dir():
        return None
    found = sorted(DIAGNOSTICS.glob(f"idea-{int(idea_id)}-*.txt"))
    return found[-1] if found else None


def preview(path: Path, limit: int = 20000) -> tuple[str, bool]:
    """The file's text and whether it was cut short. The Founder reads this
    BEFORE anything is published — publishing something you have not been shown
    is how a privacy promise quietly becomes false."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return (text[:limit], len(text) > limit)


def already_shared(path: Path) -> Path | None:
    """The copy in ops/incidents/, if this diagnostic was already sent. Sharing
    twice would make two commits saying the same thing."""
    target = INCIDENTS / path.name
    return target if target.exists() else None


def share(idea_id: int, note: str = "") -> str:
    """Copy the newest diagnostic into ops/incidents/, commit it, push it.

    Returns a sentence naming what happened. Raises ShareError with something
    the Founder can act on. Never force-pushes, never touches another file, and
    never commits anything the Founder did not ask to send."""
    src = latest_for(idea_id)
    if src is None:
        raise ShareError("There is no saved evidence for this idea to send. A diagnostic file is "
                         "only written when an evaluation actually fails.")

    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not branch or branch == "HEAD":
        raise ShareError("This checkout is not on a branch, so there is nowhere to push. "
                         "Run <code>git checkout claude/orchestrator-chief-of-staff-f35grl</code> "
                         "and try again.")
    if _git("remote", "get-url", "origin").returncode != 0:
        raise ShareError("This checkout has no <b>origin</b> remote, so there is no GitHub to send "
                         "it to.")

    INCIDENTS.mkdir(parents=True, exist_ok=True)
    target = INCIDENTS / src.name
    fresh = not target.exists()
    if fresh:
        shutil.copy2(src, target)
    # A resend must only ever ADD. Copying over an existing incident erased any
    # note the Founder had added the first time — evidence destroyed by the very
    # feature meant to preserve it. The diagnostic body cannot change anyway:
    # it is written once, when the evaluation fails.
    if note.strip():
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with target.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n----- what the Founder added, {stamp} -----\n{note.strip()}\n")

    rel = target.relative_to(REPO).as_posix()
    added = _git("add", "--", rel)
    if added.returncode != 0:
        raise ShareError(f"Could not stage the file: {_clean(added.stderr)}")

    # A pathspec on commit means ONLY this file goes, whatever else is sitting
    # in the working tree or the index. The Founder asked to send one file.
    subject = f"Idea Desk incident: {src.name}"
    committed = _git("commit", "-m", subject, "--", rel)
    if committed.returncode != 0:
        out = (committed.stdout or "") + (committed.stderr or "")
        if "nothing to commit" in out or "no changes added" in out:
            if not fresh:
                return ("That evidence was already sent — nothing changed, so there was nothing new "
                        "to commit.")
        raise ShareError(f"Could not commit the file: {_clean(out)}")

    pushed = _git("push", "origin", f"HEAD:refs/heads/{branch}", timeout=120)
    if pushed.returncode == 0:
        return f"Sent. <code>{rel}</code> is on GitHub, on branch <b>{branch}</b>."

    # Someone else pushed first. Rebase onto them and try once more — never
    # force, which would discard whatever they pushed.
    rebased = _git("pull", "--rebase", "--autostash", "origin", branch, timeout=120)
    if rebased.returncode != 0:
        raise ShareError(
            "The file is committed here, but GitHub has changes this checkout does not, and they "
            "could not be merged automatically. Nothing was lost and nothing was overwritten. "
            f"Run <code>git pull --rebase</code> then <code>git push</code>.<br><br>"
            f"Git said: {_clean(rebased.stderr or rebased.stdout)}")

    pushed = _git("push", "origin", f"HEAD:refs/heads/{branch}", timeout=120)
    if pushed.returncode != 0:
        raise ShareError(
            "The file is committed here but the push was refused. Nothing was lost — running "
            f"<code>git push</code> yourself will send it.<br><br>"
            f"Git said: {_clean(pushed.stderr or pushed.stdout)}")
    return f"Sent. <code>{rel}</code> is on GitHub, on branch <b>{branch}</b>."
