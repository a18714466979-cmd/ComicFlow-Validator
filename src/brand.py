"""Product naming and the desktop release identifier."""

APP_NAME_ZH = "漫剧镜序制片台"
APP_NAME_EN = "Comic Sequence Studio"
APP_FOLDER = "Comic-Sequence-Studio"
VERSION = "2.0.0"


def app_name(language: str) -> str:
    return APP_NAME_EN if language == "en" else APP_NAME_ZH
