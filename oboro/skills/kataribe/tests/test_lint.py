from conftest import run_lint


def test_問題のない台本はlintを通り_TTSを使わずに終了コード0で終わる(project):
    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert not (project / "out").exists()


import json

import pytest
from conftest import run_build


def edit_script(project, edit) -> None:
    path = project / "script.json"
    script = json.loads(path.read_text(encoding="utf-8"))
    edit(script)
    path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")


def first_line(script: dict) -> dict:
    return script["chapters"][0]["scenes"][0]["lines"][0]


FAILING_SCRIPTS = [
    ("speaker がない", lambda s: first_line(s).pop("speaker"), "speaker"),
    ("許可リスト外の声", lambda s: first_line(s).update(speaker="未登録の声"), "未登録の声"),
    ("title がない", lambda s: s.pop("title"), "title"),
]


@pytest.mark.parametrize("name, edit, keyword", FAILING_SCRIPTS, ids=[c[0] for c in FAILING_SCRIPTS])
def test_lintは_speakerとtitleの問題を失敗として理由つきで報告する(project, name, edit, keyword):
    edit_script(project, edit)

    result = run_lint(project)

    assert result.returncode != 0
    assert keyword in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("name, edit, keyword", FAILING_SCRIPTS, ids=[c[0] for c in FAILING_SCRIPTS])
def test_buildも同じ問題で_TTSを呼ぶ前に失敗し_出力を作らない(project, name, edit, keyword):
    edit_script(project, edit)

    result = run_build(project, tts_cmd="/nonexistent/kataribe-tts")

    assert result.returncode != 0
    assert keyword in result.stderr
    assert "Traceback" not in result.stderr
    assert "TTS" not in result.stderr
    assert not (project / "out").exists()


def test_許可リスト外の声のエラーは_使える声を示す(project):
    edit_script(project, lambda s: first_line(s).update(speaker="未登録の声"))

    result = run_lint(project)

    assert "ずんだもん" in result.stderr
    assert "四国めたん" in result.stderr


def remove(path: list):
    def edit(script):
        target = script
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return edit


def replace(path: list, value):
    def edit(script):
        target = script
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return edit


BROKEN_STRUCTURES = [
    ("chapters がない", remove(["chapters"]), "chapters"),
    ("chapters が配列でない", replace(["chapters"], "章"), "chapters"),
    ("章の id がない", remove(["chapters", 0, "id"]), "chapters[0].id"),
    ("章の title がない", remove(["chapters", 1, "title"]), "chapters[1].title"),
    ("章の scenes がない", remove(["chapters", 0, "scenes"]), "chapters[0].scenes"),
    ("シーンの id がない", remove(["chapters", 0, "scenes", 1, "id"]), "chapters[0].scenes[1].id"),
    ("シーンの lines がない", remove(["chapters", 0, "scenes", 0, "lines"]), "chapters[0].scenes[0].lines"),
    ("行の text がない", remove(["chapters", 0, "scenes", 0, "lines", 1, "text"]), "chapters[0].scenes[0].lines[1].text"),
    ("行が文字列", replace(["chapters", 1, "scenes", 0, "lines", 0], "おしまい"), "chapters[1].scenes[0].lines[0]"),
    ("行の reading が文字列でない", replace(["chapters", 0, "scenes", 0, "lines", 0, "reading"], 3), "chapters[0].scenes[0].lines[0].reading"),
]


@pytest.mark.parametrize("name, edit, location", BROKEN_STRUCTURES, ids=[c[0] for c in BROKEN_STRUCTURES])
def test_台本の構造の誤りは_トレースバックでなく項目の場所を示して失敗する(project, name, edit, location):
    edit_script(project, edit)

    for result in (run_lint(project), run_build(project)):
        assert result.returncode != 0
        assert location in result.stderr
        assert "Traceback" not in result.stderr


def test_台本がオブジェクトでないときも_利用者向けに失敗する(project):
    (project / "script.json").write_text("[]", encoding="utf-8")

    result = run_lint(project)

    assert result.returncode != 0
    assert "script.json" in result.stderr
    assert "Traceback" not in result.stderr


def long_line_script(project, length: int) -> None:
    edit_script(project, replace(["chapters", 0, "scenes", 0, "lines", 0, "text"], "あ" * length))


