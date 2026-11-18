import re
from html.parser import HTMLParser

ATTRIBUTES = ("data-at", "data-out", "data-focus")
NUMBER = re.compile(r"[0-9]+", re.ASCII)


class SceneError(Exception):
    pass


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scene: str | None = None
        self.depth = 0
        self.found: list[tuple[str, str, int, dict[str, str | None]]] = []
        self.sections: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "section":
            if self.scene is None:
                scene = values.get("data-scene")
                if scene is not None:
                    self.scene = scene
                    self.depth = 1
                    self.sections.append((scene, self.getpos()[0]))
            else:
                self.depth += 1
            return
        if self.scene is None:
            return
        found: dict[str, str | None] = {}
        for name, value in attrs:
            if name in ATTRIBUTES and name not in found:
                found[name] = value
        if found:
            self.found.append((self.scene, tag, self.getpos()[0], found))

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self.scene is not None:
            self.depth -= 1
            if self.depth == 0:
                self.scene = None


def _numbers(raw: str | None) -> list[int] | None:
    parts = (raw or "").split(",")
    if not all(NUMBER.fullmatch(part.strip()) for part in parts):
        return None
    return [int(part.strip()) for part in parts]


def check_scene_attributes(scenes_html: str, line_counts: dict[str, int]) -> None:
    collector = _Collector()
    collector.feed(scenes_html)
    collector.close()
    for scene, tag, line, attributes in collector.found:
        count = line_counts.get(scene)
        if count is None:
            continue
        where = f"scenes.html の{line}行目: シーン「{scene}」の <{tag}>"
        parsed: dict[str, list[int]] = {}
        for name, raw in attributes.items():
            value = raw or ""
            numbers = _numbers(raw)
            if numbers is not None and name != "data-focus" and len(numbers) != 1:
                numbers = None
            if numbers is None:
                kind = "0以上の整数をカンマで区切った値" if name == "data-focus" else "0以上の整数"
                raise SceneError(f'{where} の {name}="{value}" は、{kind}である必要があります')
            if any(number >= count for number in numbers):
                raise SceneError(f'{where} の {name}="{value}" は、このシーンの行番号（0〜{count - 1}）の範囲外です')
            parsed[name] = numbers
        if "data-out" in parsed and parsed["data-out"][0] <= parsed.get("data-at", [0])[0]:
            raise SceneError(
                f'{where} の data-out="{attributes["data-out"]}" は、data-at（{parsed.get("data-at", [0])[0]}）より後の行にしてください'
            )


def check_scene_sections(scenes_html: str, scene_places: dict[str, str], required: bool = True) -> list[str]:
    """台本のシーンと scenes.html の section を突き合わせる。欠落（required のとき）と重複は SceneError、余りは警告を返す。"""
    collector = _Collector()
    collector.feed(scenes_html)
    collector.close()
    first_line: dict[str, int] = {}
    for scene, line in collector.sections:
        if scene == "":
            continue
        if scene in first_line:
            raise SceneError(
                f'scenes.html の{line}行目: シーン「{scene}」の <section data-scene="{scene}"> は、'
                f"{first_line[scene]}行目にもあり、重複しています"
            )
        first_line[scene] = line
    for scene, place in scene_places.items():
        if required and scene not in first_line:
            raise SceneError(
                f'script.json の {place} のシーン「{scene}」に対応する <section data-scene="{scene}"> が、scenes.html にありません'
            )
    warnings = []
    for scene, line in collector.sections:
        if scene not in scene_places:
            label = "data-scene が空の" if scene == "" else f"シーン「{scene}」の"
            warnings.append(f"警告: scenes.html の{line}行目: {label} <section> は、台本のどのシーンにも対応しません")
    return warnings


def section_ids(scenes_html: str) -> set[str]:
    """scenes.html にある、トップレベルの <section data-scene> の ID。"""
    collector = _Collector()
    collector.feed(scenes_html)
    collector.close()
    return {scene for scene, _ in collector.sections}
