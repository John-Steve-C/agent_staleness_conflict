from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path


def _git_diff(repo: Path, left: str, right: str, file_path: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "diff",
            "--no-ext-diff",
            "--unified=20",
            left,
            right,
            "--",
            file_path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return f"Diff unavailable: {result.stderr.strip()}"
    limit = 12000
    if len(result.stdout) <= limit:
        return result.stdout or "(no textual difference)"
    return result.stdout[:limit] + "\n... [truncated; inspect the local repository for the full diff]\n"


def write_adjudication_packets(
    audit_rows: list[dict[str, str]],
    sample_rows: list[dict[str, str]],
    repo_cache_dir: Path,
    output_dir: Path,
) -> None:
    indexed = {
        (row["pr_key"], row["file_path"]): row for row in audit_rows
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for sample in sample_rows:
        row = indexed[(sample["pr_key"], sample["file_path"])]
        repo = repo_cache_dir / row["repo_full_name"].replace("/", "__")
        base_head = _git_diff(
            repo, row["base_oid"], row["head_oid"], row["file_path"]
        )
        head_merge = _git_diff(
            repo, row["head_oid"], row["merge_commit_oid"], row["file_path"]
        )
        lines = [
            f"# {sample['adjudication_id']}",
            "",
            f"- PR: [{sample['pr_key']}]({sample['pr_url']})",
            f"- File: `{sample['file_path']}`",
            f"- Archive resolution evidence: `{sample['resolution_evidence']}`",
            f"- Simulated base: `{row['base_oid']}`",
            f"- Agent head: `{row['head_oid']}`",
            f"- Merge commit: `{row['merge_commit_oid']}`",
            "",
            "## Simulated base → agent head",
            "",
            "```diff",
            base_head.rstrip(),
            "```",
            "",
            "## Agent head → merge result",
            "",
            "```diff",
            head_merge.rstrip(),
            "```",
            "",
            "Record the route, confidence, evidence note, or exclusion reason in "
            "`adjudication_sample.csv`. Do not consult the machine-hypothesis file first.",
        ]
        (output_dir / f"{sample['adjudication_id']}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--repo-cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    sample = _read_csv(args.sample)
    write_adjudication_packets(
        _read_csv(args.audit), sample, args.repo_cache_dir, args.output_dir
    )
    print(f"Wrote {len(sample)} blind adjudication packets to {args.output_dir}")


if __name__ == "__main__":
    main()
