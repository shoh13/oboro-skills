"""行ごとの合成音声のキャッシュ。"""

import subprocess
import sys
import wave
from pathlib import Path

import pytest
from test_voice_engine import FakeEngine, write_project

from kataribe import cli, tts, ttscache
from kataribe.adapters import voicevox
from kataribe.project import load_project

LINES = [
    {"speaker": "四国めたん", "text": "今日はパーティショニングの話よ。"},
    {"speaker": "ずんだもん", "text": "楽しみなのだ。"},
    {"speaker": "ずんだもん", "text": "データを分けるのだ。"},
]

PLACEHOLDER = """
import argparse, sys, wave
parser = argparse.ArgumentParser()
parser.add_argument("--voice"); parser.add_argument("--speed"); parser.add_argument("--output")
args = parser.parse_args()
text = sys.stdin.read()
with open({log!r}, "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
with wave.open(args.output, "wb") as out:
    out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000)
    out.writeframes(b"\\x00\\x01" * (2400 * max(1, len(text) // 4)))
"""


def run_build(tmp_path, capsys, cache: bool = True) -> tuple[list[str], bytes]:
    """（stderr の行, つないだ音声）。"""
    work = tmp_path / f"work-{len(list(tmp_path.glob('work-*')))}"
    work.mkdir()
    _, audio = cli._synthesize(load_project(tmp_path / "project"), work, cache)
    return capsys.readouterr().err.splitlines(), audio


@pytest.fixture
def placeholder(tmp_path, monkeypatch):
    """独自のアダプター（KATARIBE_TTS_CMD）。呼ばれるたびに引数を log に書く。エンジンには触れさせない。"""
    script = tmp_path / "placeholder_tts.py"
    log = tmp_path / "calls.log"
    script.write_text(PLACEHOLDER.format(log=str(log)), encoding="utf-8")
    monkeypatch.setenv("KATARIBE_TTS_CMD", f"{sys.executable} {script}")
    monkeypatch.setenv("KATARIBE_TTS_CACHE", str(tmp_path / "cache"))

    def no_engine(*args, **kwargs):
        raise AssertionError("KATARIBE_TTS_CMD のときにエンジンに触れた")

    monkeypatch.setattr(voicevox, "_request", no_engine)
    monkeypatch.setattr(voicevox, "_ensure_container", no_engine)
    (tmp_path / "project").mkdir()
    write_project(tmp_path / "project", LINES, {"TB": {"reading": "テラバイト", "accent": 3}})
    return lambda: log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_2回目のbuildはキャッシュから音声を使い合成しない(tmp_path, capsys, placeholder):
    first_err, first_audio = run_build(tmp_path, capsys)
    second_err, second_audio = run_build(tmp_path, capsys)

    assert "音声: 3 行のうち、合成 3 行、キャッシュ 0 行" in first_err
    assert "音声: 3 行のうち、合成 0 行、キャッシュ 3 行" in second_err
    assert len(placeholder()) == 3
    assert second_audio == first_audio


def test_文を変えた行だけを合成する(tmp_path, capsys, placeholder):
    run_build(tmp_path, capsys)
    changed = [dict(line) for line in LINES]
    changed[2]["text"] = "データを分割するのだ。"
    write_project(tmp_path / "project", changed)

    err, _ = run_build(tmp_path, capsys)

    assert "音声: 3 行のうち、合成 1 行、キャッシュ 2 行" in err
    assert len(placeholder()) == 4


def test_no_cacheはキャッシュを読まず書かない(tmp_path, capsys, placeholder):
    run_build(tmp_path, capsys)
    before = sorted((tmp_path / "cache").iterdir())

    err, _ = run_build(tmp_path, capsys, cache=False)

    assert "音声: 3 行のうち、合成 3 行、キャッシュ 0 行" in err
    assert sorted((tmp_path / "cache").iterdir()) == before


