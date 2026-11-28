# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
import sys

root = Path(SPECPATH).parent
media = Path(os.environ["STUDIO_FFMPEG"]).resolve()
payload = Path(os.environ["STUDIO_INSTALLER_PAYLOAD"]).resolve()
macos = sys.platform == "darwin"
app_name = "Comic-Sequence-Studio"
datas = [(str(payload / directory), directory) for directory in ("assets", "Examples")]
datas += [(str(payload / name), ".") for name in
          ("CHANGELOG.md", "LICENSE", "VERSION.txt", "REVISION.txt", "INSTALLER-BUILD.txt")]
datas += [(str(media.parent / "ffmpeg-source"), "Notices/FFmpeg")]
# Package redistribution notices provided by the installed wheels.
from PyInstaller.utils.hooks import copy_metadata
for dependency in ("Pillow", "numpy", "pywebview", "bottle", "proxy_tools"):
    datas += copy_metadata(dependency)
if macos:
    for dependency in ("pyobjc-core", "pyobjc-framework-Cocoa", "pyobjc-framework-WebKit",
                       "pyobjc-framework-Quartz", "pyobjc-framework-Security", "pyobjc-framework-UniformTypeIdentifiers"):
        datas += copy_metadata(dependency)
else:
    for dependency in ("pythonnet", "clr_loader", "cffi"):
        datas += copy_metadata(dependency)

a = Analysis(
    [str(root / "packaging" / "desktop_entry.py")], pathex=[str(root)],
    binaries=[(str(media), "tools")], datas=datas,
    hiddenimports=["webview.platforms.cocoa" if macos else "webview.platforms.edgechromium"],
    excludes=["imageio_ffmpeg"], noarchive=False,
)
pyz = PYZ(a.pure)
app = EXE(pyz, a.scripts, [], exclude_binaries=True, name=app_name, console=False, upx=False)
executables = [app]
if not macos:
    executables.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name=app_name + "-Worker",
                           console=True, upx=False))

distribution = COLLECT(*executables, a.binaries, a.datas, name=app_name, upx=False)
if macos:
    bundle = BUNDLE(
        distribution, name=app_name + ".app", bundle_identifier="com.comicsequencestudio.desktop",
        version=(payload / "VERSION.txt").read_text().strip(),
        info_plist={
            "CFBundleDisplayName": "Comic Sequence Studio",
            "NSHighResolutionCapable": True,
            "NSAppTransportSecurity": {"NSExceptionDomains": {
                "127.0.0.1": {"NSExceptionAllowsInsecureHTTPLoads": True},
            }},
        },
    )
