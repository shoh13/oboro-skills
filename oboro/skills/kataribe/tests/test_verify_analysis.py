from kataribe.verify import (
    check_appearance,
    check_captions,
    check_counts,
    check_played,
    check_progress,
    check_scenes,
)

# s1 は2行（0〜1秒、1〜2秒）、s2 は1行（2〜3秒）
TIMELINE = {
    "duration": 3.0,
    "chapters": [{"id": "c1", "title": "章", "start": 0.0, "end": 3.0}],
    "scenes": [{"id": "s1", "start": 0.0, "end": 2.0}, {"id": "s2", "start": 2.0, "end": 3.0}],
    "lines": [
        {"id": "s1-0", "chapter": "c1", "scene": "s1", "text": "一", "start": 0.0, "end": 1.0},
        {"id": "s1-1", "chapter": "c1", "scene": "s1", "text": "二", "start": 1.0, "end": 2.0},
        {"id": "s2-0", "chapter": "c1", "scene": "s2", "text": "三", "start": 2.0, "end": 3.0},
    ],
}


def sample(t, caption="", scene: str | None = "s1", progress=None, vis=()):
    return {"t": t, "caption": caption, "scene": scene, "progress": progress or {}, "vis": list(vis)}


def good_samples():
    out = []
    for i in range(0, 300, 5):
        t = i / 100
        line = next(l for l in reversed(TIMELINE["lines"]) if l["start"] <= t) if t < 3 else TIMELINE["lines"][-1]
        out.append(sample(t, line["text"], line["scene"]))
    return out


def test_最後まで進んだら項目1はOK_進まなければNGで理由に再生位置が出る():
    assert check_played(True, 3.0, 13.0).ok
    result = check_played(False, 1.234, 13.0)
    assert not result.ok
    assert "1.2" in result.problems[0]


def test_表示中のシーンの列が台本の順なら項目2はOK_連続する重複と空は無視される():
    samples = [sample(0, scene="s1"), sample(0.1, scene="s1"), sample(0.2, scene=None), sample(2.1, scene="s2")]
    assert check_scenes(samples, TIMELINE).ok


def test_シーンが飛ぶ_戻る_欠けると項目2はNGになる():
    assert not check_scenes([sample(0, scene="s1")], TIMELINE).ok
    assert not check_scenes([sample(0, scene="s1"), sample(1, scene="s2"), sample(2, scene="s1")], TIMELINE).ok


def test_字幕が行の時間帯の前後0_3秒以内の行の文と一致すれば項目3はOK():
    assert check_captions(good_samples(), TIMELINE).ok
    # t=1.2 は行s1-1（1〜2秒）の中。字幕が前の行「一」でも、0.3秒以内に s1-0 の時間帯（〜1.0+0.3）があるのでOK
    samples = good_samples() + [sample(1.2, "一")]
    assert check_captions(samples, TIMELINE).ok


def test_字幕が許容を超えてずれる_空_出ない行があると項目3はNGになる():
    assert not check_captions(good_samples() + [sample(1.5, "一")], TIMELINE).ok
    assert not check_captions(good_samples() + [sample(0.5, "")], TIMELINE).ok
    missing = [s for s in good_samples() if s["caption"] != "二"]
    result = check_captions(missing, TIMELINE)
    assert not result.ok
    assert "s1-1" in result.problems[0]


def test_章バーと文字起こしの数が台本と一致すれば項目4はOK():
    assert check_counts(chapters=2, transcript=5, expected_chapters=2, expected_lines=5).ok
    result = check_counts(chapters=1, transcript=4, expected_chapters=2, expected_lines=5)
    assert not result.ok
    assert len(result.problems) == 2


ELEMENTS = {"s1": [(1, float("inf")), (0, 1)], "s2": []}


def appear(t, scene, vis):
    return sample(t, scene=scene, vis=vis)


def test_各行の中ほどで_表示すべき要素が見え_消すべき要素が隠れていれば項目5はOK():
    samples = [
        appear(0.5, "s1", ["hidden", "visible"]),
        appear(1.5, "s1", ["visible", "hidden"]),
        appear(2.5, "s2", []),
    ]
    result = check_appearance(samples, TIMELINE, ELEMENTS)
    assert result.ok
    assert result.warnings == []


def test_期待と違う表示なら項目5はNGで_行と要素の番号が出る():
    result = check_appearance([appear(1.5, "s1", ["hidden", "hidden"])], TIMELINE, ELEMENTS)
    assert not result.ok
    assert "s1-1" in result.problems[0]


def test_行の端0_01秒以内のサンプルは項目5で使わない_サンプルのない行は検証できない行として警告():
    result = check_appearance([appear(1.005, "s1", ["hidden", "hidden"])], TIMELINE, ELEMENTS)
    assert result.ok
    assert any("s1-0" in w for w in result.warnings)
    assert any("s1-1" in w for w in result.warnings)


