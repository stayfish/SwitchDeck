from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

INPUT_SOURCE_VCP_CODE = 0x60


class MonitorError(RuntimeError):
    """Raised when a monitor DDC/CI operation fails."""


@dataclass(frozen=True, slots=True)
class VcpValue:
    current: int
    maximum: int


class Monitor(Protocol):
    description: str

    def capabilities(self) -> str: ...

    def get_vcp(self, code: int) -> VcpValue: ...

    def set_vcp(self, code: int, value: int) -> None: ...

    def close(self) -> None: ...


def parse_number(value: str) -> int:
    """Parse a decimal or 0x-prefixed monitor value."""
    number = int(value, 0)
    if not 0 <= number <= 0xFFFFFFFF:
        raise ValueError("数值必须在 0 到 0xffffffff 之间")
    return number
