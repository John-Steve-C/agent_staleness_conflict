from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


REQUIRED_ACTIONS = {"adapt", "abandon", "escalate"}


def _as_bool(value: str | bool) -> bool:
    if value is True or value == "True":
        return True
    if value is False or value == "False":
        return False
    raise ValueError(f"expected a CSV boolean, got {value!r}")


def _invalid_response(row: dict[str, str]) -> bool:
    return str(row.get("notes", "")).startswith("Invalid model response:")


def _read_episodes(path: Path) -> dict[str, dict[str, object]]:
    episodes: dict[str, dict[str, object]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            episode = json.loads(line)
            episodes[episode["episode_id"]] = episode
    return episodes


def _read_results(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def audit_candidate_structure(
    episodes: dict[str, dict[str, object]],
) -> dict[str, object]:
    cells: set[tuple[str, str, int]] = set()
    families: set[str] = set()
    levels: set[int] = set()
    for episode_id, episode in episodes.items():
        metadata = episode.get("metadata", {})
        family = str(metadata.get("family") or metadata.get("scenario") or "")
        if not family:
            raise ValueError(f"episode has no family metadata: {episode_id}")
        action_value = episode["correct_action"]
        action = str(getattr(action_value, "value", action_value))
        k = int(episode["staleness"]["edit_distance_writes"])
        families.add(family)
        levels.add(k)
        cells.add((family, action, k))
    missing = [
        {"family": family, "correct_action": action, "k": k}
        for family in sorted(families)
        for action in sorted(REQUIRED_ACTIONS)
        for k in sorted(levels)
        if (family, action, k) not in cells
    ]
    return {
        "candidate_family_count": len(families),
        "candidate_episode_count": len(episodes),
        "staleness_levels": sorted(levels),
        "action_staleness_fully_crossed": not missing,
        "missing_crossed_cell_count": len(missing),
        "missing_crossed_cells": missing,
    }


def calibrate_items(
    episodes: dict[str, dict[str, object]],
    results: list[dict[str, str]],
    *,
    minimum_context_tokens: int = 8000,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    p1_results = [row for row in results if row["requested_condition"] == "P1"]
    result_by_episode: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in p1_results:
        if row["episode_id"] not in episodes:
            raise ValueError(f"result references unknown episode: {row['episode_id']}")
        result_by_episode[row["episode_id"]].append(row)

    family_outcomes: dict[str, list[bool]] = defaultdict(list)
    episode_details: dict[str, tuple[str, str, int]] = {}
    for episode_id, episode in episodes.items():
        metadata = episode.get("metadata", {})
        family = str(metadata.get("family") or metadata.get("scenario") or "")
        if not family:
            raise ValueError(f"episode has no family metadata: {episode_id}")
        action_value = episode["correct_action"]
        action = str(getattr(action_value, "value", action_value))
        k = int(episode["staleness"]["edit_distance_writes"])
        episode_details[episode_id] = family, action, k
        family_outcomes[family].extend(
            _as_bool(row["recovery_success"])
            for row in result_by_episode.get(episode_id, [])
            if not _invalid_response(row)
        )

    family_has_variance = {
        family: len(set(outcomes)) > 1 for family, outcomes in family_outcomes.items()
    }
    decisions: list[dict[str, object]] = []
    for episode_id in sorted(episodes):
        family, action, k = episode_details[episode_id]
        rows = result_by_episode.get(episode_id, [])
        invalid_rows = [row for row in rows if _invalid_response(row)]
        valid_rows = [row for row in rows if not _invalid_response(row)]
        outcomes = [_as_bool(row["recovery_success"]) for row in valid_rows]
        success_rate = mean(outcomes) if outcomes else None
        contexts = [
            int(
                row.get("receiver_trajectory_tokens")
                or row.get("receiver_context_target_tokens")
                or 0
            )
            for row in rows
        ]
        realised_context = min(contexts) if contexts else 0
        reasons: list[str] = []
        if not rows:
            reasons.append("missing_p1_pilot")
        if invalid_rows:
            reasons.append("invalid_model_response")
        if realised_context < minimum_context_tokens:
            reasons.append(f"context_below_{minimum_context_tokens}")
        if not family_has_variance.get(family, False):
            reasons.append("zero_within_family_variance")
        if success_rate is not None and not 0.30 <= success_rate <= 0.70:
            reasons.append("outside_30_70_band")
        admitted = not reasons
        decisions.append(
            {
                "episode_id": episode_id,
                "family": family,
                "correct_action": action,
                "k": k,
                "n_seeds": len(rows),
                "n_valid_seeds": len(valid_rows),
                "invalid_response_count": len(invalid_rows),
                "p1_success_rate": "" if success_rate is None else success_rate,
                "minimum_realised_context_tokens": realised_context,
                "within_family_variance": family_has_variance.get(family, False),
                "in_40_70_band": (
                    success_rate is not None and 0.40 <= success_rate <= 0.70
                ),
                "floor_control": (
                    success_rate is not None
                    and not invalid_rows
                    and success_rate == 0
                ),
                "admitted": admitted,
                "exclusion_reasons": ";".join(reasons),
            }
        )

    structure = audit_candidate_structure(episodes)
    admitted = [row for row in decisions if row["admitted"]]
    action_clusters = {
        action: len(
            {
                str(row["family"])
                for row in admitted
                if row["correct_action"] == action
            }
        )
        for action in sorted(REQUIRED_ACTIONS)
    }
    calibrated_fraction = (
        mean(bool(row["in_40_70_band"]) for row in admitted) if admitted else 0.0
    )
    invalid_response_count = sum(
        _invalid_response(row) for row in p1_results
    )
    all_pilots_meet_minimum_context = all(
        int(row["minimum_realised_context_tokens"]) >= minimum_context_tokens
        for row in decisions
    )
    gate = {
        "passed": (
            int(structure["candidate_family_count"]) >= 30
            and bool(structure["action_staleness_fully_crossed"])
            and all(count >= 10 for count in action_clusters.values())
            and calibrated_fraction >= 0.60
            and all_pilots_meet_minimum_context
        ),
        **structure,
        "admitted_item_count": len(admitted),
        "floor_control_count": sum(bool(row["floor_control"]) for row in decisions),
        "admitted_fraction_in_40_70_band": calibrated_fraction,
        "admitted_family_clusters_by_action": action_clusters,
        "minimum_context_tokens": minimum_context_tokens,
        "all_pilots_meet_minimum_context": all_pilots_meet_minimum_context,
        "invalid_response_count": invalid_response_count,
        "items_with_invalid_response_count": sum(
            int(row["invalid_response_count"]) > 0 for row in decisions
        ),
        "invalid_response_fraction": (
            invalid_response_count / len(p1_results) if p1_results else 0.0
        ),
    }
    return decisions, gate


def write_calibration(
    output_dir: Path,
    decisions: list[dict[str, object]],
    gate: dict[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "item_decisions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(decisions[0]))
        writer.writeheader()
        writer.writerows(decisions)
    (output_dir / "gate_c_prime.json").write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    status = "PASS" if gate["passed"] else "FAIL"
    lines = [
        "# Gate C′ item-calibration report",
        "",
        f"**Gate C′: {status}.**",
        "",
        f"- Candidate families: {gate['candidate_family_count']} (required: ≥30).",
        f"- Action × staleness fully crossed: {gate['action_staleness_fully_crossed']}.",
        f"- Missing crossed cells: {gate['missing_crossed_cell_count']}.",
        f"- Admitted items: {gate['admitted_item_count']}.",
        f"- Admitted items in the 40–70% P1 band: "
        f"{float(gate['admitted_fraction_in_40_70_band']):.1%} (required: ≥60%).",
        f"- Minimum receiver context: {gate['minimum_context_tokens']} tokens; all pilots "
        f"meet it: {gate['all_pilots_meet_minimum_context']}.",
        f"- Invalid or truncated model responses: {gate['invalid_response_count']} "
        f"({float(gate['invalid_response_fraction']):.1%}).",
        f"- Items excluded for an invalid response: "
        f"{gate['items_with_invalid_response_count']}.",
        "- Admitted family clusters by action: "
        + ", ".join(
            f"{action}={count}"
            for action, count in gate["admitted_family_clusters_by_action"].items()
        )
        + " (required: ≥10 each).",
        "",
        "Floor items remain labelled controls and are excluded from payload contrasts. "
        "`item_decisions.csv` records every admission decision and reason.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-context-tokens", type=int, default=8000)
    args = parser.parse_args()
    decisions, gate = calibrate_items(
        _read_episodes(args.episodes),
        _read_results(args.results),
        minimum_context_tokens=args.minimum_context_tokens,
    )
    write_calibration(args.output_dir, decisions, gate)
    print(f"Gate C': {'PASS' if gate['passed'] else 'FAIL'}")


if __name__ == "__main__":
    main()