def test_要素のないシーンの行は警告しない_表示中のシーンが違うサンプルは項目5で無視する():
    result = check_appearance([appear(2.5, "s2", []), appear(0.5, "s2", [])], TIMELINE, ELEMENTS)
    assert not any("s2-0" in w for w in result.warnings)


def prog(p1, lp1=0.0, p2=0.0, lp2=0.0):
    return {"s1": [p1, lp1], "s2": [p2, lp2]}


def test_進行変数が0から1で_pが減らなければ項目6はOK():
    samples = [sample(0, progress=prog(0.0)), sample(1, progress=prog(0.5, 1.0)), sample(2, progress=prog(1.0, 1.0, 0.0))]
    assert check_progress(samples).ok


def test_範囲外_数値でない_pの減少は項目6でNGになる():
    assert not check_progress([sample(0, progress=prog(1.5))]).ok
    assert not check_progress([sample(0, progress=prog(0.1, -0.2))]).ok
    assert not check_progress([sample(0, progress={"s1": [None, 0.0]})]).ok
    decreasing = [sample(0, progress=prog(0.8)), sample(1, progress=prog(0.7))]
    result = check_progress(decreasing)
    assert not result.ok
    assert "s1" in result.problems[0]


def test_問題は最大5件まで保持され_超えた件数が分かる():
    samples = [sample(i, progress=prog(2.0)) for i in range(20)]
    result = check_progress(samples)
    assert len(result.problems) == 6
    assert "他" in result.problems[-1]


# ⑦ 立ち絵の表情と口。めたん（0〜1秒、口 "0222…"）→ ずんだもん smile（1〜2秒）→ めたん angry（2〜3秒）
CAST_TIMELINE = {
    **TIMELINE,
    "lines": [
        {**TIMELINE["lines"][0], "speaker": "四国めたん", "expression": None, "mouth": "0" + "2" * 29},
        {**TIMELINE["lines"][1], "speaker": "ずんだもん", "expression": "smile", "mouth": "1" * 30},
        {**TIMELINE["lines"][2], "speaker": "四国めたん", "expression": "angry", "mouth": ""},
    ],
}


def expected_cast(t):
    """台本どおりの立ち絵（話者、表情、口）。"""
    if t < 1.0:
        return [["四国めたん", "normal", "0" if t < 1 / 30 else "2"], ["ずんだもん", "normal", "0"]]
    if t < 2.0:
        return [["四国めたん", "normal", "0"], ["ずんだもん", "smile", "1"]]
    return [["四国めたん", "angry", "0"], ["ずんだもん", "smile", "0"]]


def cast_samples(override=None):
    out = []
    for i in range(0, 300, 5):
        t = i / 100
        item = sample(t)
        item["cast"] = override(t) if override and override(t) is not None else expected_cast(t)
        out.append(item)
    return out


def test_立ち絵の表情と口が台本と音声どおりなら項目7はOK():
    from kataribe.verify import check_characters

    result = check_characters(cast_samples(), CAST_TIMELINE)

    assert result.number == 7 and result.ok, result.problems


def test_表情が違うと項目7はNGで_時刻と話者と期待が出る():
    from kataribe.verify import check_characters

    wrong = lambda t: [["四国めたん", "normal", "0"], ["ずんだもん", "normal", "1"]] if 1.2 <= t < 1.8 else None
    result = check_characters(cast_samples(wrong), CAST_TIMELINE)

    assert not result.ok
    assert "1.20 秒" in result.problems[0] and "ずんだもん" in result.problems[0] and "smile" in result.problems[0]


def test_話していない人の口が開くと項目7はNGになる():
    from kataribe.verify import check_characters

    wrong = lambda t: [["四国めたん", "normal", "2"], ["ずんだもん", "smile", "1"]] if 1.2 <= t < 1.8 else None
    result = check_characters(cast_samples(wrong), CAST_TIMELINE)

    assert not result.ok
    assert "四国めたん" in result.problems[0]


def test_行や口の段階の境目の前後0_05秒のずれは_項目7で許す():
    from kataribe.verify import check_characters

    # 1.03 秒（行の境目の直後）でも、まだ前の行の見た目
    late = lambda t: expected_cast(0.99) if 1.0 <= t < 1.04 else None
    samples = cast_samples(late) + [{**sample(1.03), "cast": expected_cast(0.99)}]

    assert check_characters(samples, CAST_TIMELINE).ok


def test_台本の話者の立ち絵がないと項目7はNGになる():
    from kataribe.verify import check_characters

    missing = lambda t: [["四国めたん", "normal", "0"]] if 1.2 <= t < 1.8 else None
    result = check_characters(cast_samples(missing), CAST_TIMELINE)

    assert not result.ok
    assert "ずんだもん" in result.problems[0]
