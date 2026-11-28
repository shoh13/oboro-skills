"""oboro の設定ファイル（setup-oboro が書く。OBORO_CONFIG があればそのパス）の [kataribe] を読む。"""

import os
import tomllib
from pathlib import Path


class ConfigError(Exception):
    pass


def config_path() -> Path:
    return Path(os.environ.get("OBORO_CONFIG") or Path.home() / ".config" / "oboro" / "config.toml").expanduser()


def kataribe_path(key: str) -> Path | None:
    """[kataribe] の key のパス（~ はホームに展開する）。設定ファイルかキーがなければ None。"""
    config = config_path()
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"oboro の設定ファイルを読めません: {config}（{e}）") from None
    section = data.get("kataribe", {})
    if not isinstance(section, dict):
        raise ConfigError(f"oboro の設定ファイルの kataribe は、表（[kataribe]）にしてください: {config}")
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"oboro の設定ファイルの kataribe.{key} は、空でないパスの文字列にしてください: {config}")
    return Path(value).expanduser()