def test_1行が60字を超える字幕は_行IDと文字数を示す警告になり_lintは成功する(project):
    long_line_script(project, 61)

    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert "警告: s1-0" in result.stderr
    assert "61" in result.stderr
    assert "警告: s1-1" not in result.stderr


def test_ちょうど60字の字幕は警告にならない(project):
    long_line_script(project, 60)

    result = run_lint(project)

    assert result.returncode == 0
    assert "警告" not in result.stderr


def test_buildも長い字幕を警告し_ビルドは続行して出力する(project):
    long_line_script(project, 61)

    result = run_build(project)

    assert result.returncode == 0, result.stderr
    assert "警告: s1-0" in result.stderr
    assert (project / "out" / "video.html").is_file()


def set_first_line(project, text: str, reading: str | None = None, readings: str | None = None) -> None:
    def edit(script):
        line = script["chapters"][0]["scenes"][0]["lines"][0]
        line["text"] = text
        if reading is not None:
            line["reading"] = reading

    edit_script(project, edit)
    if readings is not None:
        (project / "readings.json").write_text(readings, encoding="utf-8")


def test_読みが未登録の英単語は_行IDと単語を示す警告になり_lintは成功する(project):
    set_first_line(project, "APIを使います")

    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert "警告: s1-0" in result.stderr
    assert "API" in result.stderr


def test_行にreadingがあれば_英単語があっても警告しない(project):
    set_first_line(project, "APIを使います", reading="エーピーアイをつかいます")

    assert "警告" not in run_lint(project).stderr


def test_辞書に表記があれば_英単語は警告しない(project):
    set_first_line(project, "APIを使います", readings='{"API": "エーピーアイ"}')

    assert "警告" not in run_lint(project).stderr


def test_英字1文字は警告の対象外(project):
    set_first_line(project, "Aを選びます")

    assert "警告" not in run_lint(project).stderr


def test_辞書の表記は長い語から使われ_残った英単語だけが警告になる(project):
    set_first_line(project, "Claude Codeを使います", readings='{"Claude Code": "クロードコード"}')
    assert "警告" not in run_lint(project).stderr

    set_first_line(project, "Claude Codeを使います", readings='{"Claude": "クロード"}')
    result = run_lint(project)
    assert "警告: s1-0" in result.stderr
    assert "Code" in result.stderr
    assert "Claude" not in result.stderr


def test_buildも読み未登録の英単語を警告し_ビルドは続行する(project):
    set_first_line(project, "APIを使います")

    result = run_build(project)

    assert result.returncode == 0, result.stderr
    assert "警告: s1-0" in result.stderr
    assert (project / "out" / "video.html").is_file()


def test_buildは_実測の表示時間で1秒7_5字を超える字幕を警告し_ビルドは続行する(project):
    result = run_build(project, extra_env={"FAKE_TTS_SECONDS_PER_CHAR": "0.1"})

    assert result.returncode == 0, result.stderr
    assert "警告: s1-0" in result.stderr
    assert "10.0 字/秒" in result.stderr
    assert (project / "out" / "video.html").is_file()


def test_buildは_1秒7_5字以下の字幕を警告しない(project):
    result = run_build(project, extra_env={"FAKE_TTS_SECONDS_PER_CHAR": "0.2"})

    assert result.returncode == 0, result.stderr
    assert "字/秒" not in result.stderr


def test_lintは音声を合成しないので_速度の警告を出さない(project):
    result = run_lint(project)

    assert result.returncode == 0
    assert "字/秒" not in result.stderr
    assert result.stderr == ""


EMPTY_CONTENT = [
    ("シーンのない章", replace(["chapters", 1, "scenes"], []), "chapters[1]"),
    ("行のない章", replace(["chapters", 1, "scenes", 0, "lines"], []), "chapters[1]"),
    ("章が1つもない台本", replace(["chapters"], []), "chapters"),
    ("空の text", replace(["chapters", 0, "scenes", 0, "lines", 0, "text"], ""), "chapters[0].scenes[0].lines[0].text"),
    ("空白だけの text", replace(["chapters", 0, "scenes", 0, "lines", 1, "text"], "  \n"), "chapters[0].scenes[0].lines[1].text"),
    ("空白だけの title", replace(["title"], "   "), "title"),
]


