from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from switchdeck.icon import create_tray_image  # noqa: E402


def main() -> None:
    assets = PROJECT_ROOT / ".build-assets"
    assets.mkdir(exist_ok=True)
    image = create_tray_image(512)
    if sys.platform == "win32":
        icon_path = assets / "switchdeck.ico"
        image.save(icon_path, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    elif sys.platform == "darwin":
        icon_path = assets / "switchdeck.icns"
        image.save(icon_path, format="ICNS")
    else:
        raise SystemExit("桌面应用构建仅支持 Windows 和 macOS")

    PyInstaller.__main__.run(
        [
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name=SwitchDeck",
            f"--icon={icon_path}",
            f"--paths={PROJECT_ROOT / 'src'}",
            "--collect-all=pystray",
            "--collect-all=pynput",
            str(PROJECT_ROOT / "src" / "switchdeck" / "launcher.py"),
        ]
    )


if __name__ == "__main__":
    main()
