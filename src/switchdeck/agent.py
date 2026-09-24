from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

from switchdeck.cli import select_monitor
from switchdeck.monitor import INPUT_SOURCE_VCP_CODE, Monitor, MonitorError
from switchdeck.backend import open_monitors
from switchdeck.idle import IdleCoordinator

LOGGER = logging.getLogger("switchdeck")

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_S = 0x53
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 1


@dataclass(frozen=True, slots=True)
class InputTarget:
    name: str
    value: int


class InputController:
    def __init__(
        self,
        monitor: Monitor,
        input_a: int,
        input_b: int,
        initial_target: str | None = None,
    ) -> None:
        if input_a == input_b:
            raise ValueError("输入源 A 和输入源 B 的值不能相同")
        self.monitor = monitor
        self.source_a = InputTarget("输入源 A", input_a)
        self.source_b = InputTarget("输入源 B", input_b)
        self._last_target: InputTarget | None = {
            "a": self.source_a,
            "b": self.source_b,
        }.get(initial_target or "")
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
            if current == self.source_a.value:
                target = self.source_b
            elif current == self.source_b.value:
                target = self.source_a
            elif self._last_target == self.source_a:
                target = self.source_b
            else:
                target = self.source_a
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


class ReopeningMonitor:
    """Acquire a fresh physical-monitor handle for every DDC operation."""

    def __init__(self, monitor_name: str, monitor_index: int) -> None:
        self.description = monitor_name
        self.monitor_name = monitor_name
        self.monitor_index = monitor_index

    def capabilities(self) -> str:
        return self._call("capabilities")

    def get_vcp(self, code: int):
        return self._call("get_vcp", code)

    def set_vcp(self, code: int, value: int) -> None:
        self._call("set_vcp", code, value)

    def close(self) -> None:
        return None

    def validate(self) -> None:
        with open_monitors() as monitors:
            self._select(monitors)

    def _call(self, method_name: str, *args: object):
        last_error: MonitorError | None = None
        for attempt in range(3):
            try:
                with open_monitors() as monitors:
                    monitor = self._select(monitors)
                    return getattr(monitor, method_name)(*args)
            except MonitorError as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.2)
        assert last_error is not None
        raise last_error

    def _select(self, monitors: list[Monitor]) -> Monitor:
        if sys.platform == "darwin" and self.monitor_name == "U2724D":
            try:
                return monitors[self.monitor_index]
            except IndexError as error:
                raise MonitorError(f"--index {self.monitor_index} 超出显示器范围") from error
        return select_monitor(monitors, self.monitor_name, self.monitor_index)


class WindowsHotkey:
    """Register Ctrl+Alt+S on a dedicated Windows message-loop thread."""

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
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, VK_S):
            self._error = MonitorError("注册 Ctrl+Alt+S 失败，快捷键可能已被占用")
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


class MacHotkey:
    """Register Control+Option+S through the macOS accessibility API."""

    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self._listener: object | None = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except (ImportError, OSError) as error:
            raise MonitorError(f"无法加载 macOS 全局快捷键支持: {error}") from error
        self._listener = keyboard.GlobalHotKeys({"<ctrl>+<alt>+s": self.callback})
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()


def run_agent(
    monitor_name: str,
    monitor_index: int,
    input_a: int,
    input_b: int,
) -> int:
    if sys.platform not in {"win32", "darwin"}:
        raise MonitorError("托盘后台程序仅支持 Windows 和 macOS")

    try:
        import pystray
        from switchdeck.icon import create_tray_image
    except ImportError as error:
        raise MonitorError("缺少托盘依赖，请先运行 uv sync") from error

    monitor = ReopeningMonitor(monitor_name, monitor_index)
    monitor.validate()
    try:
        initial_target = "a" if sys.platform == "win32" else "b"
        controller = InputController(
            monitor, input_a, input_b, initial_target=initial_target
        )
        image = create_tray_image()

        icon: object

        def safe_notification(message: str, title: str) -> None:
            try:
                icon.notify(message, title)
            except (NotImplementedError, AttributeError):
                LOGGER.debug("当前托盘后端不支持系统通知")

        def notify(action: Callable[[], str]) -> None:
            try:
                message = action()
            except Exception as error:
                LOGGER.exception("切换失败")
                safe_notification(str(error), "SwitchDeck 切换失败")
                return
            safe_notification(message, "SwitchDeck")

        menu = pystray.Menu(
            pystray.MenuItem(
                "切换输入源 A / B",
                lambda _icon, _item: notify(controller.toggle),
                default=True,
            ),
            pystray.MenuItem(
                "输入源 A",
                lambda _icon, _item: notify(
                    lambda: controller.switch_to(controller.source_a)
                ),
            ),
            pystray.MenuItem(
                "输入源 B",
                lambda _icon, _item: notify(
                    lambda: controller.switch_to(controller.source_b)
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda _icon, _item: icon.stop()),
        )
        icon = pystray.Icon("SwitchDeck", image, "SwitchDeck", menu)
        hotkey = (
            WindowsHotkey(lambda: notify(controller.toggle))
            if sys.platform == "win32"
            else MacHotkey(lambda: notify(controller.toggle))
        )
        hotkey.start()
        idle_coordinator: IdleCoordinator | None = None
        try:
            idle_coordinator = IdleCoordinator()
            idle_coordinator.start()
            shortcut = "Ctrl+Alt+S" if sys.platform == "win32" else "Control+Option+S"
            LOGGER.info("SwitchDeck 已在后台运行；按 %s 切换，托盘图标可选择目标", shortcut)
            icon.run()
        finally:
            if idle_coordinator is not None:
                idle_coordinator.stop()
            hotkey.stop()
    finally:
        monitor.close()
    return 0
