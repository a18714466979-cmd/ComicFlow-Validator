"""Stage exactly the verified Studio trial assets in a new installer build folder."""

import hashlib
import sys
from pathlib import Path
from zipfile import ZipFile


def main():
    archive_path, destination, build_revision = sys.argv[1:]
    destination = Path(destination)
    with open(archive_path, "rb") as archive:
        expected = "00f4a956feef4796d3c2f9371e973a1bef2cf7a1ca72dccbcce422578ed24a70"
        if hashlib.file_digest(archive, "sha256").hexdigest() != expected:
            raise ValueError("The trial payload does not match the approved v2.9.1 release.")
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("The verified trial ZIP did not pass CRC on this runner.")
        archive.extractall(destination)
    kit = destination / "Comic-Sequence-Studio"
    assert (kit / "VERSION.txt").read_text(encoding="utf-8").strip() == "2.9.1"
    assert (kit / "REVISION.txt").read_text(encoding="utf-8").strip() == "6d6c7e0fb5163d6274472142a35bf5664a25a475"
    (kit / "INSTALLER-BUILD.txt").write_text(build_revision + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
