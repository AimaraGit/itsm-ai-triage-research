import math
import tempfile
import unittest
from pathlib import Path

import yaml

from src import benchmark
from src.metrics import bounce_rate, governance_index, handoff_delta, weighted_kappa


class TestMetrics(unittest.TestCase):
    def test_handoff_delta(self):
        self.assertAlmostEqual(handoff_delta(60, 40), 33.3333, places=3)
        self.assertTrue(math.isnan(handoff_delta(60, float("nan"))))

    def test_bounce_rate(self):
        self.assertEqual(bounce_rate(10, 100), 10.0)
        with self.assertRaises(ValueError):
            bounce_rate(11, 10)

    def test_governance_index(self):
        self.assertEqual(governance_index(1, 1, 1), 3)
        self.assertEqual(governance_index(0, 0, 0), 0)
        with self.assertRaises(ValueError):
            governance_index(2, 0, 0)

    def test_kappa(self):
        self.assertEqual(weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]), 1.0)
        self.assertLess(weighted_kappa([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), 0)


class TestPipeline(unittest.TestCase):
    def test_end_to_end_on_sample(self):
        cfg = yaml.safe_load(Path("configs/config.yaml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            cfg["paths"]["output_dir"] = tmp
            cfg["benchmark"].update(warmup_runs=2, test_runs=5,
                                    output_jsonl=str(Path(tmp) / "t.jsonl"))
            cfg_path = Path(tmp) / "cfg.yaml"
            cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
            self.assertEqual(benchmark.main(["--config", str(cfg_path)]), 0)
            for name in ("metrics.csv", "hypothesis_tests.csv", "guardrails.csv", "run.log"):
                self.assertTrue((Path(tmp) / name).exists(), name)


class TestHarness(unittest.TestCase):
    def setUp(self):
        self.cfg = yaml.safe_load(Path("configs/config.yaml").read_text(encoding="utf-8"))
        self.cases = benchmark.load_cases(Path(self.cfg["paths"]["cases_csv"]))

    def test_workload_is_deterministic_and_has_all_edge_kinds(self):
        wl_cfg = self.cfg["benchmark"]["workload"]
        a = benchmark.build_workload(self.cases, 50, wl_cfg, seed=1)
        b = benchmark.build_workload(self.cases, 50, wl_cfg, seed=1)
        self.assertEqual([(w["kind"], w["n_rows"]) for w in a],
                         [(w["kind"], w["n_rows"]) for w in b])
        kinds = {w["kind"] for w in a}
        self.assertIn("pareto", kinds)
        self.assertIn("invalid_zero_total", kinds)
        self.assertIn("empty", kinds)

    def test_warmup_excluded_and_errors_counted(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] % 4 == 0:
                raise RuntimeError("boom")

        wl = [{"kind": "x", "n_rows": 0}]
        recs, summ = benchmark.execute_isolated_benchmark(
            flaky, wl, lambda item: ((), {}), warmup_runs=3, test_runs=20)
        self.assertEqual(sum(r["phase"] == "warmup" for r in recs), 3)
        self.assertEqual(summ["n_work_runs"], 20)
        self.assertEqual(summ["n_warmup_runs"], 3)
        self.assertGreater(summ["n_errors"], 0)
        self.assertEqual(summ["errors_by_type"], {"RuntimeError": summ["n_errors"]})
        self.assertEqual(summ["success"]["n"] + summ["n_errors"], 20)
        self.assertIn("failed_latency", summ)

    def test_jsonl_has_meta_header_and_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = dict(self.cfg)
            cfg["paths"] = dict(cfg["paths"], output_dir=tmp)
            cfg["benchmark"] = dict(cfg["benchmark"], warmup_runs=2, test_runs=10,
                                    output_jsonl=str(Path(tmp) / "t.jsonl"))
            cfg_path = Path(tmp) / "cfg.yaml"
            cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
            self.assertEqual(benchmark.main(["--config", str(cfg_path)]), 0)
            import json
            lines = [json.loads(l) for l in (Path(tmp) / "t.jsonl").read_text().splitlines()]
            self.assertEqual(lines[0]["record_type"], "meta")
            self.assertIn("config_sha256", lines[0])
            self.assertEqual(len(lines), 1 + 2 + 10)
            self.assertEqual({l["phase"] for l in lines[1:]}, {"warmup", "work"})
            self.assertTrue((Path(tmp) / "benchmark_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
