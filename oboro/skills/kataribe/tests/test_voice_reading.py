"""readings のアクセントの表示と、アクセント句の途中で区切られた片仮名語の警告。"""

from test_voice_engine import query_for, write_project

from kataribe.adapters.voicevox import Spoken, accented_reading_of, reading_of
from kataribe.project import load_project
from kataribe.readcheck import ReadingRow, format_rows, reading_rows, row_split_warnings, split_words


def phrases(*texts: str) -> tuple[tuple[str, ...], ...]:
    """エンジンの読みの句（拗音は前の仮名と1拍）。"""
    result = []
    for text in texts:
        moras: list[str] = []
        for char in text:
            if char in "ァィゥェォャュョ" and moras:
                moras[-1] += char
            else:
                moras.append(char)
        result.append(tuple(moras))
    return tuple(result)


# アクセント


def test_アクセント核のあとにアポストロフィを置き句をスラッシュでポーズを読点で示す():
    query = query_for(
        "",
        [
            (["キョ", "オ", "ワ"], 1, True),
            (["デ", "エ", "タ", "ガ"], 1, False),
            (["ス", "ウ", "テ", "ラ"], 3, False),
            (["タ", "ッ", "シ", "タ", "ノ"], 5, False),
        ],
    )

    assert accented_reading_of(query) == "キョ'オワ、デ'エタガ/スウテ'ラ/タッシタノ'"
    assert reading_of(query) == "キョオワ、デエタガ スウテラ タッシタノ"


def test_アクセントの行はエンジンの読みの直後に出る(tmp_path):
    write_project(tmp_path, [{"speaker": "四国めたん", "text": "データ"}, {"speaker": "ずんだもん", "text": "なのだ"}])
    results = [Spoken("デエタ", 1.0, accented="デ'エタ"), Spoken("ナノダ", 1.0)]

    rows = reading_rows(load_project(tmp_path), lambda items: results)
    text = format_rows(rows).splitlines()

    first = text.index("    エンジンの読み: デエタ")
    assert text[first + 1] == "    アクセント: デ'エタ"
    second = text.index("    エンジンの読み: ナノダ")
    assert text[second + 1].startswith("    音声の長さ（計算）:")


# 区切られた片仮名語


def test_実際の読みで区切られた片仮名語を見つける():
    assert split_words("数テラバイトに達したの", phrases("スウテラ", "バイトニ", "タッシタノ")) == [
        ("テラバイト", "スウテラ / バイトニ")
    ]
    assert split_words("シャーディングとも呼ばれるわ", phrases("シャア", "ディングトモ", "ヨバレルワ")) == [
        ("シャーディング", "シャア / ディングトモ")
    ]
    assert split_words("リージョンごとに", phrases("リイ", "ジョン", "ゴトニ")) == [("リージョン", "リイ / ジョン")]
    assert split_words("ホットスポットが", phrases("ホッ", "トスポットガ")) == [("ホットスポット", "ホッ / トスポットガ")]


def test_どの切れ端も3拍以上の複合語は警告しない():
    assert split_words("ローカルインデックスを", phrases("ロオカル", "インデックスオ")) == []
    assert split_words("グルメレビューの", phrases("グルメ", "レビュウノ")) == []


def test_1句に収まる語と見つからない語は警告しない():
    assert split_words("データが", phrases("デエタガ")) == []
    assert split_words("データが", phrases("ジョウホウガ")) == []


def test_エンジンが長音にした読みも同じ語として照らす():
    assert split_words("コンシステントハッシュホウと", phrases("コンシステント", "ハッ", "シュホオト")) == [
        ("コンシステントハッシュホウ", "コンシステント / ハッ / シュホオト")
    ]


def test_同じ語が2回出ればそれぞれの位置で判定する():
    spoken = "カサンドラとカサンドラ"
    assert split_words(spoken, phrases("カサンドラト", "カサン", "ドラ")) == [("カサンドラ", "カサン / ドラ")]


def test_区切りの警告の文面():
    row = ReadingRow(
        id="s1-4",
        speaker="四国めたん",
        text="数テラバイトに達したの",
        spoken="数テラバイトに達したの",
        reading="スウテラ バイトニ タッシタノ",
        from_line_reading=False,
        seconds=1.0,
        phrases=phrases("スウテラ", "バイトニ", "タッシタノ"),
    )

    assert row_split_warnings([row]) == [
        "警告: s1-4: 片仮名語「テラバイト」が、アクセント句の途中で区切られています（スウテラ / バイトニ）。"
        "readings.json に読みとアクセントを登録すると、1語として読みます"
    ]
