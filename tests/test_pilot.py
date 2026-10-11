from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from information_access.analysis import summarize
from information_access.ledger import Ledger, cost, dollars_to_nano, read_run, run_lock
from information_access.providers import NativeProvider, ProviderError, Result, decode, parse_choice
from information_access.runner import load_config, manifest_for, plan, run
from information_access.tasks import brute_force_value, classes, generate, solve, validate, value

ROOT = Path(__file__).resolve().parents[1]


class TaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = generate()

    def test_exact_value_against_exhaustive_policies(self):
        for c in self.cases:
            if len(classes(c)) <= 4:
                self.assertEqual(value(c, classes(c)), brute_force_value(c), c["id"])

    def test_hand_computed_two_state_example(self):
        c = {"payoffs": [[10, 0], [0, 10]], "priors": ["1/2", "1/2"],
             "safe_points": 6, "regime": "never", "signal_groups": [[0, 1]]}
        self.assertEqual(solve(c)["values"]["feasible"], "5")
        self.assertEqual(solve(c)["choices"]["feasible"], "safe")
        c["regime"] = "before"
        self.assertEqual(solve(c)["values"]["feasible"], "10")
        self.assertEqual(solve(c)["choices"]["feasible"], "plan")
        c["regime"] = "after"
        self.assertEqual(solve(c)["values"]["feasible"], "5")

    def test_safe_is_only_an_initial_choice(self):
        c = {"payoffs": [[10, 10], [0, 0]], "priors": ["1/2", "1/2"],
             "safe_points": 6, "regime": "before", "signal_groups": [[0], [1]]}
        self.assertEqual(solve(c)["values"]["feasible"], "5")  # Not (10+6)/2.

    def test_partial_value_is_intermediate_with_both_gold_choices(self):
        cs = [c for c in self.cases if c["world"] == "crossed" and c["regime"] == "partial"]
        self.assertEqual({c["gold"]["choices"]["feasible"] for c in cs}, {"safe", "plan"})
        for c in cs:
            v = {k: Fraction(x) for k, x in c["gold"]["values"].items()}
            self.assertLess(v["fixed_action"], v["feasible"])
            self.assertLess(v["feasible"], v["perfect_information"])

    def test_determinism_and_label_balance(self):
        self.assertEqual(generate(), generate())
        self.assertNotEqual(generate(1), generate(2))
        for family in ("repair", "routing"):
            cs = [c for c in self.cases if c["family"] == family]
            self.assertEqual(sum(c["labels"]["X"] == "safe" for c in cs), 16)

    def test_prompt_has_no_gold_or_hypothesis(self):
        for c in self.cases:
            for word in ("clairvoyant", "perfect_information", "aligned", "crossed", "strategy fusion", "gold"):
                self.assertNotIn(word, c["prompt"])
            self.assertLess(len(c["prompt"].encode()), 1200)

    def test_validator_rejects_stale_data(self):
        changed = deepcopy(self.cases)
        changed[0]["payoffs"][0][0] += 1
        with self.assertRaises(ValueError):
            validate(changed)


