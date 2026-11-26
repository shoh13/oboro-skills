"""動画（kataribe）とスライド（kataribe-slides）は、同じ実行コードを別々に同梱する。片方だけを直すと食い違うので、一致を検査する。"""
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
VIDEO = SKILLS / "kataribe"
SLIDES = SKILLS / "kataribe-slides"
SHARED = ["src/kataribe", "pyproject.toml", "uv.lock"]
IGNORED_DIRS = {"__pycache__"}
IGNORED_NAMES = {".DS_Store"}


def files_of(root: Path) -> dict[str, bytes]:
    found = {}
    for entry in SHARED:
        path = root / entry
        paths = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for file in paths:
            relative = file.relative_to(root)
            if IGNORED_DIRS & set(relative.parts) or file.name in IGNORED_NAMES or file.suffix == ".pyc":
                continue
            found[relative.as_posix()] = file.read_bytes()
    return found


def test_動画とスライドの実行コードと依存の定義は_バイト単位で一致する():
    video, slides = files_of(VIDEO), files_of(SLIDES)

    only_video = sorted(video.keys() - slides.keys())
    only_slides = sorted(slides.keys() - video.keys())
    differ = sorted(name for name in video.keys() & slides.keys() if video[name] != slides[name])

    assert video and slides, "動画またはスライドの実行コードが見つからない"
    assert (only_video, only_slides, differ) == ([], [], []), (
        "oboro/skills/kataribe と oboro/skills/kataribe-slides の "
        f"{', '.join(SHARED)} を同じにする（動画だけ: {only_video}、スライドだけ: {only_slides}、内容が違う: {differ}）"
    )
