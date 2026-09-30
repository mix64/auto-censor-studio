"""Writable user data is kept outside the source tree and installed package."""

import os
from pathlib import Path


def data_directory():
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    target = root / "AutoCensorStudio"
    target.mkdir(parents=True, exist_ok=True)
    return target


def model_directory():
    override = os.environ.get("AUTO_CENSOR_MODEL_DIR")
    return Path(override).expanduser().resolve() if override else data_directory() / "models"
