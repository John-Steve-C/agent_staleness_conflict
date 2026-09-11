import unittest
from dataclasses import dataclass

from staleness_adaptive.models import RecoveryAction
from staleness_adaptive.storm_adapter import episode_from_storm_refusal


@dataclass
class FakeStaleFile:
    path: str = "dependency.py"
    expected_version: int = 1
    current_version: int = 2
    changed_by: str = "engineer-B"


@dataclass
class FakeResponse:
    current_content: str = "value = 2\n"
    diff: str = ""
    stale_files: tuple[FakeStaleFile, ...] = (FakeStaleFile(),)


class StormAdapterTests(unittest.TestCase):
    def test_converts_write_response_without_sdk_import(self):
        episode = episode_from_storm_refusal(
            FakeResponse(),
            episode_id="episode-1",
            repo="fixture",
            losing_agent_id="engineer-A",
            winning_agent_id="engineer-B",
            file_path="value.py",
            base_content="value = 1\n",
            proposed_content="value = 3\n",
            read_at=1,
            refused_at=3,
            intervening_writes=1,
            tokens_since_read=20,
            tool_calls_since_read=1,
            winner_intent="Update the value.",
            winner_reasoning="Two is required.",
            winner_task="Fix the value.",
            winner_trajectory=("read", "write"),
            recommended_action=RecoveryAction.ADAPT,
            refinement_hint="Rebase.",
            correct_action=RecoveryAction.ADAPT,
        )

        self.assertEqual(episode.current_content, "value = 2\n")
        self.assertEqual(episode.stale_dependencies[0].path, "dependency.py")
        self.assertIn("-value = 1", episode.unified_diff)


if __name__ == "__main__":
    unittest.main()
