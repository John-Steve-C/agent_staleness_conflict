from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist, mean, stdev


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _read_families(path: Path) -> dict[str, str]:
    families: dict[str, str] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            episode = json.loads(line)
            families[episode["episode_id"]] = episode["metadata"]["scenario"]
    return families


def _as_bool(value: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"expected a CSV boolean, got {value!r}")


def _bootstrap_interval(
    family_differences: dict[str, list[float]], *, seed: int, samples: int = 10000
) -> tuple[float, float]:
    generator = random.Random(seed)
    families = sorted(family_differences)
    estimates: list[float] = []
    for _ in range(samples):
        sampled = [generator.choice(families) for _ in families]
        estimates.append(
            mean(
                difference
                for family in sampled
                for difference in family_differences[family]
            )
        )
    estimates.sort()
    return estimates[int(0.025 * samples)], estimates[int(0.975 * samples)]


def _randomization_p(family_differences: dict[str, list[float]]) -> float:
    families = sorted(family_differences)
    observed = abs(
        mean(value for values in family_differences.values() for value in values)
    )
    as_extreme = 0
    assignments = 1 << len(families)
    for mask in range(assignments):
        randomized = [
            value * (1 if mask & (1 << index) else -1)
            for index, family in enumerate(families)
            for value in family_differences[family]
        ]
        if abs(mean(randomized)) >= observed - 1e-12:
            as_extreme += 1
    return as_extreme / assignments


