from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .models import ConflictEpisode, PolicyPrediction, RecoveryAction, RecoveryAttempt
from .payloads import Payload
from .validation import validate_revision


SYSTEM_PROMPT = """You are recovering from a rejected write in an asynchronous coding team.
Choose the next coordination action using only your task, your attempted file, and the refusal
payload. `adapt` means return a complete replacement file rebased on current content. `abandon`
means the winning edit already fulfills your task. `escalate` means the edits disagree about a
contract or invariant requiring manager review. `queue` waits for unfinished work; `serialize`
requests exclusive follow-up. Do not infer private facts that the payload does not contain.
Return one JSON object with keys action, revised_content, and explanation. revised_content must be
the complete file for adapt and an empty string for every other action. Keep explanation to one
sentence under 40 words and do not emit any other keys."""


POLICY_SYSTEM_PROMPT = """You are the routing policy for a rejected write in an asynchronous
coding team. Predict the safest next coordination action using only the observable task and file
states supplied below. `adapt` means rebase compatible unfinished work now. `abandon` means the
current file already fulfills the losing task. `escalate` means the edits disagree about a
contract or invariant requiring manager review. `queue` waits for relevant unfinished work;
`serialize` requests exclusive ordered follow-up. Return one JSON object with keys action and
refinement_hint. The hint must be one concrete sentence. Do not assume a hidden ground-truth
label or private winning-agent reasoning."""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("model response did not contain a JSON object")


def _valid_revised_content(episode: ConflictEpisode, content: str) -> bool:
    return validate_revision(episode, content)


def build_recovery_user_prompt(episode: ConflictEpisode, payload: Payload) -> str:
    prefix = (
        f"Your assigned task:\n{episode.metadata.get('losing_agent_task', '')}\n\n"
        f"Your rejected proposed full file:\n```python\n{episode.proposed_content}\n```\n\n"
    )
    if payload.refusal_position is None:
        return f"{prefix}Refusal payload ({payload.selected_condition.value}):\n{payload.text}"
    pieces = [prefix, "Receiver's own trajectory:\n"]
    if payload.receiver_trajectory_before:
        pieces.append(f"{payload.receiver_trajectory_before}\n\n")
    pieces.append(f"Refusal payload ({payload.selected_condition.value}):\n{payload.text}\n\n")
    if payload.receiver_trajectory_after:
        pieces.append(payload.receiver_trajectory_after)
    return "".join(pieces).rstrip()


@dataclass
class OpenAICompatibleRecoveryBackend:
    endpoint: str
    model: str
    timeout: float = 300.0
    max_tokens: int = 700
    temperature: float = 0.0
    top_p: float | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    _records_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def recover(
        self, episode: ConflictEpisode, payload: Payload, seed: int
    ) -> RecoveryAttempt:
        response_body: dict[str, Any] = {}
        user_prompt = build_recovery_user_prompt(episode, payload)
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "seed": seed,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self.top_p is not None:
            request_body["top_p"] = self.top_p
        request = urllib.request.Request(
            f"{self.endpoint.rstrip('/')}/chat/completions",
            data=json.dumps(request_body).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = json.load(response)
            raw_text = response_body["choices"][0]["message"]["content"] or ""
            parsed = _extract_json(raw_text)
            action = RecoveryAction(str(parsed.get("action", "")).lower())
            revised_content = str(parsed.get("revised_content", ""))
            explanation = str(parsed.get("explanation", ""))
            usage = response_body.get("usage", {})
            model_tokens = int(usage.get("total_tokens", 0))
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            valid_revision = action == RecoveryAction.ADAPT and _valid_revised_content(
                episode, revised_content
            )
            action_correct = action == episode.correct_action
            tests_pass = action_correct and (
                valid_revision if action == RecoveryAction.ADAPT else True
            )
            with self._records_lock:
                self.records.append(
                    {
                        "episode_id": episode.episode_id,
                        "requested_condition": payload.requested_condition.value,
                        "selected_condition": payload.selected_condition.value,
                        "seed": seed,
                        "request": request_body,
                        "response": response_body,
                        "parsed": parsed,
                        "mechanical_revision_valid": valid_revision,
                    }
                )
            return RecoveryAttempt(
                action=action,
                accepted_write=valid_revision,
                touched_tests_pass=tests_pass,
                repeat_refusal=False,
                recovery_tokens=model_tokens,
                recovery_tool_calls=0,
                notes=explanation,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except (urllib.error.URLError, KeyError, TypeError, ValueError) as exc:
            usage = response_body.get("usage", {})
            with self._records_lock:
                self.records.append(
                    {
                        "episode_id": episode.episode_id,
                        "requested_condition": payload.requested_condition.value,
                        "selected_condition": payload.selected_condition.value,
                        "seed": seed,
                        "request": request_body,
                        "response": response_body,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            return RecoveryAttempt(
                action=RecoveryAction.ADAPT,
                accepted_write=False,
                touched_tests_pass=False,
                repeat_refusal=False,
                recovery_tokens=int(usage.get("total_tokens", 0)),
                recovery_tool_calls=0,
                notes=f"Invalid model response: {type(exc).__name__}: {exc}",
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )


@dataclass
class OpenAICompatibleActionPolicy:
    endpoint: str
    model: str
    timeout: float = 300.0
    max_tokens: int = 160
    temperature: float = 0.0
    top_p: float | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    _records_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def predict(self, episode: ConflictEpisode, seed: int) -> PolicyPrediction:
        response_body: dict[str, Any] = {}
        user_prompt = (
            f"Losing agent task:\n{episode.metadata.get('losing_agent_task', '')}\n\n"
            f"File at the losing agent's read:\n```python\n{episode.base_content}\n```\n\n"
            f"Losing agent's rejected proposed file:\n```python\n"
            f"{episode.proposed_content}\n```\n\n"
            f"Current file after {episode.staleness.edit_distance_writes} intervening writes:\n"
            f"```python\n{episode.current_content}\n```\n\n"
            f"Unified diff from read state to current state:\n```diff\n"
            f"{episode.unified_diff}\n```"
        )
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": POLICY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "seed": seed,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self.top_p is not None:
            request_body["top_p"] = self.top_p
        request = urllib.request.Request(
            f"{self.endpoint.rstrip('/')}/chat/completions",
            data=json.dumps(request_body).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = json.load(response)
            raw_text = response_body["choices"][0]["message"]["content"] or ""
            parsed = _extract_json(raw_text)
            action = RecoveryAction(str(parsed.get("action", "")).lower())
            hint = str(parsed.get("refinement_hint", "")).strip()
            if not hint:
                raise ValueError("policy response omitted refinement_hint")
            usage = response_body.get("usage", {})
            prediction = PolicyPrediction(
                action=action,
                refinement_hint=hint,
                source="qwen-policy",
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
            record = {
                "episode_id": episode.episode_id,
                "seed": seed,
                "request": request_body,
                "response": response_body,
                "parsed": parsed,
            }
        except (urllib.error.URLError, KeyError, TypeError, ValueError) as exc:
            usage = response_body.get("usage", {})
            prediction = PolicyPrediction(
                action=RecoveryAction.ESCALATE,
                refinement_hint="Policy prediction failed; escalate for safe manager review.",
                source="qwen-policy",
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                error=f"{type(exc).__name__}: {exc}",
            )
            record = {
                "episode_id": episode.episode_id,
                "seed": seed,
                "request": request_body,
                "response": response_body,
                "error": prediction.error,
            }
        with self._records_lock:
            self.records.append(record)
        return prediction
