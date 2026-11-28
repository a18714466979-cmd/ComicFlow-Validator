"""Drive the real local 3D Motion Clip interface and inspect clean camera frames."""

import argparse
from base64 import b64decode
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image


def legacy_scene(source):
    """An older project with two mannequins and one thin, colored envelope stand-in."""
    project = deepcopy(source)
    project.pop("motionClip", None)
    sender, = (item for item in project["objects"] if item["kind"] == "character")
    sender["name"] = "Sender"
    sender["color"] = "#4F8EF7"
    sender["transform"]["position"] = [-1.10, 0, 0]
    receiver = deepcopy(sender)
    receiver.update(id="clip-smoke-receiver", name="Receiver", color="#16BE61")
    receiver["transform"]["position"] = [1.62, 0, 0]
    envelope = {
        "id": "clip-smoke-envelope", "name": "Envelope", "kind": "prop", "geometryType": "box",
        "visible": True, "locked": False, "color": "#F84616",
        "transform": {"position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [.24, .07, .19]},
    }
    project["objects"].extend([receiver, envelope])
    return project, sender["id"], receiver["id"], envelope["id"]


def camera_pixels(frame):
    with Image.open(BytesIO(frame)) as image:
        assert image.format == "PNG" and image.size == (1280, 720), (image.format, image.size)
        image.load()
        return np.asarray(image.convert("RGB"), dtype=np.int16)


def colored_pixels(frame, primary):
    red, green, blue = frame.transpose(2, 0, 1)
    filters = {
        "blue": (blue > red + 18) & (blue > green + 8) & (blue > 35),
        "green": (green > red + 20) & (green > blue + 10) & (green > 35),
        "orange": (red > green + 34) & (red > blue + 34) & (red > 65),
    }
    y, x = np.nonzero(filters[primary])
    assert len(x) >= (24 if primary == "orange" else 1000), (primary, len(x))
    return np.array([x.mean(), y.mean(), np.percentile(x, 2), np.percentile(x, 98),
                     np.percentile(y, 2), np.percentile(y, 98)])


def close_frame(first, second, description):
    delta = np.max(np.abs(first - second), axis=2)
    different = (delta > 8).mean()
    assert different < .004, (description, different)


def exercise_director_motion_clip(run_js, until, desk, click, output, language="en"):
    """Run the same scenario in Chromium and the Windows build's real Edge WebView."""
    output = Path(output)

    def target(name):
        return "desk.querySelector(" + json.dumps(f'[data-testid="motion-clip-{name}"]') + ")"

    def press(name):
        click(f'[data-testid="motion-clip-{name}"]')

    def exists(name):
        return run_js(desk(f"Boolean({target(name)})"))

    def value(name):
        return run_js(desk(f"{target(name)}?.value ?? null"))

    def set_value(name, new, *, commit=False):
        control = target(name)
        until(desk(f"Boolean({control} && !{control}.disabled)"), f"Missing enabled motion control {name}")
        run_js(desk(f"""(() => {{
            const element = {control};
            const view = desk.defaultView;
            if ({json.dumps(commit)}) element.focus();
            Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), 'value').set.call(element, {json.dumps(str(new))});
            element.dispatchEvent(new view.Event('input', {{bubbles: true}}));
            element.dispatchEvent(new view.Event('change', {{bubbles: true}}));
            return true;
        }})()"""))
        if commit:
            run_js(desk(f"{control}.blur()"))

    def ask(action, options=None):
        run_js(f"""void (() => {{
            const frame = document.querySelector('#desk').contentWindow;
            const requestId = crypto.randomUUID();
            window.actionClipSmokeResult = null;
            const receive = (event) => {{
                if (event.source !== frame || event.origin !== location.origin ||
                    event.data?.type !== 'storyai:director-desk:response' ||
                    event.data.payload?.requestId !== requestId) return;
                removeEventListener('message', receive);
                window.actionClipSmokeResult = event.data.payload;
            }};
            addEventListener('message', receive);
            frame.postMessage({{
                type: 'storyai:director-desk:request',
                payload: {{requestId, action: {json.dumps(action)}, options: {json.dumps(options or {})}}}
            }}, location.origin);
        }})()""")
        return until("window.actionClipSmokeResult", f"No director response to {action}")

    def project():
        answer = ask("project.get")
        assert answer["ok"], answer
        return answer["data"]["project"]

    def open_panel():
        if not exists("panel"):
            press("toggle")
        until(desk(f"Boolean({target('panel')})"), "Motion Clip panel did not open")

    def import_project(document):
        open_panel()
        field = target("project-file")
        until(desk(f"Boolean({field})"), "Motion Clip Open Project file picker is missing")
        run_js(desk(f"""(() => {{
            const view = desk.defaultView;
            const files = new view.DataTransfer();
            files.items.add(new view.File([{json.dumps(json.dumps(document))}], "clip-smoke.json",
                {{type: "application/json"}}));
            const input = {field};
            input.files = files.files;
            input.dispatchEvent(new view.Event("change", {{bubbles: true}}));
            return true;
        }})()"""))

    def save_project():
        # The test captures the actual project download Blob before the native save UI opens.
        run_js(desk("""(() => {
            const view = desk.defaultView;
            view.motionClipSmokeSaved = null;
            const createObjectURL = view.URL.createObjectURL;
            const anchorClick = view.HTMLAnchorElement.prototype.click;
            const exported = new Map();
            view.URL.createObjectURL = function (blob) {
                const url = createObjectURL.call(this, blob);
                exported.set(url, blob);
                return url;
            };
            view.HTMLAnchorElement.prototype.click = function () {
                if (!this.download.endsWith(".json") || !exported.has(this.href)) {
                    return anchorClick.call(this);
                }
                const blob = exported.get(this.href);
                view.URL.createObjectURL = createObjectURL;
                view.HTMLAnchorElement.prototype.click = anchorClick;
                blob.text().then((text) => { view.motionClipSmokeSaved = text; });
            };
            return true;
        })()"""))
        press("save")
        return json.loads(until(desk("desk.defaultView.motionClipSmokeSaved"), "No project JSON was saved"))

    def seek(seconds):
        set_value("scrub", seconds)
        until(desk(f"Math.abs(Number({target('scrub')}.value) - {seconds}) < .0001"), "Seek did not apply")

    def select_actor(actor_id):
        press("actor-tab")
        set_value("actor", actor_id)

    def actor_keys(actor_id):
        return next(track["keyframes"] for track in project()["motionClip"]["actorTracks"] if track["actorId"] == actor_id)

    def capture(label):
        for attempt in range(4):
            answer = ask("export.frame", {"quality": "720p", "position": "current"})
            if answer["ok"]:
                break
            message = answer["error"]["message"]
            assert attempt < 3 and message in {
                "当前浏览器无法导出成片帧", "成片帧导出器尚未准备好",
            }, (label, message)
            time.sleep(.25)
        frame = b64decode(answer["data"]["dataUrl"].split(",", 1)[1], validate=True)
        (output / f"clip-{label}.png").write_bytes(frame)
        return camera_pixels(frame)

    english = language == "en"
    toggle_text = until(desk(f"{target('toggle')}?.textContent.trim()"), "Motion Clip entry is missing")
    assert ("Action clip" if english else "动作片段") in toggle_text, toggle_text
    old, sender, receiver, envelope = legacy_scene(project())
    old_key_count = len(old["objects"])
    import_project(old)
    until(desk('Boolean(desk.querySelector(\'[aria-label="Sender"]\'))'), "The older project did not open")
    assert "motionClip" not in project() and len(project()["objects"]) == old_key_count
    click('[aria-label="选择画幅比例"]')
    click(".viewport-aspect-option:has(.viewport-aspect-option-frame-16-9)")
    original_cameras = project()["cameras"]

    open_panel()
    assert float(run_js(desk(f"{target('scrub')}.max"))) == 5
    select_actor(sender)
    seek(0)
    press("add")
    original, = actor_keys(sender)
    assert original["time"] == 0
    seek(1.25)
    set_value("actor-position-x", -.69, commit=True)
    set_value("actor-rotation-y", 46, commit=True)
    set_value("pose-preset", "t-pose")
    set_value("interpolation", "hold")
    press("add")
    raised = actor_keys(sender)[-1]
    assert raised["time"] == 1.25 and raised["interpolation"] == "hold" and raised["controls"], raised

    press(f"key-{raised['id']}")
    set_value("key-time", 1.5, commit=True)
    press("move")
    assert [key["time"] for key in actor_keys(sender)] == [0, 1.5]
    press(f"key-{original['id']}")
    set_value("key-time", 5, commit=True)
    press("duplicate")
    copied = actor_keys(sender)[-1]
    assert copied["time"] == 5 and copied["id"] != original["id"]
    assert copied["transform"] == original["transform"] and copied["controls"] == original["controls"]

    press(f"key-{copied['id']}")
    press("delete")
    assert [key["time"] for key in actor_keys(sender)] == [0, 1.5]
    press("undo")
    assert [key["time"] for key in actor_keys(sender)] == [0, 1.5, 5]
    press(f"key-{raised['id']}")
    set_value("key-time", 3, commit=True)
    press("duplicate")
    set_value("interpolation", "linear")
    print("Verified visual actor-key add, move, duplicate, delete and undo", flush=True)

    select_actor(receiver)
    for second in (0, 2.4):
        seek(second)
        press("add")
    seek(3)
    for joint, angle in (("leftShoulder.spread", -70), ("leftShoulder.pitch", 15), ("leftElbow.bend", 10)):
        set_value("joint", joint)
        set_value("joint-angle", angle, commit=True)
    press("add")
    seek(5)
    set_value("actor-position-x", 1.82, commit=True)
    set_value("pose-preset", "stand")
    press("add")
    assert [key["time"] for key in actor_keys(receiver)] == [0, 2.4, 3, 5]
    assert [key["time"] for key in actor_keys(sender)] == [0, 1.5, 3, 5]

    press("prop-tab")
    set_value("prop", envelope)
    for second, actor_id, hand in ((0, sender, "right"), (3, receiver, "left")):
        seek(second)
        set_value("prop-holder", f"actor:{actor_id}:{hand}")
        press("prop-add")
    completed = project()
    clip = completed["motionClip"]
    events = clip["propTracks"][0]["keyframes"]
    assert [(key["time"], key["holder"]["actorId"], key["holder"]["hand"]) for key in events] == [
        (0, sender, "right"), (3, receiver, "left"),
    ]
    assert len(clip["actorTracks"]) == 2 and completed["cameras"] == original_cameras
    assert completed["activeCameraId"] == old["activeCameraId"]

    # The endpoint, the arrival and both sides of the change are sampled independently.
    frames = {}
    for label, second in (
        ("start", 0), ("turning", .75), ("raised", 1.5), ("hold", 2.2),
        ("offer", 2.999), ("handoff", 3), ("end", 5), ("handoff-repeat", 3),
    ):
        seek(second)
        frames[label] = capture(label)
    starts = colored_pixels(frames["start"], "blue")
    turns = colored_pixels(frames["turning"], "blue")
    raised = colored_pixels(frames["raised"], "blue")
    before = colored_pixels(frames["offer"], "orange")
    after = colored_pixels(frames["handoff"], "orange")
    assert 4 < turns[0] - starts[0] < raised[0] - starts[0], (starts, turns, raised)
    assert raised[3] - raised[2] > starts[3] - starts[2] + 12, (starts, raised)
    close_frame(frames["raised"], frames["hold"], "The held frame changed before the handoff")
    assert abs(colored_pixels(frames["start"], "orange")[0] - before[0]) > 12
    assert np.linalg.norm(before[:2] - after[:2]) < 25, (before, after)
    assert colored_pixels(frames["end"], "orange")[0] - after[0] > 85
    close_frame(frames["handoff"], frames["handoff-repeat"], "Seeking back to the handoff changed its image")
    print("Verified actual 720p camera frames for turn, raised arms, hold, hand-following and one transfer", flush=True)

    selected_loop = run_js(desk(f"{target('loop')}.checked"))
    if not selected_loop:
        press("loop")
    seek(4.95)
    press("play")
    until(desk(f"Number({target('scrub')}.value) < 2"), "The motion clip did not loop to the beginning")
    press("play")
    document = save_project()
    assert document["format"] == "3d-director-desk-project" and document["project"]["motionClip"] == clip
    import_project(old)
    until(desk('Boolean(desk.querySelector(\'[aria-label="Sender"]\'))'), "The old project stopped reopening")
    for attempt in range(5):
        if "motionClip" not in project():
            break
        assert attempt < 4, "Opening an older project retained the previous clip"
        time.sleep(.12)
    import_project(document)
    for attempt in range(5):
        if project().get("motionClip") == clip:
            break
        assert attempt < 4, "The saved Motion Clip project did not reopen"
        time.sleep(.12)
    open_panel()
    seek(3)
    close_frame(frames["handoff"], capture("reopened"), "The reopened clip changed the handoff pose or camera")
    assert project()["cameras"] == completed["cameras"]
    print("Verified five-second looping, explicit save/open, older project reopening and identical camera state", flush=True)


def run_chromium(product, executable, output, language):
    """Run this WebView regression against an unpacked build in local Chromium."""
    from playwright.sync_api import sync_playwright

    sys.path.insert(0, str(product))
    from src.director_desk import director_server, session_url

    with director_server(output, "pose", language) as (origin, token, _), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=executable, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 790})
            page.goto(session_url(origin, token, "motion-clip-smoke", language, "pose"))
            deadline = time.monotonic() + 80

            def until(script, message):
                while time.monotonic() < deadline:
                    if result := page.evaluate(script):
                        return result
                    time.sleep(.10)
                raise RuntimeError(message)

            def desk(script):
                return f"(() => {{const desk = document.querySelector('#desk')?.contentDocument; return desk && ({script});}})()"

            def click(selector):
                target = f"desk.querySelector({json.dumps(selector)})"
                until(desk(f"Boolean({target})"), f"Missing director control {selector}")
                page.evaluate(desk(f"{target}.click()"))

            until('document.querySelector("#send") && !document.querySelector("#send").disabled',
                  "The director bridge did not initialize")
            until(desk('Boolean(desk.querySelector("canvas"))'), "The local 3D viewport did not open")
            exercise_director_motion_clip(page.evaluate, until, desk, click, output, language)
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", type=Path, help="Folder containing the unpacked Studio assets and source")
    parser.add_argument("output", type=Path, help="Destination for captured visual evidence")
    parser.add_argument("--browser", required=True, help="Path to a Chromium executable")
    parser.add_argument("--language", default="en", choices=("en", "zh"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run_chromium(args.product.resolve(), args.browser, args.output.resolve(), args.language)
