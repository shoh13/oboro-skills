import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from kataribe.adapters import voicevox
from kataribe.images import ImageError, inline_images
from kataribe.scenes import SceneError, check_scene_attributes, check_scene_sections
from kataribe.voices import allowed_voices

MAX_VOICES = 2  # 立ち絵は左右に1人ずつ


class ProjectError(Exception):
    pass


@dataclass(frozen=True)
class Line:
    id: str
    chapter_id: str
    scene_id: str
    speaker: str | None  # None は地の文（スライドだけ）
    expression: str | None
    text: str
    reading: str | None
    path: str  # script.json の中の場所（例: chapters[0].scenes[0].lines[1]）


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str


@dataclass(frozen=True)
class Scene:
    id: str
    chapter_id: str
    title: str | None  # スライドの見出し（任意）


@dataclass(frozen=True)
class Source:
    title: str
    url: str


@dataclass(frozen=True)
class AccentWord:
    """readings.json の {"reading": …, "accent": …} の項目。エンジンのユーザー辞書に、表記も発音も reading の語として登録する。"""

    surface: str  # readings.json の表記（台本の中で置き換える文字列）
    reading: str  # カタカナの読み
    accent: int  # アクセント核の拍の位置（1始まり）。0 は平板型


@dataclass(frozen=True)
class Project:
    title: str
    description: str | None
    sources: tuple[Source, ...]
    chapters: tuple[Chapter, ...]
    lines: tuple[Line, ...]
    scenes_html: str
    readings: dict[str, str]  # 表記 → 読み。アクセントを指定した項目も読みだけを持つ
    warnings: tuple[str, ...] = ()
    scenes: tuple[Scene, ...] = ()
    accents: tuple[AccentWord, ...] = ()

    @property
    def voices(self) -> tuple[str, ...]:
        """使った声（話者）。台本で初めて出た順。地の文は含まない。"""
        return tuple(dict.fromkeys(line.speaker for line in self.lines if line.speaker is not None))


def accent_words(project: Project) -> tuple[tuple[str, int], ...]:
    """ユーザー辞書に登録する（読み, アクセント）。同じ読みは1回だけ（load_project が、違うアクセントを拒む）。"""
    return tuple(dict.fromkeys((word.reading, word.accent) for word in project.accents))


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"{path.name} が見つかりません: {path}") from None
    except json.JSONDecodeError as e:
        raise ProjectError(f"{path.name} が正しいJSONではありません: {e}") from None


def _text_field(script: dict, key: str) -> str:
    value = script.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"script.json の {key} が必要です（空でない文字列）")
    return value


def _field(parent: dict, key: str, path: str, kind: type, label: str):
    where = f"{path}.{key}" if path else key
    if key not in parent:
        raise ProjectError(f"script.json の {where} が必要です")
    value = parent[key]
    if not isinstance(value, kind):
        raise ProjectError(f"script.json の {where} は{label}である必要があります")
    return value


def _items(parent: dict, key: str, path: str) -> list[tuple[str, dict]]:
    where = f"{path}.{key}" if path else key
    entries = _field(parent, key, path, list, "配列")
    items = []
    for index, entry in enumerate(entries):
        item_path = f"{where}[{index}]"
        if not isinstance(entry, dict):
            raise ProjectError(f"script.json の {item_path} はオブジェクトである必要があります")
        items.append((item_path, entry))
    return items


def _has_host(url: str) -> bool:
    try:
        return bool(urlsplit(url).hostname)
    except ValueError:
        return False


def _load_sources(script: dict) -> tuple[Source, ...]:
    if "sources" not in script:
        return ()
    sources = []
    for path, entry in _items(script, "sources", ""):
        title = _field(entry, "title", path, str, "文字列")
        url = _field(entry, "url", path, str, "文字列")
        if not title.strip():
            raise ProjectError(f"script.json の {path}.title は空にできません")
        if not url.lower().startswith(("http://", "https://")):
            raise ProjectError(f"script.json の {path}.url は http または https で始まる URL である必要があります: {url!r}")
        if not _has_host(url):
            raise ProjectError(f"script.json の {path}.url にホスト名がありません: {url!r}")
        sources.append(Source(title=title, url=url))
    return tuple(sources)


