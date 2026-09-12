from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shlex
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from .episode_log import EpisodeLog
from .local_model import (
    OpenAICompatibleActionPolicy,
    OpenAICompatibleRecoveryBackend,
    build_recovery_user_prompt,
)
from .measurement import make_unified_diff, measure_staleness
from .models import (
    ConflictEpisode,
    PayloadCondition,
    PolicyPrediction,
    RecoveryAction,
    ReplayResult,
    StaleDependency,
)
from .payloads import AdaptivePayloadPolicy, PayloadRenderer
from .replay import ReplayRunner
from .validation import validate_revision


@dataclass(frozen=True)
class Scenario:
    name: str
    file_path: str
    switch_k: int
    high_action: RecoveryAction
    losing_task: str
    base_content: str
    proposed_content: str
    low_content: str
    high_content: str
    low_intent: str
    high_intent: str
    low_reasoning: str
    high_reasoning: str
    required_substrings: tuple[str, ...]
    symbols: frozenset[str]


SCENARIOS = (
    Scenario(
        name="normalization",
        file_path="names.py",
        switch_k=4,
        high_action=RecoveryAction.ABANDON,
        losing_task="Make normalize() return lowercase text without losing type validation.",
        base_content="def normalize(name):\n    return name.strip()\n",
        proposed_content="def normalize(name):\n    return name.strip().lower()\n",
        low_content=(
            "def normalize(name):\n"
            "    if not isinstance(name, str):\n"
            "        raise TypeError('name must be text')\n"
            "    return name.strip()\n"
        ),
        high_content=(
            "def normalize(name):\n"
            "    if not isinstance(name, str):\n"
            "        raise TypeError('name must be text')\n"
            "    return name.strip().lower()\n"
        ),
        low_intent="Add explicit input validation while preserving normalization behavior.",
        high_intent="Complete validated lowercase normalization for all callers.",
        low_reasoning=(
            "Rejecting non-text names makes failures explicit before whitespace normalization."
        ),
        high_reasoning=(
            "Type validation precedes whitespace trimming and lowercase conversion so names "
            "have a stable normalized representation."
        ),
        required_substrings=("isinstance(name, str)", ".strip().lower()"),
        symbols=frozenset({"normalize"}),
    ),
    Scenario(
        name="formatting",
        file_path="formatting.py",
        switch_k=5,
        high_action=RecoveryAction.ABANDON,
        losing_task="Strip converted values while preserving the optional prefix feature.",
        base_content="def render(value):\n    return str(value)\n",
        proposed_content="def render(value):\n    return str(value).strip()\n",
        low_content=(
            "def render(value, prefix=''):\n"
            "    text = str(value)\n"
            "    return prefix + text\n"
        ),
        high_content=(
            "def render(value, prefix=''):\n"
            "    text = str(value).strip()\n"
            "    return prefix + text\n"
        ),
        low_intent="Add an optional prefix without changing value conversion.",
        high_intent="Complete prefix-aware rendering with stripped converted values.",
        low_reasoning=(
            "The prefix is joined after text conversion so callers can add a label without "
            "changing input handling."
        ),
        high_reasoning=(
            "Whitespace is removed from the converted value before the optional prefix is joined."
        ),
        required_substrings=("prefix", ".strip()", "return prefix + text"),
        symbols=frozenset({"render"}),
    ),
    Scenario(
        name="cache",
        file_path="cache.py",
        switch_k=3,
        high_action=RecoveryAction.ABANDON,
        losing_task="Implement build_cache() with both capacity and TTL configuration.",
        base_content="def build_cache(max_size):\n    raise NotImplementedError\n",
        proposed_content=(
            "def build_cache(max_size):\n"
            "    return {'max_size': max_size, 'items': {}}\n"
        ),
        low_content=(
            "DEFAULT_TTL = 60\n\n"
            "def build_cache(max_size):\n"
            "    raise NotImplementedError\n"
        ),
        high_content=(
            "DEFAULT_TTL = 60\n\n"
            "def build_cache(max_size, ttl=DEFAULT_TTL):\n"
            "    return {'max_size': max_size, 'ttl': ttl, 'items': {}}\n"
        ),
        low_intent="Define the shared TTL default before the constructor is implemented.",
        high_intent="Finish the cache constructor with capacity, TTL, and item storage.",
        low_reasoning=(
            "A shared TTL constant centralizes the default lifetime for cache instances."
        ),
        high_reasoning=(
            "The constructor stores capacity, lifetime, and an empty item mapping so callers "
            "receive a fully initialized cache."
        ),
        required_substrings=("DEFAULT_TTL", "'ttl': ttl", "'max_size': max_size"),
        symbols=frozenset({"build_cache", "DEFAULT_TTL"}),
    ),
    Scenario(
        name="authorization",
        file_path="auth.py",
        switch_k=4,
        high_action=RecoveryAction.ESCALATE,
        losing_task="Add audit recording while preserving mandatory scope enforcement.",
        base_content=(
            "def authorize(user, scope):\n"
            "    if scope not in user.scopes:\n"
            "        raise PermissionError(scope)\n"
            "    return True\n"
        ),
        proposed_content=(
            "def authorize(user, scope, audit=None):\n"
            "    if scope not in user.scopes:\n"
            "        raise PermissionError(scope)\n"
            "    if audit is not None:\n"
            "        audit.record(user, scope)\n"
            "    return True\n"
        ),
        low_content=(
            "def authorize(user, scope):\n"
            "    scope = scope.strip()\n"
            "    if scope not in user.scopes:\n"
            "        raise PermissionError(scope)\n"
            "    return True\n"
        ),
        high_content=(
            "def authorize(user, scope, audit=None):\n"
            "    if audit is not None:\n"
            "        audit.record(user, scope)\n"
            "    return True\n"
        ),
        low_intent="Normalize scope values while retaining the existing authorization check.",
        high_intent="Move authorization to an audit-first flow that permits every request.",
        low_reasoning=(
            "Normalizing the scope before membership checking avoids mismatches caused by "
            "surrounding whitespace."
        ),
        high_reasoning=(
            "Audit recording now occurs for every request, and the earlier scope membership "
            "branch was removed to simplify the flow."
        ),
        required_substrings=("scope not in user.scopes", "audit.record(user, scope)"),
        symbols=frozenset({"authorize", "PermissionError"}),
    ),
    Scenario(
        name="transaction",
        file_path="transaction.py",
        switch_k=6,
        high_action=RecoveryAction.ESCALATE,
        losing_task="Add bounded retry while preserving optimistic version checks.",
        base_content=(
            "def commit(store, expected_version, value):\n"
            "    if store.version != expected_version:\n"
            "        raise RuntimeError('stale')\n"
            "    store.write(value)\n"
        ),
        proposed_content=(
            "def commit(store, expected_version, value, retries=2):\n"
            "    for attempt in range(retries + 1):\n"
            "        if store.version == expected_version:\n"
            "            store.write(value)\n"
            "            return\n"
            "    raise RuntimeError('stale')\n"
        ),
        low_content=(
            "def commit(store, expected_version, value, logger=None):\n"
            "    if store.version != expected_version:\n"
            "        raise RuntimeError('stale')\n"
            "    store.write(value)\n"
            "    if logger is not None:\n"
            "        logger.info('committed')\n"
        ),
        high_content=(
            "def commit(store, expected_version, value, logger=None):\n"
            "    store.write(value)\n"
            "    if logger is not None:\n"
            "        logger.info('committed')\n"
        ),
        low_intent="Add commit logging without changing optimistic concurrency checks.",
        high_intent="Simplify commits by removing version rejection before writing.",
        low_reasoning=(
            "Logging occurs only after a version-checked write completes, keeping observability "
            "aligned with successful commits."
        ),
        high_reasoning=(
            "The version guard was removed so writes proceed immediately before the optional "
            "log record."
        ),
        required_substrings=("expected_version", "range(retries + 1)", "logger.info"),
        symbols=frozenset({"commit", "expected_version"}),
    ),
    Scenario(
        name="serialization",
        file_path="serialization.py",
        switch_k=7,
        high_action=RecoveryAction.ABANDON,
        losing_task="Implement stable dictionary serialization using sorted keys.",
        base_content="def dumps(value):\n    raise NotImplementedError\n",
        proposed_content=(
            "import json\n\n"
            "def dumps(value):\n"
            "    return json.dumps(value, sort_keys=True)\n"
        ),
        low_content=(
            "import json\n\n"
            "def dumps(value):\n"
            "    if not isinstance(value, dict):\n"
            "        raise TypeError('value must be a dict')\n"
            "    raise NotImplementedError\n"
        ),
        high_content=(
            "import json\n\n"
            "def dumps(value):\n"
            "    if not isinstance(value, dict):\n"
            "        raise TypeError('value must be a dict')\n"
            "    return json.dumps(value, sort_keys=True)\n"
        ),
        low_intent="Validate dictionary input before serialization is implemented.",
        high_intent="Complete validated stable serialization with sorted keys.",
        low_reasoning=(
            "Rejecting non-dictionary values before encoding keeps the contract narrow and "
            "explicit."
        ),
        high_reasoning=(
            "Validated dictionaries are encoded with sorted keys to make output deterministic."
        ),
        required_substrings=("isinstance(value, dict)", "sort_keys=True"),
        symbols=frozenset({"dumps"}),
    ),
    Scenario(
        name="deduplication",
        file_path="deduplication.py",
        switch_k=17,
        high_action=RecoveryAction.ABANDON,
        losing_task="Preserve first-seen order while deduplicating validated input.",
        base_content="def unique(items):\n    return list(set(items))\n",
        proposed_content=(
            "def unique(items):\n"
            "    return list(dict.fromkeys(items))\n"
        ),
        low_content=(
            "def unique(items):\n"
            "    if items is None:\n"
            "        raise TypeError('items are required')\n"
            "    return list(set(items))\n"
        ),
        high_content=(
            "def unique(items):\n"
            "    if items is None:\n"
            "        raise TypeError('items are required')\n"
            "    return list(dict.fromkeys(items))\n"
        ),
        low_intent="Reject missing collections before removing duplicate values.",
        high_intent="Complete validated, order-preserving duplicate removal.",
        low_reasoning=(
            "An explicit missing-input check gives callers a stable failure mode before values "
            "are processed."
        ),
        high_reasoning=(
            "Dictionary key insertion order retains the first occurrence of each validated value."
        ),
        required_substrings=("items is None", "dict.fromkeys(items)"),
        symbols=frozenset({"unique"}),
    ),
    Scenario(
        name="pagination",
        file_path="pagination.py",
        switch_k=17,
        high_action=RecoveryAction.ABANDON,
        losing_task="Clamp negative limits while preserving offset-based pagination.",
        base_content="def page(items, limit):\n    return items[:limit]\n",
        proposed_content=(
            "def page(items, limit):\n"
            "    limit = max(0, limit)\n"
            "    return items[:limit]\n"
        ),
        low_content=(
            "def page(items, limit, offset=0):\n"
            "    return items[offset:offset + limit]\n"
        ),
        high_content=(
            "def page(items, limit, offset=0):\n"
            "    limit = max(0, limit)\n"
            "    return items[offset:offset + limit]\n"
        ),
        low_intent="Add an optional starting offset to page slicing.",
        high_intent="Complete offset pagination with non-negative limits.",
        low_reasoning=(
            "The starting offset is applied to both slice bounds so page width remains stable."
        ),
        high_reasoning=(
            "Clamping the limit before calculating slice bounds prevents negative-width pages."
        ),
        required_substrings=("max(0, limit)", "offset:offset + limit"),
        symbols=frozenset({"page"}),
    ),
)


