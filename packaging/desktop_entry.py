"""Entry point for the self-contained Studio app and console worker."""

from pathlib import Path
import runpy
import sys


def worker(argv):
    sys.argv = argv
    if len(argv) >= 2 and argv[0] == "-m":
        if argv[1] == "src.delivery_checker":
            from src.delivery_checker import main

            sys.argv = argv[1:]
            return main()
        if argv[1] == "src.director_desk":
            from src.director_desk import run_window

            folder, instance, language, mode = argv[2:]
            try:
                run_window(Path(folder), instance, language, mode)
            except Exception as error:
                Path(folder, "error.txt").write_text(str(error), encoding="utf-8")
                return 1
            return 0
        raise SystemExit("Unsupported Studio worker module.")

    path = Path(argv[0]).resolve()
    if path.suffix.lower() != ".py" or not path.is_file():
        raise SystemExit("The selected Python validation script is missing.")
    sys.argv[0] = str(path)
    sys.path.insert(0, str(path.parent))
    runpy.run_path(str(path), run_name="__main__")
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--studio-worker":
        return worker(sys.argv[2:])
    if len(sys.argv) == 3 and sys.argv[1] == "--installer-smoke":
        from packaging_smoke import exercise

        return exercise(Path(sys.argv[2]))
    from src.windows_launcher import main as launch

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
