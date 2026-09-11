from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .measurement import make_unified_diff, measure_staleness
from .models import (
    ConflictEpisode,
    RecoveryAction,
    StaleDependency,
)


def episode_from_storm_refusal(
    response: Any,
    *,
    episode_id: str,
    repo: str,
    losing_agent_id: str,
    winning_agent_id: str,
    file_path: str,
    base_content: str,
    proposed_content: str,
    read_at: float,
    refused_at: float,
    intervening_writes: int,
    tokens_since_read: int,
    tool_calls_since_read: int,
    winner_intent: str,
    winner_reasoning: str,
    winner_task: str,
    winner_trajectory: Iterable[str],
    recommended_action: RecoveryAction,
    refinement_hint: str,
    correct_action: RecoveryAction,
    referenced_symbols: set[str] | frozenset[str] = frozenset(),
    changed_symbols: set[str] | frozenset[str] = frozenset(),
    padding_text: str = "",
) -> ConflictEpisode:
    """Convert STORM's WriteResponse-like object into a replayable episode."""
    current_content = response.current_content or ""
    stale_dependencies = tuple(
        StaleDependency(
            path=item.path,
            expected_version=item.expected_version,
            current_version=item.current_version,
            changed_by=item.changed_by,
        )
        for item in response.stale_files
    )
    return ConflictEpisode(
        episode_id=episode_id,
        repo=repo,
        losing_agent_id=losing_agent_id,
        winning_agent_id=winning_agent_id,
        file_path=file_path,
        base_content=base_content,
        current_content=current_content,
        proposed_content=proposed_content,
        unified_diff=response.diff
        or make_unified_diff(file_path, base_content, current_content),
        stale_dependencies=stale_dependencies,
        staleness=measure_staleness(
            read_at=read_at,
            refused_at=refused_at,
            intervening_writes=intervening_writes,
            base_content=base_content,
            current_content=current_content,
            referenced_symbols=referenced_symbols,
            changed_symbols=changed_symbols,
            tokens_since_read=tokens_since_read,
            tool_calls_since_read=tool_calls_since_read,
        ),
        winner_intent=winner_intent,
        winner_reasoning=winner_reasoning,
        winner_task=winner_task,
        winner_trajectory=tuple(winner_trajectory),
        recommended_action=recommended_action,
        refinement_hint=refinement_hint,
        correct_action=correct_action,
        padding_text=padding_text,
    )
