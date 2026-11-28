"""立ち絵（仕様 R16）。

定義を読み、素材を取得・検証してリポジトリの外にキャッシュし、台本で使う表情のレイヤーを
単一HTMLに埋め込むデータ（cast）にする。重ねて表示するのはプレーヤー（T22）。
素材と書き出した画像は、作者が再配布を許していないので、git にも共有用の zip にも入れない。

定義の形と、レイヤーの選び方の規則（PSDTool の「!」「*」）は、yes（yuya-takeyama/agent-plugins、MIT）の
characters/*.json に合わせている。
"""

import base64
import contextlib
import hashlib
import html
import http.cookiejar
import json
import math
import os
import re
import shutil
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from kataribe.definitions import load_definitions
from kataribe.project import Project

DEFAULT_FACE = "normal"
MOUTH_STEPS = 3


class ArtError(Exception):
    pass


def cache_root() -> Path:
    configured = os.environ.get("KATARIBE_CHAR_CACHE")
    return Path(configured) if configured else Path.home() / ".cache" / "kataribe" / "characters"


def sources_root() -> Path:
    """素材の zip の置き場所。使う人が落とした zip をここで探し、自動で取得した zip もここに残す。

    環境変数 KATARIBE_CHAR_SOURCES、oboro の設定ファイルの kataribe.char_sources、既定の ~/Documents/kataribe-assets の順に決める。
    """
    configured = os.environ.get("KATARIBE_CHAR_SOURCES")
    if configured:
        return Path(configured)
    return _oboro_char_sources() or Path.home() / "Documents" / "kataribe-assets"


def _oboro_char_sources() -> Path | None:
    """oboro の設定ファイル（setup-oboro が書く。OBORO_CONFIG があればそのパス）の kataribe.char_sources。"""
    config = Path(os.environ.get("OBORO_CONFIG") or Path.home() / ".config" / "oboro" / "config.toml")
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ArtError(f"oboro の設定ファイルを読めません: {config}（{e}）") from None
    section = data.get("kataribe", {})
    if not isinstance(section, dict):
        raise ArtError(f"oboro の設定ファイルの kataribe は、表（[kataribe]）にしてください: {config}")
    value = section.get("char_sources")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ArtError(f"oboro の設定ファイルの kataribe.char_sources は、空でないパスの文字列にしてください: {config}")
    return Path(value).expanduser()


# ---------- 取得・検証 ----------


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_getuploader(url: str, password: str, dest: Path) -> None:
    """getuploader は、Cookie を受け取り、パスワードとトークンを順に POST して初めてファイルの URL を返す。"""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders = [("User-Agent", "kataribe")]

    def post(fields: dict[str, str]) -> str:
        request = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers={"Referer": url})
        with opener.open(request, timeout=60) as response:
            return response.read().decode("utf-8", "replace")

    with opener.open(url, timeout=60) as response:
        response.read()
    page = post({"password": password, "yes": "認証"})
    token = re.search(r'name="token"\s+value="([^"]+)"', page)
    if not token:
        raise ArtError(f"立ち絵素材を取得できません（パスワードが通りません）: {url}")
    page = post({"token": token.group(1), "yes": "ダウンロード"})
    link = re.search(r'https://downloadx\.getuploader\.com/[^"\'<\s]+', page)
    if not link:
        raise ArtError(f"立ち絵素材を取得できません（ダウンロード先が見つかりません）: {url}")
    request = urllib.request.Request(html.unescape(link.group(0)), headers={"Referer": url})
    with opener.open(request, timeout=600) as response, dest.open("wb") as f:
        shutil.copyfileobj(response, f)


def _download(source: dict, dest: Path) -> None:
    if "url" not in source:
        # 配布元がログインやパスワードを求めるので、使う人が落とした zip を使う（MD5 は呼び出し元で確かめる）
        local = sources_root() / source["file"]
        if not local.is_file():
            raise ArtError(f"立ち絵素材を自動では取得できません。{_how_to_get(source)}（置き場所は KATARIBE_CHAR_SOURCES か、oboro の設定ファイルの kataribe.char_sources で変えられます）")
        try:
            shutil.copyfile(local, dest)
        except OSError as e:
            raise ArtError(f"立ち絵素材を読めません: {local}（{e}）") from None
        return
    url = source["url"]
    try:
        if url.startswith("file://"):
            shutil.copyfile(urllib.request.url2pathname(urllib.parse.urlsplit(url).path), dest)
        else:
            _download_getuploader(url, source.get("password", ""), dest)
    except (OSError, urllib.error.URLError) as e:
        raise ArtError(f"立ち絵素材を取得できません: {url}（{e}）") from None


