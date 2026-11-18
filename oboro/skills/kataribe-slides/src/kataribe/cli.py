import argparse
import sys
import tempfile
from pathlib import Path

from kataribe.art import ArtError, build_cast, used_faces
from kataribe.audio import AudioError, concat_wavs, encode_aac
from kataribe.browser import BrowserError
from kataribe.check import lint_warnings, speed_warnings
from kataribe.extras import write_extras
from kataribe.mouth import mouth_levels
from kataribe.mp4 import DEFAULT_FPS, DEFAULT_SIZE, FPS_CHOICES, SIZES, make_mp4
from kataribe.output import BuildError, out_dir, write_output
from kataribe.project import ProjectError, load_project
from kataribe.reading import spoken_text
from kataribe.render import render_html, render_transcript
from kataribe.shoot import shoot
from kataribe.slides import build_slides, lint_slides
from kataribe.timeline import build_timeline, measure_seconds
from kataribe.tts import TtsError, synthesize
from kataribe.verify import MARKS, verify


def _warn(messages: list[str]) -> None:
    for message in messages:
        print(message, file=sys.stderr)


STALE_NOTICE = "前回の out/ は古いままです（今回の台本は反映されていません）"
MAX_HTML_BYTES = 16 * 1024 * 1024


def _synthesize(project, work: Path) -> tuple[dict, bytes]:
    wavs = []
    for index, line in enumerate(project.lines):
        assert line.speaker is not None  # 地の文は slides だけで、動画の台本にはない
        wav = work / f"{index}.wav"
        synthesize(spoken_text(line, project.readings), line.speaker, wav)
        wavs.append(wav)
    timeline = build_timeline(project, [measure_seconds(wav) for wav in wavs], [mouth_levels(wav) for wav in wavs])
    return timeline, concat_wavs(wavs)


def build(root: Path, extras: bool = False, out: Path | None = None) -> None:
    try:
        project = load_project(root)
        _warn(lint_warnings(project))
        cast = build_cast(project)  # 素材の取得・検証は、時間のかかる音声合成の前に行う
        with tempfile.TemporaryDirectory() as work:
            timeline, audio = _synthesize(project, Path(work))
        _warn(speed_warnings(timeline))
        embedded_audio = encode_aac(audio)  # 単一HTMLは AAC。副産物と mp4 は WAV のまま

        def write(stage: Path) -> None:
            html = render_html(project, timeline, embedded_audio, cast).encode("utf-8")
            if len(html) > MAX_HTML_BYTES:
                raise BuildError(f"単一HTMLが {len(html):,} バイトで、上限 {MAX_HTML_BYTES:,} バイト（16 MiB）を超えています")
            (stage / "video.html").write_bytes(html)
            (stage / "transcript.md").write_text(render_transcript(project), encoding="utf-8")
            if extras:
                write_extras(stage, project, timeline, audio)

        write_output(root, write, out)
    except (ProjectError, ArtError, TtsError, AudioError, BuildError) as e:
        if (out_dir(root, out) / "video.html").is_file():
            e.add_note(STALE_NOTICE)
        raise


def lint(root: Path, slides: bool = False) -> None:
    if slides:
        _warn(lint_slides(root))
        return
    project = load_project(root)
    used_faces(project)  # 表情が立ち絵の定義にあるか（素材は取得しない）
    _warn(lint_warnings(project))


def run_verify(root: Path, out: Path | None = None) -> int:
    result = verify(root, out=out)
    _warn(result.warnings)
    for check in result.checks:
        mark = MARKS[check.number - 1]
        if check.ok:
            print(f"{mark} {check.name}: OK")
        else:
            print(f"{mark} {check.name}: NG")
            for problem in check.problems:
                print(f"    {problem}")
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kataribe")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="台本と画面から単一HTMLを作る")
    build_parser.add_argument("project", type=Path)
    build_parser.add_argument("--extras", action="store_true", help="MP4化向けの副産物（音声・字幕VTT・タイムライン・利用条件）も出す")
    lint_parser = commands.add_parser("lint", help="台本を検査する（音声は合成しない）")
    lint_parser.add_argument("project", type=Path)
    lint_parser.add_argument("--slides", action="store_true", help="スライドの台本として検査する（地の文を許す）")
    slides_parser = commands.add_parser("slides", help="地の文と立ち絵のテロップで進む PowerPoint のスライド（out/slides.pptx）を作る（音声なし）")
    slides_parser.add_argument("project", type=Path)
    shoot_parser = commands.add_parser("shoot", help="シーンごとのスクリーンショットを撮る")
    shoot_parser.add_argument("project", type=Path)
    shoot_parser.add_argument("--at", choices=["start", "mid", "end"], default="end")
    verify_parser = commands.add_parser("verify", help="build 済みの動画を実時間で再生して検証する")
    verify_parser.add_argument("project", type=Path)
    mp4_parser = commands.add_parser("mp4", help="副産物（build --extras）から MP4 を作る")
    mp4_parser.add_argument("project", type=Path)
    mp4_parser.add_argument("--size", choices=list(SIZES), default=DEFAULT_SIZE)
    mp4_parser.add_argument("--fps", type=int, choices=FPS_CHOICES, default=DEFAULT_FPS)
    for command_parser in (build_parser, slides_parser, shoot_parser, verify_parser, mp4_parser):
        command_parser.add_argument("--out", type=Path, help="出力先のディレクトリ（既定は <project>/out）")
    args = parser.parse_args(argv)
    try:
        if args.command == "lint":
            lint(args.project, slides=args.slides)
        elif args.command == "slides":
            build_slides(args.project, _warn, out=args.out)
        elif args.command == "mp4":
            make_mp4(args.project, args.size, args.fps, out=args.out)
        elif args.command == "verify":
            return run_verify(args.project, out=args.out)
        elif args.command == "shoot":
            shoot(args.project, args.at, out=args.out)
        else:
            build(args.project, extras=args.extras, out=args.out)
    except (ProjectError, ArtError, TtsError, AudioError, BuildError, BrowserError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        for note in getattr(e, "__notes__", []):
            print(note, file=sys.stderr)
        return 1
    return 0
