import copy
import json

import pytest
from conftest import SCRIPT, make_project, run_build, run_lint

DIALOGUE = {
    "title": "掛け合いの動画",
    "chapters": [
        {
            "id": "c1",
            "title": "章",
            "scenes": [
                {
                    "id": "s1",
                    "lines": [
                        {"speaker": "四国めたん", "text": "説明するわ"},
                        {"speaker": "ずんだもん", "expression": "smile", "text": "わかったのだ"},
                        {"speaker": "四国めたん", "text": "続けるわね"},
                    ],
                }
            ],
        }
    ],
}
SCENES = '<section data-scene="s1"><h1>シーン1</h1></section>\n'


def dialogue_project(tmp_path, edit=None):
    script = copy.deepcopy(DIALOGUE)
    if edit:
        edit(script)
    return make_project(tmp_path / "p", script=script, scenes=SCENES)


def first_line(script):
    return script["chapters"][0]["scenes"][0]["lines"][0]


def test_行ごとに_その行のspeakerの声で合成される(tmp_path):
    project = dialogue_project(tmp_path)
    log = tmp_path / "voices.log"

    result = run_build(project, extra_env={"FAKE_TTS_VOICE_LOG": str(log)})

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == ["四国めたん", "ずんだもん", "四国めたん"]


def test_掛け合いでは_概要欄と利用条件と副産物のクレジットに使った声が初めて出た順に並ぶ(tmp_path):
    project = dialogue_project(tmp_path)

    result = run_build(project, args=["--extras"])

    assert result.returncode == 0, result.stderr
    timeline = json.loads((project / "out" / "extras" / "timeline.json").read_text(encoding="utf-8"))
    assert timeline["credit"] == ["VOICEVOX:四国めたん", "VOICEVOX:ずんだもん"]
    terms = (project / "out" / "extras" / "TERMS.txt").read_text(encoding="utf-8")
    assert "VOICEVOX:四国めたん" in terms and "VOICEVOX:ずんだもん" in terms
    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    credits = html.split('data-about="credits"', 1)[1].split("</section>", 1)[0]
    assert credits.index("VOICEVOX:四国めたん") < credits.index("VOICEVOX:ずんだもん")


def test_mp4のクレジット画面は_使った声を1行ずつ出し_以前の文字列のcreditも1行で出す():
    from kataribe.mp4 import render_credit_page

    both = render_credit_page({"title": "題", "credit": ["VOICEVOX:四国めたん", "VOICEVOX:ずんだもん"], "sources": []})
    old = render_credit_page({"title": "題", "credit": "VOICEVOX:ずんだもん", "sources": []})

    assert "<p>VOICEVOX:四国めたん</p><p>VOICEVOX:ずんだもん</p>" in both
    assert "<p>VOICEVOX:ずんだもん</p></section>" in old


def test_声が1つだけでも_timelineのcreditは配列になる(project):
    assert run_build(project, args=["--extras"]).returncode == 0

    timeline = json.loads((project / "out" / "extras" / "timeline.json").read_text(encoding="utf-8"))
    assert timeline["credit"] == ["VOICEVOX:ずんだもん"]


FAILING = [
    ("speaker がない行", lambda s: first_line(s).pop("speaker"), "chapters[0].scenes[0].lines[0].speaker"),
    ("許可リスト外の speaker", lambda s: first_line(s).update(speaker="未登録の声"), "未登録の声"),
    ("speaker が文字列でない", lambda s: first_line(s).update(speaker=3), "chapters[0].scenes[0].lines[0].speaker"),
    ("expression が文字列でない", lambda s: first_line(s).update(expression=3), "chapters[0].scenes[0].lines[0].expression"),
    ("expression が空白だけ", lambda s: first_line(s).update(expression=" "), "chapters[0].scenes[0].lines[0].expression"),
]


@pytest.mark.parametrize("name, edit, keyword", FAILING, ids=[c[0] for c in FAILING])
def test_speakerとexpressionの誤りは_lintとbuildが場所を示して失敗する(tmp_path, name, edit, keyword):
    project = dialogue_project(tmp_path, edit)

    for result in (run_lint(project), run_build(project)):
        assert result.returncode == 1
        assert keyword in result.stderr
        assert "Traceback" not in result.stderr
    assert not (project / "out").exists()


def test_冒頭にvoiceを持つ旧形式の台本は_speakerがないとして失敗し_書き方を示す(tmp_path):
    old = copy.deepcopy(SCRIPT)
    for chapter in old["chapters"]:
        for scene in chapter["scenes"]:
            for line in scene["lines"]:
                line.pop("speaker", None)
    old["voice"] = "ずんだもん"
    project = make_project(tmp_path / "old", script=old)

    result = run_lint(project)

    assert result.returncode == 1
    assert "chapters[0].scenes[0].lines[0].speaker" in result.stderr
    assert "冒頭の voice は使えません" in result.stderr
