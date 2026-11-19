from kataribe.verify import check_appearance

INF = float("inf")

# シーン s1 の4行（0〜3）。各行 1 秒。
TIMELINE = {
    "lines": [{"id": f"s1-{i}", "scene": "s1", "start": float(i), "end": float(i + 1)} for i in range(4)],
}


def samples_for(visibilities: list[list[str]]) -> list[dict]:
    """行ごとの、要素の visibility の並び → 各行の中ほどのサンプル。"""
    return [{"t": i + 0.5, "scene": "s1", "vis": vis} for i, vis in enumerate(visibilities)]


def test_祖先がdata_outで消えたあとは子も消えているのが正しい():
    # 親: data-out="2"（0〜1行目）。子: data-at="1"、data-out なし。2行目以降は親とともに消える
    elements = {"s1": [(0, 2), (1, INF)]}
    ancestors = {"s1": [[], [(0, 2)]]}
    observed = samples_for([["visible", "hidden"], ["visible", "visible"], ["hidden", "hidden"], ["hidden", "hidden"]])

    check = check_appearance(observed, TIMELINE, elements, ancestors)

    assert check.ok, check.problems


def test_祖先が見えている行で子が消えていればNGになる():
    elements = {"s1": [(0, 2), (1, INF)]}
    ancestors = {"s1": [[], [(0, 2)]]}
    observed = samples_for([["visible", "hidden"], ["visible", "hidden"], ["hidden", "hidden"], ["hidden", "hidden"]])

    check = check_appearance(observed, TIMELINE, elements, ancestors)

    assert not check.ok
    assert "行 s1-1" in check.problems[0]


def test_祖先がまだ出ていない行では子のdata_atが来ていても消えている():
    # 親: data-at="2"。子: data-at="1"。1行目は親が出ていないので子も消える
    elements = {"s1": [(2, INF), (1, INF)]}
    ancestors = {"s1": [[], [(2, INF)]]}
    observed = samples_for([["hidden", "hidden"], ["hidden", "hidden"], ["visible", "visible"], ["visible", "visible"]])

    assert check_appearance(observed, TIMELINE, elements, ancestors).ok


def test_祖先の情報を渡さなければ要素自身の区間だけで判定する():
    elements = {"s1": [(1, 3)]}
    observed = samples_for([["hidden"], ["visible"], ["visible"], ["hidden"]])

    assert check_appearance(observed, TIMELINE, elements).ok