def _how_to_get(source: dict) -> str:
    return f"{source['page']} から「{source['file']}」を落として、{sources_root()} に置いてください"


def _local_zip(source: dict) -> Path | None:
    """素材の置き場所にある、定義の file の名前で MD5 が一致する zip。"""
    if "file" not in source:
        return None
    path = sources_root() / source["file"]
    try:
        return path if path.is_file() and _md5(path) == source["md5"] else None
    except OSError:
        return None


def _keep_in_sources(source: dict, archive: Path) -> None:
    """自動で取得した zip を素材の置き場所にも残す。残せなくても、キャッシュがあるので build は止めない。"""
    if "file" not in source:
        return
    dest = sources_root() / source["file"]
    if dest.exists():  # MD5 が一致すれば取得していない。一致しないファイルは、使う人のものなので上書きしない
        print(f"警告: {dest} は MD5 が定義と一致しないので、上書きせず残します", file=sys.stderr)
        return
    temporary = dest.with_name(f".{dest.name}.tmp")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, temporary)
        os.replace(temporary, dest)
    except OSError as e:
        print(f"警告: 取得した立ち絵素材を {dest} に保存できません（{e}）", file=sys.stderr)
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)


def _obtain(definition: dict, work: Path) -> Path:
    """MD5 の一致する zip を返す。素材の置き場所にあれば、自動で取得できる話者でもネットワークに接続しない。"""
    source = definition["source"]
    local = _local_zip(source)
    if local is not None:
        return local
    archive = work / "source.zip"
    _download(source, archive)
    got = _md5(archive)
    if got != source["md5"]:
        raise ArtError(f"立ち絵素材の MD5 が一致しません（{definition['id']}）: {got}、期待は {source['md5']}")
    if "url" in source:
        _keep_in_sources(source, archive)
    return archive


def _member_name(info: zipfile.ZipInfo) -> str:
    # 配布元の zip は CP932 の名前を UTF-8 の印なしで持ち、zipfile は CP437 として読む
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp932")
    except UnicodeError:
        return info.filename


def _extract_psd(archive: Path, psd_name: str, dest: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if Path(_member_name(info)).name == psd_name:
                    with z.open(info) as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
                    return
    except zipfile.BadZipFile as e:
        raise ArtError(f"立ち絵素材の zip を開けません: {e}") from None
    raise ArtError(f"立ち絵素材の zip に {psd_name} がありません")


# ---------- 書き出し（縮小） ----------


def _blend(mode) -> str:
    name = str(getattr(mode, "name", mode)).lower()
    return "normal" if name in ("normal", "pass_through") else name.replace("_", "-")


def _export_layers(psd_path: Path, scale: float, out: Path) -> list[dict]:
    """PSD の全レイヤーを、縮小した PNG にして out/layers に書く。

    レイヤーごとに位置を丸めると、目や口が顔に対して最大1画素ずれる。縮小後の画素の格子を元画像の
    座標に戻して、その範囲を切り出して縮小することで、すべてのレイヤーの位置を揃える。
    """
    from PIL import Image
    from psd_tools import PSDImage

    psd = PSDImage.open(psd_path)
    (out / "layers").mkdir(parents=True)
    pad = math.ceil(1 / scale) + 2
    layers, seen = [], set()
    for layer in psd.descendants():  # 下から上の順（重ねる順）
        if layer.is_group():
            continue
        names: list[str] = []
        node: Any = layer  # 親のグループへたどる（psd-tools の型では親がグループの型にならない）
        opacity = 1.0
        while node is not None and node is not psd:
            names.append(node.name)
            opacity *= node.opacity / 255
            node = node.parent
        path = "/".join(reversed(names))
        if path in seen:
            raise ArtError(f"立ち絵素材に同じ名前のレイヤーが2つあります: {path}")
        seen.add(path)
        left, top, right, bottom = layer.bbox
        image = layer.topil()
        if image is None or right <= left or bottom <= top:
            continue
        x0, y0 = math.floor(left * scale), math.floor(top * scale)
        x1, y1 = math.ceil(right * scale), math.ceil(bottom * scale)
        padded = Image.new("RGBA", (image.width + 2 * pad, image.height + 2 * pad))
        padded.paste(image.convert("RGBA"), (pad, pad))
        box = (x0 / scale - left + pad, y0 / scale - top + pad, x1 / scale - left + pad, y1 / scale - top + pad)
        small = padded.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS, box=box)
        if opacity < 1:
            small.putalpha(small.getchannel("A").point([round(a * opacity) for a in range(256)]))
        file = f"layers/{len(layers):04d}.png"
        small.save(out / file, optimize=True)
        layers.append({"path": path, "file": file, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "blend": _blend(layer.blend_mode)})
    return layers


