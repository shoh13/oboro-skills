import json
import shutil
import subprocess

import pytest

from kataribe.layout import HELPERS, MEASURE

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node がない")


def run_node(script: str, source: str) -> object:
    """source を標準入力から読み、script の最後の式を JSON で返す。"""
    assert NODE is not None
    done = subprocess.run([NODE, "-e", script], input=source, capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def call_helpers(expression: str) -> object:
    script = f"const helpers = require('fs').readFileSync(0, 'utf8'); console.log(JSON.stringify(new Function(helpers + '; return ' + {json.dumps(expression)})()));"
    return run_node(script, HELPERS)


def test_測る関数は構文として正しい関数式である():
    script = "const source = require('fs').readFileSync(0, 'utf8'); console.log(JSON.stringify(typeof new Function('return (' + source + ')')()));"

    assert run_node(script, MEASURE) == "function"


def test_計算後の色の書き方ごとに不透明度を読む():
    colors = [
        "rgba(0, 0, 0, 0)",
        "rgba(127, 127, 127, 0.1)",
        "rgb(28, 28, 28)",
        "rgb(1 2 3 / 0.5)",
        "color(srgb 1 0 0 / 25%)",
        "oklch(0.5 0.1 200)",
        "transparent",
    ]

    assert call_helpers(f"{json.dumps(colors)}.map(colorAlpha)") == [0, 0.1, 1, 0.5, 0.25, 1, 0]


def test_立ち絵の画素を区画ごとの不透明の有無にまとめる():
    # 8x8 の canvas（CSS も 8x8）に、(5, 1) のアルファ200の画素と、(1, 6) のアルファ100の画素だけがある
    expression = """(() => {
      const data = new Uint8ClampedArray(8 * 8 * 4);
      data[(1 * 8 + 5) * 4 + 3] = 200;
      data[(6 * 8 + 1) * 4 + 3] = 100;
      return maskRows(data, 8, 8, 8, 8, 4, 128);
    })()"""

    assert call_helpers(expression) == ["01", "00"]


def test_devicePixelRatioで拡大したcanvasはCSSのpxの区画に戻す():
    # 16x16 の canvas を CSS で 8x8 に表示する。canvas の (10, 2) は CSS の (5, 1)
    expression = """(() => {
      const data = new Uint8ClampedArray(16 * 16 * 4);
      data[(2 * 16 + 10) * 4 + 3] = 255;
      return maskRows(data, 16, 16, 8, 8, 4, 128);
    })()"""

    assert call_helpers(expression) == ["01", "00"]


def test_要素の名前はタグとidとクラスと先頭の文字で示す():
    expression = """[
      label('div', '', ['k-card', 'k-good'], '  Cassandra／Riak:\\n  ゴシップで広める仕組み ', 18),
      label('div', 'shelf', ['k-shelf'], '   ', 18),
      label('span', '', [], '短い', 18),
    ]"""

    assert call_helpers(expression) == [
        "<div.k-card.k-good「Cassandra／Riak: ゴシ…」>",
        "<div#shelf.k-shelf>",
        "<span「短い」>",
    ]
