"""スライド（kataribe slides）。

台本の地の文（speaker のない行）を解説として本文に出し、立ち絵のキャラクターが表情を変えながら
コメントしていく PowerPoint（out/slides.pptx）を作る。音声は合成しない。コメントは、バラエティ番組のテロップの
ように、解説の枠の下に、話者のテーマカラーの大きな文字で出す（左右の詰めでも話者を区別する）。

台本の1行が1枚のスライドになる（シーンの行を進めるたびに、地の文が積み上がり、テロップと表情が変わる）。
1つのシーンのスライドは、見出しと積み上がった地の文が同じなので、続けてめくると1枚が段階的に進むように見える。
scenes.html にシーンの section があれば、動画と同じ図を、その行の状態で撮って左に置き、地の文を右に置く（diagrams.py）。
最初に表紙、最後にクレジットのスライドを付ける。

地の文のカードは、文字の大きさに合わせて高さを決めるため、行の高さを固定（文字の大きさの LINE 倍）にし、
文字の幅は、全角を1字、半角を HALF_WIDTH 字として見積もる（フォントによらず、はみ出さない側に倒し、半行の予備も取る）。
テロップは枠を持たず、下端をそろえて上へ伸ばすので、見積もりが外れても枠からはみ出すことはない。
"""

import base64
import io
import math
import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from kataribe.art import DEFAULT_FACE, build_cast, used_faces
from kataribe.definitions import load_definitions
from kataribe.diagrams import render_diagrams, scenes_with_diagram
from kataribe.output import write_output
from kataribe.project import Line, Project, load_project



def slide_font() -> str:
    """文字のフォント。既定は Google スライドで使える Noto Sans JP（KATARIBE_SLIDES_FONT で差し替え）。

    Google スライドは、Google Fonts にない Hiragino Sans や Yu Gothic を Arial などに置き換える。
    """
    return os.environ.get("KATARIBE_SLIDES_FONT") or "Noto Sans JP"


NAVY = RGBColor(0x1F, 0x2A, 0x44)
INK = RGBColor(0x1F, 0x23, 0x28)
MUTED = RGBColor(0x7A, 0x81, 0x90)
PAPER = RGBColor(0xFF, 0xFF, 0xFF)
TINT = RGBColor(0xF3, 0xF5, 0xF9)
EDGE = RGBColor(0xDD, 0xE2, 0xEA)
ACCENT = RGBColor(0xE8, 0x91, 0x2D)  # 番号の印と章の名前
EMPHASIS = RGBColor(0xB4, 0x5F, 0x0A)  # **強調**（白地で読める濃さ）

# 16:9（13.33 x 7.5 インチ。PowerPoint のワイドと同じ）
SLIDE_W, SLIDE_H = 40 / 3, 7.5
# 立ち絵。全身の高さ FIG_HEIGHT のうち、上端 FIG_TOP から画面の下端までを見せる（下は切り落とす）。
FIG_HEIGHT = 4.0
FIG_TOP = 4.6
FIG_CENTER = 1.55  # 画面の端から立ち絵の中心まで
# 解説の枠は、見た目の白い枠（立ち絵とテロップは、その下端に重なる）。解説の領域は、見出し・地の文・図を収める
# 範囲で、下端を立ち絵の頭（FIG_TOP）にそろえる。地の文と図は、解説の領域からはみ出さない。
PANEL = (0.23, 0.2, SLIDE_W - 0.23, 5.37)  # 左, 上, 右, 下
CONTENT_AREA = (0.23, 0.2, SLIDE_W - 0.23, FIG_TOP)
CONTENT_X = 0.6  # 画面の端から、地の文・図の左右の端まで
CONTENT_TOP = 1.65  # 見出しの下
CONTENT_BOTTOM = CONTENT_AREA[3] - 0.15  # 解説の領域の下端から少し上
# テロップ（コメント）。枠はスライドの中央にそろえ、文字は左の人は左詰め、右の人は右詰めにする。ひとかたまりの解説（地の文から次の地の文の前まで）のコメントは、
# 消さずに上から順に積む。かたまりの全部のコメントで配置を先に決め、最後のコメントの下端を TELOP_BOTTOM に
# そろえるので、めくっても位置が動かない。帯（TELOP_TOP から TELOP_BOTTOM）に入らなければ、文字を小さくする。
TELOP_PT = 28
TELOP_MIN_PT = 18
TELOP_GAP = 0.08
TELOP_LINE = 1.2
TELOP_W = 8.0
TELOP_BOTTOM = 7.3
TELOP_TOP = 5.5  # 帯の上端（解説の枠の下）
TELOP_MIN_CONTRAST = 4.5  # テロップの文字の色と白の、コントラスト比の下限（WCAG の本文の基準）
# 地の文
CURRENT_PT, PAST_PT, DIAGRAM_NARRATION_PT = 20, 15, 18
CARD_PAD_X, CARD_PAD_Y = 0.25, 0.18
BADGE = 0.36  # 番号の丸の直径
BADGE_GAP = 0.16
PARAGRAPH_GAP = 0.18
# 図のあるスライド。解説の領域の左に図（16:9）、右に今の地の文。
DIAGRAM_GAP = 0.25

