import json
import re

import pytest
from conftest import SECONDS_PER_CHAR, run_build


def read_timeline(project) -> dict:
    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="kataribe-timeline">(.*?)</script>', html, re.S)
    assert match, "タイムラインが単一HTMLに埋め込まれていません"
    return json.loads(match.group(1))


def test_各行の開始と終了は_音声の実測長を積み上げた時刻になる(project):
    assert run_build(project).returncode == 0

    timeline = read_timeline(project)

    expected = {"こんにちは": 5, "はじめましょう": 7, "二つ目のシーンです": 9, "おしまい": 4}
    start = 0.0
    for line in timeline["lines"]:
        length = expected[line["text"]] * SECONDS_PER_CHAR
        assert line["start"] == pytest.approx(start, abs=1e-3)
        assert line["end"] == pytest.approx(start + length, abs=1e-3)
        start += length
    assert timeline["duration"] == pytest.approx(start, abs=1e-3)


def test_シーンと章の境界は_行の時刻から導かれる(project):
    assert run_build(project).returncode == 0

    timeline = read_timeline(project)

    scenes = {s["id"]: s for s in timeline["scenes"]}
    assert scenes["s1"]["start"] == pytest.approx(0.0, abs=1e-3)
    assert scenes["s1"]["end"] == pytest.approx(0.24, abs=1e-3)
    assert scenes["s2"]["start"] == pytest.approx(0.24, abs=1e-3)
    assert scenes["s2"]["end"] == pytest.approx(0.42, abs=1e-3)
    assert scenes["s3"]["end"] == pytest.approx(0.50, abs=1e-3)

    chapters = {c["id"]: c for c in timeline["chapters"]}
    assert chapters["c1"]["title"] == "最初の章"
    assert chapters["c1"]["start"] == pytest.approx(0.0, abs=1e-3)
    assert chapters["c1"]["end"] == pytest.approx(0.42, abs=1e-3)
    assert chapters["c2"]["start"] == pytest.approx(0.42, abs=1e-3)
    assert chapters["c2"]["end"] == pytest.approx(0.50, abs=1e-3)


def test_つないだ音声の長さは_タイムラインの全体の長さと一致する(project):
    import wave

    assert run_build(project, args=["--extras"]).returncode == 0

    # 単一HTMLの音声は AAC で、末尾が 1024 標本の単位でわずかに伸びる。つないだ音声そのもの（副産物の WAV）で比べる
    with wave.open(str(project / "out" / "extras" / "audio.wav"), "rb") as audio:
        seconds = audio.getnframes() / audio.getframerate()

    assert seconds == pytest.approx(read_timeline(project)["duration"], abs=1e-3)
    assert seconds == pytest.approx(0.50, abs=1e-3)
