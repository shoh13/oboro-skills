import re
import subprocess
import wave

import imageio_ffmpeg
import pytest
from conftest import make_project, run_build, run_mp4
from test_appearance import SCRIPT_4

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
# s1 は4行（各 0.10 秒）、2行目から赤い要素が出る。s2 は1行（0.10 秒）。音声の長さは 0.5 秒
SCENES = """\
<section data-scene="s1"><h1>一</h1><p data-at="1" style="font-size:300px;color:#e00;margin:0">■</p></section>
<section data-scene="s2"><h1>二</h1></section>
"""
CREDIT_SECONDS = 5.0


@pytest.fixture
def built(tmp_path):
    script = {**SCRIPT_4, "sources": [{"title": "出典A", "url": "https://example.com/a"}]}
    project = make_project(tmp_path / "p", script=script, scenes=SCENES)
    result = run_build(project, extra_env={"FAKE_TTS_TONE": "1"}, args=["--extras"])
    assert result.returncode == 0, result.stderr
    return project


def mp4_path(project):
    return project / "out" / "mp4" / "video.mp4"


def probe(path):
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    assert duration, info
    h, m, s = duration.groups()
    size = re.search(r"Video: .*?, (\d+)x(\d+)", info)
    fps = re.search(r"([\d.]+) fps", info)
    return {
        "seconds": int(h) * 3600 + int(m) * 60 + float(s),
        "size": (int(size.group(1)), int(size.group(2))) if size else None,
        "fps": float(fps.group(1)) if fps else None,
        "audio": "Audio:" in info,
    }


def mean_volume(path):
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
    volume = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", out)
    assert volume, out
    return float(volume.group(1).replace("-inf", "-999"))


def gray(path, seconds):
    raw = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(seconds), "-i", str(path), "-frames:v", "1",
         "-vf", "scale=64:36", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True,
    ).stdout
    assert len(raw) == 64 * 36
    return raw


def difference(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def audio_seconds(project):
    with wave.open(str(project / "out" / "extras" / "audio.wav"), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def test_既定では1280x720の30fpsで_映像長が音声長に5秒を足した長さになる(built):
    result = run_mp4(built)

    assert result.returncode == 0, result.stderr
    info = probe(mp4_path(built))
    assert info["size"] == (1280, 720)
    assert info["fps"] == 30
    assert info["seconds"] == pytest.approx(audio_seconds(built) + CREDIT_SECONDS, abs=0.3)


def test_サイズとfpsを指定すると_そのとおりの映像になる(built):
    result = run_mp4(built, "--size", "1920x1080", "--fps", "24")

    assert result.returncode == 0, result.stderr
    info = probe(mp4_path(built))
    assert info["size"] == (1920, 1080)
    assert info["fps"] == 24


def test_音声トラックがあり_無音でない(built):
    run_mp4(built)

    assert probe(mp4_path(built))["audio"]
    assert mean_volume(mp4_path(built)) > -60


def test_行単位の出現が映像に反映される_2行目から赤い要素が出る(built):
    run_mp4(built)

    before = gray(mp4_path(built), 0.05)
    after = gray(mp4_path(built), 0.15)
    assert difference(before, after) > 2


def test_末尾の5秒はクレジット画面で_本編の最後の画面と違う(built):
    run_mp4(built)

    body_end = gray(mp4_path(built), audio_seconds(built) - 0.05)
    credit_a = gray(mp4_path(built), audio_seconds(built) + 1)
    credit_b = gray(mp4_path(built), audio_seconds(built) + 4)
    assert difference(body_end, credit_a) > 20
    assert difference(credit_a, credit_b) < 3


def test_利用条件ファイルがMP4と同じ場所に同梱される(built):
    run_mp4(built)

    terms = (mp4_path(built).parent / "TERMS.txt").read_text(encoding="utf-8")
    assert "VOICEVOX:ずんだもん" in terms


def test_副産物がないときは_buildの_extras_を示して失敗する(tmp_path):
    project = make_project(tmp_path / "p", script=SCRIPT_4, scenes=SCENES)
    assert run_build(project).returncode == 0

    result = run_mp4(project)

    assert result.returncode == 1
    assert "--extras" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project / "out" / "mp4").exists()


def test_単一HTMLがないときは_buildを示して失敗する(built):
    (built / "out" / "video.html").unlink()

    result = run_mp4(built)

    assert result.returncode == 1
    assert "build" in result.stderr
    assert "Traceback" not in result.stderr


def test_ffmpegが取得できないときは_失敗し_出力を作らない(built):
    result = run_mp4(built, extra_env={"KATARIBE_FFMPEG": "/nonexistent/ffmpeg"})

    assert result.returncode == 1
    assert "ffmpeg" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (built / "out" / "mp4").exists()


def test_指定できないサイズとfpsは_引数のエラーになる(built):
    assert run_mp4(built, "--size", "640x480").returncode == 2
    assert run_mp4(built, "--fps", "25").returncode == 2


MOTION_SCENES = """\
<style>@keyframes fade { from { opacity: 0 } to { opacity: 1 } } #box { animation: fade 10s forwards } .soft { transition: opacity 10s }</style>
<section data-scene="s1"><div id="box" style="background:#e00;height:200px;margin:40px">箱</div>
<p class="soft" data-focus="0">A</p><p data-focus="1">B</p></section>
<section data-scene="s2"><h1>二</h1></section>
"""
STILL_SCENES = MOTION_SCENES.replace("#box { animation: fade 10s forwards } .soft { transition: opacity 10s }", "")


def mp4_with_scenes(tmp_path, name, scenes):
    project = make_project(tmp_path / name, script=SCRIPT_4, scenes=scenes)
    assert run_build(project, extra_env={"FAKE_TTS_TONE": "1"}, args=["--extras"]).returncode == 0
    result = run_mp4(project)
    assert result.returncode == 0, result.stderr
    return mp4_path(project)


def test_撮影のとき_animationとtransitionは完了状態になる_動きのない画面と同じ映像になる(tmp_path):
    moving = mp4_with_scenes(tmp_path, "moving", MOTION_SCENES)
    still = mp4_with_scenes(tmp_path, "still", STILL_SCENES)

    for seconds in (0.05, 0.15, 0.25):
        assert difference(gray(moving, seconds), gray(still, seconds)) < 3, seconds


def test_動きのある画面でも_単一HTMLの側には無効化が入らない(tmp_path):
    project = make_project(tmp_path / "moving", script=SCRIPT_4, scenes=MOTION_SCENES)
    assert run_build(project, extra_env={"FAKE_TTS_TONE": "1"}, args=["--extras"]).returncode == 0
    before = (project / "out" / "video.html").read_bytes()

    assert run_mp4(project).returncode == 0

    assert (project / "out" / "video.html").read_bytes() == before
