"""出力先の決め方（--out、oboro の設定ファイルの kataribe.output_dir、既定の <project>/out の順）。"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import FAKE_TTS, make_project, run_build, run_shoot

from kataribe.cli import main


def write_oboro_config(tmp_path: Path, monkeypatch, text: str) -> Path:
    config = tmp_path / "oboro" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(text, encoding="utf-8")
    monkeypatch.setenv("OBORO_CONFIG", str(config))
    return config


def outputs(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def test_設定がなければ_出力先は_プロジェクトの_out(project, capsys):
    assert run_build(project).returncode == 0
    assert outputs(project / "out") == ["transcript.md", "video.html"]

    assert main(["assets"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "出力先の既定: <プロジェクト>/out"


def test_設定の_kataribe_output_dir_があれば_その下のプロジェクト名のディレクトリに出す(project, tmp_path, monkeypatch, capsys):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[org]\ndir = "~/org"\n\n[kataribe]\noutput_dir = "{videos}"\n')

    result = run_build(project)

    assert result.returncode == 0, result.stderr
    assert outputs(videos / "project") == ["transcript.md", "video.html"]
    assert outputs(videos) == ["project"]  # 一時ディレクトリが残らない
    assert not (project / "out").exists()
    assert main(["assets"]) == 0
    note = capsys.readouterr().out.splitlines()[-1]
    assert note == f"出力先の既定: {videos}/<プロジェクトのディレクトリ名>（oboro の設定ファイルの kataribe.output_dir）"


def test_build_のあとの_shoot_も_設定の出力先を読む(project, tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    assert run_build(project).returncode == 0

    result = run_shoot(project)

    assert result.returncode == 0, result.stderr
    assert outputs(videos / "project" / "frames") == ["s1-end.png", "s2-end.png", "s3-end.png"]


def test_設定の出力先と_OBORO_CONFIG_のチルダは_ホームに展開する(project, tmp_path, monkeypatch):
    home = tmp_path / "home"
    config = home / "custom" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[kataribe]\noutput_dir = "~/videos"\n', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBORO_CONFIG", "~/custom/config.toml")

    result = run_build(project)

    assert result.returncode == 0, result.stderr
    assert outputs(home / "videos" / "project") == ["transcript.md", "video.html"]


def test_引数の_out_は_設定より優先する(project, tmp_path, monkeypatch):
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{tmp_path / "videos"}"\n')
    out = tmp_path / "成果物"

    result = run_build(project, args=["--out", str(out)])

    assert result.returncode == 0, result.stderr
    assert outputs(out) == ["transcript.md", "video.html"]
    assert not (tmp_path / "videos").exists()


def test_プロジェクトを_ドット_で渡しても_プロジェクトのディレクトリ名を使う(project, tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    env = dict(os.environ, KATARIBE_TTS_CMD=f"{sys.executable} {FAKE_TTS}")

    result = subprocess.run([sys.executable, "-m", "kataribe", "build", "."], cwd=project, capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stderr
    assert outputs(videos) == ["project"]


@pytest.mark.parametrize(
    "text",
    ["[kataribe\n", "[kataribe]\noutput_dir = 1\n", '[kataribe]\noutput_dir = ""\n'],
    ids=["TOML_でない", "文字列でない", "空"],
)
def test_設定が読めないか値の形が違えば_設定ファイルを示して_何も出さずに失敗する(text, tmp_path, monkeypatch):
    project = make_project(tmp_path / "project")
    config = write_oboro_config(tmp_path, monkeypatch, text)

    result = run_build(project)

    assert result.returncode == 1
    assert str(config) in result.stderr
    assert "Traceback" not in result.stderr
    assert not (project / "out").exists()
