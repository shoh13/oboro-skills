"""build 時に、行ごとの WAV の音量から口の段階（0 閉じ、1 半開き、2 開き）を 1/30 秒ごとに決める（仕様 R15）。"""
import math
import struct
import wave

from kataribe.mouth import mouth_levels

RATE = 24000
STEP = RATE // 30  # 1フレーム（1/30 秒）の標本数


def frames_of(*amplitudes: float) -> list[int]:
    """1フレームずつ、指定した振幅の 440Hz の正弦波（0 は無音）。"""
    samples = []
    for amplitude in amplitudes:
        start = len(samples)
        samples += [round(amplitude * math.sin(2 * math.pi * 440 * (start + i) / RATE)) for i in range(STEP)]
    return samples


def write_wav(path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def levels(tmp_path, samples: list[int]) -> str:
    path = tmp_path / "line.wav"
    write_wav(path, samples)
    return mouth_levels(path)


def test_無音なら口は閉じたまま(tmp_path):
    assert levels(tmp_path, frames_of(0, 0, 0, 0)) == "0000"


def test_声のあいだは開き_音量は行の中で正規化されるので小さな声でも開く(tmp_path):
    assert levels(tmp_path, frames_of(8000, 8000, 8000)) == "222"
    assert levels(tmp_path, frames_of(1000, 1000, 1000)) == "222"


def test_RMSが300未満のフレームは無音として閉じる(tmp_path):
    # 振幅 400 の正弦波の RMS は約 283
    assert levels(tmp_path, frames_of(8000, 8000, 400, 400, 8000, 8000)) == "220022"


def test_開く基準は0_2と0_5で_その間は半開き(tmp_path):
    # 基準（声のあるフレームの90パーセンタイル）は 10000。0.3 は半開き
    assert levels(tmp_path, frames_of(3000, 3000, 3000, 10000, 10000, 10000, 10000, 10000, 10000, 10000)) == "1112222222"


def test_閉じる基準は0_12と0_38で_開いた口は少し小さくなっても開いたまま(tmp_path):
    # 0.45 は開く基準（0.5）より小さいが、閉じる基準（0.38）以上なので開いたまま。0.3 で半開きに下がる
    amplitudes = [10000] * 8 + [4500, 4500, 3000, 3000]
    assert levels(tmp_path, frames_of(*amplitudes)) == "222222222211"


def test_1フレームだけの開閉は_前の状態に合わせて除く(tmp_path):
    assert levels(tmp_path, frames_of(10000, 10000, 10000, 0, 10000, 10000, 10000)) == "2222222"
    # 行の先頭の1フレームは、次の状態に合わせる
    assert levels(tmp_path, frames_of(0, 10000, 10000, 10000)) == "2222"


def test_最後の半端なフレームも1フレームとして数える(tmp_path):
    samples = frames_of(10000, 10000)[: STEP + STEP // 2]

    assert len(levels(tmp_path, samples)) == 2
