import json
import re

import pytest
from conftest import SCRIPT, build_and_read_spoken, make_project, run_build, run_lint


def script_with_lines(*lines: dict) -> dict:
    return {**SCRIPT, "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": list(lines)}]}]}


def project_with(tmp_path, lines: list[dict], readings: dict | None = None):
    return make_project(
        tmp_path / "p",
        script=script_with_lines(*lines),
        scenes='<section data-scene="s1"></section>',
        readings=json.dumps(readings or {}, ensure_ascii=False),
    )


def test_行のreadingと辞書に同じ語があるとき_行のreadingが音声合成に使われる(tmp_path):
    project = project_with(
        tmp_path,
        [{"speaker": "ずんだもん", "text": "APIを使います", "reading": "エーピーアイをつかいます"}],
        readings={"API": "ディーアイ"},
    )

    assert build_and_read_spoken(project, tmp_path) == ["エーピーアイをつかいます"]


def test_readingのない行は_辞書の表記が長い順に読みへ置き換えられて音声合成に渡される(tmp_path):
    project = project_with(
        tmp_path,
        [{"speaker": "ずんだもん", "text": "Claude Codeと Claudeを使います"}],
        readings={"Claude": "クロード", "Claude Code": "クロードコード"},
    )

    assert build_and_read_spoken(project, tmp_path) == ["クロードコードと クロードを使います"]


def test_辞書の読みが空文字の表記は_発音されない(tmp_path):
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "えーとこんにちは"}], readings={"えーと": ""})

    assert build_and_read_spoken(project, tmp_path) == ["こんにちは"]


def test_辞書にも読みにも該当しない文字列は_表示文のまま渡され_大文字小文字は区別される(tmp_path):
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "APIを使います"}, {"speaker": "ずんだもん", "text": "こんにちは"}], readings={"api": "エーピーアイ"})

    assert build_and_read_spoken(project, tmp_path) == ["APIを使います", "こんにちは"]


def test_置き換えは連鎖しない_読みの中に別の表記があっても再度は置き換えない(tmp_path):
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "AとBとAB"}], readings={"A": "B", "B": "C"})

    assert build_and_read_spoken(project, tmp_path) == ["BとCとBC"]


def test_字幕と文字起こしとタイムラインは_読みの影響を受けず表示文のままになる(tmp_path):
    project = project_with(
        tmp_path,
        [{"speaker": "ずんだもん", "text": "APIを使います", "reading": "エーピーアイをつかいます"}, {"speaker": "ずんだもん", "text": "Claudeです"}],
        readings={"Claude": "クロード"},
    )
    assert run_build(project).returncode == 0

    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    timeline_json = re.search(r'id="kataribe-timeline">(.*?)</script>', html, re.S)
    assert timeline_json
    texts = [line["text"] for line in json.loads(timeline_json.group(1))["lines"]]
    assert texts == ["APIを使います", "Claudeです"]
    transcript = (project / "out" / "transcript.md").read_text(encoding="utf-8")
    assert "APIを使います" in transcript and "Claudeです" in transcript
    assert "エーピーアイ" not in transcript and "クロード" not in transcript


def test_辞書の読みが文字列でないとき_lintとbuildはトレースバックなしで表記を示して失敗する(tmp_path):
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "こんにちは"}], readings={"API": 3})

    for result in (run_lint(project), run_build(project, tts_cmd="/nonexistent/kataribe-tts")):
        assert result.returncode != 0
        assert "readings.json" in result.stderr
        assert "API" in result.stderr
        assert "Traceback" not in result.stderr
        assert "TTS" not in result.stderr


@pytest.mark.parametrize("empty", ["", "  "], ids=["空文字", "空白だけ"])
def test_行のreadingが空や空白だけのとき_lintとbuildは場所を示して失敗する(tmp_path, empty):
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "こんにちは", "reading": empty}])

    for result in (run_lint(project), run_build(project, tts_cmd="/nonexistent/kataribe-tts")):
        assert result.returncode != 0
        assert "chapters[0].scenes[0].lines[0].reading" in result.stderr
        assert "Traceback" not in result.stderr
        assert "TTS" not in result.stderr


def test_lintの英単語の警告は_読みの適用と同じ表記の当たり方で判定される(tmp_path):
    project = project_with(
        tmp_path,
        [{"speaker": "ずんだもん", "text": "ABCD"}],
        readings={"BCD": "ビーシーディー", "AB": "エービー"},
    )

    spoken = build_and_read_spoken(project, tmp_path)
    result = run_lint(project)

    assert spoken == ["エービーCD"]
    assert "警告: s1-0" in result.stderr
    assert "CD" in result.stderr
