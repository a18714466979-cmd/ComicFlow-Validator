"""Build the pinned local 3D Director Desk editor for ComicFlow."""

import argparse
import json
from pathlib import Path
from shutil import copy2, copytree, rmtree, which
from subprocess import run
from tarfile import open as open_tar
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/xiaozangao/3d-director-desk.git"
REVISION = "a6c931cd36d8263d986706f74ab4efe9d5151959"
VENDOR = ROOT / "vendor" / "director-desk"
DESTINATION = ROOT / "assets" / "director_desk"
SOURCE_PATHS = (
    "LICENSE", "index.html", "package.json", "package-lock.json", "src", "tsconfig.json",
    "tsconfig.node.json", "vite.config.ts", "public/benchmark-panorama.jpg",
)


def write_dependency_notices(source, destination):
    locked = json.loads((source / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    notices = ["License notices for dependencies of the 3D Director Desk distribution.\n"]
    for path, package in sorted(locked.items()):
        if not path or package.get("dev"):
            continue
        directory = source / path
        metadata = directory / "package.json"
        if not metadata.is_file():
            continue
        info = json.loads(metadata.read_text(encoding="utf-8"))
        notices.append(f"\n{info['name']} {info['version']} ({info.get('license', 'see package notices')})\n")
        for file in sorted(directory.iterdir()):
            heading = file.name.lower().split(".", 1)[0]
            if file.is_file() and heading in {"license", "licence", "notice", "copying", "authors"}:
                notices.append(file.read_text(encoding="utf-8", errors="replace").strip() + "\n")
    destination.write_text("\n".join(notices), encoding="utf-8")


def build(destination, checkout=None):
    npm = which("npm")
    if npm is None:
        raise RuntimeError("Node.js and npm are needed to build 3D Director Desk.")
    with TemporaryDirectory(prefix="comicflow-director-build-") as folder:
        scratch = Path(folder)
        if checkout is None:
            checkout = scratch / "checkout"
            run(["git", "init", "-q", str(checkout)], check=True)
            run(["git", "fetch", "-q", "--depth=1", UPSTREAM, REVISION], check=True, cwd=checkout)
        archive_path = scratch / "source.tar"
        run(["git", "-c", "core.autocrlf=false", "archive", "--format=tar", "-o", str(archive_path), REVISION, *SOURCE_PATHS],
            check=True, cwd=checkout)
        source = scratch / "source"
        source.mkdir()
        with open_tar(archive_path) as archive:
            archive.extractall(source, filter="data")
        # The archive preserves upstream LF bytes; normalize a Windows CRLF checkout of our patch.
        patch = (VENDOR / "comicflow.patch").read_bytes().replace(b"\r\n", b"\n")
        run(["git", "-c", "core.autocrlf=false", "apply", "-"], input=patch, check=True, cwd=source)
        run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], check=True, cwd=source)
        run([npm, "run", "build"], check=True, cwd=source)
        dist = source / "dist"
        copy2(source / "LICENSE", dist / "LICENSE")
        write_dependency_notices(source, dist / "THIRD-PARTY-LICENSES.txt")
        (dist / "SOURCE.txt").write_text(f"{UPSTREAM}\nGit revision: {REVISION}\nMIT License\n", encoding="utf-8")
        if destination.exists():
            rmtree(destination)
        copytree(dist, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Git checkout containing the pinned upstream revision")
    args = parser.parse_args()
    build(DESTINATION, args.source)


if __name__ == "__main__":
    main()
