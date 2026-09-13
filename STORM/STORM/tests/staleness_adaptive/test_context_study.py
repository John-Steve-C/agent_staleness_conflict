import itertools
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from staleness_adaptive.context_study import _digest, _execute, read_checkpoint, request_completion
from staleness_adaptive.pilot_analysis import family_contrasts, summarize_contrasts, write_analysis
from staleness_adaptive.pilot_context import ModelTokenizer, build_context_prompt
from staleness_adaptive.pilot_corpus import build_pilot_corpus, render_payload


class ContextStudyTests(unittest.TestCase):
    def test_family_paired_interaction_averages_seeds(self):
        rows = []
        for family, length, history, condition, seed in itertools.product(
            ("a", "b"), (1024, 12288), ("current", "superseded"), ("P1", "P2", "P3"), (0, 1),
        ):
            value = condition == "P2" and length == 12288 and seed == 0
            rows.append({
                "job_id": f"{family}:{length}:{history}:{condition}:{seed}", "case_id": family,
                "family": family, "split": "evaluation", "specified_action": "adapt",
                "length": length, "history": history, "condition": condition, "seed": seed,
                "verified_recovery": value, "route_correct": value,
                "justified_escalation": False, "equal_action_composite": value,
            })
        effects = family_contrasts(rows)
        summaries = summarize_contrasts(effects, samples=100)
        selected = next(row for row in summaries if row["split"] == "evaluation"
                        and row["comparator"] == "P2" and row["outcome"] == "adapt_verified"
                        and row["contrast"] == "length_interaction")
        self.assertEqual(selected["difference"], 0.5)
        self.assertEqual(selected["family_count"], 2)
        self.assertEqual(selected["sign_flip_p_unadjusted"], 0.5)
        self.assertIsNone(selected["approx_confirmation_families"])
        with self.assertRaises(ValueError):
            family_contrasts(rows + [rows[0]])
        with self.assertRaises((ValueError, KeyError)):
            family_contrasts(rows[:-1])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                write_analysis(Path(directory), rows)

    def test_checkpoint_recovers_torn_tail_and_rejects_duplicate_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.jsonl"
            record = {"job_id": "a", "request_hash": "x"}
            line = json.dumps(record) + "\n"
            path.write_text(line + '{"job_id":')
            self.assertEqual(read_checkpoint(path), {"a": record})
            self.assertEqual(path.read_text(), line)
            path.write_text(line.rstrip())
            read_checkpoint(path)
            self.assertEqual(path.read_text(), line)
            path.write_text(line * 2)
            with self.assertRaises(ValueError):
                read_checkpoint(path)

    def test_resume_skips_completed_jobs_and_rejects_prompt_change(self):
        job = {"job_id": "a", "request": {"prompt": "same"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.jsonl"
            path.write_text(json.dumps({"job_id": "a", "request_hash": _digest(job["request"])}) + "\n")
            args = SimpleNamespace(workers=1, endpoint="local", timeout=1)
            with patch("staleness_adaptive.context_study.request_completion") as request:
                _execute(args, [job], path)
                request.assert_not_called()
            with self.assertRaises(ValueError):
                _execute(args, [{**job, "request": {"prompt": "changed"}}], path)

    def test_usage_and_truncation_are_not_lost_on_bad_json(self):
        body = {"choices": [{"message": {"content": '{"action":'}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 1024, "completion_tokens": 2048}}
        job = {"job_id": "a", "request": {}, "prompt_tokens": 1024}
        with patch("staleness_adaptive.context_study.urllib.request.urlopen") as response:
            response.return_value.__enter__.return_value.read.return_value = json.dumps(body)
            record = request_completion("http://localhost/v1", job, 1)
        self.assertTrue(record["truncated"])
        self.assertIsNone(record["parsed"])
        self.assertNotIn("transport_error", record)
        self.assertEqual(record["response"]["usage"]["completion_tokens"], 2048)

    def test_resume_retries_infrastructure_errors_only(self):
        jobs = [{"job_id": key, "request": {"seed": index}} for index, key in enumerate(("a", "b"))]
        records = [
            {"job_id": "a", "request_hash": _digest(jobs[0]["request"]), "transport_error": "timeout"},
            {"job_id": "b", "request_hash": _digest(jobs[1]["request"]), "parsed": None, "parse_error": "invalid JSON"},
        ]
        completed = {"job_id": "a", "request_hash": _digest(jobs[0]["request"]), "parsed": {}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.jsonl"
            path.write_text("".join(json.dumps(record) + "\n" for record in records))
            with patch("staleness_adaptive.context_study.request_completion", return_value=completed) as request:
                result = _execute(SimpleNamespace(workers=1, endpoint="local", timeout=1), jobs, path)
            request.assert_called_once_with("local", jobs[0], 1)
            self.assertEqual(result["b"], records[1])
            self.assertEqual(read_checkpoint(path)["a"], completed)


@unittest.skipUnless(os.environ.get("PILOT_TOKENIZER_PATH"), "set PILOT_TOKENIZER_PATH for actual-tokenizer gates")
class ActualTokenizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = ModelTokenizer(os.environ["PILOT_TOKENIZER_PATH"])

    def test_all_lengths_histories_payloads_and_reference_capacity(self):
        for case in build_pilot_corpus():
            self.assertLess(self.tokenizer.count(json.dumps({"revised_content": case.reference})), 2048)
            for length in (1024, 12288):
                prompts = []
                for history, condition in itertools.product(("current", "superseded"), ("P1", "P2", "P3")):
                    prompt = build_context_prompt(case.public, condition, history, length, self.tokenizer)
                    prompts.append(prompt)
                    self.assertLessEqual(abs(prompt.prompt_tokens - length), length * 0.02)
                    self.assertLessEqual(prompt.prompt_tokens + 2048, 16384)
                    self.assertLess(abs(prompt.relevant_start_fraction - 0.5), 0.02)
                    self.assertTrue(prompt.messages[1]["content"].endswith(render_payload(case.public, condition)))
                    self.assertEqual(prompt.obsolete_span_tokens == 0, history == "current")
                    self.assertEqual(prompt.relevant_history.count("read main.py"), 2)
                self.assertLessEqual(max(p.prompt_tokens for p in prompts) - min(p.prompt_tokens for p in prompts), length * 0.02)
                self.assertLessEqual(max(p.relevant_tokens for p in prompts) - min(p.relevant_tokens for p in prompts), 1)


if __name__ == "__main__":
    unittest.main()
