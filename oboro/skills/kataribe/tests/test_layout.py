from kataribe.layout import Box, Mask, Rect, layout_problems

STAGE = Rect(0, 0, 1280, 720)


def box(rect, *, scene="s1", line=0, element=1, chain=(0, 1), label="<div.k-card>", text=False, clip=None):
    return Box(scene, line, element, chain, label, Rect(*rect), text, clip)


def mask(rows, *, left=1000, top=400, scene="s1", line=0, speaker="ずんだもん"):
    # 区画は4px四方。rows の1文字が1区画
    return Mask(scene, line, speaker, left, top, 4, tuple(rows))


def test_ステージの内側にあり立ち絵に重ならない要素は問題にしない():
    masks = [mask(["11", "11"])]

    assert layout_problems([box((100, 100, 900, 600))], STAGE, masks) == []


def test_ステージの外にはみ出した辺とpxを示す():
    problems = layout_problems([box((1200, 650, 1298, 730), label="<div.k-shelf>")], STAGE, [])

    assert problems == [
        "s1 の 0行目: <div.k-shelf> が、ステージの下に 10px はみ出しています",
        "s1 の 0行目: <div.k-shelf> が、ステージの右に 18px はみ出しています",
    ]


def test_1px以内のはみ出しは問題にしない():
    assert layout_problems([box((-1, 0, 1281, 721))], STAGE, []) == []


def test_立ち絵の不透明な区画と重なると話者と区画の数を示す():
    # 立ち絵の右半分の4区画（x 1008〜1016、y 400〜408）が不透明
    masks = [mask(["0011", "0011"])]
    problems = layout_problems([box((900, 300, 1020, 420), label="<div.k-card「Cassandra／Riak」>")], STAGE, masks)

    assert problems == ["s1 の 0行目: <div.k-card「Cassandra／Riak」> が、立ち絵（ずんだもん）と重なっています（4 区画）"]


def test_立ち絵のcanvasの透明な部分にだけ重なる要素は問題にしない():
    masks = [mask(["0011", "0011"])]

    assert layout_problems([box((900, 300, 1008, 420))], STAGE, masks) == []


def test_ステージの外にある立ち絵の区画は重なりに数えない():
    # 立ち絵の canvas はステージの下端を越えて伸びる。ステージの外の区画は見えない
    masks = [mask(["0", "1"], top=716)]
    problems = layout_problems([box((990, 650, 1010, 730))], STAGE, masks)

    assert problems == ["s1 の 0行目: <div.k-card> が、ステージの下に 10px はみ出しています"]


def test_祖先のoverflowで切られて見えない部分は数えない():
    clipped = box((1200, 100, 1400, 200), clip=Rect(1000, 0, 1270, 720))

    assert layout_problems([clipped], STAGE, []) == []


def test_同じ要素の同じ問題はシーンごとに1回だけ最も大きい行で示す():
    boxes = [
        box((1200, 100, 1290, 200), line=3),
        box((1200, 100, 1310, 200), line=7),
        box((1200, 100, 1310, 200), line=9),
        box((1200, 100, 1290, 200), scene="s2", line=1),
    ]

    assert layout_problems(boxes, STAGE, []) == [
        "s1 の 7行目: <div.k-card> が、ステージの右に 30px はみ出しています",
        "s2 の 1行目: <div.k-card> が、ステージの右に 10px はみ出しています",
    ]


def test_入れ子の要素が同じ問題を持つときは最も内側の要素だけを示す():
    masks = [mask(["1111", "1111"], line=line) for line in (2, 5)]
    grid = dict(element=1, chain=(0, 1), label="<div.k-grid>")
    card = dict(element=2, chain=(0, 1, 2), label="<div.k-card>")
    boxes = [
        # 2行目はカードがまだ見えず、格子の背景だけが重なる。5行目はカードも重なる
        box((900, 300, 1100, 500), line=2, **grid),
        box((900, 300, 1100, 500), line=5, **grid),
        box((950, 350, 1004, 500), line=5, **card),
    ]

    assert layout_problems(boxes, STAGE, masks) == [
        "s1 の 5行目: <div.k-card> が、立ち絵（ずんだもん）と重なっています（2 区画）"
    ]


def test_文字は背景か枠のある最も内側の祖先の要素として示す():
    # <span.k-card><b>MD5</b>: Cassandra</span> の、<b> の中の文字がはみ出す
    boxes = [
        box((1100, 100, 1279, 130), element=2, chain=(0, 1, 2), label="<span.k-card「MD5: Cassandra」>"),
        box((1250, 105, 1300, 125), element=3, chain=(0, 1, 2, 3), label="<b「MD5」>", text=True),
    ]

    assert layout_problems(boxes, STAGE, []) == [
        "s1 の 0行目: <span.k-card「MD5: Cassandra」> が、ステージの右に 20px はみ出しています"
    ]


def test_背景も枠もない要素の文字は親の要素として示す():
    boxes = [box((1250, 105, 1300, 125), element=3, chain=(0, 1, 3), label="<p「長い説明」>", text=True)]

    assert layout_problems(boxes, STAGE, []) == ["s1 の 0行目: <p「長い説明」> が、ステージの右に 20px はみ出しています"]
