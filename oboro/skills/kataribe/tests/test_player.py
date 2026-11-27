import pytest
from conftest import run_build, seek, visible_scenes


@pytest.mark.parametrize(
    "seconds, scene, chapter, caption",
    [
        (0.05, "s1", "最初の章", "こんにちは"),
        (0.15, "s1", "最初の章", "はじめましょう"),
        (0.30, "s2", "最初の章", "二つ目のシーンです"),
        (0.45, "s3", "次の章", "おしまい"),
    ],
)
def test_再生位置に応じて_字幕とシーンと章が同じ時刻から切り替わる(player, seconds, scene, chapter, caption):
    seek(player, seconds)

    assert visible_scenes(player) == [scene]
    assert player.inner_text("#kataribe-chapter") == chapter
    assert player.inner_text("#kataribe-caption") == caption


def test_再生ボタンで最後まで再生でき_終了時は最後の行の表示になる(player):
    assert player.inner_text("#kataribe-play") == "再生"

    player.click("#kataribe-play")
    player.wait_for_function("document.getElementById('kataribe-audio').ended")

    assert visible_scenes(player) == ["s3"]
    assert player.inner_text("#kataribe-chapter") == "次の章"
    assert player.inner_text("#kataribe-caption") == "おしまい"
    assert player.inner_text("#kataribe-play") == "再生"


def test_再生中は一時停止でき_ボタンの表記が切り替わる(browser, tmp_path):
    from conftest import SCRIPT, make_project

    long_script = {**SCRIPT, "chapters": [{"id": "c1", "title": "長い章", "scenes": [{"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "あ" * 400}]}]}]}
    project = make_project(tmp_path / "long", script=long_script)
    assert run_build(project).returncode == 0
    page = browser.new_page()
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")

    page.click("#kataribe-play")
    page.wait_for_function("document.getElementById('kataribe-audio').currentTime > 0.1")
    assert page.inner_text("#kataribe-play") == "一時停止"

    page.click("#kataribe-play")
    page.wait_for_function("document.getElementById('kataribe-play').textContent === '再生'")
    assert page.evaluate("document.getElementById('kataribe-audio').paused") is True
    page.close()


def test_字幕の表示切替で_字幕が消え_もう一度で戻る(player):
    seek(player, 0.05)
    assert player.inner_text("#kataribe-caption") == "こんにちは"

    player.click("#kataribe-captions-toggle")
    assert player.inner_text("#kataribe-caption") == ""
    assert player.get_attribute("#kataribe-captions-toggle", "aria-pressed") == "false"

    player.click("#kataribe-captions-toggle")
    assert player.inner_text("#kataribe-caption") == "こんにちは"
    assert player.get_attribute("#kataribe-captions-toggle", "aria-pressed") == "true"


def test_作者が指定した画面のレイアウトは_表示中のシーンでそのまま使われる(browser, tmp_path):
    from conftest import make_project

    scenes = (
        "<style>.scene{display:flex;gap:10px}</style>"
        '<section class="scene" data-scene="s1"><p>a</p></section>'
        '<section class="scene" data-scene="s2"><p>b</p></section>'
        '<section class="scene" data-scene="s3"><p>c</p></section>'
    )
    project = make_project(tmp_path / "layout", scenes=scenes)
    assert run_build(project).returncode == 0
    page = browser.new_page()
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")

    seek(page, 0.05)

    display = page.evaluate("s => getComputedStyle(document.querySelector(`section[data-scene=${s}]`)).display", "s1")
    assert display == "flex"
    assert visible_scenes(page) == ["s1"]
    page.close()
