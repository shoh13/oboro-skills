import math
from dataclasses import dataclass
from pathlib import Path

from kataribe.browser import FREEZE_CSS, BrowserError, launch, require_aac
from kataribe.output import build_hint, out_dir
from kataribe.shoot import LINE_ATTRIBUTES, VIEWPORT_HEIGHT, VIEWPORT_WIDTH, _capture_second, full_lines, seek_and_wait
from kataribe.verify import intervals

TOLERANCE = 1.0  # px。はみ出しと重なりの両方で、これ以下の食い込みは数えない
CELL = 4  # 立ち絵の不透明な部分を調べる区画の一辺（CSS px）
OPAQUE_ALPHA = 128  # 区画の中に、アルファがこれ以上の画素が1つでもあれば不透明とする（輪郭のぼかしを除く）
EXCERPT = 20  # 要素の名前に添える文字数


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    def intersect(self, other: "Rect | None") -> "Rect | None":
        if other is None:
            return self
        rect = Rect(
            max(self.left, other.left), max(self.top, other.top), min(self.right, other.right), min(self.bottom, other.bottom)
        )
        return rect if rect.left < rect.right and rect.top < rect.bottom else None


@dataclass(frozen=True)
class Box:
    """描かれた矩形（背景・枠のある要素、画像などの要素、文字の1行分）。
    element は section と、その中の要素を文書順に並べたときの番号（section が0）で、行が変わっても同じ要素を指す。
    chain は section から element までの番号。clip は、overflow で中身を切る祖先（section より内側）の領域の共通部分。"""

    scene: str
    line: int  # シーンの中の0始まりの行番号（data-at と同じ数え方）
    element: int
    chain: tuple[int, ...]
    label: str
    rect: Rect
    text: bool = False
    clip: Rect | None = None


@dataclass(frozen=True)
class Mask:
    """立ち絵の canvas を CELL 四方の区画に分け、不透明な区画を "1" にした行の並び。"""

    scene: str
    line: int
    speaker: str
    left: float
    top: float
    cell: float
    rows: tuple[str, ...]

    def opaque_cells(self, area: Rect) -> set[tuple[int, int]]:
        rows = _cells(area.top, area.bottom, self.top, self.cell, len(self.rows))
        cols = _cells(area.left, area.right, self.left, self.cell, len(self.rows[0]) if self.rows else 0)
        return {(row, col) for row in rows for col in cols if self.rows[row][col] == "1"}


def _cells(start: float, end: float, origin: float, cell: float, count: int) -> range:
    """origin から cell ごとに区切った count 個の区画のうち、start〜end に掛かる区画の番号。"""
    return range(max(math.floor((start - origin) / cell), 0), min(math.ceil((end - origin) / cell), count))


@dataclass(frozen=True)
class _Owner:
    """問題を報告する要素。文字は、背景か枠のある最も内側の祖先（なければ親の要素）として報告する。"""

    element: int
    chain: tuple[int, ...]
    label: str


@dataclass(frozen=True)
class _Finding:
    scene: str
    line: int
    kind: str  # "overflow"（where はステージの辺）か "overlap"（where は話者）
    where: str
    amount: int  # はみ出しの px か、重なった区画の数
    owner: _Owner

    @property
    def problem(self) -> tuple[str, str, str]:
        return (self.scene, self.kind, self.where)


def _owner(box: Box, painted: dict[int, Box]) -> _Owner:
    if box.text:
        for depth in range(len(box.chain) - 1, -1, -1):
            if box.chain[depth] in painted:
                return _Owner(box.chain[depth], box.chain[: depth + 1], painted[box.chain[depth]].label)
    return _Owner(box.element, box.chain, box.label)


def _overflow(rect: Rect, stage: Rect) -> list[tuple[str, int]]:
    amounts = (
        ("左", stage.left - rect.left),
        ("右", rect.right - stage.right),
        ("上", stage.top - rect.top),
        ("下", rect.bottom - stage.bottom),
    )
    return [(side, round(px)) for side, px in amounts if px > TOLERANCE]


def _shrink(rect: Rect, by: float) -> Rect | None:
    return Rect(rect.left + by, rect.top + by, rect.right - by, rect.bottom - by).intersect(rect)


