from __future__ import annotations

import sys

from switchdeck.monitor import MonitorError


def open_monitors():
    if sys.platform == "win32":
        from switchdeck.windows import open_monitors as open_windows_monitors

        return open_windows_monitors()
    if sys.platform == "darwin":
        from switchdeck.macos import open_monitors as open_macos_monitors

        return open_macos_monitors()
    raise MonitorError("DDC/CI 控制仅支持 Windows 和 macOS")
