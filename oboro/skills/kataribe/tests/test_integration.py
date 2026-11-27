"""実際の VOICEVOX（Docker）を使うテスト。Docker が使えるときだけ実行する。"""

import json
import os
import re
import subprocess
import sys
import wave

import pytest
from conftest import SCRIPT, make_project

pytestmark = pytest.mark.integration


def docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


if not docker_available():
    pytest.skip("Docker が使えないため、VOICEVOX の統合テストを飛ばします", allow_module_level=True)


def read_timeline(html: str) -> dict:
    match = re.search(r'id="kataribe-timeline">(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def real_env() -> dict:
    env = dict(os.environ)
    env.pop("KATARIBE_TTS_CMD", None)
    env.pop("KATARIBE_VOICEVOX_URL", None)
    return env


def test_実機のVOICEVOXで声を合成でき_音声の長さが実測できる(tmp_path):
    output = tmp_path / "line.wav"

    result = subprocess.run(
        [sys.executable, "-m", "kataribe.adapters.voicevox", "--voice", "ずんだもん", "--speed", "1.0", "--output", str(output)],
        input="こんにちは、はじめまして。",
        capture_output=True,
        text=True,
        env=real_env(),
    )

    assert result.returncode == 0, result.stderr
    with wave.open(str(output), "rb") as wav:
        assert wav.getnframes() / wav.getframerate() > 0.5


def test_既定のアダプターでビルドすると_実測長のタイムラインとつないだ音声の長さが一致する(tmp_path):
    script = {
        **SCRIPT,
        "chapters": [
            {"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "こんにちは。"}, {"speaker": "ずんだもん", "text": "動画を作ってみましょう。"}]}]}
        ],
    }
    project = make_project(tmp_path / "real", script=script, scenes='<section data-scene="s1"><h1>実機</h1></section>')

    result = subprocess.run(
        [sys.executable, "-m", "kataribe", "build", str(project), "--extras"], capture_output=True, text=True, env=real_env()
    )

    assert result.returncode == 0, result.stderr
    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    timeline = read_timeline(html)
    # 単一HTMLの音声は AAC で末尾がわずかに伸びるので、つないだ音声そのもの（副産物の WAV）で比べる
    with wave.open(str(project / "out" / "extras" / "audio.wav"), "rb") as wav:
        seconds = wav.getnframes() / wav.getframerate()
    assert seconds == pytest.approx(timeline["duration"], abs=1e-3)
    assert all(line["end"] - line["start"] > 0.3 for line in timeline["lines"])


def test_実機の音声を最後まで再生すると_シーンと字幕と章が音声の進行に同期して切り替わる(browser, tmp_path):
    script = {
        **SCRIPT,
        "chapters": [
            {"id": "c1", "title": "最初の章", "scenes": [{"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "最初のシーンです。"}]}]},
            {"id": "c2", "title": "次の章", "scenes": [{"id": "s2", "lines": [{"speaker": "ずんだもん", "text": "二つ目のシーンです。"}]}]},
        ],
    }
    scenes = '<section data-scene="s1"><h1>一</h1></section><section data-scene="s2"><h1>二</h1></section>'
    project = make_project(tmp_path / "play", script=script, scenes=scenes)
    built = subprocess.run([sys.executable, "-m", "kataribe", "build", str(project)], capture_output=True, text=True, env=real_env())
    assert built.returncode == 0, built.stderr
    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    timeline = read_timeline(html)
    boundary = timeline["lines"][1]["start"]

    page = browser.new_page()
    page.goto((project / "out" / "video.html").as_uri())
    page.click("#kataribe-play")
    page.wait_for_function(f"document.getElementById('kataribe-audio').currentTime > {boundary / 2}")
    assert page.inner_text("#kataribe-caption") == "最初のシーンです。"
    assert page.inner_text("#kataribe-chapter") == "最初の章"
    page.wait_for_function("document.getElementById('kataribe-audio').ended")
    assert page.inner_text("#kataribe-caption") == "二つ目のシーンです。"
    assert page.inner_text("#kataribe-chapter") == "次の章"
    page.close()


def test_実機の音声でビルドした動画を_実時間で再生して検証でき_行単位の出現も合格する(tmp_path):
    script = {
        **SCRIPT,
        "chapters": [
            {
                "id": "c1",
                "title": "最初の章",
                "scenes": [{"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "最初の説明をします。"}, {"speaker": "ずんだもん", "text": "次に図を足します。"}, {"speaker": "ずんだもん", "text": "最後にまとめます。"}]}],
            },
            {"id": "c2", "title": "次の章", "scenes": [{"id": "s2", "lines": [{"speaker": "ずんだもん", "text": "二つ目のシーンです。"}]}]},
        ],
    }
    scenes = (
        '<section data-scene="s1"><p data-out="1">前</p><p data-at="1">後</p><p data-at="2" data-focus="2">まとめ</p></section>'
        '<section data-scene="s2"><h1>二</h1></section>'
    )
    project = make_project(tmp_path / "verify", script=script, scenes=scenes)
    built = subprocess.run([sys.executable, "-m", "kataribe", "build", str(project)], capture_output=True, text=True, env=real_env())
    assert built.returncode == 0, built.stderr

    result = subprocess.run([sys.executable, "-m", "kataribe", "verify", str(project)], capture_output=True, text=True, env=real_env())

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count(": OK") == 7
    assert result.stderr == ""


def test_実機のVOICEVOXに読みを問い合わせると_合成に渡す文の読みがカタカナで返る(tmp_path):
    project = make_project(
        tmp_path / "readings",
        script={**SCRIPT, "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "こんにちは、はじめまして。"}]}]}]},
        scenes='<section data-scene="s1"><h1>実機</h1></section>',
    )

    result = subprocess.run([sys.executable, "-m", "kataribe", "readings", str(project)], capture_output=True, text=True, env=real_env())

    assert result.returncode == 0, result.stderr
    reading = re.search(r"エンジンの読み: (.+)", result.stdout)
    assert reading is not None, result.stdout
    assert re.fullmatch(r"[ァ-ヶー、 ]+", reading.group(1).strip()), reading.group(1)
    assert result.stderr == ""


def test_音声クエリから計算した長さは_実機の合成の実測長とほぼ一致し_速度の警告の判定も一致する(tmp_path):
    from compare_speed import compare, read_timeline

    from kataribe.adapters import voicevox
    from kataribe.project import load_project
    from kataribe.readcheck import reading_rows

    lines = [
        {"speaker": "ずんだもん", "text": "こんにちは、はじめまして。"},
        {"speaker": "四国めたん", "text": "読点が、いくつか、入る文は、間の分だけ長くなるわ。"},
        {"speaker": "ずんだもん", "text": "ゆっくり話すのだ？"},
        {"speaker": "四国めたん", "text": "CassandraとMongoDBとRedis", "reading": "カサンドラとモンゴディービーとレディス"},
    ]
    project = make_project(
        tmp_path / "p",
        script={**SCRIPT, "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": lines}]}]},
        scenes='<section data-scene="s1"></section>',
    )
    env = real_env()
    result = subprocess.run([sys.executable, "-m", "kataribe", "build", str(project)], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr

    base = voicevox.engine_url()
    comparison = compare(reading_rows(load_project(project), lambda items: voicevox.read_aloud(base, items)), read_timeline(project / "out"))

    assert comparison.largest_error < 0.001
    assert comparison.agrees, comparison
