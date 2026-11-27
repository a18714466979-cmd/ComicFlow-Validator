import sys

import pytest

from src import windows_launcher


@pytest.mark.parametrize("dropped", ["", r"C:\我的交付\SB05 测试.zip"])
def test_launcher_passes_drop_to_picker_and_returns_validator_exit_code(monkeypatch, dropped):
    monkeypatch.setattr(sys, "argv", ["windows_launcher", dropped] if dropped else ["windows_launcher"])
    args = [r"C:\我的交付\SB05 测试.zip", "--storyboard-validator", r"C:\工作流\validate_storyboard_package.py"]

    def pick(initial_zip):
        assert initial_zip == dropped
        return args

    def validate(options):
        assert options == args
        return 3

    monkeypatch.setattr(windows_launcher, "select_options", pick)
    monkeypatch.setattr(windows_launcher, "validate", validate)
    assert windows_launcher.main() == 3
