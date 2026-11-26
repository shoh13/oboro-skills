import json
import re
import subprocess
from pathlib import Path

import pytest
from conftest import SCRIPT, make_project, run_build, run_lint
from fake_art import UNUSED, fake_art_env

STALE = "前回の out/ は古いままです"
REPO = Path(__file__).resolve().parents[1]
FACES = ["normal", "smile", "surprised", "troubled", "jito", "panic", "think", "angry", "cry"]


def smile_script():
    script = json.loads(json.dumps(SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][1]["expression"] = "smile"
    return script


def cast_of(project):
    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    found = re.search(r'<script type="application/json" id="kataribe-cast">(.*?)</script>', html, re.S)
    assert found, "video.html に立ち絵のデータがない"
    return json.loads(found.group(1))


def test_初回のbuildで素材を取得して_使う表情のレイヤーだけを埋め込み_2回目はキャッシュを使う(tmp_path):
    env = fake_art_env(tmp_path / "art")
    project = make_project(tmp_path / "p", script=smile_script())

    first = run_build(project, extra_env=env)

    assert first.returncode == 0, first.stderr
    [zundamon] = cast_of(project)
    assert zundamon["speaker"] == "ずんだもん"
    assert zundamon["side"] == "right"
    assert sorted(zundamon["faces"]) == ["normal", "smile"]
    assert zundamon["faces"]["smile"]["layers"] == ["!brow/*up", "!eye/*smile"]
    assert zundamon["faces"]["smile"]["mouth"] == ["!mouth/*grin", "!mouth/*half", "!mouth/*open"]
    used = set(zundamon["layers"])
    assert {"!body", "!brow/*basic", "!eye/*basic", "!brow/*up", "!eye/*smile", "!mouth/*grin"} <= used
    assert "!brow/*down" not in used  # angry は台本で使っていない
    assert "!eye/*closed" in used  # normal の閉じ目（まばたき）
    assert zundamon["faces"]["normal"]["blink"] == "!eye/*closed"
    assert zundamon["faces"]["smile"]["blink"] is None  # smile は閉じ目がないので、まばたきしない
    assert not used & set(UNUSED)
    body = zundamon["layers"]["!body"]
    assert (body["w"], body["h"]) == (20, 30)  # 40x60 を scale 0.5 で縮小
    assert body["src"].startswith("data:image/png;base64,")

    (tmp_path / "art" / "source" / "fake-art.zip").unlink()
    second = run_build(project, extra_env=env)

    assert second.returncode == 0, second.stderr
    assert cast_of(project) == [zundamon]


def test_表情の一部だけを持つ表情は_残りをnormalから引き継ぐ(tmp_path):
    env = fake_art_env(tmp_path / "art")
    script = json.loads(json.dumps(SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][0]["expression"] = "angry"
    project = make_project(tmp_path / "p", script=script)

    assert run_build(project, extra_env=env).returncode == 0

    [zundamon] = cast_of(project)
    assert zundamon["faces"]["angry"]["layers"] == ["!brow/*down", "!eye/*basic"]
    assert zundamon["faces"]["angry"]["mouth"] == ["!mouth/*closed", "!mouth/*half", "!mouth/*open"]


def test_掛け合いでは_使った話者ごとに_台本に出た順で立ち絵のデータを持つ(tmp_path):
    env = fake_art_env(tmp_path / "art")
    script = json.loads(json.dumps(SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][0]["speaker"] = "四国めたん"
    project = make_project(tmp_path / "p", script=script)

    assert run_build(project, extra_env=env).returncode == 0

    assert [c["speaker"] for c in cast_of(project)] == ["四国めたん", "ずんだもん"]


@pytest.mark.parametrize(
    "name, overrides, keyword",
    [
        ("MD5 が違う", {"md5": "0" * 32}, "MD5"),
        ("zip に PSD がない", {"psd": "missing.psd"}, "missing.psd"),
        ("取得元がない", {"url": "file:///nonexistent/kataribe-art.zip"}, "取得"),
    ],
    ids=["md5", "psd", "source"],
)
def test_素材の取得_検証_合成に失敗したら_buildは失敗し_前回のoutを残す(tmp_path, name, overrides, keyword):
    project = make_project(tmp_path / "p")
    assert run_build(project, extra_env=fake_art_env(tmp_path / "good")).returncode == 0
    before = (project / "out" / "video.html").read_bytes()
    broken = fake_art_env(tmp_path / "broken", **overrides)

    result = run_build(project, extra_env=broken)

    assert result.returncode == 1
    assert keyword in result.stderr
    assert STALE in result.stderr
    assert "Traceback" not in result.stderr
    assert (project / "out" / "video.html").read_bytes() == before
    assert not list(Path(broken["KATARIBE_CHAR_CACHE"]).rglob("manifest.json"))  # 壊れたキャッシュを残さない


def test_初回のbuildで素材の取得に失敗したら_outを作らない(tmp_path):
    project = make_project(tmp_path / "p")

    result = run_build(project, extra_env=fake_art_env(tmp_path / "art", md5="0" * 32))

    assert result.returncode == 1
    assert not (project / "out").exists()


def test_定義にない表情の名前は_buildが場所を示して失敗する(tmp_path):
    script = json.loads(json.dumps(SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][1]["expression"] = "sleepy"
    project = make_project(tmp_path / "p", script=script)

    result = run_build(project, extra_env=fake_art_env(tmp_path / "art"))

    assert result.returncode == 1
    assert "sleepy" in result.stderr
    assert "chapters[0].scenes[0].lines[1].expression" in result.stderr


def test_lintは素材を取得しない(tmp_path, monkeypatch):
    env = fake_art_env(tmp_path / "art", url="file:///nonexistent/kataribe-art.zip")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    project = make_project(tmp_path / "p")

    result = run_lint(project)

    assert result.returncode == 0, result.stderr
    assert not Path(env["KATARIBE_CHAR_CACHE"]).exists()


def test_グループの不透明度は_書き出すレイヤーの透明度に掛けられる(tmp_path):
    from PIL import Image
    from psd_tools import PSDImage
    from psd_tools.api.layers import Group, PixelLayer

    from kataribe.art import _export_layers

    psd = PSDImage.new("RGBA", (8, 8))
    group = Group.new(psd, "!mark", open_folder=True)
    group.append(PixelLayer.frompil(Image.new("RGBA", (8, 8), (255, 0, 0, 255)), psd, "sweat"))
    group.opacity = 128
    psd.append(group)
    psd.save(tmp_path / "a.psd")

    [layer] = _export_layers(tmp_path / "a.psd", 1.0, tmp_path / "out")

    assert layer["path"] == "!mark/sweat"
    alpha = Image.open(tmp_path / "out" / layer["file"]).getchannel("A").getextrema()
    assert alpha == (128, 128)


def test_キャッシュの既定の場所は_リポジトリの外のユーザーのキャッシュ(monkeypatch):
    from kataribe.art import cache_root

    monkeypatch.delenv("KATARIBE_CHAR_CACHE", raising=False)

    assert cache_root() == Path.home() / ".cache" / "kataribe" / "characters"
    assert REPO not in cache_root().parents


@pytest.mark.parametrize("skill", ["kataribe", "kataribe-slides"])
def test_素材と画像はgitで追跡されず_定義はJSONだけ(skill):
    # 動画とスライドは同じ実行コードを別々に同梱するので、両方のディレクトリを確かめる。
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO.parent / skill, capture_output=True, text=True, check=True).stdout.split()

    assert not [f for f in tracked if f.endswith((".psd", ".zip"))]
    assert sorted(f for f in tracked if f.startswith("src/kataribe/characters/")) == [
        "src/kataribe/characters/ankomon.json",
        "src/kataribe/characters/hau.json",
        "src/kataribe/characters/metan.json",
        "src/kataribe/characters/tsumugi.json",
        "src/kataribe/characters/zundamon.json",
    ]


def test_同梱の定義は_5人の話者に9つの表情と3段階の口を持つ(monkeypatch):
    from kataribe.art import load_definitions

    monkeypatch.delenv("KATARIBE_CHAR_DEFS", raising=False)

    definitions = load_definitions()

    assert sorted(definitions) == sorted(["ずんだもん", "四国めたん", "春日部つむぎ", "雨晴はう", "あんこもん"])
    assert definitions["四国めたん"]["side"] == "left"
    assert definitions["ずんだもん"]["side"] == "right"
    for definition in definitions.values():
        assert list(definition["faces"]) == FACES
        assert len(definition["faces"]["normal"]["mouth"]) == 3
        source = definition["source"]
        # 自動で取得できる素材は url、手元に落とす素材は配布元のページと zip の名前を持つ
        assert source["url"].startswith("https://") if "url" in source else source["page"].startswith("https://") and source["file"].endswith(".zip")
        assert len(source["md5"]) == 32


def manual_definition(tmp_path, file="fake-art.zip"):
    """url を持たず、手元に落とした zip を使う定義と、その zip を置く場所を作る。"""
    from fake_art import FACES as FAKE_FACES
    from fake_art import PSD_NAME, make_zip, md5_of

    archive = make_zip(tmp_path / "downloads")
    definitions = tmp_path / "definitions"
    definitions.mkdir()
    definition = {
        "id": "fake-manual",
        "speaker": "ずんだもん",
        "side": "right",
        "facing": "left",
        "source": {"page": "https://example.com/art", "file": file, "md5": md5_of(archive), "psd": PSD_NAME},
        "scale": 0.5,
        "base": ["!body"],
        "faces": FAKE_FACES,
    }
    (definitions / "fake-manual.json").write_text(json.dumps(definition, ensure_ascii=False), encoding="utf-8")
    return {
        "KATARIBE_CHAR_DEFS": str(definitions),
        "KATARIBE_CHAR_CACHE": str(tmp_path / "cache"),
        "KATARIBE_CHAR_SOURCES": str(tmp_path / "downloads"),
    }


def test_url_のない素材は_手元に落とした_zip_を_MD5_で確かめて使う(tmp_path):
    project = make_project(tmp_path / "p")

    result = run_build(project, extra_env=manual_definition(tmp_path))

    assert result.returncode == 0, result.stderr
    [zundamon] = cast_of(project)
    assert "!body" in zundamon["layers"]


def test_手元に_zip_がなければ_配布元と置き場所を示して失敗する(tmp_path):
    project = make_project(tmp_path / "p")

    result = run_build(project, extra_env=manual_definition(tmp_path, file="missing.zip"))

    assert result.returncode == 1
    assert "https://example.com/art" in result.stderr
    assert "missing.zip" in result.stderr
    assert str(tmp_path / "downloads") in result.stderr
    assert "Traceback" not in result.stderr


def test_素材の既定の置き場所は_ドキュメントの_kataribe_assets(monkeypatch):
    from kataribe.art import sources_root

    monkeypatch.delenv("KATARIBE_CHAR_SOURCES", raising=False)

    assert sources_root() == Path.home() / "Documents" / "kataribe-assets"


def test_choices_のグループは_星印がなくても_表情のレイヤーがnormalの同じグループのレイヤーを隠す():
    from kataribe.art import _resolve_face

    definition = {
        "choices": ["face/eye"],
        "faces": {
            "normal": {"layers": ["face/eye/open", "face/brow/flat"], "mouth": ["m0", "m1", "m2"]},
            "smile": {"layers": ["face/eye/happy", "face/cheek"]},
        },
    }

    assert _resolve_face(definition, "smile")["layers"] == ["face/eye/happy", "face/cheek", "face/brow/flat"]
    # choices でないグループは隠さない（face/cheek は face/brow を隠さない）
    del definition["choices"]
    assert _resolve_face(definition, "smile")["layers"] == ["face/eye/happy", "face/cheek", "face/eye/open", "face/brow/flat"]
