from __future__ import annotations

from typing import Iterable, Protocol

from .models import (
    ConflictEpisode,
    PayloadCondition,
    RefusalPosition,
    RecoveryAction,
    RecoveryAttempt,
    ReplayResult,
)
from .payloads import Payload, PayloadRenderer


class RecoveryBackend(Protocol):
    """Bridge to a restored STORM/OpenHands continuation or a test double."""

    def recover(
        self, episode: ConflictEpisode, payload: Payload, seed: int
    ) -> RecoveryAttempt: ...


class ReplayRunner:
    def __init__(
        self, backend: RecoveryBackend, renderer: PayloadRenderer | None = None
    ) -> None:
        self.backend = backend
        self.renderer = renderer or PayloadRenderer()

    def run(
        self,
        episode: ConflictEpisode,
        condition: PayloadCondition,
        *,
        seed: int = 0,
        receiver_context_tokens: int | None = None,
        refusal_position: RefusalPosition = RefusalPosition.TAIL,
        injected_route: RecoveryAction | None = None,
    ) -> ReplayResult:
        payload = self.renderer.render(
            episode,
            condition,
            seed=seed,
            receiver_context_tokens=receiver_context_tokens,
            refusal_position=refusal_position,
            injected_route=injected_route,
        )
        attempt = self.backend.recover(episode, payload, seed)
        prediction = payload.policy_prediction
        prompt_tokens = attempt.prompt_tokens or (
            payload.receiver_context_target_tokens + payload.token_count
        )
        return ReplayResult(
            episode_id=episode.episode_id,
            repo=episode.repo,
            edit_distance_writes=episode.staleness.edit_distance_writes,
            semantic_ratio=episode.staleness.semantic_ratio,
            investment_tokens=episode.staleness.investment_tokens,
            requested_condition=condition,
            selected_condition=payload.selected_condition,
            seed=seed,
            payload_tokens=payload.token_count,
            correct_action=episode.correct_action,
            action=attempt.action,
            action_correct=attempt.action == episode.correct_action,
            recovery_success=attempt.success,
            accepted_write=attempt.accepted_write,
            touched_tests_pass=attempt.touched_tests_pass,
            repeat_refusal=attempt.repeat_refusal,
            recovery_tokens=attempt.recovery_tokens,
            model_prompt_tokens=attempt.prompt_tokens,
            model_completion_tokens=attempt.completion_tokens,
            recovery_tool_calls=attempt.recovery_tool_calls,
            policy_action=prediction.action if prediction is not None else None,
            policy_action_correct=(
                prediction.action == episode.correct_action
                if prediction is not None
                else None
            ),
            policy_prompt_tokens=(prediction.prompt_tokens if prediction else 0),
            policy_completion_tokens=(prediction.completion_tokens if prediction else 0),
            policy_wall_clock_seconds=(prediction.wall_clock_seconds if prediction else 0.0),
            policy_source=(prediction.source if prediction else ""),
            payload_action=payload.directed_action,
            payload_action_correct=(
                payload.directed_action == episode.correct_action
                if payload.directed_action is not None
                else None
            ),
            deferred_to_payload=(
                attempt.action == payload.directed_action
                if payload.directed_action is not None
                else None
            ),
            receiver_context_target_tokens=payload.receiver_context_target_tokens,
            receiver_trajectory_tokens=payload.receiver_trajectory_tokens,
            refusal_position=payload.refusal_position,
            payload_context_ratio=(payload.token_count / prompt_tokens if prompt_tokens else 0.0),
            notes=attempt.notes,
        )

    def run_matrix(
        self,
        episodes: Iterable[ConflictEpisode],
        conditions: Iterable[PayloadCondition],
        *,
        seeds: Iterable[int] = (0,),
        receiver_context_lengths: Iterable[int | None] = (None,),
        refusal_positions: Iterable[RefusalPosition] = (RefusalPosition.TAIL,),
        injected_routes: Iterable[RecoveryAction | None] = (None,),
    ) -> list[ReplayResult]:
        return [
            self.run(
                episode,
                condition,
                seed=seed,
                receiver_context_tokens=context_length,
                refusal_position=position,
                injected_route=injected_route,
            )
            for episode in episodes
            for condition in conditions
            for seed in seeds
            for context_length in receiver_context_lengths
            for position in refusal_positions
            for injected_route in injected_routes
        ]
