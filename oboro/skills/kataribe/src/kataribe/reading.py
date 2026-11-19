import re
from collections.abc import Callable

from kataribe.project import Line


def replace_surfaces(text: str, readings: dict[str, str], replacement: Callable[[str], str]) -> str:
    """辞書の表記を、長いものを先に1回の走査で置き換える。置き換えた結果は再び置き換えない。"""
    surfaces = sorted((surface for surface in readings if surface), key=len, reverse=True)
    if not surfaces:
        return text
    pattern = re.compile("|".join(re.escape(surface) for surface in surfaces))
    return pattern.sub(lambda match: replacement(match.group(0)), text)


def spoken_text_with_hits(line: Line, readings: dict[str, str]) -> tuple[str, tuple[str, ...]]:
    """合成に渡す文と、置き換えた辞書の表記（初めて当たった順、重複なし）。行の reading を使うときは辞書を使わない。"""
    if line.reading is not None:
        return line.reading, ()
    hits: list[str] = []

    def replace(surface: str) -> str:
        hits.append(surface)
        return readings[surface]

    return replace_surfaces(line.text, readings, replace), tuple(dict.fromkeys(hits))


def spoken_text(line: Line, readings: dict[str, str]) -> str:
    return spoken_text_with_hits(line, readings)[0]
