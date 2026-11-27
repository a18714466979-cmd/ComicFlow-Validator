import sys

import pytest

from src import windows_launcher


@pytest.mark.parametrize("dropped", ["", r"C:\我的交付\SB05 测试.zip"])
def test_launcher_passes_drop_to_workbench_and_returns_validator_exit_code(monkeypatch, dropped):
    monkeypatch.setattr(sys, "argv", ["windows_launcher", dropped] if dropped else ["windows_launcher"])
    def open_workbench(initial_zip):
        assert initial_zip == dropped
        return 3

    monkeypatch.setattr(windows_launcher, "open_workbench", open_workbench)
    assert windows_launcher.main() == 3
