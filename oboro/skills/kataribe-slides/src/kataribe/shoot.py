import re
import sys
from pathlib import Path

from kataribe.browser import FREEZE_CSS, BrowserError, launch, require_aac
from kataribe.output import build_hint, out_dir
from kataribe.verify import Interval, expected_visibility, intervals

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
CAPTURE_DELAY = 0.3
SEEK_TIMEOUT_MS = 5000
WINDOWS_UNUSABLE = set(':*?"<>|')
FRAME_NAME = re.compile(r"(?P<scene>.+)-(?:start|mid|end)\.png")
LINE_FRAME = re.compile(r".+-line\d+\.png")
LINE_MODES = ("changes", "full")  # 行ごとに撮る指定。画像は out/frames/<指定>/ に置き、撮るたびに作り直す

# section ごとに、プレーヤーが出し入れ・強調する要素（HTMLElement だけ。player.js と同じ）の属性を読む。
# timed: data-at・data-out を持つ要素の [[data-at, data-out], 祖先の [data-at, data-out] の並び]、focus: data-focus の行番号の並び
LINE_ATTRIBUTES = """() => Object.fromEntries(
    Array.from(document.querySelectorAll('#kataribe-stage section[data-scene]')).map(s => {
        const timed = el => el instanceof HTMLElement && (el.hasAttribute('data-at') || el.hasAttribute('data-out'));
        const pair = el => [el.getAttribute('data-at'), el.getAttribute('data-out')];
        return [s.dataset.scene, {
            timed: Array.from(s.querySelectorAll('[data-at],[data-out]')).filter(timed).map(e => {
                const chain = [];
                for (let node = e.parentElement; node && node !== s; node = node.parentElement) {
                    if (timed(node)) chain.push(pair(node));
                }
                return [pair(e), chain];
            }),
            focus: Array.from(s.querySelectorAll('[data-focus]'))
                .filter(e => e instanceof HTMLElement)
                .map(e => e.dataset.focus.split(',').map(n => Number(n.trim()))),
        }];
    })
)"""


class ShootError(BrowserError):
    pass


def _check_file_name(scene_id: str) -> None:
    unusable = (
        scene_id in ("", ".", "..")
        or any(char in scene_id for char in ("/", "\\"))
        or any(char in WINDOWS_UNUSABLE or ord(char) < 32 for char in scene_id)
        or scene_id.endswith((".", " "))
    )
    if unusable:
        raise ShootError(
            f"シーンID {scene_id!r} は、スクリーンショットのファイル名に使えません"
            "（空、`.`、`..`、`/`、`\\`、`:`、`*`、`?`、`\"`、`<`、`>`、`|`、制御文字を含められず、末尾を `.` や空白にもできません）。"
            "script.json のシーンの id を直してください"
        )


def _warn_stale_frames(frames: Path, scene_ids: list[str]) -> None:
    if not frames.is_dir():
        return
    current = set(scene_ids)
    for path in sorted(frames.iterdir()):
        match = FRAME_NAME.fullmatch(path.name)
        if match and path.is_file() and match.group("scene") not in current:
            print(f"警告: out/frames の {path.name} は、今回のシーンに対応しません（古い画像です）", file=sys.stderr)


def _reset_line_frames(directory: Path) -> None:
    """行ごとの画像の置き場所を空にする。台本の行が変わると、前回の画像の行番号は今回の行を指さなくなるため。"""
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.is_file() and LINE_FRAME.fullmatch(path.name):
            path.unlink()


def _check_no_collisions(scene_ids: list[str]) -> None:
    seen: dict[str, str] = {}
    for scene_id in scene_ids:
        key = scene_id.casefold()
        if key in seen and seen[key] != scene_id:
            raise ShootError(
                f"シーンID {seen[key]!r} と {scene_id!r} は、大文字小文字を無視すると同じファイル名になり、画像が上書きされます。"
                "script.json のシーンの id を、大文字小文字を無視しても違う名前にしてください"
            )
        seen[key] = scene_id


def seek_and_wait(page, seconds: float, timeout_ms: int = SEEK_TIMEOUT_MS) -> None:
    done = page.evaluate(
        """([seconds, timeout]) => new Promise(resolve => {
            const audio = document.getElementById('kataribe-audio');
            const timer = setTimeout(() => resolve(false), timeout);
            // 立ち絵の画像のデコードが終わり、プレーヤーが描ける状態になってから撮る（待たないと立ち絵が欠ける）
            const castReady = () => new Promise(done => {
                const check = () => document.documentElement.dataset.kataribeCast === 'ready' ? done() : requestAnimationFrame(check);
                check();
            });
            castReady().then(() => {
                audio.addEventListener('seeked', () => requestAnimationFrame(() => { clearTimeout(timer); resolve(true); }), { once: true });
                audio.currentTime = seconds;
            });
        })""",
        [seconds, timeout_ms],
    )
    if not done:
        raise ShootError(f"再生位置を {seconds:.2f} 秒へ動かせませんでした（{timeout_ms} ミリ秒待ちました）")