LINE = 1.5  # 行の高さ（文字の大きさに対する倍率）
HALF_WIDTH = 0.6  # 半角の文字の幅（全角に対する比）
SAFETY = 0.9  # 見積もった幅に対する余裕


# ---------- 文字の見積もりと強調 ----------


def plain(text: str) -> str:
    return text.replace("**", "")


def runs_of(text: str) -> list[tuple[str, bool]]:
    """「**強調**」を、(文字列, 強調か) の並びにする。閉じていない ** は、そのまま文字として残す。"""
    parts = text.split("**")
    if len(parts) % 2 == 0:  # 閉じていない
        parts = [*parts[:-2], parts[-2] + "**" + parts[-1]]
    return [(part, i % 2 == 1) for i, part in enumerate(parts) if part]


def _char_width(char: str) -> float:
    return 1.0 if unicodedata.east_asian_width(char) in ("W", "F", "A") else HALF_WIDTH


def count_lines(text: str, width_in: float, pt: float) -> int:
    """幅 width_in（インチ）に、大きさ pt の文字で折り返したときの行数（見積もり）。"""
    limit = width_in * 72 * SAFETY / pt  # 全角何字ぶんか
    lines = 0
    for chunk in plain(text).split("\n"):
        lines += 1
        used = 0.0
        for char in chunk:
            w = _char_width(char)
            if used + w > limit and used > 0:
                lines += 1
                used = 0.0
            used += w
    return lines


def text_height(text: str, width_in: float, pt: float) -> float:
    return count_lines(text, width_in, pt) * pt * LINE / 72


def telop_height(text: str, pt: float) -> float:
    return count_lines(text, TELOP_W, pt) * pt * TELOP_LINE / 72


def telop_layout(texts: list[str]) -> tuple[float, list[tuple[float, float]], bool]:
    """ひとかたまりのコメントのテロップの、文字の大きさと、各テロップの (上端, 高さ)、帯に収まったか。

    TELOP_PT から2ポイントずつ小さくして、帯に収まる最大の大きさにする（TELOP_MIN_PT でも収まらなければ、その大きさ）。
    """
    pt = TELOP_PT
    while True:
        heights = [telop_height(text, pt) for text in texts]
        total = sum(heights) + TELOP_GAP * max(len(texts) - 1, 0)
        fits = total <= TELOP_BOTTOM - TELOP_TOP
        if fits or pt <= TELOP_MIN_PT:
            break
        pt -= 2
    slots, bottom = [], TELOP_BOTTOM
    for height in reversed(heights):
        slots.append((bottom - height, height))
        bottom -= height + TELOP_GAP
    return pt, slots[::-1], fits


