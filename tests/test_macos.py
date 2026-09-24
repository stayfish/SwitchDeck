from __future__ import annotations

import unittest
from unittest.mock import patch

from switchdeck.macos import MacMonitor, open_monitors
from switchdeck.monitor import INPUT_SOURCE_VCP_CODE


class MacMonitorTests(unittest.TestCase):
    @patch("switchdeck.macos._run")
    def test_m1ddc_sets_input(self, run) -> None:
        monitor = MacMonitor("Display", "/opt/homebrew/bin/m1ddc", "default")

        monitor.set_vcp(INPUT_SOURCE_VCP_CODE, 0x11)

        run.assert_called_once_with(["/opt/homebrew/bin/m1ddc", "set", "input", "17"])

    @patch("switchdeck.macos._run")
    def test_ddcctl_sets_input(self, run) -> None:
        monitor = MacMonitor("Display", "/usr/local/bin/ddcctl", "1")

        monitor.set_vcp(INPUT_SOURCE_VCP_CODE, 0x0F)

        run.assert_called_once_with(["/usr/local/bin/ddcctl", "-d", "1", "-i", "15"])

    @patch("switchdeck.macos.platform.machine", return_value="x86_64")
    @patch("switchdeck.macos._find_helper", return_value="/usr/local/bin/ddcctl")
    def test_intel_collection_uses_first_ddcctl_display(self, helper, machine) -> None:
        with open_monitors() as monitors:
            self.assertEqual(monitors[0].display, "1")


if __name__ == "__main__":
    unittest.main()
