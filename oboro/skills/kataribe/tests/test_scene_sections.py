import pytest
from conftest import SCENES, SCRIPT, make_project, run_build, run_lint

ALL = '<section data-scene="s1">1</section>\n<section data-scene="s2">2</section>\n<section data-scene="s3">3</section>\n'


def run(command, project):
    return run_lint(project) if command == "lint" else run_build(project, tts_cmd="/nonexistent/kataribe-tts")


def run_ok(command, project):
    return run_lint(project) if command == "lint" else run_build(project)


@pytest.mark.parametrize("command", ["lint", "build"])
def test_台本のシーンに対応するsectionがないと_シーンIDと場所を示して失敗し_TTSも呼ばない(tmp_path, command):
    scenes = '<section data-scene="s1">1</section>\n<section data-scene="s3">3</section>\n'
    project = make_project(tmp_path / "p", scenes=scenes)

    result = run(command, project)

    assert result.returncode == 1
    assert "s2" in result.stderr
    assert "chapters[0].scenes[1]" in result.stderr
    assert "TTS" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project / "out").exists()


@pytest.mark.parametrize("command", ["lint", "build"])
def test_data_sceneの綴り違いは_欠落として失敗する(tmp_path, command):
    scenes = ALL.replace('data-scene="s2"', 'data-sence="s2"')
    project = make_project(tmp_path / "p", scenes=scenes)

    result = run(command, project)

    assert result.returncode == 1
    assert "s2" in result.stderr


@pytest.mark.parametrize("command", ["lint", "build"])
def test_同じdata_sceneのsectionが2つあると_シーンIDと行番号を示して失敗する(tmp_path, command):
    scenes = '<section data-scene="s1">1</section>\n<section data-scene="s2">2</section>\n<section data-scene="s1">1'"'"'</section>\n<section data-scene="s3">3</section>\n'
    project = make_project(tmp_path / "p", scenes=scenes)

    result = run(command, project)

    assert result.returncode == 1
    assert "s1" in result.stderr
    assert "1行目" in result.stderr and "3行目" in result.stderr
    assert "TTS" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project / "out").exists()


def test_台本にないIDのsectionが重複しているときも_失敗する(tmp_path):
    scenes = ALL + '<section data-scene="extra">a</section>\n<section data-scene="extra">b</section>\n'
    project = make_project(tmp_path / "p", scenes=scenes)

    result = run_lint(project)

    assert result.returncode == 1
    assert "extra" in result.stderr


@pytest.mark.parametrize("command", ["lint", "build"])
def test_台本にないsectionは_警告を出して続行し_終了コードは0(tmp_path, command):
    scenes = ALL + '<section data-scene="extra">余り</section>\n'
    project = make_project(tmp_path / "p", scenes=scenes)

    result = run_ok(command, project)

    assert result.returncode == 0, result.stderr
    warnings = [line for line in result.stderr.splitlines() if line.startswith("警告:") and "scenes.html" in line]
    assert len(warnings) == 1
    assert "extra" in warnings[0] and "4行目" in warnings[0]
    if command == "build":
        assert (project / "out" / "video.html").is_file()


@pytest.mark.parametrize("command", ["lint", "build"])
def test_data_sceneが空のsectionも_警告になる(tmp_path, command):
    scenes = ALL + '<section data-scene="">空</section>\n'
    project = make_project(tmp_path / "p", scenes=scenes)

    result = run_ok(command, project)

    assert result.returncode == 0, result.stderr
    assert any(line.startswith("警告:") and "4行目" in line for line in result.stderr.splitlines())


def test_シーンのsectionの中に入れ子になったsectionは_別のシーンとして数えない(tmp_path):
    scenes = '<section data-scene="s1"><section data-scene="s9">中</section></section>\n<section data-scene="s2">2</section>\n<section data-scene="s3">3</section>\n'
    project = make_project(tmp_path / "p", scenes=scenes)

    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert "s9" not in result.stderr


def test_sectionが過不足なく対応していれば_警告は出ない(project):
    result = run_lint(project)

    assert result.returncode == 0
    assert "警告" not in result.stderr


def test_大文字小文字だけが違うIDは_別のシーンとして対応づけられる(tmp_path):
    chapters = [{"id": "c1", "title": "章", "scenes": [{"id": "Intro", "lines": [{"speaker": "ずんだもん", "text": "あ"}]}, {"id": "intro", "lines": [{"speaker": "ずんだもん", "text": "い"}]}]}]
    scenes = '<section data-scene="Intro">A</section><section data-scene="intro">B</section>'
    project = make_project(tmp_path / "p", script={**SCRIPT, "chapters": chapters}, scenes=scenes)

    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert "警告" not in result.stderr


def test_buildの警告は_lintと同じ内容で出る(tmp_path):
    scenes = ALL + '<section data-scene="extra">余り</section>\n'
    project = make_project(tmp_path / "p", scenes=scenes)

    def section_warnings(result):
        return [line for line in result.stderr.splitlines() if "scenes.html" in line]

    assert section_warnings(run_lint(project)) == section_warnings(run_build(project))
    assert section_warnings(run_lint(project))
