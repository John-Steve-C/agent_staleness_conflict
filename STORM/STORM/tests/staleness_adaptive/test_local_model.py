import io
import json
import unittest
from unittest.mock import patch

from staleness_adaptive.case_studies import build_controlled_episodes
from staleness_adaptive.local_model import (
    OpenAICompatibleActionPolicy,
    _extract_json,
    _valid_revised_content,
)
from staleness_adaptive.models import RecoveryAction


class LocalModelTests(unittest.TestCase):
    def test_extracts_json_from_fenced_response(self):
        parsed = _extract_json(
            '```json\n{"action":"abandon","revised_content":"","explanation":"done"}\n```'
        )

        self.assertEqual(parsed["action"], "abandon")

    def test_mechanical_adaptation_check(self):
        episode = build_controlled_episodes()[0]
        valid = (
            "def normalize(name):\n"
            "    if not isinstance(name, str):\n"
            "        raise TypeError\n"
            "    return name.strip().lower()\n"
        )

        self.assertTrue(_valid_revised_content(episode, valid))
        self.assertFalse(_valid_revised_content(episode, "def normalize(name):\n    return name\n"))

    def test_comments_cannot_satisfy_mechanical_checks(self):
        episode = build_controlled_episodes()[0]
        fake = "# isinstance(name, str)\n# .strip().lower()\npass\n"

        self.assertFalse(_valid_revised_content(episode, fake))

    def test_action_policy_uses_observable_state_without_ground_truth(self):
        episode = build_controlled_episodes()[2]
        response = io.BytesIO(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "action": "abandon",
                                        "refinement_hint": "The task is already complete.",
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                }
            ).encode()
        )
        policy = OpenAICompatibleActionPolicy("http://local/v1", "qwen")

        with patch("urllib.request.urlopen", return_value=response):
            prediction = policy.predict(episode, seed=0)

        prompt = policy.records[0]["request"]["messages"][1]["content"]
        self.assertEqual(prediction.action, RecoveryAction.ABANDON)
        self.assertNotIn(episode.winner_reasoning, prompt)
        self.assertNotIn("correct_action", prompt)


if __name__ == "__main__":
    unittest.main()
