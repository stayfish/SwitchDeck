from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence

from switchdeck.monitor import INPUT_SOURCE_VCP_CODE, Monitor, MonitorError, parse_number
from switchdeck.windows import open_monitors

LOGGER = logging.getLogger("switchdeck")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="switchdeck", description="通过 Windows DDC/CI 控制显示器输入源"
    )
    parser.add_argument(
        "--monitor", default="U2724D", help="显示器描述匹配文本（默认: U2724D）"
    )
    parser.add_argument(
        "--index", type=int, default=0, help="有多个匹配结果时选择的序号（默认: 0）"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="枚举物理显示器并尝试读取输入源")
    subparsers.add_parser("capabilities", help="读取显示器 capabilities 字符串")
    subparsers.add_parser("get", help="读取当前输入源 VCP 0x60")

    set_parser = subparsers.add_parser("set", help="设置输入源 VCP 0x60")
    set_parser.add_argument("value", type=parse_number, help="输入源值，如 0x0f")

    roundtrip = subparsers.add_parser(
        "roundtrip", help="切到另一输入源，并在延时后用同一句柄切回来"
    )
    roundtrip.add_argument("away", type=parse_number, help="目标输入源值（Mac）")
    roundtrip.add_argument("back", type=parse_number, help="返回输入源值（Windows）")
    roundtrip.add_argument("--delay", type=float, default=8.0, help="返回前等待秒数")

    agent = subparsers.add_parser("agent", help="启动托盘后台程序和全局快捷键")
    agent.add_argument(
        "--windows-input", type=parse_number, default=0x11, help="Windows 输入值"
    )
    agent.add_argument("--mac-input", type=parse_number, default=0x0F, help="Mac 输入值")
    return parser


def select_monitor(monitors: Sequence[Monitor], name: str, index: int) -> Monitor:
    matches = [monitor for monitor in monitors if name.casefold() in monitor.description.casefold()]
    if not matches:
        available = ", ".join(m.description for m in monitors) or "（未发现显示器）"
        raise MonitorError(f"找不到包含 {name!r} 的显示器。可用: {available}")
    if index < 0 or index >= len(matches):
        raise MonitorError(f"匹配到 {len(matches)} 台显示器，--index {index} 超出范围")
    return matches[index]


def describe_vcp(monitor: Monitor) -> str:
    value = monitor.get_vcp(INPUT_SOURCE_VCP_CODE)
    return f"current=0x{value.current:02x} ({value.current}), max=0x{value.maximum:02x}"


def run(args: argparse.Namespace) -> int:
    if args.command == "agent":
        from switchdeck.agent import run_agent

        return run_agent(
            monitor_name=args.monitor,
            monitor_index=args.index,
            windows_input=args.windows_input,
            mac_input=args.mac_input,
        )

    with open_monitors() as monitors:
        if args.command == "list":
            if not monitors:
                LOGGER.warning("未发现物理显示器")
                return 1
            for index, monitor in enumerate(monitors):
                try:
                    source = describe_vcp(monitor)
                except MonitorError as error:
                    source = f"VCP 0x60 不可读: {error}"
                LOGGER.info("[%d] %s — %s", index, monitor.description, source)
            return 0

        monitor = select_monitor(monitors, args.monitor, args.index)
        LOGGER.info("已选择: %s", monitor.description)
        if args.command == "capabilities":
            LOGGER.info("%s", monitor.capabilities())
        elif args.command == "get":
            LOGGER.info("VCP 0x60: %s", describe_vcp(monitor))
        elif args.command == "set":
            monitor.set_vcp(INPUT_SOURCE_VCP_CODE, args.value)
            LOGGER.info("已发送 VCP 0x60=0x%02x", args.value)
        elif args.command == "roundtrip":
            LOGGER.info("切换到 0x%02x", args.away)
            monitor.set_vcp(INPUT_SOURCE_VCP_CODE, args.away)
            LOGGER.info("等待 %.1f 秒后切回 0x%02x", args.delay, args.back)
            time.sleep(args.delay)
            monitor.set_vcp(INPUT_SOURCE_VCP_CODE, args.back)
            LOGGER.info("已发送切回命令")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "delay", 0) < 0:
        parser.error("--delay 不能是负数")
    try:
        return run(args)
    except (MonitorError, OSError, ValueError) as error:
        LOGGER.error("错误: %s", error)
        return 1