PADDING_TEXT = (
    "documentation packaging release notes example fixtures unrelated module license "
    "formatting changelog setup metadata helper configuration benchmark history"
)

STAGE_C_CONDITIONS = (
    PayloadCondition.P0,
    PayloadCondition.P1,
    PayloadCondition.P2,
    PayloadCondition.P3,
    PayloadCondition.P4,
    PayloadCondition.P5,
    PayloadCondition.P5_ORACLE,
    PayloadCondition.P1_PAD,
    PayloadCondition.ADAPTIVE,
)


@dataclass(frozen=True)
class FrozenActionPolicy:
    predictions: dict[str, PolicyPrediction]

    def predict(self, episode: ConflictEpisode, seed: int) -> PolicyPrediction:
        del seed
        return self.predictions[episode.episode_id]


def _with_revision_history(
    content: str, scenario: Scenario, k: int
) -> tuple[str, dict[str, int]]:
    prefix = f"_{scenario.name.upper()}_REVISION_"
    assignments = {f"{prefix}{index}": index for index in range(1, k + 1)}
    history = "\n".join(f"{name} = {value}" for name, value in assignments.items())
    return f"{content.rstrip()}\n\n{history}\n", assignments


def build_crossover_episodes(
    staleness_levels: tuple[int, ...] = tuple(range(1, 17)),
) -> list[ConflictEpisode]:
    episodes: list[ConflictEpisode] = []
    for scenario_index, scenario in enumerate(SCENARIOS):
        for k in staleness_levels:
            high = k >= scenario.switch_k
            correct_action = scenario.high_action if high else RecoveryAction.ADAPT
            current_content, protected_assignments = _with_revision_history(
                scenario.high_content if high else scenario.low_content, scenario, k
            )
            if high and correct_action == RecoveryAction.ABANDON:
                hint = "The assignment is already complete; abandon the stale patch."
            elif high:
                hint = "Do not write; escalate the contract disagreement to the manager."
            else:
                hint = "Adapt the proposed behavior onto the current implementation."

            episodes.append(
                ConflictEpisode(
                    episode_id=f"{scenario.name}-k{k}",
                    repo="leakage-safe-crossover-corpus",
                    losing_agent_id="engineer-A",
                    winning_agent_id="engineer-B",
                    file_path=scenario.file_path,
                    base_content=scenario.base_content,
                    current_content=current_content,
                    proposed_content=scenario.proposed_content,
                    unified_diff=make_unified_diff(
                        scenario.file_path, scenario.base_content, current_content
                    ),
                    stale_dependencies=(
                        StaleDependency(
                            path=scenario.file_path,
                            expected_version=1,
                            current_version=1 + k,
                            changed_by="engineer-B",
                        ),
                    ),
                    staleness=measure_staleness(
                        read_at=100.0,
                        refused_at=100.0 + 12 * k + scenario_index,
                        intervening_writes=k,
                        base_content=scenario.base_content,
                        current_content=current_content,
                        referenced_symbols=scenario.symbols,
                        changed_symbols=scenario.symbols,
                        tokens_since_read=180 * k + 25 * scenario_index,
                        tool_calls_since_read=2 * k + scenario_index % 2,
                    ),
                    winner_intent=(scenario.high_intent if high else scenario.low_intent),
                    winner_reasoning=(
                        scenario.high_reasoning if high else scenario.low_reasoning
                    ),
                    winner_task=(scenario.high_intent if high else scenario.low_intent),
                    winner_trajectory=tuple(
                        f"Applied intervening write {index + 1} of {k}"
                        for index in range(min(k, 5))
                    ),
                    recommended_action=correct_action,
                    refinement_hint=hint,
                    correct_action=correct_action,
                    padding_text=PADDING_TEXT,
                    metadata={
                        "scenario": scenario.name,
                        "switch_k": scenario.switch_k,
                        "losing_agent_task": scenario.losing_task,
                        "required_substrings": list(scenario.required_substrings),
                        "forbidden_substrings": [],
                        "protected_assignments": protected_assignments,
                        "validator": scenario.name,
                    },
                )
            )
    return episodes


