import unittest

from staleness_adaptive.item_calibration import (
    audit_candidate_structure,
    calibrate_items,
)


class ItemCalibrationTests(unittest.TestCase):
    def test_gate_requires_crossed_calibrated_family_clusters(self):
        episodes = {}
        results = []
        for family_index in range(30):
            for action in ("adapt", "abandon", "escalate"):
                episode_id = f"family-{family_index}-{action}-k4"
                episodes[episode_id] = {
                    "episode_id": episode_id,
                    "correct_action": action,
                    "staleness": {"edit_distance_writes": 4},
                    "metadata": {"family": f"family-{family_index}"},
                }
                for seed in range(10):
                    results.append(
                        {
                            "episode_id": episode_id,
                            "requested_condition": "P1",
                            "recovery_success": str(seed < 5),
                            "receiver_context_target_tokens": "8000",
                            "receiver_trajectory_tokens": "8000",
                        }
                    )

        decisions, gate = calibrate_items(episodes, results)

        self.assertEqual(len(decisions), 90)
        self.assertTrue(audit_candidate_structure(episodes)["action_staleness_fully_crossed"])
        self.assertTrue(gate["passed"])
        self.assertTrue(gate["action_staleness_fully_crossed"])
        self.assertEqual(
            gate["admitted_family_clusters_by_action"],
            {"abandon": 30, "adapt": 30, "escalate": 30},
        )
        self.assertEqual(gate["invalid_response_count"], 0)

    def test_saturated_short_context_items_fail_gate(self):
        episodes = {
            "family-adapt-k1": {
                "episode_id": "family-adapt-k1",
                "correct_action": "adapt",
                "staleness": {"edit_distance_writes": 1},
                "metadata": {"family": "family"},
            }
        }
        results = [
            {
                "episode_id": "family-adapt-k1",
                "requested_condition": "P1",
                "recovery_success": "True",
                "receiver_context_target_tokens": "1000",
                "receiver_trajectory_tokens": "1000",
            }
        ]

        decisions, gate = calibrate_items(episodes, results)

        self.assertFalse(gate["passed"])
        self.assertIn("context_below_8000", decisions[0]["exclusion_reasons"])
        self.assertIn("outside_30_70_band", decisions[0]["exclusion_reasons"])

    def test_invalid_responses_cannot_admit_an_item(self):
        episodes = {
            "family-adapt-k8": {
                "episode_id": "family-adapt-k8",
                "correct_action": "adapt",
                "staleness": {"edit_distance_writes": 8},
                "metadata": {"family": "family"},
            }
        }
        results = [
            {
                "episode_id": "family-adapt-k8",
                "requested_condition": "P1",
                "recovery_success": str(index < 5),
                "receiver_trajectory_tokens": "8000",
                "notes": (
                    "Invalid model response: truncated" if index == 0 else ""
                ),
            }
            for index in range(10)
        ]

        decisions, _ = calibrate_items(episodes, results)

        self.assertFalse(decisions[0]["admitted"])
        self.assertEqual(decisions[0]["invalid_response_count"], 1)
        self.assertIn("invalid_model_response", decisions[0]["exclusion_reasons"])
        self.assertFalse(decisions[0]["floor_control"])


if __name__ == "__main__":
    unittest.main()