def _capture_second(line: dict) -> float:
    return line["start"] + min(CAPTURE_DELAY, (line["end"] - line["start"]) / 2)


def capture_times(timeline: dict, at: str) -> list[tuple[str, float]]:
    jobs = []
    for scene in timeline["scenes"]:
        lines = [line for line in timeline["lines"] if line["scene"] == scene["id"]]
        line = lines[{"start": 0, "mid": len(lines) // 2, "end": len(lines) - 1}[at]]
        jobs.append((scene["id"], _capture_second(line)))
    return jobs


def _shown(position: int, elements: list[Interval], ancestors: list[list[Interval]]) -> tuple[bool, ...]:
    return tuple(
        expected_visibility(position, own, ancestors[number] if number < len(ancestors) else []) == "visible"
        for number, own in enumerate(elements)
    )


def change_lines(elements: list[Interval], ancestors: list[list[Interval]], focus: list[list[int]], count: int) -> list[int]:
    """シーンの行（0〜count-1）のうち、見た目（data-at・data-out による表示と、data-focus による強調）が
    前の行と変わる行。先頭の行は必ず含む。"""
    states = [(_shown(p, elements, ancestors), tuple(p in lines for lines in focus)) for p in range(count)]
    return [p for p in range(count) if p == 0 or states[p] != states[p - 1]]


def full_lines(elements: list[Interval], ancestors: list[list[Interval]], count: int) -> list[int]:
    """表示が最も多い状態の行。次の行で消える要素がある行と、最後の行。
    はみ出しや立ち絵との重なりは、要素が出そろったこの行で起きる。"""
    shown = [_shown(p, elements, ancestors) for p in range(count)]
    return [
        p for p in range(count) if p == count - 1 or any(now and not after for now, after in zip(shown[p], shown[p + 1]))
    ]


def line_frame_name(scene_id: str, position: int) -> str:
    return f"{scene_id}-line{position:02d}.png"


def line_capture_times(
    timeline: dict,
    mode: str,
    elements: dict[str, list[Interval]],
    ancestors: dict[str, list[list[Interval]]],
    focus: dict[str, list[list[int]]],
) -> list[tuple[str, float]]:
    """（画像の名前, 撮る秒）の並び。シーンごとに、mode（changes か full）の行を、その行の開始から 0.3 秒後に撮る。"""
    jobs = []
    for scene in timeline["scenes"]:
        scene_id = scene["id"]
        lines = [line for line in timeline["lines"] if line["scene"] == scene_id]
        scene_elements, scene_ancestors = elements.get(scene_id, []), ancestors.get(scene_id, [])
        if mode == "changes":
            positions = change_lines(scene_elements, scene_ancestors, focus.get(scene_id, []), len(lines))
        else:
            positions = full_lines(scene_elements, scene_ancestors, len(lines))
        jobs.extend((line_frame_name(scene_id, position), _capture_second(lines[position])) for position in positions)
    return jobs


def shoot(root: Path, at: str, out: Path | None = None) -> None:
    from playwright.sync_api import sync_playwright

    html = out_dir(root, out) / "video.html"
    if not html.is_file():
        raise ShootError(f"{html} がありません。先に `{build_hint(root, out)}` を実行してください")
    with sync_playwright() as playwright:
        browser = launch(playwright)
        page = browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}, device_scale_factor=1)
        page.goto(html.resolve().as_uri())
        require_aac(page)
        page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
        timeline = page.evaluate("JSON.parse(document.getElementById('kataribe-timeline').textContent)")
        for scene in timeline["scenes"]:
            _check_file_name(scene["id"])
        _check_no_collisions([scene["id"] for scene in timeline["scenes"]])
        frames = out_dir(root, out) / "frames"
        if at in LINE_MODES:
            # 台本にないシーンの section の属性は lint が検査しないので、整数でないことがある。読まない
            in_script = {scene["id"] for scene in timeline["scenes"]}
            found = {scene: data for scene, data in page.evaluate(LINE_ATTRIBUTES).items() if scene in in_script}
            elements = {scene: intervals([own for own, _ in data["timed"]]) for scene, data in found.items()}
            ancestors = {scene: [intervals(chain) for _, chain in data["timed"]] for scene, data in found.items()}
            focus = {scene: data["focus"] for scene, data in found.items()}
            jobs = line_capture_times(timeline, at, elements, ancestors, focus)
            target = frames / at
            _reset_line_frames(target)
        else:
            jobs = [(f"{scene_id}-{at}.png", seconds) for scene_id, seconds in capture_times(timeline, at)]
            target = frames
            _warn_stale_frames(frames, [scene["id"] for scene in timeline["scenes"]])
            frames.mkdir(parents=True, exist_ok=True)
        page.add_style_tag(content=FREEZE_CSS)
        for name, seconds in jobs:
            seek_and_wait(page, seconds)
            page.locator("#kataribe-stage").screenshot(path=str(target / name))
        browser.close()
