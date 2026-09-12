from __future__ import annotations

import unittest

from staleness_adaptive.models import RecoveryAction
from staleness_adaptive.rebuilt_corpus import (
    FRESH_SCENARIO_FAMILIES,
    SCENARIO_FAMILIES,
    audit_rebuilt_corpus,
    build_rebuilt_episodes,
)


class RebuiltCorpusTests(unittest.TestCase):
    def test_corpus_is_fully_crossed_and_mechanically_valid(self) -> None:
        episodes = build_rebuilt_episodes()

        self.assertGreaterEqual(len(SCENARIO_FAMILIES), 30)
        self.assertEqual(len(episodes), len(SCENARIO_FAMILIES) * 3)
        for family in SCENARIO_FAMILIES:
            family_episodes = [
                episode
                for episode in episodes
                if episode.metadata["family"] == family.name
            ]
            self.assertEqual(
                {episode.correct_action for episode in family_episodes},
                {
                    RecoveryAction.ADAPT,
                    RecoveryAction.ABANDON,
                    RecoveryAction.ESCALATE,
                },
            )
            self.assertEqual(
                {episode.staleness.edit_distance_writes for episode in family_episodes},
                {8},
            )

        audit = audit_rebuilt_corpus(episodes)
        self.assertTrue(audit["passed"], audit)
        self.assertEqual(audit["mechanical_failure_count"], 0)

    def test_fresh_corpus_is_independently_large_enough(self) -> None:
        episodes = build_rebuilt_episodes(families=FRESH_SCENARIO_FAMILIES)

        self.assertEqual(len(FRESH_SCENARIO_FAMILIES), 40)
        self.assertEqual(len(episodes), 120)
        self.assertTrue(audit_rebuilt_corpus(episodes)["passed"])


if __name__ == "__main__":
    unittest.main()