def comment_blocks(project: Project) -> list[list[int]]:
    """ひとかたまりの解説ごとの、コメントの行の番号（project.lines の添字）。シーンの先頭か地の文で区切る。"""
    blocks: list[list[int]] = []
    scene = None
    for index, line in enumerate(project.lines):
        if line.scene_id != scene or line.speaker is None:
            blocks.append([])
            scene = line.scene_id
        if line.speaker is not None:
            blocks[-1].append(index)
    return [block for block in blocks if block]


def column_width() -> float:
    """地の文の段の幅（解説の領域の左右いっぱい。立ち絵は解説の領域より下にいるので、避けなくてよい）。"""
    return SLIDE_W - 2 * CONTENT_X


def card_text_width(width_in: float) -> float:
    return width_in - BADGE - BADGE_GAP - 2 * CARD_PAD_X


def card_height(text: str, width_in: float, pt: float) -> float:
    """カードの高さ。見積もりが外れても収まるよう、半行の予備を足す。"""
    return 2 * CARD_PAD_Y + text_height(text, card_text_width(width_in), pt) + pt * LINE / 72 / 2


def diagram_box() -> tuple[float, float, float, float]:
    """図の x, y, 幅, 高さ。16:9 で、解説の領域の下端に収まる高さにする。"""
    height = CONTENT_BOTTOM - CONTENT_TOP
    return CONTENT_X, CONTENT_TOP, height * 16 / 9, height


def diagram_card_box() -> tuple[float, float, float]:
    """図の右の地の文のカードの x、幅、入る高さ。"""
    diagram_x, _, diagram_w, _ = diagram_box()
    x = diagram_x + diagram_w + DIAGRAM_GAP
    return x, SLIDE_W - CONTENT_X - x, CONTENT_BOTTOM - CONTENT_TOP


# ---------- 検査 ----------


def slide_warnings(project: Project) -> list[str]:
    warnings = list(project.warnings)
    diagrams = scenes_with_diagram(project)
    width = column_width()
    _, card_w, card_room = diagram_card_box()
    for line in project.lines:
        chars = len(plain(line.text))
        if line.speaker is not None:
            continue
        if line.scene_id in diagrams:
            if card_height(line.text, card_w, DIAGRAM_NARRATION_PT) > card_room:
                warnings.append(f"警告: {line.id}: 図のあるスライドの地の文が長く、はみ出します（{chars} 字。短くするか、行を分けてください）")
        elif card_height(line.text, width, CURRENT_PT) > CONTENT_BOTTOM - CONTENT_TOP:
            warnings.append(f"警告: {line.id}: 地の文が長く、1枚に収まりません（{chars} 字。行を分けてください）")
    for block in comment_blocks(project):
        _, _, fits = telop_layout([project.lines[i].text for i in block])
        if not fits:
            first, last = project.lines[block[0]].id, project.lines[block[-1]].id
            warnings.append(
                f"警告: {first}〜{last}: 同じ解説へのコメントが多く（長く）、{TELOP_MIN_PT}pt にしてもテロップが下の帯に収まりません"
                "（コメントを減らすか、間に地の文を入れてください）"
            )
    return warnings


# ---------- 立ち絵 ----------


def faces_at(lines: tuple[Line, ...], index: int, speakers: list[str]) -> dict[str, str]:
    """行 index の時点の、話者ごとの表情（cast.js の facesAt と同じ規則。地の文は飛ばす）。"""
    faces = {speaker: DEFAULT_FACE for speaker in speakers}
    for line in lines[: index + 1]:
        if line.speaker is not None:
            faces[line.speaker] = line.expression or DEFAULT_FACE
    return faces


def _layer_image(layer: dict) -> Image.Image:
    data = base64.b64decode(layer["src"].split(",", 1)[1])
    return Image.open(io.BytesIO(data)).convert("RGBA")


