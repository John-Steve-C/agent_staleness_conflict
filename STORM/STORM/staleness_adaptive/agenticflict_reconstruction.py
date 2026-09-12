from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Iterable

from .agenticflict_source_audit import AGENTICFLICT_V2_MD5


MANIFEST_FIELDS = (
    "pr_key",
    "repo_full_name",
    "pr_number",
    "agent",
    "pr_base_oid",
    "pr_head_oid",
    "base_oid",
    "head_oid",
    "merge_commit_oid",
    "merged_at",
    "file_path",
    "file_ext",
    "num_regions_in_file",
    "conflict_lines_in_file",
    "head_last_touch_oid",
    "base_last_touch_oid",
)
ROUTE_HYPOTHESES = {
    "exact_base": (
        "abandon",
        "The agent-head file state was dropped in favor of the simulated base.",
    ),
    "manual_or_combined": (
        "adapt",
        "The resolved file differs from both conflicting sides.",
    ),
    "exact_head": (
        "escalate",
        "The agent-head file state prevailed over the simulated base.",
    ),
}


def build_reconstruction_manifest(
    pr_rows: Iterable[dict[str, str]],
    file_rows: Iterable[dict[str, str]],
    commit_rows: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    merged = {
        str(row["pr_key"]): row
        for row in pr_rows
        if (row.get("conflict_label") or "").lower() == "true"
        and row.get("merged_at")
        and row.get("merge_commit_oid")
    }
    touches = {
        (str(row["pr_key"]), str(row["file_path"])): row
        for row in commit_rows
        if str(row.get("pr_key") or "") in merged
    }
    manifest: list[dict[str, str]] = []
    for file_row in file_rows:
        pr_key = str(file_row.get("pr_key") or "")
        if pr_key not in merged:
            continue
        pr_row = merged[pr_key]
        touch = touches.get((pr_key, str(file_row["file_path"])), {})
        values = {**pr_row, **file_row, **touch}
        values["pr_base_oid"] = pr_row.get("base_oid")
        values["pr_head_oid"] = pr_row.get("head_oid")
        manifest.append(
            {field: str(values.get(field) or "") for field in MANIFEST_FIELDS}
        )
    return sorted(
        manifest,
        key=lambda row: (
            row["repo_full_name"],
            int(row["pr_number"]),
            row["file_path"],
        ),
    )


def classify_blob_resolution(
    base_blob: str, head_blob: str, merge_blob: str
) -> str:
    if not base_blob or not head_blob or not merge_blob:
        return "missing_blob"
    if base_blob == head_blob == merge_blob:
        return "unchanged_sides"
    if merge_blob == base_blob:
        return "exact_base"
    if merge_blob == head_blob:
        return "exact_head"
    return "manual_or_combined"


def classify_tree_resolution(
    base_tree: dict[str, str] | None,
    head_tree: dict[str, str] | None,
    merge_tree: dict[str, str] | None,
    file_path: str,
) -> str:
    if base_tree is None or head_tree is None or merge_tree is None:
        return "missing_commit"
    absent = "<absent>"
    base_state = base_tree.get(file_path, absent)
    head_state = head_tree.get(file_path, absent)
    merge_state = merge_tree.get(file_path, absent)
    if base_state == head_state == merge_state == absent:
        return "absent_all"
    if base_state == head_state == merge_state:
        return "unchanged_sides"
    if merge_state == base_state:
        return "exact_base"
    if merge_state == head_state:
        return "exact_head"
    return "manual_or_combined"


def _archive_rows(archive: tarfile.TarFile, name: str) -> Iterable[dict[str, str]]:
    member = archive.extractfile(name)
    if member is None:
        raise ValueError(f"archive member is not a file: {name}")
    return csv.DictReader(io.TextIOWrapper(member, encoding="utf-8", newline=""))


def load_reconstruction_manifest(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open("rb") as stream:
        archive_md5 = hashlib.file_digest(stream, "md5").hexdigest()
    if archive_md5 != AGENTICFLICT_V2_MD5:
        raise ValueError(
            f"AgenticFlict v2 checksum mismatch: expected {AGENTICFLICT_V2_MD5}, "
            f"got {archive_md5}"
        )
    with tarfile.open(path) as archive:
        prs = list(_archive_rows(archive, "data/raw/agenticflict_pr_raw.csv"))
        files = _archive_rows(archive, "data/raw/agenticflict_conflict_files_raw.csv")
        commits = list(
            _archive_rows(
                archive, "data/raw/agenticflict_conflict_file_commits_raw.csv"
            )
        )
        return build_reconstruction_manifest(prs, files, commits)


def _tree_blobs(repo: Path, commit: str) -> dict[str, str] | None:
    if not commit:
        return None
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "-z", "--full-tree", commit],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return None
    blobs: dict[str, str] = {}
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        _, object_type, oid = metadata.split(b" ", 2)
        if object_type == b"blob":
            blobs[path.decode("utf-8", errors="surrogateescape")] = oid.decode("ascii")
    return blobs


def audit_local_repositories(
    manifest: Iterable[dict[str, str]], repo_cache_dir: Path
) -> list[dict[str, str]]:
    tree_cache: dict[tuple[Path, str], dict[str, str] | None] = {}
    results: list[dict[str, str]] = []
    for row in manifest:
        repo = repo_cache_dir / row["repo_full_name"].replace("/", "__")
        available = (repo / "HEAD").is_file()
        trees: list[dict[str, str] | None] = []
        for commit_field in ("base_oid", "head_oid", "merge_commit_oid"):
            key = (repo, row[commit_field])
            if available and key not in tree_cache:
                tree_cache[key] = _tree_blobs(*key)
            trees.append(tree_cache.get(key))
        base_tree, head_tree, merge_tree = trees
        base_blob = (base_tree or {}).get(row["file_path"], "")
        head_blob = (head_tree or {}).get(row["file_path"], "")
        merge_blob = (merge_tree or {}).get(row["file_path"], "")
        results.append(
            {
                **row,
                "repository_available": str(available),
                "base_commit_available": str(base_tree is not None),
                "head_commit_available": str(head_tree is not None),
                "merge_commit_available": str(merge_tree is not None),
                "base_path_present": str(row["file_path"] in (base_tree or {})),
                "head_path_present": str(row["file_path"] in (head_tree or {})),
                "merge_path_present": str(row["file_path"] in (merge_tree or {})),
                "base_blob_oid": base_blob,
                "head_blob_oid": head_blob,
                "merge_blob_oid": merge_blob,
                "resolution_evidence": classify_tree_resolution(
                    base_tree, head_tree, merge_tree, row["file_path"]
                ),
            }
        )
    return results


def build_adjudication_sample(
    audit: Iterable[dict[str, str]], per_evidence: int = 10
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    rows = list(audit)
    for evidence in ROUTE_HYPOTHESES:
        by_repo: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            if row["resolution_evidence"] == evidence:
                by_repo.setdefault(row["repo_full_name"], []).append(row)
        for candidates in by_repo.values():
            candidates.sort(key=lambda row: (int(row["pr_number"]), row["file_path"]))
        while (
            len(
                [row for row in selected if row["resolution_evidence"] == evidence]
            )
            < per_evidence
        ):
            progressed = False
            for repo in sorted(by_repo):
                if not by_repo[repo]:
                    continue
                row = by_repo[repo].pop(0)
                selected.append(
                    {
                        "adjudication_id": f"S3-{len(selected) + 1:03d}",
                        "pr_key": row["pr_key"],
                        "pr_url": (
                            f"https://github.com/{row['repo_full_name']}/pull/"
                            f"{row['pr_number']}"
                        ),
                        "file_path": row["file_path"],
                        "resolution_evidence": evidence,
                        "human_route": "",
                        "human_confidence": "",
                        "reviewer_notes": "",
                        "exclude_reason": "",
                    }
                )
                progressed = True
                if (
                    len(
                        [
                            item
                            for item in selected
                            if item["resolution_evidence"] == evidence
                        ]
                    )
                    >= per_evidence
                ):
                    break
            if not progressed:
                break
    return selected


def build_machine_hypotheses(
    adjudication: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "adjudication_id": row["adjudication_id"],
            "resolution_evidence": row["resolution_evidence"],
            "machine_route_hypothesis": ROUTE_HYPOTHESES[
                row["resolution_evidence"]
            ][0],
            "machine_rationale": ROUTE_HYPOTHESES[row["resolution_evidence"]][1],
        }
        for row in adjudication
    ]


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty reconstruction table")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-cache-dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_reconstruction_manifest(args.archive)
    _write_csv(args.output_dir / "merged_conflict_manifest.csv", manifest)
    summary: dict[str, object] = {
        "merged_pr_count": len({row["pr_key"] for row in manifest}),
        "conflict_file_count": len(manifest),
        "repository_count": len({row["repo_full_name"] for row in manifest}),
    }
    if args.repo_cache_dir is not None:
        audit = audit_local_repositories(manifest, args.repo_cache_dir)
        _write_csv(args.output_dir / "blob_resolution_audit.csv", audit)
        counts: dict[str, int] = {}
        available_rows = [
            row for row in audit if row["repository_available"] == "True"
        ]
        for row in available_rows:
            evidence = row["resolution_evidence"]
            counts[evidence] = counts.get(evidence, 0) + 1
        summary["available_blob_resolution_evidence"] = dict(sorted(counts.items()))
        summary["available_conflict_file_count"] = len(available_rows)
        summary["available_merged_pr_count"] = len(
            {row["pr_key"] for row in available_rows}
        )
        summary["available_repository_count"] = len(
            {row["repo_full_name"] for row in available_rows}
        )
        summary["unavailable_repositories"] = sorted(
            {
                row["repo_full_name"]
                for row in audit
                if row["repository_available"] != "True"
            }
        )
        adjudication = build_adjudication_sample(audit)
        _write_csv(args.output_dir / "adjudication_sample.csv", adjudication)
        _write_csv(
            args.output_dir / "adjudication_machine_hypotheses.csv",
            build_machine_hypotheses(adjudication),
        )
        summary["adjudication_sample_count"] = len(adjudication)
    (args.output_dir / "reconstruction_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
