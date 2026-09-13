from __future__ import annotations

import ast
import json
from dataclasses import dataclass

from .pilot_corpus import PublicCase, render_payload


OUTPUT_TOKENS = 2048
SERVER_LIMIT = 16384
LENGTHS = (1024, 12288)
HISTORIES = ("current", "superseded")
CONDITIONS = ("P1", "P2", "P3")
SYSTEM_PROMPT = (
    "Recover from a rejected write using the assigned task, coordination rules, and authoritative refusal. "
    "History records have provenance and versions and may be superseded. "
    "Choose adapt to implement compatible unfinished work, abandon if the task already holds, "
    "or escalate if conflicting protected contracts need a manager decision. "
    "Return a JSON object with action, revised_content, explanation. For adapt, revised_content "
    "is the complete main.py; otherwise it is an empty string."
)


class ModelTokenizer:
    def __init__(self, model_path: str):
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def prompt_tokens(self, messages: list[dict[str, str]]) -> int:
        return len(self.tokenizer.apply_chat_template(
            messages, tokenize=True, return_dict=False,
            add_generation_prompt=True, enable_thinking=False,
        ))


@dataclass(frozen=True)
class ContextPrompt:
    messages: list[dict[str, str]]
    prompt_tokens: int
    payload_tokens: int
    relevant_tokens: int
    obsolete_span_tokens: int
    obsolete_fraction: float
    relevant_start_fraction: float
    relevant_history: str


def _observations(case: PublicCase, history: str, tokenizer: ModelTokenizer) -> str:
    expression = case.current.strip().splitlines()[-1].strip().removeprefix("return ")
    tree = ast.parse(expression, mode="eval")
    # Construct an earlier source variant at the same two source locations.
    # Change a literal where possible; the bare-identity controls use str(value).
    constants = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    if constants:
        node = constants[0]
        if isinstance(node.value, int):
            node.value += 1
        elif isinstance(node.value, str):
            node.value = node.value.replace(".", "_") if "." in node.value else "x"
        old_expression = ast.unparse(tree)
    else:
        old_expression = f"str({expression})"
    records = {}
    for condition, version, sentinel, body in (
        ("current", case.k, "missing", expression),
        ("superseded", 0, "unknown", old_expression),
    ):
        records[condition] = (
            f"read main.py@v{version}, main/None-branch: return '{sentinel}'\n"
            f"read main.py@v{version}, main/final-return: return {body}\n"
        )
    # Match relevant block size using layout whitespace only, never extra facts.
    target = max(tokenizer.count(text) for text in records.values())
    for condition, text in records.items():
        while tokenizer.count(text) < target:
            text += " \n"
        records[condition] = text
    if abs(tokenizer.count(records["current"]) - tokenizer.count(records["superseded"])) > 1:
        raise ValueError("relevant history blocks did not match in size")
    return records[history]


def build_context_prompt(
    case: PublicCase, condition: str, history: str, length: int, tokenizer: ModelTokenizer,
) -> ContextPrompt:
    if length not in LENGTHS or history not in HISTORIES:
        raise ValueError("unsupported primary-study context")
    payload = render_payload(case, condition)
    prefix = (
        f"Task: {case.task}\nCoordination: {case.coordination}\n"
        f"Protected input/output contracts: {json.dumps(case.protected)}\n"
        f"Rejected main.py:\n{case.proposed}\n"
        "Constructed repository history (source-read records):\n"
    )
    relevant = _observations(case, history, tokenizer)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": ""}]

    def count(user: str) -> int:
        return tokenizer.prompt_tokens([messages[0], {"role": "user", "content": user}])

    # Count the chat-template prefix up to the history, excluding its closing
    # user/assistant generation suffix. The same suffix cancels in this difference.
    marker = "PILOT_CONTENT_BOUNDARY"
    rendered = tokenizer.tokenizer.apply_chat_template(
        [messages[0], {"role": "user", "content": marker}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )
    suffix_tokens = count("") - tokenizer.count(rendered.split(marker)[0])
    # Neutral records reference an unrelated document and are always complete.
    neutral = "read docs/build.txt@v1: build notes unchanged.\n"
    short_neutral = "read docs/x@v1: OK.\n"
    before = ""
    target_position = length // 2
    if count(prefix) - suffix_tokens > target_position:
        raise ValueError("core task exceeds the fixed history position; repair corpus")
    for record in (neutral, short_neutral):
        copies = max(0, (target_position - count(prefix + before) + suffix_tokens) // tokenizer.count(record))
        before += record * copies
        while count(prefix + before + record) - suffix_tokens <= target_position:
            before += record
    body = prefix + before + relevant
    tail = "\nRefusal (current authoritative state):\n" + payload
    if count(body + tail) > length * 1.02:
        raise ValueError("essential evidence exceeds input budget; repair corpus")
    after = ""
    for record in (neutral, short_neutral):
        # Approximate the large fill, then measure with the actual chat template.
        increment = max(tokenizer.count(record), 1)
        copies = max(0, (length - count(body + after + tail)) // increment)
        after += record * copies
        while count(body + after + record + tail) <= length:
            after += record
    text = body + after + tail
    tokens = count(text)
    if abs(tokens - length) / length > 0.02 or tokens + OUTPUT_TOKENS > SERVER_LIMIT:
        raise ValueError("input/output capacity gate failed")
    position = (count(prefix + before) - suffix_tokens) / tokens
    if abs(position - 0.5) > 0.02:
        raise ValueError("relevant history position gate failed")
    messages[1]["content"] = text
    obsolete = tokenizer.count(relevant.rstrip()) if history == "superseded" else 0
    return ContextPrompt(
        messages=messages, prompt_tokens=tokens, payload_tokens=tokenizer.count(payload),
        relevant_tokens=tokenizer.count(relevant), obsolete_span_tokens=obsolete,
        obsolete_fraction=obsolete / tokens, relevant_start_fraction=position,
        relevant_history=relevant,
    )
