import io
import wave
from pathlib import Path


class AudioError(Exception):
    pass


def concat_wavs(wavs: list[Path]) -> bytes:
    params = None
    frames = []
    for wav in wavs:
        with wave.open(str(wav), "rb") as f:
            current = (f.getnchannels(), f.getsampwidth(), f.getframerate())
            if params is None:
                params = current
            elif current != params:
                raise AudioError(f"音声の形式が行ごとに異なります: {wav.name}")
            frames.append(f.readframes(f.getnframes()))
    if params is None:
        raise AudioError("音声にする行がありません")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(params[0])
        out.setsampwidth(params[1])
        out.setframerate(params[2])
        out.writeframes(b"".join(frames))
    return buffer.getvalue()


AAC_BITRATE = "48k"


def encode_aac(wav: bytes) -> bytes:
    """単一HTMLに埋め込む音声。WAV を AAC（48 kbps）の m4a にする（仕様 R5。16 MiB の上限に長い動画を収める）。

    ffmpeg は imageio-ffmpeg のもの（KATARIBE_FFMPEG で差し替え可）を使う。
    """
    import subprocess
    import tempfile

    # mp4 は撮影のためにブラウザ周りを読み込むので、使うときだけ読む（循環 import を避ける）
    from kataribe.browser import BrowserError
    from kataribe.mp4 import ffmpeg_exe

    try:
        ffmpeg = ffmpeg_exe()
    except BrowserError as e:
        raise AudioError(f"音声を AAC に変換できません: {e}") from None
    with tempfile.TemporaryDirectory() as work:
        source, target = Path(work) / "audio.wav", Path(work) / "audio.m4a"
        source.write_bytes(wav)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-c:a", "aac", "-b:a", AAC_BITRATE, "-movflags", "+faststart", str(target)]
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except OSError as e:
            raise AudioError(f"音声を AAC に変換できません: {e}") from None
        if result.returncode != 0 or not target.exists():
            raise AudioError(f"音声を AAC に変換できません: {result.stderr.strip()}")
        return target.read_bytes()
