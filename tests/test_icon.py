from __future__ import annotations

import unittest

from switchdeck.icon import create_tray_image


class TrayIconTests(unittest.TestCase):
    def test_icon_has_transparent_background_and_black_arrow(self) -> None:
        image = create_tray_image()

        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        center = image.getpixel((image.width // 2, image.height // 2))
        self.assertEqual(center[:3], (0, 0, 0))
        self.assertGreater(center[3], 0)


if __name__ == "__main__":
    unittest.main()
