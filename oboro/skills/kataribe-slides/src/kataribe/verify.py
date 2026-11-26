import math
from dataclasses import dataclass, field
from pathlib import Path

from kataribe.browser import BrowserError, launch, require_aac
from kataribe.output import build_hint, out_dir
from kataribe.project import load_project

END_MARGIN = 10.0
CAPTION_TOLERANCE = 0.3
LINE_EDGE = 0.01
PROGRESS_TOLERANCE = 1e-6
MAX_PROBLEMS = 5
NAMES = [
    "再生が最後まで進む",
    "全シーンが順に表示される",
    "各行の字幕がその行の時間帯に表示される",
    "章バーと文字起こしの数が台本と一致する",
    "各行の開始時点で表示すべき要素が表示され消すべき要素が非表示",
    "進行変数が0〜1で、シーン内で --p が減らない",
    "立ち絵の表情と口が、その時刻の台本と音声に合う",
]
MARKS = "①②③④⑤⑥⑦"
CHARACTER_TOLERANCE = 0.05
MOUTH_FPS = 30
DEFAULT_FACE = "normal"


class VerifyError(BrowserError):
    pass


@dataclass
class Check:
    number: int
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def name(self) -> str:
        return NAMES[self.number - 1]


def _check(number: int, problems: list[str], warnings: list[str] | None = None) -> Check:
    shown = problems[:MAX_PROBLEMS]
    if len(problems) > MAX_PROBLEMS:
        shown.append(f"他 {len(problems) - MAX_PROBLEMS} 件")
    return Check(number, shown, warnings or [])


def check_played(ended: bool, current: float, waited: float) -> Check:
    problems = []
    if not ended:
        problems.append(f"{waited:.1f} 秒待っても最後まで進みませんでした（再生位置 {current:.2f} 秒）")
    return _check(1, problems)


def check_scenes(samples: list[dict], timeline: dict) -> Check:
    seen: list[str] = []
    for item in samples:
        scene = item["scene"]
        if scene is not None and (not seen or seen[-1] != scene):
            seen.append(scene)
    expected = [scene["id"] for scene in timeline["scenes"]]
    problems = []
    if seen != expected:
        problems.append(f"表示されたシーンの順が台本と違います（台本: {expected}、実際: {seen}）")
    return _check(2, problems)


def check_captions(samples: list[dict], timeline: dict) -> Check:
    lines = timeline["lines"]
    problems = []
    for item in samples:
        allowed = [
            line["text"]
            for line in lines
            if line["start"] - CAPTION_TOLERANCE <= item["t"] <= line["end"] + CAPTION_TOLERANCE
        ]
        if item["caption"] not in allowed:
            problems.append(f"{item['t']:.2f} 秒の字幕 {item['caption']!r} が、その時刻（±{CAPTION_TOLERANCE}秒）の行の文と違います")
    shown = {item["caption"] for item in samples}
    for line in lines:
        if line["text"] not in shown:
            problems.append(f"行 {line['id']} の字幕が一度も表示されませんでした")
    return _check(3, problems)


def check_counts(chapters: int, transcript: int, expected_chapters: int, expected_lines: int) -> Check:
    problems = []
    if chapters != expected_chapters:
        problems.append(f"章バーの章の数が台本と違います（台本: {expected_chapters}、実際: {chapters}）")
    if transcript != expected_lines:
        problems.append(f"文字起こしの行の数が台本と違います（台本: {expected_lines}、実際: {transcript}）")
    return _check(4, problems)


Interval = tuple[float, float]


def expected_visibility(position: int, own: Interval, ancestors: list[Interval]) -> str:
    """要素自身の区間と、data-at・data-out を持つ祖先（section の中）のすべての区間に入る行でだけ見える。
    祖先が消えている間は、visibility の継承で、子も消える。"""
    shown = all(at <= position < out for at, out in [own, *ancestors])
    return "visible" if shown else "hidden"


def check_appearance(
    samples: list[dict],
    timeline: dict,
    elements: dict[str, list[Interval]],
    ancestors: dict[str, list[list[Interval]]] | None = None,
) -> Check:
    problems: list[str] = []
    warnings: list[str] = []
    index_in_scene: dict[str, int] = {}
    counters: dict[str, int] = {}
    for line in timeline["lines"]:
        index_in_scene[line["id"]] = counters.get(line["scene"], 0)
        counters[line["scene"]] = index_in_scene[line["id"]] + 1
    for line in timeline["lines"]:
        scene_elements = elements.get(line["scene"], [])
        if not scene_elements:
            continue
        inside = [
            item
            for item in samples
            if line["start"] + LINE_EDGE <= item["t"] <= line["end"] - LINE_EDGE and item["scene"] == line["scene"]
        ]
        if not inside:
            warnings.append(f"行 {line['id']} は、検証できるサンプルがなく、検証できませんでした")
            continue
        position = index_in_scene[line["id"]]
        scene_ancestors = (ancestors or {}).get(line["scene"], [])
        for number, own in enumerate(scene_elements):
            chain = scene_ancestors[number] if number < len(scene_ancestors) else []
            expected = expected_visibility(position, own, chain)
            wrong = [item for item in inside if item["vis"][number] != expected]
            if wrong:
                problems.append(
                    f"行 {line['id']} で、シーン {line['scene']} の {number + 1} 番目の要素（data-at/data-out）が "
                    f"{wrong[0]['vis'][number]} です（期待: {expected}、{wrong[0]['t']:.2f} 秒）"
                )
    return _check(5, problems, warnings)


