import re
import sys
from pathlib import Path

from kataribe.browser import FREEZE_CSS, BrowserError, launch, require_aac
from kataribe.output import build_hint, out_dir

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
CAPTURE_DELAY = 0.3
SEEK_TIMEOUT_MS = 5000
WINDOWS_UNUSABLE = set(':*?"<>|')
FRAME_NAME = re.compile(r"(?P<scene>.+)-(?:start|mid|end)\.png")


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


def capture_times(timeline: dict, at: str) -> list[tuple[str, float]]:
    jobs = []
    for scene in timeline["scenes"]:
        lines = [line for line in timeline["lines"] if line["scene"] == scene["id"]]
        line = lines[{"start": 0, "mid": len(lines) // 2, "end": len(lines) - 1}[at]]
        delay = min(CAPTURE_DELAY, (line["end"] - line["start"]) / 2)
        jobs.append((scene["id"], line["start"] + delay))
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
        jobs = capture_times(timeline, at)
        frames = out_dir(root, out) / "frames"
        _warn_stale_frames(frames, [scene["id"] for scene in timeline["scenes"]])
        page.add_style_tag(content=FREEZE_CSS)
        frames.mkdir(parents=True, exist_ok=True)
        for scene_id, seconds in jobs:
            seek_and_wait(page, seconds)
            page.locator("#kataribe-stage").screenshot(path=str(frames / f"{scene_id}-{at}.png"))
        browser.close()
