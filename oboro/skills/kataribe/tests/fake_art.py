"""テスト用の立ち絵素材。ASCII 名のレイヤーを持つ小さな PSD を zip にし、file:// から取得する定義を書く。"""
import hashlib
import json
import zipfile
from pathlib import Path

PSD_NAME = "fake.psd"
SPEAKERS = {"ずんだもん": "fake-zundamon", "四国めたん": "fake-metan", "春日部つむぎ": "fake-tsumugi", "雨晴はう": "fake-hau", "あんこもん": "fake-ankomon"}
FACES = {
    "normal": {
        "layers": ["!brow/*basic", "!eye/*basic"],
        "mouth": ["!mouth/*closed", "!mouth/*half", "!mouth/*open"],
        "blink": "!eye/*closed",
    },
    "smile": {
        "layers": ["!brow/*up", "!eye/*smile"],
        "mouth": ["!mouth/*grin", "!mouth/*half", "!mouth/*open"],
        "blink": None,
    },
    "angry": {"layers": ["!brow/*down"]},
}
# 素材にあるが、どの表情でも使わないレイヤー
UNUSED = ["!eye/*wink"]


def make_psd(path: Path) -> None:
    from PIL import Image
    from psd_tools import PSDImage
    from psd_tools.api.layers import Group, PixelLayer

    psd = PSDImage.new("RGBA", (40, 60))

    def pixel(name, color, size, left, top):
        return PixelLayer.frompil(Image.new("RGBA", size, color), psd, name, top=top, left=left)

    psd.append(pixel("!body", (200, 200, 200, 255), (40, 60), 0, 0))
    groups = {
        "!brow": ["*basic", "*up", "*down"],
        "!eye": ["*basic", "*smile", "*closed", "*wink"],
        "!mouth": ["*closed", "*half", "*open", "*grin"],
    }
    for group_name, names in groups.items():
        group = Group.new(psd, group_name, open_folder=True)
        for i, name in enumerate(names):
            group.append(pixel(name, (40 * i, 100, 200, 255), (10, 4), 5 + i, 10 + 2 * i))
        psd.append(group)
    psd.save(path)


def make_zip(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    psd = directory / PSD_NAME
    make_psd(psd)
    archive = directory / "fake-art.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(psd, f"素材/{PSD_NAME}")
    psd.unlink()
    return archive


def md5_of(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def write_definitions(directory: Path, archive: Path, **overrides) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for speaker, char_id in SPEAKERS.items():
        definition = {
            "id": char_id,
            "speaker": speaker,
            "side": "right" if speaker == "ずんだもん" else "left",
            "facing": "left",
            "source": {"url": archive.as_uri(), "md5": md5_of(archive), "psd": PSD_NAME},
            "scale": 0.5,
            "base": ["!body"],
            "faces": FACES,
        }
        for key, value in overrides.items():
            if key in definition["source"]:
                definition["source"][key] = value
            else:
                definition[key] = value
        (directory / f"{char_id}.json").write_text(json.dumps(definition, ensure_ascii=False), encoding="utf-8")
    return directory


def fake_art_env(root: Path, **overrides) -> dict[str, str]:
    """素材の zip、定義、キャッシュを root の下に作り、build に渡す環境変数を返す。"""
    archive = make_zip(root / "source")
    definitions = write_definitions(root / "definitions", archive, **overrides)
    return {"KATARIBE_CHAR_DEFS": str(definitions), "KATARIBE_CHAR_CACHE": str(root / "cache"), "KATARIBE_CHAR_SOURCES": str(root / "assets")}
