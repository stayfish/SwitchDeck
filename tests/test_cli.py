from __future__ import annotations

import unittest

from switchdeck.cli import build_parser, select_monitor
from switchdeck.monitor import MonitorError, VcpValue, parse_number


class FakeMonitor:
    def __init__(self, description: str) -> None:
        self.description = description

    def capabilities(self) -> str:
        return ""

    def get_vcp(self, code: int) -> VcpValue:
        return VcpValue(0x0F, 0x12)

    def set_vcp(self, code: int, value: int) -> None:
        return None

    def close(self) -> None:
        return None


class ParseNumberTests(unittest.TestCase):
    def test_accepts_hex_and_decimal(self) -> None:
        self.assertEqual(parse_number("0x0f"), 15)
        self.assertEqual(parse_number("17"), 17)

    def test_rejects_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            parse_number("-1")


class MonitorSelectionTests(unittest.TestCase):
    def test_selects_case_insensitively(self) -> None:
        monitors = [FakeMonitor("Generic PnP"), FakeMonitor("DELL U2724D")]
        self.assertEqual(select_monitor(monitors, "u2724d", 0).description, "DELL U2724D")

    def test_reports_missing_monitor(self) -> None:
        with self.assertRaises(MonitorError):
            select_monitor([FakeMonitor("Other")], "U2724D", 0)


class ParserTests(unittest.TestCase):
    def test_roundtrip_arguments(self) -> None:
        args = build_parser().parse_args(["roundtrip", "0x11", "0x0f", "--delay", "2"])
        self.assertEqual((args.away, args.back, args.delay), (0x11, 0x0F, 2.0))


if __name__ == "__main__":
    unittest.main()
