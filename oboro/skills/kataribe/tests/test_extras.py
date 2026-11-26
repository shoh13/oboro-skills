import json
import wave

from conftest import SCRIPT, make_project, run_build

SCRIPT_SOURCES = {**SCRIPT, "sources": [{"title": "出典A", "url": "https://example.com/a"}]}


def extras(project):
    return project / "out" / "extras"


def test_extras_を付けないときは_副産物を出さない(project):
    assert run_build(project).returncode == 0
    assert not extras(project).exists()


def test_extras_を付けると_音声と字幕とタイムラインと利用条件ファイルが出る(project):
    result = run_build(project, args=["--extras"])

    assert result.returncode == 0, result.stderr
    for name in ("audio.wav", "captions.vtt", "timeline.json", "TERMS.txt"):
        assert (extras(project) / name).is_file(), name


def test_副産物の音声は_単一HTMLの音声と同じ長さで_タイムラインJSONの長さと一致する(project):
    run_build(project, args=["--extras"])

    timeline = json.loads((extras(project) / "timeline.json").read_text(encoding="utf-8"))
    with wave.open(str(extras(project) / "audio.wav"), "rb") as wav:
        seconds = wav.getnframes() / wav.getframerate()
    assert abs(seconds - timeline["duration"]) < 1e-3
    assert [line["id"] for line in timeline["lines"]] == ["s1-0", "s1-1", "s2-0", "s3-0"]


def test_字幕VTTは_行ごとにタイムラインの開始と終了と表示文を持つ(project):
    run_build(project, args=["--extras"])

    vtt = (extras(project) / "captions.vtt").read_text(encoding="utf-8")
    lines = vtt.splitlines()
    assert lines[0] == "WEBVTT"
    # fake TTS は 1 文字 0.02 秒。「こんにちは」は 5 字 = 0.100 秒、「はじめましょう」は 7 字 = 0.140 秒
    assert "00:00:00.000 --> 00:00:00.100" in lines
    assert "00:00:00.100 --> 00:00:00.240" in lines
    assert "こんにちは" in lines and "はじめましょう" in lines


def test_タイムラインJSONは_クレジットと出典と題名を持つ_mp4のクレジット画面の元になる(tmp_path):
    project = make_project(tmp_path / "p", script=SCRIPT_SOURCES)
    run_build(project, args=["--extras"])

    timeline = json.loads((extras(project) / "timeline.json").read_text(encoding="utf-8"))
    assert timeline["title"] == "テスト動画"
    assert timeline["credit"] == ["VOICEVOX:ずんだもん"]
    assert timeline["sources"] == [{"title": "出典A", "url": "https://example.com/a"}]


def test_利用条件ファイルには_クレジットと2つの規約へのリンクが書かれている(project):
    run_build(project, args=["--extras"])

    terms = (extras(project) / "TERMS.txt").read_text(encoding="utf-8")
    assert "VOICEVOX:ずんだもん" in terms
    assert "https://voicevox.hiroshiba.jp/term/" in terms
    assert "https://zunko.jp/con_ongen_kiyaku.html" in terms


def test_TTSが失敗したときは_副産物も出さない(project):
    result = run_build(project, tts_cmd="/nonexistent/kataribe-tts", args=["--extras"])

    assert result.returncode != 0
    assert not (project / "out").exists()
