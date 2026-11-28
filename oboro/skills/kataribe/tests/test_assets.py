"""立ち絵素材の状態（kataribe assets）と置き場所。ネットワークを使わない（素材は tests/fake_art.py）。"""

import json
import os
import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import SCRIPT, make_project, run_build, run_lint
from fake_art import PSD_NAME, make_zip, md5_of

from kataribe import art
from kataribe.cli import main

ZIP_NAME = "素材.zip"
PAGE = "https://example.com/art"


def definition(archive: Path, *, url: str | None = None, md5: str | None = None, speaker: str = "ずんだもん") -> dict:
    source: dict = {"file": ZIP_NAME, "md5": md5 or md5_of(archive), "psd": PSD_NAME}
    source.update({"url": url} if url else {"page": PAGE})
    return {
        "id": "fake",
        "speaker": speaker,
        "side": "right",
        "facing": "left",
        "source": source,
        "scale": 0.5,
        "base": ["!body"],
        "faces": {"normal": {"layers": ["!brow/*basic", "!eye/*basic"], "mouth": ["!mouth/*closed", "!mouth/*half", "!mouth/*open"], "blink": "!eye/*closed"}},
    }


@pytest.fixture(scope="module")
def archive(tmp_path_factory) -> Path:
    return make_zip(tmp_path_factory.mktemp("zip"))


@pytest.fixture
def places(tmp_path, monkeypatch) -> tuple[Path, Path]:
    cache, assets = tmp_path / "cache", tmp_path / "assets"
    monkeypatch.setenv("KATARIBE_CHAR_CACHE", str(cache))
    monkeypatch.setenv("KATARIBE_CHAR_SOURCES", str(assets))
    return cache, assets


def write_definitions(tmp_path: Path, monkeypatch, *definitions: dict) -> None:
    directory = tmp_path / "definitions"
    directory.mkdir()
    for index, item in enumerate(definitions):
        (directory / f"{index}.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("KATARIBE_CHAR_DEFS", str(directory))


def write_manifest(cache: Path, item: dict, **changes) -> None:
    source = item["source"]
    (cache / item["id"]).mkdir(parents=True)
    manifest = {"md5": source["md5"], "psd": source["psd"], "scale": item["scale"], "layers": [], **changes}
    (cache / item["id"] / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


# ---------- 4つの状態 ----------


def test_manifest_が定義と一致すれば_キャッシュ済み(archive, places):
    item = definition(archive)
    write_manifest(places[0], item)

    assert art.asset_state(item) == art.ASSET_CACHED


def test_manifest_が定義と違えば_キャッシュ済みにしない(archive, places):
    item = definition(archive)
    write_manifest(places[0], item, scale=0.25)

    assert art.asset_state(item) == art.ASSET_MISSING


def test_壊れた_manifest_はキャッシュ済みにしない(archive, places):
    item = definition(archive)
    (places[0] / item["id"]).mkdir(parents=True)
    (places[0] / item["id"] / "manifest.json").write_text("{", encoding="utf-8")

    assert art.asset_state(item) == art.ASSET_MISSING


def test_置き場所に_MD5_の一致する_zip_があれば_zip_あり(archive, places):
    places[1].mkdir()
    shutil.copyfile(archive, places[1] / ZIP_NAME)

    assert art.asset_state(definition(archive)) == art.ASSET_ZIP


def test_url_があれば_自動取得可(archive, places):
    assert art.asset_state(definition(archive, url=archive.as_uri())) == art.ASSET_AUTO


def test_url_も_zip_もなければ_素材なし(archive, places):
    assert art.asset_state(definition(archive)) == art.ASSET_MISSING


def test_MD5_の違う_zip_は_zip_ありにしない(archive, places):
    places[1].mkdir()
    (places[1] / ZIP_NAME).write_bytes(b"other")

    assert art.asset_state(definition(archive)) == art.ASSET_MISSING
    assert art.asset_state(definition(archive, url=archive.as_uri())) == art.ASSET_AUTO


def test_状態は_キャッシュ_zip_自動取得の優先順で決まる(archive, places):
    item = definition(archive, url=archive.as_uri())
    assert art.asset_state(item) == art.ASSET_AUTO
    places[1].mkdir()
    shutil.copyfile(archive, places[1] / ZIP_NAME)
    assert art.asset_state(item) == art.ASSET_ZIP
    write_manifest(places[0], item)
    assert art.asset_state(item) == art.ASSET_CACHED


# ---------- assets コマンド ----------


def test_assets_は話者ごとに1行を出し_素材なしは手順を示して終了コード0(archive, places, tmp_path, monkeypatch, capsys):
    write_definitions(
        tmp_path,
        monkeypatch,
        definition(archive, speaker="ずんだもん"),
        definition(archive, speaker="四国めたん", url=archive.as_uri()),
    )

    code = main(["assets"])

    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert len(out) == 2
    assert out[1] == "四国めたん: 自動取得可"
    assert out[0].startswith("ずんだもん: 素材なし（警告: ")
    assert PAGE in out[0] and ZIP_NAME in out[0] and str(places[1]) in out[0]


def test_assets_はネットワーク接続_zip_の展開_キャッシュへの書き込みをしない(archive, places, tmp_path, monkeypatch, capsys):
    write_definitions(
        tmp_path,
        monkeypatch,
        definition(archive, speaker="ずんだもん"),
        definition(archive, speaker="四国めたん", url="https://example.invalid/art.zip"),
    )
    places[1].mkdir()
    shutil.copyfile(archive, places[1] / ZIP_NAME)

    def forbidden(*args, **kwargs):
        raise AssertionError("assets が禁止された処理を呼びました")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)

    assert main(["assets"]) == 0
    assert capsys.readouterr().out.splitlines() == ["ずんだもん: zip あり", "四国めたん: zip あり"]
    assert not places[0].exists()
    assert [path.name for path in places[1].iterdir()] == [ZIP_NAME]


def test_実際の定義でも5人の状態を出す(places, monkeypatch, capsys):
    monkeypatch.delenv("KATARIBE_CHAR_DEFS", raising=False)

    assert main(["assets"]) == 0

    out = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in out] == ["あんこもん", "雨晴はう", "四国めたん", "春日部つむぎ", "ずんだもん"]
    assert sum(": 自動取得可" in line for line in out) == 2
    assert sum(": 素材なし" in line for line in out) == 3


