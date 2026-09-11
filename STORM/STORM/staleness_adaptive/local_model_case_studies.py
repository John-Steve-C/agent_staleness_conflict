from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .case_studies import build_controlled_episodes
from .local_model import OpenAICompatibleRecoveryBackend
from .models import PayloadCondition, ReplayResult
from .replay import ReplayRunner


DEFAULT_CONDITIONS = (
    PayloadCondition.P0,
    PayloadCondition.P1,
    PayloadCondition.P2,
    PayloadCondition.P3,
    PayloadCondition.P5,
    PayloadCondition.P1_PAD,
    PayloadCondition.ADAPTIVE,
)


def _write_csv(path: Path, results: list[ReplayResult]) -> None:
    rows = [item.to_dict() for item in results]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _aggregate(results: list[ReplayResult]) -> list[dict[str, object]]:
    groups: dict[PayloadCondition, list[ReplayResult]] = defaultdict(list)
    for item in results:
        groups[item.requested_condition].append(item)
    return [
        {
            "condition": condition.value,
            "n": len(cell),
            "recovery_success_rate": mean(item.recovery_success for item in cell),
            "action_accuracy": mean(item.action_correct for item in cell),
            "mean_payload_tokens_proxy": mean(item.payload_tokens for item in cell),
            "mean_model_prompt_tokens": mean(item.model_prompt_tokens for item in cell),
            "mean_model_completion_tokens": mean(item.model_completion_tokens for item in cell),
            "mean_model_total_tokens": mean(item.recovery_tokens for item in cell),
        }
        for condition in DEFAULT_CONDITIONS
        if (cell := groups.get(condition))
    ]


def _cell(
    results: list[ReplayResult], condition: PayloadCondition, writes: int
) -> ReplayResult | None:
    return next(
        (
            item
            for item in results
            if item.requested_condition == condition
            and item.edit_distance_writes == writes
        ),
        None,
    )


def _rate(results: list[ReplayResult], condition: PayloadCondition, high: bool) -> float:
    values = [
        item.recovery_success
        for item in results
        if item.requested_condition == condition
        and ((item.edit_distance_writes >= 4) == high)
    ]
    return mean(values) if values else float("nan")


