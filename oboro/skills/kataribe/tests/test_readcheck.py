import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import SCRIPT, build_and_read_spoken, make_project

from kataribe.adapters.voicevox import Spoken
from kataribe.project import load_project
from kataribe.readcheck import format_rows, reading_rows


def script_with_lines(*lines: dict) -> dict:
    return {**SCRIPT, "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": "s1", "lines": list(lines)}]}]}


def project_with(tmp_path: Path, lines: list[dict], readings: dict | None = None) -> Path:
    return make_project(
        tmp_path / "p",
        script=script_with_lines(*lines),
        scenes='<section data-scene="s1"></section>',
        readings=json.dumps(readings or {}, ensure_ascii=False),
    )


def run_readings(project: Path, url: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("KATARIBE_TTS_CMD", None)
    env.pop("KATARIBE_VOICEVOX_URL", None)
    if url is not None:
        env["KATARIBE_VOICEVOX_URL"] = url
    return subprocess.run([sys.executable, "-m", "kataribe", "readings", str(project)], capture_output=True, text=True, env=env)


def echo_read(items: list[tuple[str, str]]) -> list[Spoken]:
    return [Spoken(text, 1.0) for text, _ in items]


def test_行の表示文と合成に渡す文を並べ_読みの辞書の置き換えと行のreadingを反映する(tmp_path):
    project = project_with(
        tmp_path,
        [
            {"speaker": "ずんだもん", "text": "APIを使います"},
            {"speaker": "四国めたん", "text": "こんにちは", "reading": "コンニチワ"},
        ],
        readings={"API": "エーピーアイ"},
    )

    rows = reading_rows(load_project(project), echo_read)

    assert [(row.text, row.spoken, row.reading, row.from_line_reading) for row in rows] == [
        ("APIを使います", "エーピーアイを使います", "エーピーアイを使います", False),
        ("こんにちは", "コンニチワ", "コンニチワ", True),
    ]


def test_合成に渡す文が空の行も_buildと同じくエンジンへ渡し_返った読みをそのまま示す(tmp_path):
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "えーと"}, {"speaker": "ずんだもん", "text": "こんにちは"}], readings={"えーと": ""})
    asked: list[list[tuple[str, str]]] = []

    def record(items):
        asked.append(items)
        return echo_read(items)

    rows = reading_rows(load_project(project), record)

    assert asked == [[("", "ずんだもん"), ("こんにちは", "ずんだもん")]]
    assert [row.reading for row in rows] == ["", "こんにちは"]


def test_確認した合成に渡す文は_buildが実際に合成へ渡した文と同じになる(tmp_path):
    project = project_with(
        tmp_path,
        [{"speaker": "ずんだもん", "text": "Claude Codeと Claudeを使います"}, {"speaker": "四国めたん", "text": "APIです", "reading": "エーピーアイです"}],
        readings={"Claude": "クロード", "Claude Code": "クロードコード", "API": "ディーアイ"},
    )

    spoken_by_build = build_and_read_spoken(project, tmp_path)
    rows = reading_rows(load_project(project), echo_read)

    assert [row.spoken for row in rows] == spoken_by_build == ["クロードコードと クロードを使います", "エーピーアイです"]


def test_readingsコマンドは_エンジンへ合成と同じ文と声を渡し_読みを行ごとに表示する(engine, tmp_path):
    url, requests = engine
    project = project_with(
        tmp_path,
        [
            {"speaker": "ずんだもん", "text": "APIを使います"},
            {"speaker": "四国めたん", "text": "こんにちは、はじめまして", "reading": "コンニチワ、ハジメマシテ"},
            {"speaker": "ずんだもん", "text": "えーと"},
        ],
        readings={"API": "エーピーアイ", "えーと": ""},
    )

    result = run_readings(project, url)

    assert result.returncode == 0, result.stderr
    queries = [(r["query"]["speaker"][0], r["query"]["text"][0]) for r in requests if r["path"] == "/audio_query"]
    assert queries == [("3", "エーピーアイを使います"), ("2", "コンニチワ、ハジメマシテ"), ("3", "")]
    assert "s1-0 [ずんだもん] APIを使います" in result.stdout
    assert "合成に渡す文: エーピーアイを使います" in result.stdout
    assert "合成に渡す文: コンニチワ、ハジメマシテ（行の reading）" in result.stdout
    assert "s1-2 [ずんだもん] えーと" in result.stdout
    assert "エンジンの読み: （空。エンジンは読みを返しませんでした）" in result.stdout
    assert "自動では判定できません" in result.stdout
    assert not (project / "out").exists()  # 読みの確認は、出力を作らない


def test_独自のTTSを使うときは_読みを取らず_理由と戻し方を示して失敗する(engine, tmp_path):
    url, requests = engine
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "こんにちは"}])
    env = dict(os.environ)
    env["KATARIBE_TTS_CMD"] = f"{sys.executable} x.py"
    env["KATARIBE_VOICEVOX_URL"] = url

    result = subprocess.run([sys.executable, "-m", "kataribe", "readings", str(project)], capture_output=True, text=True, env=env)

    assert result.returncode != 0
    assert "KATARIBE_TTS_CMD" in result.stderr
    assert "Traceback" not in result.stderr
    assert requests == []


def test_エンジンに接続できないとき_読みを取れないことと理由を示して失敗する(tmp_path):
    project = project_with(tmp_path, [{"speaker": "ずんだもん", "text": "こんにちは"}])

    result = run_readings(project, "http://127.0.0.1:9")

    assert result.returncode != 0
    assert "読みを取得できません" in result.stderr
    assert "VOICEVOX に接続できません" in result.stderr
    assert "Traceback" not in result.stderr


def test_読みの表示は_文脈への適否を自動では判定できないと明記し_直す手段を示す():
    from kataribe.readcheck import ReadingRow

    text = format_rows([ReadingRow(id="s1-0", speaker="ずんだもん", text="こんにちは", spoken="こんにちは", reading="コンニチワ", from_line_reading=False, seconds=1.0)])

    assert "エンジンの読み: コンニチワ" in text
    assert "自動では判定できません" in text
    assert "readings.json" in text and "reading を書いて" in text