def _manifest_key(definition: dict) -> dict:
    source = definition["source"]
    return {"md5": source["md5"], "psd": source["psd"], "scale": definition["scale"]}


def _cached_manifest(definition: dict) -> dict | None:
    """キャッシュの manifest が定義と一致すれば返す。読めない・壊れている・定義と違うなら None。"""
    try:
        manifest = json.loads((cache_root() / definition["id"] / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    key = _manifest_key(definition)
    return manifest if {k: manifest.get(k) for k in key} == key else None


def _prepare(definition: dict) -> tuple[Path, dict]:
    """キャッシュに、この定義の素材の書き出しがあることを保証する。途中で失敗したら、キャッシュを変えない。"""
    source = definition["source"]
    key = _manifest_key(definition)
    directory = cache_root() / definition["id"]
    manifest = _cached_manifest(definition)
    if manifest is not None:
        return directory, manifest
    cache_root().mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{definition['id']}-", dir=cache_root()))
    try:
        archive = directory / "source.zip"
        if not (archive.exists() and _md5(archive) == source["md5"]):
            archive = _obtain(definition, work)
        psd = work / "source.psd"
        _extract_psd(archive, source["psd"], psd)
        staged = work / "staged"
        try:
            layers = _export_layers(psd, definition["scale"], staged)
        except ArtError:
            raise
        except Exception as e:  # psd-tools と Pillow の読み込み・書き出しの失敗
            raise ArtError(f"立ち絵素材のレイヤーを書き出せません（{definition['id']}）: {e}") from None
        shutil.copyfile(archive, staged / "source.zip")  # 書き出しの規則が変わったとき、取得し直さずに済む
        manifest = {**key, "layers": layers}
        (staged / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        if directory.exists():
            shutil.rmtree(directory)
        os.replace(staged, directory)
        return directory, manifest
    except OSError as e:
        raise ArtError(f"立ち絵素材のキャッシュに書き込めません: {e}") from None
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------- 素材の状態（assets） ----------

ASSET_CACHED = "キャッシュ済み"
ASSET_ZIP = "zip あり"
ASSET_AUTO = "自動取得可"
ASSET_MISSING = "素材なし"


def asset_state(definition: dict) -> str:
    """素材の状態を、優先順に判定する。読むだけで、ネットワーク接続・zip の展開・キャッシュへの書き込みをしない。"""
    source = definition["source"]
    if _cached_manifest(definition) is not None:
        return ASSET_CACHED
    if _local_zip(source) is not None:
        return ASSET_ZIP
    return ASSET_AUTO if "url" in source else ASSET_MISSING


def _missing_guide(source: dict) -> str:
    guide = _how_to_get(source)
    if (sources_root() / source["file"]).exists():
        guide += "（いま置いてある zip は MD5 が定義と一致しません）"
    return guide


def asset_report(definitions: dict[str, dict] | None = None) -> list[str]:
    """話者ごとに1行で、素材の状態を返す。素材なしの行には、取得手順の警告を含める。"""
    definitions = load_definitions() if definitions is None else definitions
    lines = []
    for speaker, definition in definitions.items():
        state = asset_state(definition)
        if state == ASSET_MISSING:
            lines.append(f"{speaker}: {state}（警告: {_missing_guide(definition['source'])}）")
        else:
            lines.append(f"{speaker}: {state}")
    return lines


def asset_warnings(project: Project, definitions: dict[str, dict] | None = None) -> list[str]:
    """台本で使う話者のうち、素材なしの話者についての警告（lint が出す）。"""
    definitions = load_definitions() if definitions is None else definitions
    return [
        f"警告: 話者「{voice}」の立ち絵素材がありません（build は失敗します）。{_missing_guide(definitions[voice]['source'])}"
        for voice in project.voices
        if voice in definitions and asset_state(definitions[voice]) == ASSET_MISSING
    ]


# ---------- 表情 ----------


def _hidden_by(chosen: list[str], path: str, choices: tuple[str, ...] = ()) -> bool:
    """chosen を表示すると path が隠れるか（PSDTool の規則）。

    「*」で始まる名前は、同じグループの中で1つだけ選べる選択肢。選ぶと、同じ階層の他の「*」と
    その下が隠れる。「!」で始まる名前は、選択肢に関係なく表示される。
    choices は、「*」のない素材で、中の1つだけを選ぶグループ（定義の choices）。
    """
    parts = path.split("/")
    for c in chosen:
        if c == path:
            return True
        if "/" in c and c.rsplit("/", 1)[0] in choices and path.rsplit("/", 1)[0] == c.rsplit("/", 1)[0]:
            return True
        cparts = c.split("/")
        for i, name in enumerate(cparts):
            if (
                name.startswith("*")
                and len(parts) > i
                and parts[:i] == cparts[:i]
                and parts[i].startswith("*")
                and parts[i] != name
            ):
                return True
    return False


def _resolve_face(definition: dict, name: str) -> dict:
    """表情を、自分のレイヤー＋ normal のレイヤーのうち隠れないもの、として解決する。

    blink は、まばたきで目のレイヤーに替える閉じ目のレイヤー。省略なら normal のもの、null ならまばたきしない。
    """
    faces, choices = definition["faces"], tuple(definition.get("choices", ()))
    face, normal = faces[name], faces[DEFAULT_FACE]
    own = list(face.get("layers", []))
    return {
        "layers": own + [p for p in normal["layers"] if not _hidden_by(own, p, choices)],
        "mouth": list(face.get("mouth", normal["mouth"])),
        "blink": face["blink"] if "blink" in face else normal.get("blink"),
    }


def used_faces(project: Project, definitions: dict[str, dict] | None = None) -> dict[str, list[str]]:
    """話者ごとに、台本で使う表情（既定の表情を含む）を返す。定義にない話者や表情があれば失敗する（E33）。

    素材は取得しない（lint からも呼ぶ）。
    """
    definitions = load_definitions() if definitions is None else definitions
    used: dict[str, list[str]] = {}
    for voice in project.voices:
        definition = definitions.get(voice)
        if definition is None:
            raise ArtError(f"話者「{voice}」の立ち絵の定義がありません")
        faces = definition["faces"]
        names = [DEFAULT_FACE]
        for line in project.lines:
            if line.speaker == voice and line.expression and line.expression not in names:
                if line.expression not in faces:
                    raise ArtError(
                        f"script.json の {line.path}.expression「{line.expression}」は、{voice}の立ち絵にありません。"
                        f"使える表情: {', '.join(faces)}"
                    )
                names.append(line.expression)
        used[voice] = names
    return used


def _sides(definitions: list[dict]) -> list[str]:
    """立ち位置。定義の side を使い、2人が同じ側なら、後から出た人を反対側に置く（話者は2人まで）。"""
    sides = [definition["side"] for definition in definitions]
    if len(sides) == 2 and sides[0] == sides[1]:
        sides[1] = "right" if sides[0] == "left" else "left"
    return sides


def build_cast(project: Project) -> list[dict]:
    """台本で使う話者ごとに、使う表情のレイヤーを埋め込んだデータを返す（台本に出た順）。"""
    definitions = load_definitions()
    used = used_faces(project, definitions)
    cast = []
    for (voice, names), side in zip(used.items(), _sides([definitions[voice] for voice in used]), strict=True):
        definition = definitions[voice]
        resolved = {name: _resolve_face(definition, name) for name in names}
        directory, manifest = _prepare(definition)
        by_path = {layer["path"]: layer for layer in manifest["layers"]}
        wanted = set(definition["base"]) | {
            p for f in resolved.values() for p in [*f["layers"], *f["mouth"], f["blink"]] if p is not None
        }
        missing = sorted(wanted - set(by_path))
        if missing:
            raise ArtError(f"立ち絵の定義のレイヤーが素材にありません（{definition['id']}）: {', '.join(missing)}")
        layers = {}
        for layer in manifest["layers"]:  # 重ねる順を保つ
            if layer["path"] in wanted:
                png = (directory / layer["file"]).read_bytes()
                layers[layer["path"]] = {
                    "x": layer["x"],
                    "y": layer["y"],
                    "w": layer["w"],
                    "h": layer["h"],
                    "blend": layer["blend"],
                    "src": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                }
        cast.append(
            {
                "speaker": voice,
                "color": definition.get("color", "#888888"),
                "side": side,
                "facing": definition["facing"],
                "base": definition["base"],
                "faces": resolved,
                "layers": layers,
            }
        )
    return cast
