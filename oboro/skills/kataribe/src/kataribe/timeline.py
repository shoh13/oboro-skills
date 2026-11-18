import wave
from pathlib import Path

from kataribe.project import Project


def measure_seconds(wav: Path) -> float:
    with wave.open(str(wav), "rb") as f:
        return f.getnframes() / f.getframerate()


def build_timeline(project: Project, durations: list[float], mouths: list[str] | None = None) -> dict:
    """mouths は、行ごとの口の段階の文字列（1/30 秒ごと）。省略すると、口はずっと閉じる。"""
    lines = []
    start = 0.0
    mouths = mouths if mouths is not None else [""] * len(durations)
    for line, length, mouth in zip(project.lines, durations, mouths, strict=True):
        lines.append(
            {
                "id": line.id,
                "chapter": line.chapter_id,
                "scene": line.scene_id,
                "speaker": line.speaker,
                "expression": line.expression,
                "mouth": mouth,
                "text": line.text,
                "start": start,
                "end": start + length,
            }
        )
        start += length

    scenes = _spans(lines, "scene")
    chapter_spans = {span["id"]: span for span in _spans(lines, "chapter")}
    chapters = [
        {"id": chapter.id, "title": chapter.title, "start": chapter_spans[chapter.id]["start"], "end": chapter_spans[chapter.id]["end"]}
        for chapter in project.chapters
    ]
    return {"duration": start, "chapters": chapters, "scenes": scenes, "lines": lines}


def _spans(lines: list[dict], key: str) -> list[dict]:
    spans: dict[str, dict] = {}
    for line in lines:
        span = spans.setdefault(line[key], {"id": line[key], "start": line["start"], "end": line["end"]})
        span["end"] = line["end"]
    return list(spans.values())
