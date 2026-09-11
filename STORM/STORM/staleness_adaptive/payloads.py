from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import (
    ConflictEpisode,
    PayloadCondition,
    PolicyPrediction,
    RecoveryAction,
)


def count_tokens(text: str) -> int:
    """Dependency-free token proxy used only for payload cost comparisons."""
    return len(text.split())


@dataclass(frozen=True)
class Payload:
    requested_condition: PayloadCondition
    selected_condition: PayloadCondition
    text: str
    policy_prediction: PolicyPrediction | None = None

    @property
    def token_count(self) -> int:
        return count_tokens(self.text)


@dataclass(frozen=True)
class AdaptivePayloadPolicy:
    threshold_writes: int = 4
    low_staleness_condition: PayloadCondition = PayloadCondition.P1
    high_staleness_condition: PayloadCondition = PayloadCondition.P5

    def select(self, episode: ConflictEpisode) -> PayloadCondition:
        if episode.staleness.edit_distance_writes < self.threshold_writes:
            return self.low_staleness_condition
        return self.high_staleness_condition


class RecoveryActionPolicy(Protocol):
    def predict(self, episode: ConflictEpisode, seed: int) -> PolicyPrediction: ...


class ContentDeltaActionPolicy:
    """Dependency-free policy based only on state visible to the refused agent."""

    def predict(self, episode: ConflictEpisode, seed: int) -> PolicyPrediction:
        del seed
        base_lines = self._meaningful_lines(episode.base_content)
        current_lines = self._meaningful_lines(episode.current_content)
        proposed_lines = self._meaningful_lines(episode.proposed_content)
        removed_requirements = (base_lines & proposed_lines) - current_lines
        desired_additions = proposed_lines - base_lines
        if removed_requirements:
            action = RecoveryAction.ESCALATE
            hint = "The current edit removed behavior preserved by the proposed patch; escalate."
        elif desired_additions and desired_additions <= current_lines:
            action = RecoveryAction.ABANDON
            hint = "The current file already contains the proposed behavior; abandon the patch."
        else:
            action = RecoveryAction.ADAPT
            hint = "Rebase the proposed behavior onto the current file and preserve both edits."
        return PolicyPrediction(action=action, refinement_hint=hint, source="content-delta")

    @staticmethod
    def _meaningful_lines(content: str) -> set[str]:
        return {
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }


class PayloadRenderer:
    def __init__(
        self,
        *,
        reasoning_token_cap: int = 160,
        adaptive_policy: AdaptivePayloadPolicy | None = None,
        action_policy: RecoveryActionPolicy | None = None,
    ) -> None:
        self.reasoning_token_cap = reasoning_token_cap
        self.adaptive_policy = adaptive_policy or AdaptivePayloadPolicy()
        self.action_policy = action_policy or ContentDeltaActionPolicy()

    def render(
        self, episode: ConflictEpisode, condition: PayloadCondition, *, seed: int = 0
    ) -> Payload:
        selected = (
            self.adaptive_policy.select(episode)
            if condition == PayloadCondition.ADAPTIVE
            else condition
        )
        prediction = None
        if selected == PayloadCondition.P5:
            prediction = self.action_policy.predict(episode, seed)
        text = self._render_selected(episode, selected, prediction)
        return Payload(condition, selected, text, prediction)

    def _render_selected(
        self,
        episode: ConflictEpisode,
        condition: PayloadCondition,
        prediction: PolicyPrediction | None = None,
    ) -> str:
        if condition == PayloadCondition.P0:
            return f"Write rejected, stale read on `{episode.file_path}`."

        base = self._p1(episode)
        if condition == PayloadCondition.P1:
            return base
        if condition == PayloadCondition.P2:
            return f"{base}\n\nWinning edit intent:\n{episode.winner_intent}"
        if condition == PayloadCondition.P3:
            reasoning = " ".join(
                episode.winner_reasoning.split()[: self.reasoning_token_cap]
            )
            return f"{base}\n\nWinning edit reasoning (capped):\n{reasoning}"
        if condition == PayloadCondition.P4:
            trajectory = "\n".join(f"- {step}" for step in episode.winner_trajectory)
            return (
                f"{base}\n\nWinning agent task:\n{episode.winner_task}"
                f"\n\nRecent winning-agent trajectory:\n{trajectory}"
            )
        if condition == PayloadCondition.P5:
            if prediction is None:
                raise ValueError("P5 requires a policy prediction")
            return (
                f"{base}\n\nPolicy-predicted recovery route: {prediction.action.value}."
                f"\nRefinement hint: {prediction.refinement_hint}"
            )
        if condition == PayloadCondition.P5_ORACLE:
            return (
                f"{base}\n\nOracle recovery route: {episode.recommended_action.value}."
                f"\nRefinement hint: {episode.refinement_hint}"
            )
        if condition == PayloadCondition.P1_PAD:
            target = count_tokens(self._render_selected(episode, PayloadCondition.P3))
            return self._pad_to_tokens(base, episode.padding_text, target)
        raise ValueError(f"unsupported payload condition: {condition}")

    @staticmethod
    def _p1(episode: ConflictEpisode) -> str:
        dependencies = ", ".join(
            f"{item.path}(v{item.expected_version}->v{item.current_version} "
            f"by {item.changed_by})"
            for item in episode.stale_dependencies
        ) or "none"
        return (
            f"WRITE REJECTED on {episode.file_path}.\n"
            f"Unified diff since your read:\n```diff\n{episode.unified_diff}\n```\n"
            f"Stale dependencies: {dependencies}.\n"
            f"Full current content:\n{episode.current_content}\n"
            "Re-read the changed state and replan; do not repeat the same write."
        )

    @staticmethod
    def _pad_to_tokens(base: str, padding_text: str, target: int) -> str:
        words = padding_text.split() or ["irrelevant"]
        heading = "Unrelated repository context (length control):"
        needed = max(target - count_tokens(base) - count_tokens(heading), 0)
        padding = [words[index % len(words)] for index in range(needed)]
        if not padding:
            return base
        return f"{base}\n\n{heading}\n{' '.join(padding)}"
