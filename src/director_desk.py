"""Run the bundled upstream 3D Director Desk in a local WebView."""

from base64 import b64decode
from binascii import Error as Base64Error
from contextlib import contextmanager
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
from tkinter import messagebox
from urllib.parse import urlencode, urlsplit, unquote

from PIL import Image

from .desktop_runtime import NO_CONSOLE, python_command, application_data
from .brand import APP_FOLDER, app_name
from .director_action_import import MAX_PROJECT_BYTES, import_director_cards
from .image_api import MAX_IMAGE_BYTES


ROOT = Path(__file__).resolve().parents[1]
DIRECTOR_BUNDLE = Path("assets/director_desk")
DIRECTOR_HOST = Path("assets/director_host")
RESULT = {"pose": "frame.png", "action": "project.json"}
PNG_PREFIX = "data:image/png;base64,"
MAX_TRANSFER_BYTES = ((max(MAX_IMAGE_BYTES, MAX_PROJECT_BYTES) + 2) // 3) * 4 + 4096

# Images, 3D models and textures are loaded from bundled files or local uploads.
CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "connect-src 'self' data: blob:; worker-src 'self' blob:; "
    "media-src 'self' data: blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
)


def write_result(output, mode, payload, language):
    filename = output / RESULT[mode]
    if mode == "pose":
        encoded = payload.get("dataUrl")
        if not isinstance(encoded, str) or not encoded.startswith(PNG_PREFIX):
            raise ValueError("A PNG capture is required.")
        try:
            data = b64decode(encoded[len(PNG_PREFIX):], validate=True)
        except Base64Error as error:
            raise ValueError("The PNG data is invalid.") from error
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("The PNG exceeds 32 MiB.")
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or image.width * image.height > 32_000_000 or image.n_frames != 1:
                raise ValueError("A single-frame PNG of up to 32 million pixels is required.")
            image.load()
    else:
        data = json.dumps(payload.get("project"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(data) > MAX_PROJECT_BYTES:
            raise ValueError("The Director Desk project exceeds 32 MiB.")
    pending = filename.with_suffix(".pending")
    try:
        pending.write_bytes(data)
        if mode == "action" and not import_director_cards(pending, language=language):
            raise ValueError("Add at least two path points to a visible character or prop."
                             if language == "en" else "请给一个可见角色或道具添加至少两个路线点。")
        pending.replace(filename)
    finally:
        pending.unlink(missing_ok=True)


@contextmanager
def director_server(output, mode, language, *, port=0):
    """Only serve assets on loopback and accept a single authorized handoff."""
    token = secrets.token_urlsafe(24)
    finished = Event()
    receive_lock = Lock()
    directories = {folder.name: (ROOT / folder).resolve() for folder in (DIRECTOR_BUNDLE, DIRECTOR_HOST)}

    class Handler(SimpleHTTPRequestHandler):
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                          ".js": "text/javascript", ".wasm": "application/wasm"}
        timeout = 35

        def log_message(self, *_args):
            pass

        def log_request(self, code="-", size="-"):
            if os.environ.get("STUDIO_DIRECTOR_SMOKE") == "1":
                with (output / "requests.log").open("a", encoding="utf-8") as stream:
                    print(f"{self.command} {urlsplit(self.path).path} {code}", file=stream)

        def end_headers(self):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def valid_host(self):
            return self.headers.get("Host") == urlsplit(origin).netloc

        def send_head(self):
            if self.valid_host():
                _, _, url_path = unquote(urlsplit(self.path).path).partition("/")
                name, _, suffix = url_path.partition("/")
                root = directories.get(name)
                if root is not None and "\\" not in suffix:
                    target = (root / (suffix or "index.html")).resolve()
                    if target.is_relative_to(root) and target.is_file():
                        stream = target.open("rb")
                        self.send_response(200)
                        self.send_header("Content-Type", self.guess_type(str(target)))
                        self.send_header("Content-Length", str(os.fstat(stream.fileno()).st_size))
                        self.end_headers()
                        return stream
            self.send_error(404)
            return None

        def do_POST(self):
            if (not self.valid_host() or self.path != "/__director_output" or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-ComicFlow-Director", ""), token)):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_TRANSFER_BYTES:
                    raise ValueError("The Director Desk result is too large or empty.")
                payload = json.loads(self.rfile.read(size))
                kind = payload.get("kind") if isinstance(payload, dict) else None
                with receive_lock:
                    if kind == "ready":
                        (output / "ready").touch()
                    elif not finished.is_set() and kind in {mode, "close"}:
                        if kind == mode:
                            write_result(output, mode, payload, language)
                    else:
                        raise ValueError("The Director Desk result does not match this window.")
                    self.reply(200, {"ok": True})
                    if kind in {mode, "close"}:
                        finished.set()
            except (OSError, ValueError, RecursionError, Image.DecompressionBombError) as error:
                self.reply(400, {"ok": False, "error": str(error)})

        def reply(self, status, data):
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield origin, token, finished
        finally:
            server.shutdown()
            thread.join()


def session_url(origin, token, instance, language, mode):
    query = urlencode({"token": token, "instanceId": instance, "language": language, "mode": mode})
    return f"{origin}/director_host/?{query}"


def run_window(output, instance, language, mode):
    english = language == "en"
    if not (ROOT / DIRECTOR_BUNDLE / "index.html").is_file():
        raise OSError("This build does not contain the 3D Director Desk. Reinstall the complete Windows trial."
                      if english else "当前安装缺少内置 3D 导演台。请重新解压完整的 Windows 试用包。")
    try:
        import webview
    except ImportError as error:
        raise RuntimeError(f"Run {APP_FOLDER}-Setup.bat to install the desktop WebView."
                           if english else f"请运行 {APP_FOLDER}-Setup.bat 补装桌面 WebView。") from error

    appdata = application_data() or Path.home() / ".local" / "share" / APP_FOLDER
    profile = appdata / "director-webview"
    profile.mkdir(parents=True, exist_ok=True)
    port_file = profile / "port.txt"
    port = int(port_file.read_text("ascii")) if port_file.is_file() else 0
    try:
        with director_server(output, mode, language, port=port) as (origin, token, finished):
            if not port:
                port_file.write_text(urlsplit(origin).netloc.rsplit(":", 1)[-1], encoding="ascii")
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
            webview.settings["ALLOW_DOWNLOADS"] = True
            window = webview.create_window(
                f"{app_name(language)} · " + ("3D Director Desk" if english else "3D 导演台"),
                session_url(origin, token, instance, language, mode), width=1280, height=830, min_size=(940, 610),
            )

            closed = Event()

            def window_closed():
                closed.set()
                finished.set()

            def wait_for_result():
                if os.environ.get("STUDIO_DIRECTOR_SMOKE") == "1":
                    def diagnose():
                        try:
                            status = window.evaluate_js(
                                "({secure:isSecureContext, text:document.querySelector('#status')?.textContent})"
                            )
                            (output / "webview-status.txt").write_text(str(status), encoding="utf-8")
                        except Exception as error:
                            (output / "webview-status.txt").write_text(type(error).__name__, encoding="utf-8")

                    from threading import Timer

                    timer = Timer(10, diagnose)
                    timer.daemon = True
                    timer.start()
                finished.wait()
                if not closed.is_set():
                    window.destroy()

            window.events.closed += window_closed
            webview.start(wait_for_result, gui="edgechromium" if sys.platform == "win32" else None,
                          private_mode=False, storage_path=str(profile / "browser"))
    except OSError as error:
        if error.errno in {98, 48, 10048} or getattr(error, "winerror", None) == 10048:
            raise RuntimeError("A 3D Director Desk session is already using the local workspace. Close it and try again."
                               if english else "已有 3D 导演台窗口占用本地工作区。关闭后再打开。") from error
        raise


def director_uses(parent):
    session = getattr(parent._root(), "_director_session", None)
    return bool(session and session[1] is parent)


def open_director(parent, project_path, mode, on_result, *, language="zh"):
    root = parent._root()
    current = getattr(root, "_director_session", None)
    english = language == "en"
    title = "3D Director Desk" if english else "3D 导演台"
    if current is not None:
        if current[1] is not parent:
            raise RuntimeError("3D Director Desk is already open for another group. Finish that session first."
                               if english else "另一组已打开 3D 导演台，请先完成那一组的取景。")
        return
    instance = "comicflow_" + sha256(os.fsencode(Path(project_path).resolve())).hexdigest()[:24]
    temporary = TemporaryDirectory(prefix="comicflow-director-")
    output = Path(temporary.name)
    try:
        process = subprocess.Popen(
            python_command("-m", "src.director_desk", str(output), instance, language, mode),
            cwd=ROOT, creationflags=NO_CONSOLE,
        )
    except OSError:
        temporary.cleanup()
        raise
    root._director_session = (process, parent)

    def cancel(event):
        if event.widget == parent and process.poll() is None:
            process.terminate()

    def receive():
        if process.poll() is None:
            root.after(150, receive)
            return
        try:
            if not parent.winfo_exists():
                return
            parent.unbind("<Destroy>", binding)
            result = output / RESULT[mode]
            error = output / "error.txt"
            if result.is_file():
                on_result(result)
            elif error.is_file():
                messagebox.showerror(title, error.read_text("utf-8"), parent=parent)
            elif process.returncode:
                messagebox.showerror(title, "The desktop 3D window could not launch." if english
                                     else "无法启动本地 3D 导演台窗口。", parent=parent)
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror(title, str(error), parent=parent)
        finally:
            root._director_session = None
            temporary.cleanup()

    binding = parent.bind("<Destroy>", cancel, add="+")
    root.after(150, receive)


if __name__ == "__main__":
    folder, instance, language, mode = sys.argv[1:]
    try:
        run_window(Path(folder), instance, language, mode)
    except Exception as error:
        Path(folder, "error.txt").write_text(str(error), encoding="utf-8")
        sys.exit(1)