def _speaker(line: dict, path: str, old_voice: bool, allowed: tuple[str, ...], slides: bool) -> str | None:
    if "speaker" not in line:
        if slides:
            return None  # 地の文
        if old_voice:
            raise ProjectError(
                f"script.json の {path}.speaker が必要です（冒頭の voice は使えません。各行に speaker を書いてください）"
            )
        raise ProjectError(f"script.json の {path}.speaker が必要です（speaker のない地の文は、slides でだけ使えます）")
    speaker = _field(line, "speaker", path, str, "文字列")
    if speaker not in allowed:
        raise ProjectError(
            f"script.json の {path}.speaker「{speaker}」は許可リストにありません。使える声: {', '.join(allowed)}"
        )
    return speaker


def _expression(line: dict, path: str) -> str | None:
    expression = line.get("expression")
    if expression is None:
        return None
    if not isinstance(expression, str) or not expression.strip():
        raise ProjectError(f"script.json の {path}.expression は空でない文字列である必要があります")
    return expression


def _unique_id(entry: dict, path: str, kind: str, seen: dict[str, str]) -> str:
    value = _field(entry, "id", path, str, "文字列")
    if not value.strip():
        raise ProjectError(f"script.json の {path}.id は空にできません（{kind}ID）")
    if value in seen:
        raise ProjectError(f"script.json の {kind}ID「{value}」が重複しています: {seen[value]} と {path}")
    seen[value] = path
    return value


def _scene_title(scene: dict, path: str) -> str | None:
    title = scene.get("title")
    if title is None:
        return None
    if not isinstance(title, str) or not title.strip():
        raise ProjectError(f"script.json の {path}.title は空でない文字列である必要があります")
    return title


def _accent_word(surface: str, entry: dict) -> AccentWord:
    where = f"readings.json の「{surface}」"
    unknown = sorted(set(entry) - {"reading", "accent"})
    if unknown:
        raise ProjectError(f"{where}に使えないキーがあります: {', '.join(unknown)}（使えるのは reading と accent）")
    if "reading" not in entry or "accent" not in entry:
        raise ProjectError(f"{where}には reading と accent の両方が必要です")
    reading, accent = entry["reading"], entry["accent"]
    if not isinstance(reading, str) or not voicevox.KATAKANA.fullmatch(reading):
        raise ProjectError(f"{where}の reading はカタカナ（長音「ー」を含む）だけの文字列である必要があります: {reading!r}")
    if not isinstance(accent, int) or isinstance(accent, bool):
        raise ProjectError(f"{where}の accent は整数である必要があります: {accent!r}")
    moras = voicevox.mora_count(reading)
    if not 0 <= accent <= moras:
        raise ProjectError(f"{where}の accent は 0（平板型）から {moras}（「{reading}」の拍の数）までです: {accent}")
    return AccentWord(surface=surface, reading=reading, accent=accent)


def _load_readings(readings: object) -> tuple[dict[str, str], tuple[AccentWord, ...]]:
    """readings.json の値は、読みの文字列か、{"reading": カタカナ, "accent": アクセント核の位置} のオブジェクト。"""
    if not isinstance(readings, dict):
        raise ProjectError("readings.json は JSON のオブジェクトである必要があります")
    spoken: dict[str, str] = {}
    accents: list[AccentWord] = []
    for surface, value in readings.items():
        if isinstance(value, dict):
            word = _accent_word(surface, value)
            accents.append(word)
            spoken[surface] = word.reading
        elif isinstance(value, str):
            spoken[surface] = value
        else:
            raise ProjectError(f"readings.json の「{surface}」の読みは文字列である必要があります")
    first: dict[str, AccentWord] = {}
    for word in accents:
        other = first.setdefault(word.reading, word)
        if other.accent != word.accent:
            raise ProjectError(
                f"readings.json の「{other.surface}」と「{word.surface}」は、同じ読み「{word.reading}」に"
                f"違うアクセント（{other.accent} と {word.accent}）を指定しています"
            )
    return spoken, tuple(accents)


