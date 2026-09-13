from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass

from .measurement import make_unified_diff
from .validation import _safe_syntax


CORPUS_VERSION = "context-pilot-v1"
ACTIONS = ("adapt", "abandon", "escalate")
COORDINATION_RULE = (
    "Edit only main.py. Preserve the peer's protected input/output contracts below. "
    "Compatible unfinished requirements may be implemented locally. Only the manager "
    "may waive a protected contract that conflicts with the assigned requirements. "
    "An ordinary implementation bug does not require manager approval."
)


@dataclass(frozen=True)
class Family:
    name: str
    task: str
    probes: tuple[tuple[object, object], ...]
    partial: str
    complete: str
    intent: str
    rationale: str
    challenge: bool = True
    caller: str = ""


# Requirements and explicit input/output obligations precede implementations.
# Probe 0 distinguishes partial completion; later probes retain ordinary controls.
FAMILIES = (
    Family(
        "bounded_percentage", "Clamp integer value into the inclusive range 0..100.",
        ((101, 100), (-1, 0), (40, 40), (0, 0), (100, 100)),
        "max(0, value)", "min(100, max(0, value))",
        "Handle out-of-range percentage readings.",
        "Sensor readings can cross either endpoint; the inclusive endpoints retain their values.",
        caller="def display(value):\n    return str(main(value)) + '%'\n",
    ),
    Family(
        "shipping_units", "For nonnegative integer cents, return whole dollars rounded up.",
        ((101, 2), (0, 0), (100, 1), (1, 1), (299, 3)),
        "value // 100", "(value + 99) // 100",
        "Convert shipping charges to billable dollars.",
        "A fractional dollar occupies one billing unit, while zero cents occupies none.",
    ),
    Family(
        "archive_suffix", "Remove exactly one trailing '.gz' from text; preserve interior occurrences.",
        (("a.gz.b.gz", "a.gz.b"), ("x.gz", "x"), ("x", "x"), (".gz.gz", ".gz")),
        "value.replace('.gz', '')", "value[:-3] if value.endswith('.gz') else value",
        "Expose an archive's underlying filename.",
        "Only the outer compression suffix identifies this layer; interior text names the original file.",
    ),
    Family(
        "path_components", "Split text on '/', drop empty and '.' components, and retain '..'.",
        (("/a/./b//", ["a", "b"]), ("../x", ["..", "x"]), ("/", []), ("a/b", ["a", "b"])),
        "[p for p in value.split('/') if p]",
        "[p for p in value.split('/') if p and p != '.']",
        "Tokenize paths without resolving parent traversal.",
        "Empty and current-directory segments add no component; parent segments carry information for callers.",
    ),
    Family(
        "batch_count", "Return batches of size four needed for nonnegative integer value, including a partial batch.",
        ((5, 2), (0, 0), (4, 1), (1, 1), (12, 3)),
        "0", "(value + 3) // 4",
        "Account for storage batches.",
        "Any remaining item consumes another batch; an empty input consumes no batch.", False,
    ),
    Family(
        "account_mask", "Mask all but the last four text characters with '*'; keep original length, including short inputs.",
        (("123456", "**3456"), ("123", "123"), ("", ""), ("abcd", "abcd")),
        "value[-4:]", "'*' * max(0, len(value) - 4) + value[-4:]",
        "Retain a recognizable account suffix.",
        "The suffix identifies the account while masking earlier characters preserves display width.",
        caller="def display(value):\n    return '[' + main(value) + ']'\n",
    ),
    Family(
        "inclusive_range", "Given [start, stop] integers, return ascending inclusive range; return [] when start exceeds stop.",
        (([2, 4], [2, 3, 4]), ([2, 2], [2]), ([4, 2], []), ([-1, 1], [-1, 0, 1])),
        "list(range(value[0], value[1]))", "list(range(value[0], value[1] + 1))",
        "Enumerate inclusive sequence bounds.",
        "Both endpoint values belong to the sequence; reversed bounds contain no ascending values.",
    ),
    Family(
        "header_keys", "Lowercase dictionary keys, preserving their values. Inputs have no case-colliding keys.",
        (({"Host": "X"}, {"host": "X"}), ({"A": 1, "b": 2}, {"a": 1, "b": 2}), ({}, {})),
        "value", "{key.lower(): item for key, item in value.items()}",
        "Canonicalize request header names.",
        "Header names are case-insensitive but their values retain the original representation.", False,
    ),
    Family(
        "duration_millis", "Convert nonnegative integer seconds to integer milliseconds.",
        ((2, 2000), (0, 0), (1, 1000), (45, 45000)),
        "value", "value * 1000",
        "Expose duration in the client's time unit.",
        "The client consumes milliseconds, with one thousand units per second.", False,
        caller="def display(value):\n    return {'ms': main(value)}\n",
    ),
    Family(
        "byte_checksum", "Return sum of integer byte values modulo 256, with zero for an empty list.",
        (([255, 2], 1), ([], 0), ([1, 2], 3), ([128, 128], 0)),
        "sum(value)", "sum(value) % 256",
        "Compute the packet's one-byte checksum.",
        "The wire field stores one byte, so sums wrap at 256 without changing small totals.",
    ),
    Family(
        "comma_fields", "Split comma-separated text, strip each field, drop empty fields, and preserve order.",
        ((" a, ,b,,", ["a", "b"]), ("", []), ("x,y", ["x", "y"]), (" x ", ["x"])),
        "[p.strip() for p in value.split(',')]",
        "[p.strip() for p in value.split(',') if p.strip()]",
        "Read user-entered field lists.",
        "Whitespace surrounds field values; blank entries do not designate a field.",
    ),
    Family(
        "positive_total", "Sum only strictly positive integers in a list; empty lists return zero.",
        (([-2, 3], 3), ([], 0), ([1, 2], 3), ([-3, 0], 0)),
        "0", "sum(item for item in value if item > 0)",
        "Accumulate positive contributions.",
        "Negative adjustments and zero contribute nothing to this positive-only total.", False,
    ),
)


