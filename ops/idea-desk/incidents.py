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

import os
import re
import subprocess
import tempfile
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


# The branch incidents are pushed to. Deliberately NOT the branch the Founder
# works on: a commit there diverges their history from the build side's, and the
# next `git pull` then demands a merge, opens an editor, and asks the person
# using the app to write a commit message. That is developer work, and it was
# being handed to the Founder as the price of pressing one button.
INCIDENT_BRANCH = "idea-desk-incidents"

# Used only when this machine's git has no identity of its own. Supplying it
# here means a send can never fail with "Author identity unknown" — the failure
# that stranded a staged file and blocked pulls for days.
_FALLBACK_WHO = {"GIT_AUTHOR_NAME": "Idea Desk", "GIT_AUTHOR_EMAIL": "idea-desk@localhost",
                 "GIT_COMMITTER_NAME": "Idea Desk", "GIT_COMMITTER_EMAIL": "idea-desk@localhost"}


def _git(*args: str, timeout: int = 60, env: dict | None = None,
         stdin: str | None = None) -> subprocess.CompletedProcess:
    full = None
    if env:
        full = {**os.environ, **env}
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          timeout=timeout, env=full, input=stdin)


def _clean(text: str) -> str:
    return _CREDS.sub(r"\1", (text or "").strip())[:600]


def _explain(out: str) -> str | None:
    """Turn git's own words into something the Founder can act on.

    Pasting raw git output at someone is not an error message, it is a
    handoff of the problem. These are the failures that are about the
    machine's setup rather than about this repository, and each has one fix."""
    low = (out or "").lower()
    if "author identity unknown" in low or "unable to auto-detect email" in low:
        return ("Git on this machine does not know who you are yet, so it will not sign a commit. "
                "This is a one-time setup and has nothing to do with your idea. In a terminal:"
                "<br><br><code>git config --global user.name \"Your Name\"</code><br>"
                "<code>git config --global user.email \"you@example.com\"</code>"
                "<br><br>Then press Send again. Nothing was lost &mdash; the file is already "
                "prepared and will go straight through.")
    if "could not read username" in low or "authentication failed" in low or "403" in low:
        return ("GitHub refused the push because this machine is not signed in to it. Your idea "
                "and the evidence are safe here; only the send failed."
                "<br><br>Sign in once with <code>gh auth login</code>, or set up a credential "
                "helper, then press Send again.")
    if "permission denied" in low and "publickey" in low:
        return ("GitHub refused this machine's SSH key. Nothing was lost. Fix the key, or switch "
                "the remote to HTTPS, then press Send again.")
    return None


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
    """Whether this diagnostic has been sent. Recorded as a marker file NEXT TO
    the diagnostic, inside the gitignored folder — not by leaving a copy in the
    repository, because the whole point is that a send changes nothing in the
    Founder's working tree."""
    marker = path.with_suffix(path.suffix + ".sent")
    return marker if marker.exists() else None


def share(idea_id: int, note: str = "") -> str:
    """Put the evidence on GitHub WITHOUT touching the Founder's branch.

    This uses git's plumbing deliberately. A normal add-commit-push would:
      * stage a file — and a staged file that fails to commit blocks every
        later `git pull` (it did, for days);
      * put a commit on the Founder's branch — which diverges their history
        from the build side's, so the next pull demands a merge and an editor.

    Instead the file is turned straight into a blob, a tree is built in a
    TEMPORARY index, a commit is made with commit-tree, and that commit is
    pushed to its own branch. HEAD does not move. The index is untouched. The
    working tree is untouched. `git pull` stays a fast-forward, forever.
    """
    src = latest_for(idea_id)
    if src is None:
        raise ShareError("There is no saved evidence for this idea to send. A diagnostic file is "
                         "only written when an evaluation actually fails.")
    if _git("remote", "get-url", "origin").returncode != 0:
        raise ShareError("This checkout has no <b>origin</b> remote, so there is no GitHub to send "
                         "it to.")

    content = src.read_text(encoding="utf-8", errors="replace")
    if note.strip():
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        content += f"\n\n----- what the Founder added, {stamp} -----\n{note.strip()}\n"

    blob = _git("hash-object", "-w", "--stdin", stdin=content)
    if blob.returncode != 0:
        raise ShareError(_explain(blob.stderr) or f"Could not store the file: {_clean(blob.stderr)}")
    blob_sha = blob.stdout.strip()

    # Build on whatever is already on the incident branch, so incidents
    # accumulate rather than replacing each other.
    _git("fetch", "origin", INCIDENT_BRANCH, timeout=120)
    parent = _git("rev-parse", "--verify", "--quiet", "FETCH_HEAD").stdout.strip()

    with tempfile.TemporaryDirectory() as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        if parent:
            read = _git("read-tree", parent, env=env)
            if read.returncode != 0:
                raise ShareError(f"Could not read the incident branch: {_clean(read.stderr)}")
        upd = _git("update-index", "--add", "--cacheinfo",
                   f"100644,{blob_sha},ops/incidents/{src.name}", env=env)
        if upd.returncode != 0:
            raise ShareError(f"Could not prepare the file: {_clean(upd.stderr)}")
        tree = _git("write-tree", env=env)
        if tree.returncode != 0:
            raise ShareError(f"Could not prepare the file: {_clean(tree.stderr)}")
        tree_sha = tree.stdout.strip()

    args = ["commit-tree", tree_sha, "-m", f"Idea Desk incident: {src.name}"]
    if parent:
        args += ["-p", parent]
    made = _git(*args, env=_FALLBACK_WHO)
    if made.returncode != 0:
        raise ShareError(_explain(made.stderr) or f"Could not record it: {_clean(made.stderr)}")
    commit_sha = made.stdout.strip()

    pushed = _git("push", "origin", f"{commit_sha}:refs/heads/{INCIDENT_BRANCH}", timeout=120)
    if pushed.returncode != 0:
        out = (pushed.stderr or "") + (pushed.stdout or "")
        raise ShareError(_explain(out) or (
            "GitHub refused the push. <b>Nothing on your machine changed</b> &mdash; your branch, "
            "your files and your history are exactly as they were.<br><br>"
            f"Git said: {_clean(out)}"))

    (src.with_suffix(src.suffix + ".sent")).write_text(commit_sha, encoding="utf-8")
    return (f"Sent. <code>ops/incidents/{src.name}</code> is on GitHub, on branch "
            f"<b>{INCIDENT_BRANCH}</b>.<br><br>Your own branch was not touched &mdash; nothing to "
            "merge, nothing to commit, and <code>git pull</code> still just works.")
