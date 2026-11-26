import pytest
from conftest import SCRIPT, make_project, run_build, run_lint


def script_with(chapters):
    return {**SCRIPT, "chapters": chapters}


def scene(scene_id, text="あ"):
    return {"id": scene_id, "lines": [{"speaker": "ずんだもん", "text": text}]}


DUPLICATES = {
    "同じ章のシーンID": (
        [{"id": "c1", "title": "章", "scenes": [scene("s1"), scene("s1")]}],
        "s1",
        ["chapters[0].scenes[0]", "chapters[0].scenes[1]"],
    ),
    "別の章のシーンID": (
        [{"id": "c1", "title": "章1", "scenes": [scene("s1")]}, {"id": "c2", "title": "章2", "scenes": [scene("s1")]}],
        "s1",
        ["chapters[0].scenes[0]", "chapters[1].scenes[0]"],
    ),
    "章ID": (
        [{"id": "c1", "title": "章1", "scenes": [scene("s1")]}, {"id": "c1", "title": "章2", "scenes": [scene("s2")]}],
        "c1",
        ["chapters[0]", "chapters[1]"],
    ),
}


@pytest.mark.parametrize("chapters, duplicated, places", DUPLICATES.values(), ids=list(DUPLICATES))
@pytest.mark.parametrize("command", ["lint", "build"])
def test_重複したIDは_lintとbuildが_IDと場所を示して失敗し_TTSも呼ばない(tmp_path, command, chapters, duplicated, places):
    project = make_project(tmp_path / "p", script=script_with(chapters))

    result = run_lint(project) if command == "lint" else run_build(project, tts_cmd="/nonexistent/kataribe-tts")

    assert result.returncode == 1
    assert duplicated in result.stderr
    for place in places:
        assert place in result.stderr
    assert "TTS" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project / "out").exists()


EMPTY = {
    "空のシーンID": ([{"id": "c1", "title": "章", "scenes": [scene("")]}], "chapters[0].scenes[0].id"),
    "空白だけのシーンID": ([{"id": "c1", "title": "章", "scenes": [scene("  ")]}], "chapters[0].scenes[0].id"),
    "空の章ID": ([{"id": "", "title": "章", "scenes": [scene("s1")]}], "chapters[0].id"),
    "空白だけの章ID": ([{"id": " ", "title": "章", "scenes": [scene("s1")]}], "chapters[0].id"),
}


@pytest.mark.parametrize("chapters, place", EMPTY.values(), ids=list(EMPTY))
@pytest.mark.parametrize("command", ["lint", "build"])
def test_空のIDは_lintとbuildが_場所を示して失敗し_TTSも呼ばない(tmp_path, command, chapters, place):
    project = make_project(tmp_path / "p", script=script_with(chapters))

    result = run_lint(project) if command == "lint" else run_build(project, tts_cmd="/nonexistent/kataribe-tts")

    assert result.returncode == 1
    assert place in result.stderr
    assert "TTS" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project / "out").exists()


def test_大文字小文字だけが違うシーンIDは_lintとbuildを通る(tmp_path):
    chapters = [{"id": "c1", "title": "章", "scenes": [scene("Intro"), scene("intro")]}]
    scenes = '<section data-scene="Intro">A</section><section data-scene="intro">B</section>'
    project = make_project(tmp_path / "p", script=script_with(chapters), scenes=scenes)

    assert run_lint(project).returncode == 0
    assert run_build(project).returncode == 0


def test_重複のないIDは_これまでどおりbuildを通る(project):
    assert run_build(project).returncode == 0
