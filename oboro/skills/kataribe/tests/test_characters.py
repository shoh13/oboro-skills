import json

import pytest
from conftest import SCRIPT, make_project, run_build, run_lint, seek
from fake_art import fake_art_env

DIALOGUE = {
    "title": "掛け合い",
    "chapters": [
        {
            "id": "c1",
            "title": "章",
            "scenes": [
                {
                    "id": "s1",
                    "lines": [
                        {"speaker": "四国めたん", "text": "はじめるわ"},
                        {"speaker": "ずんだもん", "expression": "smile", "text": "たのしみなのだ"},
                        {"speaker": "四国めたん", "expression": "angry", "text": "まじめにね"},
                        {"speaker": "ずんだもん", "text": "わかったのだ"},
                    ],
                }
            ],
        }
    ],
}
SCENES = '<section data-scene="s1"><h1>シーン1</h1></section>\n'
# fake TTS は 1 文字 0.02 秒。各行の開始の少し後の時刻
STARTS = [0.01, 0.11, 0.25, 0.35]
FACES = [
    {"四国めたん": "normal", "ずんだもん": "normal"},
    {"四国めたん": "normal", "ずんだもん": "smile"},
    {"四国めたん": "angry", "ずんだもん": "smile"},
    {"四国めたん": "angry", "ずんだもん": "normal"},
]


@pytest.fixture
def page(browser, tmp_path):
    project = make_project(tmp_path / "p", script=DIALOGUE, scenes=SCENES)
    result = run_build(project)
    assert result.returncode == 0, result.stderr
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.set_default_timeout(5000)
    page.goto((project / "out" / "video.html").as_uri())
    yield page
    page.close()


def characters(page):
    return page.eval_on_selector_all(
        "#kataribe-stage .kataribe-character",
        """els => els.map(el => ({
            speaker: el.dataset.speaker,
            face: el.dataset.face,
            mouth: el.dataset.mouth,
            blink: el.dataset.blink,
            visible: el.checkVisibility(),
            x: el.getBoundingClientRect().x,
            layers: JSON.parse(el.dataset.layers),
        }))""",
    )


def by_speaker(page):
    return {c["speaker"]: c for c in characters(page)}


def test_2人の立ち絵は_ステージの中で_めたんが左_ずんだもんが右に常に表示される(page):
    for seconds in STARTS:
        seek(page, seconds)
        chars = by_speaker(page)
        assert sorted(chars) == ["ずんだもん", "四国めたん"]
        assert all(c["visible"] for c in chars.values())
        assert chars["四国めたん"]["x"] < chars["ずんだもん"]["x"]


@pytest.mark.parametrize("index", range(4))
def test_行ごとに_話している人はその行の表情_話していない人は最後に話した行の表情になる(page, index):
    seek(page, STARTS[index])

    assert {s: c["face"] for s, c in by_speaker(page).items()} == FACES[index]


def test_表情に応じて_そのレイヤーだけが表示され_口は閉じている(page):
    seek(page, STARTS[1])
    zundamon = by_speaker(page)["ずんだもん"]

    assert zundamon["layers"] == ["!body", "!brow/*up", "!eye/*smile", "!mouth/*grin"]
    assert zundamon["mouth"] == "0"


def test_見た目は時刻だけで決まり_戻ってシークしても同じになる(page):
    seek(page, STARTS[2])
    later = characters(page)
    seek(page, STARTS[0])
    seek(page, STARTS[2])

    assert characters(page) == later


@pytest.fixture
def toned(browser, tmp_path):
    """fake TTS が音（440Hz）を出す掛け合い。どの行も声があるので、話している人の口が開く。"""
    project = make_project(tmp_path / "toned", script=DIALOGUE, scenes=SCENES)
    result = run_build(project, extra_env={"FAKE_TTS_TONE": "1"})
    assert result.returncode == 0, result.stderr
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
    yield page
    page.close()


def capture(page, seconds):
    """shoot と mp4 と同じ撮影の手順（立ち絵の準備を待つシーク）で、ステージを撮る。"""
    from kataribe.shoot import seek_and_wait

    seek_and_wait(page, seconds)
    return page.locator("#kataribe-stage").screenshot()


