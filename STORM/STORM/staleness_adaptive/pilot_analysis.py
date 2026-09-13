from __future__ import annotations

import csv
import itertools
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path.name}")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def grouped_outcomes(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups = defaultdict(list)
    for row in rows:
        for split in ("all_exploratory", row["split"]):
            groups[(split, row["challenge"], row["specified_action"], row["length"], row["history"], row["condition"])].append(row)
    summaries = []
    for key, group in sorted(groups.items()):
        result = dict(zip(("split", "challenge", "specified_action", "length", "history", "condition"), key))
        result["n"] = len(group)
        for metric in (
            "route_correct", "verified_recovery", "justified_escalation", "equal_action_composite",
            "failed_revision", "unnecessary_abandonment", "unjustified_escalation", "truncated", "valid_response",
        ):
            values = [row[metric] for row in group if row[metric] is not None]
            result[metric] = mean(values) if values else None
        result["predicted_abandons"] = sum(row["action"] == "abandon" for row in group)
        result["abandon_precision"] = (
            sum(row["action"] == "abandon" and row["route_correct"] for row in group) / result["predicted_abandons"]
            if result["predicted_abandons"] else None
        )
        result["prompt_tokens"] = sum(row["model_prompt_tokens"] for row in group)
        result["completion_tokens"] = sum(row["model_completion_tokens"] for row in group)
        summaries.append(result)
    return summaries


