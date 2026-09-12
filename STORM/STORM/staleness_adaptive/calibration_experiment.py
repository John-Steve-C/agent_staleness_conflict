from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from .episode_log import EpisodeLog
from .item_calibration import (
    audit_candidate_structure,
    calibrate_items,
    write_calibration,
)
from .local_model import OpenAICompatibleRecoveryBackend
from .models import ConflictEpisode, PayloadCondition, RefusalPosition, ReplayResult
from .payloads import PayloadRenderer, TokenizerJsonCounter
from .replay import ReplayRunner


def _run_p1_pilot(
    episodes: list[ConflictEpisode],
    runner: ReplayRunner,
    *,
    seeds: tuple[int, ...],
    context_length: int,
    workers: int,
) -> list[ReplayResult]:
    jobs = [(episode, seed) for episode in episodes for seed in seeds]
    results: list[ReplayResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                runner.run,
                episode,
                PayloadCondition.P1,
                seed=seed,
                receiver_context_tokens=context_length,
                refusal_position=RefusalPosition.TAIL,
            ): (episode.episode_id, seed)
            for episode, seed in jobs
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if completed % 100 == 0 or completed == len(jobs):
                print(f"Completed {completed}/{len(jobs)} P1 calibrations", flush=True)
    results.sort(key=lambda item: (item.episode_id, item.seed))
    return results


def _write_csv(path: Path, results: list[ReplayResult]) -> None:
    rows = [item.to_dict() for item in results]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_calibration(args: argparse.Namespace) -> list[ReplayResult]:
    if args.context_length < 8000:
        raise ValueError("corpus calibration requires at least 8000 receiver tokens")
    episodes = EpisodeLog(args.episodes).read()
    episode_dict = {item.episode_id: item.to_dict() for item in episodes}
    structure = audit_candidate_structure(episode_dict)
    if int(structure["candidate_family_count"]) < 30:
        raise ValueError("candidate corpus must contain at least 30 scenario families")
    if not structure["action_staleness_fully_crossed"]:
        raise ValueError("candidate corpus must fully cross action with staleness")

    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    seeds = tuple(int(item) for item in args.seeds.split(","))
    config = {
        "created_at": datetime.now(UTC).isoformat(),
        "endpoint": args.endpoint,
        "model": args.model,
        "tokenizer_path": str(args.tokenizer_path),
        "candidate_structure": structure,
        "condition": PayloadCondition.P1.value,
        "seeds": list(seeds),
        "receiver_context_tokens": args.context_length,
        "refusal_position": RefusalPosition.TAIL.value,
        "workers": args.workers,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "planned_effect": 0.10,
        "admission_band": [0.30, 0.70],
        "gate_band": [0.40, 0.70],
    }
    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    EpisodeLog(output_dir / "episodes.jsonl").write(episodes)

    backend = OpenAICompatibleRecoveryBackend(
        args.endpoint,
        args.model,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
    )
    results = _run_p1_pilot(
        episodes,
        ReplayRunner(
            backend,
            PayloadRenderer(token_counter=TokenizerJsonCounter(args.tokenizer_path)),
        ),
        seeds=seeds,
        context_length=args.context_length,
        workers=args.workers,
    )
    _write_csv(output_dir / "replay_results.csv", results)
    with (output_dir / "model_responses.jsonl").open("w", encoding="utf-8") as stream:
        for record in sorted(
            backend.records, key=lambda item: (item["episode_id"], item["seed"])
        ):
            json.dump(record, stream, sort_keys=True)
            stream.write("\n")
    decisions, gate = calibrate_items(episode_dict, [item.to_dict() for item in results])
    write_calibration(output_dir, decisions, gate)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8102/v1")
    parser.add_argument("--model", default="qwen3.5-35b-a3b")
    parser.add_argument(
        "--tokenizer-path",
        type=Path,
        default=Path("/shared/models/hf/Qwen3.5-35B-A3B/tokenizer.json"),
    )
    parser.add_argument("--seeds", default="0,1,2,3,4,5,6,7,8,9")
    parser.add_argument("--context-length", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    results = run_calibration(args)
    print(f"Wrote {len(results)} P1 calibrations to {args.output_dir}")


if __name__ == "__main__":
    main()
