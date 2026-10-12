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
            cfg_path = Path(tmp) / "cfg.yaml"
            cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
            self.assertEqual(benchmark.main(["--config", str(cfg_path)]), 0)
            for name in ("metrics.csv", "hypothesis_tests.csv", "guardrails.csv", "run.log"):
                self.assertTrue((Path(tmp) / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
