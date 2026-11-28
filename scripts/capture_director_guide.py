"""Capture the bundled 3D Director Desk in Chromium for the offline storyboard guide.

Run from the repository root after building the Director Desk:
    python -m scripts.capture_director_guide --browser /path/to/chromium

Requires Playwright, Pillow and a Chromium build with WebGL. The built-in
mannequin is used in a fresh browser session, with no user project or API.
"""

import argparse
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from playwright.sync_api import expect, sync_playwright

from src.director_desk import ROOT, director_server, session_url


OUTPUT = ROOT / "assets" / "storyboard_guide"
LOCALES = {
    "zh": ("取当前画面作为参考", "动作片段", "示例场景"),
    "en": ("Use current frame as reference", "Action clip", "Sample scene"),
}


def capture(browser, language, output):
    send_caption, clip_caption, scene_name = LOCALES[language]
    with TemporaryDirectory(prefix="director-guide-") as scratch:
        handoff = Path(scratch)
        with director_server(handoff, "pose", language) as (origin, token, finished):
            page = browser.new_page(viewport={"width": 1280, "height": 880}, device_scale_factor=1)
            try:
                page.goto(session_url(origin, token, scene_name, language, "pose"))
                send = page.get_by_role("button", name=send_caption, exact=True)
                expect(send).to_be_enabled(timeout=30000)

                desk = page.frame_locator("#desk")
                expect(desk.locator("canvas").first).to_be_visible()
                desk.get_by_role("button", name=clip_caption, exact=True).click()
                expect(desk.get_by_test_id("motion-clip-panel")).to_be_visible()
                add_key = desk.get_by_test_id("motion-clip-add")
                add_key.click()

                time = desk.get_by_test_id("motion-clip-time")
                time.fill("2.5")
                time.press("Tab")
                desk.get_by_test_id("motion-clip-pose-preset").select_option("t-pose")
                add_key.click()
                expect(desk.locator(".motion-clip-lane button")).to_have_count(2)
                expect(time).to_have_value("2.5")
                page.mouse.move(2, 2)
                screenshot = page.screenshot()
                send.click()
                if not finished.wait(timeout=35):
                    raise RuntimeError(page.get_by_role("status").inner_text())
                with Image.open(handoff / "frame.png") as frame:
                    frame.verify()
                with Image.open(BytesIO(screenshot)) as image:
                    image.convert("RGB").save(output / f"director_{language}.webp", quality=84, method=6)
            finally:
                page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", help="Chromium executable path. Defaults to Playwright's Chromium.")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Directory for the two WebP screenshots.")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.browser,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        try:
            for language in LOCALES:
                capture(browser, language, args.output)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
