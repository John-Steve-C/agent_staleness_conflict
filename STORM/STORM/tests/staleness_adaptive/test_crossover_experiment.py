import unittest
from collections import Counter
from dataclasses import replace

from staleness_adaptive.crossover_experiment import (
    SCENARIOS,
    audit_p3_leakage,
    build_crossover_episodes,
    parse_staleness_levels,
)
from staleness_adaptive.models import RecoveryAction
from staleness_adaptive.payloads import PayloadRenderer


class CrossoverExperimentTests(unittest.TestCase):
    def test_builds_every_scenario_at_every_staleness_level(self):
        episodes = build_crossover_episodes()

        self.assertEqual(len(episodes), len(SCENARIOS) * 16)
        self.assertEqual(
            Counter(item.staleness.edit_distance_writes for item in episodes),
            Counter({k: len(SCENARIOS) for k in range(1, 17)}),
        )
        self.assertEqual(len({item.episode_id for item in episodes}), len(episodes))

    def test_each_scenario_switches_from_adapt_at_its_boundary(self):
        episodes = build_crossover_episodes(tuple(range(1, 18)))
        by_id = {item.episode_id: item for item in episodes}

        for scenario in SCENARIOS:
            before = by_id[f"{scenario.name}-k{scenario.switch_k - 1}"]
            after = by_id[f"{scenario.name}-k{scenario.switch_k}"]
            self.assertEqual(before.correct_action, RecoveryAction.ADAPT)
            self.assertEqual(after.correct_action, scenario.high_action)

    def test_p3_payloads_pass_leakage_audit(self):
        audit = audit_p3_leakage(build_crossover_episodes(), PayloadRenderer())

        self.assertTrue(audit["passed"])
        self.assertEqual(audit["p3_directive_cue_count"], 0)
        self.assertEqual(audit["forbidden_prompt_field_count"], 0)

    def test_p3_leakage_audit_rejects_recovery_directives(self):
        episode = replace(
            build_crossover_episodes((1,))[0],
            winner_reasoning="The correct recovery is to abandon the stale patch.",
        )

        audit = audit_p3_leakage([episode], PayloadRenderer())

        self.assertFalse(audit["passed"])
        self.assertEqual(audit["p3_directive_cue_count"], 1)

    def test_revision_history_grows_with_k_and_is_protected(self):
        first, second = build_crossover_episodes((1, 2))[:2]

        self.assertEqual(len(first.metadata["protected_assignments"]), 1)
        self.assertEqual(len(second.metadata["protected_assignments"]), 2)

    def test_parses_ranges_and_explicit_staleness_levels(self):
        self.assertEqual(parse_staleness_levels("1-3,8,12"), (1, 2, 3, 8, 12))


if __name__ == "__main__":
    unittest.main()
