"""Guards on the evidence artifacts and the public disclosures."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrozenBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data" / "benchmark.json").read_text(encoding="utf-8"))

    def test_frozen_matrix_is_complete(self):
        self.assertEqual(self.data["status"], "complete")
        self.assertEqual(self.data["cells"], 192)
        self.assertEqual(self.data["n_per_cell"], 24)

    def test_claim_is_synthetic_and_bounded(self):
        self.assertIn("24 synthetic", self.data["claim"])
        self.assertIn("Wilson 95% CIs", self.data["claim"])

    def test_no_stale_no_key_disclosure(self):
        text = " ".join(self.data["caveats"])
        self.assertNotIn("No Gnani API key was provisioned", text)


class ProviderCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data" / "benchmark-gnani.json").read_text(encoding="utf-8"))

    def test_provider_matrix_is_complete(self):
        self.assertEqual(self.data["status"], "complete")
        self.assertEqual(self.data["cells"], 192)
        self.assertEqual(self.data["errors"], [])

    def test_no_key_material_is_stored(self):
        self.assertEqual(self.data["provider"]["key"], "participant-supplied, not logged")

    def test_claim_prefix_is_not_duplicated(self):
        self.assertNotIn("clips: On 24 synthetic", self.data["claim"])
        self.assertTrue(self.data["claim"].startswith("Live Gnani Prisma v3.0 decoded"))

    def test_slot_metric_is_separated_from_wer(self):
        self.assertIn("WER", self.data["claim"])
        self.assertIn("not comparable", self.data["claim"])


if __name__ == "__main__":
    unittest.main()
