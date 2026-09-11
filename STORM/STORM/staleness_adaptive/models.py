from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PayloadCondition(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"
    P5_ORACLE = "P5-oracle"
    P1_PAD = "P1-pad"
    ADAPTIVE = "adaptive"


class RecoveryAction(str, Enum):
    ADAPT = "adapt"
    QUEUE = "queue"
    SERIALIZE = "serialize"
    ABANDON = "abandon"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class PolicyPrediction:
    action: RecoveryAction
    refinement_hint: str
    source: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str = ""


@dataclass(frozen=True)
class StaleDependency:
    path: str
    expected_version: int
    current_version: int
    changed_by: str


@dataclass(frozen=True)
class StalenessMeasures:
    temporal_seconds: float
    edit_distance_writes: int
    semantic_ratio: float
    symbol_overlap: bool
    investment_tokens: int
    investment_tool_calls: int

    def __post_init__(self) -> None:
        if self.temporal_seconds < 0:
            raise ValueError("temporal_seconds must be non-negative")
        if self.edit_distance_writes < 1:
            raise ValueError("a refusal episode requires at least one intervening write")
        if not 0.0 <= self.semantic_ratio <= 1.0:
            raise ValueError("semantic_ratio must be between 0 and 1")
        if self.investment_tokens < 0 or self.investment_tool_calls < 0:
            raise ValueError("investment measures must be non-negative")


@dataclass(frozen=True)
class ConflictEpisode:
    episode_id: str
    repo: str
    losing_agent_id: str
    winning_agent_id: str
    file_path: str
    base_content: str
    current_content: str
    proposed_content: str
    unified_diff: str
    stale_dependencies: tuple[StaleDependency, ...]
    staleness: StalenessMeasures
    winner_intent: str
    winner_reasoning: str
    winner_task: str
    winner_trajectory: tuple[str, ...]
    recommended_action: RecoveryAction
    refinement_hint: str
    correct_action: RecoveryAction
    padding_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConflictEpisode:
        values = dict(data)
        values["stale_dependencies"] = tuple(
            StaleDependency(**item) for item in values.get("stale_dependencies", [])
        )
        values["staleness"] = StalenessMeasures(**values["staleness"])
        values["winner_trajectory"] = tuple(values.get("winner_trajectory", []))
        values["recommended_action"] = RecoveryAction(values["recommended_action"])
        values["correct_action"] = RecoveryAction(values["correct_action"])
        return cls(**values)


@dataclass(frozen=True)
class RecoveryAttempt:
    action: RecoveryAction
    accepted_write: bool
    touched_tests_pass: bool
    repeat_refusal: bool
    recovery_tokens: int
    recovery_tool_calls: int
    notes: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def success(self) -> bool:
        if self.action != RecoveryAction.ADAPT:
            return self.touched_tests_pass and not self.repeat_refusal
        return self.accepted_write and self.touched_tests_pass


@dataclass(frozen=True)
class ReplayResult:
    episode_id: str
    repo: str
    edit_distance_writes: int
    semantic_ratio: float
    investment_tokens: int
    requested_condition: PayloadCondition
    selected_condition: PayloadCondition
    seed: int
    payload_tokens: int
    correct_action: RecoveryAction
    action: RecoveryAction
    action_correct: bool
    recovery_success: bool
    accepted_write: bool
    touched_tests_pass: bool
    repeat_refusal: bool
    recovery_tokens: int
    model_prompt_tokens: int
    model_completion_tokens: int
    recovery_tool_calls: int
    policy_action: RecoveryAction | None = None
    policy_action_correct: bool | None = None
    policy_prompt_tokens: int = 0
    policy_completion_tokens: int = 0
    policy_source: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["requested_condition"] = self.requested_condition.value
        data["selected_condition"] = self.selected_condition.value
        data["correct_action"] = self.correct_action.value
        data["action"] = self.action.value
        data["policy_action"] = (
            self.policy_action.value if self.policy_action is not None else ""
        )
        return data