# ---------- 置き場所の決め方（環境変数、oboro の設定ファイル、既定の順） ----------


def write_oboro_config(tmp_path: Path, monkeypatch, text: str) -> Path:
    config = tmp_path / "oboro" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(text, encoding="utf-8")
    monkeypatch.setenv("OBORO_CONFIG", str(config))
    return config


def test_環境変数がなければ_oboro_の設定ファイルの_kataribe_char_sources_の_zip_を使う(archive, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KATARIBE_CHAR_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("KATARIBE_CHAR_SOURCES", raising=False)
    write_definitions(tmp_path, monkeypatch, definition(archive))
    zips = tmp_path / "zips"
    zips.mkdir()
    shutil.copyfile(archive, zips / ZIP_NAME)
    write_oboro_config(tmp_path, monkeypatch, f'[org]\ndir = "~/org"\n\n[kataribe]\nchar_sources = "{zips}"\n')

    assert main(["assets"]) == 0
    assert capsys.readouterr().out.splitlines() == ["ずんだもん: zip あり"]


def test_設定ファイルの置き場所の_チルダは_ホームに展開する(tmp_path, monkeypatch):
    monkeypatch.delenv("KATARIBE_CHAR_SOURCES", raising=False)
    write_oboro_config(tmp_path, monkeypatch, '[kataribe]\nchar_sources = "~/kataribe-zips"\n')

    assert art.sources_root() == Path.home() / "kataribe-zips"


def test_OBORO_CONFIG_のチルダも_ホームに展開して_その設定ファイルを読む(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KATARIBE_CHAR_SOURCES", raising=False)
    config = home / "custom" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[kataribe]\nchar_sources = "~/zips"\n', encoding="utf-8")
    monkeypatch.setenv("OBORO_CONFIG", "~/custom/config.toml")

    assert art.sources_root() == home / "zips"


def test_環境変数_KATARIBE_CHAR_SOURCES_は_設定ファイルより優先する(places, tmp_path, monkeypatch):
    write_oboro_config(tmp_path, monkeypatch, f'[kataribe]\nchar_sources = "{tmp_path / "from-config"}"\n')

    assert art.sources_root() == places[1]


@pytest.mark.parametrize("text", [None, '[org]\ndir = "~/org"\n'], ids=["設定ファイルなし", "kataribe_の表なし"])
def test_設定ファイルに_kataribe_char_sources_がなければ_既定の置き場所(text, tmp_path, monkeypatch):
    monkeypatch.delenv("KATARIBE_CHAR_SOURCES", raising=False)
    if text is not None:
        write_oboro_config(tmp_path, monkeypatch, text)

    assert art.sources_root() == Path.home() / "Documents" / "kataribe-assets"


@pytest.mark.parametrize(
    "text",
    ["[kataribe\n", "[kataribe]\nchar_sources = 1\n", '[kataribe]\nchar_sources = ""\n', 'kataribe = "zips"\n'],
    ids=["TOML_でない", "文字列でない", "空", "表でない"],
)
def test_設定ファイルが読めないか値の形が違えば_設定ファイルを示して失敗する(text, archive, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KATARIBE_CHAR_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("KATARIBE_CHAR_SOURCES", raising=False)
    write_definitions(tmp_path, monkeypatch, definition(archive))
    config = write_oboro_config(tmp_path, monkeypatch, text)

    assert main(["assets"]) == 1
    err = capsys.readouterr().err
    assert str(config) in err
    assert "Traceback" not in err


# ---------- 置き場所の zip の使い方 ----------


def zundamon_env(tmp_path: Path, item: dict) -> dict[str, str]:
    directory = tmp_path / "definitions"
    directory.mkdir()
    (directory / "fake.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    return {
        "KATARIBE_CHAR_DEFS": str(directory),
        "KATARIBE_CHAR_CACHE": str(tmp_path / "cache"),
        "KATARIBE_CHAR_SOURCES": str(tmp_path / "assets"),
    }


def test_自動取得した_zip_は_キャッシュと置き場所の両方に残る(archive, tmp_path):
    project = make_project(tmp_path / "p")

    result = run_build(project, extra_env=zundamon_env(tmp_path, definition(archive, url=archive.as_uri())))

    assert result.returncode == 0, result.stderr
    assert md5_of(tmp_path / "assets" / ZIP_NAME) == md5_of(archive)
    assert md5_of(tmp_path / "cache" / "fake" / "source.zip") == md5_of(archive)


def test_置き場所に_zip_があれば_自動取得の話者もネットワークに接続しない(archive, tmp_path):
    (tmp_path / "assets").mkdir()
    shutil.copyfile(archive, tmp_path / "assets" / ZIP_NAME)
    project = make_project(tmp_path / "p")

    # 接続先は存在しないので、取得しに行けば失敗する
    result = run_build(project, extra_env=zundamon_env(tmp_path, definition(archive, url="file:///nonexistent/art.zip")))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "cache" / "fake" / "manifest.json").is_file()


def test_置き場所の_MD5_の違うファイルは_自動取得しても上書きしない(archive, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / ZIP_NAME).write_bytes(b"other")
    project = make_project(tmp_path / "p")

    result = run_build(project, extra_env=zundamon_env(tmp_path, definition(archive, url=archive.as_uri())))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "assets" / ZIP_NAME).read_bytes() == b"other"
    assert "上書きせず" in result.stderr


def test_置き場所に書き込めなくても_キャッシュがあるので_build_は成功する(archive, tmp_path):
    (tmp_path / "blocked").write_text("ディレクトリを作れない場所", encoding="utf-8")
    env = {**zundamon_env(tmp_path, definition(archive, url=archive.as_uri())), "KATARIBE_CHAR_SOURCES": str(tmp_path / "blocked" / "assets")}
    project = make_project(tmp_path / "p")

    result = run_build(project, extra_env=env)

    assert result.returncode == 0, result.stderr
    assert "保存できません" in result.stderr


def test_実際の定義の_url_を持つ話者には_file_があり_素材を同梱しない():
    directory = Path(art.__file__).parent / "characters"
    sources = [json.loads(path.read_text(encoding="utf-8"))["source"] for path in sorted(directory.glob("*.json"))]

    assert len(sources) == 5
    assert all(source.get("file", "").endswith(".zip") for source in sources)
    assert not [path for path in directory.rglob("*") if path.suffix.lower() in {".zip", ".psd", ".png"}]


# ---------- lint ----------


def lint_env(monkeypatch, env: dict[str, str]) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_lint_は使う話者が素材なしのとき_手順つきで警告し_失敗にしない(archive, tmp_path, monkeypatch):
    project = make_project(tmp_path / "p")
    lint_env(monkeypatch, zundamon_env(tmp_path, definition(archive)))

    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert "ずんだもん" in result.stderr and PAGE in result.stderr and ZIP_NAME in result.stderr
    assert str(tmp_path / "assets") in result.stderr
    assert "lint: 成功（警告 1 件）" in result.stdout


def test_lint_は台本で使わない話者の素材なしを警告しない(archive, tmp_path, monkeypatch):
    project = make_project(tmp_path / "p")
    directory = tmp_path / "definitions"
    directory.mkdir()
    for name, item in {"a": definition(archive, url=archive.as_uri()), "b": definition(archive, speaker="四国めたん")}.items():
        (directory / f"{name}.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    env = {"KATARIBE_CHAR_DEFS": str(directory), "KATARIBE_CHAR_CACHE": str(tmp_path / "c"), "KATARIBE_CHAR_SOURCES": str(tmp_path / "s")}
    lint_env(monkeypatch, env)

    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "lint: 成功（警告 0 件）" in result.stdout


def test_lint_slides_も素材なしを警告する(archive, tmp_path):
    script = {"title": "t", "chapters": [{"id": "c", "title": "章", "scenes": [{"id": "s", "lines": [{"speaker": "ずんだもん", "text": "こんにちは"}]}]}]}
    project = make_project(tmp_path / "p", script=script, scenes='<section data-scene="s"></section>')
    env = {**os.environ, **zundamon_env(tmp_path, definition(archive))}

    result = subprocess.run([sys.executable, "-m", "kataribe", "lint", "--slides", str(project)], capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stderr
    assert PAGE in result.stderr


def test_素材なしの話者の_build_は_新しい置き場所を示して失敗する(archive, tmp_path):
    project = make_project(tmp_path / "p", script=SCRIPT)

    result = run_build(project, extra_env=zundamon_env(tmp_path, definition(archive)))

    assert result.returncode == 1
    assert str(tmp_path / "assets") in result.stderr
