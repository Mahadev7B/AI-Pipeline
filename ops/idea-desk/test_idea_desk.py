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
# AFTER evaluator: importing it is what puts ops/control-center on the path.
import agent_runtime  # noqa: E402


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
        def fake(agent, transcript, idea_id=None, **kw):
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
    """Sending evidence to GitHub must leave the Founder's repository exactly as
    it found it. Two real failures taught this: a staged file that never
    committed blocked every later `git pull` for days, and commits landing on
    the Founder's own branch made each pull demand a merge and an editor."""

    def setUp(self):
        import incidents
        self.inc = incidents
        self.tmp = Path(tempfile.mkdtemp())
        self._saved = (incidents.DIAGNOSTICS, incidents.REPO, incidents._git)
        incidents.REPO = self.tmp
        incidents.DIAGNOSTICS = self.tmp / "diagnostics"
        incidents.DIAGNOSTICS.mkdir()
        self.ran: list[tuple] = []

    def tearDown(self):
        self.inc.DIAGNOSTICS, self.inc.REPO, self.inc._git = self._saved

    def write_diag(self, idea_id=9, stamp="20260902T195129Z", body="the evidence"):
        p = self.inc.DIAGNOSTICS / f"idea-{idea_id}-{stamp}.txt"
        p.write_text(body, encoding="utf-8")
        return p

    def fake_git(self, **codes):
        """Record every git call. Returns plausible plumbing output."""
        def run(*args, timeout=60, env=None, stdin=None, **kw):
            self.ran.append(args)
            out = {"hash-object": "b" * 40, "write-tree": "t" * 40,
                   "commit-tree": "c" * 40, "rev-parse": "p" * 40}.get(args[0], "")
            class R:
                returncode = codes.get(args[0], 0)
                stdout = out
                stderr = ""
            return R()
        self.inc._git = run

    def called(self, name):
        return [a for a in self.ran if a and a[0] == name]

    # --- the guarantee that matters ---------------------------------------
    def test_it_never_touches_the_founders_branch_or_index(self):
        self.write_diag()
        self.fake_git()
        self.inc.share(9)
        for forbidden in ("add", "commit", "checkout", "merge", "reset", "restore", "stash"):
            self.assertFalse(self.called(forbidden),
                             f"git {forbidden} would change the Founder's repository")

    def test_the_commit_goes_to_its_own_branch(self):
        self.write_diag()
        self.fake_git()
        self.inc.share(9)
        push = self.called("push")[0]
        self.assertIn(f"refs/heads/{self.inc.INCIDENT_BRANCH}", push[-1])
        self.assertNotIn("orchestrator", push[-1], "never the Founder's working branch")

    def test_it_never_force_pushes(self):
        self.write_diag()
        self.fake_git()
        self.inc.share(9)
        for call in self.ran:
            for flag in ("--force", "-f", "--force-with-lease"):
                self.assertNotIn(flag, call)

    def test_it_works_with_no_git_identity_configured(self):
        # "Author identity unknown" was the first real failure. commit-tree is
        # given an identity explicitly so it cannot happen again.
        self.write_diag()
        seen = {}
        def run(*args, timeout=60, env=None, stdin=None, **kw):
            self.ran.append(args)
            if args[0] == "commit-tree":
                seen.update(env or {})
            class R:
                returncode = 0
                stdout = {"hash-object": "b" * 40, "write-tree": "t" * 40,
                          "commit-tree": "c" * 40, "rev-parse": "p" * 40}.get(args[0], "")
                stderr = ""
            return R()
        self.inc._git = run
        self.inc.share(9)
        self.assertIn("GIT_AUTHOR_NAME", seen)
        self.assertIn("GIT_COMMITTER_EMAIL", seen)

    def test_the_tree_is_built_in_a_temporary_index(self):
        self.write_diag()
        seen = {}
        def run(*args, timeout=60, env=None, stdin=None, **kw):
            self.ran.append(args)
            if args[0] in ("update-index", "write-tree", "read-tree"):
                seen[args[0]] = (env or {}).get("GIT_INDEX_FILE")
            class R:
                returncode = 0
                stdout = {"hash-object": "b" * 40, "write-tree": "t" * 40,
                          "commit-tree": "c" * 40, "rev-parse": ""}.get(args[0], "")
                stderr = ""
            return R()
        self.inc._git = run
        self.inc.share(9)
        self.assertTrue(seen.get("write-tree"), "write-tree must use a temporary index")
        self.assertTrue(seen.get("update-index"))
        self.assertNotIn(str(self.tmp / ".git" / "index"), str(seen["write-tree"]))

    # --- picking the right file -------------------------------------------
    def test_no_diagnostic_means_no_send(self):
        self.fake_git()
        with self.assertRaises(self.inc.ShareError):
            self.inc.share(9)
        self.assertEqual(self.ran, [])

    def test_the_newest_diagnostic_for_that_idea_is_chosen(self):
        self.write_diag(9, "20260902T100000Z", "old")
        newest = self.write_diag(9, "20260902T195129Z", "new")
        self.write_diag(11, "20260902T230000Z", "another idea")
        self.assertEqual(self.inc.latest_for(9), newest)

    def test_one_idea_does_not_see_anothers_evidence(self):
        self.write_diag(11)
        self.assertIsNone(self.inc.latest_for(9))

    # --- content ------------------------------------------------------------
    def test_the_founders_note_is_included_in_what_is_sent(self):
        self.write_diag(body="the evidence")
        sent = {}
        def run(*args, timeout=60, env=None, stdin=None, **kw):
            self.ran.append(args)
            if args[0] == "hash-object":
                sent["blob"] = stdin
            class R:
                returncode = 0
                stdout = {"hash-object": "b" * 40, "write-tree": "t" * 40,
                          "commit-tree": "c" * 40, "rev-parse": ""}.get(args[0], "")
                stderr = ""
            return R()
        self.inc._git = run
        self.inc.share(9, "it hung for a minute first")
        self.assertIn("the evidence", sent["blob"])
        self.assertIn("it hung for a minute first", sent["blob"])

    def test_a_sent_diagnostic_is_marked_outside_the_repository(self):
        d = self.write_diag()
        self.assertIsNone(self.inc.already_shared(d))
        self.fake_git()
        self.inc.share(9)
        marker = self.inc.already_shared(d)
        self.assertIsNotNone(marker)
        # The marker lives beside the diagnostic, in the gitignored folder —
        # never as a file in the repository the Founder works in.
        self.assertEqual(marker.parent, self.inc.DIAGNOSTICS)

    # --- failure ------------------------------------------------------------
    def test_a_refused_push_says_nothing_on_your_machine_changed(self):
        self.write_diag()
        self.fake_git(push=1)
        with self.assertRaises(self.inc.ShareError) as caught:
            self.inc.share(9)
        self.assertIn("Nothing on your machine changed", str(caught.exception))

    def test_git_setup_failures_are_explained_not_pasted(self):
        identity = "Author identity unknown\n*** Please tell me who you are."
        told = self.inc._explain(identity)
        self.assertIsNotNone(told)
        self.assertIn("git config --global user.name", told)
        self.assertIsNotNone(self.inc._explain("fatal: Authentication failed for 'https://...'"))
        self.assertIsNone(self.inc._explain("some failure nobody anticipated"),
                          "an unrecognised failure must fall through, not be mislabelled")

    def test_credentials_in_git_output_are_never_echoed_back(self):
        leak = "fatal: https://user:ghp_secrettoken@github.com/x/y.git rejected"
        self.assertNotIn("ghp_secrettoken", self.inc._clean(leak))
        self.assertIn("https://github.com", self.inc._clean(leak))

    def test_no_origin_refuses_before_doing_anything(self):
        self.write_diag()
        self.fake_git(remote=1)
        with self.assertRaises(self.inc.ShareError):
            self.inc.share(9)
        self.assertFalse(self.called("push"))

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


