import pytest
from conftest import seek

LINE_STARTS = [0.0, 0.10, 0.24, 0.42]  # こんにちは(5字)、はじめましょう(7字)、二つ目のシーンです(9字)、おしまい(4字) を 0.02秒/字 で積み上げた開始時刻


def wait_time(page, expected: float) -> None:
    page.wait_for_function(
        "expected => Math.abs(document.getElementById('kataribe-audio').currentTime - expected) < 0.01",
        arg=expected,
        timeout=3000,
    )


def current_time(page) -> float:
    return page.evaluate("document.getElementById('kataribe-audio').currentTime")


def test_次へで_1つ後の行の先頭へ移動し_最終行では動かない(player):
    seek(player, 0.05)
    player.click("#kataribe-next")
    wait_time(player, LINE_STARTS[1])
    player.click("#kataribe-next")
    wait_time(player, LINE_STARTS[2])

    seek(player, 0.45)
    player.click("#kataribe-next")
    player.wait_for_timeout(300)
    assert current_time(player) == pytest.approx(0.45, abs=0.01)


def test_前へで_1つ前の行の先頭へ移動し_先頭の行では時刻0へ戻る(player):
    seek(player, 0.30)
    player.click("#kataribe-prev")
    wait_time(player, LINE_STARTS[1])
    player.click("#kataribe-prev")
    wait_time(player, LINE_STARTS[0])
    player.click("#kataribe-prev")
    wait_time(player, LINE_STARTS[0])

    seek(player, 0.05)
    player.click("#kataribe-prev")
    wait_time(player, 0.0)


