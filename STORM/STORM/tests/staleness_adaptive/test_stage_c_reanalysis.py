import unittest

from staleness_adaptive.stage_c_reanalysis import action_contrasts


class StageCReanalysisTests(unittest.TestCase):
    def test_clusters_paired_contrasts_on_family_and_nests_seeds(self):
        rows = []
        families = {}
        outcomes = {
            "family-a-k1": ((True, False), (True, True)),
            "family-a-k2": ((False, False), (True, False)),
            "family-b-k1": ((False, True), (True, True)),
        }
        for episode_id, (p1, p2) in outcomes.items():
            families[episode_id] = episode_id.split("-k", 1)[0]
            for seed, (baseline, comparator) in enumerate(zip(p1, p2, strict=True)):
                for condition, success in (("P1", baseline), ("P2", comparator)):
                    rows.append(
                        {
                            "episode_id": episode_id,
                            "seed": str(seed),
                            "requested_condition": condition,
                            "correct_action": "adapt",
                            "recovery_success": str(success),
                        }
                    )

        result = action_contrasts(rows, families)["adapt"][0]

        self.assertEqual(result["n_episode_pairs"], 3)
        self.assertEqual(result["n_family_clusters"], 2)
        self.assertAlmostEqual(result["baseline_success_rate"], 1 / 3)
        self.assertAlmostEqual(result["comparator_success_rate"], 5 / 6)
        self.assertAlmostEqual(result["paired_success_difference"], 0.5)

    def test_marks_saturated_baseline_mde_as_not_estimable(self):
        rows = []
        families = {"a-k1": "a", "b-k1": "b"}
        for episode_id in families:
            for condition in ("P1", "P2"):
                rows.append(
                    {
                        "episode_id": episode_id,
                        "seed": "0",
                        "requested_condition": condition,
                        "correct_action": "abandon",
                        "recovery_success": "True",
                    }
                )

        result = action_contrasts(rows, families)["abandon"][0]

        self.assertEqual(result["mde_80pct_power"], "")
        self.assertEqual(result["mde_status"], "not_estimable_saturated_baseline")


if __name__ == "__main__":
    unittest.main()
