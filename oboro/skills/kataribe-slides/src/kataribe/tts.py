import os
import shlex
import subprocess
import sys
from pathlib import Path

from kataribe.adapters import voicevox


class TtsError(Exception):
    pass


def uses_custom_adapter() -> bool:
    """KATARIBE_TTS_CMD で既定以外のアダプターを使うか。空文字は既定と同じ扱い。"""
    return bool(os.environ.get("KATARIBE_TTS_CMD"))


def adapter_command() -> list[str]:
    if uses_custom_adapter():
        return shlex.split(os.environ["KATARIBE_TTS_CMD"])
    return [sys.executable, "-m", "kataribe.adapters.voicevox"]


def adapter_identity() -> str:
    """合成する音声を左右するアダプターの識別（音声のキャッシュの鍵に入れる）。独自のアダプターはコマンドの文字列。"""
    if uses_custom_adapter():
        return "command " + os.environ["KATARIBE_TTS_CMD"]
    try:
        return voicevox.engine_identity()
    except voicevox.AdapterError as e:
        raise TtsError(str(e)) from None


def synthesize(text: str, voice: str, output: Path, speed: float = 1.0, engine: str | None = None) -> None:
    """engine（用意済みのエンジンの URL）は既定の VOICEVOX のアダプターにだけ渡す。独自のアダプターの契約は変えない。"""
    command = [*adapter_command(), "--voice", voice, "--speed", str(speed), "--output", str(output)]
    env = None
    if engine is not None and not uses_custom_adapter():
        env = {**os.environ, "KATARIBE_VOICEVOX_URL": engine}  # 子のプロセスごとの Docker の確認を省く
    try:
        result = subprocess.run(command, input=text, capture_output=True, text=True, env=env)
    except OSError as e:
        raise TtsError(f"TTSアダプターを実行できません: {e}") from None
    if result.returncode != 0:
        detail = result.stderr.strip() or f"終了コード {result.returncode}"
        raise TtsError(f"TTSアダプターが失敗しました: {detail}")
    if not output.is_file():
        raise TtsError("TTSアダプターが WAV を出力しませんでした")