def family_contrasts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if len({row["job_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate continuation rows")
    lookup = {
        (row["case_id"], row["length"], row["history"], row["condition"], row["seed"]): row
        for row in rows
    }
    measures = (
        ("adapt_verified", "adapt", "verified_recovery"),
        ("abandon_verified", "abandon", "verified_recovery"),
        ("escalation_justified", "escalate", "justified_escalation"),
        ("verified_adapt_abandon", None, "verified_recovery"),
        ("route_accuracy", None, "route_correct"),
        ("equal_action_composite", None, "equal_action_composite"),
    )
    effects = []
    for comparator in ("P2", "P3"):
        for name, action, metric in measures:
            cells = defaultdict(lambda: defaultdict(list))
            splits = {}
            for row in rows:
                if row["condition"] != "P1" or action and row["specified_action"] != action or row[metric] is None:
                    continue
                other = lookup[(row["case_id"], row["length"], row["history"], comparator, row["seed"])]
                cells[row["family"]][(row["length"], row["history"])].append(float(other[metric]) - float(row[metric]))
                splits[row["family"]] = row["split"]
            for family, values in sorted(cells.items()):
                if set(values) != set(itertools.product((1024, 12288), ("current", "superseded"))):
                    raise ValueError("incomplete paired context cells")
                cell_means = {key: mean(value) for key, value in values.items()}
                contrasts = {f"L{length}_{history}": value for (length, history), value in cell_means.items()}
                contrasts["overall"] = mean(cell_means.values())
                contrasts["length_interaction"] = mean(
                    cell_means[(12288, history)] - cell_means[(1024, history)]
                    for history in ("current", "superseded")
                )
                contrasts["history_interaction"] = mean(
                    cell_means[(length, "superseded")] - cell_means[(length, "current")]
                    for length in (1024, 12288)
                )
                for contrast, value in contrasts.items():
                    effects.append({
                        "family": family, "split": splits[family], "comparator": comparator,
                        "baseline": "P1", "outcome": name, "contrast": contrast, "difference": value,
                    })
    return effects


def summarize_contrasts(effects: list[dict[str, object]], samples: int = 5000) -> list[dict[str, object]]:
    groups = defaultdict(list)
    for row in effects:
        for split in ("all_exploratory", row["split"]):
            groups[(split, row["comparator"], row["outcome"], row["contrast"])].append(row["difference"])
    summaries = []
    for key, values in sorted(groups.items()):
        generator = random.Random(20260912)
        n = len(values)
        bootstrap = sorted(mean(generator.choices(values, k=n)) for _ in range(samples))
        observed = mean(values)
        signs = itertools.product((-1, 1), repeat=n)
        p_value = sum(
            abs(mean(value * sign for value, sign in zip(values, sample))) >= abs(observed) - 1e-12
            for sample in signs
        ) / 2 ** n
        spread = stdev(values) if n > 1 else None
        summaries.append({
            **dict(zip(("split", "comparator", "outcome", "contrast"), key)),
            "family_count": n, "difference": observed,
            "bootstrap_95_low": bootstrap[int(samples * 0.025)],
            "bootstrap_95_high": bootstrap[min(int(samples * 0.975), samples - 1)],
            "sign_flip_p_unadjusted": p_value,
            "positive_families": sum(value > 0 for value in values),
            "negative_families": sum(value < 0 for value in values),
            "family_sd": spread, "meaningful_effect": 0.10,
            "approx_confirmation_families": math.ceil(((1.96 + 0.84) * spread / 0.10) ** 2) if spread else None,
        })
    return summaries


def write_analysis(output: Path, rows: list[dict[str, object]]) -> None:
    if len(rows) != 864 or any(row.get("transport_error") for row in rows):
        raise ValueError("analysis requires all 864 completed continuations")
    expected_cells = set(itertools.product((1024, 12288), ("current", "superseded"), ("P1", "P2", "P3"), (0, 1)))
    cases = defaultdict(set)
    for row in rows:
        cases[row["case_id"]].add((row["length"], row["history"], row["condition"], row["seed"]))
    if len(cases) != 36 or any(cells != expected_cells for cells in cases.values()):
        raise ValueError("unbalanced continuation grid")
    grouped = grouped_outcomes(rows)
    effects = family_contrasts(rows)
    summaries = summarize_contrasts(effects)
    write_csv(output / "replay_results.csv", rows)
    write_csv(output / "grouped_outcomes.csv", grouped)
    write_csv(output / "family_contrasts.csv", effects)
    write_csv(output / "paired_contrasts.csv", summaries)
    lines = [
        "# Context-by-payload pilot v1", "",
        f"Completed {len(rows)} continuations across twelve families. All effects are exploratory; "
        "nine evaluation families were held out from setup calibration.", "",
        "Verified recovery measures adapt/abandon task and peer behavior. Justified escalation "
        "measures route choice only. Completed coordination is unmeasured. The equal-action "
        "composite averages those different outcomes and is not end-to-end task success.", "",
        f"Actual model cost: {sum(row['model_prompt_tokens'] for row in rows):,} input tokens and "
        f"{sum(row['model_completion_tokens'] for row in rows):,} output tokens. "
        f"Truncated: {sum(row['truncated'] for row in rows)}. "
        f"Invalid responses: {sum(not row['valid_response'] for row in rows)}. "
        "No monetary cost is inferred for local inference.", "",
        "| Payload | Verified adapt/abandon | Route accuracy | Justified escalation | Abandon precision |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition in ("P1", "P2", "P3"):
        selected = [row for row in rows if row["condition"] == condition]
        verified = [row["verified_recovery"] for row in selected if row["verified_recovery"] is not None]
        escalation = [row["justified_escalation"] for row in selected if row["specified_action"] == "escalate"]
        abandons = [row for row in selected if row["action"] == "abandon"]
        precision = f"{sum(row['route_correct'] for row in abandons)}/{len(abandons)}" if abandons else "unmeasured (0)"
        lines.append(f"| {condition} | {mean(verified):.1%} | {mean(row['route_correct'] for row in selected):.1%} | {mean(escalation):.1%} | {precision} |")
    lines += [
        "", "## Predeclared interactions", "",
        "Family bootstrap intervals are exploratory, unadjusted 95% intervals. Seeds are nested "
        "within cases; families, not individual continuations, are the sampling units.", "",
        "| Split | Contrast | Outcome | Payload − P1 | Difference | 95% interval | Families +/− |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in summaries:
        if row["split"] == "development" or row["contrast"] not in ("length_interaction", "history_interaction"):
            continue
        if row["outcome"] not in ("verified_adapt_abandon", "escalation_justified"):
            continue
        lines.append(
            f"| {row['split']} | {row['contrast']} | {row['outcome']} | {row['comparator']} | "
            f"{row['difference']:+.1%} | [{row['bootstrap_95_low']:+.1%}, {row['bootstrap_95_high']:+.1%}] | "
            f"{row['positive_families']}/{row['negative_families']} |"
        )
    lines += [
        "", "All within-action, cell-specific and overall contrasts, sign-flip diagnostics, "
        "family effects and variance-based confirmation size estimates are in the CSV files. "
        "Estimates target a provisional 10-point effect with 80% power and require reassessment "
        "on independent families; zero pilot variance leaves the estimate undefined.", "",
        "These are constructed histories with fixed k4 and authoritative state. A common decline "
        "across payloads is a difficulty effect, not evidence for adaptive payload choice. "
        "Escalation-only differences support route-decision claims, not completed recovery. "
        "No adaptive threshold, router, Priority 3 study, or deployment claim follows from this pilot.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")