def figure_png(entry: dict, face: str) -> tuple[bytes, float]:
    """表情 face の立ち絵を、口を閉じ・目を開けた1枚の PNG にする。画面の下端より下は切り落とす。

    返すのは PNG と、縦横比（幅 / 高さ、切り落とした後）。中央を向くように、必要なら左右を反転する。
    """
    resolved = entry["faces"][face]
    active = set(entry["base"]) | set(resolved["layers"]) | {resolved["mouth"][0]}
    boxes = list(entry["layers"].values())
    left, top = min(b["x"] for b in boxes), min(b["y"] for b in boxes)
    right, bottom = max(b["x"] + b["w"] for b in boxes), max(b["y"] + b["h"] for b in boxes)
    canvas = Image.new("RGBA", (right - left, bottom - top))
    for path, layer in entry["layers"].items():  # 重ねる順
        if path not in active:
            continue
        image = _layer_image(layer)
        at = (layer["x"] - left, layer["y"] - top)
        if layer["blend"] == "multiply":
            region = canvas.crop((at[0], at[1], at[0] + image.width, at[1] + image.height))
            multiplied = ImageChops.multiply(region.convert("RGB"), image.convert("RGB")).convert("RGBA")
            multiplied.putalpha(region.getchannel("A"))
            canvas.paste(multiplied, at, image)
        else:
            canvas.alpha_composite(image, at)
    if entry["side"] == entry["facing"]:
        canvas = canvas.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    visible = (SLIDE_H - FIG_TOP) / FIG_HEIGHT
    canvas = canvas.crop((0, 0, canvas.width, math.ceil(canvas.height * visible)))
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue(), canvas.width / canvas.height


# ---------- 図形と文字 ----------


def _font(run, size: float, color: RGBColor, bold: bool = False) -> None:
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea"):
        element = rpr.find(qn(tag))
        if element is None:
            element = rpr.makeelement(qn(tag), {})
            rpr.append(element)
        element.set("typeface", slide_font())


def _write(paragraph, text: str, size: float, color: RGBColor, bold: bool = False, emphasis: RGBColor | None = None) -> None:
    """段落に文字を足す。行の高さは固定にする（見積もりと合わせるため）。**強調** は太字にし、emphasis の色にする。"""
    paragraph.line_spacing = Pt(size * LINE)
    for part, strong in runs_of(text):
        run = paragraph.add_run()
        run.text = part
        _font(run, size, (emphasis or color) if strong else color, bold=bold or strong)


def _frame(shape, pad_x: float = 0, pad_y: float = 0, anchor=MSO_ANCHOR.TOP):
    frame = shape.text_frame
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = Inches(pad_x)
    frame.margin_top = frame.margin_bottom = Inches(pad_y)
    return frame


def _text_box(slide, x: float, y: float, w: float, h: float, name: str):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    box.name = name
    return _frame(box)


def _shape(slide, kind, x: float, y: float, w: float, h: float, name: str, fill: RGBColor, line: RGBColor | None = None, line_pt: float = 1):
    shape = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.name = name
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_pt)
    shape.shadow.inherit = False
    return shape


def _luminance(rgb: tuple[int, ...]) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_with_white(rgb: tuple[int, ...]) -> float:
    return 1.05 / (_luminance(rgb) + 0.05)


