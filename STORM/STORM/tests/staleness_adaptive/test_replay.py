import unittest

from staleness_adaptive.case_studies import (
    ControlledRecoveryBackend,
    build_controlled_episodes,
)
from staleness_adaptive.models import (
    PayloadCondition,
    RecoveryAction,
    RecoveryAttempt,
    RefusalPosition,
)
from staleness_adaptive.replay import ReplayRunner


class ReplayTests(unittest.TestCase):
    def test_non_write_coordination_actions_can_succeed(self):
        for action in (RecoveryAction.QUEUE, RecoveryAction.SERIALIZE):
            attempt = RecoveryAttempt(
                action=action,
                accepted_write=False,
                touched_tests_pass=True,
                repeat_refusal=False,
                recovery_tokens=0,
                recovery_tool_calls=0,
            )
            self.assertTrue(attempt.success)

    def test_controlled_cases_expose_crossover(self):
        results = ReplayRunner(ControlledRecoveryBackend()).run_matrix(
            build_controlled_episodes(),
            (PayloadCondition.P1, PayloadCondition.P3, PayloadCondition.ADAPTIVE),
        )

        low = [item for item in results if item.edit_distance_writes < 4]
        high = [item for item in results if item.edit_distance_writes >= 4]
        p1_low = [
            item.recovery_success
            for item in low
            if item.requested_condition == PayloadCondition.P1
        ]
        p3_low = [
            item.recovery_success
            for item in low
            if item.requested_condition == PayloadCondition.P3
        ]
        p1_high = [
            item.recovery_success
            for item in high
            if item.requested_condition == PayloadCondition.P1
        ]
        p3_high = [
            item.recovery_success
            for item in high
            if item.requested_condition == PayloadCondition.P3
        ]
        adaptive = [
            item
            for item in results
            if item.requested_condition == PayloadCondition.ADAPTIVE
        ]

        self.assertEqual(p1_low, p3_low)
        self.assertLess(sum(p1_high), sum(p3_high))
        self.assertTrue(all(item.recovery_success for item in adaptive))

    def test_records_context_position_signal_ratio_and_deference(self):
        episode = build_controlled_episodes()[0]

        result = ReplayRunner(ControlledRecoveryBackend()).run(
            episode,
            PayloadCondition.P6,
            receiver_context_tokens=1000,
            refusal_position=RefusalPosition.MIDDLE,
            injected_route=RecoveryAction.ADAPT,
        )

        self.assertEqual(result.receiver_context_target_tokens, 1000)
        self.assertEqual(result.receiver_trajectory_tokens, 1000)
        self.assertEqual(result.refusal_position, RefusalPosition.MIDDLE)
        self.assertTrue(result.payload_action_correct)
        self.assertTrue(result.deferred_to_payload)
        self.assertGreater(result.payload_context_ratio, 0)


if __name__ == "__main__":
    unittest.main()
