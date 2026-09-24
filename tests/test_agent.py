from __future__ import annotations

import unittest

from switchdeck.agent import InputController
from switchdeck.monitor import INPUT_SOURCE_VCP_CODE, VcpValue


class FakeMonitor:
    description = "Dell U2724D"

    def __init__(self, current: int) -> None:
        self.current = current
        self.set_values: list[tuple[int, int]] = []

    def capabilities(self) -> str:
        return ""

    def get_vcp(self, code: int) -> VcpValue:
        return VcpValue(self.current, self.current)

    def set_vcp(self, code: int, value: int) -> None:
        self.set_values.append((code, value))
        self.current = value

    def close(self) -> None:
        return None


class InputControllerTests(unittest.TestCase):
    def test_normalizes_duplicated_dell_value_and_switches_to_source_b(self) -> None:
        monitor = FakeMonitor(0x1111)
        controller = InputController(monitor, input_a=0x11, input_b=0x0F)

        message = controller.toggle()

        self.assertEqual(monitor.set_values, [(INPUT_SOURCE_VCP_CODE, 0x0F)])
        self.assertIn("输入源 B", message)

    def test_toggles_back_to_source_a(self) -> None:
        monitor = FakeMonitor(0x0F)
        controller = InputController(monitor, input_a=0x11, input_b=0x0F)

        controller.toggle()

        self.assertEqual(monitor.set_values[-1], (INPUT_SOURCE_VCP_CODE, 0x11))

    def test_rejects_equal_inputs(self) -> None:
        with self.assertRaises(ValueError):
            InputController(FakeMonitor(0x11), input_a=0x11, input_b=0x11)

    def test_initial_source_b_toggles_to_a_when_read_is_unknown(self) -> None:
        monitor = FakeMonitor(0x99)
        controller = InputController(
            monitor, input_a=0x11, input_b=0x0F, initial_target="b"
        )

        controller.toggle()

        self.assertEqual(monitor.set_values[-1], (INPUT_SOURCE_VCP_CODE, 0x11))


if __name__ == "__main__":
    unittest.main()