def _mde(
    baseline_by_family: dict[str, list[float]],
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> tuple[float | None, str]:
    family_rates = [mean(values) for values in baseline_by_family.values()]
    if len(family_rates) < 2:
        return None, "not_estimable_fewer_than_2_clusters"
    observed_sd = stdev(family_rates)
    if observed_sd == 0:
        return None, "not_estimable_saturated_baseline"
    critical = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    value = critical * observed_sd / len(family_rates) ** 0.5
    status = "estimable" if len(family_rates) >= 10 else "fragile_fewer_than_10_clusters"
    return value, status


def action_contrasts(
    rows: list[dict[str, str]], families: dict[str, str]
) -> dict[str, list[dict[str, object]]]:
    indexed: dict[tuple[str, str, str], bool] = {}
    for row in rows:
        key = (row["episode_id"], row["seed"], row["requested_condition"])
        if key in indexed:
            raise ValueError(f"duplicate replay result: {key}")
        indexed[key] = _as_bool(row["recovery_success"])

    baseline = [row for row in rows if row["requested_condition"] == "P1"]
    if not baseline:
        raise ValueError("replay results do not contain the P1 baseline")
    comparators = sorted(
        {row["requested_condition"] for row in rows} - {"P1"}
    )
    actions = sorted({row["correct_action"] for row in baseline})
    output: dict[str, list[dict[str, object]]] = {}

    for action in actions:
        action_baseline = [row for row in baseline if row["correct_action"] == action]
        baseline_by_episode: dict[str, list[float]] = defaultdict(list)
        for row in action_baseline:
            baseline_by_episode[row["episode_id"]].append(
                float(_as_bool(row["recovery_success"]))
            )
        baseline_by_family: dict[str, list[float]] = defaultdict(list)
        for episode_id, values in baseline_by_episode.items():
            baseline_by_family[families[episode_id]].append(mean(values))
        mde, mde_status = _mde(baseline_by_family)

        action_rows: list[dict[str, object]] = []
        for comparator in comparators:
            difference_by_episode: dict[str, list[float]] = defaultdict(list)
            comparator_by_episode: dict[str, list[float]] = defaultdict(list)
            for row in action_baseline:
                key = (row["episode_id"], row["seed"], comparator)
                if key not in indexed:
                    raise ValueError(f"missing paired replay result: {key}")
                comparator_success = float(indexed[key])
                baseline_success = float(_as_bool(row["recovery_success"]))
                difference_by_episode[row["episode_id"]].append(
                    comparator_success - baseline_success
                )
                comparator_by_episode[row["episode_id"]].append(comparator_success)

            family_differences: dict[str, list[float]] = defaultdict(list)
            for episode_id, values in difference_by_episode.items():
                family_differences[families[episode_id]].append(mean(values))
            episode_differences = [
                mean(values) for values in difference_by_episode.values()
            ]
            lower, upper = _bootstrap_interval(
                family_differences,
                seed=20260911 + sum(map(ord, f"{action}:{comparator}")),
            )
            action_rows.append(
                {
                    "correct_action": action,
                    "comparator": comparator,
                    "baseline": "P1",
                    "n_episode_pairs": len(episode_differences),
                    "n_family_clusters": len(family_differences),
                    "baseline_success_rate": mean(
                        mean(values) for values in baseline_by_episode.values()
                    ),
                    "comparator_success_rate": mean(
                        mean(values) for values in comparator_by_episode.values()
                    ),
                    "paired_success_difference": mean(episode_differences),
                    "family_clustered_bootstrap_95_low": lower,
                    "family_clustered_bootstrap_95_high": upper,
                    "family_clustered_randomization_p": _randomization_p(
                        family_differences
                    ),
                    "episode_gains": sum(value > 0 for value in episode_differences),
                    "episode_losses": sum(value < 0 for value in episode_differences),
                    "episode_ties": sum(value == 0 for value in episode_differences),
                    "mde_80pct_power": "" if mde is None else mde,
                    "mde_status": mde_status,
                }
            )
        output[action] = action_rows
    return output


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _format_percentage(value: object) -> str:
    if value == "":
        return "not estimable"
    return f"{100 * float(value):.1f} points"


def write_reanalysis(
    output_dir: Path,
    contrasts: dict[str, list[dict[str, object]]],
    *,
    input_path: Path,
    episodes_path: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for action, rows in contrasts.items():
        _write_csv(output_dir / f"{action}_contrasts.csv", rows)

    summary_rows = [
        {
            "correct_action": action,
            "n_episode_pairs": rows[0]["n_episode_pairs"],
            "n_family_clusters": rows[0]["n_family_clusters"],
            "p1_success_rate": rows[0]["baseline_success_rate"],
            "mde_80pct_power": rows[0]["mde_80pct_power"],
            "mde_status": rows[0]["mde_status"],
        }
        for action, rows in contrasts.items()
    ]
    _write_csv(output_dir / "action_summary.csv", summary_rows)

    mde_lines = [
        "# Stage-C minimum detectable effects",
        "",
        "MDE is the two-sided 5%-alpha, 80%-power normal-approximation planning "
        "threshold, computed as `(z0.975 + z0.80) × SD(P1 family rates) / sqrt(G)`. "
        "Seeds are averaged within episodes and episodes within scenario families. This "
        "uses Stage C's observed between-family P1 variance; it is a sensitivity "
        "diagnostic, not a claim that the small-G normal approximation is reliable.",
        "",
        "| Correct action | Episodes | Family clusters (G) | P1 success | MDE | Status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        mde_lines.append(
            f"| {row['correct_action']} | {row['n_episode_pairs']} | "
            f"{row['n_family_clusters']} | {float(row['p1_success_rate']):.1%} | "
            f"{_format_percentage(row['mde_80pct_power'])} | {row['mde_status']} |"
        )
    mde_lines.extend(
        [
            "",
            "The abandon baseline is saturated at 100%, so its observed variance is "
            "zero and an empirical MDE cannot be estimated. With only four abandon and "
            "two escalate family clusters, exact two-sided family sign-randomization "
            "cannot reach p < 0.05 regardless of effect size. No action stratum can "
            "support a 10-point-effect claim.",
        ]
    )
    (output_dir / "mde.md").write_text("\n".join(mde_lines) + "\n", encoding="utf-8")

    readme_lines = [
        "# Stage-C action-stratified re-analysis",
        "",
        f"Inputs: `{input_path}` and `{episodes_path}`.",
        "",
        "Every non-P1 payload is compared with P1 separately within each correct-action "
        "stratum. Recovery seeds are averaged within an episode; confidence intervals "
        "resample scenario families; randomization tests flip the whole scenario family. "
        "The CSV tables carry the realised episode count, family-cluster count, and MDE "
        "for every contrast.",
        "",
        "## Files",
        "",
        "- `adapt_contrasts.csv`, `abandon_contrasts.csv`, and "
        "`escalate_contrasts.csv`: all action-stratified payload-vs-P1 contrasts.",
        "- `action_summary.csv`: P1 rate, realised cluster count, and planning MDE by action.",
        "- `mde.md`: MDE definition, estimates, and small-cluster limitations.",
        "- `errata.md`: corrected interpretation of the Stage-C gate.",
    ]
    (output_dir / "README.md").write_text(
        "\n".join(readme_lines) + "\n", encoding="utf-8"
    )

    (output_dir / "errata.md").write_text(
        """# Errata to the Stage-C gate decision

The aggregate k-band result is withdrawn as evidence of a staleness crossover.
`correct_action` changes with k: k1–2 contains only adapt items, while k8–16 repeats
the same 2 adapt / 4 abandon / 2 escalate family mix. The apparent P3−P1 reversal
therefore mixes action composition with staleness.

The corpus is also not a discriminating payload instrument. Every content-bearing
payload scores 100% on the abandon items, six adapt families are at ceiling under
P1, and the transaction-escalate family is at floor for all non-directive payloads.
The realised action strata contain only 8 adapt, 4 abandon, and 2 escalate family
clusters. See `mde.md`: the estimable action-level MDEs are far above the planned
10-point effect, and abandon's MDE is not empirically estimable because P1 is
saturated.

Consequently the Stage-C null does not support either equivalence among payloads or
an adaptive policy. No further payload condition should be run on this corpus. The
next payload study is gated on a rebuilt, action-crossed, item-calibrated corpus with
at least 10 family clusters per action cell and realistic receiver context.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    contrasts = action_contrasts(_read_rows(args.input), _read_families(args.episodes))
    write_reanalysis(
        args.output_dir,
        contrasts,
        input_path=args.input,
        episodes_path=args.episodes,
    )


if __name__ == "__main__":
    main()
