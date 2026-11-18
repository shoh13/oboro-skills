import json
from pathlib import Path

from kataribe.project import Project
from kataribe.voices import VOICES, terms_links

EXTRAS_DIR = "extras"


def _vtt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def render_vtt(timeline: dict) -> str:
    parts = ["WEBVTT", ""]
    for line in timeline["lines"]:
        parts += [f"{_vtt_time(line['start'])} --> {_vtt_time(line['end'])}", line["text"], ""]
    return "\n".join(parts)


def render_terms(project: Project) -> str:
    links = "\n".join(f"- {label}: {url}" for label, url in terms_links(project.voices))
    return (
        f"このファイルは、音声（audio.wav）と、そこから作る動画に必ず添えてください。\n\n"
        f"クレジット: {'、'.join(VOICES[voice] for voice in project.voices)}\n\n"
        f"利用条件（公開・共有の前に、最新の内容を確認してください）:\n{links}\n"
    )


def extras_timeline(project: Project, timeline: dict) -> dict:
    return {
        **timeline,
        "title": project.title,
        "credit": [VOICES[voice] for voice in project.voices],
        "sources": [{"title": source.title, "url": source.url} for source in project.sources],
    }


def write_extras(out: Path, project: Project, timeline: dict, audio: bytes) -> None:
    directory = out / EXTRAS_DIR
    directory.mkdir(exist_ok=True)
    (directory / "audio.wav").write_bytes(audio)
    (directory / "captions.vtt").write_text(render_vtt(timeline), encoding="utf-8")
    (directory / "timeline.json").write_text(json.dumps(extras_timeline(project, timeline), ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "TERMS.txt").write_text(render_terms(project), encoding="utf-8")
