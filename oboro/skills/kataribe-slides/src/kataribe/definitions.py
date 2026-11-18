"""立ち絵の定義（characters/*.json）の読み込み。許可リスト（voices）と立ち絵（art）の両方が使う。"""

import json
import os
from importlib import resources
from pathlib import Path


def load_definitions() -> dict[str, dict]:
    """話者の名前 → 定義。KATARIBE_CHAR_DEFS があれば、そのディレクトリの定義を使う（開発・テスト用）。"""
    configured = os.environ.get("KATARIBE_CHAR_DEFS")
    directory = Path(configured) if configured else resources.files("kataribe") / "characters"
    definitions = {}
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if path.name.endswith(".json"):
            definition = json.loads(path.read_text(encoding="utf-8"))
            definitions[definition["speaker"]] = definition
    return definitions
