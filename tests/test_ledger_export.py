"""The ledger CSV export is a plain, stable day-book for the society's accounts."""
from __future__ import annotations

import unittest

from server.app import ledger_csv

ENTRY = {
    "id": "E-TEST01",
    "created_at": "2026-11-10T18:42:00+05:30",
    "member_id": 127,
    "member_name": "Kumar, V",
    "shift": "evening",
    "litres": 3.0,
    "fat": 4.4,
    "rate": 41.6,
    "amount": 124.8,
    "status": "confirmed",
    "source": "clip",
    "override": False,
    "hash": "abc123",
}


class LedgerCsvTests(unittest.TestCase):
    def test_bom_and_header(self):
        text = ledger_csv([])
        self.assertTrue(text.startswith("\ufeffReceipt,Time,Member,Name,Shift,Litres,Fat,Rate,Amount"))
        self.assertTrue(text.rstrip().endswith("Source,Corrected,Audit hash"))

    def test_row_and_escaping(self):
        lines = ledger_csv([ENTRY]).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn('"Kumar, V"', lines[1])
        self.assertIn("E-TEST01", lines[1])
        self.assertIn("124.8", lines[1])
        self.assertIn(",no,abc123", lines[1])


if __name__ == "__main__":
    unittest.main()
