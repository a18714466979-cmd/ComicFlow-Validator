import json
import sys

import pytest

from src import windows_launcher
from src.production_export import build_delivery
from src.production_handoff import adjacent
from src.production_project import ProductionProject
from src.production_rules import CHINESE, ENGLISH


@pytest.mark.parametrize("dropped", ["", r"C:\我的交付\SB05 测试.zip"])
def test_launcher_passes_drop_to_workbench_and_returns_validator_exit_code(monkeypatch, dropped):
    monkeypatch.setattr(sys, "argv", ["windows_launcher", dropped] if dropped else ["windows_launcher"])
    def open_workbench(initial_zip):
        assert initial_zip == dropped
        return 3

    monkeypatch.setattr(windows_launcher, "open_workbench", open_workbench)
    assert windows_launcher.main() == 3


def test_each_mode_keeps_its_own_validator_and_respects_legacy_preferences(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("COMICFLOW_STORYBOARD_VALIDATOR", raising=False)
    monkeypatch.delenv("COMICFLOW_CHINESE_STORYBOARD_VALIDATOR", raising=False)
    english, chinese, override = (tmp_path / name for name in ("英文.py", "中文.py", "override.py"))
    for script in (english, chinese, override):
        script.touch()
    legacy = tmp_path / "ComicFlow" / "settings.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"validator": str(english)}), encoding="utf-8")

    assert windows_launcher.saved_validator() == str(english)
    assert not windows_launcher.saved_validator(CHINESE)
    windows_launcher.remember_validator(str(chinese), CHINESE)
    assert windows_launcher.saved_validator(CHINESE) == str(chinese)
    assert windows_launcher.saved_validator(ENGLISH) == str(english)

    monkeypatch.setenv("COMICFLOW_CHINESE_STORYBOARD_VALIDATOR", str(override))
    windows_launcher.remember_validator(str(english), CHINESE)
    assert windows_launcher.saved_validator(CHINESE) == str(override)
    monkeypatch.delenv("COMICFLOW_CHINESE_STORYBOARD_VALIDATOR")
    assert windows_launcher.saved_validator(CHINESE) == str(chinese)


def test_project_mode_round_trips_and_mixed_rules_cannot_share_a_delivery(tmp_path):
    english = ProductionProject("示例", "EP01", "SB01")
    chinese = ProductionProject("示例", "EP01", "SB02", rules=CHINESE)
    assert english.rules == ENGLISH
    for project in (english, chinese):
        path = tmp_path / f"{project.group}.cfproject"
        project.save(path)
        reopened = ProductionProject.open(path)
        assert reopened.rules == project.rules
        assert reopened.fingerprint() == project.fingerprint()
    with pytest.raises(ValueError, match="同一套制作规则"):
        adjacent(english, chinese)

    delivery = tmp_path / "delivery"
    with pytest.raises(ValueError, match="中文项目的交付模板"):
        build_delivery(chinese, path, delivery, tmp_path / "validator.py", tmp_path / "registry.sqlite3")
    assert not delivery.exists()