@pytest.mark.parametrize("name, edit, location", EMPTY_CONTENT, ids=[c[0] for c in EMPTY_CONTENT])
def test_空の内容は_lintとbuildのどちらでも_TTSの前にトレースバックなしで失敗する(project, name, edit, location):
    edit_script(project, edit)

    for result in (run_lint(project), run_build(project, tts_cmd="/nonexistent/kataribe-tts")):
        assert result.returncode != 0
        assert location in result.stderr
        assert "Traceback" not in result.stderr
        assert "TTS" not in result.stderr
    assert not (project / "out").exists()


BAD_ABOUT = [
    ("description が文字列でない", {"description": 3}, "description"),
    ("sources が配列でない", {"sources": "https://example.com"}, "sources"),
    ("sources の要素がオブジェクトでない", {"sources": ["https://example.com"]}, "sources[0]"),
    ("sources の title がない", {"sources": [{"url": "https://example.com"}]}, "sources[0].title"),
    ("sources の url がない", {"sources": [{"title": "資料"}]}, "sources[0].url"),
    ("sources の title が文字列でない", {"sources": [{"title": 1, "url": "https://example.com"}]}, "sources[0].title"),
    ("sources の url が文字列でない", {"sources": [{"title": "資料", "url": 2}]}, "sources[0].url"),
    ("2つ目の url が javascript:", {"sources": [{"title": "A", "url": "https://example.com"}, {"title": "B", "url": "javascript:alert(1)"}]}, "sources[1].url"),
    ("url が相対パス", {"sources": [{"title": "資料", "url": "/docs/readme"}]}, "sources[0].url"),
    ("url が ftp:", {"sources": [{"title": "資料", "url": "ftp://example.com/file"}]}, "sources[0].url"),
    ("sources の title が空", {"sources": [{"title": "  ", "url": "https://example.com"}]}, "sources[0].title"),
    ("sources の url が空", {"sources": [{"title": "資料", "url": ""}]}, "sources[0].url"),
    ("url が https:// だけ", {"sources": [{"title": "資料", "url": "https://"}]}, "sources[0].url"),
    ("url が http:// だけ", {"sources": [{"title": "資料", "url": "http://"}]}, "sources[0].url"),
    ("url のホストが空で パスだけ", {"sources": [{"title": "資料", "url": "http:///x"}]}, "sources[0].url"),
    ("url のホストが空で ポートだけ", {"sources": [{"title": "資料", "url": "http://:80/"}]}, "sources[0].url"),
    ("url のホストが空で クエリだけ", {"sources": [{"title": "資料", "url": "https://?a=1"}]}, "sources[0].url"),
    ("url のホストが空で ユーザー情報だけ", {"sources": [{"title": "資料", "url": "https://user@/x"}]}, "sources[0].url"),
    ("2つ目の url にホストがない", {"sources": [{"title": "A", "url": "https://example.com"}, {"title": "B", "url": "https://"}]}, "sources[1].url"),
]


@pytest.mark.parametrize("name, extra, location", BAD_ABOUT, ids=[c[0] for c in BAD_ABOUT])
def test_説明文と出典の誤りは_lintとbuildのどちらでも_TTSの前に場所を示して失敗する(project, name, extra, location):
    edit_script(project, lambda script: script.update(extra))

    for result in (run_lint(project), run_build(project, tts_cmd="/nonexistent/kataribe-tts")):
        assert result.returncode != 0
        assert location in result.stderr
        assert "Traceback" not in result.stderr
        assert "TTS" not in result.stderr
    assert not (project / "out").exists()


def test_httpとhttpsのURLは出典として受け付ける(project):
    edit_script(
        project,
        lambda script: script.update(
            description="説明", sources=[{"title": "A", "url": "https://example.com"}, {"title": "B", "url": "HTTP://example.org"}]
        ),
    )

    assert run_lint(project).returncode == 0


@pytest.mark.parametrize(
    "url",
    ["http://localhost:8080/", "https://example.com/a?b=1#c", "http://127.0.0.1/x", "http://[::1]:8080/", "https://user@example.com/"],
)
def test_ホスト名のあるURLは_ポート番号やパスやクエリがついていても出典として受け付ける(project, url):
    edit_script(project, lambda script: script.update(sources=[{"title": "A", "url": url}]))

    assert run_lint(project).returncode == 0
