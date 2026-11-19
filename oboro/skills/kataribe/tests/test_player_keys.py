import json
import shutil
import subprocess
from importlib import resources

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node がありません")

KEYS_JS = resources.files("kataribe") / "player" / "keys.js"

RUNNER = """
const window = {};
require("vm").runInNewContext(require("fs").readFileSync(process.argv[1], "utf8"), { window });
const calls = JSON.parse(process.argv[2]);
const run = ([name, args]) => (typeof window.KataribeKeys[name] === "function" ? window.KataribeKeys[name](...args) : window.KataribeKeys[name]);
process.stdout.write(JSON.stringify(calls.map((c) => run(c) ?? null)));
"""

BODY = {"tagName": "BODY"}
BUTTON = {"tagName": "BUTTON"}
LINK = {"tagName": "A"}
SEEK_BAR = {"tagName": "INPUT", "id": "kataribe-seek-bar"}
TEXT_INPUT = {"tagName": "INPUT"}
TEXTAREA = {"tagName": "TEXTAREA"}
RATE_SELECT = {"tagName": "SELECT", "id": "kataribe-rate"}
EDITABLE = {"tagName": "DIV", "isContentEditable": True}


def call(*calls):
    result = subprocess.run(
        [NODE, "-e", RUNNER, str(KEYS_JS), json.dumps([[name, list(args)] for name, *args in calls])],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def press(*keys, target=BODY, list_open=False, **modifiers):
    """押したときの操作の並び（キーを奪わないときは None）。"""
    results = call(*[("decide", {"key": key, "target": target, **modifiers}, list_open) for key in keys])
    return [binding and binding["action"] for binding in results]


def test_表のキーはそれぞれの操作になる():
    keys = [" ", "k", "j", "l", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "0", "9", "[", "]", "c", "t", "?"]

    assert press(*keys) == [
        "play", "play", "back", "forward", "prev-line", "next-line", "prev-chapter", "next-chapter",
        "first", "last", "percent", "percent", "slower", "faster", "captions", "transcript", "keys",
    ]


def test_英字は大文字でもShiftがなければ同じ操作になる():
    assert press("K", "J", "C", "T") == ["play", "back", "captions", "transcript"]


def test_Shiftつきは疑問符のほかはキーを奪わない():
    assert press("K", "k", "ArrowLeft", " ", "1", "[", shiftKey=True) == [None] * 6
    assert press("?", shiftKey=True) == ["keys"]


def test_CtrlとMetaとAltつきはキーを奪わない():
    for modifier in ("ctrlKey", "metaKey", "altKey"):
        assert press("k", "ArrowLeft", " ", "?", **{modifier: True}) == [None] * 4


def test_入力欄と再生速度の選択にフォーカスがあるときはキーを奪わない():
    for target in (TEXT_INPUT, TEXTAREA, RATE_SELECT, EDITABLE):
        assert press("k", " ", "ArrowLeft", "ArrowDown", "?", target=target) == [None] * 5


def test_再生位置のバーでは左右の矢印だけを行の移動にする():
    assert press("ArrowLeft", "ArrowRight", target=SEEK_BAR) == ["prev-line", "next-line"]
    assert press(" ", "k", "ArrowUp", "Home", "5", target=SEEK_BAR) == [None] * 5


def test_ボタンとリンクではSpaceを奪わずに本来の押下にする():
    assert press(" ", target=BUTTON) == [None]
    assert press(" ", target=LINK) == [None]


def test_ボタンにフォーカスがあってもSpace以外のキーは操作になる():
    assert press("k", "ArrowRight", "c", target=BUTTON) == ["play", "next-line", "captions"]


def test_キー一覧が開いている間は疑問符だけを受ける():
    assert press("?", target=BUTTON, list_open=True) == ["keys"]
    assert press("k", " ", "ArrowLeft", "Escape", target=BUTTON, list_open=True) == [None] * 4


def test_表にないキーとkeyのないイベントは奪わない():
    assert press("Escape", "Enter", "x", "Tab", "PageDown") == [None] * 5
    assert call(("decide", {"target": BODY})) == [None]


def test_押し続けて繰り返すのは移動と再生速度の操作だけ():
    (bindings,) = call(("BINDINGS",))

    assert {b["action"] for b in bindings if b.get("repeat")} == {
        "back", "forward", "prev-line", "next-line", "prev-chapter", "next-chapter", "slower", "faster",
    }


def test_キー一覧に出す名前():
    names = call(
        ("keyNames", {"keys": [" ", "k"]}),
        ("keyNames", {"keys": ["ArrowLeft"]}),
        ("keyNames", {"keys": ["Home"]}),
        ("keyNames", {"keys": ["0", "1"], "names": ["0–9"]}),
    )

    assert names == [["Space", "K"], ["←"], ["Home"], ["0–9"]]


def test_ボタンのaria_keyshortcutsの値():
    assert call(("ariaShortcuts", ["play"]), ("ariaShortcuts", ["slower", "faster"]), ("ariaShortcuts", ["prev-line"])) == [
        "Space K",
        "[ ]",
        "ArrowLeft",
    ]


CHAPTERS = [{"start": 0.0}, {"start": 10.0}, {"start": 20.0}]


def test_上矢印は章の先頭から2秒を過ぎていればその章の先頭へ_2秒以内なら前の章の先頭へ():
    assert call(
        ("chapterStart", CHAPTERS, 1, 12.5, -1),
        ("chapterStart", CHAPTERS, 1, 11.5, -1),
        ("chapterStart", CHAPTERS, 0, 1.0, -1),
        ("chapterStart", CHAPTERS, 0, 5.0, -1),
    ) == [10.0, 0.0, 0.0, 0.0]


def test_下矢印は次の章の先頭へ_最後の章では動かない():
    assert call(("chapterStart", CHAPTERS, 0, 3.0, 1), ("chapterStart", CHAPTERS, 2, 21.0, 1)) == [10.0, None]
