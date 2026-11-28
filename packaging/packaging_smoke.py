"""Exercise the installed runtime without a system Python or system FFmpeg."""

import json
from pathlib import Path
import platform
from shutil import copytree
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import traceback

from scripts.verify_windows_trial import exercise_sample
from src.brand import VERSION, app_name
from src.bundled_validators import bundled_validator
from src.desktop_runtime import NO_CONSOLE, python_command
from src.ecommerce_video import analyze_video, resolve_ffmpeg
from src.production_rules import CHINESE, ENGLISH
from src.windows_launcher import open_workbench


def verify_director(folder):
    process = subprocess.Popen(
        python_command("-m", "src.director_desk", str(folder), "installer-smoke", "en", "pose"),
        creationflags=NO_CONSOLE,
    )
    try:
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if (folder / "ready").is_file():
                return
            if process.poll() is not None:
                error = folder / "error.txt"
                detail = error.read_text(encoding="utf-8") if error.is_file() else str(process.returncode)
                raise RuntimeError(f"The bundled 3D Director Desk exited before drawing: {detail}")
            time.sleep(0.15)
        raise TimeoutError("The bundled native 3D Director Desk did not signal bridge readiness.")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=8)


def exercise(report_path):
    root = Path(sys._MEIPASS)
    checks = []
    result = {"status": "failed", "version": VERSION, "platform": sys.platform, "architecture": platform.machine(),
              "checks": checks}
    try:
        result["revision"] = (root / "REVISION.txt").read_text(encoding="utf-8").strip()
        result["installer_build"] = (root / "INSTALLER-BUILD.txt").read_text(encoding="ascii").strip()
        with TemporaryDirectory(prefix="Studio installed 试用 ") as temp:
            base = Path(temp)
            ffmpeg = Path(resolve_ffmpeg())
            assert ffmpeg.name in {"ffmpeg.exe", "ffmpeg"} and ffmpeg.parent == root / "tools"
            analysis = analyze_video(root / "Examples" / "Workbench" / "Ecommerce" / "Reference.mp4")
            assert analysis.info.duration_ms and len(analysis.shots) > 1
            checks.append("Bundled FFmpeg decoded the e-commerce practice video and found cuts")

            examples = base / "Examples"
            copytree(root / "Examples", examples)
            for language, folder, counts in ((ENGLISH, examples, (9, 9)), (CHINESE, examples / "中文制作", (10, 9))):
                script = bundled_validator(language)
                assert script and script.is_file()
                exercise_sample(folder, base, script, language, counts)
            checks.append("English and Chinese single-group, two-group and repair ZIPs passed with bundled validators")

            def inspect_window(window):
                try:
                    window.update_idletasks()
                    assert window.title() == app_name(window.ui_language) and window.winfo_ismapped()
                    checks.append("The installed Studio opened its Tk workbench")
                except Exception:
                    result["tk_error"] = traceback.format_exc()
                finally:
                    window.destroy()

            assert open_workbench("", on_ready=inspect_window) == 0
            if "tk_error" in result:
                raise RuntimeError(result["tk_error"])
            base.joinpath("director").mkdir()
            verify_director(base / "director")
            checks.append("Bundled 3D Director Desk opened and completed its native WebView handshake")
        result["status"] = "ok"
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        report = json.dumps(result, ensure_ascii=False)
        report_path.write_text(report, encoding="utf-8")
        if sys.stdout is not None:
            print(report, flush=True)
    return 0 if result["status"] == "ok" else 1
