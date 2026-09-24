from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from pathlib import Path

from switchdeck.agent import run_agent


def main() -> int:
    _configure_file_logging()
    try:
        return run_agent(
            monitor_name="U2724D",
            monitor_index=0,
            input_a=0x11,
            input_b=0x0F,
        )
    except Exception as error:
        logging.getLogger("switchdeck").exception("SwitchDeck 启动失败")
        _show_error(str(error))
        return 1


def _configure_file_logging() -> None:
    if sys.platform == "win32":
        directory = Path.home() / "AppData" / "Local" / "SwitchDeck"
    else:
        directory = Path.home() / "Library" / "Logs" / "SwitchDeck"
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=directory / "switchdeck.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _show_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "SwitchDeck 启动失败", 0x10)
    elif sys.platform == "darwin":
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(
            ["osascript", "-e", f'display alert "SwitchDeck 启动失败" message "{escaped}"'],
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
