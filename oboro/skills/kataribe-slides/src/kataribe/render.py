import base64
import html
import json
import re
from importlib import resources

from kataribe.project import Project
from kataribe.voices import VOICES, terms_links


def _asset(name: str) -> str:
    return (resources.files("kataribe") / "player" / name).read_text(encoding="utf-8")


def _icon(name: str, extra_class: str = "") -> str:
    """icons/<name>.svg（Lucide）の中身を、ボタンに埋め込めるインラインSVGにする。"""
    source = (resources.files("kataribe") / "player" / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    body = re.search(r"<svg[^>]*>(.*)</svg>", source, re.S).group(1)
    body = re.sub(r"\s*\n\s*", "", body.strip())
    classes = f"kataribe-icon {extra_class}".strip()
    return f'<svg class="{classes}" viewBox="0 0 24 24" aria-hidden="true">{body}</svg>'


def render_about(project: Project) -> str:
    credit = "".join(f"<p>{html.escape(VOICES[voice])}</p>" for voice in project.voices)
    links = "".join(
        f'<li><a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{html.escape(label)}</a></li>'
        for label, url in terms_links(project.voices)
    )
    description = (
        f'<section data-about="description"><h2>説明</h2><p>{html.escape(project.description)}</p></section>'
        if project.description and project.description.strip()
        else ""
    )
    sources = (
        '<section data-about="sources"><h2>出典</h2><ul>'
        + "".join(
            f'<li><a href="{html.escape(source.url)}" target="_blank" rel="noopener noreferrer">{html.escape(source.title)}</a></li>'
            for source in project.sources
        )
        + "</ul></section>"
        if project.sources
        else ""
    )
    return (
        '<footer id="kataribe-about">'
        f"{description}{sources}"
        f'<section data-about="credits"><h2>クレジット</h2>{credit}</section>'
        f'<section data-about="terms"><h2>利用条件</h2><ul>{links}</ul></section>'
        "</footer>"
    )


def render_html(project: Project, timeline: dict, audio_aac: bytes, cast: list[dict] | None = None) -> str:
    timeline_json = json.dumps(timeline, ensure_ascii=False).replace("<", "\\u003c")
    cast_json = json.dumps(cast or [], ensure_ascii=False).replace("<", "\\u003c")
    replacements = {
        "{{TITLE}}": html.escape(project.title),
        "{{CSS}}": _asset("player.css"),
        "{{SCENES}}": project.scenes_html,
        "{{ABOUT}}": render_about(project),
        "{{AUDIO}}": base64.b64encode(audio_aac).decode("ascii"),
        "{{TIMELINE}}": timeline_json,
        "{{CAST}}": cast_json,
        "{{CASTJS}}": _asset("cast.js"),
        "{{JS}}": _asset("player.js"),
    }
    page = re.sub(r"\{\{ICON:([a-z-]+)(?::([a-z-]+))?\}\}", lambda m: _icon(m.group(1), m.group(2) or ""), _asset("page.html"))
    return re.sub(r"\{\{[A-Z]+\}\}", lambda m: replacements[m.group(0)], page)


def render_transcript(project: Project) -> str:
    parts = [f"# {project.title}", ""]
    for chapter in project.chapters:
        parts += [f"## {chapter.title}", ""]
        parts += [f"- {line.text}" for line in project.lines if line.chapter_id == chapter.id]
        parts.append("")
    return "\n".join(parts)
