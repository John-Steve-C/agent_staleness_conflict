from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Protocol

from .models import (
    ConflictEpisode,
    PayloadCondition,
    PolicyPrediction,
    RefusalPosition,
    RecoveryAction,
)
from .validation import validate_dependencies, validate_revision


STANDING_TO_REJECT = (
    "You may reject a peer's change when it conflicts with your assignment or required invariants."
)
CONTEXT_LENGTHS = (1000, 8000, 32000, 128000)


def count_tokens(text: str) -> int:
    """Dependency-free token proxy used only for payload cost comparisons."""
    return len(text.split())


class TokenCounter(Protocol):
    def __call__(self, text: str) -> int: ...


class TokenizerJsonCounter:
    def __init__(self, path: Path) -> None:
        from tokenizers import Tokenizer

        self.tokenizer = Tokenizer.from_file(str(path))

    def __call__(self, text: str) -> int:
        return len(self.tokenizer.encode(text).ids)


@dataclass(frozen=True)
class Payload:
    requested_condition: PayloadCondition
    selected_condition: PayloadCondition
    text: str
    policy_prediction: PolicyPrediction | None = None
    directed_action: RecoveryAction | None = None
    receiver_trajectory_before: str = ""
    receiver_trajectory_after: str = ""
    receiver_context_target_tokens: int = 0
    receiver_trajectory_tokens: int = 0
    refusal_position: RefusalPosition | None = None
    measured_token_count: int | None = None

    @property
    def token_count(self) -> int:
        return (
            self.measured_token_count
            if self.measured_token_count is not None
            else count_tokens(self.text)
        )


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


class ExecutionActionPolicy:
    """Compute a route from the losing task's checks instead of predicting it."""

    def predict(self, episode: ConflictEpisode, seed: int) -> PolicyPrediction:
        del seed
        started = monotonic()
        assignment_satisfied = validate_revision(episode, episode.current_content)
        dependencies_hold = validate_dependencies(episode, episode.current_content)
        if assignment_satisfied:
            action = RecoveryAction.ABANDON
            hint = self._ground(episode, "already satisfies the assigned behavior")
        elif not dependencies_hold:
            action = RecoveryAction.ESCALATE
            hint = self._ground(episode, "fails a required dependency check")
        else:
            action = RecoveryAction.ADAPT
            hint = self._ground(
                episode, "preserves dependency checks but does not finish the assignment"
            )
        return PolicyPrediction(
            action=action,
            refinement_hint=hint,
            source="execution",
            wall_clock_seconds=monotonic() - started,
        )

    @staticmethod
    def _ground(episode: ConflictEpisode, result: str) -> str:
        symbol = str(episode.metadata.get("ground_symbol", ""))
        line = int(episode.metadata.get("ground_line", 0))
        if not symbol or not line:
            for number, source_line in enumerate(
                episode.current_content.splitlines(), start=1
            ):
                stripped = source_line.strip()
                if stripped.startswith(("def ", "class ")):
                    symbol = stripped.split()[1].split("(", 1)[0].rstrip(":")
                    line = number
                    break
        symbol = symbol or "changed symbol"
        line = line or 1
        return f"engineer-B's {symbol} at {episode.file_path}:{line} {result}."


