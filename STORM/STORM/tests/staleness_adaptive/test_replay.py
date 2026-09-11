import unittest

from staleness_adaptive.case_studies import (
    ControlledRecoveryBackend,
    build_controlled_episodes,
)
from staleness_adaptive.models import PayloadCondition, RecoveryAction, RecoveryAttempt
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


if __name__ == "__main__":
    unittest.main()
