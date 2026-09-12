from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .episode_log import EpisodeLog
from .measurement import make_unified_diff, measure_staleness
from .models import (
    ConflictEpisode,
    PayloadCondition,
    RecoveryAction,
    RecoveryAttempt,
    ReplayResult,
    StaleDependency,
)
from .payloads import Payload
from .replay import ReplayRunner


PADDING_TEXT = (
    "repository setup packaging changelog documentation license fixtures examples "
    "release automation formatting configuration unrelated helper module"
)
CASE_STUDY_CONDITIONS = tuple(
    condition
    for condition in PayloadCondition
    if condition not in {PayloadCondition.P6, PayloadCondition.P7, PayloadCondition.P8}
)


class ControlledRecoveryBackend:
    """Deterministic mechanism check; this is not an LLM performance model."""

    decision_bearing = {
        PayloadCondition.P2,
        PayloadCondition.P3,
        PayloadCondition.P4,
        PayloadCondition.P5,
        PayloadCondition.P5_ORACLE,
        PayloadCondition.P6,
        PayloadCondition.P8,
    }

    def recover(
        self, episode: ConflictEpisode, payload: Payload, seed: int
    ) -> RecoveryAttempt:
        del seed
        selected = payload.selected_condition
        if selected == PayloadCondition.P0:
            return RecoveryAttempt(
                action=RecoveryAction.ADAPT,
                accepted_write=False,
                touched_tests_pass=False,
                repeat_refusal=True,
                recovery_tokens=260,
                recovery_tool_calls=4,
                notes="Bare refusal does not expose a fresh edit baseline.",
            )

        if episode.correct_action == RecoveryAction.ADAPT:
            return RecoveryAttempt(
                action=RecoveryAction.ADAPT,
                accepted_write=True,
                touched_tests_pass=True,
                repeat_refusal=False,
                recovery_tokens=120,
                recovery_tool_calls=2,
                notes="Current content and diff are sufficient for local adaptation.",
            )

        if selected in self.decision_bearing:
            return RecoveryAttempt(
                action=episode.correct_action,
                accepted_write=False,
                touched_tests_pass=True,
                repeat_refusal=False,
                recovery_tokens=(25 if episode.correct_action == RecoveryAction.ABANDON else 45),
                recovery_tool_calls=1,
                notes="Intent, reasoning, trajectory, or directive resolves the action ambiguity.",
            )

        return RecoveryAttempt(
            action=RecoveryAction.ADAPT,
            accepted_write=True,
            touched_tests_pass=False,
            repeat_refusal=episode.correct_action == RecoveryAction.ESCALATE,
            recovery_tokens=310,
            recovery_tool_calls=5,
            notes="Content-only feedback cannot resolve whether to adapt or stop.",
        )


def _episode(
    *,
    episode_id: str,
    file_path: str,
    base_content: str,
    current_content: str,
    proposed_content: str,
    writes: int,
    seconds: float,
    investment_tokens: int,
    investment_tool_calls: int,
    winner_intent: str,
    winner_reasoning: str,
    winner_task: str,
    winner_trajectory: tuple[str, ...],
    correct_action: RecoveryAction,
    refinement_hint: str,
    referenced_symbols: set[str],
    changed_symbols: set[str],
    losing_agent_task: str,
    required_substrings: tuple[str, ...] = (),
    forbidden_substrings: tuple[str, ...] = (),
) -> ConflictEpisode:
    return ConflictEpisode(
        episode_id=episode_id,
        repo="controlled-python-cases",
        losing_agent_id="engineer-A",
        winning_agent_id="engineer-B",
        file_path=file_path,
        base_content=base_content,
        current_content=current_content,
        proposed_content=proposed_content,
        unified_diff=make_unified_diff(file_path, base_content, current_content),
        stale_dependencies=(
            StaleDependency(
                path=file_path,
                expected_version=1,
                current_version=1 + writes,
                changed_by="engineer-B",
            ),
        ),
        staleness=measure_staleness(
            read_at=100.0,
            refused_at=100.0 + seconds,
            intervening_writes=writes,
            base_content=base_content,
            current_content=current_content,
            referenced_symbols=referenced_symbols,
            changed_symbols=changed_symbols,
            tokens_since_read=investment_tokens,
            tool_calls_since_read=investment_tool_calls,
        ),
        winner_intent=winner_intent,
        winner_reasoning=winner_reasoning,
        winner_task=winner_task,
        winner_trajectory=winner_trajectory,
        recommended_action=correct_action,
        refinement_hint=refinement_hint,
        correct_action=correct_action,
        padding_text=PADDING_TEXT,
        metadata={
            "case_type": correct_action.value,
            "losing_agent_task": losing_agent_task,
            "required_substrings": list(required_substrings),
            "forbidden_substrings": list(forbidden_substrings),
        },
    )


