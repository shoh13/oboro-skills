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


def spoken_text(line: Line, readings: dict[str, str]) -> str:
    if line.reading is not None:
        return line.reading
    return replace_surfaces(line.text, readings, lambda surface: readings[surface])
