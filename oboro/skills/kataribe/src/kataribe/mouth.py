"""口パク（仕様 R15）。行ごとの WAV の音量から、1/30 秒ごとの口の段階を決める。

段階は 0（閉じ）、1（半開き）、2（開き）。行の文字列（例: "0122210"）にしてタイムラインに入れ、
プレーヤーは時刻からこの文字列を引くだけにする。見た目が時刻だけで決まるので、shoot と mp4 でも同じ口になる。
閾値は yes（yuya-takeyama/agent-plugins、MIT）の値に合わせている。
"""

import math
import wave
from array import array
from pathlib import Path

from kataribe.audio import AudioError

FPS = 30
FLOOR = 300  # RMS がこれ未満のフレームは無音（約 -40 dBFS）
OPEN = (0.2, 0.5)  # 正規化した音量が、これ以上で半開き・開きになる
CLOSE = (0.12, 0.38)  # 開いた口は、これ未満になって初めて半開き・閉じに下がる
REFERENCE_PERCENTILE = 0.9  # 声のあるフレームの90パーセンタイルで正規化する（大きな1音節に引っ張られない）


def _rms_per_frame(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as f:
        if f.getsampwidth() != 2:
            raise AudioError(f"口パクを計算できません（{path.name} は 16bit の WAV である必要があります）")
        channels, rate = f.getnchannels(), f.getframerate()
        samples = array("h", f.readframes(f.getnframes()))
    if channels > 1:
        samples = samples[::channels]  # 先頭のチャンネルだけを見る
    step = rate // FPS
    rms = []
    for i in range(0, len(samples), step):
        frame = samples[i : i + step]
        rms.append(math.sqrt(sum(s * s for s in frame) / len(frame)))
    return rms


def _step(value: float, thresholds: tuple[float, float]) -> int:
    return 2 if value >= thresholds[1] else 1 if value >= thresholds[0] else 0


def _drop_blips(levels: list[int]) -> list[int]:
    """1フレームだけの段階を、前の段階（行の先頭なら次の段階）に合わせる。"""
    runs: list[list[int]] = []
    for level in levels:
        if runs and runs[-1][0] == level:
            runs[-1][1] += 1
        else:
            runs.append([level, 1])
    merged: list[list[int]] = []
    for i, (level, count) in enumerate(runs):
        if count == 1 and len(runs) > 1:
            level = merged[-1][0] if merged else runs[i + 1][0]
        if merged and merged[-1][0] == level:
            merged[-1][1] += count
        else:
            merged.append([level, count])
    return [level for level, count in merged for _ in range(count)]


def mouth_levels(path: Path) -> str:
    rms = _rms_per_frame(path)
    voiced = sorted(r for r in rms if r >= FLOOR)
    reference = voiced[int(len(voiced) * REFERENCE_PERCENTILE)] if voiced else 1.0
    levels, level = [], 0
    for r in rms:
        x = min(r / reference, 1.0) if r >= FLOOR else 0.0
        up, down = _step(x, OPEN), _step(x, CLOSE)
        level = up if up > level else down if down < level else level
        levels.append(level)
    return "".join(str(v) for v in _drop_blips(levels))