def build_controlled_episodes() -> list[ConflictEpisode]:
    return [
        _episode(
            episode_id="k1-local-validation",
            file_path="names.py",
            base_content=(
                "def normalize(name):\n"
                "    return name.strip()\n"
            ),
            current_content=(
                "def normalize(name):\n"
                "    if not isinstance(name, str):\n"
                "        raise TypeError('name must be text')\n"
                "    return name.strip()\n"
            ),
            proposed_content=(
                "def normalize(name):\n"
                "    return name.strip().lower()\n"
            ),
            writes=1,
            seconds=8,
            investment_tokens=140,
            investment_tool_calls=2,
            winner_intent="Validate input type without changing normalization semantics.",
            winner_reasoning=(
                "The public function currently assumes text and fails with an opaque attribute "
                "error for other inputs. Add an explicit type check while retaining the existing "
                "strip behavior so a concurrent lowercase normalization can be layered on safely."
            ),
            winner_task="Add defensive validation to normalize().",
            winner_trajectory=("Viewed names.py", "Added a type guard", "Ran names tests"),
            correct_action=RecoveryAction.ADAPT,
            refinement_hint="Rebase the lowercase change on the validated implementation.",
            referenced_symbols={"normalize"},
            changed_symbols={"normalize"},
            losing_agent_task="Make normalize() return lowercase text without losing validation.",
            required_substrings=("isinstance(name, str)", ".strip().lower()"),
        ),
        _episode(
            episode_id="k2-compatible-signature",
            file_path="formatting.py",
            base_content=(
                "def render(value):\n"
                "    return str(value)\n"
            ),
            current_content=(
                "def render(value, prefix=''):\n"
                "    text = str(value)\n"
                "    return prefix + text\n"
            ),
            proposed_content=(
                "def render(value):\n"
                "    return str(value).strip()\n"
            ),
            writes=2,
            seconds=24,
            investment_tokens=420,
            investment_tool_calls=4,
            winner_intent="Add an optional output prefix while preserving existing callers.",
            winner_reasoning=(
                "The new prefix argument has a default, so the existing one-argument interface "
                "remains compatible. Separating conversion from concatenation also leaves a clear "
                "place for the other agent's whitespace normalization before the prefix is added."
            ),
            winner_task="Support optional prefixes in render().",
            winner_trajectory=("Inspected callers", "Extended signature", "Ran formatting tests"),
            correct_action=RecoveryAction.ADAPT,
            refinement_hint="Apply stripping to text before prefix concatenation.",
            referenced_symbols={"render"},
            changed_symbols={"render"},
            losing_agent_task=(
                "Strip converted values while preserving the optional prefix feature."
            ),
            required_substrings=("prefix", ".strip()", "return prefix + text"),
        ),
        _episode(
            episode_id="k4-redundant-cache",
            file_path="cache.py",
            base_content=(
                "def build_cache(max_size):\n"
                "    raise NotImplementedError\n"
            ),
            current_content=(
                "def build_cache(max_size, ttl_seconds=60):\n"
                "    return {'max_size': max_size, 'ttl': ttl_seconds, 'items': {}}\n"
            ),
            proposed_content=(
                "def build_cache(max_size):\n"
                "    return {'capacity': max_size, 'data': {}}\n"
            ),
            writes=4,
            seconds=71,
            investment_tokens=1180,
            investment_tool_calls=9,
            winner_intent=(
                "Implement the shared cache constructor, including the required TTL contract."
            ),
            winner_reasoning=(
                "Callers and tests require max_size, ttl, and items keys. The optional TTL "
                "keeps old callers valid while satisfying expiration tests. A second "
                "constructor with capacity and data keys would duplicate the completed "
                "work and break consumers, so it should "
                "not be merged. The losing agent should stop this edit and move to another task."
            ),
            winner_task="Implement build_cache and its TTL behavior.",
            winner_trajectory=(
                "Inspected cache tests",
                "Implemented constructor",
                "Added expiration path",
                "Ran full cache suite",
            ),
            correct_action=RecoveryAction.ABANDON,
            refinement_hint="The assigned symbol is already complete; abandon this patch.",
            referenced_symbols={"build_cache"},
            changed_symbols={"build_cache"},
            losing_agent_task="Implement build_cache() without duplicating completed work.",
        ),
        _episode(
            episode_id="k8-security-invariant",
            file_path="auth.py",
            base_content=(
                "def authorize(user, scope):\n"
                "    if scope not in user.scopes:\n"
                "        raise PermissionError(scope)\n"
                "    return True\n"
            ),
            current_content=(
                "def authorize(user, scope, audit=None):\n"
                "    if audit is not None:\n"
                "        audit.record(user, scope)\n"
                "    return True\n"
            ),
            proposed_content=(
                "def authorize(user, scope):\n"
                "    allowed = scope in user.scopes\n"
                "    return allowed\n"
            ),
            writes=8,
            seconds=188,
            investment_tokens=2460,
            investment_tool_calls=17,
            winner_intent="Add authorization audit events and simplify the success path.",
            winner_reasoning=(
                "An audit hook was threaded through authorization and several callers. During that "
                "refactor the explicit scope rejection was removed to make the new audit "
                "tests pass, "
                "but this changes the security invariant. The two assignments now conflict at the "
                "contract level and a manager must decide whether rejection or audit behavior wins."
            ),
            winner_task="Add audit logging to the authorization flow.",
            winner_trajectory=(
                "Changed authorize signature",
                "Updated service callers",
                "Added audit recording",
                "Adjusted tests around the new path",
                "Observed disagreement with scope enforcement",
            ),
            correct_action=RecoveryAction.ESCALATE,
            refinement_hint="Do not overwrite; ask the manager to resolve the security contract.",
            referenced_symbols={"authorize", "PermissionError"},
            changed_symbols={"authorize", "PermissionError"},
            losing_agent_task=(
                "Preserve scope enforcement while coordinating with the audit refactor."
            ),
        ),
    ]