class PayloadRenderer:
    def __init__(
        self,
        *,
        reasoning_token_cap: int = 160,
        adaptive_policy: AdaptivePayloadPolicy | None = None,
        action_policy: RecoveryActionPolicy | None = None,
        execution_policy: RecoveryActionPolicy | None = None,
        token_counter: TokenCounter = count_tokens,
    ) -> None:
        self.reasoning_token_cap = reasoning_token_cap
        self.adaptive_policy = adaptive_policy or AdaptivePayloadPolicy()
        self.action_policy = action_policy or ContentDeltaActionPolicy()
        self.execution_policy = execution_policy or ExecutionActionPolicy()
        self.token_counter = token_counter

    def render(
        self,
        episode: ConflictEpisode,
        condition: PayloadCondition,
        *,
        seed: int = 0,
        receiver_context_tokens: int | None = None,
        refusal_position: RefusalPosition = RefusalPosition.TAIL,
        injected_route: RecoveryAction | None = None,
    ) -> Payload:
        selected = (
            self.adaptive_policy.select(episode)
            if condition == PayloadCondition.ADAPTIVE
            else condition
        )
        prediction = None
        if selected == PayloadCondition.P5:
            prediction = self.action_policy.predict(episode, seed)
        elif selected == PayloadCondition.P6:
            if injected_route is None:
                raise ValueError("P6 requires an explicitly injected route")
            action = injected_route
            prediction = PolicyPrediction(
                action=action,
                refinement_hint=ExecutionActionPolicy._ground(
                    episode, self._route_ground_result(action)
                ),
                source="injected-route",
            )
        elif selected == PayloadCondition.P8:
            prediction = self.execution_policy.predict(episode, seed)
        text = self._render_selected(episode, selected, prediction)
        directed_action = prediction.action if prediction is not None else None
        if selected == PayloadCondition.P5_ORACLE:
            directed_action = episode.recommended_action
        before, after, trajectory_tokens = self._receiver_trajectory(
            episode, receiver_context_tokens, refusal_position
        )
        return Payload(
            requested_condition=condition,
            selected_condition=selected,
            text=text,
            policy_prediction=prediction,
            directed_action=directed_action,
            receiver_trajectory_before=before,
            receiver_trajectory_after=after,
            receiver_context_target_tokens=receiver_context_tokens or 0,
            receiver_trajectory_tokens=trajectory_tokens,
            refusal_position=(
                refusal_position if receiver_context_tokens is not None else None
            ),
            measured_token_count=self.token_counter(text),
        )

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
        if condition == PayloadCondition.P6:
            if prediction is None:
                raise ValueError("P6 requires an injected route")
            return (
                f"{base}\n\nInjected recovery route: {prediction.action.value}."
                f"\nFalsifiable ground: {prediction.refinement_hint}"
            )
        if condition == PayloadCondition.P7:
            return f"{base}\n\nStanding instruction:\n{STANDING_TO_REJECT}"
        if condition == PayloadCondition.P8:
            if prediction is None:
                raise ValueError("P8 requires an execution result")
            return (
                f"{base}\n\nExecution-verified recovery route: {prediction.action.value}."
                f"\nVerification ground: {prediction.refinement_hint}"
            )
        if condition == PayloadCondition.P1_PAD:
            target = count_tokens(self._render_selected(episode, PayloadCondition.P3))
            return self._pad_to_tokens(base, episode.padding_text, target)
        raise ValueError(f"unsupported payload condition: {condition}")

    @staticmethod
    def _route_ground_result(action: RecoveryAction) -> str:
        return {
            RecoveryAction.ABANDON: "already satisfies the assigned behavior",
            RecoveryAction.ESCALATE: "fails a required dependency check",
            RecoveryAction.ADAPT: (
                "preserves dependency checks but does not finish the assignment"
            ),
        }.get(action, "requires the injected coordination route")

    def _receiver_trajectory(
        self,
        episode: ConflictEpisode,
        target_tokens: int | None,
        position: RefusalPosition,
    ) -> tuple[str, str, int]:
        if target_tokens is None:
            return "", "", 0
        if target_tokens < 1:
            raise ValueError("receiver_context_tokens must be positive")
        steps = episode.receiver_trajectory or (
            f"Tool call: read {episode.file_path}.",
            f"Tool result: {episode.base_content}",
            f"Working note: {episode.metadata.get('losing_agent_task', '')}",
            f"Partial edit under consideration: {episode.proposed_content}",
            f"Tool call: inspect references to {episode.file_path} and dependent tests.",
        )
        trajectory = "\n".join(steps).split()
        filler = episode.padding_text.split() or (
            "Tool call search repository for callers and nearby tests Tool result "
            "several unrelated modules inspected no additional write attempted"
        ).split()
        trajectory.extend(
            filler[index % len(filler)] for index in range(target_tokens * 2)
        )
        while self.token_counter(" ".join(trajectory)) < target_tokens:
            trajectory.extend(filler)
        low, high = 0, len(trajectory)
        while low < high:
            middle = (low + high + 1) // 2
            if self.token_counter(" ".join(trajectory[:middle])) <= target_tokens:
                low = middle
            else:
                high = middle - 1
        trajectory = trajectory[:low]
        realised = self.token_counter(" ".join(trajectory))
        while realised < target_tokens:
            candidate = [*trajectory, "read"]
            candidate_tokens = self.token_counter(" ".join(candidate))
            if candidate_tokens > target_tokens:
                break
            trajectory = candidate
            realised = candidate_tokens
        target_before = {
            RefusalPosition.HEAD: 0,
            RefusalPosition.MIDDLE: realised // 2,
            RefusalPosition.TAIL: realised,
        }[position]
        low, high = 0, len(trajectory)
        while low < high:
            middle = (low + high + 1) // 2
            if self.token_counter(" ".join(trajectory[:middle])) <= target_before:
                low = middle
            else:
                high = middle - 1
        return " ".join(trajectory[:low]), " ".join(trajectory[low:]), realised

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
