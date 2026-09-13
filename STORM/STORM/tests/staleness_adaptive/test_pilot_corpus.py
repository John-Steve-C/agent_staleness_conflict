import unittest
from dataclasses import replace

from staleness_adaptive.pilot_corpus import (
    audit_corpus,
    build_pilot_corpus,
    render_payload,
    score_response,
    verify_behavior,
)


class PilotCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = build_pilot_corpus()

    def test_corpus_gates(self):
        self.assertTrue(audit_corpus(self.cases)["passed"])

    def test_false_abandon_fails_and_complete_abandon_passes(self):
        response = {"action": "abandon", "revised_content": "", "explanation": "done"}
        for case in self.cases:
            score = score_response(case, response)
            if case.acceptable_actions == ("escalate",):
                self.assertIsNone(score["verified_recovery"])
                self.assertFalse(score["equal_action_composite"])
            else:
                self.assertEqual(score["verified_recovery"], case.acceptable_actions == ("abandon",))

    def test_escalation_is_not_completed_coordination(self):
        case = self.cases[2]
        score = score_response(case, {"action": "escalate", "revised_content": "", "explanation": "conflict"})
        self.assertTrue(score["justified_escalation"])
        self.assertIsNone(score["verified_recovery"])
        self.assertIsNone(score["completed_coordination"])
        self.assertFalse(verify_behavior(case, case.reference))

    def test_behavior_and_route_are_separate(self):
        case = self.cases[1]
        response = {"action": "adapt", "revised_content": case.reference, "explanation": "rebase"}
        score = score_response(case, response)
        self.assertFalse(score["route_correct"])
        self.assertTrue(score["verified_recovery"])
        self.assertFalse(score_response(case, response, truncated=True)["verified_recovery"])

    def test_prompt_is_independent_of_evaluator_fields(self):
        case = self.cases[0]
        altered = replace(case, acceptable_actions=("escalate",), reference="SECRET", obligations=())
        for condition in ("P1", "P2", "P3"):
            self.assertEqual(render_payload(case.public, condition), render_payload(altered.public, condition))
        with self.assertRaises(ValueError):
            render_payload(case.public, "P5")

    def test_rejects_invalid_and_unsafe_revisions(self):
        case = self.cases[0]
        for content in ("import os", "open('/tmp/x', 'w')", "while True: pass", "def main(:", ""):
            self.assertFalse(verify_behavior(case, content))
        for parsed in (None, {}, {"action": "queue"}, {"action": "abandon", "revised_content": None}):
            self.assertFalse(score_response(case, parsed)["valid_response"])


if __name__ == "__main__":
    unittest.main()
