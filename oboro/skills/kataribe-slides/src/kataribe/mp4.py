import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from kataribe.browser import FREEZE_CSS, BrowserError, launch, require_aac
from kataribe.extras import EXTRAS_DIR
from kataribe.output import build_hint, out_dir
from kataribe.shoot import seek_and_wait

SIZES = {"1280x720": (1280, 720), "1920x1080": (1920, 1080)}
FPS_CHOICES = (24, 30, 60)
DEFAULT_SIZE = "1280x720"
DEFAULT_FPS = 30
CREDIT_SECONDS = 5
BASE_WIDTH = 1280
BASE_HEIGHT = 720

FRAME_CSS = """
#kataribe-controls, #kataribe-seek, #kataribe-chapter-bar, #kataribe-chapter, #kataribe-transcript, #kataribe-about { display: none !important; }
html, body { margin: 0; overflow: hidden; }
#kataribe-player { max-width: none; padding: 0; margin: 0; }
#kataribe-stage { width: 1280px; height: 720px; aspect-ratio: auto; border: 0; border-radius: 0; box-sizing: border-box; }
#kataribe-caption { position: fixed; left: 0; right: 0; bottom: 0; margin: 0; min-height: 0; padding: 12px 48px; box-sizing: border-box; background: rgba(0, 0, 0, 0.65); color: #fff; }
#kataribe-caption:empty { display: none; }
"""

CREDIT_PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: 1280px; height: 720px; background: #17181a; color: #ececec; font-family: system-ui, "Hiragino Sans", "Noto Sans JP", sans-serif; }}
main {{ box-sizing: border-box; height: 720px; padding: 72px 96px; display: flex; flex-direction: column; justify-content: center; gap: 28px; }}
h1 {{ margin: 0; font-size: 44px; }}
h2 {{ margin: 0 0 8px; font-size: 24px; color: #9a9a9a; }}
p, li {{ margin: 0; font-size: 32px; line-height: 1.5; overflow-wrap: anywhere; }}
ul {{ margin: 0; padding-left: 1.2em; }}
small {{ display: block; font-size: 22px; color: #9a9a9a; }}
</style></head><body><main>
<h1>{title}</h1>
<section><h2>クレジット</h2>{credit}</section>
{sources}
</main></body></html>"""


class Mp4Error(BrowserError):
    pass


def ffmpeg_exe() -> str:
    override = os.environ.get("KATARIBE_FFMPEG")
    if override:
        if shutil.which(override) is None:
            raise Mp4Error(f"ffmpeg を取得できません（KATARIBE_FFMPEG={override} が実行できません）")
        return override
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise Mp4Error(f"ffmpeg を取得できません: {e}") from None


def frame_times(duration: float, fps: int) -> list[float]:
    return [i / fps for i in range(math.ceil(duration * fps - 1e-9))]


def render_credit_page(timeline: dict) -> str:
    sources = ""
    if timeline["sources"]:
        items = "".join(
            f"<li>{html.escape(s['title'])}<small>{html.escape(s['url'])}</small></li>" for s in timeline["sources"]
        )
        sources = f"<section><h2>出典</h2><ul>{items}</ul></section>"
    credits = timeline["credit"]
    if isinstance(credits, str):  # T18 より前の build --extras の timeline.json は文字列
        credits = [credits]
    credit = "".join(f"<p>{html.escape(c)}</p>" for c in credits)
    return CREDIT_PAGE.format(title=html.escape(timeline["title"]), credit=credit, sources=sources)


def _read_extras(root: Path, out: Path | None = None) -> tuple[Path, dict]:
    directory = out_dir(root, out) / EXTRAS_DIR
    required = [directory / name for name in ("audio.wav", "captions.vtt", "timeline.json", "TERMS.txt")]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise Mp4Error(f"副産物がありません（{', '.join(missing)}）。先に `{build_hint(root, out, extras=True)}` を実行してください")
    try:
        return directory, json.loads((directory / "timeline.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Mp4Error(f"timeline.json が正しいJSONではありません: {e}") from None


def _command(ffmpeg: str, fps: int, credit: Path, audio: Path, total: float, output: Path) -> list[str]:
    graph = (
        "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v];"
        f"[2:a]apad=whole_dur={total:.6f}[a]"
    )
    return [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
        "-loop", "1", "-framerate", str(fps), "-t", str(CREDIT_SECONDS), "-i", str(credit),
        "-i", str(audio),
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-r", str(fps), "-c:a", "aac", "-t", f"{total:.6f}", "-movflags", "+faststart", str(output),
    ]


def make_mp4(root: Path, size: str = DEFAULT_SIZE, fps: int = DEFAULT_FPS, out: Path | None = None) -> Path:
    from playwright.sync_api import Error, sync_playwright

    width, height = SIZES[size]
    directory, timeline = _read_extras(root, out)
    html_path = out_dir(root, out) / "video.html"
    if not html_path.is_file():
        raise Mp4Error(f"{html_path} がありません。先に `{build_hint(root, out, extras=True)}` を実行してください")
    ffmpeg = ffmpeg_exe()
    times = frame_times(timeline["duration"], fps)
    total = len(times) / fps + CREDIT_SECONDS
    scale = width / BASE_WIDTH
    with tempfile.TemporaryDirectory() as work_name, sync_playwright() as playwright:
        work = Path(work_name)
        browser = launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": BASE_WIDTH, "height": BASE_HEIGHT}, device_scale_factor=scale, color_scheme="light"
            )
            page = context.new_page()
            page.goto(html_path.resolve().as_uri())
            require_aac(page)
            page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
            in_page = page.evaluate("JSON.parse(document.getElementById('kataribe-timeline').textContent)")
            if [(line["id"], line["start"], line["end"]) for line in in_page["lines"]] != [
                (line["id"], line["start"], line["end"]) for line in timeline["lines"]
            ]:
                raise Mp4Error(
                    f"副産物と {html_path.name} の内容が食い違っています。もう一度 `kataribe build {root} --extras` を実行してください"
                )
            page.add_style_tag(content=FRAME_CSS)
            page.add_style_tag(content=FREEZE_CSS)
            credit_page = context.new_page()
            credit_page.set_content(render_credit_page(timeline))
            credit_png = work / "credit.png"
            credit_page.screenshot(path=str(credit_png))
            output = work / "video.mp4"
            log = work / "ffmpeg.log"
            with log.open("wb") as log_file:
                process = subprocess.Popen(
                    _command(ffmpeg, fps, credit_png, directory / "audio.wav", total, output),
                    stdin=subprocess.PIPE, stderr=log_file,
                )
                assert process.stdin is not None
                step = max(len(times) // 10, 100)
                try:
                    for number, seconds in enumerate(times):
                        seek_and_wait(page, seconds)
                        process.stdin.write(page.screenshot(type="png"))
                        if number % step == 0 and number:
                            print(f"{number}/{len(times)} フレーム", file=sys.stderr)
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                finally:
                    if not process.stdin.closed:
                        process.stdin.close()
                    code = process.wait()
            if code != 0:
                raise Mp4Error(f"ffmpeg が失敗しました: {log.read_text(encoding='utf-8', errors='replace').strip()[-500:]}")
        except Error as e:
            raise Mp4Error(f"ブラウザの操作に失敗しました: {str(e).splitlines()[0]}") from None
        finally:
            browser.close()
        destination = out_dir(root, out) / "mp4"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.move(str(output), destination / "video.mp4")
        shutil.copyfile(directory / "TERMS.txt", destination / "TERMS.txt")
    return destination / "video.mp4"
