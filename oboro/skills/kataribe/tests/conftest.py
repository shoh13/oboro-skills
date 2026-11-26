import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fake_art import fake_art_env
from fake_voicevox import engine  # noqa: F401  偽の VOICEVOX エンジン（フィクスチャ）
from playwright.sync_api import sync_playwright

FAKE_TTS = Path(__file__).parent / "fake_tts.py"
SECONDS_PER_CHAR = 0.02

SCRIPT = {
    "title": "テスト動画",
    "chapters": [
        {
            "id": "c1",
            "title": "最初の章",
            "scenes": [
                {"id": "s1", "lines": [{"speaker": "ずんだもん", "text": "こんにちは"}, {"speaker": "ずんだもん", "text": "はじめましょう"}]},
                {"id": "s2", "lines": [{"speaker": "ずんだもん", "text": "二つ目のシーンです"}]},
            ],
        },
        {
            "id": "c2",
            "title": "次の章",
            "scenes": [{"id": "s3", "lines": [{"speaker": "ずんだもん", "text": "おしまい"}]}],
        },
    ],
}

SCENES = """\
<section data-scene="s1"><h1>シーン1</h1></section>
<section data-scene="s2"><h1>シーン2</h1></section>
<section data-scene="s3"><h1>シーン3</h1></section>
"""


def make_project(root: Path, script: dict | None = None, scenes: str | None = None, readings: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "script.json").write_text(json.dumps(script or SCRIPT, ensure_ascii=False), encoding="utf-8")
    (root / "scenes.html").write_text(SCENES if scenes is None else scenes, encoding="utf-8")
    (root / "readings.json").write_text("{}" if readings is None else readings, encoding="utf-8")
    return root


def run_build(project: Path, tts_cmd: str | None = None, extra_env: dict[str, str] | None = None, args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KATARIBE_TTS_CMD"] = tts_cmd if tts_cmd is not None else f"{sys.executable} {FAKE_TTS}"
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", "kataribe", "build", str(project), *(args or [])],
        capture_output=True,
        text=True,
        env=env,
    )


def run_shoot(project: Path, at: str | None = None, cwd: Path | None = None, out: Path | None = None) -> subprocess.CompletedProcess:
    command = [sys.executable, "-m", "kataribe", "shoot", str(project)]
    if at is not None:
        command += ["--at", at]
    if out is not None:
        command += ["--out", str(out)]
    return subprocess.run(command, capture_output=True, text=True, env=dict(os.environ), cwd=cwd)


def run_lint(project: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KATARIBE_TTS_CMD"] = "/nonexistent/kataribe-tts"
    return subprocess.run(
        [sys.executable, "-m", "kataribe", "lint", str(project)],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture(scope="session", autouse=True)
def fake_art(tmp_path_factory):
    """すべてのテストで、立ち絵素材をネットワークから取らず、テスト用の小さな素材を使う。"""
    env = fake_art_env(tmp_path_factory.mktemp("art"))
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    yield env
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def isolated_tts_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("KATARIBE_TTS_CACHE", str(tmp_path / "tts-cache"))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "project")


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            b = p.chromium.launch(headless=True)
        yield b
        b.close()


def build_and_read_spoken(project: Path, tmp_path: Path) -> list[str]:
    """build を実行し、偽のTTSが実際に受け取った文字列（行の順）を返す。"""
    log = tmp_path / "spoken.log"
    result = run_build(project, extra_env={"FAKE_TTS_LOG": str(log)})
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def player(browser, project):
    assert run_build(project).returncode == 0
    page = browser.new_page()
    page.set_default_timeout(5000)
    page.goto((project / "out" / "video.html").as_uri())
    page.wait_for_function("document.getElementById('kataribe-audio').readyState >= 1")
    yield page
    page.close()


def seek(page, seconds: float) -> None:
    page.evaluate(
        """seconds => new Promise(resolve => {
            const audio = document.getElementById('kataribe-audio');
            audio.addEventListener('seeked', () => requestAnimationFrame(() => resolve()), { once: true });
            audio.currentTime = seconds;
        })""",
        seconds,
    )


def visible_scenes(page) -> list[str]:
    return page.eval_on_selector_all(
        "section[data-scene]",
        "els => els.filter(e => e.offsetParent !== null).map(e => e.dataset.scene)",
    )


def run_verify(project: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "kataribe", "verify", str(project)],
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def run_mp4(project: Path, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", "kataribe", "mp4", str(project), *args],
        capture_output=True,
        text=True,
        env=env,
    )
