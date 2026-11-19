import pytest

from kataribe.shoot import _reset_line_frames, change_lines, full_lines, line_capture_times

INF = float("inf")


def test_changesは表示か強調が変わる行だけを撮る():
    # 要素A: 0〜1行目。要素B: 3行目から。2行目と4行目は何も変わらない。5行目は強調が始まる
    elements = [(0, 2), (3, INF)]
    focus = [[5]]

    assert change_lines(elements, [[], []], focus, 7) == [0, 2, 3, 5, 6]


def test_祖先が消えている間の子の変化は見た目の変化に数えない():
    # 親: 0〜1行目。子: data-at="2"（親が消えたあとなので一度も見えない）
    elements = [(0, 2), (2, INF)]
    ancestors = [[], [(0, 2)]]

    assert change_lines(elements, ancestors, [], 4) == [0, 2]


def test_要素のないシーンは先頭の行だけを撮る():
    assert change_lines([], [], [], 3) == [0]


def test_fullは要素が消える直前の行と最後の行を撮る():
    # パネルA: 0〜3行目（中の子は1行目から）。パネルB: 4行目から（中の子は6行目から）
    elements = [(0, 4), (1, INF), (4, INF), (6, INF)]
    ancestors = [[], [(0, 4)], [], [(4, INF)]]

    assert full_lines(elements, ancestors, 8) == [3, 7]


def test_fullは要素のないシーンでは最後の行だけを撮る():
    assert full_lines([], [], 5) == [4]


def test_画像の名前と撮る時刻():
    timeline = {
        "scenes": [{"id": "s1"}, {"id": "s2"}],
        "lines": [
            {"scene": "s1", "start": 0.0, "end": 2.0},
            {"scene": "s1", "start": 2.0, "end": 2.4},
            {"scene": "s2", "start": 2.4, "end": 5.0},
        ],
    }
    jobs = line_capture_times(timeline, "changes", {"s1": [(1, INF)]}, {"s1": [[]]}, {})

    # 短い行（0.4秒）は、その行の中央を撮る
    assert [name for name, _ in jobs] == ["s1-line00.png", "s1-line01.png", "s2-line00.png"]
    assert [seconds for _, seconds in jobs] == pytest.approx([0.3, 2.2, 2.7])


def test_行ごとの画像の置き場所は撮るたびに前回の画像を消す(tmp_path):
    target = tmp_path / "frames" / "full"
    target.mkdir(parents=True)
    (target / "s1-line07.png").write_bytes(b"")
    (target / "notes.txt").write_text("keep", encoding="utf-8")

    _reset_line_frames(target)

    assert sorted(path.name for path in target.iterdir()) == ["notes.txt"]
