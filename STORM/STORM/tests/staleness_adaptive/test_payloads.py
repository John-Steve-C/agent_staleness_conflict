import unittest
from pathlib import Path

from staleness_adaptive.case_studies import build_controlled_episodes
from staleness_adaptive.crossover_experiment import build_crossover_episodes
from staleness_adaptive.local_model import build_recovery_user_prompt
from staleness_adaptive.models import (
    PayloadCondition,
    PolicyPrediction,
    RefusalPosition,
    RecoveryAction,
)
from staleness_adaptive.payloads import (
    STANDING_TO_REJECT,
    PayloadRenderer,
    TokenizerJsonCounter,
)


QWEN_TOKENIZER = Path("/shared/models/hf/Qwen3.5-35B-A3B/tokenizer.json")


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

    def test_context_length_pads_trajectory_without_padding_payload(self):
        short = self.renderer.render(
            self.low,
            PayloadCondition.P1,
            receiver_context_tokens=1000,
            refusal_position=RefusalPosition.HEAD,
        )
        long = self.renderer.render(
            self.low,
            PayloadCondition.P1,
            receiver_context_tokens=8000,
            refusal_position=RefusalPosition.MIDDLE,
        )

        self.assertEqual(short.text, long.text)
        self.assertEqual(short.token_count, long.token_count)
        self.assertEqual(
            len(long.receiver_trajectory_before.split())
            + len(long.receiver_trajectory_after.split()),
            8000,
        )
        trajectory = (
            long.receiver_trajectory_before + " " + long.receiver_trajectory_after
        )
        self.assertEqual(
            trajectory.count(self.low.metadata["losing_agent_task"]),
            1,
        )
        middle_prompt = build_recovery_user_prompt(self.low, long)
        self.assertLess(
            middle_prompt.index("Receiver's own trajectory"),
            middle_prompt.index("Refusal payload"),
        )
        self.assertTrue(long.receiver_trajectory_before)
        self.assertTrue(long.receiver_trajectory_after)

    @unittest.skipUnless(QWEN_TOKENIZER.is_file(), "Qwen tokenizer is not installed")
    def test_qwen_tokenizer_realises_every_registered_context_length(self):
        renderer = PayloadRenderer(token_counter=TokenizerJsonCounter(QWEN_TOKENIZER))

        for target in (1000, 8000, 32000, 128000):
            payload = renderer.render(
                self.low,
                PayloadCondition.P1,
                receiver_context_tokens=target,
                refusal_position=RefusalPosition.TAIL,
            )
            trajectory = payload.receiver_trajectory_before
            self.assertEqual(payload.receiver_trajectory_tokens, target)
            self.assertEqual(renderer.token_counter(trajectory), target)
            self.assertEqual(
                trajectory.count(self.low.metadata["losing_agent_task"]), 1
            )

    def test_p6_uses_injected_route_with_falsifiable_ground(self):
        payload = self.renderer.render(
            self.low,
            PayloadCondition.P6,
            injected_route=RecoveryAction.ESCALATE,
        )

        self.assertEqual(payload.directed_action, RecoveryAction.ESCALATE)
        self.assertEqual(payload.policy_prediction.source, "injected-route")
        self.assertIn("Injected recovery route: escalate", payload.text)
        self.assertIn(f"{self.low.file_path}:1", payload.text)

        with self.assertRaisesRegex(ValueError, "explicitly injected route"):
            self.renderer.render(self.low, PayloadCondition.P6)

    def test_p7_instruction_is_episode_independent_and_fifteen_tokens(self):
        extensions = []
        for episode in build_controlled_episodes():
            text = self.renderer.render(episode, PayloadCondition.P7).text
            extensions.append(text.rsplit("Standing instruction:\n", 1)[1])

        self.assertEqual(set(extensions), {STANDING_TO_REJECT})
        self.assertEqual(len(STANDING_TO_REJECT.split()), 15)

    def test_p8_computes_all_three_routes_from_execution(self):
        episodes = {item.episode_id: item for item in build_crossover_episodes((1, 4))}
        adapt = self.renderer.render(episodes["normalization-k1"], PayloadCondition.P8)
        abandon = self.renderer.render(episodes["normalization-k4"], PayloadCondition.P8)
        escalate = self.renderer.render(episodes["authorization-k4"], PayloadCondition.P8)

        self.assertEqual(adapt.directed_action, RecoveryAction.ADAPT)
        self.assertEqual(abandon.directed_action, RecoveryAction.ABANDON)
        self.assertEqual(escalate.directed_action, RecoveryAction.ESCALATE)
        self.assertEqual(escalate.policy_prediction.source, "execution")


if __name__ == "__main__":
    unittest.main()
