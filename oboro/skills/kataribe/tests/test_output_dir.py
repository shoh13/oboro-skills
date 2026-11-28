"""出力先の決め方（--out、oboro の設定ファイルの kataribe.output_dir、既定の <project>/out の順）。"""
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from conftest import FAKE_TTS, SCRIPT, make_project, run_build, run_shoot

from kataribe.cli import main
from kataribe.output import configured_out


def write_oboro_config(tmp_path: Path, monkeypatch, text: str) -> Path:
    config = tmp_path / "oboro" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(text, encoding="utf-8")
    monkeypatch.setenv("OBORO_CONFIG", str(config))
    return config


def outputs(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def only_output(parent: Path, name: str) -> Path:
    """parent の下にある、ただ1つの出力先（<name>-<パスから作る8文字>）。"""
    found = list(parent.iterdir())
    assert len(found) == 1, found
    assert found[0].name.startswith(f"{name}-") and len(found[0].name) == len(name) + 9, found[0].name
    return found[0]


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
    out = only_output(videos, "project")  # 一時ディレクトリも残らない
    assert outputs(out) == ["transcript.md", "video.html"]
    assert f"出力先: {out}（oboro の設定ファイルの kataribe.output_dir）" in result.stderr
    assert not (project / "out").exists()
    assert main(["assets"]) == 0
    note = capsys.readouterr().out.splitlines()[-1]
    assert note == f"出力先の既定: {videos}/<プロジェクトのディレクトリ名>-<パスから作る8文字>（oboro の設定ファイルの kataribe.output_dir）"


def test_名前の同じ別のプロジェクトは_別の出力先になり_互いの成果物を上書きしない(tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    first = make_project(tmp_path / "a" / "demo")
    second = make_project(tmp_path / "b" / "demo", script={**SCRIPT, "title": "二つ目の動画"})

    assert run_build(first).returncode == 0
    assert run_build(second).returncode == 0

    built = sorted(videos.iterdir())
    assert len(built) == 2 and all(path.name.startswith("demo-") for path in built)
    titles = sorted(next(line for line in (path / "transcript.md").read_text(encoding="utf-8").splitlines() if line) for path in built)
    assert titles == ["# テスト動画", "# 二つ目の動画"]


def test_build_のあとの_shoot_も_設定の出力先を読む(project, tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    assert run_build(project).returncode == 0

    result = run_shoot(project)

    assert result.returncode == 0, result.stderr
    assert outputs(only_output(videos, "project") / "frames") == ["s1-end.png", "s2-end.png", "s3-end.png"]


def test_設定の出力先と_OBORO_CONFIG_のチルダは_ホームに展開する(project, tmp_path, monkeypatch):
    home = tmp_path / "home"
    config = home / "custom" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[kataribe]\noutput_dir = "~/videos"\n', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBORO_CONFIG", "~/custom/config.toml")

    result = run_build(project)

    assert result.returncode == 0, result.stderr
    assert outputs(only_output(home / "videos", "project")) == ["transcript.md", "video.html"]


def test_引数の_out_は_設定より優先する(project, tmp_path, monkeypatch):
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{tmp_path / "videos"}"\n')
    out = tmp_path / "成果物"

    result = run_build(project, args=["--out", str(out)])

    assert result.returncode == 0, result.stderr
    assert outputs(out) == ["transcript.md", "video.html"]
    assert not (tmp_path / "videos").exists()


def test_プロジェクトを_ドット_で渡しても_絶対パスと同じ出力先になる(project, tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    env = dict(os.environ, KATARIBE_TTS_CMD=f"{sys.executable} {FAKE_TTS}")
    assert run_build(project).returncode == 0
    out = only_output(videos, "project")
    (out / "video.html").unlink()

    result = subprocess.run([sys.executable, "-m", "kataribe", "build", "."], cwd=project, capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stderr
    assert only_output(videos, "project") == out
    assert (out / "video.html").is_file()


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


def case_insensitive(directory: Path) -> bool:
    return (directory.parent / directory.name.upper()).exists()


def test_綴りの違う2つの表記で同じディレクトリを指すとき_同じ出力先になる(tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    project = make_project(tmp_path / "chromis")
    nfc = make_project(tmp_path / unicodedata.normalize("NFC", "プロジェクト"))
    if not case_insensitive(project):
        pytest.skip("大文字小文字を区別するファイルシステム")

    assert configured_out(tmp_path / "CHROMIS") == configured_out(project)
    assert configured_out(tmp_path / unicodedata.normalize("NFD", nfc.name)) == configured_out(nfc)
    assert configured_out(tmp_path / "CHROMIS").name.startswith("chromis-")


def test_大文字小文字を区別するなら_綴りの違う別のディレクトリは別の出力先になる(tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    lower = make_project(tmp_path / "chromis")
    if case_insensitive(lower):
        pytest.skip("大文字小文字を区別しないファイルシステム")
    upper = make_project(tmp_path / "CHROMIS")

    assert configured_out(lower) != configured_out(upper)


def test_fcntl_を読めない_OS_でも_output_を読み込めて_出力先を決められる(tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\noutput_dir = "{videos}"\n')
    project = make_project(tmp_path / "project")
    code = (
        "import sys; sys.modules['fcntl'] = None  # import fcntl を ImportError にする（Windows と同じ）\n"
        "from pathlib import Path\n"
        "from kataribe.output import configured_out\n"
        f"print(configured_out(Path({str(project)!r})))\n"
    )

    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ))

    assert result.returncode == 0, result.stderr
    out = Path(result.stdout.strip())
    assert out.parent == videos and out.name.startswith("project-")
