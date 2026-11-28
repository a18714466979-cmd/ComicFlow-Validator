from base64 import b64encode
from io import BytesIO
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
import pytest

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
