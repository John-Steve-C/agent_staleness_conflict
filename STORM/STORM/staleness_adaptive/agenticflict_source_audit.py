from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import tarfile
from collections import Counter
from pathlib import Path
from typing import Iterable


AGENTICFLICT_V2_MD5 = "1d6b79f1fed77c39e195b116cd2ad46d"


def summarize_prs(rows: Iterable[dict[str, str]]) -> dict[str, object]:
    total = 0
    conflicts = 0
    conflict_states: Counter[str] = Counter()
    merged_conflicts = 0
    for row in rows:
        total += 1
        if (row.get("conflict_label") or "").lower() != "true":
            continue
        conflicts += 1
        conflict_states[row.get("gh_state") or "missing"] += 1
        merged_conflicts += bool(row.get("merged_at"))
    return {
        "pr_count": total,
        "conflicting_pr_count": conflicts,
        "conflicting_pr_states": dict(sorted(conflict_states.items())),
        "conflicting_prs_with_merged_at": merged_conflicts,
    }


def summarize_regions(rows: Iterable[dict[str, str]]) -> dict[str, object]:
    total = 0
    full_text = 0
    paired_previews = 0
    for row in rows:
        total += 1
        full_text += bool(row.get("ours_text")) and bool(row.get("theirs_text"))
        paired_previews += bool(row.get("ours_preview")) and bool(
            row.get("theirs_preview")
        )
    return {
        "region_count": total,
        "regions_with_both_full_texts": full_text,
        "regions_with_both_previews": paired_previews,
    }


def _csv_rows(
    archive: tarfile.TarFile, name: str
) -> tuple[list[str], Iterable[dict[str, str]]]:
    member = archive.extractfile(name)
    if member is None:
        raise ValueError(f"archive member is not a file: {name}")
    stream = io.TextIOWrapper(member, encoding="utf-8", newline="")
    reader = csv.DictReader(stream)
    return list(reader.fieldnames or []), reader


def audit_archive(path: Path) -> dict[str, object]:
    csv.field_size_limit(sys.maxsize)
    with path.open("rb") as stream:
        archive_md5 = hashlib.file_digest(stream, "md5").hexdigest()
    if archive_md5 != AGENTICFLICT_V2_MD5:
        raise ValueError(
            f"AgenticFlict v2 checksum mismatch: expected {AGENTICFLICT_V2_MD5}, "
            f"got {archive_md5}"
        )
    with tarfile.open(path) as archive:
        pr_name = "data/raw/agenticflict_pr_raw.csv"
        region_name = "data/raw/agenticflict_regions_raw.csv"
        pr_fields, pr_rows = _csv_rows(archive, pr_name)
        pr_summary = summarize_prs(pr_rows)
        region_fields, region_rows = _csv_rows(archive, region_name)
        region_summary = summarize_regions(region_rows)

    resolution_fields = {
        "recovery_action",
        "resolution_action",
        "resolution_label",
        "resolved_content",
        "revert_commit_oid",
        "contested",
    }
    available_resolution_fields = sorted(resolution_fields & set(pr_fields + region_fields))
    return {
        "archive": str(path),
        "archive_md5": archive_md5,
        "checksum_verified": True,
        "pr_table_columns": pr_fields,
        "region_table_columns": region_fields,
        **pr_summary,
        **region_summary,
        "available_direct_resolution_fields": available_resolution_fields,
        "three_class_route_label_available": bool(available_resolution_fields),
        "routing_features_available_without_repo_mining": {
            "staleness": ["base_oid", "head_oid"],
            "context": [],
            "task_semantics": [],
            "repo_graph": ["file_path"],
            "history": ["gh_state", "created_at", "closed_at", "merged_at"],
        },
    }


def write_audit(output_dir: Path, audit: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    states = audit["conflicting_pr_states"]
    lines = [
        "# RecoveryRoute-Bench source audit",
        "",
        "Source: AgenticFlict v2, Zenodo record 20118379 (CC-BY-4.0). The archive "
        "checksum was verified before this audit.",
        "",
        f"- PRs: {int(audit['pr_count']):,}; conflicting: "
        f"{int(audit['conflicting_pr_count']):,}.",
        "- Conflicting PR states: "
        + ", ".join(f"{state}={count:,}" for state, count in states.items())
        + ".",
        f"- Conflicting PRs with `merged_at`: "
        f"{int(audit['conflicting_prs_with_merged_at']):,}.",
        f"- Conflict regions: {int(audit['region_count']):,}; both full-text sides "
        f"present: {int(audit['regions_with_both_full_texts']):,}; both short previews "
        f"present: {int(audit['regions_with_both_previews']):,}.",
        "",
        "## Gate status",
        "",
        "The archive does not contain an `abandon` / `adapt` / `escalate` outcome, "
        "resolved file content, revert link, or contested-resolution field. PR state is "
        "not a valid substitute: a closed-unmerged PR can be dropped for reasons unrelated "
        "to its conflict, and an open PR is right-censored rather than escalated. Only 55 "
        "conflicting PRs carry `merged_at`, and even those require repository history to "
        "distinguish adaptation from a manual merge resolution.",
        "",
        "Therefore the routing ceiling cannot yet be estimated from AgenticFlict alone. "
        "The next valid S3 step is to reconstruct selected repositories at `base_oid`, "
        "`head_oid`, and the eventual resolution commit; derive candidate labels from the "
        "resolved content and reverts/discussion; then validate them on a hand-labelled "
        "subset before fitting §5.8 features. `source_audit.json` records the exact schema "
        "and counts that establish this dependency.",
    ]
    (output_dir / "SOURCE_AUDIT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    audit = audit_archive(args.archive)
    write_audit(args.output_dir, audit)
    print(
        f"Audited {audit['conflicting_pr_count']} conflicting PRs and "
        f"{audit['region_count']} regions"
    )


if __name__ == "__main__":
    main()
