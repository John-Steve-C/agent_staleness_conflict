from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import os
import random
import shlex
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .local_model import _extract_json
from .pilot_analysis import write_analysis
from .pilot_context import (
    CONDITIONS, HISTORIES, LENGTHS, OUTPUT_TOKENS, SERVER_LIMIT,
    ModelTokenizer, build_context_prompt,
)
from .pilot_corpus import CORPUS_VERSION, audit_corpus, build_pilot_corpus, score_response


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def read_checkpoint(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    records = {}
    with path.open("rb+") as handle:
        while line := handle.readline():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                if line.endswith(b"\n"):
                    raise ValueError(f"corrupt checkpoint: {path}")
                handle.truncate(handle.tell() - len(line))
                break
            previous = records.get(record["job_id"])
            if previous and not previous.get("transport_error"):
                raise ValueError("duplicate completed job in checkpoint")
            records[record["job_id"]] = record
            if not line.endswith(b"\n"):
                handle.write(b"\n")
    return records


def _append_record(path: Path, record: dict[str, object]) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def request_completion(endpoint: str, job: dict[str, object], timeout: float) -> dict[str, object]:
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps(job["request"]).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        method="POST",
    )
    started = time.monotonic()
    record = {"job_id": job["job_id"], "request_hash": _digest(job["request"])}
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            record["response"] = json.load(response)
        body = record["response"]
        choice = body["choices"][0]
        usage = body["usage"]
        if int(usage["prompt_tokens"]) != job["prompt_tokens"]:
            raise ValueError("server/tokenizer prompt count mismatch")
        if not 0 <= int(usage["completion_tokens"]) <= OUTPUT_TOKENS:
            raise ValueError("server exceeded output allowance")
        record["finish_reason"] = choice["finish_reason"]
        record["truncated"] = choice["finish_reason"] == "length" or int(usage["completion_tokens"]) >= OUTPUT_TOKENS
        try:
            record["parsed"] = _extract_json(choice["message"]["content"] or "")
        except (TypeError, ValueError) as exc:
            record["parsed"] = None
            record["parse_error"] = f"{type(exc).__name__}: {exc}"
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as exc:
        record["transport_error"] = f"{type(exc).__name__}: {exc}"
    record["elapsed_seconds"] = time.monotonic() - started
    return record


def prepare(args: argparse.Namespace) -> tuple[list, list[dict[str, object]], dict[str, object]]:
    tokenizer = ModelTokenizer(args.model_path)
    cases = build_pilot_corpus()
    audit = audit_corpus(cases)
    references = [tokenizer.count(json.dumps({
        "action": "adapt", "revised_content": case.reference,
        "explanation": "Implemented requirements and preserved peer behavior.",
    })) for case in cases]
    if max(references) > OUTPUT_TOKENS:
        raise ValueError("reference outputs exceed common allowance")
    audit["max_reference_output_tokens"] = max(references)
    jobs = []
    for case in cases:
        for length, history in itertools.product(LENGTHS, HISTORIES):
            matched = []
            authoritative = case.public.current
            for condition in CONDITIONS:
                prompt = build_context_prompt(case.public, condition, history, length, tokenizer)
                assert case.public.current == authoritative
                matched.append(prompt.prompt_tokens)
                metadata = asdict(prompt)
                messages = metadata.pop("messages")
                metadata.pop("relevant_history")
                for seed in (0, 1):
                    job_id = f"{case.case_id}:{length}:{history}:{condition}:{seed}"
                    jobs.append({
                        "job_id": job_id, "case_id": case.case_id,
                        "length": length, "history": history, "condition": condition, "seed": seed,
                        **metadata,
                        "request": {
                            "model": args.model, "messages": messages, "seed": seed,
                            "temperature": 0.4, "top_p": 0.8, "max_tokens": OUTPUT_TOKENS,
                            "response_format": {"type": "json_object"},
                            "chat_template_kwargs": {"enable_thinking": False},
                        },
                    })
            if (max(matched) - min(matched)) / length > 0.02:
                raise ValueError("payload inputs are not matched within 2%")
    audit.update({
        "prompt_count": len(jobs) // 2, "continuation_count": len(jobs),
        "prompt_token_range": [min(job["prompt_tokens"] for job in jobs), max(job["prompt_tokens"] for job in jobs)],
        "max_input_plus_output": max(job["prompt_tokens"] for job in jobs) + OUTPUT_TOKENS,
        "relevant_position_range": [min(job["relevant_start_fraction"] for job in jobs), max(job["relevant_start_fraction"] for job in jobs)],
        "output_allowance": OUTPUT_TOKENS, "server_limit": SERVER_LIMIT,
    })
    return cases, jobs, audit


