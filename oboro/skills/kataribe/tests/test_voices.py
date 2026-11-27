import pytest
from conftest import SCRIPT, make_project, run_build, run_lint

from kataribe.art import _sides
from kataribe.voices import VOICES, VOICEVOX_TERMS, allowed_voices, terms_links


def test_同梱の定義では_5人の声が使える(monkeypatch):
    monkeypatch.delenv("KATARIBE_CHAR_DEFS", raising=False)

    assert allowed_voices() == ("ずんだもん", "四国めたん", "春日部つむぎ", "雨晴はう", "あんこもん")
    assert all(VOICES[name] == f"VOICEVOX:{name}" for name in VOICES)


def test_立ち絵の定義がない声は_使えない(tmp_path, monkeypatch):
    definitions = tmp_path / "definitions"
    definitions.mkdir()
    (definitions / "z.json").write_text('{"speaker": "ずんだもん"}', encoding="utf-8")
    monkeypatch.setenv("KATARIBE_CHAR_DEFS", str(definitions))

    assert allowed_voices() == ("ずんだもん",)


@pytest.mark.parametrize("voice", VOICES)
def test_声はすべて_共通の規約に加えて_自分の規約を持つ(voice):
    links = terms_links((voice,))
    assert links[: len(VOICEVOX_TERMS)] == list(VOICEVOX_TERMS)
    assert len(links) > len(VOICEVOX_TERMS)


def test_規約は_使った声のぶんだけ_重複なく_初めて出た順に並ぶ():
    zunko = terms_links(("ずんだもん", "四国めたん"))
    assert [url for _, url in zunko] == ["https://voicevox.hiroshiba.jp/term/", "https://zunko.jp/con_ongen_kiyaku.html"]

    mixed = terms_links(("雨晴はう", "春日部つむぎ"))
    assert [url for _, url in mixed] == [
        "https://voicevox.hiroshiba.jp/term/",
        "https://amehau.com/",
        "https://tsumugi-official.studio.site/rule",
    ]

    # あんこもんは、ずんだもん・四国めたんと同じ規約
    assert terms_links(("あんこもん", "ずんだもん")) == terms_links(("ずんだもん",))


def test_春日部つむぎの台本は_buildを通り_利用条件に春日部つむぎの規約だけが出る(tmp_path):
    script = {**SCRIPT, "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": [{"speaker": "春日部つむぎ", "text": "こんにちは"}]}]}]}
    project = make_project(tmp_path / "p", script=script, scenes='<section data-scene="s1"><h1>見出し</h1></section>\n')

    result = run_build(project, args=["--extras"])

    assert result.returncode == 0, result.stderr
    terms = (project / "out" / "extras" / "TERMS.txt").read_text(encoding="utf-8")
    assert "VOICEVOX:春日部つむぎ" in terms
    assert "https://tsumugi-official.studio.site/rule" in terms
    assert "https://zunko.jp/con_ongen_kiyaku.html" not in terms


def test_3人目の話者は_lintとbuildが場所と使っている話者を示して失敗する(tmp_path):
    lines = [
        {"speaker": "四国めたん", "text": "はじめるわ"},
        {"speaker": "ずんだもん", "text": "わかったのだ"},
        {"speaker": "春日部つむぎ", "text": "まぜて"},
    ]
    script = {**SCRIPT, "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": lines}]}]}
    project = make_project(tmp_path / "p", script=script, scenes='<section data-scene="s1"><h1>見出し</h1></section>\n')

    for result in (run_lint(project), run_build(project)):
        assert result.returncode != 0
        assert "lines[2].speaker" in result.stderr and "2人まで" in result.stderr
        assert "四国めたん、ずんだもん" in result.stderr
    assert not (project / "out").exists()


@pytest.mark.parametrize(
    "sides, expected",
    [
        (["left", "right"], ["left", "right"]),
        (["right", "left"], ["right", "left"]),
        (["left", "left"], ["left", "right"]),
        (["right", "right"], ["right", "left"]),
        (["right"], ["right"]),
    ],
)
def test_立ち位置は定義に従い_同じ側なら後の人が反対側(sides, expected):
    assert _sides([{"side": side} for side in sides]) == expected