class TimeoutOnWindows(unittest.TestCase):
    """The timeout handler itself crashed on Windows. os.killpg does not exist
    there, so a plain "the agent took too long" became an AttributeError and a
    traceback in the Founder's face — the error path failing louder than the
    error it was reporting."""

    def test_the_kill_path_does_not_assume_posix(self):
        import agent_runtime, os as _os
        killed = []

        class FakeProc:
            pid = 4321
            args = ["claude.CMD"]
            def kill(self): killed.append(True)

        real = getattr(_os, "killpg", None)
        try:
            if hasattr(_os, "killpg"):
                del _os.killpg                      # pretend to be Windows
            self.assertTrue(agent_runtime._kill_process_group(FakeProc()))
            self.assertEqual(killed, [True], "it must fall back to killing the process")
        finally:
            if real is not None:
                _os.killpg = real

    def test_the_synthesis_gets_longer_than_a_role_reading(self):
        import agent_runtime
        self.assertGreater(agent_runtime.IDEA_SYNTHESIS_TIMEOUT_S,
                           agent_runtime.IDEA_EVALUATION_TIMEOUT_S,
                           "the synthesis reads everything and writes the most; 180s lost a "
                           "complete five-agent evaluation")

    def test_the_synthesis_actually_asks_for_that_timeout(self):
        # No blanket except here. Swallowing the exception made this test pass
        # over a KeyError in its own fixture, asserting nothing.
        seen = {}
        saved = evaluator._invoke
        try:
            evaluator._invoke = lambda *a, **k: seen.update(k) or "{}"
            evaluator._synthesise(
                {"raw_idea": "x", "current_raw": "x"}, [], None,
                {"depth": "Light", "depth_reason": "internal", "in": [["product", "w"]],
                 "out": []},
                [("product", "said")], 1)
        finally:
            evaluator._invoke = saved
        self.assertEqual(seen.get("timeout_s"), agent_runtime.IDEA_SYNTHESIS_TIMEOUT_S)
        self.assertEqual(seen.get("budget"), agent_runtime.IDEA_SYNTHESIS_BUDGET_USD)


