"""字幕の表示速度の事前検出（readings）。音声クエリから計算した長さで、build と同じ判定をする。"""

import pytest
from compare_speed import compare, read_timeline
from conftest import SCRIPT, make_project, run_build
from fake_voicevox import FRAME
from test_readcheck import project_with, run_readings

from kataribe.adapters.voicevox import AdapterError, Spoken, query_seconds
from kataribe.check import speed_warnings
from kataribe.project import load_project
from kataribe.readcheck import ReadingRow, reading_rows, row_speed_warnings


def query(speed: float = 1.0) -> dict:
    return {
        "speedScale": speed,
        "prePhonemeLength": 10 * FRAME,
        "postPhonemeLength": 20 * FRAME,
        "accent_phrases": [
            {
                "moras": [
                    {"text": "コ", "consonant_length": 4 * FRAME, "vowel_length": 8 * FRAME, "pitch": 5.0},
                    {"text": "ン", "consonant_length": None, "vowel_length": 12 * FRAME, "pitch": 5.0},
                ],
                "pause_mora": {"text": "、", "consonant_length": None, "vowel_length": 40 * FRAME},
            },
            {"moras": [{"text": "ア", "vowel_length": 16 * FRAME, "pitch": 5.0}], "pause_mora": None},
        ],
    }


def test_拍と間と前後の無音を足して音声の長さを計算する():
    assert query_seconds(query()) == pytest.approx((10 + 20 + 4 + 8 + 12 + 40 + 16) * FRAME)


def test_話速の倍率は_前後の無音と間にも掛かる():
    assert query_seconds(query(speed=2.0)) == pytest.approx(query_seconds(query()) / 2)


def test_音素ごとにフレームへ丸める():
    # 1.4 フレームの母音3つは、足してから丸めると4フレーム、音素ごとに丸めると3フレーム
    moras = [{"text": "ア", "vowel_length": 1.4 * FRAME, "pitch": 5.0}] * 3
    item = {"speedScale": 1.0, "prePhonemeLength": 0.0, "postPhonemeLength": 0.0, "accent_phrases": [{"moras": moras}]}

    assert query_seconds(item) == pytest.approx(3 * FRAME)


def test_疑問文の句は_上げ調子の分だけ長くなる():
    item = query()
    item["accent_phrases"][-1]["is_interrogative"] = True

    assert query_seconds(item) - query_seconds(query()) == pytest.approx(14 * FRAME)  # 0.15秒は14フレーム


def test_疑問文でも末尾の拍が無声なら_上げ調子は足さない():
    item = query()
    item["accent_phrases"][-1]["is_interrogative"] = True
    item["accent_phrases"][-1]["moras"][-1]["pitch"] = 0.0

    assert query_seconds(item) == pytest.approx(query_seconds(query()))


def test_文が空なら前後の無音だけになる():
    assert query_seconds({"speedScale": 1.0, "prePhonemeLength": 9 * FRAME, "postPhonemeLength": 9 * FRAME, "accent_phrases": []}) == pytest.approx(18 * FRAME)


@pytest.mark.parametrize("missing", ["speedScale", "prePhonemeLength", "postPhonemeLength", "accent_phrases"])
def test_長さの計算に要る項目がなければ_理由を示して失敗する(missing):
    broken = query()
    del broken[missing]

    with pytest.raises(AdapterError, match=missing):
        query_seconds(broken)


def test_閾値の前後で_buildと同じ文言の警告を出す(tmp_path):
    def row(line_id: str, seconds: float) -> ReadingRow:
        return ReadingRow(id=line_id, speaker="ずんだもん", text="あ" * 15, spoken="", reading="", from_line_reading=False, seconds=seconds)

    rows = [row("ちょうど", 2.0), row("超える", 1.99)]
    timeline = {"lines": [{"id": r.id, "text": r.text, "start": 0.0, "end": r.seconds} for r in rows]}

    warnings = row_speed_warnings(rows)

    assert warnings == speed_warnings(timeline)
    assert len(warnings) == 1 and "超える" in warnings[0] and "7.5" in warnings[0]


def test_readings_コマンドは長さを示し_超過を警告しても終了コード0(engine, tmp_path):
    url, _ = engine
    # 偽のエンジンは1拍9フレームで、前後に9フレームずつの無音（1フレームは 256/24000 秒）
    project = project_with(
        tmp_path,
        [{"speaker": "ずんだもん", "text": "ゆっくりはなす"}, {"speaker": "ずんだもん", "text": "とても長い字幕です", "reading": "ア"}],
    )

    result = run_readings(project, url)

    assert result.returncode == 0, result.stderr
    assert "音声の長さ（計算）: 0.86 秒（字幕 8.1 字/秒）" in result.stdout
    assert "音声の長さ（計算）: 0.29 秒（字幕 31.3 字/秒）" in result.stdout
    assert "警告: s1-1: 字幕の表示速度が 31.3 字/秒です" in result.stderr


def test_読点の間で速度が下がり_警告が消える(engine, tmp_path):
    url, _ = engine
    without = project_with(tmp_path / "a", [{"speaker": "ずんだもん", "text": "あいうえおかきくけこさしす"}])
    with_comma = project_with(tmp_path / "b", [{"speaker": "ずんだもん", "text": "あいうえお、かきくけこさしす"}])

    # 13拍で135フレーム、1.44秒（9.0字/秒）。読点を足すと、1字増えて45フレームの間が入るので1.92秒（7.3字/秒）
    assert "字幕の表示速度が 9.0 字/秒" in run_readings(without, url).stderr
    assert "字幕の表示速度" not in run_readings(with_comma, url).stderr


def test_比較は_長さの差と警告の判定の一致を示す():
    rows = [ReadingRow(id=i, speaker="", text="あ" * 15, spoken="", reading="", from_line_reading=False, seconds=s) for i, s in [("a", 1.0), ("b", 3.0)]]
    same = {"lines": [{"id": "a", "text": "あ" * 15, "start": 0.0, "end": 1.1}, {"id": "b", "text": "あ" * 15, "start": 1.1, "end": 4.1}]}
    different = {"lines": [{"id": "a", "text": "あ" * 15, "start": 0.0, "end": 3.0}, {"id": "b", "text": "あ" * 15, "start": 3.0, "end": 6.0}]}

    assert compare(rows, same).agrees
    assert compare(rows, same).largest_error == pytest.approx(0.1)
    assert not compare(rows, different).agrees


def test_比較は_台本とタイムラインの行が違えば失敗する():
    rows = [ReadingRow(id="a", speaker="", text="あ", spoken="", reading="", from_line_reading=False, seconds=1.0)]

    with pytest.raises(ValueError, match="build し直して"):
        compare(rows, {"lines": [{"id": "a", "text": "い", "start": 0.0, "end": 1.0}]})


def test_比較は_build_の出力からタイムラインを読める(tmp_path):
    project = make_project(tmp_path / "p", script=SCRIPT)

    assert run_build(project).returncode == 0

    rows = reading_rows(load_project(project), lambda items: [Spoken(text, 0.0) for text, _ in items])
    timeline = read_timeline(project / "out")
    assert [line["id"] for line in timeline["lines"]] == [row.id for row in rows]


def test_比較は古いextrasではなく現在のvideoを読む(tmp_path):
    project = make_project(tmp_path / "p", script=SCRIPT)
    assert run_build(project).returncode == 0
    extras = project / "out" / "extras"
    extras.mkdir()
    (extras / "timeline.json").write_text('{"lines": []}', encoding="utf-8")

    assert read_timeline(project / "out")["lines"]
