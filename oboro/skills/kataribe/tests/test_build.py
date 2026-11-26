import sys

from conftest import run_build


def test_台本と画面と辞書の3ファイルからビルドが完了し_単一HTMLと文字起こしが出力される(project):
    result = run_build(project)

    assert result.returncode == 0, result.stderr
    assert (project / "out" / "video.html").is_file()
    transcript = (project / "out" / "transcript.md").read_text(encoding="utf-8")
    assert "テスト動画" in transcript
    assert "最初の章" in transcript
    assert "こんにちは" in transcript
    assert "おしまい" in transcript


def test_TTSアダプターが実行できないとき_理由を表示して失敗し_出力を作らない(project):
    result = run_build(project, tts_cmd="/nonexistent/kataribe-tts")

    assert result.returncode != 0
    assert "TTS" in result.stderr
    assert not (project / "out").exists()


def test_TTSアダプターが失敗したとき_アダプターの理由を表示して失敗し_出力を作らない(project, tmp_path):
    broken = tmp_path / "broken_tts.py"
    broken.write_text("import sys\nsys.stderr.write('エンジンに接続できません')\nraise SystemExit(3)\n", encoding="utf-8")

    result = run_build(project, tts_cmd=f"{sys.executable} {broken}")

    assert result.returncode != 0
    assert "エンジンに接続できません" in result.stderr
    assert not (project / "out").exists()


def test_画面や台本に置換用の記号に似た文字列があっても_そのまま出力される(tmp_path):
    from conftest import SCRIPT, make_project

    scenes = (
        '<section data-scene="s1"><p>{{TIMELINE}} {{JS}} {{AUDIO}}</p></section>'
        '<section data-scene="s2"></section><section data-scene="s3"></section>'
    )
    script = {**SCRIPT, "title": "{{CSS}}の使い方"}
    project = make_project(tmp_path / "p", script=script, scenes=scenes)

    assert run_build(project).returncode == 0, "build"

    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    assert "<p>{{TIMELINE}} {{JS}} {{AUDIO}}</p>" in html
    assert "<title>{{CSS}}の使い方</title>" in html


import pytest


@pytest.mark.parametrize(
    "broken, message",
    [
        ("readings.json", "readings.json"),
        ("script.json", "script.json"),
        ("scenes.html", "scenes.html"),
    ],
)
def test_入力ファイルが読めないとき_どのファイルか表示して失敗し_出力を作らない(project, broken, message):
    if broken == "scenes.html":
        (project / broken).unlink()
    else:
        (project / broken).write_text("{壊れたJSON", encoding="utf-8")

    result = run_build(project)

    assert result.returncode != 0
    assert message in result.stderr
    assert not (project / "out").exists()
