"""Locate per-user data and launch the project's Python workers."""

import os
from pathlib import Path
import subprocess
import sys

from .brand import APP_FOLDER


NO_CONSOLE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def python_command(*arguments):
    """Select the Python interpreter or its equivalent in a packaged desktop build."""
    if not getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    worker = (Path(sys.executable).with_name(f"{APP_FOLDER}-Worker.exe")
              if sys.platform == "win32" else Path(sys.executable))
    return [str(worker), "--studio-worker", *arguments]


def application_data():
    if app_data := os.environ.get("LOCALAPPDATA"):
        return Path(app_data) / APP_FOLDER
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_FOLDER
    return None