def test_offはキャッシュを使わない(tmp_path, capsys, placeholder, monkeypatch):
    monkeypatch.setenv("KATARIBE_TTS_CACHE", "off")

    run_build(tmp_path, capsys)
    err, _ = run_build(tmp_path, capsys)

    assert "音声: 3 行のうち、合成 3 行、キャッシュ 0 行" in err
    assert not (tmp_path / "cache").exists()


def test_キャッシュに書けなくてもbuildは続ける(tmp_path, capsys, placeholder, monkeypatch):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("KATARIBE_TTS_CACHE", str(blocker / "tts"))

    err, audio = run_build(tmp_path, capsys)

    assert sum(line.startswith("警告: 音声のキャッシュに書き込めません") for line in err) == 1
    assert "音声: 3 行のうち、合成 3 行、キャッシュ 0 行" in err
    assert audio


def test_キャッシュの音声は途中のファイルを残さない(tmp_path, capsys, placeholder):
    run_build(tmp_path, capsys)

    names = [path.name for path in (tmp_path / "cache").iterdir()]
    assert len(names) == 3
    assert all(name.endswith(".wav") and not name.startswith(".") for name in names)
    for path in (tmp_path / "cache").iterdir():
        with wave.open(str(path), "rb") as audio:
            assert audio.getnframes() > 0


# 既定の VOICEVOX のアダプター


