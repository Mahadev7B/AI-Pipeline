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
            return evaluator._select_roster({"raw_idea": "x"}, [], None)
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
        self.assertIn("the Chief of Staff's answer", blobs)
        self.assertIn("not json at all", blobs["the Chief of Staff's answer"])
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
