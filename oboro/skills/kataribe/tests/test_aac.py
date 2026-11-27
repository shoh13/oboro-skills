"""単一HTMLの音声は AAC（48 kbps）で埋め込む（仕様 R5・AC-39）。"""
import base64
import json
import re

import pytest
from conftest import run_build

STALE = "前回の out/ は古いままです"


def embedded(project) -> tuple[str, bytes]:
    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    match = re.search(r'<audio id="kataribe-audio" src="data:(audio/[^;]+);base64,([^"]+)"', html)
    assert match, "音声が単一HTMLに埋め込まれていません"
    return match.group(1), base64.b64decode(match.group(2))


def test_単一HTMLの音声はAACのm4aで埋め込まれ_WAVは含まれない(project):
    assert run_build(project).returncode == 0

    mime, data = embedded(project)

    assert mime == "audio/mp4"
    assert data[4:8] == b"ftyp"  # MP4（m4a）のコンテナ
    assert b"mp4a" in data  # AAC の音声トラック
    assert b"RIFF" not in data[:16] and b"WAVE" not in data[:16]


def test_AACの音声は_ブラウザで再生でき_長さはタイムラインとほぼ同じ(browser, project):
    assert run_build(project).returncode == 0
    page = browser.new_page()
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")

    duration = page.evaluate("document.getElementById('kataribe-audio').duration")
    timeline = json.loads(page.eval_on_selector("#kataribe-timeline", "el => el.textContent"))
    page.close()

    # AAC は 1024 標本の単位なので、末尾がわずかに伸びる
    assert duration == pytest.approx(timeline["duration"], abs=0.1)


def test_副産物の音声は_WAVのまま(project):
    assert run_build(project, args=["--extras"]).returncode == 0

    assert (project / "out" / "extras" / "audio.wav").read_bytes()[:4] == b"RIFF"


def test_AACに変換できないときは_buildは失敗し_前回のoutを残す(project):
    assert run_build(project).returncode == 0
    before = (project / "out" / "video.html").read_bytes()

    result = run_build(project, extra_env={"KATARIBE_FFMPEG": "/nonexistent/ffmpeg"})

    assert result.returncode == 1
    assert "AAC" in result.stderr
    assert STALE in result.stderr
    assert "Traceback" not in result.stderr
    assert (project / "out" / "video.html").read_bytes() == before


def test_AACを再生できないブラウザでは_Chromeを入れるよう示して止める(browser):
    from kataribe.browser import BrowserError, require_aac

    page = browser.new_page()
    page.set_content("<!doctype html><p>x</p>")
    page.evaluate("HTMLMediaElement.prototype.canPlayType = () => ''")  # AAC を持たない Chromium のふり

    with pytest.raises(BrowserError, match="Google Chrome"):
        require_aac(page)
    page.close()


def test_AACを再生できるブラウザでは_止めない(browser):
    from kataribe.browser import require_aac

    page = browser.new_page()
    page.set_content("<!doctype html><p>x</p>")

    require_aac(page)
    page.close()