def telop_color(color: str) -> RGBColor:
    """定義のテーマカラー（#rrggbb）を、白との比が TELOP_MIN_CONTRAST 以上になるまで暗くした色。

    黄色のような淡い色も、明るい地の上で文字として読める濃さにする。もとから濃い色は変えない。
    """
    rgb = tuple(int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    scale = 1.0
    while contrast_with_white(tuple(round(c * scale) for c in rgb)) < TELOP_MIN_CONTRAST:
        scale -= 0.02
    return RGBColor(*(round(c * scale) for c in rgb))


def _background(slide, color: RGBColor) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


# ---------- スライド ----------


@dataclass(frozen=True)
class _Paragraph:
    number: int  # シーンの中の地の文の番号（1から）
    text: str
    current: bool


class _Deck:
    def __init__(self, project: Project, cast: list[dict], diagrams: dict[int, bytes]):
        self.project = project
        self.cast = cast
        self.diagrams = diagrams
        self.speakers = [entry["speaker"] for entry in cast]
        self.width = column_width()
        self.blocks = comment_blocks(project)
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(SLIDE_W), Inches(SLIDE_H)
        self.blank = self.prs.slide_layouts[6]
        self.figures: dict[tuple[str, str], tuple[bytes, float]] = {}

    def figure(self, entry: dict, face: str) -> tuple[bytes, float]:
        key = (entry["speaker"], face)
        if key not in self.figures:
            self.figures[key] = figure_png(entry, face)
        return self.figures[key]

    def add_figure(self, slide, entry: dict, face: str) -> None:
        png, aspect = self.figure(entry, face)
        height = SLIDE_H - FIG_TOP
        width = height * aspect
        center = FIG_CENTER if entry["side"] == "left" else SLIDE_W - FIG_CENTER
        picture = slide.shapes.add_picture(io.BytesIO(png), Inches(center - width / 2), Inches(FIG_TOP), Inches(width), Inches(height))
        picture.name = f"立ち絵 {entry['speaker']}（{face}）"

    def add_telop(self, slide, entry: dict, text: str, top: float, height: float, pt: float, line_id: str) -> None:
        """コメントのテロップ。枠はスライドの中央にそろえ、文字は話者の側に詰めて、話者のテーマカラーで書く。

        縁取りは Google スライドで表示されないので付けない（解説の枠の下の、無地の地に置いて読ませる）。
        **強調** は、地の文と同じ強調の色にする。下端をそろえるので、見積もりより行が増えても、上の隙間へ伸びる。
        """
        left = entry["side"] == "left"
        frame = _text_box(slide, (SLIDE_W - TELOP_W) / 2, top, TELOP_W, height, f"テロップ {entry['speaker']}（{line_id}）")
        frame.vertical_anchor = MSO_ANCHOR.BOTTOM
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.LEFT if left else PP_ALIGN.RIGHT
        _write(paragraph, text, pt, telop_color(entry["color"]), bold=True, emphasis=EMPHASIS)
        paragraph.line_spacing = Pt(pt * TELOP_LINE)

    def add_panel(self, slide) -> None:
        """見出しと地の文・図を囲む白い枠（立ち絵とテロップは、この外と上に重ねる）。"""
        left, top, right, bottom = PANEL
        panel = _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, left, top, right - left, bottom - top, "解説の枠", PAPER, EDGE, 1)
        panel.adjustments[0] = 0.04

    def add_heading(self, slide, chapter: str, title: str | None) -> None:
        frame = _text_box(slide, 0.6, 0.42, SLIDE_W - 1.2, 1.1, "見出し")
        _write(frame.paragraphs[0], chapter if title is not None else "", 13, ACCENT, bold=True)
        _write(frame.add_paragraph(), title if title is not None else chapter, 30, NAVY, bold=True)

    def add_badge(self, slide, x: float, y: float, number: int, current: bool) -> None:
        badge = _shape(slide, MSO_SHAPE.OVAL, x, y, BADGE, BADGE, f"番号 {number}", ACCENT if current else EDGE)
        paragraph = _frame(badge, 0, 0, MSO_ANCHOR.MIDDLE).paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        _write(paragraph, str(number), 12, PAPER if current else MUTED, bold=True)
        paragraph.line_spacing = 1.0

    def add_card(self, slide, x: float, y: float, w: float, paragraph: _Paragraph, pt: float) -> float:
        """今の地の文（オレンジの番号の印と、濃く大きな文字。解説の枠の中に置くので、背景は付けない）。高さを返す。"""
        h = card_height(paragraph.text, w, pt)
        self.add_badge(slide, x + CARD_PAD_X, y + CARD_PAD_Y + (pt * LINE / 72 - BADGE) / 2, paragraph.number, True)
        frame = _text_box(slide, x + CARD_PAD_X + BADGE + BADGE_GAP, y + CARD_PAD_Y, card_text_width(w), h - 2 * CARD_PAD_Y, f"地の文 {paragraph.number}")
        _write(frame.paragraphs[0], paragraph.text, pt, INK, emphasis=EMPHASIS)
        return h

    def add_past(self, slide, x: float, y: float, w: float, paragraph: _Paragraph) -> float:
        """前の地の文（小さく薄く、番号の印は灰色）。高さを返す。"""
        h = text_height(paragraph.text, card_text_width(w), PAST_PT)
        self.add_badge(slide, x + CARD_PAD_X, y + (PAST_PT * LINE / 72 - BADGE) / 2, paragraph.number, False)
        frame = _text_box(slide, x + CARD_PAD_X + BADGE + BADGE_GAP, y, card_text_width(w), h, f"地の文 {paragraph.number}")
        _write(frame.paragraphs[0], paragraph.text, PAST_PT, MUTED)
        return h

    def paragraph_height(self, paragraph: _Paragraph) -> float:
        if paragraph.current:
            return card_height(paragraph.text, self.width, CURRENT_PT)
        return text_height(paragraph.text, card_text_width(self.width), PAST_PT)

    def add_narration(self, slide, paragraphs: list[_Paragraph]) -> None:
        """図のないスライド。前の地の文を小さく、今の地の文をカードにして上から積む。入らなければ古いものから省く。"""
        x = SLIDE_W / 2 - self.width / 2
        shown = list(paragraphs)
        while len(shown) > 1 and sum(map(self.paragraph_height, shown)) + PARAGRAPH_GAP * (len(shown) - 1) > CONTENT_BOTTOM - CONTENT_TOP:
            shown.pop(0)
        y = CONTENT_TOP
        for paragraph in shown:
            if paragraph.current:
                y += self.add_card(slide, x, y, self.width, paragraph, CURRENT_PT)
            else:
                y += self.add_past(slide, x, y, self.width, paragraph)
            y += PARAGRAPH_GAP

    def add_diagram(self, slide, png: bytes, current: _Paragraph | None) -> None:
        """図のあるスライド。左に図、右に今の地の文だけを置く。"""
        x, y, w, h = diagram_box()
        picture = slide.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), Inches(w), Inches(h))
        picture.name = "図"
        if current is not None:
            card_x, card_w, _ = diagram_card_box()
            self.add_card(slide, card_x, y, card_w, current, DIAGRAM_NARRATION_PT)

    def add_step(self, index: int) -> None:
        project = self.project
        line = project.lines[index]
        scene = next(s for s in project.scenes if s.id == line.scene_id)
        chapter = next(c.title for c in project.chapters if c.id == line.chapter_id)
        shown = [i for i, other in enumerate(project.lines) if other.scene_id == scene.id and i <= index]
        narration = [i for i in shown if project.lines[i].speaker is None]
        latest = narration[-1] if narration else None
        paragraphs = [_Paragraph(n + 1, project.lines[i].text, i == latest) for n, i in enumerate(narration)]

        slide = self.prs.slides.add_slide(self.blank)
        _background(slide, TINT)
        self.add_panel(slide)
        self.add_heading(slide, chapter, scene.title)
        if index in self.diagrams:
            self.add_diagram(slide, self.diagrams[index], paragraphs[-1] if paragraphs else None)
        else:
            self.add_narration(slide, paragraphs)

        # 立ち絵と、今のかたまりの今の行までのコメントのテロップ（立ち絵の上に重ねる）
        faces = faces_at(project.lines, index, self.speakers)
        for entry in self.cast:
            self.add_figure(slide, entry, faces[entry["speaker"]])
        block = next((b for b in self.blocks if index in b), None)  # 地の文の行なら None（テロップを出さない）
        if block is not None:
            pt, slots, _ = telop_layout([project.lines[i].text for i in block])
            entries = {entry["speaker"]: entry for entry in self.cast}
            for i, (top, height) in zip(block, slots, strict=True):
                if i <= index:
                    said = project.lines[i]
                    self.add_telop(slide, entries[said.speaker], said.text, top, height, pt, said.id)

        slide.notes_slide.notes_text_frame.text = f"{line.speaker or '地の文'}: {plain(line.text)}"

    def add_cover(self) -> None:
        slide = self.prs.slides.add_slide(self.blank)
        _background(slide, NAVY)
        frame = _text_box(slide, SLIDE_W / 2 - self.width / 2, 1.3, self.width, 3.2, "表紙")
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        title = frame.paragraphs[0]
        title.alignment = PP_ALIGN.CENTER
        _write(title, self.project.title, 40, PAPER, bold=True, emphasis=ACCENT)
        if self.project.description and self.project.description.strip():
            description = frame.add_paragraph()
            description.alignment = PP_ALIGN.CENTER
            description.space_before = Pt(18)
            _write(description, self.project.description.strip(), 16, RGBColor(0xC9, 0xD1, 0xE0))
        for entry in self.cast:
            self.add_figure(slide, entry, "smile" if "smile" in entry["faces"] else DEFAULT_FACE)

    def add_credits(self) -> None:
        project = self.project
        definitions = load_definitions()
        credits, terms = [], []
        for voice in project.voices:
            source = definitions[voice]["source"]
            if source.get("credit") and source["credit"] not in credits:
                credits.append(source["credit"])
            for term in source.get("terms", []):
                if (term["title"], term["url"]) not in terms:
                    terms.append((term["title"], term["url"]))
        slide = self.prs.slides.add_slide(self.blank)
        _background(slide, TINT)
        self.add_panel(slide)
        self.add_heading(slide, project.title, "クレジット")
        frame = _text_box(slide, 0.6, CONTENT_TOP, SLIDE_W - 1.2, CONTENT_BOTTOM - CONTENT_TOP, "クレジット")
        first = True

        def section(label: str) -> None:
            nonlocal first
            paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
            paragraph.space_before = Pt(0 if first else 14)
            paragraph.space_after = Pt(4)
            first = False
            _write(paragraph, label, 14, NAVY, bold=True)

        def item(text: str, url: str | None = None) -> None:
            paragraph = frame.add_paragraph()
            _write(paragraph, text, 14, INK)
            if url:
                paragraph.runs[0].hyperlink.address = url

        if self.cast:
            section("立ち絵")
            for credit in credits:
                item(credit)
            item("立ち絵を含むこのスライドの利用は、非商用に限ります。")
        if terms:
            section("利用条件")
            for title, url in terms:
                item(title, url)
        if project.sources:
            section("出典")
            for source in project.sources:
                item(source.title, source.url)
        if first:
            _write(frame.paragraphs[0], "（なし）", 14, MUTED)

    def save(self) -> bytes:
        out = io.BytesIO()
        self.prs.save(out)
        return out.getvalue()


def render_slides(project: Project, cast: list[dict], diagrams: dict[int, bytes] | None = None) -> bytes:
    deck = _Deck(project, cast, diagrams or {})
    deck.add_cover()
    for index in range(len(project.lines)):
        deck.add_step(index)
    deck.add_credits()
    return deck.save()


def lint_slides(root: Path) -> list[str]:
    project = load_project(root, slides=True)
    used_faces(project)  # 表情が立ち絵の定義にあるか（素材は取得しない）
    return slide_warnings(project)


def build_slides(root: Path, warn: Callable[[list[str]], None], out: Path | None = None) -> None:
    """出力先（既定は out/）に slides.pptx を作る。出力先の他のファイル（video.html など）には触らない。"""
    project = load_project(root, slides=True)
    warn(slide_warnings(project))
    cast = build_cast(project)
    diagrams = render_diagrams(project)  # 図があるときだけブラウザを使う
    pptx = render_slides(project, cast, diagrams)

    def write(stage: Path) -> None:
        (stage / "slides.pptx").write_bytes(pptx)

    write_output(root, write, out)