def _write_results(path: Path, results: list[ReplayResult]) -> None:
    rows = [result.to_dict() for result in results]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _summaries(results: list[ReplayResult]) -> list[dict[str, object]]:
    grouped: dict[PayloadCondition, list[ReplayResult]] = defaultdict(list)
    for result in results:
        grouped[result.requested_condition].append(result)
    rows: list[dict[str, object]] = []
    for condition in PayloadCondition:
        cell = grouped.get(condition, [])
        if not cell:
            continue
        rows.append(
            {
                "condition": condition.value,
                "episodes": len(cell),
                "recovery_success_rate": mean(item.recovery_success for item in cell),
                "action_accuracy": mean(item.action_correct for item in cell),
                "repeat_refusal_rate": mean(item.repeat_refusal for item in cell),
                "mean_payload_tokens": mean(item.payload_tokens for item in cell),
                "mean_recovery_tokens": mean(item.recovery_tokens for item in cell),
            }
        )
    return rows


def _write_summary(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _condition_at(
    results: list[ReplayResult], condition: PayloadCondition, writes: int
) -> ReplayResult:
    return next(
        item
        for item in results
        if item.requested_condition == condition and item.edit_distance_writes == writes
    )


def _write_report(
    path: Path, episodes: list[ConflictEpisode], results: list[ReplayResult]
) -> None:
    p3 = [item for item in results if item.requested_condition == PayloadCondition.P3]
    adaptive = [
        item for item in results if item.requested_condition == PayloadCondition.ADAPTIVE
    ]
    savings = 1 - mean(item.payload_tokens for item in adaptive) / mean(
        item.payload_tokens for item in p3
    )
    lines = [
        "# Controlled staleness-adaptive communication case studies",
        "",
        "> These are deterministic mechanism checks for the framework, not LLM or Commit0",
        "> evidence.",
        "> The recovery backend encodes only which payload families expose enough information to",
        "> choose the fixture's mechanically specified action.",
        "",
        "## Primary crossover check",
        "",
        "| k | Case | Correct action | P1 success | P3 success | "
        "Adaptive selection | Adaptive success |",
        "|---:|---|---|---:|---:|---|---:|",
    ]
    for episode in episodes:
        writes = episode.staleness.edit_distance_writes
        p1_item = _condition_at(results, PayloadCondition.P1, writes)
        p3_item = _condition_at(results, PayloadCondition.P3, writes)
        adaptive_item = _condition_at(results, PayloadCondition.ADAPTIVE, writes)
        lines.append(
            f"| {writes} | {episode.episode_id} | {episode.correct_action.value} | "
            f"{int(p1_item.recovery_success)} | {int(p3_item.recovery_success)} | "
            f"{adaptive_item.selected_condition.value} | {int(adaptive_item.recovery_success)} |"
        )
    lines.extend(
        [
            "",
            "In the two low-staleness adaptation cases (k=1,2), P1 and P3 are tied. In the",
            "high-staleness decision cases (k=4,8), P3 gains 100 percentage points over P1.",
            "The threshold policy selects P1 below k=4 and directive P5 at or above k=4,",
            f"matching P3 on all four fixtures with {savings:.1%} fewer mean payload tokens.",
            "",
            "## Interpretation",
            "",
            "The case studies verify that the framework can express the proposed H2 crossover and",
            "the H5/H6 decision mechanism: content/diff is sufficient for local adaptation, while",
            "intent-bearing or directive payloads disambiguate abandon/escalate decisions. This",
            "does not estimate an effect size. Natural STORM refusals replayed through an LLM",
            "backend are required before accepting or rejecting the research hypotheses.",
            "",
            "## Artifacts",
            "",
            "- `episodes.jsonl`: replayable refusal snapshots",
            "- `replay_results.csv`: every episode × payload result",
            "- `summary.csv`: aggregate recovery, action, repetition, and token metrics",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_case_studies(output_dir: Path) -> list[ReplayResult]:
    output_dir.mkdir(parents=True, exist_ok=True)
    episodes = build_controlled_episodes()
    EpisodeLog(output_dir / "episodes.jsonl").write(episodes)
    results = ReplayRunner(ControlledRecoveryBackend()).run_matrix(
        episodes, CASE_STUDY_CONDITIONS
    )
    _write_results(output_dir / "replay_results.csv", results)
    summary = _summaries(results)
    _write_summary(output_dir / "summary.csv", summary)
    _write_report(output_dir / "report.md", episodes, results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("case_study_results"),
        help="Directory for JSONL, CSV, and Markdown outputs.",
    )
    args = parser.parse_args()
    results = run_case_studies(args.output_dir)
    print(f"Wrote {len(results)} paired replay results to {args.output_dir}")


if __name__ == "__main__":
    main()
