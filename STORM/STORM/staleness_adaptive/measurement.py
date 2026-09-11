from __future__ import annotations

import difflib

from .models import StalenessMeasures


def _code_lines(content: str) -> list[str]:
    return [
        line.rstrip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def semantic_change_ratio(base_content: str, current_content: str) -> float:
    """Return changed non-comment lines divided by the larger code snapshot."""
    before = _code_lines(base_content)
    after = _code_lines(current_content)
    denominator = max(len(before), len(after), 1)
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    changed = 0
    for tag, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        if tag != "equal":
            changed += max(end_a - start_a, end_b - start_b)
    return min(changed / denominator, 1.0)


def make_unified_diff(path: str, base_content: str, current_content: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            base_content.splitlines(),
            current_content.splitlines(),
            fromfile=f"{path} (agent read)",
            tofile=f"{path} (current)",
            lineterm="",
        )
    )


def measure_staleness(
    *,
    read_at: float,
    refused_at: float,
    intervening_writes: int,
    base_content: str,
    current_content: str,
    referenced_symbols: set[str] | frozenset[str] = frozenset(),
    changed_symbols: set[str] | frozenset[str] = frozenset(),
    tokens_since_read: int,
    tool_calls_since_read: int,
) -> StalenessMeasures:
    return StalenessMeasures(
        temporal_seconds=refused_at - read_at,
        edit_distance_writes=intervening_writes,
        semantic_ratio=semantic_change_ratio(base_content, current_content),
        symbol_overlap=bool(referenced_symbols & changed_symbols),
        investment_tokens=tokens_since_read,
        investment_tool_calls=tool_calls_since_read,
    )
