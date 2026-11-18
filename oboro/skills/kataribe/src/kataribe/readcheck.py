"""合成に渡す文の読みと音声の長さを、VOICEVOX の音声クエリで行ごとに確認する。音声は作らない。

台本の各行は、build と同じ規則（reading.spoken_text）で「合成に渡す文」にしてから、エンジンに問い合わせる。
そのため、ここで見える読みは、build の合成でエンジンが使う読みと同じ入力に対するものになる。

限界: 読みの取得は、エンジンが組み立てた読み（モーラのカタカナ）を見せるだけで、正しさを保証しない。
アクセント・抑揚・語の読み分けは、ここでは確かめられない。独自の TTS（KATARIBE_TTS_CMD）では読みを取れない。
"""

from collections.abc import Callable
from dataclasses import dataclass

from kataribe.adapters import voicevox
from kataribe.check import chars_per_second, line_speed_warnings
from kataribe.project import Project
from kataribe.reading import spoken_text
from kataribe.tts import uses_custom_adapter


class ReadingCheckError(Exception):
    pass


@dataclass(frozen=True)
class ReadingRow:
    id: str
    speaker: str | None
    text: str  # 台本の表示文（字幕と同じ）
    spoken: str  # 合成に渡す文（build と同じ規則で作る）
    reading: str  # エンジンが組み立てた読み（空のこともある）
    from_line_reading: bool  # 行の reading を使ったか（readings.json は使わない）
    seconds: float  # 音声クエリから計算した音声の長さ


# （合成に渡す文, 声）の並び → 読みと長さの並び。エンジン（VOICEVOX）への問い合わせを差し替えられるように受け取る。
Read = Callable[[list[tuple[str, str]]], list[voicevox.Spoken]]


def reading_rows(project: Project, read: Read) -> list[ReadingRow]:
    """build と同じ行の順・同じ文・同じ声で、エンジンに読みを問い合わせる。空の文も、build と同じく渡す。"""
    for line in project.lines:
        assert line.speaker is not None  # 動画の台本には地の文がない（load_project の既定）
    spoken = [spoken_text(line, project.readings) for line in project.lines]
    results = read([(text, line.speaker or "") for text, line in zip(spoken, project.lines)])
    assert len(results) == len(project.lines)
    return [
        ReadingRow(
            id=line.id,
            speaker=line.speaker,
            text=line.text,
            spoken=text,
            reading=result.reading,
            from_line_reading=line.reading is not None,
            seconds=result.seconds,
        )
        for line, text, result in zip(project.lines, spoken, results)
    ]


def check_readings(project: Project) -> list[ReadingRow]:
    if uses_custom_adapter():
        raise ReadingCheckError(
            "KATARIBE_TTS_CMD で独自の TTS を使っているため、読みを取得できません（読みを返すのは VOICEVOX の音声クエリだけです）。"
            "既定の VOICEVOX で確かめるには KATARIBE_TTS_CMD を外してください。独自の TTS の読みは、その TTS の仕様で確かめてください。"
        )
    try:
        base = voicevox.engine_url()
        return reading_rows(project, lambda items: voicevox.read_aloud(base, items))
    except voicevox.AdapterError as e:
        raise ReadingCheckError(f"読みを取得できません: {e}") from None


def row_speed_warnings(rows: list[ReadingRow]) -> list[str]:
    """build が音声の実測長で出す字幕の表示速度の警告を、音声クエリから計算した長さで先に出す。"""
    return line_speed_warnings((row.id, row.text, row.seconds) for row in rows)


def format_rows(rows: list[ReadingRow]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(f"{row.id} [{row.speaker}] {row.text}")
        source = "（行の reading）" if row.from_line_reading else ""
        lines.append(f"    合成に渡す文: {row.spoken}{source}")
        lines.append(f"    エンジンの読み: {row.reading or '（空。エンジンは読みを返しませんでした）'}")
        lines.append(f"    音声の長さ（計算）: {row.seconds:.2f} 秒（字幕 {chars_per_second(row.text, row.seconds):.1f} 字/秒）")
    lines.append("")
    lines.append("この表は、エンジンが合成に使う読みを示すだけです。読みが文脈に合っているか、アクセントや抑揚が自然かは、自動では判定できません。")
    lines.append("台本と照らして人が確かめてください。直すには、readings.json に「表記」と「読み」を足すか、行に reading を書いてから、もう一度 readings を実行してください。")
    return "\n".join(lines)
