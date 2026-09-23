from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

from switchdeck.cli import select_monitor
from switchdeck.monitor import INPUT_SOURCE_VCP_CODE, Monitor, MonitorError
from switchdeck.windows import open_monitors

LOGGER = logging.getLogger("switchdeck")

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 1


@dataclass(frozen=True, slots=True)
class InputTarget:
    name: str
    value: int


class InputController:
    def __init__(self, monitor: Monitor, windows_input: int, mac_input: int) -> None:
        if windows_input == mac_input:
            raise ValueError("Windows 和 Mac 的输入值不能相同")
        self.monitor = monitor
        self.windows = InputTarget("Windows", windows_input)
        self.mac = InputTarget("Mac", mac_input)
        self._last_target: InputTarget | None = None
        self._lock = threading.Lock()

    def switch_to(self, target: InputTarget) -> str:
        with self._lock:
            self.monitor.set_vcp(INPUT_SOURCE_VCP_CODE, target.value)
            self._last_target = target
        message = f"已切换到 {target.name}（0x{target.value:02x}）"
        LOGGER.info(message)
        return message

    def toggle(self) -> str:
        with self._lock:
            current = self._read_current_input()
            if current == self.windows.value:
                target = self.mac
            elif current == self.mac.value:
                target = self.windows
            elif self._last_target == self.windows:
                target = self.mac
            else:
                target = self.windows
            self.monitor.set_vcp(INPUT_SOURCE_VCP_CODE, target.value)
            self._last_target = target
        message = f"已切换到 {target.name}（0x{target.value:02x}）"
        LOGGER.info(message)
        return message

    def _read_current_input(self) -> int | None:
        try:
            raw = self.monitor.get_vcp(INPUT_SOURCE_VCP_CODE).current
        except MonitorError as error:
            LOGGER.warning("无法读取当前输入，使用上次状态判断: %s", error)
            return None
        low_byte = raw & 0xFF
        if raw != low_byte:
            LOGGER.debug("归一化显示器返回值 0x%x -> 0x%02x", raw, low_byte)
        return low_byte


class WindowsHotkey:
    """Register Ctrl+Alt+Space on a dedicated Windows message-loop thread."""

    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._error: Exception | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="switchdeck-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        if self._thread_id is not None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread_id = kernel32.GetCurrentThreadId()
        modifiers = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, VK_SPACE):
            self._error = MonitorError("注册 Ctrl+Alt+Space 失败，快捷键可能已被占用")
            self._ready.set()
            return
        self._ready.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    try:
                        self.callback()
                    except Exception:
                        LOGGER.exception("快捷键切换失败")
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)


def run_agent(
    monitor_name: str,
    monitor_index: int,
    windows_input: int,
    mac_input: int,
) -> int:
    if sys.platform != "win32":
        raise MonitorError("托盘后台程序目前仅支持 Windows")

    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise MonitorError("缺少托盘依赖，请先运行 uv sync") from error

    collection = open_monitors()
    monitors = collection.__enter__()
    try:
        monitor = select_monitor(monitors, monitor_name, monitor_index)
        controller = InputController(monitor, windows_input, mac_input)
        image = Image.new("RGB", (64, 64), "#111827")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((7, 10, 57, 49), radius=5, outline="#60a5fa", width=5)
        draw.rectangle((25, 50, 39, 56), fill="#60a5fa")

        icon: object

        def notify(action: Callable[[], str]) -> None:
            try:
                message = action()
                icon.notify(message, "SwitchDeck")
            except Exception as error:
                LOGGER.exception("切换失败")
                icon.notify(str(error), "SwitchDeck 切换失败")

        menu = pystray.Menu(
            pystray.MenuItem(
                "切换 Windows / Mac",
                lambda _icon, _item: notify(controller.toggle),
                default=True,
            ),
            pystray.MenuItem(
                "Windows",
                lambda _icon, _item: notify(lambda: controller.switch_to(controller.windows)),
            ),
            pystray.MenuItem(
                "Mac",
                lambda _icon, _item: notify(lambda: controller.switch_to(controller.mac)),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda _icon, _item: icon.stop()),
        )
        icon = pystray.Icon("SwitchDeck", image, "SwitchDeck", menu)
        hotkey = WindowsHotkey(lambda: notify(controller.toggle))
        hotkey.start()
        LOGGER.info("SwitchDeck 已在后台运行；按 Ctrl+Alt+Space 切换，托盘图标可选择目标")
        try:
            icon.run()
        finally:
            hotkey.stop()
    finally:
        collection.__exit__(None, None, None)
    return 0