def check_progress(samples: list[dict]) -> Check:
    problems: list[str] = []
    last: dict[str, float] = {}
    for item in samples:
        for scene_id, pair in item["progress"].items():
            for label, value in zip(("--p", "--lp"), pair):
                if not isinstance(value, (int, float)) or not (-PROGRESS_TOLERANCE <= value <= 1 + PROGRESS_TOLERANCE):
                    problems.append(f"{item['t']:.2f} 秒に、シーン {scene_id} の {label} が 0〜1 の範囲外です（{value!r}）")
            p = pair[0]
            if isinstance(p, (int, float)):
                if scene_id in last and p < last[scene_id] - PROGRESS_TOLERANCE:
                    problems.append(f"{item['t']:.2f} 秒に、シーン {scene_id} の --p が減りました（{last[scene_id]:.3f} → {p:.3f}）")
                last[scene_id] = p
    return _check(6, problems)


@dataclass
class VerifyResult:
    checks: list[Check]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def _expected_cast(timeline: dict, t: float) -> dict[str, tuple[str, str]]:
    """時刻 t の、話者ごとの（表情, 口の段階）。プレーヤーとは別に、タイムラインから計算する。"""
    lines = [line for line in timeline["lines"] if "speaker" in line]
    if not lines:
        return {}
    speakers = list(dict.fromkeys(line["speaker"] for line in lines))
    index = 0
    for i, line in enumerate(lines):
        if line["start"] <= t:
            index = i
    faces = {speaker: DEFAULT_FACE for speaker in speakers}
    for line in lines[: index + 1]:
        faces[line["speaker"]] = line.get("expression") or DEFAULT_FACE
    mouths = {speaker: "0" for speaker in speakers}
    current = lines[index]
    if current["start"] <= t < current["end"]:
        frame = math.floor((t - current["start"]) * MOUTH_FPS)
        levels = current.get("mouth") or ""
        if 0 <= frame < len(levels) and levels[frame] in "12":
            mouths[current["speaker"]] = levels[frame]
    return {speaker: (faces[speaker], mouths[speaker]) for speaker in speakers}


def check_characters(samples: list[dict], timeline: dict) -> Check:
    """⑦ 各サンプルの立ち絵の表情と口が、その時刻（±0.05 秒のどこか）の期待と一致するか。まばたきは見ない。"""
    offsets = [CHARACTER_TOLERANCE * (k / 3) for k in range(-3, 4)]  # 1/60 秒刻み（口の段階は 1/30 秒ごと）
    problems = []
    for item in samples:
        t = item["t"]
        shown = {speaker: (face, mouth) for speaker, face, mouth in item.get("cast", [])}
        candidates = [_expected_cast(timeline, t + d) for d in offsets]
        expected = _expected_cast(timeline, t)
        for speaker, (face, mouth) in expected.items():
            if speaker not in shown:
                problems.append(f"{t:.2f} 秒に、{speaker}の立ち絵がありません")
            else:
                # 表情と口は別々に比べる。行の境目では、表情が先に次の行へ変わり、口は行の開始まで閉じたままになりうる
                got_face, got_mouth = shown[speaker]
                faces = {c[speaker][0] for c in candidates if speaker in c}
                mouths = {c[speaker][1] for c in candidates if speaker in c}
                if got_face in faces and got_mouth in mouths:
                    continue
                problems.append(
                    f"{t:.2f} 秒の{speaker}の立ち絵が、表情 {got_face}・口 {got_mouth} で、"
                    f"期待（表情 {face}・口 {mouth}、±{CHARACTER_TOLERANCE}秒）と違います"
                )
    return _check(7, problems)


