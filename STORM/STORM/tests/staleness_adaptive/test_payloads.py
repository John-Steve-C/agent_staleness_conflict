import unittest

from staleness_adaptive.case_studies import build_controlled_episodes
from staleness_adaptive.models import (
    PayloadCondition,
    PolicyPrediction,
    RecoveryAction,
)
from staleness_adaptive.payloads import PayloadRenderer


class QueuePolicy:
    def predict(self, episode, seed):
        del episode, seed
        return PolicyPrediction(
            action=RecoveryAction.QUEUE,
            refinement_hint="Wait for the dependency owner to finish.",
            source="test-policy",
        )


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.low, _, self.high, _ = build_controlled_episodes()
        self.renderer = PayloadRenderer()

    def test_p1_contains_storm_feedback(self):
        text = self.renderer.render(self.low, PayloadCondition.P1).text

        self.assertIn("Unified diff", text)
        self.assertIn("Stale dependencies", text)
        self.assertIn("Full current content", text)

    def test_payload_extensions_are_condition_specific(self):
        self.assertIn(
            self.low.winner_intent,
            self.renderer.render(self.low, PayloadCondition.P2).text,
        )
        self.assertIn(
            "Winning edit reasoning",
            self.renderer.render(self.low, PayloadCondition.P3).text,
        )
        self.assertIn(
            "Policy-predicted recovery route",
            self.renderer.render(self.low, PayloadCondition.P5).text,
        )

    def test_p5_uses_policy_prediction_not_ground_truth(self):
        renderer = PayloadRenderer(action_policy=QueuePolicy())

        predicted = renderer.render(self.low, PayloadCondition.P5)
        oracle = renderer.render(self.low, PayloadCondition.P5_ORACLE)

        self.assertIn("route: queue", predicted.text)
        self.assertEqual(predicted.policy_prediction.action, RecoveryAction.QUEUE)
        self.assertNotIn("route: queue", oracle.text)

    def test_padded_control_matches_p3_proxy_token_count(self):
        p3 = self.renderer.render(self.high, PayloadCondition.P3)
        padded = self.renderer.render(self.high, PayloadCondition.P1_PAD)

        self.assertEqual(padded.token_count, p3.token_count)
        self.assertNotIn(self.high.winner_reasoning, padded.text)

    def test_adaptive_policy_switches_at_four_writes(self):
        low = self.renderer.render(self.low, PayloadCondition.ADAPTIVE)
        high = self.renderer.render(self.high, PayloadCondition.ADAPTIVE)

        self.assertEqual(low.selected_condition, PayloadCondition.P1)
        self.assertEqual(high.selected_condition, PayloadCondition.P5)


if __name__ == "__main__":
    unittest.main()
