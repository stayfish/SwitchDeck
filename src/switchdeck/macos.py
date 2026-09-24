from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass

from switchdeck.monitor import INPUT_SOURCE_VCP_CODE, MonitorError, VcpValue


@dataclass(slots=True)
class MacMonitor:
    description: str
    helper: str
    display: str

    def capabilities(self) -> str:
        raise MonitorError("macOS DDC helper 不支持读取 MCCS capabilities")

    def get_vcp(self, code: int) -> VcpValue:
        if code != INPUT_SOURCE_VCP_CODE or Path(self.helper).name != "m1ddc":
            raise MonitorError("当前 macOS DDC helper 不支持可靠读取 VCP 值")
        command = self._m1ddc_prefix() + ["get", "input"]
        output = _run(command)
        numbers = re.findall(r"(?:0x[0-9a-fA-F]+|\b\d+\b)", output)
        if not numbers:
            raise MonitorError(f"无法解析 m1ddc 返回值: {output.strip()}")
        current = int(numbers[-1], 0)
        return VcpValue(current=current, maximum=current)

    def set_vcp(self, code: int, value: int) -> None:
        if code != INPUT_SOURCE_VCP_CODE:
            raise MonitorError(f"macOS 后端目前仅支持输入源 VCP 0x60，而非 0x{code:02x}")
        if Path(self.helper).name == "m1ddc":
            command = self._m1ddc_prefix() + ["set", "input", str(value)]
        else:
            command = [self.helper, "-d", self.display, "-i", str(value)]
        _run(command)

    def close(self) -> None:
        return None

    def _m1ddc_prefix(self) -> list[str]:
        if self.display == "default":
            return [self.helper]
        return [self.helper, "display", self.display]


class MonitorCollection:
    def __init__(self, monitors: list[MacMonitor]) -> None:
        self.monitors = monitors

    def __enter__(self) -> list[MacMonitor]:
        return self.monitors

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        for monitor in self.monitors:
            monitor.close()


def open_monitors() -> MonitorCollection:
    helper = _find_helper()
    architecture = platform.machine().lower()
    description = f"macOS external display ({helper}, {architecture})"
    display = "default" if Path(helper).name == "m1ddc" else "1"
    return MonitorCollection([MacMonitor(description, helper, display)])


def _find_helper() -> str:
    preferred = ("m1ddc", "ddcctl") if platform.machine().lower() in {"arm64", "aarch64"} else ("ddcctl", "m1ddc")
    for name in preferred:
        path = shutil.which(name)
        if path:
            return path
    if preferred[0] == "m1ddc":
        instruction = "brew install m1ddc"
    else:
        instruction = "brew install ddcctl"
    raise MonitorError(f"未找到 macOS DDC helper，请先运行: {instruction}")


def _run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"退出码 {result.returncode}"
        raise MonitorError(f"macOS DDC 命令失败: {detail}")
    return result.stdout
