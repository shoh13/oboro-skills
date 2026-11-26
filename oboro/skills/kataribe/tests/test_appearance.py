import json

import pytest
from conftest import SCRIPT, make_project, run_build, seek

# s1 は4行、各行 5 字 = 0.10 秒。行の開始は 0、0.10、0.20、0.30。s2 は1行（0.40〜0.50）。
LINE_TIMES = [0.05, 0.15, 0.25, 0.35]
SCRIPT_4 = {
    **SCRIPT,
    "chapters": [
        {"id": "c1", "title": "章1", "scenes": [{"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "あああああ"}, {"speaker": "ずんだもん", "text": "いいいいい"}, {"speaker": "ずんだもん", "text": "ううううう"}, {"speaker": "ずんだもん", "text": "えええええ"}]}]},
        {"id": "c2", "title": "章2", "scenes": [{"id": "s2", "lines": [{"speaker": "ずんだもん", "text": "おおおおお"}]}]},
    ],
}


def open_scenes(browser, tmp_path, scenes_html: str, name: str = "p"):
    project = make_project(tmp_path / name, script=SCRIPT_4, scenes=scenes_html)
    result = run_build(project)
    assert result.returncode == 0, result.stderr
    page = browser.new_page()
    page.set_default_timeout(5000)
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
    return page


def visibility(page, selector: str) -> str:
    return page.eval_on_selector(selector, "e => getComputedStyle(e).visibility")


APPEAR_SCENES = """\
<section data-scene="s1">
  <p id="always">いつも</p>
  <p id="at1" data-at="1">1行目から</p>
  <p id="out2" data-out="2">2行目で消える</p>
  <p id="win" data-at="1" data-out="3">1行目から3行目の前まで</p>
  <div id="stack"><p id="before" data-out="2">前</p><p id="after" data-at="2">後</p></div>
</section>
<section data-scene="s2"><p>別のシーン</p></section>
"""

# 行ごとの表示（V=見える、H=見えない）。仕様 R13 の規則から手で導いた期待値
EXPECTED = {
    "#always": "VVVV",
    "#at1": "HVVV",
    "#out2": "VVHH",
    "#win": "HVVH",
    "#before": "VVHH",
    "#after": "HHVV",
}


@pytest.mark.parametrize("line", range(4))
def test_data_atとdata_outは_シーン内の行番号に合わせて要素を出し入れする(browser, tmp_path, line):
    page = open_scenes(browser, tmp_path, APPEAR_SCENES)
    seek(page, LINE_TIMES[line])

    for selector, pattern in EXPECTED.items():
        expected = "visible" if pattern[line] == "V" else "hidden"
        assert visibility(page, selector) == expected, f"{selector} の {line} 行目"
    page.close()


def test_消えた要素も場所を残し_周りの要素は動かない(browser, tmp_path):
    page = open_scenes(browser, tmp_path, APPEAR_SCENES)
    boxes = []
    for time in LINE_TIMES:
        seek(page, time)
        boxes.append({selector: page.eval_on_selector(selector, "e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }") for selector in EXPECTED})

    for selector in EXPECTED:
        assert boxes[0][selector] == boxes[1][selector] == boxes[2][selector] == boxes[3][selector], selector
        assert boxes[0][selector][2] > 0 and boxes[0][selector][3] > 0
    page.close()


def test_どの時刻へシークしても_見た目は時刻だけで決まる(browser, tmp_path):
    page = open_scenes(browser, tmp_path, APPEAR_SCENES)

    def snapshot():
        return {selector: visibility(page, selector) for selector in EXPECTED}

    seek(page, 0.35)
    seek(page, 0.05)
    first = snapshot()
    seek(page, 0.25)
    seek(page, 0.15)
    seek(page, 0.05)

    assert snapshot() == first
    page.close()


FOCUS_SCENES = """\
<section data-scene="s1">
  <ul id="g1">
    <li id="f1" data-focus="0">A</li>
    <li id="f2" data-focus="2, 3">B</li>
    <li id="f3" data-focus="3">C</li>
    <li id="plain">D</li>
  </ul>
  <ul id="g2"><li id="h1" data-focus="1">E</li><li id="h2" data-focus="2">F</li></ul>
</section>
<section data-scene="s2"><p>別のシーン</p></section>
"""

# 行ごとの強調の状態（A=強調、D=薄める、-=状態なし）。仕様 R13 から手で導いた期待値。
# g1: f1={0}、f2={2,3}、f3={3} のうち、その行を指す要素がいれば、その要素を強調し、同じ親の他の data-focus 要素を薄める。
#     誰も指していない行（1行目）は、全員が状態なし。plain は data-focus を持たないので、いつも状態なし。
# g2: h1={1}、h2={2}。g1 とは親が違うので、互いに影響しない。
FOCUS_EXPECTED = {
    "#f1": "A-DD",
    "#f2": "D-AA",
    "#f3": "D-DA",
    "#plain": "----",
    "#h1": "-AD-",
    "#h2": "-DA-",
}


def focus_state(page, selector: str) -> str:
    return {None: "-", "active": "A", "dim": "D"}[page.eval_on_selector(selector, "e => e.getAttribute('data-kataribe-focus-state')")]


@pytest.mark.parametrize("line", range(4))
def test_data_focusは_指定した行で対象に目印を付け_同じ親の兄弟を薄める(browser, tmp_path, line):
    page = open_scenes(browser, tmp_path, FOCUS_SCENES)
    seek(page, LINE_TIMES[line])

    for selector, pattern in FOCUS_EXPECTED.items():
        assert focus_state(page, selector) == pattern[line], f"{selector} の {line} 行目"
    page.close()


def test_強調の見た目は_強調中は輪郭の目印が付き_薄める要素は透明度が下がる(browser, tmp_path):
    page = open_scenes(browser, tmp_path, FOCUS_SCENES)

    def look(selector: str) -> dict:
        return page.eval_on_selector(selector, "e => { const s = getComputedStyle(e); return {outline: s.outlineStyle, opacity: Number(s.opacity)}; }")

    seek(page, LINE_TIMES[2])  # f2 を強調し、f1・f3 を薄める
    assert look("#f2")["outline"] != "none" and look("#f2")["opacity"] == 1
    assert look("#f1")["outline"] == "none" and look("#f1")["opacity"] < 1
    assert look("#f3")["opacity"] < 1

    seek(page, LINE_TIMES[1])  # g1 は誰も指さない行
    for selector in ("#f1", "#f2", "#f3", "#plain"):
        assert look(selector) == {"outline": "none", "opacity": 1}
    page.close()


def progress(page, scene: str) -> dict[str, float]:
    return page.eval_on_selector(
        f"section[data-scene='{scene}']",
        "e => { const s = getComputedStyle(e); return {p: parseFloat(s.getPropertyValue('--p')), lp: parseFloat(s.getPropertyValue('--lp')), gp: parseFloat(s.getPropertyValue('--gp'))}; }",
    )


PLAIN_SCENES = '<section data-scene="s1"><p>一</p></section><section data-scene="s2"><p>二</p></section>'


@pytest.mark.parametrize(
    "time, scene, p, lp",
    [
        (0.15, "s1", 0.375, 0.5),   # s1 は 0〜0.40。0.15 は、2行目（0.10〜0.20）の半ば
        (0.35, "s1", 0.875, 0.5),   # 4行目（0.30〜0.40）の半ば
        (0.45, "s2", 0.5, 0.5),     # s2 は 0.40〜0.50
    ],
)
def test_進行変数は_シーンと現在の行の進み具合を0から1で表す(browser, tmp_path, time, scene, p, lp):
    page = open_scenes(browser, tmp_path, PLAIN_SCENES)
    seek(page, time)

    values = progress(page, scene)

    assert values["p"] == pytest.approx(p, abs=0.03)
    assert values["lp"] == pytest.approx(lp, abs=0.1)
    page.close()


def test_現在のシーンより前のシーンは_1_後のシーンは_0になる(browser, tmp_path):
    page = open_scenes(browser, tmp_path, PLAIN_SCENES)

    seek(page, 0.45)
    assert progress(page, "s1") == {"p": 1, "lp": 1, "gp": 0}

    seek(page, 0.05)
    assert progress(page, "s2") == {"p": 0, "lp": 0, "gp": 0}
    page.close()


def test_行後の間の進行は_行の間に無音がないので_いつも0(browser, tmp_path):
    page = open_scenes(browser, tmp_path, PLAIN_SCENES)

    for time in (0.0, 0.05, 0.1, 0.25, 0.39, 0.45):
        seek(page, time)
        assert progress(page, "s1")["gp"] == 0
        assert progress(page, "s2")["gp"] == 0
    page.close()


def test_シーンの進行変数は_時間とともに減らず_0から1の範囲に収まる(browser, tmp_path):
    page = open_scenes(browser, tmp_path, PLAIN_SCENES)

    previous = {"s1": 0.0, "s2": 0.0}
    for step in range(0, 51, 5):
        seek(page, step / 100)
        for scene in previous:
            values = progress(page, scene)
            assert 0 <= values["p"] <= 1 and 0 <= values["lp"] <= 1
            assert values["p"] >= previous[scene] - 1e-9
            previous[scene] = values["p"]
    page.close()


def test_作者が同じ名前の属性を使っていても_プレーヤーは作者の属性を上書きも削除もしない(browser, tmp_path):
    scenes = (
        '<section data-scene="s1">'
        '<ul><li id="mine" data-state="mine" data-focus-state="theirs" data-at="1" data-focus="1">A</li>'
        '<li id="other" data-state="other" data-focus="2">B</li></ul>'
        "</section>"
        '<section data-scene="s2"></section>'
    )
    page = open_scenes(browser, tmp_path, scenes)

    def attributes(selector: str) -> dict:
        return page.eval_on_selector(selector, "e => ({state: e.getAttribute('data-state'), focus: e.getAttribute('data-focus-state')})")

    for time in LINE_TIMES:
        seek(page, time)
        assert attributes("#mine") == {"state": "mine", "focus": "theirs"}
        assert attributes("#other")["state"] == "other"
    page.close()