def test_話している人の口だけが_音声の振幅に合わせて開き_話していない人は閉じている(toned):
    seek(toned, STARTS[1] + 0.05)  # ずんだもんが話している行の中ほど
    chars = by_speaker(toned)

    assert chars["ずんだもん"]["mouth"] == "2"
    assert "!mouth/*open" in chars["ずんだもん"]["layers"]
    assert chars["四国めたん"]["mouth"] == "0"


def test_口は時刻だけで決まり_撮影でも_開いた時刻と閉じた時刻で画像が変わる(toned):
    duration = toned.evaluate("document.getElementById('kataribe-audio').duration")
    speaking = capture(toned, STARTS[3] + 0.03)  # 最後の行の中ほど（ずんだもんの口が開いている）

    assert capture(toned, STARTS[0]) != speaking
    assert capture(toned, STARTS[3] + 0.03) == speaking  # 戻って撮り直しても同じ
    assert capture(toned, duration) != speaking  # 音声の終わりでは口が閉じる


FIND_BLINK = """speaker => {
    const timeline = JSON.parse(document.getElementById('kataribe-timeline').textContent);
    const cast = JSON.parse(document.getElementById('kataribe-cast').textContent);
    const entry = cast.find(c => c.speaker === speaker);
    const seed = KataribeCast.seedOf(speaker);
    const speakers = cast.map(c => c.speaker);
    for (let t = 0; t < timeline.duration; t += 0.01) {
        let index = 0;
        timeline.lines.forEach((line, i) => { if (line.start <= t) index = i; });
        const face = KataribeCast.facesAt(timeline.lines, index, speakers)[speaker];
        if (entry.faces[face].blink && KataribeCast.blinkClosed(t, seed) && KataribeCast.blinkClosed(t + 0.06, seed)) return t + 0.03;
    }
    return null;
}"""


def test_立ち絵は_時刻だけで決まる時刻にまばたきし_その間は閉じ目になる(browser, tmp_path):
    project = make_project(tmp_path / "slow", script=DIALOGUE, scenes=SCENES)
    assert run_build(project, extra_env={"FAKE_TTS_SECONDS_PER_CHAR": "0.5"}).returncode == 0  # 約 10 秒の動画
    page = browser.new_page()
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
    blink_at = page.evaluate(FIND_BLINK, "ずんだもん")
    assert blink_at is not None, "約 10 秒の間に、閉じ目のある表情でのまばたきが1回もない"

    seek(page, blink_at)
    blinking = by_speaker(page)["ずんだもん"]
    seek(page, blink_at - 0.5)
    open_eyes = by_speaker(page)["ずんだもん"]
    seek(page, blink_at)
    page_close_again = by_speaker(page)["ずんだもん"]
    page.close()

    assert blinking["blink"] == "1" and "!eye/*closed" in blinking["layers"]
    assert open_eyes["blink"] == "0" and "!eye/*closed" not in open_eyes["layers"]
    assert page_close_again == blinking  # 戻ってシークしても同じ


def test_話者が1人なら_立ち絵も1人だけ表示される(browser, project):
    assert run_build(project).returncode == 0
    page = browser.new_page()
    page.goto((project / "out" / "video.html").as_uri())

    assert [c["speaker"] for c in characters(page)] == ["ずんだもん"]
    page.close()


def test_定義にない表情は_lintが素材を取得せずに_場所と使える表情を示して失敗する(tmp_path, monkeypatch):
    env = fake_art_env(tmp_path / "art")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    script = json.loads(json.dumps(SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][1]["expression"] = "sleepy"
    project = make_project(tmp_path / "p", script=script)

    result = run_lint(project)

    assert result.returncode == 1
    assert "chapters[0].scenes[0].lines[1].expression「sleepy」" in result.stderr
    assert "使える表情: normal, smile, angry" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "art" / "cache").exists()


def test_定義で同じ側の2人は_後から出た人が反対側に立つ(browser, tmp_path):
    # テスト用の定義では、ずんだもん以外は左。春日部つむぎ・雨晴はうはどちらも左になる
    lines = [{"speaker": "雨晴はう", "text": "はじめます"}, {"speaker": "春日部つむぎ", "text": "よろしくね"}]
    script = {"title": "掛け合い", "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": lines}]}]}
    project = make_project(tmp_path / "p", script=script, scenes=SCENES)
    assert run_build(project).returncode == 0
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto((project / "out" / "video.html").as_uri())

    chars = by_speaker(page)

    assert chars["雨晴はう"]["x"] < chars["春日部つむぎ"]["x"]
    page.close()
