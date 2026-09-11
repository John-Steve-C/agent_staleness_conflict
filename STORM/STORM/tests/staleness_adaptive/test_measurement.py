import unittest

from staleness_adaptive.measurement import measure_staleness, semantic_change_ratio


class MeasurementTests(unittest.TestCase):
    def test_semantic_ratio_ignores_comment_only_changes(self):
        before = "# old note\ndef value():\n    return 1\n"
        after = "# new note\ndef value():\n    return 1\n"

        self.assertEqual(semantic_change_ratio(before, after), 0.0)

    def test_measurement_records_all_three_staleness_families(self):
        result = measure_staleness(
            read_at=10,
            refused_at=14.5,
            intervening_writes=2,
            base_content="def f():\n    return 1\n",
            current_content="def f():\n    return 2\n",
            referenced_symbols={"f"},
            changed_symbols={"f"},
            tokens_since_read=90,
            tool_calls_since_read=3,
        )

        self.assertEqual(result.temporal_seconds, 4.5)
        self.assertEqual(result.edit_distance_writes, 2)
        self.assertGreater(result.semantic_ratio, 0)
        self.assertTrue(result.symbol_overlap)
        self.assertEqual(result.investment_tokens, 90)
        self.assertEqual(result.investment_tool_calls, 3)


if __name__ == "__main__":
    unittest.main()
