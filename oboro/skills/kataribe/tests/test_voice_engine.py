"""VOICEVOX エンジンとのやりとり（ユーザー辞書の同期・合成・readings）を、偽のエンジンで確かめる。"""

import json
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from kataribe import cli
from kataribe.adapters import voicevox
from kataribe.project import load_project
from kataribe.readcheck import check_readings

SPEAKERS = [
    {"name": "四国めたん", "styles": [{"name": "ノーマル", "id": 2}, {"name": "あまあま", "id": 0}]},
    {"name": "ずんだもん", "styles": [{"name": "ノーマル", "id": 3}, {"name": "あまあま", "id": 1}, {"name": "ツンツン", "id": 7}]},
]


def fullwidth(text: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


def query_for(text: str, phrases: list[tuple[list[str], int, bool]] | None = None) -> dict:
    """音声クエリ。phrases は（モーラ, アクセント, ポーズの有無）の並び。省略すると文の1字を1拍とする1句。"""
    phrases = phrases or [(list(text) or ["ア"], 1, False)]
    return {
        "accent_phrases": [
            {
                "moras": [{"text": m, "consonant_length": 0.05, "vowel_length": 0.1, "pitch": 5.5} for m in moras],
                "accent": accent,
                "pause_mora": {"text": "、", "vowel_length": 0.3, "pitch": 0.0} if pause else None,
                "is_interrogative": False,
            }
            for moras, accent, pause in phrases
        ],
        "speedScale": 1.0,
        "intonationScale": 1.0,
        "prePhonemeLength": 0.1,
        "postPhonemeLength": 0.1,
    }


class FakeEngine:
    """voicevox._request の代わり。VOICEVOX エンジン 0.25 の応答の形を返し、届いた要求を記録する。"""

    def __init__(self, words: dict | None = None, queries: dict | None = None, version: str = "0.25.2"):
        self.words = {uuid: dict(word) for uuid, word in (words or {}).items()}
        self.queries = queries or {}
        self.version = version
        self.calls: list[tuple[str, str, dict]] = []
        self.synthesized: list[tuple[int, dict]] = []
        self.reject_words = False
        self._next = 0

    def writes(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.calls if method in ("POST", "PUT", "DELETE") and "user_dict" in path]

    def dictionary(self) -> set[tuple[str, str, int]]:
        return {(w["surface"], w["pronunciation"], w["accent_type"]) for w in self.words.values()}

    def __call__(self, url, data=None, content_type=None, method=None):
        method = method or ("POST" if data is not None else "GET")
        parts = urlsplit(url)
        params = dict(parse_qsl(parts.query))
        path = unquote(parts.path)
        self.calls.append((method, path, params))
        if path == "/version":
            return json.dumps(self.version).encode()
        if path == "/speakers":
            return json.dumps(SPEAKERS).encode()
        if path == "/user_dict":
            return json.dumps(self.words, ensure_ascii=False).encode()
        if path.startswith("/user_dict_word"):
            if method in ("POST", "PUT") and self.reject_words:
                raise voicevox.AdapterError(f"VOICEVOX がエラーを返しました ({url}, HTTP 422): 誤ったアクセント型です")
            if method == "POST":
                self._next += 1
                uuid = f"new-{self._next}"
            else:
                uuid = path.rsplit("/", 1)[1]
            if method == "DELETE":
                del self.words[uuid]
                return b""
            self.words[uuid] = {
                "surface": fullwidth(params["surface"]),
                "pronunciation": params["pronunciation"],
                "accent_type": int(params["accent_type"]),
                "priority": int(params.get("priority", 5)),  # エンジンの既定値は5
            }
            return json.dumps(uuid).encode() if method == "POST" else b""
        if path == "/audio_query":
            return json.dumps(self.queries.get(params["text"]) or query_for(params["text"]), ensure_ascii=False).encode()
        if path == "/synthesis":
            self.synthesized.append((int(params["speaker"]), json.loads(data)))
            return b"RIFF-fake"
        raise AssertionError(f"想定していない要求: {method} {url}")


@pytest.fixture
def own_engine(monkeypatch):
    """kataribe の Docker のコンテナ（KATARIBE_VOICEVOX_URL なし）。"""
    engine = FakeEngine()
    monkeypatch.delenv("KATARIBE_VOICEVOX_URL", raising=False)
    monkeypatch.delenv("KATARIBE_TTS_CMD", raising=False)
    monkeypatch.setattr(voicevox, "_ensure_container", lambda: "http://own")
    monkeypatch.setattr(voicevox, "_request", engine)
    return engine


@pytest.fixture
def external_engine(monkeypatch):
    """KATARIBE_VOICEVOX_URL の、他の人も使うエンジン。"""
    engine = FakeEngine()
    monkeypatch.setenv("KATARIBE_VOICEVOX_URL", "http://shared")
    monkeypatch.delenv("KATARIBE_TTS_CMD", raising=False)
    monkeypatch.setattr(voicevox, "_request", engine)
    return engine


def write_project(root, lines: list[dict], readings: dict | None = None) -> None:
    script = {"title": "題名", "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": lines}]}]}
    (root / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    (root / "readings.json").write_text(json.dumps(readings or {}, ensure_ascii=False), encoding="utf-8")
    (root / "scenes.html").write_text('<section data-scene="s1"></section>', encoding="utf-8")


FOREIGN = {"surface": "ＡＢＣ", "pronunciation": "エービーシー", "accent_type": 1, "priority": 5}


# ユーザー辞書の同期


def test_自前のコンテナの辞書はプロジェクトの語ちょうどになる(own_engine):
    own_engine.words = {
        "old": dict(FOREIGN),
        "stale": {"surface": "テラバイト", "pronunciation": "テラバイト", "accent_type": 1, "priority": 5},
    }

    voicevox.prepare_engine((("テラバイト", 3), ("シャーディング", 0)))

    assert own_engine.dictionary() == {("テラバイト", "テラバイト", 3), ("シャーディング", "シャーディング", 0)}


def test_外部のエンジンの辞書は追加と更新だけで他の語を消さない(external_engine):
    external_engine.words = {"theirs": dict(FOREIGN)}

    voicevox.prepare_engine((("テラバイト", 3),))

    assert external_engine.dictionary() == {("ＡＢＣ", "エービーシー", 1), ("テラバイト", "テラバイト", 3)}
    assert not [call for call in external_engine.writes() if call[0] == "DELETE"]


@pytest.mark.parametrize("engine_fixture", ["own_engine", "external_engine"])
def test_辞書の同期は2回目には何も書かない(engine_fixture, request):
    engine = request.getfixturevalue(engine_fixture)
    engine.words = {"theirs": dict(FOREIGN)}
    words = (("テラバイト", 3), ("リージョン", 1))
    voicevox.prepare_engine(words)
    after_first = engine.dictionary()
    engine.calls.clear()

    voicevox.prepare_engine(words)

    assert engine.writes() == []
    assert engine.dictionary() == after_first


def test_自前のコンテナでは同じ表記の重複を1つにする(own_engine):
    own_engine.words = {
        "a": {"surface": "テラバイト", "pronunciation": "テラバイト", "accent_type": 3, "priority": 5},
        "b": {"surface": "テラバイト", "pronunciation": "テラバイト", "accent_type": 1, "priority": 5},
    }

    voicevox.prepare_engine((("テラバイト", 3),))

    assert list(own_engine.words) == ["a"]


def test_外部のエンジンで登録する語がなければ辞書に触れない(external_engine):
    voicevox.prepare_engine(())

    assert not [call for call in external_engine.calls if "user_dict" in call[1]]


def test_辞書に登録できなければ読みを示して失敗する(own_engine):
    own_engine.reject_words = True

    with pytest.raises(voicevox.AdapterError, match="「テラバイト」（アクセント 3）"):
        voicevox.prepare_engine((("テラバイト", 3),))


# 合成


def test_合成は声のノーマルのIDでエンジンに問い合わせる(external_engine, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("こんにちは"))

    code = voicevox.main(["--voice", "ずんだもん", "--output", str(tmp_path / "a.wav")])

    assert code == 0
    assert external_engine.synthesized[0][0] == 3


def test_声がなければ失敗する(external_engine):
    with pytest.raises(voicevox.AdapterError, match="声「春日部つむぎ」（スタイル ノーマル）がありません"):
        voicevox.synthesize("http://shared", "こんにちは", "春日部つむぎ", 1.0)


# readings


def test_readingsは辞書を先に合わせてから問い合わせる(own_engine, tmp_path):
    write_project(tmp_path, [{"speaker": "ずんだもん", "text": "テラバイトなのだ"}], {"TB": {"reading": "テラバイト", "accent": 3}})

    check_readings(load_project(tmp_path))

    first_query = next(i for i, call in enumerate(own_engine.calls) if call[1] == "/audio_query")
    first_write = next(i for i, call in enumerate(own_engine.calls) if call[1].startswith("/user_dict_word"))
    assert first_write < first_query
    assert own_engine.dictionary() == {("テラバイト", "テラバイト", 3)}


def test_readingsはアクセントを表示し区切られた片仮名語を警告する(own_engine, tmp_path, capsys):
    text = "数テラバイトに達したの"
    write_project(tmp_path, [{"speaker": "四国めたん", "text": text}])
    own_engine.queries[text] = query_for(
        text,
        [(["ス", "ウ", "テ", "ラ"], 3, False), (["バ", "イ", "ト", "ニ"], 1, False), (["タ", "ッ", "シ", "タ", "ノ"], 2, False)],
    )

    assert cli.main(["readings", str(tmp_path)]) == 0

    out, err = capsys.readouterr()
    assert "    エンジンの読み: スウテラ バイトニ タッシタノ\n    アクセント: スウテ'ラ/バ'イトニ/タッ'シタノ\n" in out
    assert (
        "警告: s1-0: 片仮名語「テラバイト」が、アクセント句の途中で区切られています（スウテラ / バイトニ）。"
        "readings.json に読みとアクセントを登録すると、1語として読みます"
    ) in err.splitlines()


def test_登録した語はエンジンの解析より優先される優先度で登録し既定の優先度の語は更新する(own_engine):
    own_engine.words = {"old": {"surface": "テラバイト", "pronunciation": "テラバイト", "accent_type": 3, "priority": 5}}

    voicevox.prepare_engine((("テラバイト", 3),))

    assert [w["priority"] for w in own_engine.words.values()] == [voicevox.WORD_PRIORITY]
    assert voicevox.WORD_PRIORITY > 5
