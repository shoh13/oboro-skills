import json

import pytest

from kataribe.adapters.voicevox import Spoken
from kataribe.project import ProjectError, load_project
from kataribe.readcheck import format_rows, reading_rows

SCRIPT = {
    "title": "題名",
    "chapters": [
        {
            "id": "c1",
            "title": "章",
            "scenes": [
                {
                    "id": "s1",
                    "lines": [
                        {"speaker": "四国めたん", "text": "ある架空の物語を、空のデータベースで解説するわ。"},
                        {"speaker": "ずんだもん", "text": "読みは辞書を通らないのだ。", "reading": "よみはじしょをとおらないのだ"},
                        {"speaker": "ずんだもん", "text": "MD5もMD5なのだ。"},
                    ],
                }
            ],
        }
    ],
}
READINGS = {"空の": "カラの", "MD5": "エムディーファイブ", "物語": ""}


def write_project(root, *, scenes: bool) -> None:
    (root / "script.json").write_text(json.dumps(SCRIPT, ensure_ascii=False), encoding="utf-8")
    (root / "readings.json").write_text(json.dumps(READINGS, ensure_ascii=False), encoding="utf-8")
    if scenes:
        (root / "scenes.html").write_text('<section data-scene="s1"></section>', encoding="utf-8")


def fake_engine(items):
    return [Spoken(reading=text, seconds=1.0) for text, _ in items]


def test_readingsはscenes_htmlがなくても台本を読める(tmp_path):
    write_project(tmp_path, scenes=False)

    project = load_project(tmp_path, require_scenes=False)

    assert [line.id for line in project.lines] == ["s1-0", "s1-1", "s1-2"]


def test_buildの読み込みはscenes_htmlがなければ失敗する(tmp_path):
    write_project(tmp_path, scenes=False)

    with pytest.raises(ProjectError, match="scenes.html"):
        load_project(tmp_path)


def test_scenes_htmlがあればrequire_scenesが偽でも検査する(tmp_path):
    write_project(tmp_path, scenes=False)
    (tmp_path / "scenes.html").write_text('<section data-scene="s1"><p data-at="9">x</p></section>', encoding="utf-8")

    with pytest.raises(ProjectError, match="範囲外"):
        load_project(tmp_path, require_scenes=False)


def test_行ごとに置き換えた辞書の表記と読みを表示する(tmp_path):
    write_project(tmp_path, scenes=True)
    rows = reading_rows(load_project(tmp_path), fake_engine)

    # 「架空の」の途中の「空の」にも当たる。これを見つけられるように表示する
    assert rows[0].dictionary == (("空の", "カラの"), ("物語", ""))
    assert rows[0].spoken == "ある架カラのを、カラのデータベースで解説するわ。"
    # 行の reading を使う行は辞書を通らない
    assert rows[1].dictionary == ()
    # 同じ表記が何度当たっても1回だけ示す
    assert rows[2].dictionary == (("MD5", "エムディーファイブ"),)

    text = format_rows(rows)
    assert "    辞書: 空の→カラの、物語→（発音しない）" in text
    assert "    辞書: MD5→エムディーファイブ" in text