@pytest.fixture
def long_player(browser, tmp_path):
    from conftest import SCRIPT, make_project, run_build

    script = {**SCRIPT, "chapters": [{"id": "c1", "title": "長い章", "scenes": [{"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "あ" * 400}, {"speaker": "ずんだもん", "text": "い" * 400}, {"speaker": "ずんだもん", "text": "う" * 400}]}]}]}
    project = make_project(tmp_path / "long", script=script, scenes='<section data-scene="s1"><input id="memo"></section>')
    assert run_build(project).returncode == 0
    page = browser.new_page()
    page.set_default_timeout(5000)
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
    yield page
    page.close()


def test_再生中に移動しても_再生は止まらず続く(long_player):
    long_player.click("#kataribe-play")
    long_player.wait_for_function("document.getElementById('kataribe-audio').currentTime > 0.1")

    long_player.click("#kataribe-next")

    wait_time(long_player, 8.0)
    assert long_player.evaluate("document.getElementById('kataribe-audio').paused") is False
    long_player.wait_for_function("document.getElementById('kataribe-audio').currentTime > 8.2")


def test_矢印キーで前後の行へ移動できる(player):
    seek(player, 0.05)

    player.keyboard.press("ArrowRight")
    wait_time(player, LINE_STARTS[1])
    player.keyboard.press("ArrowRight")
    wait_time(player, LINE_STARTS[2])
    player.keyboard.press("ArrowLeft")
    wait_time(player, LINE_STARTS[1])


def test_ボタンにフォーカスがあっても_矢印キーで移動できる(player):
    seek(player, 0.05)
    player.focus("#kataribe-captions-toggle")

    player.keyboard.press("ArrowRight")

    wait_time(player, LINE_STARTS[1])


@pytest.mark.parametrize("modifier", ["Control", "Meta", "Alt", "Shift"])
def test_修飾キーつきの矢印キーでは_移動しない(player, modifier):
    seek(player, 0.05)

    player.keyboard.press(f"{modifier}+ArrowRight")

    player.wait_for_timeout(300)
    assert current_time(player) == pytest.approx(0.05, abs=0.01)


def test_入力欄にフォーカスがあるとき_矢印キーを奪わない(long_player):
    long_player.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
    long_player.evaluate("document.getElementById('kataribe-audio').currentTime = 1")
    long_player.wait_for_function("document.getElementById('kataribe-audio').currentTime >= 0.99")
    long_player.focus("#memo")

    long_player.keyboard.press("ArrowRight")

    long_player.wait_for_timeout(300)
    assert current_time(long_player) == pytest.approx(1.0, abs=0.01)


def chapter_items(page) -> list[dict]:
    return page.eval_on_selector_all(
        "#kataribe-chapter-bar [data-chapter-id]",
        "els => els.map(e => ({id: e.dataset.chapterId, text: e.textContent.trim(), current: e.getAttribute('aria-current')}))",
    )


def test_章バーには_台本の章がタイトルつきで順に並ぶ(player):
    items = chapter_items(player)

    assert [(item["id"], item["text"]) for item in items] == [("c1", "最初の章"), ("c2", "次の章")]


def test_章バーの章をクリックすると_その章の先頭へ移動する(player):
    seek(player, 0.05)

    player.click("#kataribe-chapter-bar [data-chapter-id='c2']")
    wait_time(player, LINE_STARTS[3])
    player.click("#kataribe-chapter-bar [data-chapter-id='c1']")
    wait_time(player, 0.0)


@pytest.mark.parametrize("seconds, current", [(0.05, "c1"), (0.30, "c1"), (0.45, "c2")])
def test_章バーは_現在の章だけを示す(player, seconds, current):
    seek(player, seconds)

    marked = [item["id"] for item in chapter_items(player) if item["current"] == "true"]
    assert marked == [current]


def transcript_items(page) -> list[dict]:
    return page.eval_on_selector_all(
        "#kataribe-transcript [data-line-id]",
        "els => els.map(e => ({id: e.dataset.lineId, text: e.textContent.trim(), current: e.getAttribute('aria-current')}))",
    )


def transcript_visible(page) -> bool:
    return page.evaluate("document.getElementById('kataribe-transcript').offsetParent !== null")


def test_文字起こしは既定で閉じているが_全行がDOMにあり_表示文のまま並ぶ(player):
    assert transcript_visible(player) is False
    assert player.get_attribute("#kataribe-transcript-toggle", "aria-expanded") == "false"
    assert [(item["id"], item["text"]) for item in transcript_items(player)] == [
        ("s1-0", "こんにちは"),
        ("s1-1", "はじめましょう"),
        ("s2-0", "二つ目のシーンです"),
        ("s3-0", "おしまい"),
    ]


def test_文字起こしは_ボタンで開閉できる(player):
    player.click("#kataribe-transcript-toggle")
    assert transcript_visible(player) is True
    assert player.get_attribute("#kataribe-transcript-toggle", "aria-expanded") == "true"

    player.click("#kataribe-transcript-toggle")
    assert transcript_visible(player) is False
    assert player.get_attribute("#kataribe-transcript-toggle", "aria-expanded") == "false"


def test_文字起こしの行をクリックすると_その行の先頭へジャンプする(player):
    player.click("#kataribe-transcript-toggle")

    player.click("#kataribe-transcript [data-line-id='s2-0']")
    wait_time(player, LINE_STARTS[2])
    player.click("#kataribe-transcript [data-line-id='s1-1']")
    wait_time(player, LINE_STARTS[1])


@pytest.mark.parametrize("seconds, current", [(0.05, "s1-0"), (0.15, "s1-1"), (0.30, "s2-0"), (0.45, "s3-0")])
def test_文字起こしは_現在の行だけを示す(player, seconds, current):
    seek(player, seconds)

    marked = [item["id"] for item in transcript_items(player) if item["current"] == "true"]
    assert marked == [current]


def test_再生速度は既定で1倍で_6段階から選べる(player):
    options = player.eval_on_selector_all("#kataribe-rate option", "els => els.map(e => [e.value, e.textContent])")
    assert options == [["0.5", "0.5倍"], ["0.75", "0.75倍"], ["1", "1倍"], ["1.25", "1.25倍"], ["1.5", "1.5倍"], ["2", "2倍"]]
    assert player.input_value("#kataribe-rate") == "1"
    assert player.evaluate("document.getElementById('kataribe-audio').playbackRate") == 1


def test_再生速度を選ぶと_音声の再生速度が変わり_再生しても保たれる(long_player):
    long_player.select_option("#kataribe-rate", "1.5")
    assert long_player.evaluate("document.getElementById('kataribe-audio').playbackRate") == 1.5

    long_player.click("#kataribe-play")
    long_player.wait_for_function("!document.getElementById('kataribe-audio').paused")
    long_player.click("#kataribe-next")
    long_player.wait_for_timeout(200)
    assert long_player.evaluate("document.getElementById('kataribe-audio').playbackRate") == 1.5


def test_再生速度の選択にフォーカスがあるとき_矢印キーを奪わない(player):
    seek(player, 0.05)
    player.focus("#kataribe-rate")
    player.keyboard.press("ArrowRight")
    player.wait_for_timeout(300)
    assert current_time(player) == pytest.approx(0.05, abs=0.01)


def seek_bar(page) -> dict:
    return page.evaluate(
        """() => {
            const bar = document.getElementById('kataribe-seek-bar');
            return {
                value: Number(bar.value),
                max: Number(bar.max),
                current: document.getElementById('kataribe-seek-current').textContent,
                duration: document.getElementById('kataribe-seek-duration').textContent,
            };
        }"""
    )


def test_再生位置のバーは_音声の長さを最大とし_現在位置に追従する(player):
    duration = player.evaluate("document.getElementById('kataribe-audio').duration")

    seek(player, 0.30)

    bar = seek_bar(player)
    assert bar["max"] == pytest.approx(duration, abs=0.001)
    assert bar["value"] == pytest.approx(0.30, abs=0.01)
    assert bar["current"] == "0:00"
    assert bar["duration"] == "0:00"


def test_再生位置のバーを動かすと_その時刻へ移動する(player):
    player.evaluate(
        """() => {
            const bar = document.getElementById('kataribe-seek-bar');
            bar.value = '0.25';
            bar.dispatchEvent(new Event('input', { bubbles: true }));
        }"""
    )

    wait_time(player, 0.25)


def test_再生位置のバーにフォーカスがあるとき_矢印キーで前後の行へ移動する(player):
    seek(player, 0.05)
    player.focus("#kataribe-seek-bar")

    player.keyboard.press("ArrowRight")

    wait_time(player, LINE_STARTS[1])


def test_再生位置の時刻は_分と秒で表示される(long_player):
    long_player.evaluate("document.getElementById('kataribe-audio').currentTime = 5")
    long_player.wait_for_function("document.getElementById('kataribe-seek-current').textContent === '0:05'")
    total = int(long_player.evaluate("document.getElementById('kataribe-audio').duration"))
    assert seek_bar(long_player)["duration"] == f"{total // 60}:{total % 60:02d}"


def test_再生中に再生位置のバーを動かしても_再生は止まらない(long_player):
    long_player.click("#kataribe-play")
    long_player.wait_for_function("!document.getElementById('kataribe-audio').paused")

    long_player.evaluate(
        """() => {
            const bar = document.getElementById('kataribe-seek-bar');
            bar.value = '10';
            bar.dispatchEvent(new Event('input', { bubbles: true }));
        }"""
    )

    long_player.wait_for_function("document.getElementById('kataribe-audio').currentTime >= 10")
    assert not long_player.evaluate("document.getElementById('kataribe-audio').paused")


def test_MP4の撮影用CSSは_再生位置のバーを隠す(player):
    from kataribe.mp4 import FRAME_CSS

    assert player.is_visible("#kataribe-seek")

    player.add_style_tag(content=FRAME_CSS)

    assert not player.is_visible("#kataribe-seek")


def visible_icons(page) -> dict[str, bool]:
    return page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll('#kataribe-controls button')].map(b => [
            b.id,
            [...b.querySelectorAll('svg')].some(i => getComputedStyle(i).display !== 'none'),
        ]))"""
    )


def test_モバイル幅ではボタンがアイコンになり_広い画面では文字のまま(player):
    assert not any(visible_icons(player).values())
    player.set_viewport_size({"width": 390, "height": 800})
    assert all(visible_icons(player).values())
    box = player.locator("#kataribe-next").bounding_box()
    assert box["width"] >= 44 and box["height"] >= 44
    assert player.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_モバイル幅でも_ボタンの名前は文字で残り_再生中は一時停止のアイコンに替わる(player):
    player.set_viewport_size({"width": 390, "height": 800})
    assert player.get_by_role("button", name="次へ").count() == 1

    def icon(cls):
        return player.evaluate(f"getComputedStyle(document.querySelector('#kataribe-play .{cls}')).display !== 'none'")

    assert icon("kataribe-icon-play") and not icon("kataribe-icon-pause")
    player.evaluate("document.getElementById('kataribe-audio').dispatchEvent(new Event('play'))")
    assert icon("kataribe-icon-pause") and not icon("kataribe-icon-play")
    assert player.get_by_role("button", name="一時停止").count() == 1


def test_モバイル幅では章バーの題が切れず_バーが横にスクロールする(player):
    player.set_viewport_size({"width": 390, "height": 800})
    clipped = player.evaluate(
        """() => [...document.querySelectorAll('#kataribe-chapter-bar button')]
            .filter(b => b.scrollWidth > b.clientWidth).map(b => b.textContent)"""
    )
    assert clipped == []
    assert player.evaluate("document.documentElement.scrollWidth <= innerWidth")
