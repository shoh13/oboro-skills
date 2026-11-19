"""readings.json の、読みとアクセントを持つオブジェクトの項目。"""

import pytest
from test_voice_engine import write_project

from kataribe.project import AccentWord, ProjectError, accent_words, load_project
from kataribe.reading import spoken_text

LINE = {"speaker": "四国めたん", "text": "数TBに達したの"}


def load(tmp_path, readings):
    write_project(tmp_path, [LINE], readings)
    return load_project(tmp_path)


def test_オブジェクトの項目は読みで置き換えてアクセントの語になる(tmp_path):
    project = load(tmp_path, {"TB": {"reading": "テラバイト", "accent": 3}, "数": "スウ"})

    assert spoken_text(project.lines[0], project.readings) == "スウテラバイトに達したの"
    assert project.readings == {"TB": "テラバイト", "数": "スウ"}
    assert project.accents == (AccentWord(surface="TB", reading="テラバイト", accent=3),)
    assert accent_words(project) == (("テラバイト", 3),)


def test_アクセントは0から拍の数まで使える(tmp_path):
    # シャーディング は シャ・ー・ディ・ン・グ の5拍
    project = load(tmp_path, {"a": {"reading": "シャーディング", "accent": 0}, "b": {"reading": "リージョン", "accent": 3}})

    assert [word.accent for word in project.accents] == [0, 3]


def test_同じ読みと同じアクセントの項目は1語として登録する(tmp_path):
    project = load(tmp_path, {"TB": {"reading": "テラバイト", "accent": 3}, "テラバイト": {"reading": "テラバイト", "accent": 3}})

    assert accent_words(project) == (("テラバイト", 3),)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"reading": "てらばいと", "accent": 3}, "「TB」の reading はカタカナ（長音「ー」を含む）だけ"),
        ({"reading": "", "accent": 0}, "「TB」の reading はカタカナ"),
        ({"reading": "テラ バイト", "accent": 1}, "「TB」の reading はカタカナ"),
        ({"reading": "テラバイト", "accent": True}, "「TB」の accent は整数である必要があります"),
        ({"reading": "テラバイト", "accent": "3"}, "「TB」の accent は整数である必要があります"),
        ({"reading": "テラバイト", "accent": 6}, "「TB」の accent は 0（平板型）から 5（「テラバイト」の拍の数）までです: 6"),
        ({"reading": "テラバイト", "accent": -1}, "から 5"),
        ({"reading": "テラバイト"}, "「TB」には reading と accent の両方が必要です"),
        ({"reading": "テラバイト", "accent": 3, "priority": 9}, "「TB」に使えないキーがあります: priority"),
    ],
)
def test_オブジェクトの項目の誤りは表記を示して失敗する(tmp_path, value, message):
    with pytest.raises(ProjectError, match=message):
        load(tmp_path, {"TB": value})


def test_同じ読みに違うアクセントを付けると失敗する(tmp_path):
    with pytest.raises(ProjectError, match="「TB」と「テラバイト」は、同じ読み「テラバイト」に違うアクセント（3 と 1）"):
        load(tmp_path, {"TB": {"reading": "テラバイト", "accent": 3}, "テラバイト": {"reading": "テラバイト", "accent": 1}})


def test_文字列でもオブジェクトでもない読みはこれまでの文面で失敗する(tmp_path):
    with pytest.raises(ProjectError, match="readings.json の「TB」の読みは文字列である必要があります"):
        load(tmp_path, {"TB": 3})


def test_長音で始まる読みはアクセントの語にできない(tmp_path):
    with pytest.raises(ProjectError, match="TB"):
        load(tmp_path, {"TB": {"reading": "ーア", "accent": 0}})