def _frame_findings(scene: str, line: int, boxes: list[Box], masks: list[Mask], stage: Rect) -> list[_Finding]:
    """1つの行の、要素ごとの問題。はみ出しは辺ごとの最大の px、重なりは話者ごとの、要素の矩形すべてで覆った区画の数。"""
    painted = {box.element: box for box in boxes if not box.text}
    overflow: dict[tuple[str, int], _Finding] = {}
    covered: dict[tuple[str, int], tuple[_Owner, set[tuple[int, int]]]] = {}
    for box in boxes:
        visible = box.rect.intersect(box.clip)
        if visible is None:
            continue
        owner = _owner(box, painted)
        for side, px in _overflow(visible, stage):
            key = (side, owner.element)
            if key not in overflow or px > overflow[key].amount:
                overflow[key] = _Finding(scene, line, "overflow", side, px, owner)
        on_stage = visible.intersect(stage)
        area = _shrink(on_stage, TOLERANCE) if on_stage else None
        if area is None:
            continue
        for mask in masks:
            cells = mask.opaque_cells(area)
            if cells:
                covered.setdefault((mask.speaker, owner.element), (owner, set()))[1].update(cells)
    overlap = [_Finding(scene, line, "overlap", speaker, len(cells), owner) for (speaker, _), (owner, cells) in covered.items()]
    return [*overflow.values(), *overlap]


def _message(finding: _Finding) -> str:
    head = f"{finding.scene} の {finding.line}行目: {finding.owner.label} が、"
    if finding.kind == "overflow":
        return f"{head}ステージの{finding.where}に {finding.amount}px はみ出しています"
    return f"{head}立ち絵（{finding.where}）と重なっています（{finding.amount} 区画）"


def layout_problems(boxes: list[Box], stage: Rect, masks: list[Mask]) -> list[str]:
    """ステージからのはみ出しと、立ち絵の不透明な部分との重なり。同じ要素の同じ問題は、シーンごとに、
    最も大きい行（同じなら先の行）で1回だけ示す。入れ子の要素が同じ問題を持つときは、最も内側の要素だけを示す。"""
    frames: dict[tuple[str, int], list[Box]] = {}
    for box in boxes:
        frames.setdefault((box.scene, box.line), []).append(box)
    worst: dict[tuple[str, str, str, int], _Finding] = {}
    for (scene, line), frame in frames.items():
        frame_masks = [mask for mask in masks if mask.scene == scene and mask.line == line]
        for finding in _frame_findings(scene, line, frame, frame_masks, stage):
            key = (*finding.problem, finding.owner.element)
            known = worst.get(key)
            if known is None or (finding.amount, -finding.line) > (known.amount, -known.line):
                worst[key] = finding
    # 行をまたいでまとめてから、内側に同じ問題を持つ要素を除く（行ごとに除くと、内側が消えている行で外側が残る）
    findings = list(worst.values())
    kept = [
        finding
        for finding in findings
        if not any(
            other is not finding and other.problem == finding.problem and finding.owner.element in other.owner.chain
            for other in findings
        )
    ]
    scene_order = {scene: number for number, scene in enumerate(dict.fromkeys(box.scene for box in boxes))}
    kept.sort(key=lambda f: (scene_order[f.scene], f.line, f.owner.element, f.kind, f.where))
    return [_message(finding) for finding in kept]


class LayoutError(BrowserError):
    pass


