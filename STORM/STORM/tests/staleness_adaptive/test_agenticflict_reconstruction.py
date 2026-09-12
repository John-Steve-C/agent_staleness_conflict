from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from staleness_adaptive.agenticflict_reconstruction import (
    audit_local_repositories,
    build_adjudication_sample,
    build_machine_hypotheses,
    build_reconstruction_manifest,
    classify_blob_resolution,
    classify_tree_resolution,
)


class AgenticFlictReconstructionTests(unittest.TestCase):
    def test_manifest_keeps_only_merged_conflict_files(self) -> None:
        prs = [
            {
                "pr_key": "owner/repo#1",
                "repo_full_name": "owner/repo",
                "pr_number": "1",
                "agent": "agent",
                "base_oid": "base",
                "head_oid": "head",
                "merge_commit_oid": "merge",
                "merged_at": "2026-01-01",
                "conflict_label": "true",
            },
            {
                "pr_key": "owner/repo#2",
                "merge_commit_oid": "",
                "merged_at": "",
                "conflict_label": "true",
            },
        ]
        files = [
            {
                "pr_key": "owner/repo#1",
                "file_path": "src/a.py",
                "file_ext": ".py",
                "num_regions_in_file": "2",
                "conflict_lines_in_file": "8",
            },
            {"pr_key": "owner/repo#2", "file_path": "src/b.py"},
        ]
        commits = [
            {
                "pr_key": "owner/repo#1",
                "file_path": "src/a.py",
                "head_last_touch_oid": "head-touch",
                "base_last_touch_oid": "base-touch",
            }
        ]

        manifest = build_reconstruction_manifest(prs, files, commits)

        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["file_path"], "src/a.py")
        self.assertEqual(manifest[0]["head_last_touch_oid"], "head-touch")
        self.assertEqual(manifest[0]["pr_base_oid"], "base")

    def test_blob_evidence_does_not_claim_route_labels(self) -> None:
        self.assertEqual(classify_blob_resolution("a", "b", "a"), "exact_base")
        self.assertEqual(classify_blob_resolution("a", "b", "b"), "exact_head")
        self.assertEqual(
            classify_blob_resolution("a", "b", "c"), "manual_or_combined"
        )
        self.assertEqual(classify_blob_resolution("", "b", "c"), "missing_blob")
        self.assertEqual(
            classify_tree_resolution({}, {"a.py": "head"}, {"a.py": "head"}, "a.py"),
            "exact_head",
        )
        self.assertEqual(classify_tree_resolution({}, {}, {}, "a.py"), "absent_all")
        self.assertEqual(
            classify_tree_resolution(None, {}, {}, "a.py"), "missing_commit"
        )

    @patch("staleness_adaptive.agenticflict_reconstruction._tree_blobs")
    def test_repository_audit_reads_each_commit_tree_once(self, tree_blobs) -> None:
        tree_blobs.side_effect = [
            {"src/a.py": "base-a", "src/b.py": "base-b"},
            {"src/a.py": "head-a", "src/b.py": "head-b"},
            {"src/a.py": "head-a", "src/b.py": "merge-b"},
        ]
        rows = [
            {
                "repo_full_name": "owner/repo",
                "pr_key": "owner/repo#1",
                "base_oid": "base",
                "head_oid": "head",
                "merge_commit_oid": "merge",
                "file_path": path,
            }
            for path in ("src/a.py", "src/b.py")
        ]
        repo = Path("/tmp/agenticflict-test/owner__repo")

        with patch.object(Path, "is_file", return_value=True):
            audit = audit_local_repositories(rows, repo.parent)

        self.assertEqual(tree_blobs.call_count, 3)
        self.assertEqual(audit[0]["resolution_evidence"], "exact_head")
        self.assertEqual(audit[1]["resolution_evidence"], "manual_or_combined")

    def test_adjudication_sample_is_balanced(self) -> None:
        audit = [
            {
                "repo_full_name": f"owner/repo-{index}",
                "pr_number": str(index),
                "pr_key": f"owner/repo-{index}#{index}",
                "file_path": "src/a.py",
                "resolution_evidence": evidence,
            }
            for evidence in ("exact_base", "manual_or_combined", "exact_head")
            for index in range(2)
        ]

        sample = build_adjudication_sample(audit, per_evidence=2)

        self.assertEqual(len(sample), 6)
        hypotheses = build_machine_hypotheses(sample)
        self.assertEqual(
            {row["machine_route_hypothesis"] for row in hypotheses},
            {"abandon", "adapt", "escalate"},
        )
        self.assertTrue(all(not row["human_route"] for row in sample))
        self.assertTrue(
            all("machine_route_hypothesis" not in row for row in sample)
        )


if __name__ == "__main__":
    unittest.main()