def run(args: argparse.Namespace) -> None:
    if not 1 <= args.workers <= 4:
        raise ValueError("workers must be between one and four")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / "config.json"
    if config_path.exists() and not args.resume:
        raise ValueError("existing experiment: choose a unique directory or use --resume")
    if args.resume and not config_path.exists():
        raise ValueError("no experiment configuration to resume")
    cases, jobs, audit = prepare(args)
    model_path = Path(args.model_path)
    fingerprints = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            Path(__file__), Path(__file__).with_name("pilot_corpus.py"),
            Path(__file__).with_name("pilot_context.py"), Path(__file__).with_name("pilot_analysis.py"),
            model_path / "tokenizer.json", model_path / "tokenizer_config.json",
            model_path / "chat_template.jinja", model_path / "config.json",
        )
    }
    config = {
        "corpus_version": CORPUS_VERSION, "corpus_hash": _digest([asdict(case) for case in cases]),
        "jobs_hash": _digest(jobs), "fingerprints": fingerprints,
        "model": args.model, "model_path": str(model_path.resolve()), "endpoint": args.endpoint,
        "workers": args.workers, "timeout": args.timeout,
        "k": 4, "lengths": LENGTHS, "histories": HISTORIES, "conditions": CONDITIONS,
        "seeds": [0, 1], "temperature": 0.4, "top_p": 0.8,
        "output_tokens": OUTPUT_TOKENS, "server_limit": SERVER_LIMIT,
        "continuations": 864, "calibration_calls": 6,
        "practically_meaningful_effect": 0.10,
        "tokenizer_versions": {name: importlib.metadata.version(name) for name in ("transformers", "tokenizers")},
    }
    # JSON round-trip normalizes tuples for exact resume comparison.
    config = json.loads(json.dumps(config))
    if config_path.exists():
        saved = json.loads(config_path.read_text())
        saved.pop("created_at")
        if saved != config:
            raise ValueError("resume configuration, corpus, source, or prompts changed")
    else:
        _write_json(config_path, {**config, "created_at": datetime.now(UTC).isoformat()})
        (output / "corpus.jsonl").write_text("".join(json.dumps(asdict(case)) + "\n" for case in cases))
        (output / "requests.jsonl").write_text("".join(json.dumps(job) + "\n" for job in jobs))
        command = [sys.executable, "-m", "staleness_adaptive.context_study", "--output-dir", str(output),
                   "--model-path", args.model_path, "--model", args.model, "--endpoint", args.endpoint,
                   "--workers", str(args.workers), "--timeout", str(args.timeout), "--resume"]
        (output / "resume_command.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\ncd " + shlex.quote(str(Path.cwd())) + "\n" + shlex.join(command) + "\n")
    _write_json(output / "gates.json", audit)
    print(json.dumps(audit), flush=True)
    if args.prepare_only:
        return

    with urllib.request.urlopen(args.endpoint.rstrip("/") + "/models", timeout=args.timeout) as response:
        server_models = json.load(response)
    served = next((model for model in server_models["data"] if model["id"] == args.model), None)
    if served is None or served.get("max_model_len") != SERVER_LIMIT:
        raise ValueError("server must expose the requested model with the saved 16384-token limit")
    if served.get("root") and Path(served["root"]).resolve() != model_path.resolve():
        raise ValueError("server model path differs from tokenizer/model provenance")
    _write_json(output / "server.json", server_models)

    # A small development-only setup check, never used to select corpus rows.
    development_ids = {case.case_id for case in cases if case.family == "bounded_percentage"}
    calibration_jobs = []
    for job in jobs:
        if job["case_id"] in development_ids and job["history"] == "current" and job["condition"] == "P1" and job["seed"] == 0:
            calibration_jobs.append({**job, "job_id": "calibration:" + job["job_id"],
                                     "request": {**job["request"], "seed": 117}})
    calibration = _execute(args, calibration_jobs, output / "calibration.jsonl")
    if any(record.get("transport_error") or record.get("truncated") or record.get("parsed") is None for record in calibration.values()):
        raise ValueError("calibration failed: inspect calibration.jsonl before inference")
    _write_json(output / "calibration_gate.json", {
        "passed": True, "calls": len(calibration), "token_counts_match_server": True,
        "truncations": 0,
    })
    records = _execute(args, jobs, output / "model_responses.jsonl")
    errors = sum(bool(record.get("transport_error")) for record in records.values())
    if errors:
        raise ValueError(f"{errors} infrastructure errors; resume to retry them before analysis")
    by_id = {case.case_id: case for case in cases}
    rows = []
    for job in jobs:
        record = records[job["job_id"]]
        case = by_id[job["case_id"]]
        usage = record["response"]["usage"]
        rows.append({
            **{key: value for key, value in job.items() if key != "request"},
            "family": case.family, "split": case.split, "challenge": case.challenge,
            "specified_action": case.acceptable_actions[0],
            **score_response(case, record["parsed"], truncated=record["truncated"]),
            "model_prompt_tokens": int(usage["prompt_tokens"]),
            "model_completion_tokens": int(usage["completion_tokens"]),
            "finish_reason": record["finish_reason"], "elapsed_seconds": record["elapsed_seconds"],
        })
    write_analysis(output, rows)
    _write_json(output / "postrun_audit.json", {
        "passed": True, "completed_continuations": len(rows), "infrastructure_errors": 0,
        "token_counts_match_server": True,
        "truncations": sum(row["truncated"] for row in rows),
        "invalid_responses": sum(not row["valid_response"] for row in rows),
        "completed_coordination": "unmeasured",
    })
    print(f"Completed primary study: {output / 'report.md'}", flush=True)


def _execute(args: argparse.Namespace, jobs: list[dict[str, object]], path: Path) -> dict[str, dict[str, object]]:
    records = read_checkpoint(path)
    by_id = {job["job_id"]: job for job in jobs}
    for key, record in records.items():
        if key not in by_id or record["request_hash"] != _digest(by_id[key]["request"]):
            raise ValueError("checkpoint request does not match frozen job")
    pending = [job for job in jobs if job["job_id"] not in records or records[job["job_id"]].get("transport_error")]
    random.Random(20260912).shuffle(pending)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(request_completion, args.endpoint, job, args.timeout): job for job in pending}
        for future in as_completed(futures):
            record = future.result()
            _append_record(path, record)
            records[record["job_id"]] = record
            if record.get("transport_error"):
                print(f"Infrastructure error {record['job_id']}: {record['transport_error']}", flush=True)
            if len(records) % 24 == 0 or len(records) == len(jobs):
                print(f"{path.name}: {len(records)}/{len(jobs)} checkpointed", flush=True)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Versioned Priority 1/2 context-by-payload pilot")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8102/v1")
    parser.add_argument("--model", default="qwen3.5-35b-a3b")
    parser.add_argument("--model-path", default="/shared/models/hf/Qwen3.5-35B-A3B")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