class ProviderTests(unittest.TestCase):
    def test_strict_json_parsing(self):
        self.assertEqual(parse_choice('{"choice":"X"}'), "X")
        self.assertEqual(parse_choice('```json\n{"choice":"Y"}\n```'), "Y")
        for text in ('X', 'I pick X. {"choice":"X"}', '{"choice":"X","choice":"Y"}',
                     '{"choice":"Z"}', '{"choice":"X","reason":"yes"}', 'null', '[]'):
            self.assertIsNone(parse_choice(text), text)

    def test_anthropic_thought_blocks_not_parsed_as_final(self):
        raw = {"content": [{"type": "thinking", "thinking": '{"choice":"Y"}'},
                           {"type": "text", "text": '{"choice":"X"}'}],
               "stop_reason": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 800}}
        result = decode("anthropic", raw)
        self.assertEqual(result.choice, "X")
        self.assertEqual(result.output_tokens, 800)
        raw["stop_reason"] = "max_tokens"
        self.assertEqual(decode("anthropic", raw).status, "truncated")
        self.assertIsNone(decode("anthropic", raw).choice)

    def test_gemini_hidden_thinking_is_billed(self):
        raw = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"thought": True, "text": '{"choice":"Y"}'}, {"text": '{"choice":"X"}'}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 10,
                              "thoughtsTokenCount": 500, "totalTokenCount": 610}}
        result = decode("gemini", raw)
        self.assertEqual((result.choice, result.output_tokens), ("X", 510))
        raw["candidates"][0]["finishReason"] = "MAX_TOKENS"
        self.assertEqual(decode("gemini", raw).status, "truncated")
        self.assertIsNone(decode("gemini", raw).choice)

    def test_missing_usage_stays_unknown(self):
        result = decode("anthropic", {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": '{"choice":"X"}'}]})
        self.assertEqual(result.status, "valid")
        self.assertIsNone(result.input_tokens)
        self.assertIsNone(result.output_tokens)

    def test_safety_and_empty_responses_are_not_answers(self):
        result = decode("gemini", {"promptFeedback": {"blockReason": "SAFETY"}})
        self.assertEqual(result.status, "blocked")
        self.assertIsNone(result.choice)
        self.assertEqual(decode("anthropic", {"stop_reason": "end_turn"}).status, "invalid_format")

    def test_malformed_provider_payload_is_preserved(self):
        for provider, raw in (("anthropic", ["unexpected"]), ("gemini", {"candidates": None})):
            result = decode(provider, raw)
            self.assertEqual(result.status, "malformed_response")
            self.assertIsNone(result.choice)
            self.assertEqual(result.raw, raw)

    def test_native_payloads_and_token_count_endpoints(self):
        config = load_config(ROOT / "configs/screen.json")
        calls = []

        def transport(url, body, headers, timeout):
            calls.append((url, body, headers, timeout))
            return {"input_tokens": 123, "totalTokens": 123}

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-only", "GEMINI_API_KEY": "test-only"}):
            for model in config["models"]:
                adapter = NativeProvider(model, config, transport=transport)
                self.assertEqual(adapter.count("hello"), 123)
                body = adapter.body("hello")
                self.assertNotIn("temperature", body)
                self.assertNotIn("tools", body)
                if model["provider"] == "anthropic":
                    self.assertEqual(body["max_tokens"], 4096)
                    self.assertEqual(body["thinking"], {"type": "adaptive"})
                else:
                    self.assertEqual(body["generationConfig"]["maxOutputTokens"], 4096)
                    self.assertNotIn("candidateCount", body["generationConfig"])
        self.assertTrue(calls[0][0].endswith("/messages/count_tokens"))
        self.assertTrue(calls[1][0].endswith(":countTokens"))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.config = load_config(ROOT / "configs/screen.json")
        # Tests must remain offline and independent of the wall-clock pricing expiry.
        self.config["pricing_valid_through"] = "2099-12-31"
        self.cases = generate()
        self.sent = 0
        outer = self

        class Fake:
            def __init__(self, model, config):
                pass

            def count(self, prompt):
                return 200

            def generate(self, prompt):
                outer.sent += 1
                return Result("valid", "X", '{"choice":"X"}', "end_turn", 200, 10, {"synthetic": True})

        self.factory = Fake

    def tearDown(self):
        self.tmp.cleanup()

    def execute(self, **kwargs):
        return run(self.config, self.cases, self.directory, provider_factory=self.factory,
                   progress=lambda _: None, **kwargs)

    def test_exact_cost_envelope(self):
        result = plan(self.config, self.cases)
        self.assertEqual(result["generation_requests"], 128)
        self.assertEqual(result["first_pass_reserved_usd"], "3.956480")
        self.assertEqual(result["retry_headroom_usd"], "1.043520")

    def test_resume_and_no_resampling_valid_wrong_answers(self):
        self.execute(limit=4)
        self.assertEqual(self.sent, 4)
        report = self.execute()
        self.assertEqual(self.sent, 128)
        self.execute(retry=True)
        self.assertEqual(self.sent, 128)
        self.assertEqual(report["cost"]["reserved_exposure_usd"], "3.956480")
        self.assertTrue((self.directory / "attempts.jsonl").exists())

    def test_budget_blocks_before_network_and_persists(self):
        self.config["budget_usd"] = "0.05"
        self.execute()
        self.assertEqual(self.sent, 1)
        self.execute()
        self.assertEqual(self.sent, 1)

    def test_interruption_is_reserved_and_retry_is_explicit(self):
        original = self.factory.generate

        def interrupt(adapter, prompt):
            raise KeyboardInterrupt()

        self.factory.generate = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.execute(limit=1)
        _, attempts = read_run(self.directory)
        self.assertEqual(attempts[0]["status"], "pending")
        self.assertGreater(attempts[0]["reserved"], 0)
        self.factory.generate = original
        self.execute(limit=1, retry=True)
        _, attempts = read_run(self.directory)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["cell"], attempts[1]["cell"])
        self.assertEqual(attempts[1]["status"], "valid")

    def test_invalid_not_scored_as_wrong_and_not_retried_by_default(self):
        self.factory.generate = lambda s, p: Result("truncated", None, "", "max_tokens", 200, 4096, {})
        report = self.execute(limit=1)
        self.assertEqual(report["models"]["sonnet"]["valid_cells"], 0)
        self.assertEqual(report["models"]["sonnet"]["outcome"], "incomplete")
        self.execute(limit=1)
        _, attempts = read_run(self.directory)
        self.assertNotEqual((attempts[0]["cell"], attempts[0]["model"]),
                            (attempts[1]["cell"], attempts[1]["model"]))

    def test_manifest_change_and_simulation_mix_are_rejected(self):
        self.execute(limit=1)
        changed = deepcopy(self.config)
        changed["budget_usd"] = "4.00"
        with self.assertRaises(ValueError):
            run(changed, self.cases, self.directory, provider_factory=self.factory)
        with self.assertRaises(ValueError):
            run(self.config, self.cases, self.directory, mode="simulation:feasible")

    def test_oversized_input_blocks_generation(self):
        self.factory.count = lambda s, p: 2000
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.sent, 0)

    def test_http_configuration_error_halts_after_one_reservation(self):
        def fail(adapter, prompt):
            raise ProviderError("Provider HTTP 401", 401)
        self.factory.generate = fail
        with self.assertRaises(ValueError):
            self.execute()
        _, attempts = read_run(self.directory)
        self.assertEqual(len(attempts), 1)
        self.assertIsNone(attempts[0]["actual"])
        self.assertEqual(attempts[0]["status"], "transport_error")

    def test_unknown_transport_charge_halts_and_keeps_reservation(self):
        def fail(adapter, prompt):
            raise ProviderError("Transport failure")
        self.factory.generate = fail
        with self.assertRaises(ValueError):
            self.execute()
        _, attempts = read_run(self.directory)
        self.assertEqual(len(attempts), 1)
        self.assertIsNone(attempts[0]["actual"])
        self.assertEqual(attempts[0]["reserved"], dollars_to_nano("0.04496"))

    def test_unexpected_usage_halts_and_records_actual_cost(self):
        self.factory.generate = lambda s, p: Result("valid", "X", '{"choice":"X"}', "end_turn", 200, 5000, {})
        with self.assertRaises(ValueError):
            self.execute()
        _, attempts = read_run(self.directory)
        self.assertEqual(len(attempts), 1)
        self.assertGreater(attempts[0]["actual"], attempts[0]["reserved"])

    def test_only_one_runner_per_directory(self):
        with run_lock(self.directory):
            with self.assertRaises(ValueError):
                with run_lock(self.directory):
                    self.fail("Second lock acquired")

    def test_reference_policies_have_distinct_signatures(self):
        for policy, expected_signature, expected_outcome in (
                ("feasible", 0, "no_replicated_signature"),
                ("perfect_information", 8, "signal_to_recheck"),
                ("fixed_action", 0, "control_failure")):
            report = run(self.config, self.cases, self.directory / policy,
                         mode=f"simulation:{policy}", progress=lambda _: None)
            self.assertEqual(report["cost"]["reserved_exposure_usd"], "0.000000")
            for m in report["models"].values():
                self.assertEqual(m["joint_signature_pairs"], expected_signature)
                self.assertEqual(m["outcome"], expected_outcome)


if __name__ == "__main__":
    unittest.main()
