import unittest

from staleness_adaptive.agenticflict_source_audit import (
    summarize_prs,
    summarize_regions,
)


class AgenticFlictSourceAuditTests(unittest.TestCase):
    def test_summarizes_only_conflicting_pr_resolution_metadata(self):
        summary = summarize_prs(
            [
                {"conflict_label": "True", "gh_state": "CLOSED", "merged_at": ""},
                {
                    "conflict_label": "True",
                    "gh_state": "MERGED",
                    "merged_at": "2026-01-01",
                },
                {"conflict_label": "False", "gh_state": "OPEN", "merged_at": ""},
            ]
        )

        self.assertEqual(summary["pr_count"], 3)
        self.assertEqual(summary["conflicting_pr_count"], 2)
        self.assertEqual(summary["conflicting_prs_with_merged_at"], 1)

    def test_distinguishes_previews_from_full_conflict_text(self):
        summary = summarize_regions(
            [
                {
                    "ours_text": "",
                    "theirs_text": "",
                    "ours_preview": "left",
                    "theirs_preview": "right",
                }
            ]
        )

        self.assertEqual(summary["regions_with_both_full_texts"], 0)
        self.assertEqual(summary["regions_with_both_previews"], 1)


if __name__ == "__main__":
    unittest.main()
