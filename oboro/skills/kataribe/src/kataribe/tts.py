import os
import shlex
import subprocess
import sys
from pathlib import Path


class TtsError(Exception):
    pass


def uses_custom_adapter() -> bool:
    """KATARIBE_TTS_CMD で既定以外のアダプターを使うか。空文字は既定と同じ扱い。"""
    return bool(os.environ.get("KATARIBE_TTS_CMD"))


def adapter_command() -> list[str]:
    if uses_custom_adapter():
        return shlex.split(os.environ["KATARIBE_TTS_CMD"])
    return [sys.executable, "-m", "kataribe.adapters.voicevox"]


def synthesize(text: str, voice: str, output: Path, speed: float = 1.0) -> None:
    command = [*adapter_command(), "--voice", voice, "--speed", str(speed), "--output", str(output)]
    try:
        result = subprocess.run(command, input=text, capture_output=True, text=True)
    except OSError as e:
        raise TtsError(f"TTSアダプターを実行できません: {e}") from None
    if result.returncode != 0:
        detail = result.stderr.strip() or f"終了コード {result.returncode}"
        raise TtsError(f"TTSアダプターが失敗しました: {detail}")
    if not output.is_file():
        raise TtsError("TTSアダプターが WAV を出力しませんでした")