@pytest.fixture
def default_adapter(tmp_path, monkeypatch):
    """既定のアダプター。合成は記録するだけ（WAV を書く）。エンジンは偽物。"""
    engine = FakeEngine()
    calls: list[dict] = []

    def synthesize(text, voice, output, **options):
        with wave.open(str(output), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
            out.writeframes(b"\x00\x01" * 2400)
        calls.append({"text": text, "voice": voice, **options})

    monkeypatch.delenv("KATARIBE_TTS_CMD", raising=False)
    monkeypatch.delenv("KATARIBE_VOICEVOX_URL", raising=False)
    monkeypatch.setenv("KATARIBE_TTS_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(voicevox, "_request", engine)
    monkeypatch.setattr(voicevox, "_ensure_container", lambda: "http://own")
    monkeypatch.setattr(cli, "synthesize", synthesize)
    (tmp_path / "project").mkdir()
    write_project(tmp_path / "project", LINES, {"TB": {"reading": "テラバイト", "accent": 3}})
    return engine, calls


def test_既定のアダプターは用意したエンジンで合成し辞書を先に合わせる(tmp_path, capsys, default_adapter):
    engine, calls = default_adapter

    run_build(tmp_path, capsys)

    assert calls == [{"text": line["text"], "voice": line["speaker"], "engine": "http://own"} for line in LINES]
    assert engine.dictionary() == {("テラバイト", "テラバイト", 3)}


def test_全行がキャッシュにあればエンジンを起動しない(tmp_path, capsys, default_adapter, monkeypatch):
    run_build(tmp_path, capsys)

    def no_engine(*args, **kwargs):
        raise AssertionError("エンジンに触れた")

    monkeypatch.setattr(voicevox, "_request", no_engine)
    monkeypatch.setattr(voicevox, "_ensure_container", no_engine)
    err, _ = run_build(tmp_path, capsys)

    assert "音声: 3 行のうち、合成 0 行、キャッシュ 3 行" in err


def change_accent(tmp_path, monkeypatch):
    write_project(tmp_path / "project", LINES, {"TB": {"reading": "テラバイト", "accent": 0}})


def change_image(tmp_path, monkeypatch):
    monkeypatch.setattr(voicevox, "IMAGE", "voicevox/voicevox_engine:cpu-ubuntu24.04-0.26.0")


@pytest.mark.parametrize(
    ("change", "synthesized"),
    [(change_accent, 3), (change_image, 3)],
    ids=["アクセント辞書", "イメージ"],
)
def test_音声を変えるものが変わればキャッシュを使わない(tmp_path, capsys, default_adapter, monkeypatch, change, synthesized):
    run_build(tmp_path, capsys)

    change(tmp_path, monkeypatch)
    err, _ = run_build(tmp_path, capsys)

    assert f"音声: 3 行のうち、合成 {synthesized} 行、キャッシュ {3 - synthesized} 行" in err


def test_外部のエンジンの版が変わればキャッシュを使わない(tmp_path, capsys, default_adapter, monkeypatch):
    engine, _ = default_adapter
    monkeypatch.setenv("KATARIBE_VOICEVOX_URL", "http://shared")
    run_build(tmp_path, capsys)
    same_err, _ = run_build(tmp_path, capsys)

    engine.version = "0.26.0"
    err, _ = run_build(tmp_path, capsys)

    assert "音声: 3 行のうち、合成 0 行、キャッシュ 3 行" in same_err
    assert "音声: 3 行のうち、合成 3 行、キャッシュ 0 行" in err


def test_エンジンを用意できなければTtsErrorで失敗する(tmp_path, capsys, default_adapter, monkeypatch):
    def down():
        raise voicevox.AdapterError("VOICEVOX を起動できません: Docker が動いていません")

    monkeypatch.setattr(voicevox, "_ensure_container", down)

    with pytest.raises(cli.TtsError, match="Docker が動いていません"):
        run_build(tmp_path, capsys)


def test_build_no_cacheのフラグはキャッシュを使わない(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "build", lambda root, extras=False, out=None, cache=True: seen.append(cache))

    cli.main(["build", str(tmp_path)])
    cli.main(["build", str(tmp_path), "--no-cache"])

    assert seen == [True, False]


def test_キャッシュの既定の置き場所(monkeypatch):
    monkeypatch.delenv("KATARIBE_TTS_CACHE", raising=False)
    assert ttscache.cache_dir() == Path.home() / ".cache" / "kataribe" / "tts"
    monkeypatch.setenv("KATARIBE_TTS_CACHE", "off")
    assert ttscache.cache_dir() is None


@pytest.mark.parametrize("value", ["off", "OFF", " Off "])
def test_キャッシュはoffの大文字小文字を問わず無効にできる(monkeypatch, value):
    monkeypatch.setenv("KATARIBE_TTS_CACHE", value)

    assert ttscache.cache_dir() is None


def test_キャッシュの置き場所はホームの記号を展開する(monkeypatch):
    monkeypatch.setenv("KATARIBE_TTS_CACHE", "~/kataribe-tts")

    assert ttscache.cache_dir() == Path.home() / "kataribe-tts"


# アダプターに渡す用意済みのエンジン


@pytest.fixture
def adapter_runs(monkeypatch):
    runs: list[dict] = []

    def run(command, input, capture_output, text, env=None):
        Path(command[command.index("--output") + 1]).write_bytes(b"RIFF")
        runs.append({"command": command, "env": env})
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(tts.subprocess, "run", run)
    return runs


def test_既定のアダプターには用意済みのエンジンのURLを渡す(adapter_runs, monkeypatch, tmp_path):
    monkeypatch.delenv("KATARIBE_TTS_CMD", raising=False)

    tts.synthesize("文", "ずんだもん", tmp_path / "a.wav", engine="http://own:1")

    assert adapter_runs[0]["command"][-6:] == ["--voice", "ずんだもん", "--speed", "1.0", "--output", str(tmp_path / "a.wav")]
    assert adapter_runs[0]["env"]["KATARIBE_VOICEVOX_URL"] == "http://own:1"


def test_独自のアダプターにはエンジンのURLを渡さない(adapter_runs, monkeypatch, tmp_path):
    monkeypatch.setenv("KATARIBE_TTS_CMD", "my-tts --flag")

    tts.synthesize("文", "ずんだもん", tmp_path / "a.wav", engine="http://own:1")

    assert adapter_runs[0]["command"] == ["my-tts", "--flag", "--voice", "ずんだもん", "--speed", "1.0", "--output", str(tmp_path / "a.wav")]
    assert adapter_runs[0]["env"] is None
