"""行ごとの合成音声（WAV）のキャッシュ。鍵は、音声を変えるものすべてのハッシュ。

置き場所は KATARIBE_TTS_CACHE（off で無効）、なければ ~/.cache/kataribe/tts。
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

ENV = "KATARIBE_TTS_CACHE"
OFF = "off"
FORMAT = 2  #鍵の作り方や保存の形を変えたら上げる（古いキャッシュを使わない）


def cache_dir() -> Path | None:
    """キャッシュの置き場所。KATARIBE_TTS_CACHE が off なら None（使わない）。"""
    configured = (os.environ.get(ENV) or "").strip()
    if configured.lower() == OFF:
        return None
    return Path(configured).expanduser() if configured else Path.home() / ".cache" / "kataribe" / "tts"


def cache_key(*, text: str, voice: str, speed: float, adapter: str, words: tuple[tuple[str, int], ...]) -> str:
    """合成に渡す文・声・話速・アダプターの識別・ユーザー辞書の語から作る鍵。"""
    fields = {
        "format": FORMAT,
        "text": text,
        "voice": voice,
        "speed": speed,
        "adapter": adapter,
        "words": sorted(words),
    }
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def fetch(directory: Path, key: str, destination: Path) -> bool:
    """キャッシュにあれば destination に写して真。なければ（読めなければ）偽。"""
    try:
        shutil.copyfile(directory / f"{key}.wav", destination)
    except OSError:
        return False
    return True


def store(directory: Path, key: str, wav: Path) -> None:
    """一時ファイルに写してから置き換えるので、途中で止まっても壊れた WAV は残らない。書けなければ OSError。"""
    directory.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{key}-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(handle, "wb") as target, wav.open("rb") as source:
            shutil.copyfileobj(source, target)
        os.replace(temporary, directory / f"{key}.wav")
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