# 画素や色を読む、DOM に触れない関数。MEASURE が使い、テストは node で直接動かす
HELPERS = r"""
function colorAlpha(css) {
  const value = css.trim();
  if (value === 'transparent') return 0;
  const match = value.match(/\/\s*([^\s)]+)\s*\)$/) || value.match(/^rgba?\((?:[^,()]+,){3}\s*([^\s)]+)\s*\)$/);
  if (!match) return 1;
  const alpha = parseFloat(match[1]);
  return match[1].endsWith('%') ? alpha / 100 : alpha;
}

function maskRows(data, width, height, cssWidth, cssHeight, cell, threshold) {
  const scaleX = width / cssWidth, scaleY = height / cssHeight;
  const rows = [];
  for (let row = 0; row < Math.ceil(cssHeight / cell); row++) {
    const y0 = Math.floor(row * cell * scaleY), y1 = Math.min(height, Math.ceil((row + 1) * cell * scaleY));
    let line = '';
    for (let col = 0; col < Math.ceil(cssWidth / cell); col++) {
      const x0 = Math.floor(col * cell * scaleX), x1 = Math.min(width, Math.ceil((col + 1) * cell * scaleX));
      let opaque = false;
      for (let y = y0; y < y1 && !opaque; y++) {
        for (let x = x0; x < x1 && !opaque; x++) opaque = data[(y * width + x) * 4 + 3] >= threshold;
      }
      line += opaque ? '1' : '0';
    }
    rows.push(line);
  }
  return rows;
}

function label(tag, id, classes, text, excerpt) {
  const name = tag + (id ? `#${id}` : '') + classes.map((c) => `.${c}`).join('');
  const chars = Array.from(text.replace(/\s+/g, ' ').trim());
  const shown = chars.length > excerpt ? `${chars.slice(0, excerpt).join('')}…` : chars.join('');
  return shown ? `<${name}「${shown}」>` : `<${name}>`;
}
"""

# シーンの section の中で、いま見えている描かれた矩形と、立ち絵の不透明な区画を測る。判定は Python が行う
MEASURE = (
    r"""(scene) => {
"""
    + HELPERS
    + rf"""
  const CELL = {CELL}, OPAQUE_ALPHA = {OPAQUE_ALPHA}, EXCERPT = {EXCERPT};
"""
    + r"""
  const REPLACED = new Set(['img', 'svg', 'canvas', 'video', 'iframe', 'object', 'embed']);
  const stage = document.getElementById('kataribe-stage');
  const section = Array.from(stage.querySelectorAll('section[data-scene]')).find((s) => s.dataset.scene === scene);
  const elements = [section, ...section.querySelectorAll('*')];
  const index = new Map(elements.map((e, i) => [e, i]));
  const rectOf = (r) => [r.left, r.top, r.right, r.bottom];
  const paddingBox = (e) => {
    const r = e.getBoundingClientRect();
    const left = r.left + e.clientLeft, top = r.top + e.clientTop;
    return [left, top, left + e.clientWidth, top + e.clientHeight];
  };
  const intersect = (a, b) => (a === null ? b : [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])]);

  const memo = (compute) => {
    const cache = new Map();
    return (e) => {
      if (!cache.has(e)) cache.set(e, compute(e));
      return cache.get(e);
    };
  };
  // section 自身と stage は除く（ステージの境界は Python が比べる。section で切ると、はみ出しが見えなくなる）
  const contentClip = memo((e) => {
    if (e === section) return null;
    const outer = contentClip(e.parentElement);
    const style = getComputedStyle(e);
    const clips = (style.overflowX !== 'visible' || style.overflowY !== 'visible') && !['inline', 'contents'].includes(style.display);
    return clips ? intersect(outer, paddingBox(e)) : outer;
  });
  const opacity = memo((e) => Number(getComputedStyle(e).opacity) * (e === section ? 1 : opacity(e.parentElement)));
  const chainOf = memo((e) => (e === section ? [0] : [...chainOf(e.parentElement), index.get(e)]));
  const labelOf = memo((e) => label(e.localName, e.id, Array.from(e.classList), e.textContent || '', EXCERPT));
  const shown = (e) => getComputedStyle(e).visibility === 'visible' && opacity(e) > 0;
  const painted = (style) =>
    style.backgroundImage !== 'none' ||
    colorAlpha(style.backgroundColor) > 0 ||
    ['Top', 'Right', 'Bottom', 'Left'].some(
      (side) =>
        parseFloat(style[`border${side}Width`]) > 0 &&
        !['none', 'hidden'].includes(style[`border${side}Style`]) &&
        colorAlpha(style[`border${side}Color`]) > 0,
    );

  const boxes = [];
  const add = (e, rects, text, clip) => {
    for (const r of rects) {
      if (r.width > 0 && r.height > 0) {
        boxes.push({ element: index.get(e), chain: chainOf(e), label: labelOf(e), rect: rectOf(r), text, clip });
      }
    }
  };
  // section 自身の背景は、シーンの地なので測らない。SVG の中は、svg 要素1つとして測る
  for (const e of elements.slice(1)) {
    if (e.parentElement.closest('svg') || !shown(e)) continue;
    if (REPLACED.has(e.localName) || painted(getComputedStyle(e))) add(e, e.getClientRects(), false, contentClip(e.parentElement));
  }
  const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (!/\S/.test(node.data) || parent.closest('svg') || !shown(parent)) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    add(parent, range.getClientRects(), true, contentClip(parent));
  }

  const masks = [];
  for (const canvas of stage.querySelectorAll('canvas.kataribe-character')) {
    const r = canvas.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || canvas.width === 0 || canvas.height === 0) continue;
    // getImageData は描いた後の画素なので、左右の反転はすでに入っている
    const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    masks.push({
      speaker: canvas.dataset.speaker,
      left: r.left,
      top: r.top,
      cell: CELL,
      rows: maskRows(data, canvas.width, canvas.height, r.width, r.height, CELL, OPAQUE_ALPHA),
    });
  }
  return { stage: paddingBox(stage), boxes, masks };
}"""
)


