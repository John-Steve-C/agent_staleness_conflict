import tempfile
import unittest
from pathlib import Path

from staleness_adaptive.case_studies import build_controlled_episodes
from staleness_adaptive.episode_log import EpisodeLog


class EpisodeLogTests(unittest.TestCase):
    def test_jsonl_round_trip(self):
        episodes = build_controlled_episodes()
        with tempfile.TemporaryDirectory() as directory:
            log = EpisodeLog(Path(directory) / "episodes.jsonl")
            log.write(episodes)

            restored = log.read()

        self.assertEqual(restored, episodes)


if __name__ == "__main__":
    unittest.main()
