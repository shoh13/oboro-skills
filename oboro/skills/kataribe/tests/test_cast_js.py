"""player/cast.js の純粋な関数を、ブラウザで直接呼んで検査する（build も再生もしない）。"""
from pathlib import Path

import pytest

CAST_JS = (Path(__file__).resolve().parents[1] / "src" / "kataribe" / "player" / "cast.js").read_text(encoding="utf-8")
SPEAKERS = ["四国めたん", "ずんだもん"]
LINES = [
    {"speaker": "四国めたん", "expression": None},
    {"speaker": "ずんだもん", "expression": "smile"},
    {"speaker": "四国めたん", "expression": "angry"},
    {"speaker": "ずんだもん", "expression": None},
]


@pytest.fixture
def js(browser):
    page = browser.new_page()
    page.set_content(f"<!doctype html><script>{CAST_JS}</script>")
    yield page
    page.close()


def call(page, name, *args):
    return page.evaluate(f"(args) => window.KataribeCast.{name}(...args)", list(args))


@pytest.mark.parametrize(
    "index, expected",
    [
        (0, {"四国めたん": "normal", "ずんだもん": "normal"}),  # まだ話していない人は既定の表情
        (1, {"四国めたん": "normal", "ずんだもん": "smile"}),
        (2, {"四国めたん": "angry", "ずんだもん": "smile"}),  # 話していない人は最後に話した行の表情のまま
        (3, {"四国めたん": "angry", "ずんだもん": "normal"}),  # 話している人は、表情の省略で既定の表情
    ],
)
def test_話している人はその行の表情_話していない人は最後に話した行の表情になる(js, index, expected):
    assert call(js, "facesAt", LINES, index, SPEAKERS) == expected


ENTRY = {
    "base": ["!body"],
    "faces": {
        "normal": {"layers": ["!brow/*basic", "!eye/*basic"], "mouth": ["!mouth/*closed", "!mouth/*half", "!mouth/*open"]},
        "smile": {"layers": ["!brow/*up", "!eye/*basic"], "mouth": ["!mouth/*grin", "!mouth/*half", "!mouth/*open"]},
    },
    # キーの順が重ねる順（下から上）
    "layers": {p: {} for p in ["!body", "!mouth/*closed", "!brow/*basic", "!brow/*up", "!eye/*basic", "!mouth/*grin", "!mouth/*half", "!mouth/*open"]},
}


def test_表示するレイヤーは_体と表情のレイヤーと口の段階のレイヤーを重ねる順に並べる(js):
    assert call(js, "activeLayers", ENTRY, "normal", 0) == ["!body", "!mouth/*closed", "!brow/*basic", "!eye/*basic"]
    assert call(js, "activeLayers", ENTRY, "smile", 0) == ["!body", "!brow/*up", "!eye/*basic", "!mouth/*grin"]
    assert call(js, "activeLayers", ENTRY, "smile", 2) == ["!body", "!brow/*up", "!eye/*basic", "!mouth/*open"]


BLINK_ENTRY = {
    "base": ["!body"],
    "faces": {
        "normal": {"layers": ["!brow/*basic", "!eye/*basic"], "mouth": ["m0", "m1", "m2"], "blink": "!eye/*closed"},
        "smile": {"layers": ["!brow/*up", "!eye/*smile"], "mouth": ["m0", "m1", "m2"], "blink": None},
    },
    "layers": {p: {} for p in ["!body", "!brow/*basic", "!brow/*up", "!eye/*basic", "!eye/*smile", "!eye/*closed", "m0", "m1", "m2"]},
}


def blink_spans(page, seed: int, seconds: float, step: float = 0.01) -> list[tuple[float, float]]:
    """0〜seconds 秒で、目を閉じている区間の一覧（step 刻みで調べる）。"""
    return page.evaluate(
        """([seed, seconds, step]) => {
            const spans = [];
            let start = null;
            for (let i = 0; i * step <= seconds; i++) {
                const t = i * step, closed = window.KataribeCast.blinkClosed(t, seed);
                if (closed && start === null) start = t;
                if (!closed && start !== null) { spans.push([start, t]); start = null; }
            }
            return spans;
        }""",
        [seed, seconds, step],
    )


def test_まばたきは_4秒ごとの区間に1回_0_12秒だけ目を閉じる(js):
    spans = blink_spans(js, 7, 40.0)

    assert 9 <= len(spans) <= 11  # 40 秒でおよそ 10 回（区間の境目の位置で前後する）
    for start, end in spans:
        assert end - start == pytest.approx(0.12, abs=0.011)
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert start - end > 0.5  # 続けて閉じない


def test_まばたきの時刻は_時刻と話者だけで決まり_話者が違えば時刻も違う(js):
    assert blink_spans(js, 7, 20.0) == blink_spans(js, 7, 20.0)
    assert blink_spans(js, 7, 20.0) != blink_spans(js, 8, 20.0)
    zundamon, metan = call(js, "seedOf", "ずんだもん"), call(js, "seedOf", "四国めたん")
    assert zundamon == call(js, "seedOf", "ずんだもん") and zundamon != metan


def test_まばたき中は_表情の目のレイヤーを閉じ目に替え_閉じ目のない表情は替えない(js):
    assert call(js, "activeLayers", BLINK_ENTRY, "normal", 0, True) == ["!body", "!brow/*basic", "!eye/*closed", "m0"]
    assert call(js, "activeLayers", BLINK_ENTRY, "normal", 0, False) == ["!body", "!brow/*basic", "!eye/*basic", "m0"]
    assert call(js, "activeLayers", BLINK_ENTRY, "smile", 0, True) == ["!body", "!brow/*up", "!eye/*smile", "m0"]


MOUTH_LINE = {"start": 1.0, "end": 2.0, "mouth": "0122"}


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0.99, 0),  # 行の前は閉じる
        (1.0, 0),
        (1.04, 1),  # 1/30 秒ごとの文字を引く
        (1.07, 2),
        (1.12, 2),
        (1.5, 0),  # 文字列の後は閉じる
        (2.0, 0),  # 行の終わりからは閉じる
    ],
)
def test_口の段階は_行の開始からの時刻で文字列を引いて決まる(js, seconds, expected):
    assert call(js, "mouthLevel", MOUTH_LINE, seconds) == expected


@pytest.mark.parametrize(
    "side, facing, expected",
    [("left", "left", True), ("right", "left", False), ("left", "right", False), ("right", "right", True)],
)
def test_立ち絵は画面の中央を向くように_外向きなら左右を反転する(js, side, facing, expected):
    assert call(js, "mirrored", side, facing) is expected
