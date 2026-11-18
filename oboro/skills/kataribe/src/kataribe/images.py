"""scenes.html の画像ファイル（<img src="figures/a.png"> などの相対パス）を、data URI にして埋め込む。

単一HTMLは out/ に置かれ、スライドは画像に撮るので、プロジェクトからの相対パスのままでは画像が見えない。
http(s)・data・プロトコル相対（//）・絶対パス（/）・フラグメント（#）の参照は、そのまま残す。
"""

import base64
import html
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

SOURCE = re.compile(r"""(<(?:img|source|image)\b[^>]*?\s(?:src|href|xlink:href)\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
TYPES = {".svg": "image/svg+xml", ".webp": "image/webp", ".avif": "image/avif"}


class ImageError(Exception):
    pass


def _is_local(ref: str) -> bool:
    if not ref or ref.startswith(("#", "/", "//")):
        return False
    return not urlsplit(ref).scheme


def inline_images(scenes_html: str, root: Path) -> str:
    """root からの相対パスで参照した画像を、data URI に置き換える。ファイルがなければ ImageError。"""

    def replace(match: re.Match) -> str:
        prefix, quote, raw = match.groups()
        ref = html.unescape(raw).strip()
        if not _is_local(ref):
            return match.group(0)
        path = (root / unquote(urlsplit(ref).path)).resolve()
        if not path.is_file():
            line = scenes_html.count("\n", 0, match.start()) + 1
            raise ImageError(f"scenes.html の{line}行目: 画像「{ref}」が見つかりません（プロジェクトからの相対パスで書いてください）: {path}")
        kind = TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"{prefix}{quote}data:{kind};base64,{data}{quote}"

    return SOURCE.sub(replace, scenes_html)