@dataclass(frozen=True)
class PublicCase:
    task: str
    coordination: str
    protected: tuple[tuple[object, object], ...]
    base: str
    current: str
    proposed: str
    caller: str
    winner_intent: str
    winner_rationale: str
    k: int
    revision_history: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class PilotCase:
    case_id: str
    family: str
    split: str
    challenge: bool
    public: PublicCase
    acceptable_actions: tuple[str, ...]
    obligations: tuple[tuple[object, object], ...]
    reference: str


def _source(expression: str, protected: tuple[tuple[object, object], ...] = ()) -> str:
    lines = ["def main(value):"]
    for value, expected in protected:
        lines.extend((f"    if value == {value!r}:", f"        return {expected!r}"))
    lines.append(f"    return {expression}")
    return "\n".join(lines) + "\n"


def build_pilot_corpus(k: int = 4) -> list[PilotCase]:
    if k < 1:
        raise ValueError("k must be positive")
    cases = []
    for index, family in enumerate(FAMILIES):
        for action in ACTIONS:
            # Route is a case specification, never a function of k or payload.
            protected = ((None, "missing"),)
            if action == "escalate":
                protected += ((family.probes[0][0], "reserved"),)
            expression = family.partial if action == "adapt" else family.complete
            base = _source(family.partial)
            current = _source(expression, protected)
            public = PublicCase(
                task="Implement main(value) in main.py for non-None inputs. " + family.task,
                coordination=COORDINATION_RULE,
                protected=protected,
                base=base,
                current=current,
                proposed=_source(family.complete),
                caller=family.caller,
                winner_intent=family.intent + " Retain the peer's protected cases.",
                winner_rationale=family.rationale + " Protected inputs have dedicated handling.",
                k=k,
                revision_history=tuple(
                    {"version": version, "writer": "peer", "path": "main.py"}
                    for version in range(1, k + 1)
                ),
            )
            cases.append(PilotCase(
                case_id=hashlib.sha256(f"{CORPUS_VERSION}:{family.name}:{action}".encode()).hexdigest()[:12],
                family=family.name,
                split="development" if index in (0, 4, 8) else "evaluation",
                challenge=family.challenge,
                public=public,
                acceptable_actions=(action,),
                obligations=family.probes,
                reference=_source(family.complete, ((None, "missing"),)),
            ))
    return cases


def render_payload(case: PublicCase, condition: str) -> str:
    if condition not in ("P1", "P2", "P3"):
        raise ValueError("pilot permits only P1/P2/P3")
    text = (
        "WRITE REJECTED. Authoritative state follows.\n"
        f"Stale dependencies: main.py(v0->v{case.k}, peer).\n"
        f"Diff since read:\n{make_unified_diff('main.py', case.base, case.current)}\n"
        f"Current main.py:\n{case.current}"
    )
    if case.caller:
        text += f"Read-only caller.py (unchanged, v0):\n{case.caller}"
    if condition == "P2":
        text += f"Winner declared intent: {case.winner_intent}\n"
    elif condition == "P3":
        text += f"Winner rationale: {case.winner_rationale}\n"
    return text