def parse_staleness_levels(specification: str) -> tuple[int, ...]:
    levels: set[int] = set()
    for part in specification.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise ValueError(f"invalid staleness range: {item}")
            levels.update(range(start, end + 1))
        else:
            levels.add(int(item))
    if not levels or min(levels) < 1:
        raise ValueError("staleness levels must be positive integers")
    return tuple(sorted(levels))


def audit_p3_leakage(
    episodes: list[ConflictEpisode], renderer: PayloadRenderer
) -> dict[str, object]:
    route_cue = re.compile(
        r"\b(adapt|abandon|escalate|queue|serialize|rebase)\b|correct recovery",
        re.IGNORECASE,
    )
    directive_violations = [
        episode.episode_id
        for episode in episodes
        if route_cue.search(episode.winner_reasoning)
    ]
    forbidden_prompt_fields: dict[str, list[str]] = {}
    oracle_hint_violations: list[str] = []
    for episode in episodes:
        payload = renderer.render(episode, PayloadCondition.P3)
        prompt = build_recovery_user_prompt(episode, payload)
        leaked_fields = [
            field
            for field in (
                "correct_action",
                "recommended_action",
                "required_substrings",
                "forbidden_substrings",
            )
            if field in prompt
        ]
        if leaked_fields:
            forbidden_prompt_fields[episode.episode_id] = leaked_fields
        if episode.refinement_hint in prompt:
            oracle_hint_violations.append(episode.episode_id)
    validators = {str(item.metadata.get("validator", "")) for item in episodes}
    passed = not (
        directive_violations
        or forbidden_prompt_fields
        or oracle_hint_violations
        or "" in validators
    )
    return {
        "passed": passed,
        "episode_count": len(episodes),
        "p3_directive_cue_count": len(directive_violations),
        "p3_directive_cue_episodes": directive_violations,
        "forbidden_prompt_field_count": len(forbidden_prompt_fields),
        "forbidden_prompt_fields": forbidden_prompt_fields,
        "oracle_hint_in_p3_count": len(oracle_hint_violations),
        "oracle_hint_in_p3_episodes": oracle_hint_violations,
        "behavioral_validators": sorted(validators),
        "scorer": "isolated behavioral checks plus protected concurrent assignments",
    }