class LateRosterAddition(unittest.TestCase):
    """The roster is chosen from the Founder's raw sentence, before anyone knows
    what the company will design. A kids' coding toy that acquires share links,
    resume identifiers and telemetry is handling children's data — and Security
    was left out when none of that existed yet."""

    def test_a_named_role_is_picked_up(self):
        text = ("...direction as it stands: browser-only, share links, resume codes.\n"
                "NEEDS: security — under-13 data, share links and telemetry now exist")
        self.assertEqual(evaluator._late_addition(text, ["product", "cto"]), "security")

    def test_none_means_none(self):
        self.assertIsNone(evaluator._late_addition("...\nNEEDS: none", ["product"]))

    def test_a_role_already_present_is_not_re_added(self):
        self.assertIsNone(evaluator._late_addition("NEEDS: cto — more architecture",
                                                   ["product", "cto"]))

    def test_an_invented_role_is_ignored(self):
        self.assertIsNone(evaluator._late_addition("NEEDS: lawyer — we need counsel", ["product"]))

    def test_silence_is_not_an_addition(self):
        # A repair that simply forgets the line must not add anybody.
        self.assertIsNone(evaluator._late_addition("a repair with no NEEDS line at all", ["product"]))
        self.assertIsNone(evaluator._late_addition("", ["product"]))

    def test_only_the_first_valid_name_is_taken(self):
        # One extra call, never a cascade.
        text = "NEEDS: security — data\nNEEDS: financial — pricing"
        self.assertEqual(evaluator._late_addition(text, ["product"]), "security")


