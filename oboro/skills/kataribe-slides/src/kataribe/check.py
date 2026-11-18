import re

from kataribe.project import Project
from kataribe.reading import replace_surfaces

MAX_LINE_CHARS = 60
MAX_CHARS_PER_SECOND = 7.5
ENGLISH_WORD = re.compile(r"[A-Za-z]{2,}")


def lint_warnings(project: Project) -> list[str]:
    warnings = list(project.warnings)
    for line in project.lines:
        if len(line.text) > MAX_LINE_CHARS:
            warnings.append(f"警告: {line.id}: 字幕が {len(line.text)} 字あります（{MAX_LINE_CHARS} 字以内にしてください）")
        if line.reading is None:
            words = _unregistered_words(line.text, project.readings)
            if words:
                warnings.append(f"警告: {line.id}: 読みが未登録の英単語があります: {', '.join(words)}")
    return warnings


def _unregistered_words(text: str, readings: dict[str, str]) -> list[str]:
    remaining = replace_surfaces(text, readings, lambda surface: " ")
    return list(dict.fromkeys(ENGLISH_WORD.findall(remaining)))


def speed_warnings(timeline: dict) -> list[str]:
    warnings = []
    for line in timeline["lines"]:
        speed = len(line["text"]) / max(line["end"] - line["start"], 0.1)
        if speed > MAX_CHARS_PER_SECOND:
            warnings.append(f"警告: {line['id']}: 字幕の表示速度が {speed:.1f} 字/秒です（{MAX_CHARS_PER_SECOND} 字/秒以内にしてください）")
    return warnings