def load_project(root: Path, slides: bool = False, require_scenes: bool = True) -> Project:
    """台本を読む。slides なら、地の文（speaker のない行）を許し、readings.json と scenes.html を任意にする
    （scenes.html にシーンの section がなければ、そのスライドは図なし）。
    require_scenes が偽なら、scenes.html がなくても読む（readings は画面を使わない）。あれば、いつもどおり検査する。"""
    script = _read_json(root / "script.json")
    if not isinstance(script, dict):
        raise ProjectError("script.json は JSON のオブジェクトである必要があります")
    title = _text_field(script, "title")
    old_voice = "voice" in script
    readings, accents = _load_readings(
        {} if slides and not (root / "readings.json").exists() else _read_json(root / "readings.json")
    )
    scenes_present = True
    try:
        scenes_html = (root / "scenes.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        if not slides and require_scenes:
            raise ProjectError(f"scenes.html が見つかりません: {root}") from None
        scenes_present = False
        scenes_html = ""

    chapters = []
    scenes = []
    lines = []
    speakers: list[str] = []
    allowed = allowed_voices()
    seen_chapters: dict[str, str] = {}
    seen_scenes: dict[str, str] = {}
    chapter_entries = _items(script, "chapters", "")
    if not chapter_entries:
        raise ProjectError("script.json の chapters に章が1つもありません")
    for chapter_path, chapter in chapter_entries:
        chapter_id = _unique_id(chapter, chapter_path, "章", seen_chapters)
        chapters.append(Chapter(id=chapter_id, title=_field(chapter, "title", chapter_path, str, "文字列")))
        lines_before = len(lines)
        for scene_path, scene in _items(chapter, "scenes", chapter_path):
            scene_id = _unique_id(scene, scene_path, "シーン", seen_scenes)
            scenes.append(Scene(id=scene_id, chapter_id=chapter_id, title=_scene_title(scene, scene_path)))
            for index, (line_path, line) in enumerate(_items(scene, "lines", scene_path)):
                reading = line.get("reading")
                if reading is not None and not isinstance(reading, str):
                    raise ProjectError(f"script.json の {line_path}.reading は文字列である必要があります")
                if reading is not None and not reading.strip():
                    raise ProjectError(f"script.json の {line_path}.reading は空にできません")
                speaker = _speaker(line, line_path, old_voice, allowed, slides)
                if speaker is not None and speaker not in speakers:
                    if len(speakers) == MAX_VOICES:
                        raise ProjectError(
                            f"script.json の {line_path}.speaker「{speaker}」: 1本の動画で使える話者は{MAX_VOICES}人までです"
                            f"（使っている話者: {'、'.join(speakers)}）"
                        )
                    speakers.append(speaker)
                expression = _expression(line, line_path)
                if speaker is None and expression is not None:
                    raise ProjectError(f"script.json の {line_path}.expression: 地の文（speaker のない行）には表情を付けられません")
                text = _field(line, "text", line_path, str, "文字列")
                if not text.strip():
                    raise ProjectError(f"script.json の {line_path}.text は空にできません")
                lines.append(
                    Line(
                        id=f"{scene_id}-{index}",
                        chapter_id=chapter_id,
                        scene_id=scene_id,
                        speaker=speaker,
                        expression=expression,
                        text=text,
                        reading=reading,
                        path=line_path,
                    )
                )
        if len(lines) == lines_before:
            raise ProjectError(f"script.json の {chapter_path} に行（lines）が1つもありません")
    line_counts: dict[str, int] = {}
    for line in lines:
        line_counts[line.scene_id] = line_counts.get(line.scene_id, 0) + 1
    try:
        warnings = check_scene_sections(scenes_html, seen_scenes, required=not slides and scenes_present)
        check_scene_attributes(scenes_html, line_counts)
        scenes_html = inline_images(scenes_html, root)
    except (SceneError, ImageError) as e:
        raise ProjectError(str(e)) from None
    description = script.get("description")
    if description is not None and not isinstance(description, str):
        raise ProjectError("script.json の description は文字列である必要があります")
    sources = _load_sources(script)
    return Project(
        title=title,
        description=description,
        sources=sources,
        chapters=tuple(chapters),
        lines=tuple(lines),
        scenes_html=scenes_html,
        readings=readings,
        warnings=tuple(warnings),
        scenes=tuple(scenes),
        accents=accents,
    )