SAMPLER = """() => {
    const stage = document.getElementById('kataribe-stage');
    const caption = document.getElementById('kataribe-caption');
    const audio = document.getElementById('kataribe-audio');
    const sections = Array.from(stage.querySelectorAll('section[data-scene]'));
    window.__kataribeSamples = [];
    window.__kataribeStop = false;
    const take = () => {
        const active = sections.find(s => getComputedStyle(s).display !== 'none');
        const progress = {};
        for (const s of sections) {
            const read = name => { const v = s.style.getPropertyValue(name).trim(); return v === '' ? null : Number(v); };
            progress[s.dataset.scene] = [read('--p'), read('--lp')];
        }
        window.__kataribeSamples.push({
            t: audio.currentTime,
            caption: caption.textContent,
            scene: active ? active.dataset.scene : null,
            progress,
            vis: active ? Array.from(active.querySelectorAll('[data-at],[data-out]')).filter(e => e instanceof HTMLElement).map(e => getComputedStyle(e).visibility) : [],
            cast: Array.from(stage.querySelectorAll('.kataribe-character')).map(el => [el.dataset.speaker, el.dataset.face, el.dataset.mouth]),
        });
    };
    const loop = () => {
        take();
        if (!window.__kataribeStop) requestAnimationFrame(loop);
    };
    // プレーヤーの play ハンドラ（描画ループを始める）より後に登録するので、毎フレーム「描画 → 読み取り」の順になり、DOM と時刻が揃う
    audio.addEventListener('play', () => requestAnimationFrame(loop), { once: true });
}"""

ELEMENTS = """() => Object.fromEntries(
    Array.from(document.querySelectorAll('#kataribe-stage section[data-scene]')).map(s => [
        s.dataset.scene,
        Array.from(s.querySelectorAll('[data-at],[data-out]')).filter(e => e instanceof HTMLElement).map(e => [e.getAttribute('data-at'), e.getAttribute('data-out')]),
    ])
)"""

# ELEMENTS と同じ順の要素ごとに、data-at・data-out を持つ祖先（section 自身は含めない）の [data-at, data-out]。
# プレーヤーは HTMLElement だけを出し入れする（SVG の <g data-at> は常に見える）ので、祖先も HTMLElement に限る
ANCESTORS = """() => Object.fromEntries(
    Array.from(document.querySelectorAll('#kataribe-stage section[data-scene]')).map(s => [
        s.dataset.scene,
        Array.from(s.querySelectorAll('[data-at],[data-out]')).filter(e => e instanceof HTMLElement).map(e => {
            const chain = [];
            for (let node = e.parentElement; node && node !== s; node = node.parentElement) {
                if (node instanceof HTMLElement && (node.hasAttribute('data-at') || node.hasAttribute('data-out'))) {
                    chain.push([node.getAttribute('data-at'), node.getAttribute('data-out')]);
                }
            }
            return chain;
        }),
    ])
)"""


def _number(value: str | None, default: float) -> float:
    return default if value is None else float(int(value.strip()))


def intervals(pairs: list) -> list[Interval]:
    """[data-at, data-out] の値（属性がなければ None）の並び → 表示する行の区間 [at, out) の並び。"""
    return [(_number(at, 0), _number(out, float("inf"))) for at, out in pairs]


def verify(root: Path, end_margin: float = END_MARGIN, out: Path | None = None) -> VerifyResult:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    project = load_project(root)
    html = out_dir(root, out) / "video.html"
    if not html.is_file():
        raise VerifyError(f"{html} がありません。先に `{build_hint(root, out)}` を実行してください")
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(html.resolve().as_uri())
            require_aac(page)
            page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
            timeline = page.evaluate("JSON.parse(document.getElementById('kataribe-timeline').textContent)")
            # 台本にないシーンの section の属性は lint が検査しないので、整数でないことがある。読まない
            in_script = {scene["id"] for scene in timeline["scenes"]}
            elements = {
                scene_id: intervals(pairs) for scene_id, pairs in page.evaluate(ELEMENTS).items() if scene_id in in_script
            }
            ancestors = {
                scene_id: [intervals(chain) for chain in chains]
                for scene_id, chains in page.evaluate(ANCESTORS).items()
                if scene_id in in_script
            }
            chapter_count = page.locator("#kataribe-chapter-bar > [data-chapter-id]").count()
            transcript_count = page.locator("#kataribe-transcript > [data-line-id]").count()
            page.evaluate(SAMPLER)
            page.click("#kataribe-play")
            waited = timeline["duration"] + end_margin
            try:
                page.wait_for_function("document.getElementById('kataribe-audio').ended", timeout=waited * 1000)
            except PlaywrightTimeout:
                pass
            page.wait_for_timeout(100)
            ended = page.evaluate("document.getElementById('kataribe-audio').ended")
            current = page.evaluate("document.getElementById('kataribe-audio').currentTime")
            page.evaluate("window.__kataribeStop = true")
            samples = page.evaluate("window.__kataribeSamples")
        finally:
            browser.close()
    appearance = check_appearance(samples, timeline, elements, ancestors)
    checks = [
        check_played(ended, current, waited),
        check_scenes(samples, timeline),
        check_captions(samples, timeline),
        check_counts(chapter_count, transcript_count, len(project.chapters), len(project.lines)),
        appearance,
        check_progress(samples),
        check_characters(samples, timeline),
    ]
    return VerifyResult(checks, appearance.warnings)
