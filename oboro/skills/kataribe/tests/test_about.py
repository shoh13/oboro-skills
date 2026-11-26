import json

import pytest
from conftest import SCRIPT, make_project, run_build

VOICEVOX_TERMS = "https://voicevox.hiroshiba.jp/term/"
ZUNKO_TERMS = "https://zunko.jp/con_ongen_kiyaku.html"


def open_page(browser, project):
    assert run_build(project).returncode == 0
    page = browser.new_page()
    page.set_default_timeout(5000)
    page.goto((project / "out" / "video.html").as_uri())
    return page


def about_part(page, name: str):
    return page.query_selector(f"#kataribe-about [data-about='{name}']")


def test_概要欄は_プレーヤーの下に常時表示され_使った声のクレジットだけが出る(browser, project):
    page = open_page(browser, project)

    about = page.query_selector("#kataribe-about")
    assert about and about.is_visible()
    controls = page.query_selector("#kataribe-controls")
    assert controls
    assert about.bounding_box()["y"] >= controls.bounding_box()["y"] + controls.bounding_box()["height"]
    credits = about_part(page, "credits")
    assert credits
    assert "VOICEVOX:ずんだもん" in credits.inner_text()
    assert "四国めたん" not in credits.inner_text()
    page.close()


def test_声が四国めたんなら_四国めたんのクレジットだけが出る(browser, tmp_path):
    project = make_project(tmp_path / "metan", script=json.loads(json.dumps(SCRIPT, ensure_ascii=False).replace("ずんだもん", "四国めたん")))
    page = open_page(browser, project)

    credits = about_part(page, "credits")
    assert credits
    assert "VOICEVOX:四国めたん" in credits.inner_text()
    assert "ずんだもん" not in credits.inner_text()
    page.close()


def test_利用条件は_2つの規約へのリンクを別タブで安全に開く形で示す(browser, project):
    page = open_page(browser, project)

    links = page.eval_on_selector_all(
        "#kataribe-about [data-about='terms'] a",
        "els => els.map(e => ({href: e.href, target: e.target, rel: e.rel}))",
    )
    assert [link["href"] for link in links] == [VOICEVOX_TERMS, ZUNKO_TERMS]
    for link in links:
        assert link["target"] == "_blank"
        assert "noopener" in link["rel"] and "noreferrer" in link["rel"]
    page.close()


def test_説明文は_HTMLとして解釈されず_改行を保って表示される(browser, tmp_path):
    description = "1行目です。\n<b>2行目</b>と&amp;です。\n<script>window.injected = true</script>"
    project = make_project(tmp_path / "desc", script={**SCRIPT, "description": description})
    page = open_page(browser, project)

    part = about_part(page, "description")
    assert part
    assert "1行目です。\n<b>2行目</b>と&amp;です。\n<script>window.injected = true</script>" in part.inner_text()
    assert page.query_selector("#kataribe-about b") is None
    assert page.evaluate("window.injected") is None
    page.close()


def test_出典は_タイトルをリンクの文字にして別タブで安全に開く形で順に並ぶ(browser, tmp_path):
    sources = [
        {"title": "公式ドキュメント", "url": "https://example.com/docs?a=1&b=2"},
        {"title": "解説記事 <1>", "url": "http://example.org/article"},
    ]
    project = make_project(tmp_path / "src", script={**SCRIPT, "sources": sources})
    page = open_page(browser, project)

    links = page.eval_on_selector_all(
        "#kataribe-about [data-about='sources'] a",
        "els => els.map(e => ({text: e.textContent, href: e.href, target: e.target, rel: e.rel}))",
    )
    assert [(link["text"], link["href"]) for link in links] == [
        ("公式ドキュメント", "https://example.com/docs?a=1&b=2"),
        ("解説記事 <1>", "http://example.org/article"),
    ]
    for link in links:
        assert link["target"] == "_blank"
        assert "noopener" in link["rel"] and "noreferrer" in link["rel"]
    page.close()


def test_説明文も出典もないとき_その部分は出さず_クレジットと利用条件は出る(browser, project):
    page = open_page(browser, project)

    assert about_part(page, "description") is None
    assert about_part(page, "sources") is None
    assert about_part(page, "credits") is not None
    assert about_part(page, "terms") is not None
    page.close()


@pytest.mark.parametrize("description", ["   ", "\n\n", "\t", "　　", " \n\t　 "], ids=["スペース", "改行", "タブ", "全角スペース", "混在"])
def test_descriptionが空白だけのとき_説明の部分は出ず_エラーも警告も出ない(browser, tmp_path, description):
    from conftest import run_lint

    project = make_project(tmp_path / "blank", script={**SCRIPT, "description": description})
    lint = run_lint(project)
    assert lint.returncode == 0, lint.stderr
    assert lint.stderr == ""
    built = run_build(project)
    assert built.returncode == 0, built.stderr
    assert "description" not in built.stderr
    page = browser.new_page()
    page.goto((project / "out" / "video.html").as_uri())

    assert about_part(page, "description") is None
    assert "説明" not in (page.inner_text("#kataribe-about"))
    assert about_part(page, "credits") is not None
    page.close()


def test_descriptionが空文字のときも_説明の部分は出ない(browser, tmp_path):
    project = make_project(tmp_path / "empty", script={**SCRIPT, "description": ""})
    page = open_page(browser, project)

    assert about_part(page, "description") is None
    page.close()


def test_中身のあるdescriptionは_前後の空白も含めて加工せずに表示される(browser, tmp_path):
    project = make_project(tmp_path / "pad", script={**SCRIPT, "description": "\n  本文です  \n"})
    page = open_page(browser, project)

    part = about_part(page, "description")
    assert part
    assert "本文です" in part.inner_text()
    assert page.evaluate("document.querySelector(\"#kataribe-about [data-about='description'] p\").textContent") == "\n  本文です  \n"
    page.close()
