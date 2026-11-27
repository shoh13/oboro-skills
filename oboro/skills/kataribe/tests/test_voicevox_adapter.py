import json
import os
import subprocess
import sys
import wave

import pytest


def run_adapter(url: str, text: str, voice: str, output, speed: str = "1.0") -> subprocess.CompletedProcess:
    env = {**os.environ, "KATARIBE_VOICEVOX_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "kataribe.adapters.voicevox", "--voice", voice, "--speed", speed, "--output", str(output)],
        input=text,
        capture_output=True,
        text=True,
        env=env,
    )


def test_声の名前をノーマルのスタイルに対応づけ_テキストと速度を指定して音声を書き出す(engine, tmp_path):
    url, requests = engine
    output = tmp_path / "line.wav"

    result = run_adapter(url, "こんにちは", "ずんだもん", output, speed="1.2")

    assert result.returncode == 0, result.stderr
    with wave.open(str(output), "rb") as wav:
        assert wav.getnframes() / wav.getframerate() == pytest.approx(0.3, abs=1e-3)
    query_request, synthesis_request = requests
    assert query_request["path"] == "/audio_query"
    assert query_request["query"] == {"speaker": ["3"], "text": ["こんにちは"]}
    assert synthesis_request["path"] == "/synthesis"
    assert synthesis_request["query"] == {"speaker": ["3"]}
    assert json.loads(synthesis_request["body"])["speedScale"] == 1.2


def test_四国めたんの声はそのノーマルのスタイルで合成される(engine, tmp_path):
    url, requests = engine

    result = run_adapter(url, "こんばんは", "四国めたん", tmp_path / "line.wav")

    assert result.returncode == 0, result.stderr
    assert requests[0]["query"]["speaker"] == ["2"]


def test_エンジンにない声を指定すると_声の名前を示して失敗する(engine, tmp_path):
    url, _ = engine

    result = run_adapter(url, "こんにちは", "存在しない声", tmp_path / "line.wav")

    assert result.returncode != 0
    assert "存在しない声" in result.stderr
    assert not (tmp_path / "line.wav").exists()


def test_音声クエリの読みは_モーラのカタカナを連ね_アクセント句は空白_ポーズは読点で示す():
    from kataribe.adapters.voicevox import reading_of

    query = {
        "accent_phrases": [
            {"moras": [{"text": "コ"}, {"text": "ン"}, {"text": "ニ"}, {"text": "チ"}, {"text": "ワ"}], "pause_mora": {"text": "、"}},
            {"moras": [{"text": "ハ"}, {"text": "ジ"}, {"text": "メ"}], "pause_mora": None},
            {"moras": [{"text": "ワ"}], "pause_mora": None},
        ]
    }

    assert reading_of(query) == "コンニチワ、ハジメ ワ"


def test_音声クエリに読みがないとき_読みを作らず_理由を示して失敗する():
    from kataribe.adapters.voicevox import AdapterError, reading_of

    with pytest.raises(AdapterError, match="accent_phrases"):
        reading_of({"speedScale": 1.0})


def test_読みの取得は_合成と同じ文と声を使い_音声は作らない(engine):
    from kataribe.adapters.voicevox import read_aloud

    url, requests = engine

    spoken = read_aloud(url, [("こんにちは、はじめまして", "ずんだもん"), ("さようなら", "四国めたん")])

    assert [item.reading for item in spoken] == ["こんにちは、はじめまして", "さようなら"]
    assert [r["path"] for r in requests] == ["/audio_query", "/audio_query"]
    assert requests[0]["query"] == {"speaker": ["3"], "text": ["こんにちは、はじめまして"]}
    assert requests[1]["query"] == {"speaker": ["2"], "text": ["さようなら"]}


def test_エンジンがエラーを返したとき_接続できないとは言わず_状態と理由を示して失敗する(engine):
    from kataribe.adapters.voicevox import AdapterError, _request

    url, _ = engine

    with pytest.raises(AdapterError, match="HTTP 404") as error:
        _request(f"{url}/no-such-path")
    assert "接続できません" not in str(error.value)


def test_エンジンに接続できないとき_理由を示して失敗する(tmp_path):
    result = run_adapter("http://127.0.0.1:9", "こんにちは", "ずんだもん", tmp_path / "line.wav")

    assert result.returncode != 0
    assert "VOICEVOX" in result.stderr
    assert not (tmp_path / "line.wav").exists()