def _measured_lines(timeline: dict, found: dict[str, dict]) -> list[tuple[str, int, float]]:
    """（シーンID, シーンの中の行番号, 測る秒）。shoot --at full と同じ行を、同じ時刻に測る。"""
    jobs = []
    for scene in timeline["scenes"]:
        scene_id = scene["id"]
        lines = [line for line in timeline["lines"] if line["scene"] == scene_id]
        timed = found.get(scene_id, {}).get("timed", [])
        elements = intervals([own for own, _ in timed])
        ancestors = [intervals(chain) for _, chain in timed]
        jobs.extend((scene_id, position, _capture_second(lines[position])) for position in full_lines(elements, ancestors, len(lines)))
    return jobs


def _rect(values: list[float] | None) -> Rect | None:
    return None if values is None else Rect(*values)


def _parse(raw: dict, scene: str, line: int) -> tuple[Rect, list[Box], list[Mask]]:
    boxes = [
        Box(scene, line, item["element"], tuple(item["chain"]), item["label"], Rect(*item["rect"]), item["text"], _rect(item["clip"]))
        for item in raw["boxes"]
    ]
    masks = [
        Mask(scene, line, item["speaker"], item["left"], item["top"], item["cell"], tuple(item["rows"])) for item in raw["masks"]
    ]
    return Rect(*raw["stage"]), boxes, masks


def check_layout(root: Path, out: Path | None = None) -> list[str]:
    """out/video.html を開き、shoot --at full と同じ行で、図のはみ出しと立ち絵との重なりを測る。問題がなければ空。"""
    from playwright.sync_api import sync_playwright

    html = out_dir(root, out) / "video.html"
    if not html.is_file():
        raise LayoutError(f"{html} がありません。先に `{build_hint(root, out)}` を実行してください")
    stage = None
    boxes: list[Box] = []
    masks: list[Mask] = []
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            page = browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}, device_scale_factor=1)
            page.goto(html.resolve().as_uri())
            require_aac(page)
            page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
            timeline = page.evaluate("JSON.parse(document.getElementById('kataribe-timeline').textContent)")
            # 台本にないシーンの section の属性は lint が検査しないので、整数でないことがある。読まない
            in_script = {scene["id"] for scene in timeline["scenes"]}
            found = {scene: data for scene, data in page.evaluate(LINE_ATTRIBUTES).items() if scene in in_script}
            page.add_style_tag(content=FREEZE_CSS)
            for scene_id, position, seconds in _measured_lines(timeline, found):
                seek_and_wait(page, seconds)
                stage, frame_boxes, frame_masks = _parse(page.evaluate(MEASURE, scene_id), scene_id, position)
                boxes.extend(frame_boxes)
                masks.extend(frame_masks)
        finally:
            browser.close()
    return [] if stage is None else layout_problems(boxes, stage, masks)
