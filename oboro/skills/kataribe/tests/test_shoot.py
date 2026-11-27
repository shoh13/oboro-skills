import html
import io
import struct

import pytest
from conftest import make_project, run_build, run_shoot
from kataribe.browser import FREEZE_CSS
from kataribe.shoot import seek_and_wait

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

COLORED_SCENES = """\
<section data-scene="s1" style="background:#d33;height:200px"><h1>シーン1</h1></section>
<section data-scene="s2" style="background:#3a3;height:200px"><h1>シーン2</h1></section>
<section data-scene="s3" style="background:#33d;height:200px"><h1>シーン3</h1></section>
"""


@pytest.fixture
def built(tmp_path):
    project = make_project(tmp_path / "project", scenes=COLORED_SCENES)
    assert run_build(project).returncode == 0
    return project


def pixels(data: bytes) -> tuple[tuple[int, int], bytes]:
    """PNG を、大きさと RGBA の画素にする。Chrome の PNG は、同じ画素でも圧縮の結果が毎回同じとは限らない。"""
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGBA")
    return image.size, image.tobytes()


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == PNG_SIGNATURE
    return struct.unpack(">II", data[16:24])


def test_atを指定しないと_endでシーンごとのPNGが_out_framesに出力される(built):
    result = run_shoot(built)

    assert result.returncode == 0, result.stderr
    frames = built / "out" / "frames"
    assert sorted(path.name for path in frames.iterdir()) == ["s1-end.png", "s2-end.png", "s3-end.png"]
    for path in frames.iterdir():
        width, height = png_size(path.read_bytes())
        assert width > 600 and height > 300



def test_プロジェクトを相対パスで指定しても_撮影できる(built):
    result = run_shoot(built.relative_to(built.parent), cwd=built.parent)

    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in (built / "out" / "frames").iterdir()) == ["s1-end.png", "s2-end.png", "s3-end.png"]

from kataribe.shoot import capture_times


def timeline_of(*scenes: list[tuple[float, float]]) -> dict:
    lines, spans = [], []
    for index, scene_lines in enumerate(scenes):
        scene_id = f"s{index + 1}"
        spans.append({"id": scene_id, "start": scene_lines[0][0], "end": scene_lines[-1][1]})
        lines += [{"id": f"{scene_id}-{i}", "scene": scene_id, "start": start, "end": end} for i, (start, end) in enumerate(scene_lines)]
    return {"scenes": spans, "lines": lines}


FOUR_LINES = timeline_of([(0.0, 2.0), (2.0, 4.0), (4.0, 6.0), (6.0, 8.0)])


@pytest.mark.parametrize("at, expected", [("start", 0.3), ("mid", 4.3), ("end", 6.3)])
def test_撮る時刻は_先頭行_中央行_最終行の開始から0_3秒後(at, expected):
    assert capture_times(FOUR_LINES, at) == [("s1", pytest.approx(expected))]


@pytest.mark.parametrize("count, mid_start", [(1, 0.0), (2, 2.0), (3, 2.0), (5, 4.0)])
def test_中央行は_行の列の中ほどの行で_偶数のときは後ろ側を選ぶ(count, mid_start):
    timeline = timeline_of([(2.0 * i, 2.0 * i + 2.0) for i in range(count)])

    assert capture_times(timeline, "mid") == [("s1", pytest.approx(mid_start + 0.3))]


def test_行が0_3秒より短いとき_撮る時刻はその行の中央になり_前後の行に食い込まない():
    timeline = timeline_of([(0.0, 0.1), (0.1, 0.24)], [(0.24, 0.42)])

    times = dict(capture_times(timeline, "start"))

    assert times["s1"] == pytest.approx(0.05)
    assert times["s2"] == pytest.approx(0.33)


def reference(browser, project, seconds: float) -> bytes:
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
    # shoot と同じ撮影の条件（動きを止める CSS と、立ち絵の準備を待つシーク）で撮る
    page.add_style_tag(content=FREEZE_CSS)
    seek_and_wait(page, seconds)
    data = page.locator("#kataribe-stage").screenshot()
    page.close()
    return data


# 行は 0〜0.10、0.10〜0.24（s1）、0.24〜0.42（s2）、0.42〜0.50（s3）。撮る時刻を、規則（行の開始から 0.3 秒後、
# 行が 0.6 秒より短いときは行の中央）から手で計算した。立ち絵のまばたきは時刻で決まるので、同じ時刻で比べる
SCENE_TIMES = {
    "start": {"s1": 0.05, "s2": 0.33, "s3": 0.46},
    "mid": {"s1": 0.17, "s2": 0.33, "s3": 0.46},
    "end": {"s1": 0.17, "s2": 0.33, "s3": 0.46},
}