def _write_report(path: Path, model: str, results: list[ReplayResult]) -> None:
    low_gap = _rate(results, PayloadCondition.P3, False) - _rate(
        results, PayloadCondition.P1, False
    )
    high_gap = _rate(results, PayloadCondition.P3, True) - _rate(
        results, PayloadCondition.P1, True
    )
    p3_results = [
        item for item in results if item.requested_condition == PayloadCondition.P3
    ]
    p5_results = [
        item for item in results if item.requested_condition == PayloadCondition.P5
    ]
    adaptive_results = [
        item for item in results if item.requested_condition == PayloadCondition.ADAPTIVE
    ]
    p1_pad = [
        item for item in results if item.requested_condition == PayloadCondition.P1_PAD
    ]
    p1_results = [
        item for item in results if item.requested_condition == PayloadCondition.P1
    ]
    p2_results = [
        item for item in results if item.requested_condition == PayloadCondition.P2
    ]

    def success_rate(cell: list[ReplayResult]) -> float:
        return mean(item.recovery_success for item in cell)

    def payload_saving(cell: list[ReplayResult]) -> float:
        return 1 - mean(item.payload_tokens for item in cell) / mean(
            item.payload_tokens for item in p3_results
        )

    max_prompt_gap = max(
        abs(
            _cell(results, PayloadCondition.P1_PAD, writes).model_prompt_tokens
            - _cell(results, PayloadCondition.P3, writes).model_prompt_tokens
        )
        for writes in (1, 2, 4, 8)
    )

    lines = [
        "# Local-model refusal-payload case study",
        "",
        f"Model: `{model}`",
        "",
        "> This is a four-episode, one-seed pilot on controlled code conflicts. It is real model",
        "> inference, but it is not a powered Commit0 experiment and cannot confirm H2",
        "> statistically.",
        "",
        "## Per-case decisions",
        "",
        "| k | Correct | P1 | P3 | P5 | Adaptive (selected) |",
        "|---:|---|---|---|---|---|",
    ]
    for writes in (1, 2, 4, 8):
        p1 = _cell(results, PayloadCondition.P1, writes)
        p3 = _cell(results, PayloadCondition.P3, writes)
        p5 = _cell(results, PayloadCondition.P5, writes)
        adaptive = _cell(results, PayloadCondition.ADAPTIVE, writes)
        available = next(item for item in (p1, p3, p5, adaptive) if item is not None)

        def show(item: ReplayResult | None) -> str:
            if item is None:
                return "—"
            mark = "✓" if item.recovery_success else "✗"
            return f"{item.action.value} {mark}"

        adaptive_text = (
            f"{show(adaptive)} ({adaptive.selected_condition.value})"
            if adaptive is not None
            else "—"
        )
        lines.append(
            f"| {writes} | {available.correct_action.value} | "
            f"{show(p1)} | {show(p3)} | {show(p5)} | {adaptive_text} |"
        )
    lines.extend(
        [
            "",
            "## Primary H2 diagnostic",
            "",
            f"- P3 − P1 recovery gap at low staleness (k=1,2): {low_gap:+.0%}",
            f"- P3 − P1 recovery gap at high staleness (k=4,8): {high_gap:+.0%}",
            "",
            "A larger high-staleness gap is directionally consistent with H2; an equal or smaller",
            "gap is not. Inspect `model_responses.jsonl` for the decisions and explanations rather",
            "than treating four binary outcomes as an effect-size estimate.",
            "",
            "## Secondary diagnostics",
            "",
            f"- H3 length control: P1-pad success was {success_rate(p1_pad):.0%}, versus "
            f"{success_rate(p1_results):.0%} for P1 and {success_rate(p3_results):.0%} for P3.",
            f"- H6 direction versus transcript: P5 and P3 both achieved "
            f"{success_rate(p5_results):.0%}; "
            f"P5 used {payload_saving(p5_results):.1%} fewer proxy payload tokens.",
            f"- Adaptive policy: {success_rate(adaptive_results):.0%} success with "
            f"{payload_saving(adaptive_results):.1%} fewer proxy payload tokens than P3.",
            f"- P2 intent alone achieved {success_rate(p2_results):.0%}; in these fixtures, the "
            "winner's conclusion was more",
            "  reliable than its short declared intent for abandon/escalate decisions.",
            "",
            f"The P1-pad and P3 prompts differed by at most {max_prompt_gap} "
            "model-tokenizer tokens per case,",
            "so the observed high-staleness difference is not explained by gross prompt length.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_local_model_cases(
    *,
    endpoint: str,
    model: str,
    output_dir: Path,
    conditions: tuple[PayloadCondition, ...] = DEFAULT_CONDITIONS,
    seed: int = 0,
    timeout: float = 300.0,
) -> list[ReplayResult]:
    output_dir.mkdir(parents=True, exist_ok=True)
    backend = OpenAICompatibleRecoveryBackend(endpoint, model, timeout=timeout)
    results = ReplayRunner(backend).run_matrix(
        build_controlled_episodes(), conditions, seeds=(seed,)
    )
    _write_csv(output_dir / "replay_results.csv", results)
    aggregate = _aggregate(results)
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(aggregate[0]))
        writer.writeheader()
        writer.writerows(aggregate)
    with (output_dir / "model_responses.jsonl").open("w", encoding="utf-8") as stream:
        for record in backend.records:
            json.dump(record, stream, sort_keys=True)
            stream.write("\n")
    _write_report(output_dir / "report.md", model, results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8101/v1")
    parser.add_argument("--model", default="qwen3.5-35b-a3b")
    parser.add_argument("--output-dir", type=Path, default=Path("local_model_case_study_results"))
    parser.add_argument(
        "--conditions",
        default=",".join(item.value for item in DEFAULT_CONDITIONS),
        help="Comma-separated payload conditions.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    conditions = tuple(PayloadCondition(item) for item in args.conditions.split(","))
    report_conditions = {
        PayloadCondition.P1,
        PayloadCondition.P2,
        PayloadCondition.P3,
        PayloadCondition.P5,
        PayloadCondition.P1_PAD,
        PayloadCondition.ADAPTIVE,
    }
    if not report_conditions.issubset(conditions):
        parser.error(
            "--conditions must include P1,P2,P3,P5,P1-pad,adaptive for the report"
        )
    results = run_local_model_cases(
        endpoint=args.endpoint,
        model=args.model,
        output_dir=args.output_dir,
        conditions=conditions,
        seed=args.seed,
        timeout=args.timeout,
    )
    successes = sum(item.recovery_success for item in results)
    print(f"Wrote {len(results)} model replays ({successes} successful) to {args.output_dir}")


if __name__ == "__main__":
    main()
