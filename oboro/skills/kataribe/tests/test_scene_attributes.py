import pytest
from conftest import make_project, run_build, run_lint

# conftest の SCRIPT: s1 は2行（行番号 0、1）、s2 は1行（0）、s3 は1行（0）


def project_with(tmp_path, scenes_html: str):
    return make_project(tmp_path / "p", scenes=scenes_html)


def s1(body: str) -> str:
    return f'<section data-scene="s1">\n  <p>ok</p>\n  {body}\n</section>\n<section data-scene="s2"></section>\n<section data-scene="s3"></section>\n'


BAD = [
    ("data-at が行数と同じ", s1('<p data-at="2">x</p>'), "data-at", '"2"'),
    ("data-at が行数を超える", s1('<p data-at="5">x</p>'), "data-at", '"5"'),
    ("data-out が行数と同じ", s1('<p data-out="2">x</p>'), "data-out", '"2"'),
    ("data-focus の1つが範囲外", s1('<p data-focus="0,2">x</p>'), "data-focus", '"0,2"'),
    ("別のシーンの行数で判定する", '<section data-scene="s1"></section><section data-scene="s2"><p data-at="1">x</p></section><section data-scene="s3"></section>', "data-at", "s2"),
    ("data-out が data-at と同じ", s1('<p data-at="1" data-out="1">x</p>'), "data-out", '"1"'),
    ("data-out が data-at より前", s1('<p data-at="1" data-out="0">x</p>'), "data-out", '"0"'),
    ("data-at がなく data-out が0", s1('<p data-out="0">x</p>'), "data-out", '"0"'),
    ("data-at が英字", s1('<p data-at="abc">x</p>'), "data-at", '"abc"'),
    ("data-at が負", s1('<p data-at="-1">x</p>'), "data-at", '"-1"'),
    ("data-out が小数", s1('<p data-out="1.5">x</p>'), "data-out", '"1.5"'),
    ("data-at が空", s1('<p data-at="">x</p>'), "data-at", '""'),
    ("data-at が空白だけ", s1('<p data-at="  ">x</p>'), "data-at", '"  "'),
    ("data-at が値なし", s1("<p data-at>x</p>"), "data-at", '""'),
    ("data-focus に空の要素", s1('<p data-focus="0,,1">x</p>'), "data-focus", '"0,,1"'),
    ("data-focus に英字", s1('<p data-focus="0,a">x</p>'), "data-focus", '"0,a"'),
    ("data-at が全角の数字", s1('<p data-at="１">x</p>'), "data-at", '"１"'),
]


@pytest.mark.parametrize("name, html, attribute, value", BAD, ids=[c[0] for c in BAD])
def test_不正な属性は_lintとbuildのどちらでも_TTSの前に場所を示して失敗する(tmp_path, name, html, attribute, value):
    project = project_with(tmp_path, html)

    for result in (run_lint(project), run_build(project, tts_cmd="/nonexistent/kataribe-tts")):
        assert result.returncode != 0
        assert "scenes.html" in result.stderr
        assert attribute in result.stderr
        assert value in result.stderr
        assert "Traceback" not in result.stderr
        assert "TTS" not in result.stderr
    assert not (project / "out").exists()


def test_エラーには_scenes_htmlの行番号とシーンIDと要素名が出る(tmp_path):
    project = project_with(tmp_path, s1('<p data-at="9">x</p>'))

    result = run_lint(project)

    assert "3行目" in result.stderr
    assert "s1" in result.stderr
    assert "<p>" in result.stderr


GOOD = [
    ("範囲内の data-at と data-out", s1('<p data-at="0" data-out="1">x</p>')),
    ("data-focus の空白つきの複数", s1('<p data-focus="0, 1">x</p>')),
    ("最終行を指す data-at", s1('<p data-at="1">x</p>')),
    ("シーンの外の要素は検査しない", '<p data-at="99">外</p>' + s1("")),
    ("section 自身の属性は検査しない", '<section data-scene="s1" data-at="99"></section><section data-scene="s2"></section><section data-scene="s3"></section>'),
    ("台本にないシーンの section は検査しない", s1("") + '<section data-scene="zzz"><p data-at="99">x</p></section>'),
    ("data-scene のない section の中の要素は検査しない", s1("") + '<section><p data-at="99">x</p></section>'),
]


@pytest.mark.parametrize("name, html", GOOD, ids=[c[0] for c in GOOD])
def test_有効な属性や検査の対象外の要素は_lintが成功する(tmp_path, name, html):
    project = project_with(tmp_path, html)

    result = run_lint(project)

    assert result.returncode == 0, result.stderr


def test_入れ子のsectionの中の要素も_そのシーンの要素として検査する(tmp_path):
    project = project_with(tmp_path, s1('<section><p data-at="9">x</p></section><p data-at="9">y</p>'))

    result = run_lint(project)

    assert result.returncode != 0
    assert "s1" in result.stderr


def test_同じ属性が2回書かれたときは_ブラウザと同じく最初の値で検査する(tmp_path):
    first_ok = project_with(tmp_path / "a", s1('<p data-at="1" data-at="99">x</p>'))
    first_bad = project_with(tmp_path / "b", s1('<p data-at="99" data-at="1">x</p>'))

    assert run_lint(first_ok).returncode == 0
    result = run_lint(first_bad)
    assert result.returncode != 0
    assert '"99"' in result.stderr
