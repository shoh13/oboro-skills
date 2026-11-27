"""合成に渡す文の読みと音声の長さを、VOICEVOX の音声クエリで行ごとに確認する。音声は作らない。

台本の各行は、build と同じ規則（reading.spoken_text）で「合成に渡す文」にしてから、エンジンに問い合わせる。
そのため、ここで見える読みは、build の合成でエンジンが使う読みと同じ入力に対するものになる。

限界: 読みの取得は、エンジンが組み立てた読み（モーラのカタカナとアクセント）を見せるだけで、正しさを保証しない。
アクセントが自然か・語の読み分けが文脈に合うかは、ここでは判定しない。片仮名語がアクセント句の途中で区切られたものだけを警告する。
独自の TTS（KATARIBE_TTS_CMD）では読みを取れない。
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from kataribe.adapters import voicevox
from kataribe.check import chars_per_second, line_speed_warnings
from kataribe.project import Project, accent_words
from kataribe.reading import spoken_text_with_hits
from kataribe.tts import uses_custom_adapter


SILENT = "（発音しない）"  # readings.json で読みを空文字にした表記


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
    dictionary: tuple[tuple[str, str], ...] = ()  # 置き換えた readings.json の（表記, 読み）。表記は語の途中にも当たる
    accented: str = ""  # アクセント付きの読み（voicevox.accented_reading_of）
    phrases: tuple[tuple[str, ...], ...] = ()  # アクセント句ごとのモーラのカタカナ


# （合成に渡す文, 声）の並び → 読みと長さの並び。エンジン（VOICEVOX）への問い合わせを差し替えられるように受け取る。
Read = Callable[[list[tuple[str, str]]], list[voicevox.Spoken]]


def reading_rows(project: Project, read: Read) -> list[ReadingRow]:
    """build と同じ行の順・同じ文・同じ声で、エンジンに読みを問い合わせる。空の文も、build と同じく渡す。"""
    for line in project.lines:
        assert line.speaker is not None  # 動画の台本には地の文がない（load_project の既定）
    converted = [spoken_text_with_hits(line, project.readings) for line in project.lines]
    results = read([(text, line.speaker or "") for (text, _), line in zip(converted, project.lines)])
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
            dictionary=tuple((surface, project.readings[surface]) for surface in hits),
            accented=result.accented,
            phrases=result.phrases,
        )
        for line, (text, hits), result in zip(project.lines, converted, results)
    ]


def check_readings(project: Project) -> list[ReadingRow]:
    if uses_custom_adapter():
        raise ReadingCheckError(
            "KATARIBE_TTS_CMD で独自の TTS を使っているため、読みを取得できません（読みを返すのは VOICEVOX の音声クエリだけです）。"
            "既定の VOICEVOX で確かめるには KATARIBE_TTS_CMD を外してください。独自の TTS の読みは、その TTS の仕様で確かめてください。"
        )
    try:
        base = voicevox.prepare_engine(accent_words(project))
        return reading_rows(project, lambda items: voicevox.read_aloud(base, items))
    except voicevox.AdapterError as e:
        raise ReadingCheckError(f"読みを取得できません: {e}") from None


def row_speed_warnings(rows: list[ReadingRow]) -> list[str]:
    """build が音声の実測長で出す字幕の表示速度の警告を、音声クエリから計算した長さで先に出す。"""
    return line_speed_warnings((row.id, row.text, row.seconds) for row in rows)


_SMALL_KANA = "ァィゥェォャュョヮ"
_VOWEL_OF = {
    **dict.fromkeys("アカガサザタダナハバパマヤラワァャヮ", "ア"),
    **dict.fromkeys("イキギシジチヂニヒビピミリィ", "イ"),
    **dict.fromkeys("ウクグスズツヅヌフブプムユルゥュヴ", "ウ"),
    **dict.fromkeys("エケゲセゼテデネヘベペメレェ", "エ"),
    **dict.fromkeys("オコゴソゾトドノホボポモヨロヲォョ", "オ"),
}
_ENGINE_KANA = str.maketrans("ヲヂヅ", "オジズ")  # エンジンのモーラの表記
KATAKANA_WORD = re.compile(r"[ァ-ヴー]{3,}")
MAX_SPLIT_MORAS = 2  # 語の中で、この拍数以下の切れ端ができる区切りを警告する


def _engine_moras(word: str) -> list[str]:
    """片仮名語を、エンジンが書くモーラの並びにする。長音「ー」は直前の仮名の母音にする（データ → デ・エ・タ）。"""
    moras: list[str] = []
    for char in word.translate(_ENGINE_KANA):
        if char in _SMALL_KANA and moras:
            moras[-1] += char
        elif char == "ー" and moras:
            moras.append(_VOWEL_OF.get(moras[-1][-1], char))
        else:
            moras.append(char)
    return moras


_LONG_VOWELS = {("オ", "ウ"): "オ", ("エ", "イ"): "エ"}  # エンジンは、ホウをホオ、エイをエエと書くことがある


def _same_moras(word: list[str], engine: list[str]) -> bool:
    for position, (mora, written) in enumerate(zip(word, engine, strict=True)):
        if mora == written:
            continue
        before = _VOWEL_OF.get(word[position - 1][-1]) if position else None
        if _LONG_VOWELS.get((before or "", mora)) != written:
            return False
    return True


def split_words(spoken: str, phrases: tuple[tuple[str, ...], ...]) -> list[tuple[str, str]]:
    """合成に渡す文の片仮名語（3字以上）のうち、アクセント句の境目が語の中にあり、語の切れ端が2拍以下になるもの。

    返すのは（語, 語にかかるアクセント句を「 / 」でつないだもの）。テラバイト → スウテラ / バイトニ。
    ローカル / インデックスのように、どの切れ端も3拍以上の区切りは、複合語の切れ目として警告しない。
    エンジンのモーラの並びに語が見つからないとき（エンジンが別の読みにしたとき）は、判定しない。
    """
    flat = [(mora, index) for index, phrase in enumerate(phrases) for mora in phrase]
    texts = [mora for mora, _ in flat]
    found = []
    cursor = 0
    for word in KATAKANA_WORD.findall(spoken):
        moras = _engine_moras(word)
        start = next(
            (i for i in range(cursor, len(texts) - len(moras) + 1) if _same_moras(moras, texts[i : i + len(moras)])),
            None,
        )
        if start is None:
            continue
        cursor = start + len(moras)
        spans = [index for _, index in flat[start:cursor]]
        pieces = [spans.count(index) for index in dict.fromkeys(spans)]
        if len(pieces) > 1 and min(pieces) <= MAX_SPLIT_MORAS:
            context = " / ".join("".join(phrases[index]) for index in dict.fromkeys(spans))
            found.append((word, context))
    return found


def row_split_warnings(rows: list[ReadingRow]) -> list[str]:
    """アクセント句の途中で区切られた片仮名語の警告。1語として読ませるには、readings.json に読みとアクセントを登録する。"""
    return [
        f"警告: {row.id}: 片仮名語「{word}」が、アクセント句の途中で区切られています（{context}）。"
        "readings.json に読みとアクセントを登録すると、1語として読みます"
        for row in rows
        for word, context in split_words(row.spoken, row.phrases)
    ]


def format_rows(rows: list[ReadingRow]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(f"{row.id} [{row.speaker}] {row.text}")
        source = "（行の reading）" if row.from_line_reading else ""
        lines.append(f"    合成に渡す文: {row.spoken}{source}")
        if row.dictionary:
            hits = "、".join(f"{surface}→{spoken or SILENT}" for surface, spoken in row.dictionary)
            lines.append(f"    辞書: {hits}")
        lines.append(f"    エンジンの読み: {row.reading or '（空。エンジンは読みを返しませんでした）'}")
        if row.accented:
            lines.append(f"    アクセント: {row.accented}")
        lines.append(f"    音声の長さ（計算）: {row.seconds:.2f} 秒（字幕 {chars_per_second(row.text, row.seconds):.1f} 字/秒）")
    lines.append("")
    lines.append("この表は、エンジンが合成に使う読みを示すだけです。読みが文脈に合っているか、アクセントや抑揚が自然かは、自動では判定できません。")
    lines.append("台本と照らして人が確かめてください。直すには、readings.json に「表記」と「読み」を足すか、行に reading を書いてから、もう一度 readings を実行してください。")
    return "\n".join(lines)
