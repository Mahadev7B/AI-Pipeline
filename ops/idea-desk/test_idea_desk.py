#!/usr/bin/env python3
"""ops/idea-desk/test_idea_desk.py — tests for the parts that must not regress.

Code Review's catch-up finding: 2,000 lines shipped with no tests, in a repo
that has eight `ops/db/test_*.py`, and the function most needing them was the
sanitiser. These cover the sanitiser, the approve gate the Founder designed,
and the model-output shapes that used to destroy a completed, paid-for run.

    python3 ops/idea-desk/test_idea_desk.py

Never touches the live database: every database test runs against a scratch
file, per ops/db/README.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OPSDB = REPO / "ops" / "db" / "opsdb.py"
sys.path.insert(0, str(HERE))
import pages  # noqa: E402
import evaluator  # noqa: E402


class Sanitiser(unittest.TestCase):
    """Agent output is rendered, so this is the highest-risk function here."""

    # Only these can appear as REAL tags in the output. Substring checks are the
    # wrong tool here: `&lt;img onerror=...&gt;` contains "onerror" but renders
    # as inert visible text, which is exactly what the sanitiser is for. What
    # matters is which unescaped tags survive, and what they carry.
    ALLOWED_TAGS = {"b", "i", "em", "strong", "br", "div", "span"}
    ALLOWED_ATTRS = {'class="sk"', 'class="two"', 'class="dec"',
                     'class="lab"', 'class="lab unk"', 'class="na"'}

    def assert_inert(self, payload: str) -> str:
        import re
        out = pages.safe_html(payload)
        for tag in re.findall(r"<[^>]*>", out):
            m = re.fullmatch(r"</?([a-zA-Z0-9]+)\s*([^>]*?)/?>", tag)
            self.assertIsNotNone(m, f"unparseable tag {tag!r} from {payload!r}")
            name, attrs = m.group(1).lower(), m.group(2).strip()
            self.assertIn(name, self.ALLOWED_TAGS,
                          f"tag <{name}> survived {payload!r} -> {out!r}")
            if attrs:
                self.assertIn(attrs, self.ALLOWED_ATTRS,
                              f"attribute {attrs!r} survived {payload!r} -> {out!r}")
        return out

    def test_scripts_and_handlers_do_not_survive(self):
        for payload in (
            "<script>alert(1)</script>",
            "<img src=x onerror=alert(1)>",
            '<a href="javascript:alert(1)">x</a>',
            "<svg/onload=alert(1)>",
            "<style>body{display:none}</style>",
            "<iframe src=//evil></iframe>",
            "&lt;script&gt;alert(1)&lt;/script&gt;",          # already-escaped input
            '<div class="sk" onmouseover="alert(1)">x</div>',  # handler on an allowed tag
            "<DIV CLASS=\"sk\">uppercase</DIV>",
        ):
            self.assert_inert(payload)

    def test_allowed_formatting_survives(self):
        self.assertIn("<b>", pages.safe_html("<b>bold</b>"))
        self.assertIn('<div class="sk">', pages.safe_html('<div class="sk">Heading</div>'))
        self.assertIn('<span class="lab unk">', pages.safe_html("<span class='lab unk'>UNKNOWN</span>"))

    def test_a_class_that_merely_starts_like_an_allowed_one_is_refused(self):
        self.assertNotIn("<span", pages.safe_html('<span class="lab unknown">x</span>'))
        self.assertNotIn("<div", pages.safe_html('<div class="sketchy">x</div>'))

    def test_every_open_tag_is_closed_and_every_stray_close_dropped(self):
        # An unclosed <b> is an active-formatting element: the parser
        # reconstructs it past the enclosing </div>, so it really does escape.
        self.assertEqual(pages.safe_html("<b>unclosed"), "<b>unclosed</b>")
        self.assertEqual(pages.safe_html("<strong/>"), "<strong></strong>")
        self.assertEqual(pages.safe_html("</div></div>oops"), "oops")
        self.assertEqual(pages.safe_html("</b>oops"), "oops")
        self.assertEqual(pages.safe_html("<b><i>x</b></i>"), "<b><i>x</i></b>")
        self.assertEqual(pages.safe_html('<div class="sk">a<b>b</div>c'),
                         '<div class="sk">a<b>b</b></div>c')

    def test_code_survives_and_is_still_balanced(self):
        # Failure messages name a command to run and a diagnostics file; those
        # used to reach the Founder with the literal tags showing.
        self.assertEqual(pages.safe_html("run <code>doctor.py</code> now"),
                         "run <code>doctor.py</code> now")
        self.assertEqual(pages.safe_html('<div class="sk">a<code>b</div>c'),
                         '<div class="sk">a<code>b</code></div>c')
        # An attribute form is not on the allowlist, so it stays escaped — and
        # its now-orphaned closer is dropped rather than leaking out of the card.
        self.assertEqual(pages.safe_html('<code onclick="x">a</code>'),
                         '&lt;code onclick=&quot;x&quot;&gt;a')

    def test_none_and_empty(self):
        self.assertEqual(pages.safe_html(None), "")
        self.assertEqual(pages.safe_html(""), "")


class RosterParsing(unittest.TestCase):
    """Shapes a model really produces. Two of these used to raise and discard a
    completed evaluation the Founder had already paid for."""

    def parse(self, data: dict) -> dict:
        saved = evaluator._invoke
        evaluator._invoke = lambda *a, **k: __import__("json").dumps(data)
        try:
            return evaluator._select_roster({"raw_idea": "x"}, [], None)[0]
        finally:
            evaluator._invoke = saved

    def test_explicit_nulls_do_not_crash(self):
        got = self.parse({"depth": "Light", "in": None, "out": None})
        self.assertEqual([r for r, _ in got["in"]], ["product"])

    def test_an_over_long_entry_does_not_crash(self):
        got = self.parse({"depth": "Light",
                          "in": [["cto", "why", "extra"]],
                          "out": [["ceo", "why", "extra"]]})
        self.assertIn("cto", [r for r, _ in got["in"]])
        self.assertEqual(len(got["out"][0]), 2)

    def test_product_is_always_on_the_roster(self):
        got = self.parse({"depth": "Full", "in": [["cto", "only cto"]], "out": []})
        self.assertIn("product", [r for r, _ in got["in"]])

    def test_invented_roles_are_dropped(self):
        got = self.parse({"depth": "Light", "in": [["developer", "x"], ["cfo", "y"]], "out": []})
        self.assertEqual([r for r, _ in got["in"]], ["product"])

    def test_a_nonsense_depth_falls_back_rather_than_propagating(self):
        self.assertEqual(self.parse({"depth": "Extremely Deep", "in": [], "out": []})["depth"],
                         "Standard")

    def test_the_roster_is_capped(self):
        got = self.parse({"depth": "Full", "out": [],
                          "in": [[r, "x"] for r in
                                 ("cto", "red-team", "ceo", "design", "financial", "security")]})
        self.assertLessEqual(len(got["in"]), evaluator.MAX_PERSPECTIVES)


class ApproveGate(unittest.TestCase):
    """The Founder's own rule: no approving against the company's advice, and
    no approving a reading the company has already withdrawn."""

    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "gate.sqlite3"
        self.env = {**os.environ, "OPSDB_PATH": str(self.db)}
        self.ops("init")
        self.ops("idea-create", "--raw", "a thing")

    def ops(self, *args):
        return subprocess.run([sys.executable, str(OPSDB), *args],
                              capture_output=True, text=True, env=self.env)

    def approve(self, round_id):
        return self.ops("idea-approve", "--idea-id", "1", "--round-id", str(round_id),
                        "--confirm-founder-decision")

    def test_a_recommendation_against_building_cannot_be_approved(self):
        self.ops("idea-round-add", "--idea-id", "1", "--recommendation", "Reconsider")
        r = self.approve(1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no approve-anyway path", (r.stdout + r.stderr))

    def test_a_superseded_proceed_cannot_be_approved(self):
        # The hole CTO found: round 1 says Proceed, the Founder corrects, round
        # 2 says Reconsider — and round 1 stayed approvable forever.
        self.ops("idea-round-add", "--idea-id", "1", "--recommendation", "Proceed")
        self.ops("idea-round-add", "--idea-id", "1", "--recommendation", "Reconsider")
        r = self.approve(1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("superseded", (r.stdout + r.stderr))

    def test_cannot_approve_while_the_company_is_still_reading(self):
        self.ops("idea-round-add", "--idea-id", "1", "--recommendation", "Proceed")
        self.ops("idea-evaluation-start", "--idea-id", "1")
        r = self.approve(1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("running right now", (r.stdout + r.stderr))

    def test_the_current_proceed_approves(self):
        self.ops("idea-round-add", "--idea-id", "1", "--recommendation",
                 "Proceed with narrowed scope")
        r = self.approve(1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("frozen", r.stdout)

    def test_approving_twice_is_refused(self):
        self.ops("idea-round-add", "--idea-id", "1", "--recommendation", "Proceed")
        self.approve(1)
        self.assertNotEqual(self.approve(1).returncode, 0)

    def test_the_founder_must_say_it_is_them(self):
        self.ops("idea-round-add", "--idea-id", "1", "--recommendation", "Proceed")
        r = self.ops("idea-approve", "--idea-id", "1", "--round-id", "1")
        self.assertNotEqual(r.returncode, 0)

    def test_the_original_words_are_never_rewritten(self):
        self.ops("idea-edit", "--idea-id", "1", "--raw", "completely different words")
        out = self.ops("query", "SELECT raw_idea FROM ideas WHERE id=1").stdout
        self.assertIn("a thing", out)
        self.assertNotIn("completely different", out)

    def test_a_correction_is_held_durably_from_the_moment_it_is_sent(self):
        self.ops("idea-evaluation-start", "--idea-id", "1", "--note", "you misread me")
        self.assertIn("you misread me",
                      self.ops("query", "SELECT pending_note FROM ideas WHERE id=1").stdout)


class SynthesisValidation(unittest.TestCase):
    """Nothing half-understood is ever stored as a round."""

    def test_a_missing_question_is_refused(self):
        answers = {str(n): ["a", "b"] for n in range(1, 11)}
        del answers["7"]
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._validate({"answers": answers, "view": {}})

    def test_an_invented_recommendation_is_refused(self):
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._validate({
                "answers": {str(n): ["a", "b"] for n in range(1, 11)},
                "view": {"opp": "High", "why": "w", "merit": "m", "threat": "t", "diff": "d",
                         "rec": "Ship it immediately"}})

    def test_prose_around_the_json_is_tolerated(self):
        self.assertEqual(evaluator._extract_json('Sure!\n```json\n{"a": 1}\n```\nHope that helps')["a"], 1)

    def test_unparseable_output_is_refused_rather_than_guessed_at(self):
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._extract_json("I could not answer that.")


class SynthesisRecovery(unittest.TestCase):
    """A formatting slip in the LAST model response used to discard a completed
    multi-agent evaluation. One bounded repair attempt now rescues it — without
    loosening what a stored round must contain."""

    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "recover.sqlite3"
        self.env = {**os.environ, "OPSDB_PATH": str(self.db)}
        self._ops("init")
        self._ops("idea-create", "--raw=a thing worth evaluating")
        self._saved_invoke = evaluator._invoke
        self._saved_opsdb = evaluator._opsdb
        self._saved_diag = evaluator._preserve_diagnostics
        self.calls: list[str] = []
        self.written: list[list[str]] = []
        self.preserved: list[dict] = []
        evaluator._opsdb = lambda *a: (self.written.append(list(a)) or "ok")
        evaluator._preserve_diagnostics = lambda i, blobs: (self.preserved.append(blobs)
                                                            or Path("/tmp/diag.txt"))

    def tearDown(self):
        evaluator._invoke = self._saved_invoke
        evaluator._opsdb = self._saved_opsdb
        evaluator._preserve_diagnostics = self._saved_diag

    def _ops(self, *args):
        return subprocess.run([sys.executable, str(OPSDB), *args],
                              capture_output=True, text=True, env=self.env)

    ROSTER = json.dumps({"depth": "Light", "depth_reason": "internal",
                         "in": [["cto", "records"]], "out": [["ceo", "no market"]]})

    @staticmethod
    def good(rec="Proceed"):
        return {"title": "A title",
                "answers": {str(n): [f"concise {n}", f"expanded {n}"] for n in range(1, 11)},
                "view": {"opp": "Medium", "why": "w", "merit": "m", "threat": "t", "diff": "d",
                         "rec": rec}}

    def drive(self, final_responses):
        """Run one whole evaluation. final_responses are the Chief of Staff's
        synthesis reply and then its repair reply, in order."""
        pending = list(final_responses)
        def fake(agent, transcript, idea_id=None):
            self.calls.append("repair" if "FORMAT REPAIR ONLY" in transcript
                              else ("roster" if "decide WHO should read it" in transcript
                                    else ("synthesis" if "answer these ten questions" in transcript
                                          else "perspective")))
            if self.calls[-1] == "roster":
                return self.ROSTER
            if self.calls[-1] == "perspective":
                return "my reading of it"
            return pending.pop(0)
        evaluator._invoke = fake
        evaluator.run_evaluation(1, {"raw_idea": "a thing worth evaluating",
                                     "current_raw": "a thing worth evaluating"}, [])

    def stored(self):
        return next((a for a in self.written if a and a[0] == "idea-round-add"), None)

    # --- the seven cases the Founder asked for -----------------------------
    def test_valid_json_first_try(self):
        self.drive([json.dumps(self.good())])
        self.assertIsNotNone(self.stored(), "a clean answer must be stored")
        self.assertNotIn("--repaired", self.stored())
        self.assertNotIn("repair", self.calls)

    def test_json_inside_a_markdown_fence(self):
        self.drive(["Here you go:\n```json\n" + json.dumps(self.good()) + "\n```"])
        self.assertIsNotNone(self.stored())
        self.assertNotIn("repair", self.calls, "a fence is not a failure and must not cost a call")

    def test_prose_before_and_after_valid_json(self):
        self.drive(["Sure. " + json.dumps(self.good()) + " Hope that helps!"])
        self.assertIsNotNone(self.stored())
        self.assertNotIn("repair", self.calls)

    def test_malformed_json_is_repaired_and_the_evaluation_survives(self):
        broken = json.dumps(self.good())[:-3] + ",,,"          # trailing garbage, unparseable
        self.drive([broken, json.dumps(self.good())])
        stored = self.stored()
        self.assertIsNotNone(stored, "the repaired evaluation must be saved, not discarded")
        self.assertIn("--repaired", stored, "the repair must be recorded")
        self.assertEqual(self.calls.count("repair"), 1)

    def test_when_repair_also_fails_nothing_is_saved_and_the_evidence_is_kept(self):
        self.drive(["not json at all", "still not json"])
        self.assertIsNone(self.stored(), "a half-understood brief must never be stored")
        self.assertEqual(self.calls.count("repair"), 1)
        self.assertTrue(self.preserved, "the raw answers must be preserved for diagnosis")
        blobs = self.preserved[-1]
        self.assertIn("the Chief of Staff's final answer", blobs)
        self.assertIn("not json at all", blobs["the Chief of Staff's final answer"])
        self.assertIn("the stage that failed", blobs, "the file must name the stage")
        self.assertTrue(any("said" in k for k in blobs), "each role's reading is kept too")
        ended = [a for a in self.written if a and a[0] == "idea-evaluation-end"]
        self.assertTrue(any("--error" in a for a in ended), "the Founder must be told")

    def test_valid_json_missing_a_required_answer_is_refused_and_not_repaired(self):
        missing = self.good()
        del missing["answers"]["7"]
        self.drive([json.dumps(missing)])
        self.assertIsNone(self.stored())
        # Repairing this could only mean inventing answer 7. The company does
        # not invent, so this stays a hard failure.
        self.assertNotIn("repair", self.calls,
                         "a genuinely missing answer must not be 'repaired' into existence")
        self.assertTrue(self.preserved, "the evidence is still kept")

    def test_repair_never_loops(self):
        self.drive(["{bad", "{still bad"])
        self.assertEqual(self.calls.count("repair"), 1, "exactly one repair attempt, ever")
        self.assertEqual(self.calls.count("synthesis"), 1, "and the idea is not re-read")

    def test_an_invented_recommendation_survives_neither_path(self):
        bad = self.good(rec="Ship it now")
        self.drive([json.dumps(bad)])
        self.assertIsNone(self.stored())


class SharingEvidence(unittest.TestCase):
    """Sending a failed evaluation's evidence to GitHub. It publishes the
    Founder's own words permanently, so the rules that matter are: only when
    they ask, only the one file, never a force-push, and never a button that
    leads nowhere."""

    def setUp(self):
        import incidents
        self.inc = incidents
        self.tmp = Path(tempfile.mkdtemp())
        self._saved = (incidents.DIAGNOSTICS, incidents.INCIDENTS, incidents.REPO, incidents._git)
        incidents.REPO = self.tmp
        incidents.DIAGNOSTICS = self.tmp / "diagnostics"
        incidents.INCIDENTS = self.tmp / "incidents"
        incidents.DIAGNOSTICS.mkdir()
        self.ran: list[tuple] = []

    def tearDown(self):
        (self.inc.DIAGNOSTICS, self.inc.INCIDENTS,
         self.inc.REPO, self.inc._git) = self._saved

    def write_diag(self, idea_id=9, stamp="20260902T195129Z", body="the evidence"):
        p = self.inc.DIAGNOSTICS / f"idea-{idea_id}-{stamp}.txt"
        p.write_text(body, encoding="utf-8")
        return p

    def fake_git(self, **codes):
        """Record every git call; return the given code per subcommand."""
        def run(*args, timeout=60):
            self.ran.append(args)
            class R:
                returncode = codes.get(args[0], 0)
                stdout = {"symbolic-ref": "claude/orchestrator-chief-of-staff-f35grl"}.get(args[0], "")
                stderr = ""
            return R()
        self.inc._git = run

    # --- picking the right file -------------------------------------------
    def test_no_diagnostic_means_no_button_and_no_send(self):
        self.assertIsNone(self.inc.latest_for(9))
        self.fake_git()
        with self.assertRaises(self.inc.ShareError):
            self.inc.share(9)
        self.assertEqual(self.ran, [], "nothing should touch git when there is nothing to send")

    def test_the_newest_diagnostic_for_that_idea_is_chosen(self):
        self.write_diag(9, "20260902T100000Z", "old")
        newest = self.write_diag(9, "20260902T195129Z", "new")
        self.write_diag(11, "20260902T230000Z", "another idea")
        self.assertEqual(self.inc.latest_for(9), newest)

    def test_one_idea_does_not_see_anothers_evidence(self):
        self.write_diag(11)
        self.assertIsNone(self.inc.latest_for(9))

    # --- what it does to git ----------------------------------------------
    def test_a_successful_send_commits_only_that_one_file(self):
        self.write_diag()
        self.fake_git()
        msg = self.inc.share(9)
        self.assertIn("Sent", msg)
        commit = next(a for a in self.ran if a[0] == "commit")
        self.assertIn("--", commit, "the commit must be limited to a pathspec")
        path = commit[commit.index("--") + 1]
        self.assertTrue(path.endswith("idea-9-20260902T195129Z.txt"))
        self.assertNotIn("-a", commit, "never commit everything in the working tree")

    def test_it_never_force_pushes(self):
        self.write_diag()
        self.fake_git(push=1, pull=0)
        # Both pushes are refused, so this ends in a ShareError. What matters is
        # what it did NOT reach for on the way there.
        with self.assertRaises(self.inc.ShareError):
            self.inc.share(9)
        for call in self.ran:
            self.assertNotIn("--force", call)
            self.assertNotIn("-f", call)
            self.assertNotIn("--force-with-lease", call)

    def test_a_rejected_push_is_rebased_once_and_retried(self):
        self.write_diag()
        pushes = []
        def run(*args, timeout=60):
            self.ran.append(args)
            class R:
                stdout = "claude/orchestrator-chief-of-staff-f35grl" if args[0] == "symbolic-ref" else ""
                stderr = ""
                returncode = 0
            if args[0] == "push":
                pushes.append(args)
                R.returncode = 1 if len(pushes) == 1 else 0
            return R()
        self.inc._git = run
        self.assertIn("Sent", self.inc.share(9))
        self.assertEqual(len(pushes), 2, "one retry, not a loop")
        self.assertTrue(any(a[0] == "pull" and "--rebase" in a for a in self.ran))

    def test_a_failed_push_says_nothing_was_lost(self):
        self.write_diag()
        self.fake_git(push=1, pull=1)
        with self.assertRaises(self.inc.ShareError) as caught:
            self.inc.share(9)
        self.assertIn("Nothing was lost", str(caught.exception))

    def test_the_founders_note_is_appended_to_what_is_sent(self):
        self.write_diag(body="the evidence")
        self.fake_git()
        self.inc.share(9, "it hung for a minute first")
        sent = (self.inc.INCIDENTS / "idea-9-20260902T195129Z.txt").read_text()
        self.assertIn("the evidence", sent)
        self.assertIn("it hung for a minute first", sent)

    def test_resending_never_erases_a_note_added_the_first_time(self):
        # Copying over an existing incident destroyed the Founder's earlier
        # note — the feature meant to preserve evidence deleting some of it.
        self.write_diag(body="the evidence")
        self.fake_git()
        self.inc.share(9, "it hung first")
        self.inc.share(9, "and the fan spun up")
        sent = (self.inc.INCIDENTS / "idea-9-20260902T195129Z.txt").read_text()
        self.assertIn("it hung first", sent, "the first note must survive a resend")
        self.assertIn("and the fan spun up", sent)
        self.assertEqual(sent.count("the evidence"), 1, "the body is not duplicated")

    def test_resending_with_nothing_new_says_so_instead_of_committing_again(self):
        self.write_diag()
        self.fake_git()
        self.inc.share(9)
        def run(*args, timeout=60):
            self.ran.append(args)
            class R:
                returncode = 1 if args[0] == "commit" else 0
                # The wording git actually used on the Founder's machine.
                stdout = ("nothing added to commit but untracked files present"
                          if args[0] == "commit"
                          else "claude/orchestrator-chief-of-staff-f35grl")
                stderr = ""
            return R()
        self.inc._git = run
        self.assertIn("already sent", self.inc.share(9))

    def test_a_branch_with_no_commits_is_not_mistaken_for_a_detached_head(self):
        # rev-parse cannot resolve HEAD on an unborn branch and reports nothing,
        # which read as "detached" and sent the Founder to fix a non-problem.
        self.write_diag()
        self.fake_git()
        self.inc.share(9)
        self.assertTrue(any(a[0] == "symbolic-ref" for a in self.ran),
                        "the branch must be read with symbolic-ref")
        self.assertFalse(any(a[0] == "rev-parse" for a in self.ran))

    def test_git_setup_failures_are_explained_not_pasted(self):
        # Handing someone raw git output is not an error message, it is a
        # handoff of the problem. The Founder hit exactly this one.
        identity = ("Author identity unknown\n*** Please tell me who you are.\n"
                    "fatal: unable to auto-detect email address (got 'x@y.(none)')")
        told = self.inc._explain(identity)
        self.assertIsNotNone(told)
        self.assertIn("git config --global user.name", told)
        self.assertIn("Nothing was lost", told)
        self.assertIsNotNone(self.inc._explain("fatal: Authentication failed for 'https://...'"))
        self.assertIsNotNone(self.inc._explain("could not read Username for 'https://github.com'"))
        self.assertIsNone(self.inc._explain("some failure nobody anticipated"),
                          "an unrecognised failure must fall through, not be mislabelled")

    def test_an_unsigned_commit_says_what_to_do(self):
        self.write_diag()
        def run(*args, timeout=60):
            class R:
                returncode = 1 if args[0] == "commit" else 0
                stdout = "claude/orchestrator-chief-of-staff-f35grl" if args[0] == "symbolic-ref" else ""
                stderr = "Author identity unknown" if args[0] == "commit" else ""
            return R()
        self.inc._git = run
        with self.assertRaises(self.inc.ShareError) as caught:
            self.inc.share(9)
        self.assertIn("git config --global", str(caught.exception))

    def test_a_signin_failure_is_not_treated_as_a_diverged_branch(self):
        # Rebasing would not help, and would rewrite history for nothing.
        self.write_diag()
        pulls = []
        def run(*args, timeout=60):
            if args[0] == "pull":
                pulls.append(args)
            class R:
                returncode = 1 if args[0] == "push" else 0
                stdout = "claude/orchestrator-chief-of-staff-f35grl" if args[0] == "symbolic-ref" else ""
                stderr = "fatal: Authentication failed" if args[0] == "push" else ""
            return R()
        self.inc._git = run
        with self.assertRaises(self.inc.ShareError) as caught:
            self.inc.share(9)
        self.assertEqual(pulls, [], "a sign-in problem must not trigger a rebase")
        self.assertIn("not signed in", str(caught.exception))

    def test_a_detached_head_refuses_rather_than_pushing_somewhere_odd(self):
        self.write_diag()
        def run(*args, timeout=60):
            class R:
                returncode = 0
                stdout = "HEAD" if args[0] == "symbolic-ref" else ""
                stderr = ""
            return R()
        self.inc._git = run
        with self.assertRaises(self.inc.ShareError):
            self.inc.share(9)

    def test_credentials_in_git_output_are_never_echoed_back(self):
        leak = "fatal: https://user:ghp_secrettoken@github.com/x/y.git rejected"
        self.assertNotIn("ghp_secrettoken", self.inc._clean(leak))
        self.assertIn("https://github.com", self.inc._clean(leak))

    def test_already_shared_is_detectable(self):
        d = self.write_diag()
        self.assertIsNone(self.inc.already_shared(d))
        self.inc.INCIDENTS.mkdir(parents=True)
        (self.inc.INCIDENTS / d.name).write_text("x")
        self.assertIsNotNone(self.inc.already_shared(d))

    # --- the button ---------------------------------------------------------
    def test_no_button_without_evidence(self):
        self.assertEqual(pages._share_link({"id": 9, "has_diagnostic": False}), "")
        self.assertEqual(pages._share_link({"id": 9}), "")
        self.assertIn("/share/9", pages._share_link({"id": 9, "has_diagnostic": True}))


class AnswerShape(unittest.TestCase):
    """A COMPLETE evaluation arriving in a different container was rejected as
    if it were missing, discarding a paid-for multi-agent run. Shape is
    normalised; completeness is not. Every one of the ten must still be there."""

    @staticmethod
    def ten(): return {str(n): [f"c{n}", f"x{n}"] for n in range(1, 11)}
    VIEW = {"opp": "Medium", "why": "w", "merit": "m", "threat": "t", "diff": "d", "rec": "Proceed"}

    def ok(self, result):
        answers, view, _title = evaluator._validate(result)
        self.assertEqual(len(answers), 10)
        self.assertEqual(view["rec"], "Proceed")
        return answers

    def test_the_plain_shape_still_works(self):
        self.ok({"answers": self.ten(), "view": self.VIEW})

    def test_ten_answers_in_a_list(self):
        got = self.ok({"answers": [[f"c{n}", f"x{n}"] for n in range(1, 11)], "view": self.VIEW})
        self.assertEqual(got["1"][0], "c1")
        self.assertEqual(got["10"][0], "c10")

    def test_question_prefixed_keys(self):
        got = self.ok({"answers": {f"Q{n}": [f"c{n}", ""] for n in range(1, 11)},
                       "view": self.VIEW})
        self.assertEqual(got["7"][0], "c7")
        self.ok({"answers": {f"question {n}": [f"c{n}", ""] for n in range(1, 11)},
                 "view": self.VIEW})
        self.ok({"answers": {f"{n}.": [f"c{n}", ""] for n in range(1, 11)}, "view": self.VIEW})

    def test_a_payload_wrapped_one_level_down(self):
        self.ok({"evaluation": {"answers": self.ten(), "view": self.VIEW}})

    # --- what normalisation must NOT rescue --------------------------------
    def test_nine_answers_in_a_list_is_still_a_failure(self):
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._validate({"answers": [[f"c{n}", ""] for n in range(1, 10)],
                                 "view": self.VIEW})

    def test_a_missing_numbered_answer_is_still_a_failure(self):
        short = self.ten()
        del short["4"]
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._validate({"answers": short, "view": self.VIEW})

    def test_two_candidate_wrappers_are_not_guessed_between(self):
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._validate({"a": {"answers": self.ten(), "view": self.VIEW},
                                 "b": {"answers": self.ten(), "view": self.VIEW}})

    def test_an_invented_recommendation_is_not_rescued_by_a_wrapper(self):
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._validate({"evaluation": {"answers": self.ten(),
                                                "view": {**self.VIEW, "rec": "Ship it"}}})


class RosterRecovery(unittest.TestCase):
    """Roster selection needs machine-readable JSON exactly as much as the
    final answer does, and used to have neither a repair attempt nor any
    preservation of what came back. A malformed roster therefore discarded the
    raw response, wrote no diagnostics file at all, and surfaced the same
    sentence a synthesis failure would — which is how several real, paid
    evaluations were spent looking at the wrong stage."""

    GOOD_ROSTER = json.dumps({"depth": "Light", "depth_reason": "internal",
                              "in": [["cto", "records"]], "out": [["ceo", "no market"]]})

    def setUp(self):
        self._saved_invoke = evaluator._invoke
        self._saved_opsdb = evaluator._opsdb
        self._saved_diag = evaluator._preserve_diagnostics
        self.calls: list[str] = []
        self.written: list[list[str]] = []
        self.preserved: list[dict] = []
        evaluator._opsdb = lambda *a: (self.written.append(list(a)) or "ok")
        evaluator._preserve_diagnostics = lambda i, blobs: (self.preserved.append(blobs)
                                                            or Path("/tmp/diag.txt"))

    def tearDown(self):
        evaluator._invoke = self._saved_invoke
        evaluator._opsdb = self._saved_opsdb
        evaluator._preserve_diagnostics = self._saved_diag

    @staticmethod
    def _good_final():
        return json.dumps({"title": "A title",
                           "answers": {str(n): [f"concise {n}", f"expanded {n}"]
                                       for n in range(1, 11)},
                           "view": {"opp": "Medium", "why": "w", "merit": "m", "threat": "t",
                                    "diff": "d", "rec": "Proceed"}})

    def drive(self, roster_responses):
        """roster_responses: the Chief of Staff's roster reply, then its repair
        reply, in order. Everything downstream answers cleanly, so any failure
        is unambiguously the roster stage."""
        pending = list(roster_responses)
        def fake(agent, transcript, idea_id=None):
            if "FORMAT REPAIR ONLY" in transcript:
                kind = "repair"
            elif "decide WHO should read it" in transcript:
                kind = "roster"
            elif "answer these ten questions" in transcript:
                kind = "synthesis"
            else:
                kind = "perspective"
            self.calls.append(kind)
            if kind in ("roster", "repair") and pending:
                return pending.pop(0)
            if kind == "perspective":
                return "my reading of it"
            return self._good_final()
        evaluator._invoke = fake
        evaluator.run_evaluation(1, {"raw_idea": "a thing", "current_raw": "a thing"}, [])

    def stored(self):
        return next((a for a in self.written if a and a[0] == "idea-round-add"), None)

    def error(self) -> str:
        for a in self.written:
            if a and a[0] == "idea-evaluation-end" and "--error" in a:
                return a[a.index("--error") + 1]
        return ""

    def test_a_clean_roster_costs_no_repair_call(self):
        self.drive([self.GOOD_ROSTER])
        self.assertIsNotNone(self.stored())
        self.assertNotIn("repair", self.calls)

    def test_malformed_roster_json_is_repaired_and_the_evaluation_survives(self):
        self.drive([self.GOOD_ROSTER[:-3] + ",,,", self.GOOD_ROSTER])
        self.assertIsNotNone(self.stored(), "a reformatted roster must not lose the evaluation")
        self.assertEqual(self.calls.count("repair"), 1)
        self.assertEqual(self.calls.count("roster"), 1, "the idea is not re-read to choose again")

    def test_a_failed_roster_repair_keeps_the_evidence_and_names_the_stage(self):
        self.drive(["not json at all", "still not json"])
        self.assertIsNone(self.stored())
        self.assertTrue(self.preserved, "a roster failure must write diagnostics too")
        blobs = self.preserved[-1]
        self.assertIn("not json at all",
                      blobs["who should read it — the Chief of Staff's answer"])
        self.assertIn("still not json", blobs["who should read it — the reformatting attempt"])
        self.assertEqual(blobs["the stage that failed"], evaluator.ROSTER_STAGE)
        self.assertIn(evaluator.ROSTER_STAGE, self.error(),
                      "the Founder must be told WHICH stage failed")

    def test_roster_repair_never_loops(self):
        self.drive(["{bad", "{still bad"])
        self.assertEqual(self.calls.count("repair"), 1, "exactly one repair attempt, ever")

    def test_the_roster_repair_asks_for_the_roster_shape_not_the_synthesis_one(self):
        seen: list[str] = []
        def fake(agent, transcript, idea_id=None):
            if "FORMAT REPAIR ONLY" in transcript:
                seen.append(transcript)
                return self.GOOD_ROSTER
            if "decide WHO should read it" in transcript:
                return "not json"
            return "my reading of it" if "answer these ten questions" not in transcript \
                else self._good_final()
        evaluator._invoke = fake
        evaluator.run_evaluation(1, {"raw_idea": "a thing", "current_raw": "a thing"}, [])
        self.assertTrue(seen)
        self.assertIn('"depth"', seen[0], "the repair must ask for the ROSTER shape")
        self.assertNotIn("answers", seen[0], "and never for the synthesis shape")

    def test_an_empty_answer_is_not_sent_for_repair(self):
        # Nothing can be reformatted out of nothing. Asking would spend a real
        # call for a certain failure, and the old message blamed the shape of
        # an answer that was never given.
        self.drive(["   "])
        self.assertIsNone(self.stored())
        self.assertNotIn("repair", self.calls)
        self.assertIn("nothing at all", self.error())

    def test_a_perspective_failure_still_preserves_what_was_already_said(self):
        def fake(agent, transcript, idea_id=None):
            if "decide WHO should read it" in transcript:
                return self.GOOD_ROSTER
            raise evaluator.EvaluationError("the agent gave up")
        evaluator._invoke = fake
        evaluator.run_evaluation(1, {"raw_idea": "a thing", "current_raw": "a thing"}, [])
        self.assertIsNone(self.stored())
        self.assertTrue(self.preserved, "the roster reply is evidence even when a role fails")
        self.assertIn("reading the idea", self.error(), "the failing role must be named")


if __name__ == "__main__":
    unittest.main(verbosity=2)
