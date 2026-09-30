"""Bundle the app and its Python runtime into dist/AutoCensorStudio with PyInstaller."""

from pathlib import Path

import PyInstaller.__main__


def main():
    root = Path(__file__).resolve().parents[1]
    assets = root / "auto_censor_studio" / "assets"
    PyInstaller.__main__.run(
        [
            str(root / "app.py"),
            "--name=AutoCensorStudio",
            "--onedir",
            "--windowed",
            "--noconfirm",
            "--clean",
            f"--icon={assets / 'app-icon.ico'}",
            f"--add-data={assets};auto_censor_studio/assets",
            f"--distpath={root / 'dist'}",
            f"--workpath={root / 'build'}",
            f"--specpath={root / 'build'}",
            "--exclude-module=tkinter",
        ]
    )


if __name__ == "__main__":
    main()