class ExpandedWorking(unittest.TestCase):
    """A real run stored ten expanded sections of 19-31 characters: the model
    had pasted back the contract's own placeholder ("expanded: section 7").
    Nothing caught it, so the page offered ten expanders that opened onto a
    label. An absence must be shown as an absence, never dressed as working."""

    VIEW = {"opp": "Medium", "why": "w", "merit": "m", "threat": "t", "diff": "d", "rec": "Proceed"}
    REAL = ("<div class=\"sk\">1. What we heard</div>A browser-based way for children to learn "
            "Python where the learning and the making are the same activity, prompted by wanting "
            "kids to actually improve rather than just be exposed to it.")

    def answers(self, expanded):
        return {str(n): [f"concise answer {n}, long enough to be real", expanded]
                for n in range(1, 11)}

    def test_real_working_is_kept_exactly(self):
        a, _v, _t = evaluator._validate({"answers": self.answers(self.REAL), "view": self.VIEW})
        self.assertEqual(a["3"][1], self.REAL)

    def test_the_placeholder_the_model_actually_echoed(self):
        # Verbatim from the stored round that exposed this.
        for stub in ("expanded: sections 1 and 2", "expanded: section 7",
                     "expanded: sections 9, 10 and 12"):
            a, _v, _t = evaluator._validate({"answers": self.answers(stub), "view": self.VIEW})
            self.assertEqual(a["1"][1], evaluator.NO_WORKING, f"{stub!r} must not pass as working")

    def test_the_new_slot_syntax_is_not_stored_either(self):
        a, _v, _t = evaluator._validate(
            {"answers": self.answers("<<your working, section 7>>"), "view": self.VIEW})
        self.assertEqual(a["1"][1], evaluator.NO_WORKING)

    def test_empty_and_whitespace_and_markup_only(self):
        for stub in ("", "   ", "<div class=\"sk\"></div>"):
            a, _v, _t = evaluator._validate({"answers": self.answers(stub), "view": self.VIEW})
            self.assertEqual(a["1"][1], evaluator.NO_WORKING)

    def test_restating_the_concise_answer_is_not_working(self):
        same = "concise answer 1, long enough to be real"
        a, _v, _t = evaluator._validate(
            {"answers": {**self.answers(self.REAL), "1": [same, same]}, "view": self.VIEW})
        self.assertEqual(a["1"][1], evaluator.NO_WORKING)

    def test_a_thin_answer_never_discards_the_paid_evaluation(self):
        # The concise layer is what the Founder decides on. Failing the whole
        # round over missing working would cost more than it saves.
        a, v, _t = evaluator._validate({"answers": self.answers("expanded: section 3"),
                                        "view": self.VIEW})
        self.assertEqual(len(a), 10)
        self.assertEqual(v["rec"], "Proceed")

    def test_the_page_shows_a_plain_line_not_an_empty_expander(self):
        rendered = pages.safe_html(evaluator.NO_WORKING)
        self.assertEqual(rendered, pages.NO_WORKING_HTML,
                         "the page constant must match what safe_html actually produces")


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
        def fake(agent, transcript, idea_id=None, **kw):
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
        def fake(agent, transcript, idea_id=None, **kw):
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
        def fake(agent, transcript, idea_id=None, **kw):
            if "decide WHO should read it" in transcript:
                return self.GOOD_ROSTER
            raise evaluator.EvaluationError("the agent gave up")
        evaluator._invoke = fake
        evaluator.run_evaluation(1, {"raw_idea": "a thing", "current_raw": "a thing"}, [])
        self.assertIsNone(self.stored())
        self.assertTrue(self.preserved, "the roster reply is evidence even when a role fails")
        # Assert the ROLE is named, not one particular phrasing of the stage —
        # the wording moved when the pipeline became invent/attack/improve, and
        # a test pinned to prose fails on a rename rather than on a defect.
        self.assertIn("Product", self.error(), "the failing role must be named")


if __name__ == "__main__":
    unittest.main(verbosity=2)
