"""Deterministic tests: parser variants, validation, two-path gate, mode routing."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from server.app import decide_gate
from server.env import gnani_live
from server.parser import parse_transcript, validate
from server.store import MEMBERS
from server.tts import _key

B12_RAW = "number one two seven மூணு liter பால் pack நாலு பாயன். நாலு evening shift."
B12_MIT = "number one two seven, மூணு litre பால், pack நாலு, பாயின்ட். நாலு evening shift."
B15_RAW = "number one three seven, மூன்றரை litre fat, நாலு point. ஒன்பது morning."
B15_MIT = "Number one three seven மூன்றரை லிட்டர் fat non-veg buying. ஒன்பது morning."
B09_RAW = "number one two four, மூணு liter, என்ன என்ன, மூன்றரை liter. page நாலு point எட்டு கானை."
B09_MIT = "number one two four, மூணு liter, என்ன என்ன, மூன்றரை liter. பேக் நாலு point எட்டு காலை."
B01_RAW = "Society number one zero one, ரெண்டு liter பால். பேட் நாலு point ஐந்து, college shift."
B01_MIT = "Society number one zero one, ரெண்டு Richard Paul. பேக் நாலு point ஐந்து, college fees."


def parsed(text: str) -> dict:
    return parse_transcript(text)


def checked(text: str) -> tuple[dict, dict]:
    p = parse_transcript(text)
    return p, validate(p, MEMBERS)


def values(p: dict) -> dict:
    return {k: v["value"] for k, v in p["slots"].items()}


def synthetic(**slots) -> tuple[dict, dict]:
    p = {"slots": {k: {"value": v} for k, v in slots.items()}, "missing": []}
    return p, validate(p, MEMBERS)


class ParserTests(unittest.TestCase):
    def test_prisma_digit_words_and_loanwords(self):
        self.assertEqual(
            values(parsed(B12_RAW)),
            {"member_id": 127, "litres": 3.0, "fat": 4.4, "shift": "evening"},
        )

    def test_missing_shift_is_flagged(self):
        p, v = checked(B09_RAW)
        self.assertNotIn("shift", values(p))
        self.assertFalse(v["ok"])
        self.assertIn("shift_missing", [f["code"] for f in v["flags"]])

    def test_fractional_fat_from_tamil_phrase(self):
        self.assertEqual(values(parsed(B15_RAW))["fat"], 4.9)


class ValidationTests(unittest.TestCase):
    def test_unknown_member(self):
        _, v = synthetic(member_id=999, litres=2.0, fat=4.5, shift="morning")
        self.assertEqual([f["code"] for f in v["flags"]], ["member_unknown"])

    def test_litres_range(self):
        _, v = synthetic(member_id=101, litres=25.0, fat=4.5, shift="morning")
        self.assertEqual([f["code"] for f in v["flags"]], ["litres_range"])

    def test_fat_range(self):
        _, v = synthetic(member_id=101, litres=2.0, fat=9.5, shift="morning")
        self.assertEqual([f["code"] for f in v["flags"]], ["fat_range"])

    def test_shift_vocabulary(self):
        _, v = synthetic(member_id=101, litres=2.0, fat=4.5, shift="noon")
        self.assertFalse(v["ok"])


class GateTests(unittest.TestCase):
    def test_agree(self):
        raw_p, raw_v = checked(B12_RAW)
        mit_p, mit_v = checked(B12_MIT)
        out = decide_gate(raw_p, raw_v, mit_p, mit_v)
        self.assertEqual(out["agreement"], "agree")
        self.assertEqual(out["chosen"], "raw")
        self.assertEqual(out["differing"], [])

    def test_disagree_keeps_raw_and_reports_fat(self):
        raw_p, raw_v = checked(B15_RAW)
        mit_p, mit_v = checked(B15_MIT)
        out = decide_gate(raw_p, raw_v, mit_p, mit_v)
        self.assertEqual(out["agreement"], "disagree")
        self.assertEqual(out["chosen"], "raw")
        self.assertEqual(out["differing"], ["fat"])
        self.assertEqual(out["raw_slots"]["fat"], 4.9)
        self.assertEqual(out["mit_slots"]["fat"], 9.0)

    def test_one_path_uses_conditioned_read(self):
        raw_p, raw_v = checked(B09_RAW)
        mit_p, mit_v = checked(B09_MIT)
        out = decide_gate(raw_p, raw_v, mit_p, mit_v)
        self.assertEqual(out["agreement"], "mit_only")
        self.assertEqual(out["chosen"], "processed")

    def test_raw_only(self):
        raw_p, raw_v = checked(B12_RAW)
        _, bad_v = synthetic(member_id=101, litres=2.0, fat=4.5)
        bad_p = {"slots": {"member_id": {"value": 101}}, "missing": ["litres", "fat", "shift"]}
        out = decide_gate(raw_p, raw_v, bad_p, bad_v)
        self.assertEqual(out["agreement"], "raw_only")
        self.assertEqual(out["chosen"], "raw")

    def test_neither_path_is_a_reask(self):
        raw_p, raw_v = checked(B01_RAW)
        mit_p, mit_v = checked(B01_MIT)
        out = decide_gate(raw_p, raw_v, mit_p, mit_v)
        self.assertEqual(out["agreement"], "none")
        self.assertEqual(out["chosen"], "raw")


class ProviderModeTests(unittest.TestCase):
    def test_no_key_is_local(self):
        with mock.patch.dict(os.environ, {"GNANI_API_KEY": "", "DEMO_MODE": ""}, clear=False):
            self.assertFalse(gnani_live())

    def test_key_defaults_to_live(self):
        with mock.patch.dict(os.environ, {"GNANI_API_KEY": "test-key", "DEMO_MODE": ""}, clear=False):
            self.assertTrue(gnani_live())

    def test_demo_flag_forces_local(self):
        with mock.patch.dict(os.environ, {"GNANI_API_KEY": "test-key", "DEMO_MODE": "1"}, clear=False):
            self.assertFalse(gnani_live())

    def test_zero_flag_forces_live(self):
        with mock.patch.dict(os.environ, {"GNANI_API_KEY": "test-key", "DEMO_MODE": "0"}, clear=False):
            self.assertTrue(gnani_live())


class TTSCacheTests(unittest.TestCase):
    def test_provider_is_part_of_the_cache_key(self):
        self.assertNotEqual(_key("மீண்டும் சொல்லுங்கள்.", True), _key("மீண்டும் சொல்லுங்கள்.", False))


if __name__ == "__main__":
    unittest.main()
