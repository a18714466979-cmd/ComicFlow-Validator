from base64 import b64encode
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
import pytest

from src import director_desk
from src.director_desk import director_server, session_url
from src.director_action_import import import_director_cards


def submit(origin, token, payload):
    request = Request(origin + "/__director_output", data=json.dumps(payload).encode(), headers={
        "Origin": origin, "X-ComicFlow-Director": token, "Content-Type": "application/json",
    })
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def test_local_director_pose_handoff_preserves_png(tmp_path):
    with director_server(tmp_path, "pose", "en") as (origin, token, finished):
        with urlopen(session_url(origin, token, "storyboard", "en", "pose"), timeout=5) as response:
            assert b"host.js" in response.read()
            assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
        with pytest.raises(HTTPError, match="403"):
            submit(origin, "other", {"kind": "ready"})
        assert not (tmp_path / "ready").exists()
        assert submit(origin, token, {"kind": "ready"})["ok"]
        assert (tmp_path / "ready").is_file()
        with pytest.raises(HTTPError, match="400"):
            submit(origin, token, {"kind": "pose", "dataUrl": "data:image/png;base64,AAAA"})
        assert not finished.is_set()
        stream = BytesIO()
        Image.new("RGB", (16, 9), "indigo").save(stream, "PNG")
        encoded = b64encode(stream.getvalue()).decode()
        assert submit(origin, token, {"kind": "pose", "dataUrl": "data:image/png;base64," + encoded})["ok"]
        assert finished.wait(1)
        assert (tmp_path / "frame.png").read_bytes() == stream.getvalue()


def test_action_handoff_waits_for_usable_tracks(tmp_path):
    with director_server(tmp_path, "action", "en") as (origin, token, finished):
        scene = {"version": 1, "scene": {"backgroundColor": "#ffffff"}, "assets": [], "cameras": [], "objects": []}
        with pytest.raises(HTTPError, match="400"):
            submit(origin, token, {"kind": "action", "project": scene})
        assert not (tmp_path / "project.json").exists()
        assert not finished.is_set()

        points = [{"time": step, "transform": {"position": [step, 0, 0], "rotation": [0, 0, 0]}}
                  for step in (0, 1)]
        scene["objects"].append({"kind": "character", "visible": True, "name": "Actor",
                                 "motionPath": {"keyframes": points}})
        assert submit(origin, token, {"kind": "action", "project": scene})["ok"]
        assert finished.wait(1)
        assert import_director_cards(tmp_path / "project.json", language="en")[0]["actor"] == "Actor"


def test_workbench_director_uses_one_window_and_calls_the_origin(tmp_path, monkeypatch):
    class Workbench:
        def __init__(self):
            self.callbacks = []

        def after(self, _milliseconds, callback):
            self.callbacks.append(callback)

    class Tab:
        def __init__(self, workbench):
            self.workbench = workbench

        def _root(self):
            return self.workbench

        def bind(self, *_args, **_kwargs):
            return "director"

        def unbind(self, *_args):
            pass

        def winfo_exists(self):
            return True

    class Process:
        returncode = None

        def poll(self):
            return self.returncode

    launches = []
    process = Process()

    def spawn(args, **_options):
        launches.append(Path(args[3]))
        return process

    monkeypatch.setattr(director_desk.subprocess, "Popen", spawn)
    workbench = Workbench()
    first, second = Tab(workbench), Tab(workbench)
    captures = []
    capture = lambda path: captures.append(path.read_bytes())
    director_desk.open_director(first, tmp_path / "SB03.cfproject", "pose", capture)
    director_desk.open_director(first, tmp_path / "SB03.cfproject", "pose", capture)
    with pytest.raises(RuntimeError, match="already open"):
        director_desk.open_director(second, tmp_path / "SB04.cfproject", "pose",
                                   lambda _: pytest.fail("A result went to the other group."), language="en")

    assert len(launches) == 1 and director_desk.director_uses(first)
    assert not director_desk.director_uses(second)
    Image.new("RGB", (16, 9), "blue").save(launches[0] / "frame.png")
    process.returncode = 0
    workbench.callbacks.pop(0)()
    assert len(captures) == 1 and captures[0].startswith(b"\x89PNG")
    assert not director_desk.director_uses(first) and not launches[0].exists()
