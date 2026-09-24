from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

from switchdeck.monitor import MonitorError, VcpValue

PHYSICAL_MONITOR_DESCRIPTION_SIZE = 128
ERROR_GRAPHICS_MONITOR_NO_LONGER_EXISTS = 0xC026258D


class PhysicalMonitor(ctypes.Structure):
    _fields_ = [
        ("handle", wintypes.HANDLE),
        ("description", wintypes.WCHAR * PHYSICAL_MONITOR_DESCRIPTION_SIZE),
    ]


@dataclass(slots=True)
class WindowsMonitor:
    description: str
    _handle: int
    _dxva2: object
    _closed: bool = False

    def _require_open(self) -> None:
        if self._closed:
            raise MonitorError(f"显示器句柄已关闭: {self.description}")

    def capabilities(self) -> str:
        self._require_open()
        length = wintypes.DWORD()
        if not self._dxva2.GetCapabilitiesStringLength(self._handle, ctypes.byref(length)):
            _raise_last_error("读取 capabilities 长度失败", self.description)
        buffer = ctypes.create_string_buffer(length.value)
        if not self._dxva2.CapabilitiesRequestAndCapabilitiesReply(
            self._handle, buffer, length.value
        ):
            _raise_last_error("读取 capabilities 失败", self.description)
        return buffer.value.decode("ascii", errors="replace")

    def get_vcp(self, code: int) -> VcpValue:
        self._require_open()
        current = wintypes.DWORD()
        maximum = wintypes.DWORD()
        code_type = wintypes.DWORD()
        if not self._dxva2.GetVCPFeatureAndVCPFeatureReply(
            self._handle,
            code,
            ctypes.byref(code_type),
            ctypes.byref(current),
            ctypes.byref(maximum),
        ):
            _raise_last_error(f"读取 VCP 0x{code:02x} 失败", self.description)
        return VcpValue(current=current.value, maximum=maximum.value)

    def set_vcp(self, code: int, value: int) -> None:
        self._require_open()
        if not self._dxva2.SetVCPFeature(self._handle, code, value):
            _raise_last_error(
                f"设置 VCP 0x{code:02x}=0x{value:02x} 失败", self.description
            )

    def close(self) -> None:
        if not self._closed:
            if not self._dxva2.DestroyPhysicalMonitor(self._handle):
                error_code = ctypes.get_last_error() & 0xFFFFFFFF
                if error_code != ERROR_GRAPHICS_MONITOR_NO_LONGER_EXISTS:
                    _raise_last_error("释放物理显示器句柄失败", self.description)
            self._closed = True


class MonitorCollection:
    def __init__(self, monitors: list[WindowsMonitor]) -> None:
        self.monitors = monitors

    def __enter__(self) -> list[WindowsMonitor]:
        return self.monitors

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        first_error: Exception | None = None
        for monitor in self.monitors:
            try:
                monitor.close()
            except Exception as error:  # keep releasing the remaining handles
                first_error = first_error or error
        if exc is None and first_error is not None:
            raise first_error


def open_monitors() -> MonitorCollection:
    """Enumerate Windows logical monitors and open their physical monitor handles."""
    if sys.platform != "win32":
        raise MonitorError("DDC/CI 控制仅支持 Windows")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)
    _configure_functions(user32, dxva2)

    logical_handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    @callback_type
    def collect(handle: int, hdc: int, rect: object, data: int) -> bool:
        logical_handles.append(handle)
        return True

    if not user32.EnumDisplayMonitors(None, None, collect, 0):
        _raise_last_error("枚举逻辑显示器失败")

    monitors: list[WindowsMonitor] = []
    try:
        for logical_handle in logical_handles:
            count = wintypes.DWORD()
            if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
                logical_handle, ctypes.byref(count)
            ):
                _raise_last_error("获取物理显示器数量失败")
            physical = (PhysicalMonitor * count.value)()
            if count.value and not dxva2.GetPhysicalMonitorsFromHMONITOR(
                logical_handle, count.value, physical
            ):
                _raise_last_error("获取物理显示器失败")
            for item in physical:
                monitors.append(
                    WindowsMonitor(item.description, item.handle, dxva2)
                )
    except Exception:
        for monitor in monitors:
            monitor.close()
        raise
    return MonitorCollection(monitors)


def _configure_functions(user32: object, dxva2: object) -> None:
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        ctypes.c_void_p,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HMONITOR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HMONITOR,
        wintypes.DWORD,
        ctypes.POINTER(PhysicalMonitor),
    ]
    dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.DestroyPhysicalMonitor.argtypes = [wintypes.HANDLE]
    dxva2.DestroyPhysicalMonitor.restype = wintypes.BOOL
    dxva2.GetCapabilitiesStringLength.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    dxva2.GetCapabilitiesStringLength.restype = wintypes.BOOL
    dxva2.CapabilitiesRequestAndCapabilitiesReply.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_char),
        wintypes.DWORD,
    ]
    dxva2.CapabilitiesRequestAndCapabilitiesReply.restype = wintypes.BOOL
    dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
        wintypes.HANDLE,
        wintypes.BYTE,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
    dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
    dxva2.SetVCPFeature.restype = wintypes.BOOL


def _raise_last_error(action: str, description: str | None = None) -> None:
    error = ctypes.WinError(ctypes.get_last_error())
    target = f"（{description}）" if description else ""
    raise MonitorError(f"{action}{target}: {error}") from error