def audit_completed_run(
    records: list[dict[str, object]],
    episodes: list[ConflictEpisode],
    *,
    workers: int,
) -> dict[str, object]:
    episode_lookup = {item.episode_id: item for item in episodes}
    cue = re.compile(
        r"\b(adapt|abandon|escalate|queue|serialize|rebase)\b|correct recovery",
        re.IGNORECASE,
    )
    p3_records = [item for item in records if item["requested_condition"] == "P3"]
    directive_violations = []
    forbidden_field_violations = []
    for record in p3_records:
        request = record["request"]
        prompt = request["messages"][1]["content"]
        rationale = prompt.split("Winning edit reasoning (capped):", 1)[-1]
        if cue.search(rationale):
            directive_violations.append(record["episode_id"])
        if any(
            field in prompt
            for field in (
                "correct_action",
                "recommended_action",
                "required_substrings",
                "forbidden_substrings",
            )
        ):
            forbidden_field_violations.append(record["episode_id"])

    adapt_records = [
        item for item in records if item.get("parsed", {}).get("action") == "adapt"
    ]

    def score_matches(record: dict[str, object]) -> bool:
        parsed = record["parsed"]
        actual = validate_revision(
            episode_lookup[str(record["episode_id"])],
            str(parsed.get("revised_content", "")),
        )
        return actual == bool(record["mechanical_revision_valid"])

    with ThreadPoolExecutor(max_workers=workers) as executor:
        score_mismatches = sum(
            not matched for matched in executor.map(score_matches, adapt_records)
        )
    invalid_by_condition = Counter(
        str(item["requested_condition"]) for item in records if "error" in item
    )
    passed = not directive_violations and not forbidden_field_violations and not score_mismatches
    return {
        "passed": passed,
        "p3_prompts_audited": len(p3_records),
        "p3_directive_cue_count": len(directive_violations),
        "forbidden_prompt_field_count": len(forbidden_field_violations),
        "adapt_revisions_rescored": len(adapt_records),
        "logged_score_mismatches": score_mismatches,
        "invalid_recovery_responses": dict(sorted(invalid_by_condition.items())),
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _run_concurrent(
    *,
    runner: ReplayRunner,
    episodes: list[ConflictEpisode],
    conditions: tuple[PayloadCondition, ...],
    seeds: tuple[int, ...],
    workers: int,
) -> list[ReplayResult]:
    jobs = [
        (episode, condition, seed)
        for episode in episodes
        for condition in conditions
        for seed in seeds
    ]
    results: list[ReplayResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(runner.run, episode, condition, seed=seed): (
                episode.episode_id,
                condition,
                seed,
            )
            for episode, condition, seed in jobs
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if completed % 100 == 0 or completed == len(jobs):
                print(f"Completed {completed}/{len(jobs)} model continuations", flush=True)
    results.sort(
        key=lambda item: (
            item.edit_distance_writes,
            item.episode_id,
            item.requested_condition.value,
            item.seed,
        )
    )
    return results


def _predict_policy_actions(
    *,
    policy: OpenAICompatibleActionPolicy,
    episodes: list[ConflictEpisode],
    seed: int,
    workers: int,
) -> dict[str, PolicyPrediction]:
    predictions: dict[str, PolicyPrediction] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(policy.predict, episode, seed): episode.episode_id
            for episode in episodes
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            predictions[futures[future]] = future.result()
            if completed % 20 == 0 or completed == len(futures):
                print(f"Completed {completed}/{len(futures)} policy predictions", flush=True)
    return predictions


def _by_k_strategy(results: list[ReplayResult]) -> list[dict[str, object]]:
    groups: dict[tuple[int, PayloadCondition], list[ReplayResult]] = defaultdict(list)
    for item in results:
        groups[(item.edit_distance_writes, item.requested_condition)].append(item)
    rows: list[dict[str, object]] = []
    for (k, condition), cell in sorted(
        groups.items(), key=lambda pair: (pair[0][0], pair[0][1].value)
    ):
        rows.append(
            {
                "k": k,
                "condition": condition.value,
                "n": len(cell),
                "recovery_success_rate": mean(item.recovery_success for item in cell),
                "action_accuracy": mean(item.action_correct for item in cell),
                "mean_payload_tokens_proxy": mean(item.payload_tokens for item in cell),
                "mean_prompt_tokens": mean(item.model_prompt_tokens for item in cell),
                "mean_completion_tokens": mean(
                    item.model_completion_tokens for item in cell
                ),
                "mean_total_tokens": mean(item.recovery_tokens for item in cell),
                "policy_action_accuracy": (
                    mean(
                        item.policy_action_correct
                        for item in cell
                        if item.policy_action_correct is not None
                    )
                    if any(item.policy_action_correct is not None for item in cell)
                    else ""
                ),
                "mean_policy_tokens": mean(
                    item.policy_prompt_tokens + item.policy_completion_tokens
                    for item in cell
                ),
                "mean_end_to_end_tokens": mean(
                    item.recovery_tokens
                    + item.policy_prompt_tokens
                    + item.policy_completion_tokens
                    for item in cell
                ),
            }
        )
    return rows


def _by_action_strategy(results: list[ReplayResult]) -> list[dict[str, object]]:
    groups: dict[tuple[RecoveryAction, PayloadCondition], list[ReplayResult]] = defaultdict(list)
    for item in results:
        groups[(item.correct_action, item.requested_condition)].append(item)
    return [
        {
            "correct_action": action.value,
            "condition": condition.value,
            "n": len(cell),
            "recovery_success_rate": mean(item.recovery_success for item in cell),
            "action_accuracy": mean(item.action_correct for item in cell),
        }
        for (action, condition), cell in sorted(
            groups.items(), key=lambda pair: (pair[0][0].value, pair[0][1].value)
        )
    ]


def _policy_accuracy(
    episodes: list[ConflictEpisode], predictions: dict[str, PolicyPrediction]
) -> list[dict[str, object]]:
    groups: dict[str, list[ConflictEpisode]] = defaultdict(list)
    groups["overall"] = episodes
    for episode in episodes:
        groups[episode.correct_action.value].append(episode)
    rows: list[dict[str, object]] = []
    for label, group in groups.items():
        rows.append(
            {
                "correct_action_group": label,
                "n": len(group),
                "policy_action_accuracy": mean(
                    predictions[item.episode_id].action == item.correct_action
                    for item in group
                ),
                **{
                    f"predicted_{action.value}": sum(
                        predictions[item.episode_id].action == action for item in group
                    )
                    for action in RecoveryAction
                },
            }
        )
    return rows


def _cluster_statistics(
    *,
    baseline_items: list[ReplayResult],
    lookup: dict[tuple[str, int, PayloadCondition], ReplayResult],
    comparator: PayloadCondition,
    seed: int,
    randomization_samples: int = 10000,
) -> tuple[float, float, float, int, float, int, int]:
    clusters: dict[str, list[float]] = defaultdict(list)
    for item in baseline_items:
        difference = float(
            lookup[(item.episode_id, item.seed, comparator)].recovery_success
        ) - float(item.recovery_success)
        clusters[item.episode_id].append(difference)
    cluster_effects = [mean(values) for values in clusters.values()]
    lower, upper = _bootstrap_interval(cluster_effects, seed=seed)
    observed = abs(mean(cluster_effects))
    generator = random.Random(seed + 1)
    as_extreme = sum(
        abs(mean(value * generator.choice((-1, 1)) for value in cluster_effects))
        >= observed
        for _ in range(randomization_samples)
    )
    differences = [value for values in clusters.values() for value in values]
    gains = sum(value > 0 for value in differences)
    losses = sum(value < 0 for value in differences)
    return (
        mean(cluster_effects),
        lower,
        upper,
        len(cluster_effects),
        (as_extreme + 1) / (randomization_samples + 1)
        if randomization_samples
        else float("nan"),
        gains,
        losses,
    )


def _contrast_row(
    *,
    baseline_items: list[ReplayResult],
    lookup: dict[tuple[str, int, PayloadCondition], ReplayResult],
    comparator: PayloadCondition,
    stratum_type: str,
    stratum: str,
) -> dict[str, object]:
    seed = 20260909 + sum(
        map(ord, f"{comparator.value}:{stratum_type}:{stratum}")
    )
    effect, lower, upper, cluster_count, p_value, gains, losses = _cluster_statistics(
        baseline_items=baseline_items,
        lookup=lookup,
        comparator=comparator,
        seed=seed,
    )
    return {
        "comparator": comparator.value,
        "baseline": PayloadCondition.P1.value,
        "stratum_type": stratum_type,
        "stratum": stratum,
        "n_pairs": len(baseline_items),
        "n_episode_clusters": cluster_count,
        "paired_success_difference": effect,
        "bootstrap_95_low": lower,
        "bootstrap_95_high": upper,
        "discordant_gains": gains,
        "discordant_losses": losses,
        "cluster_randomization_p": p_value,
    }


def _robustness_contrasts(results: list[ReplayResult]) -> list[dict[str, object]]:
    lookup = {
        (item.episode_id, item.seed, item.requested_condition): item
        for item in results
    }
    baseline = [
        item for item in results if item.requested_condition == PayloadCondition.P1
    ]
    comparators = sorted(
        {item.requested_condition for item in results} - {PayloadCondition.P1},
        key=lambda item: item.value,
    )
    rows = [
        _contrast_row(
            baseline_items=baseline,
            lookup=lookup,
            comparator=comparator,
            stratum_type="overall",
            stratum="all",
        )
        for comparator in comparators
    ]
    levels = sorted({item.edit_distance_writes for item in baseline})
    bands = [levels[index : index + 4] for index in range(0, len(levels), 4)]
    for band in bands:
        rows.append(
            _contrast_row(
                baseline_items=[
                    item for item in baseline if item.edit_distance_writes in band
                ],
                lookup=lookup,
                comparator=PayloadCondition.P3,
                stratum_type="k_band",
                stratum=f"k{band[0]}-{band[-1]}",
            )
        )
    for action in sorted({item.correct_action for item in baseline}, key=lambda item: item.value):
        rows.append(
            _contrast_row(
                baseline_items=[item for item in baseline if item.correct_action == action],
                lookup=lookup,
                comparator=PayloadCondition.P3,
                stratum_type="correct_action",
                stratum=action.value,
            )
        )
        for band in bands:
            cell = [
                item
                for item in baseline
                if item.correct_action == action and item.edit_distance_writes in band
            ]
            if cell:
                rows.append(
                    _contrast_row(
                        baseline_items=cell,
                        lookup=lookup,
                        comparator=PayloadCondition.P3,
                        stratum_type="action_by_k_band",
                        stratum=f"{action.value}:k{band[0]}-{band[-1]}",
                    )
                )
    return rows


def _bootstrap_interval(
    values: list[float], *, samples: int = 4000, seed: int = 20260908
) -> tuple[float, float]:
    generator = random.Random(seed)
    estimates = sorted(
        mean(generator.choice(values) for _ in values) for _ in range(samples)
    )
    return estimates[int(0.025 * samples)], estimates[int(0.975 * samples)]


def _paired_advantages(
    results: list[ReplayResult], baseline: PayloadCondition = PayloadCondition.P1
) -> list[dict[str, object]]:
    lookup = {
        (item.episode_id, item.seed, item.requested_condition): item
        for item in results
    }
    comparators = sorted(
        {item.requested_condition for item in results} - {baseline},
        key=lambda item: item.value,
    )
    rows: list[dict[str, object]] = []
    levels = sorted({item.edit_distance_writes for item in results})
    for k in levels:
        baseline_items = [
            item
            for item in results
            if item.edit_distance_writes == k
            and item.requested_condition == baseline
        ]
        for comparator in comparators:
            effect, lower, upper, cluster_count, _, _, _ = _cluster_statistics(
                baseline_items=baseline_items,
                lookup=lookup,
                comparator=comparator,
                seed=20260908 + k + sum(map(ord, comparator.value)),
                randomization_samples=0,
            )
            rows.append(
                {
                    "k": k,
                    "comparator": comparator.value,
                    "baseline": baseline.value,
                    "n_pairs": len(baseline_items),
                    "n_episode_clusters": cluster_count,
                    "paired_success_difference": effect,
                    "bootstrap_95_low": lower,
                    "bootstrap_95_high": upper,
                }
            )
    return rows


def _threshold_sweep(
    results: list[ReplayResult], rich_conditions: tuple[PayloadCondition, ...]
) -> list[dict[str, object]]:
    lookup = {
        (item.episode_id, item.seed, item.requested_condition): item
        for item in results
    }
    baseline_items = [
        item for item in results if item.requested_condition == PayloadCondition.P1
    ]
    levels = sorted({item.edit_distance_writes for item in results})
    rows: list[dict[str, object]] = []
    for rich in rich_conditions:
        for threshold in range(levels[0], levels[-1] + 2):
            selected = [
                (
                    item
                    if item.edit_distance_writes < threshold
                    else lookup[(item.episode_id, item.seed, rich)]
                )
                for item in baseline_items
            ]
            rows.append(
                {
                    "rich_condition": rich.value,
                    "threshold_k": threshold,
                    "n": len(selected),
                    "recovery_success_rate": mean(
                        item.recovery_success for item in selected
                    ),
                    "mean_payload_tokens_proxy": mean(
                        item.payload_tokens for item in selected
                    ),
                    "mean_total_tokens": mean(item.recovery_tokens for item in selected),
                }
            )
    return rows


def _first_consistent_positive(
    paired_rows: list[dict[str, object]], comparator: PayloadCondition
) -> int | None:
    effects = {
        int(row["k"]): float(row["paired_success_difference"])
        for row in paired_rows
        if row["comparator"] == comparator.value
    }
    levels = sorted(effects)
    for index, k in enumerate(levels):
        if effects[k] > 0 and all(effects[later] >= 0 for later in levels[index:]):
            return k
    return None


def _first_interval_above_zero(
    paired_rows: list[dict[str, object]], comparator: PayloadCondition
) -> int | None:
    for row in paired_rows:
        if (
            row["comparator"] == comparator.value
            and float(row["bootstrap_95_low"]) > 0
        ):
            return int(row["k"])
    return None


def _best_threshold(
    threshold_rows: list[dict[str, object]], rich: PayloadCondition
) -> dict[str, object]:
    candidates = [
        row for row in threshold_rows if row["rich_condition"] == rich.value
    ]
    return min(
        candidates,
        key=lambda row: (
            -float(row["recovery_success_rate"]),
            float(row["mean_payload_tokens_proxy"]),
        ),
    )


def _mean_optional(rows: list[dict[str, object]], key: str) -> str:
    values = [float(row[key]) for row in rows if row[key] != ""]
    return f"{mean(values):.1%}" if values else "—"


def _write_report(
    path: Path,
    *,
    config: dict[str, object],
    by_k_rows: list[dict[str, object]],
    paired_rows: list[dict[str, object]],
    threshold_rows: list[dict[str, object]],
    policy_rows: list[dict[str, object]],
    robustness_rows: list[dict[str, object]],
    results: list[ReplayResult],
    invalid_responses: int,
    invalid_policy_responses: int,
) -> None:
    cell = {
        (int(row["k"]), str(row["condition"])): row for row in by_k_rows
    }
    p3_crosspoint = _first_consistent_positive(paired_rows, PayloadCondition.P3)
    p5_crosspoint = _first_consistent_positive(paired_rows, PayloadCondition.P5)
    p3_interval_crosspoint = _first_interval_above_zero(
        paired_rows, PayloadCondition.P3
    )
    p5_interval_crosspoint = _first_interval_above_zero(
        paired_rows, PayloadCondition.P5
    )
    best_p3 = _best_threshold(threshold_rows, PayloadCondition.P3)
    best_p5 = _best_threshold(threshold_rows, PayloadCondition.P5)
    p5_results = [
        item for item in results if item.requested_condition == PayloadCondition.P5
    ]
    correct_routes = [item for item in p5_results if item.policy_action_correct]
    wrong_routes = [item for item in p5_results if item.policy_action_correct is False]
    directive_adherence = mean(
        item.action == item.policy_action for item in p5_results
    )
    correct_route_success = (
        f"{mean(item.recovery_success for item in correct_routes):.1%}"
        if correct_routes
        else "not observed"
    )
    wrong_route_success = (
        f"{mean(item.recovery_success for item in wrong_routes):.1%}"
        if wrong_routes
        else "not observed"
    )
    overall_success = {
        condition: mean(
            item.recovery_success
            for item in results
            if item.requested_condition == condition
        )
        for condition in STAGE_C_CONDITIONS
    }
    policy_by_group = {str(row["correct_action_group"]): row for row in policy_rows}
    robustness = {
        (str(row["comparator"]), str(row["stratum_type"]), str(row["stratum"])): row
        for row in robustness_rows
    }
    p3_overall = robustness[(PayloadCondition.P3.value, "overall", "all")]
    lines = [
        "# Qwen staleness-strategy crossover experiment",
        "",
        f"Model: `{config['model']}`",
        "",
        f"Design: {config['scenario_count']} paired scenario families × "
        f"{len(config['staleness_levels'])} staleness levels × "
        f"{len(config['conditions'])} strategies × {len(config['seeds'])} seeds = "
        f"{config['continuation_count']} continuations.",
        "",
        "## Success curves",
        "",
        "Each cell contains scenario families × seeds observations. Success requires the correct",
        "coordination action and, for `adapt`, a syntactically valid revision satisfying the",
        "behavioral validator while preserving every concurrent revision marker.",
        "",
        "| k | P0 | P1 | P2 | P3 | P4 | P5 predicted | P5 oracle | P1-pad | "
        "Adaptive | P3−P1 | P5−P1 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k in config["staleness_levels"]:
        rates = {
            condition.value: float(cell[(k, condition.value)]["recovery_success_rate"])
            for condition in STAGE_C_CONDITIONS
        }
        p3_difference = rates[PayloadCondition.P3.value] - rates[PayloadCondition.P1.value]
        lines.append(
            f"| {k} | {rates['P0']:.0%} | {rates['P1']:.0%} | {rates['P2']:.0%} | "
            f"{rates['P3']:.0%} | {rates['P4']:.0%} | {rates['P5']:.0%} | "
            f"{rates['P5-oracle']:.0%} | {rates['P1-pad']:.0%} | "
            f"{rates['adaptive']:.0%} | {p3_difference:+.0%} | "
            f"{rates['P5'] - rates['P1']:+.0%} |"
        )
    lines.extend(
        [
            "",
            "## Overall strategy performance",
            "",
            "| Strategy | Success | Action accuracy | Policy accuracy | Payload tokens | "
            "Recovery tokens | Policy tokens | End-to-end tokens |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for condition in STAGE_C_CONDITIONS:
        condition_rows = [
            row for row in by_k_rows if row["condition"] == condition.value
        ]
        lines.append(
            f"| {condition.value} | "
            f"{mean(float(row['recovery_success_rate']) for row in condition_rows):.1%} | "
            f"{mean(float(row['action_accuracy']) for row in condition_rows):.1%} | "
            f"{_mean_optional(condition_rows, 'policy_action_accuracy')} | "
            f"{mean(float(row['mean_payload_tokens_proxy']) for row in condition_rows):.1f} | "
            f"{mean(float(row['mean_total_tokens']) for row in condition_rows):.1f} | "
            f"{mean(float(row['mean_policy_tokens']) for row in condition_rows):.1f} | "
            f"{mean(float(row['mean_end_to_end_tokens']) for row in condition_rows):.1f} |"
        )
    lines.extend(
        [
            "",
            "## P3 leakage-safe result",
            "",
            f"P3 improved over P1 by "
            f"{float(p3_overall['paired_success_difference']):+.1%} overall "
            f"(95% paired bootstrap interval "
            f"[{float(p3_overall['bootstrap_95_low']):+.1%}, "
            f"{float(p3_overall['bootstrap_95_high']):+.1%}]; episode-clustered "
            f"randomization p={float(p3_overall['cluster_randomization_p']):.3f}). "
            "This does not establish an "
            "overall P3 advantage.",
            "",
            "| Staleness band | P3−P1 | 95% bootstrap interval |",
            "|---|---:|---:|",
            *[
                f"| {row['stratum']} | "
                f"{float(row['paired_success_difference']):+.1%} | "
                f"[{float(row['bootstrap_95_low']):+.1%}, "
                f"{float(row['bootstrap_95_high']):+.1%}] |"
                for row in robustness_rows
                if row["comparator"] == PayloadCondition.P3.value
                and row["stratum_type"] == "k_band"
            ],
            "",
            f"More payload was not monotonically better: P4 achieved "
            f"{overall_success[PayloadCondition.P4]:.1%} success and P1-pad achieved "
            f"{overall_success[PayloadCondition.P1_PAD]:.1%}, versus "
            f"{overall_success[PayloadCondition.P1]:.1%} for P1.",
            "",
            "| Correct action | P3−P1 | 95% bootstrap interval |",
            "|---|---:|---:|",
            *[
                f"| {row['stratum']} | "
                f"{float(row['paired_success_difference']):+.1%} | "
                f"[{float(row['bootstrap_95_low']):+.1%}, "
                f"{float(row['bootstrap_95_high']):+.1%}] |"
                for row in robustness_rows
                if row["comparator"] == PayloadCondition.P3.value
                and row["stratum_type"] == "correct_action"
            ],
            "",
            "Action-stratified contrasts also fail to establish a universal P3 benefit; see "
            "`robustness_contrasts.csv` for action-by-k-band reversals.",
            "",
            "## P5 interpretation",
            "",
            f"Policy-predicted P5 achieved {overall_success[PayloadCondition.P5]:.1%} "
            f"success, versus {overall_success[PayloadCondition.P3]:.1%} for P3 and "
            f"{overall_success[PayloadCondition.P5_ORACLE]:.1%} for P5-oracle. The oracle "
            "arm measures the upper bound from a correct compact direction; its gap from P5 "
            "contains routing and directive-adherence errors.",
            "",
            f"The router was correct on "
            f"{float(policy_by_group['adapt']['policy_action_accuracy']):.1%} of adapt cases, "
            f"{float(policy_by_group['abandon']['policy_action_accuracy']):.1%} of abandon "
            f"cases, and {float(policy_by_group['escalate']['policy_action_accuracy']):.1%} "
            "of escalate cases.",
            "",
            "## Estimated crossover",
            "",
            f"- First consistently positive P3−P1 level: {p3_crosspoint or 'not observed'}.",
            f"- First consistently positive P5−P1 level: {p5_crosspoint or 'not observed'}.",
            f"- First P3−P1 bootstrap interval fully above zero: "
            f"{p3_interval_crosspoint or 'not observed'}.",
            f"- First P5−P1 bootstrap interval fully above zero: "
            f"{p5_interval_crosspoint or 'not observed'}.",
            f"- Best exploratory P1→P3 threshold: k={best_p3['threshold_k']} "
            f"({float(best_p3['recovery_success_rate']):.1%} success, "
            f"{float(best_p3['mean_payload_tokens_proxy']):.1f} mean payload tokens).",
            f"- Best exploratory P1→P5 threshold: k={best_p5['threshold_k']} "
            f"({float(best_p5['recovery_success_rate']):.1%} success, "
            f"{float(best_p5['mean_payload_tokens_proxy']):.1f} mean payload tokens).",
            "",
            "The threshold sweep maximizes observed success and breaks ties using lower payload",
            "cost. It is exploratory and fitted on the same controlled corpus; it is not a",
            "held-out deployment threshold.",
            "",
            "## Routing policy",
            "",
            "P5 is generated in two stages. A frozen Qwen policy first predicts a route from",
            "only the losing task, the base/proposed/current files, the diff, and observed k.",
            "The recovery continuation then receives P1 plus that predicted route and hint.",
            "`correct_action`, winner intent, and winner reasoning are withheld from the router.",
            "",
            f"The recovery agent followed the predicted route in {directive_adherence:.1%} of "
            "P5 continuations. Recovery succeeded in "
            f"{correct_route_success} when the route was correct and "
            f"{wrong_route_success} when it was wrong.",
            "",
            "| Ground-truth group | n | Router accuracy |",
            "|---|---:|---:|",
            *[
                f"| {row['correct_action_group']} | {row['n']} | "
                f"{float(row['policy_action_accuracy']):.1%} |"
                for row in policy_rows
            ],
            "",
            "## Validity notes",
            "",
            f"- Pre-run P3 leakage audit passed: {config['leakage_audit_passed']}.",
            f"- Post-run prompt/rescoring audit passed: {config['postrun_audit_passed']}.",
            f"- Invalid or unparsable model responses: {invalid_responses}.",
            f"- Invalid or unparsable policy responses: {invalid_policy_responses}.",
            "- P5 is policy-predicted; P5-oracle is retained only as an explicit upper bound.",
            "- End-to-end P5 tokens include the extra routing call. P3's winner reasoning was "
            "already present in the fixture, so its original generation cost is not measured.",
            "- Winner reasoning describes the winning edit without recovery-action words; the "
            "pre-run audit enforces this constraint.",
            "- Correct actions switch at fixture-specific k values, so action mix and staleness "
            "are coupled. The observed crossover is a mechanism demonstration, not a causal "
            "estimate from natural conflicts.",
            "- The corpus contains adapt, abandon, and escalate labels, but no ground-truth "
            "queue or serialize episodes.",
            "- This paired controlled study improves on the four-case pilot, but it is still not",
            "  a natural-refusal Commit0 corpus or an end-to-end STORM pass-rate experiment.",
            "- Bootstrap intervals resample episode-level paired effects while retaining all "
            "seeds inside each episode cluster; they quantify this corpus only.",
            "",
            "## Artifacts",
            "",
            "- `config.json`: model and experimental design",
            "- `leakage_audit.json`: pre-run directive and evaluator leakage checks",
            "- `implementation_audit.md`: diagnosis of the superseded 100% P3 result",
            "- `postrun_audit.json`: raw-prompt and independent rescoring checks",
            "- `run_command.sh`: complete rerun command",
            f"- `episodes.jsonl`: {config['episode_count']} replayable paired episodes",
            "- `replay_results.csv`: all model-level outcomes",
            "- `by_k_strategy.csv`: success and token curves",
            "- `by_action_strategy.csv`: performance stratified by correct action",
            "- `paired_advantage.csv`: paired strategy-minus-P1 effects with bootstrap intervals",
            "- `robustness_contrasts.csv`: overall, k-band, and action-stratified contrasts",
            "- `threshold_sweep.csv`: P1→P3/P5 candidate thresholds",
            "- `policy_accuracy.csv`: router accuracy and action distribution",
            "- `policy_responses.jsonl`: raw policy requests, responses, and predictions",
            "- `model_responses.jsonl`: raw requests, responses, and parsed decisions",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_rerun_script(
    output_dir: Path, project_dir: Path, config: dict[str, object]
) -> None:
    script = output_dir / "run_command.sh"
    content = f"""#!/usr/bin/env bash
# Reproduce this complete experiment, including starting and stopping local vLLM.
set -euo pipefail
cd {shlex.quote(str(project_dir))}
OUTPUT_DIR={shlex.quote(str(output_dir))} \\
MODEL_PATH={shlex.quote(str(config['model_path']))} \\
SERVED_MODEL_NAME={shlex.quote(str(config['model']))} \\
SEEDS={shlex.quote(','.join(str(item) for item in config['seeds']))} \\
STALENESS_LEVELS={shlex.quote(','.join(str(item) for item in config['staleness_levels']))} \\
TEMPERATURE={shlex.quote(str(config['temperature']))} \\
TOP_P={shlex.quote(str(config['top_p']))} \\
POLICY_TEMPERATURE={shlex.quote(str(config['policy_temperature']))} \\
POLICY_SEED={shlex.quote(str(config['policy_seed']))} \\
POLICY_MAX_TOKENS={shlex.quote(str(config['policy_max_tokens']))} \\
CONCURRENCY={shlex.quote(str(config['workers']))} \\
ADAPTIVE_THRESHOLD={shlex.quote(str(config['adaptive_threshold']))} \\
MAX_TOKENS={shlex.quote(str(config['max_tokens']))} \\
bash scripts/run_crossover_experiment.sh
"""
    script.write_text(content, encoding="utf-8")
    script.chmod(0o775)


def run_experiment(args: argparse.Namespace) -> list[ReplayResult]:
    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    staleness_levels = parse_staleness_levels(args.staleness_levels)
    episodes = build_crossover_episodes(staleness_levels)
    conditions = tuple(PayloadCondition(item) for item in args.conditions.split(","))
    seeds = tuple(int(item) for item in args.seeds.split(","))
    continuation_count = len(episodes) * len(conditions) * len(seeds)
    leakage_audit = audit_p3_leakage(episodes, PayloadRenderer())
    (output_dir / "leakage_audit.json").write_text(
        json.dumps(leakage_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not leakage_audit["passed"]:
        raise ValueError(f"P3 leakage audit failed; inspect {output_dir / 'leakage_audit.json'}")
    config: dict[str, object] = {
        "created_at": datetime.now(UTC).isoformat(),
        "endpoint": args.endpoint,
        "model": args.model,
        "model_path": args.model_path,
        "scenario_count": len(SCENARIOS),
        "episode_count": len(episodes),
        "staleness_levels": list(staleness_levels),
        "conditions": [item.value for item in conditions],
        "seeds": list(seeds),
        "temperature": args.temperature,
        "top_p": args.top_p,
        "policy_temperature": args.policy_temperature,
        "policy_seed": args.policy_seed,
        "policy_max_tokens": args.policy_max_tokens,
        "policy_prediction_count": len(episodes),
        "workers": args.workers,
        "adaptive_threshold": args.adaptive_threshold,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
        "continuation_count": continuation_count,
        "leakage_audit_passed": leakage_audit["passed"],
    }
    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    EpisodeLog(output_dir / "episodes.jsonl").write(episodes)

    action_policy = OpenAICompatibleActionPolicy(
        args.endpoint,
        args.model,
        timeout=args.timeout,
        max_tokens=args.policy_max_tokens,
        temperature=args.policy_temperature,
        top_p=args.top_p,
    )
    predictions = _predict_policy_actions(
        policy=action_policy,
        episodes=episodes,
        seed=args.policy_seed,
        workers=args.workers,
    )
    with (output_dir / "policy_responses.jsonl").open("w", encoding="utf-8") as stream:
        for record in sorted(action_policy.records, key=lambda item: item["episode_id"]):
            json.dump(record, stream, sort_keys=True)
            stream.write("\n")

    backend = OpenAICompatibleRecoveryBackend(
        args.endpoint,
        args.model,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
    )
    renderer = PayloadRenderer(
        adaptive_policy=AdaptivePayloadPolicy(threshold_writes=args.adaptive_threshold),
        action_policy=FrozenActionPolicy(predictions),
    )
    results = _run_concurrent(
        runner=ReplayRunner(backend, renderer),
        episodes=episodes,
        conditions=conditions,
        seeds=seeds,
        workers=args.workers,
    )
    _write_csv(output_dir / "replay_results.csv", [item.to_dict() for item in results])
    with (output_dir / "model_responses.jsonl").open("w", encoding="utf-8") as stream:
        for record in sorted(
            backend.records,
            key=lambda item: (
                item["episode_id"],
                item["requested_condition"],
                item["seed"],
            ),
        ):
            json.dump(record, stream, sort_keys=True)
            stream.write("\n")

    postrun_audit = audit_completed_run(
        backend.records, episodes, workers=args.workers
    )
    (output_dir / "postrun_audit.json").write_text(
        json.dumps(postrun_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not postrun_audit["passed"]:
        raise ValueError(
            f"post-run audit failed; inspect {output_dir / 'postrun_audit.json'}"
        )
    config["postrun_audit_passed"] = postrun_audit["passed"]
    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    by_k_rows = _by_k_strategy(results)
    paired_rows = _paired_advantages(results)
    threshold_rows = _threshold_sweep(
        results, (PayloadCondition.P3, PayloadCondition.P5)
    )
    policy_rows = _policy_accuracy(episodes, predictions)
    action_rows = _by_action_strategy(results)
    robustness_rows = _robustness_contrasts(results)
    _write_csv(output_dir / "by_k_strategy.csv", by_k_rows)
    _write_csv(output_dir / "paired_advantage.csv", paired_rows)
    _write_csv(output_dir / "threshold_sweep.csv", threshold_rows)
    _write_csv(output_dir / "policy_accuracy.csv", policy_rows)
    _write_csv(output_dir / "by_action_strategy.csv", action_rows)
    _write_csv(output_dir / "robustness_contrasts.csv", robustness_rows)
    _write_report(
        output_dir / "report.md",
        config=config,
        by_k_rows=by_k_rows,
        paired_rows=paired_rows,
        threshold_rows=threshold_rows,
        policy_rows=policy_rows,
        robustness_rows=robustness_rows,
        results=results,
        invalid_responses=sum("error" in record for record in backend.records),
        invalid_policy_responses=sum("error" in record for record in action_policy.records),
    )
    _write_rerun_script(output_dir, Path(__file__).resolve().parent.parent, config)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8102/v1")
    parser.add_argument("--model", default="qwen3.5-35b-a3b")
    parser.add_argument("--model-path", default="/shared/models/hf/Qwen3.5-35B-A3B")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("crossover_experiment_qwen35_leakage_safe_k16_20260909"),
    )
    parser.add_argument(
        "--conditions",
        default=",".join(item.value for item in STAGE_C_CONDITIONS),
    )
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--staleness-levels", default="1-16")
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--policy-temperature", type=float, default=0.0)
    parser.add_argument("--policy-seed", type=int, default=0)
    parser.add_argument("--policy-max-tokens", type=int, default=160)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--adaptive-threshold", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    required = set(STAGE_C_CONDITIONS)
    supplied = {PayloadCondition(item) for item in args.conditions.split(",")}
    if supplied != required:
        parser.error(
            "--conditions must contain P0-P5, P5-oracle, P1-pad, and adaptive"
        )
    results = run_experiment(args)
    successes = sum(item.recovery_success for item in results)
    print(
        f"Wrote {len(results)} continuations ({successes} successful) to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
