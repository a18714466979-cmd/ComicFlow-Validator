"""Build a drag-to-Applications disk image and verify the installed macOS app."""

import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from src.brand import APP_NAME_EN, VERSION


APP_BUNDLE = f"{APP_NAME_EN}.app"
APPLICATIONS = Path("/Applications")
ARCHITECTURES = ("arm64", "x86_64")


def check_bundle(bundle: Path, arch: str) -> None:
    with (bundle / "Contents" / "Info.plist").open("rb") as file:
        info = plistlib.load(file)
    executable = info["CFBundleExecutable"]
    if info.get("CFBundlePackageType") != "APPL" or Path(executable).name != executable:
        raise ValueError("The disk image must contain a valid macOS application bundle.")
    if info.get("CFBundleShortVersionString") != VERSION:
        raise ValueError(f"The application bundle does not declare version {VERSION}.")
    binary = bundle / "Contents" / "MacOS" / executable
    binary_archs = subprocess.check_output(["/usr/bin/lipo", "-archs", binary], text=True).split()
    if binary_archs != [arch]:
        raise ValueError(f"Expected a native {arch} application, got {' '.join(binary_archs)}.")
    subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", bundle], check=True)


def launch_installed(bundle: Path, workspace: Path, arch: str, revision: str) -> None:
    marker = workspace / "installer-smoke.json"
    stdout = workspace / "installer.stdout"
    stderr = workspace / "installer.stderr"
    profile = workspace / "profile"
    profile.mkdir()
    stdout.touch()
    stderr.touch()
    try:
        subprocess.run(
            ["/usr/bin/open", "-n", "-W", "-a", bundle, "--env", f"LOCALAPPDATA={profile}",
             "--stdout", stdout, "--stderr", stderr, "--args", "--installer-smoke", marker],
            cwd=workspace, check=True, timeout=180,
        )
        result = json.loads(marker.read_text(encoding="utf-8"))
        expected = {"status": "ok", "platform": "darwin", "architecture": arch, "revision": revision}
        if any(result.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Installed app failed smoke verification: {result}")
        print(f"Verified LaunchServices start on macOS {arch}: {json.dumps(result, ensure_ascii=False)}", flush=True)
    finally:
        for path in (stdout, stderr):
            if data := path.read_text(encoding="utf-8", errors="replace"):
                print(data, end="", flush=True)


def verify_image(image: Path, workspace: Path, arch: str, revision: str) -> None:
    subprocess.run(["/usr/bin/hdiutil", "verify", image], check=True, timeout=90)
    mount = workspace / "Mounted image"
    mount.mkdir()
    subprocess.run(
        ["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, image],
        check=True, timeout=90,
    )
    try:
        link = mount / "Applications"
        if not link.is_symlink() or Path(os.readlink(link)) != APPLICATIONS:
            raise ValueError("The disk image is missing its Applications shortcut.")
        installed = workspace / "Clean Applications" / APP_BUNDLE
        installed.parent.mkdir()
        subprocess.run(["/usr/bin/ditto", mount / APP_BUNDLE, installed], check=True, timeout=90)
    finally:
        subprocess.run(["/usr/bin/hdiutil", "detach", mount], check=True, timeout=90)
    check_bundle(installed, arch)
    launch_installed(installed, workspace, arch, revision)


def build(bundle: Path, output: Path, arch: str, revision: str) -> None:
    if sys.platform != "darwin" or platform.machine() != arch:
        raise ValueError(f"Build and verify this installer on a native macOS {arch} runner.")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Pass the complete source revision used to build the application.")
    if output.suffix.lower() != ".dmg":
        raise ValueError("The output filename must end in .dmg.")
    if output.exists():
        raise FileExistsError(output)
    check_bundle(bundle, arch)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="studio-macos-", dir=output.parent) as directory:
        workspace = Path(directory)
        source = workspace / "Disk image contents"
        source.mkdir()
        subprocess.run(["/usr/bin/ditto", bundle, source / APP_BUNDLE], check=True, timeout=90)
        (source / "Applications").symlink_to(APPLICATIONS, target_is_directory=True)
        image = workspace / "verified.dmg"
        subprocess.run(
            ["/usr/bin/hdiutil", "create", "-format", "UDZO", "-fs", "HFS+", "-volname", APP_NAME_EN,
             "-srcfolder", source, image], check=True, timeout=150,
        )
        verify_image(image, workspace, arch, revision)
        image.replace(output)
    print(f"Created {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--arch", choices=ARCHITECTURES, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    build(args.bundle.resolve(), args.output.resolve(), args.arch, args.revision)
