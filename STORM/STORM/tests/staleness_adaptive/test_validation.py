import unittest
from dataclasses import replace

from staleness_adaptive.crossover_experiment import build_crossover_episodes
from staleness_adaptive.validation import validate_dependencies, validate_revision


VALID_REVISIONS = {
    "normalization": (
        "def normalize(name):\n"
        "    if not isinstance(name, str):\n"
        "        raise TypeError('name must be text')\n"
        "    return name.strip().lower()\n"
    ),
    "formatting": (
        "def render(value, prefix=''):\n"
        "    text = str(value).strip()\n"
        "    return prefix + text\n"
    ),
    "cache": (
        "DEFAULT_TTL = 60\n\n"
        "def build_cache(max_size, ttl=DEFAULT_TTL):\n"
        "    return {'max_size': max_size, 'ttl': ttl, 'items': {}}\n"
    ),
    "authorization": (
        "def authorize(user, scope, audit=None):\n"
        "    scope = scope.strip()\n"
        "    if scope not in user.scopes:\n"
        "        raise PermissionError(scope)\n"
        "    if audit is not None:\n"
        "        audit.record(user, scope)\n"
        "    return True\n"
    ),
    "transaction": (
        "def commit(store, expected_version, value, retries=2, logger=None):\n"
        "    for attempt in range(retries + 1):\n"
        "        if store.version == expected_version:\n"
        "            store.write(value)\n"
        "            if logger is not None:\n"
        "                logger.info('committed')\n"
        "            return\n"
        "    raise RuntimeError('stale')\n"
    ),
    "serialization": (
        "import json\n\n"
        "def dumps(value):\n"
        "    if not isinstance(value, dict):\n"
        "        raise TypeError('value must be a dict')\n"
        "    return json.dumps(value, sort_keys=True)\n"
    ),
    "deduplication": (
        "def unique(items):\n"
        "    if items is None:\n"
        "        raise TypeError('items are required')\n"
        "    return list(dict.fromkeys(items))\n"
    ),
    "pagination": (
        "def page(items, limit, offset=0):\n"
        "    limit = max(0, limit)\n"
        "    return items[offset:offset + limit]\n"
    ),
}


def _with_protected_assignments(source, episode):
    lines = "\n".join(
        f"{name} = {value}"
        for name, value in episode.metadata["protected_assignments"].items()
    )
    return f"{source}\n{lines}\n"


class ValidationTests(unittest.TestCase):
    def test_behavioral_validators_accept_complete_rebases(self):
        for episode in build_crossover_episodes((1,)):
            source = _with_protected_assignments(
                VALID_REVISIONS[episode.metadata["scenario"]], episode
            )
            with self.subTest(scenario=episode.metadata["scenario"]):
                self.assertTrue(validate_revision(episode, source))

    def test_behavioral_validators_reject_dropped_concurrent_state(self):
        episode = build_crossover_episodes((1,))[0]

        self.assertFalse(validate_revision(episode, VALID_REVISIONS["normalization"]))

    def test_dependency_checks_distinguish_adaptation_from_escalation(self):
        episodes = {
            item.episode_id: item for item in build_crossover_episodes((1, 4))
        }

        self.assertTrue(
            validate_dependencies(
                episodes["normalization-k1"],
                episodes["normalization-k1"].current_content,
            )
        )
        self.assertFalse(
            validate_dependencies(
                episodes["authorization-k4"],
                episodes["authorization-k4"].current_content,
            )
        )

    def test_custom_behavior_and_dependency_checks(self):
        episode = replace(
            build_crossover_episodes((1,))[0],
            metadata={
                "protected_assignments": {},
                "validator": "custom",
                "behavior_check": "assert transform(2) == 4",
                "dependency_check": "assert transform(0) >= 0",
            },
        )

        self.assertTrue(
            validate_revision(episode, "def transform(value):\n    return value * 2\n")
        )
        self.assertFalse(
            validate_revision(episode, "def transform(value):\n    return value\n")
        )
        self.assertFalse(
            validate_dependencies(episode, "def transform(value):\n    return -1\n")
        )


if __name__ == "__main__":
    unittest.main()