@pytest.mark.parametrize("at", ["start", "mid", "end"])
def test_写っているのは_そのシーンの画面で_別のシーンに食い込まない(browser, built, at):
    assert run_shoot(built, at).returncode == 0

    images = {}
    for scene, seconds in SCENE_TIMES[at].items():
        shot = (built / "out" / "frames" / f"{scene}-{at}.png").read_bytes()
        assert pixels(shot) == pixels(reference(browser, built, seconds)), f"{scene}-{at}.png が、そのシーンの画面と一致しません"
        images[scene] = pixels(shot)
    assert len(set(images.values())) == 3


def test_atを変えて撮っても_前の画像は上書きされず残る(built):
    frames = built / "out" / "frames"
    assert run_shoot(built, "start").returncode == 0
    start_images = {path.name: path.read_bytes() for path in frames.iterdir()}

    assert run_shoot(built, "mid").returncode == 0
    assert run_shoot(built, "end").returncode == 0

    assert sorted(path.name for path in frames.iterdir()) == sorted(f"{scene}-{at}.png" for scene in ("s1", "s2", "s3") for at in ("start", "mid", "end"))
    for name, data in start_images.items():
        assert (frames / name).read_bytes() == data


def test_同じatで撮り直すと_同じ名前の画像が置き換わり_成功する(built):
    assert run_shoot(built, "end").returncode == 0

    result = run_shoot(built, "end")

    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in (built / "out" / "frames").iterdir()) == ["s1-end.png", "s2-end.png", "s3-end.png"]


def test_out_video_htmlがないとき_先にbuildするよう示して失敗する(tmp_path):
    project = make_project(tmp_path / "project", scenes=COLORED_SCENES)

    result = run_shoot(project)

    assert result.returncode != 0
    assert "build" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project / "out").exists()