# Generated code runs with no imports, I/O, or evaluator data in its namespace.
# OS limits and the parent timeout bound resource use; this is a restricted local
# benchmark evaluator, not a general-purpose hostile-code sandbox.
_HARNESS = r"""
import json, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
data = json.load(sys.stdin)
scope = {'__builtins__': {name: getattr(__builtins__, name) for name in
    ('dict', 'list', 'str', 'int', 'bool', 'len', 'min', 'max', 'sum', 'range',
     'isinstance', 'sorted', 'enumerate', 'zip', 'abs', 'round', 'TypeError', 'ValueError')}}
exec(compile(data['source'], 'main.py', 'exec'), scope)
if data['caller']:
    exec(compile(data['caller'], 'caller.py', 'exec'), scope)
for value, expected in data['probes']:
    assert scope['main'](value) == expected
if data['caller']:
    reference = dict(scope)
    exec(compile(data['reference'], 'reference.py', 'exec'), reference)
    exec(compile(data['caller'], 'caller.py', 'exec'), reference)
    for value, expected in data['probes']:
        assert scope['display'](value) == reference['display'](value)
"""


def verify_behavior(case: PilotCase, source: str) -> bool:
    if not isinstance(source, str) or not source.strip():
        return False
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    if not _safe_syntax(tree) or any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        or isinstance(node, ast.Name) and node.id.startswith("__")
        for node in ast.walk(tree)
    ):
        return False
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _HARNESS],
            input=json.dumps({
                "source": source,
                "caller": case.public.caller,
                "reference": case.reference,
                "probes": case.obligations + case.public.protected,
            }),
            text=True, capture_output=True, timeout=2.0, check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def score_response(case: PilotCase, parsed: dict[str, object] | None, *, truncated: bool = False) -> dict[str, object]:
    action = parsed.get("action") if parsed else None
    source = parsed.get("revised_content") if parsed else None
    valid = bool(
        not truncated and action in ACTIONS and isinstance(source, str)
        and isinstance(parsed.get("explanation"), str)
        and (bool(source.strip()) if action == "adapt" else source == "")
    )
    route_correct = valid and action in case.acceptable_actions
    verified = None
    if case.acceptable_actions != ("escalate",):
        verified = bool(valid and (
            verify_behavior(case, source) if action == "adapt"
            else action == "abandon" and verify_behavior(case, case.public.current)
        ))
    justified = bool(route_correct and action == "escalate")
    return {
        "action": action, "valid_response": valid, "route_correct": route_correct,
        "verified_recovery": verified, "justified_escalation": justified,
        "completed_coordination": None,
        "equal_action_composite": justified if verified is None else verified,
        "failed_revision": action == "adapt" and not bool(verified),
        "unnecessary_abandonment": action == "abandon" and "abandon" not in case.acceptable_actions,
        "unjustified_escalation": action == "escalate" and not justified,
        "truncated": truncated,
    }


def audit_corpus(cases: list[PilotCase]) -> dict[str, object]:
    counts = Counter(case.acceptable_actions[0] for case in cases)
    assert counts == Counter({action: 12 for action in ACTIONS}), counts
    development = {case.family for case in cases if case.split == "development"}
    evaluation = {case.family for case in cases if case.split == "evaluation"}
    assert not development & evaluation
    assert len(development | evaluation) == 12
    assert len({case.case_id for case in cases}) == 36
    checks = 0
    for case in cases:
        complete = case.acceptable_actions == ("abandon",)
        assert verify_behavior(case, case.public.current) == complete, case.case_id
        assert verify_behavior(case, case.reference) == (case.acceptable_actions != ("escalate",))
        assert not verify_behavior(case, case.public.proposed), case.case_id
        assert not verify_behavior(case, "def main(value):\n    return None\n")
        checks += 4
        for condition in ("P1", "P2", "P3"):
            payload = render_payload(case.public, condition)
            assert not any(field in payload for field in (
                "acceptable_actions", "correct_action", "reference", "obligations",
                "adapt", "abandon", "escalate",
            ))
    variants = [build_pilot_corpus(k) for k in (1, 8)]
    for first, last in zip(*variants, strict=True):
        assert first.acceptable_actions == last.acceptable_actions
        assert first.public.current == last.public.current
        assert first.obligations == last.obligations
        assert len(first.public.revision_history) == 1
        assert len(last.public.revision_history) == 8
    return {
        "passed": True, "corpus_version": CORPUS_VERSION,
        "cases": len(cases), "action_counts": dict(counts),
        "development_families": sorted(development), "evaluation_families": sorted(evaluation),
        "behavioral_controls": checks, "k_invariance": [1, 8],
        "prompt_boundary": "render_payload accepts only PublicCase; no evaluator fields",
    }


if __name__ == "__main__":
    print(json.dumps(audit_corpus(build_pilot_corpus()), indent=2))
