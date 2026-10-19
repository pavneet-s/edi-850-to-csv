"""Tests for edi850_to_csv.py. Run with: python -m unittest -v"""

import unittest
from decimal import Decimal
from pathlib import Path

from edi850_to_csv import parse_850, read_segments

SAMPLES = Path(__file__).parent / "samples"


def load(name):
    return read_segments((SAMPLES / name).read_text(encoding="utf-8"))


class GoodFileTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.errors = parse_850(load("sample_850.edi"))

    def test_no_errors(self):
        self.assertEqual(self.errors, [])

    def test_reads_every_line_from_both_pos(self):
        self.assertEqual(len(self.rows), 5)
        self.assertEqual({r["po_number"] for r in self.rows}, {"PO45001", "PO45002"})

    def test_first_line_values(self):
        first = self.rows[0]
        self.assertEqual(first["po_date"], "2026-10-19")
        self.assertEqual(first["ship_to"], "SAMPLE DC TORONTO")
        self.assertEqual(first["quantity"], Decimal("24"))
        self.assertEqual(first["line_total"], Decimal("444.00"))
        self.assertEqual(first["vendor_part"], "V-1001")
        self.assertEqual(first["upc"], "012345678905")
        self.assertEqual(first["description"], "EXTRA VIRGIN OLIVE OIL 1L")


class BadFileTests(unittest.TestCase):
    def test_catches_count_and_control_number_errors(self):
        _, errors = parse_850(load("bad_850.edi"))
        text = "\n".join(errors)
        self.assertIn("SE01 says 12 segments", text)
        self.assertIn("CTT01 says 3 lines", text)
        self.assertIn("GE02 103 does not match GS06 102", text)

    def test_reads_custom_separators(self):
        raw = (SAMPLES / "sample_850.edi").read_text(encoding="utf-8")
        swapped = raw.replace("*", "|").replace("~", "'")
        rows, errors = parse_850(read_segments(swapped))
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 5)

    def test_flags_cut_off_file(self):
        raw = (SAMPLES / "sample_850.edi").read_text(encoding="utf-8")
        cut = raw[: raw.index("GE*")]
        _, errors = parse_850(read_segments(cut))
        self.assertTrue(any("without an IEA" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