UNUSABLE_IDS = ["../evil", "a/b", "a\\b", ".", "..", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b", "ctrl\x01", "trail.", "trail "]


@pytest.mark.parametrize("scene_id", UNUSABLE_IDS, ids=repr)
def test_ファイル名に使えないシーンIDのとき_何も出力せず_理由を示して失敗する(tmp_path, scene_id):
    from conftest import SCRIPT

    script = {**SCRIPT, "chapters": [{"id": "c1", "title": "章", "scenes": [{"id": scene_id, "lines": [{"speaker": "ずんだもん", "text": "こんにちは"}]}]}]}
    project = make_project(tmp_path / "project", script=script, scenes=f'<section data-scene="{html.escape(scene_id)}"></section>')
    assert run_build(project).returncode == 0

    result = run_shoot(project)

    assert result.returncode != 0
    assert "シーン" in result.stderr
    assert "Traceback" not in result.stderr
    assert not list((project / "out").rglob("*.png"))
    assert not list(tmp_path.rglob("evil*"))


def test_大文字小文字だけ違うシーンIDは_画像が上書きされるので_何も出力せず失敗する(tmp_path):
    from conftest import SCRIPT

    script = {
        **SCRIPT,
        "chapters": [
            {"id": "c1", "title": "章", "scenes": [{"id": "Intro", "lines": [{"speaker": "ずんだもん", "text": "こんにちは"}]}, {"id": "intro", "lines": [{"speaker": "ずんだもん", "text": "はじめます"}]}]}
        ],
    }
    scenes = '<section data-scene="Intro">A</section><section data-scene="intro">B</section>'
    project = make_project(tmp_path / "project", script=script, scenes=scenes)
    assert run_build(project).returncode == 0

    result = run_shoot(project)

    assert result.returncode != 0
    assert "Intro" in result.stderr and "intro" in result.stderr
    assert "大文字小文字" in result.stderr
    assert "Traceback" not in result.stderr
    assert not list((project / "out").rglob("*.png"))


def test_シークが完了しないとき_待ち続けずに_時間切れで失敗する(browser):
    from kataribe.shoot import ShootError, seek_and_wait

    page = browser.new_page()
    page.set_content('<audio id="kataribe-audio"></audio>')

    with pytest.raises(ShootError, match="再生位置"):
        seek_and_wait(page, 0.1, timeout_ms=300)
    page.close()


def test_シークが完了すれば_待たずに戻る(browser, built):
    from kataribe.shoot import seek_and_wait

    page = browser.new_page()
    page.goto((built / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")

    seek_and_wait(page, 0.3, timeout_ms=5000)

    assert page.evaluate("document.getElementById('kataribe-audio').currentTime") == pytest.approx(0.3, abs=0.01)
    page.close()


def test_行単位の出現があると_atによって画像が変わる(tmp_path):
    scenes = """\
<section data-scene="s1" style="height:200px"><h1>見出し</h1><p data-at="1" style="background:#d33;height:80px">2行目から</p></section>
<section data-scene="s2" style="height:200px"><p>1行だけ</p></section>
<section data-scene="s3" style="height:200px"><p>1行だけ</p></section>
"""
    project = make_project(tmp_path / "project", scenes=scenes)
    assert run_build(project).returncode == 0
    for at in ("start", "mid", "end"):
        assert run_shoot(project, at).returncode == 0
    frames = project / "out" / "frames"

    def image(scene: str, at: str) -> tuple[tuple[int, int], bytes]:
        return pixels((frames / f"{scene}-{at}.png").read_bytes())

    assert image("s1", "start") != image("s1", "end")  # 先頭行(0行目)では2行目から出る要素が見えない
    assert image("s1", "mid") == image("s1", "end")  # 2行のシーンの中央行は2行目
    assert image("s2", "start") == image("s2", "mid") == image("s2", "end")  # 1行のシーンは、どの at も同じ行


MOTION_STYLE = "<style>@keyframes fade { from { opacity: 0 } to { opacity: 1 } } #box { animation: fade 10s forwards } .soft { transition: opacity 10s }</style>"
STILL_STYLE = "<style>#box { }</style>"
MOTION_BODY = (
    '<section data-scene="s1" style="height:200px">{style}'
    '<div id="box" style="background:#d33;height:60px">箱</div>'
    '<p class="{soft}" data-focus="0">A</p><p data-focus="1">B</p></section>'
    '<section data-scene="s2">2</section><section data-scene="s3">3</section>'
)


def shot_s1(tmp_path, name, style, soft):
    project = make_project(tmp_path / name, scenes=MOTION_BODY.format(style=style, soft=soft))
    assert run_build(project).returncode == 0
    result = run_shoot(project, "end")
    assert result.returncode == 0, result.stderr
    return project, pixels((project / "out" / "frames" / "s1-end.png").read_bytes())


def test_撮影のとき_animationとtransitionは完了状態になる_動きのない画面と同じ画像になる(tmp_path):
    _, moving = shot_s1(tmp_path, "moving", MOTION_STYLE, "soft")
    _, still = shot_s1(tmp_path, "still", STILL_STYLE, "")

    assert moving == still


def test_撮影のための無効化は_単一HTMLには残らない(tmp_path):
    project, _ = shot_s1(tmp_path, "moving", MOTION_STYLE, "soft")

    text = (project / "out" / "video.html").read_text(encoding="utf-8")
    assert "animation: fade 10s forwards" in text
    assert "animation-duration: 0s" not in text


def test_out_framesに今回のシーンに対応しない画像があると_警告を出して続行し_ファイルは消さない(built):
    frames = built / "out" / "frames"
    frames.mkdir(parents=True)
    stale = ["old-end.png", "old-start.png", "a-b-mid.png"]
    keep = ["s1-mid.png", "notes.txt", "readme.png", "s2-other.png"]
    for name in stale + keep:
        (frames / name).write_bytes(b"x")

    result = run_shoot(built, "end")

    assert result.returncode == 0, result.stderr
    warned = [line for line in result.stderr.splitlines() if line.startswith("警告:")]
    for name in stale:
        assert any(name in line and "古い画像" in line for line in warned), name
    for name in keep:
        assert not any(name in line for line in warned), name
    assert len(warned) == len(stale)
    for name in stale + keep:
        assert (frames / name).is_file(), name


def test_古い画像がなければ_警告は出ない(built):
    result = run_shoot(built, "end")

    assert result.returncode == 0
    assert "警告" not in result.stderr


def test_outを指定すると_そこのvideo_htmlから撮り_そこのframesに出す(tmp_path):
    project = make_project(tmp_path / "project", scenes=COLORED_SCENES)
    out = tmp_path / "成果物"
    assert run_build(project, args=["--out", str(out)]).returncode == 0

    result = run_shoot(project, out=out)

    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in (out / "frames").iterdir()) == ["s1-end.png", "s2-end.png", "s3-end.png"]
    assert not (project / "out").exists()


def test_outを指定してvideo_htmlがないとき_outつきのbuildを示して失敗する(tmp_path):
    project = make_project(tmp_path / "project", scenes=COLORED_SCENES)
    out = tmp_path / "成果物"

    result = run_shoot(project, out=out)

    assert result.returncode != 0
    assert f"--out {out}" in result.stderr
    assert not out.exists()
