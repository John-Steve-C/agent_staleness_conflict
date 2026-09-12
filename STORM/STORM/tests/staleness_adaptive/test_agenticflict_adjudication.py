from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from staleness_adaptive.agenticflict_adjudication import (
    write_adjudication_packets,
)


class AgenticFlictAdjudicationTests(unittest.TestCase):
    @patch("staleness_adaptive.agenticflict_adjudication._git_diff")
    def test_packet_contains_evidence_but_not_machine_route(self, git_diff) -> None:
        git_diff.side_effect = ["base-head", "head-merge"]
        audit = [
            {
                "pr_key": "owner/repo#1",
                "repo_full_name": "owner/repo",
                "file_path": "src/a.py",
                "base_oid": "base",
                "head_oid": "head",
                "merge_commit_oid": "merge",
            }
        ]
        sample = [
            {
                "adjudication_id": "S3-001",
                "pr_key": "owner/repo#1",
                "pr_url": "https://github.com/owner/repo/pull/1",
                "file_path": "src/a.py",
                "resolution_evidence": "manual_or_combined",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_adjudication_packets(audit, sample, Path("/repos"), output)
            packet = (output / "S3-001.md").read_text()

        self.assertIn("base-head", packet)
        self.assertIn("head-merge", packet)
        self.assertNotIn("machine_route", packet)


if __name__ == "__main__":
    unittest.main()
