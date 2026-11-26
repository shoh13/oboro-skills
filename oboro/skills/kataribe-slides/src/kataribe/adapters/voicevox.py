"""VOICEVOX（Docker 上のエンジン）を使う TTSアダプター。

契約: テキストを stdin、--voice、--speed、--output（WAV）。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

IMAGE = "voicevox/voicevox_engine:cpu-ubuntu24.04-0.25.2"
CONTAINER = "kataribe-voicevox"
LABEL = "kataribe=voicevox"
STYLE = "ノーマル"
STARTUP_TIMEOUT = 120.0
# エンジンの合成の定数（voicevox_engine の tts_engine.py）
FRAMES_PER_SECOND = 24000 / 256
UPSPEAK_SECONDS = 0.15


class AdapterError(Exception):
    pass


@dataclass(frozen=True)
class Spoken:
    reading: str  # エンジンが組み立てた読み
    seconds: float  # 音声クエリから計算した音声の長さ
    accented: str = ""  # アクセント付きの読み（accented_reading_of）
    phrases: tuple[tuple[str, ...], ...] = ()  # アクセント句ごとのモーラのカタカナ


def _docker(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise AdapterError("VOICEVOX を起動できません: docker コマンドが見つかりません") from None


def _container_url() -> str:
    port = _docker("port", CONTAINER, "50021/tcp")
    if port.returncode != 0 or not port.stdout.strip():
        raise AdapterError(f"VOICEVOX のコンテナ {CONTAINER} のポートを取得できません: {port.stderr.strip()}")
    return f"http://{port.stdout.splitlines()[0].strip().replace('0.0.0.0', '127.0.0.1')}"


def _ensure_container() -> str:
    info = _docker("info", "--format", "{{.ServerVersion}}")
    if info.returncode != 0:
        raise AdapterError(f"VOICEVOX を起動できません: Docker が動いていません ({info.stderr.strip()})")
    inspect = _docker("container", "inspect", CONTAINER)
    if inspect.returncode != 0:
        print(f"VOICEVOX を起動します（{IMAGE}。初回はイメージを取得します）", file=sys.stderr)
        run = _docker("run", "-d", "--name", CONTAINER, "--label", LABEL, "-p", "127.0.0.1::50021", IMAGE)
        if run.returncode != 0:
            raise AdapterError(f"VOICEVOX のコンテナを作成できません: {run.stderr.strip()}")
    else:
        start = _docker("start", CONTAINER)
        if start.returncode != 0:
            raise AdapterError(f"VOICEVOX のコンテナを開始できません: {start.stderr.strip()}")
    url = _container_url()
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            _request(f"{url}/version")
            return url
        except AdapterError:
            time.sleep(1)
    raise AdapterError(f"VOICEVOX が起動しませんでした。`docker logs {CONTAINER}` を確認してください")


def _external_url() -> str | None:
    return os.environ.get("KATARIBE_VOICEVOX_URL") or None


def engine_url() -> str:
    """使う VOICEVOX エンジンの URL。KATARIBE_VOICEVOX_URL があればそれを、なければ Docker のコンテナを起動する。"""
    return _external_url() or _ensure_container()


def uses_own_container() -> bool:
    """kataribe が起動する Docker のコンテナを使うか（KATARIBE_VOICEVOX_URL がない）。"""
    return _external_url() is None


def engine_identity() -> str:
    """合成する音声を左右するエンジンの版。自前のコンテナはイメージのタグ、KATARIBE_VOICEVOX_URL はエンジンの /version。"""
    url = _external_url()
    if url is None:
        return IMAGE
    return "voicevox_engine " + _request(f"{url}/version").decode("utf-8", "replace").strip()


def _request(url: str, data: bytes | None = None, content_type: str | None = None, method: str | None = None) -> bytes:
    request = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"))
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as e:  # URLError の下位なので先に書く
        detail = e.read().decode("utf-8", "replace").strip()[:200]
        raise AdapterError(f"VOICEVOX がエラーを返しました ({url}, HTTP {e.code}): {detail}") from None
    except (urllib.error.URLError, OSError) as e:
        raise AdapterError(f"VOICEVOX に接続できません ({url}): {e}") from None


def _speakers(base: str) -> list[dict]:
    return json.loads(_request(f"{base}/speakers"))


def _speaker_id(speakers: list[dict], voice: str) -> int:
    for speaker in speakers:
        if speaker["name"] == voice:
            for style in speaker["styles"]:
                if style["name"] == STYLE:
                    return style["id"]
    names = ", ".join(speaker["name"] for speaker in speakers)
    raise AdapterError(f"VOICEVOX に声「{voice}」（スタイル {STYLE}）がありません。使える声: {names}")


def _query(base: str, speaker: int, text: str) -> dict:
    """/audio_query の応答（音声クエリ）。合成に使う読み・アクセント・ポーズを含む。"""
    url = f"{base}/audio_query?" + urllib.parse.urlencode({"speaker": speaker, "text": text})
    return json.loads(_request(url, data=b""))


def reading_of(query: dict) -> str:
    """音声クエリから、エンジンが組み立てた読みを返す。アクセント句ごとに空白で区切り、ポーズは「、」で示す。

    読みは各モーラ（拍）のカタカナを連ねたもので、エンジンが実際に発音する単位。
    ただし、アクセントや抑揚が正しいかは分からない（この値は、正しさの保証ではない）。
    """
    if "accent_phrases" not in query:
        raise AdapterError("VOICEVOX の音声クエリに読み（accent_phrases）がありません")
    reading = ""
    after_pause = True
    for phrase in query["accent_phrases"]:
        if reading and not after_pause:
            reading += " "  # ポーズのあとは「、」が区切りを示すので、空白は要らない
        reading += "".join(mora["text"] for mora in phrase["moras"])
        pause = phrase.get("pause_mora")
        if pause:
            reading += pause["text"]
        after_pause = bool(pause)
    return reading


def accented_reading_of(query: dict) -> str:
    """音声クエリから、アクセント付きの読みを返す（AquesTalk 風の記法）。

    アクセント核（その拍のあとで音が下がる拍。accent は句の先頭からの1始まりの位置）のあとに「'」を置き、
    アクセント句を「/」で区切り、ポーズを「、」で示す。
    """
    if "accent_phrases" not in query:
        raise AdapterError("VOICEVOX の音声クエリに読み（accent_phrases）がありません")
    text = ""
    after_pause = True
    for phrase in query["accent_phrases"]:
        if text and not after_pause:
            text += "/"
        for position, mora in enumerate(phrase["moras"], start=1):
            text += mora["text"] + ("'" if position == phrase.get("accent") else "")
        pause = phrase.get("pause_mora")
        if pause:
            text += "、"
        after_pause = bool(pause)
    return text


def phrase_moras(query: dict) -> tuple[tuple[str, ...], ...]:
    """音声クエリのアクセント句ごとの、モーラのカタカナ。"""
    return tuple(tuple(mora["text"] for mora in phrase["moras"]) for phrase in query.get("accent_phrases", ()))


def query_seconds(query: dict) -> float:
    """音声クエリから音声の長さ（秒）を計算する。エンジンの合成と同じ手順で、音素ごとにフレームへ丸める。

    話速の倍率は、前後の無音・間・疑問文の上げ調子にも掛かる。疑問文の句は、末尾の拍が有声なら、
    上げ調子の拍が1つ増える（音声クエリの拍には現れない）。
    """

    def frames(seconds: float) -> int:
        return round(seconds / query["speedScale"] * FRAMES_PER_SECOND)

    try:
        total = frames(query["prePhonemeLength"]) + frames(query["postPhonemeLength"])
        for phrase in query["accent_phrases"]:
            for mora in [*phrase["moras"], phrase.get("pause_mora")]:
                if mora:
                    total += frames(mora.get("consonant_length") or 0.0) + frames(mora["vowel_length"])
            if phrase.get("is_interrogative") and phrase["moras"] and phrase["moras"][-1]["pitch"] > 0:
                total += frames(UPSPEAK_SECONDS)
    except (KeyError, TypeError, ZeroDivisionError) as e:
        raise AdapterError(f"VOICEVOX の音声クエリから音声の長さを計算できません: {e!r}") from None
    return total / FRAMES_PER_SECOND


def read_aloud(base: str, items: list[tuple[str, str]]) -> list[Spoken]:
    """（合成に渡す文, 声）の並びそれぞれについて、エンジンが合成に使う読みと音声の長さを返す。音声は作らない。"""
    speakers = _speakers(base)
    results = []
    for text, voice in items:
        query = _query(base, _speaker_id(speakers, voice), text)
        results.append(Spoken(reading_of(query), query_seconds(query), accented_reading_of(query), phrase_moras(query)))
    return results


def synthesize(base: str, text: str, voice: str, speed: float) -> bytes:
    speaker = _speaker_id(_speakers(base), voice)
    query = _query(base, speaker, text)
    query["speedScale"] = speed
    return _request(
        f"{base}/synthesis?" + urllib.parse.urlencode({"speaker": speaker}),
        data=json.dumps(query).encode("utf-8"),
        content_type="application/json",
    )


# ユーザー辞書の発音の拍の数え方（voicevox_engine の user_dict/model.py の UserDictWord と同じ規則）
_MORA = re.compile(
    "(?:[イ][ェ]|[ヴ][ャュョ]|[ウクグトド][ゥ]|[テデ][ィェャュョ]|[クグ][ヮ]"
    "|[キシチニヒミリギジヂビピ][ェャュョ]|[キニヒミリギビピ][ィ]"
    "|[クツフヴグ][ァ]|[ウクスツフヴグズ][ィ]|[ウクツフヴグ][ェォ]"
    "|[ァ-ヴー])"
)
KATAKANA = re.compile(r"[ァ-ヴ][ァ-ヴー]*")  # 長音で始まる読みは、拍にならないので受け付けない


def mora_count(pronunciation: str) -> int:
    """カタカナの発音の拍の数。ユーザー辞書のアクセント型は 0 からこの数まで。"""
    return len(_MORA.findall(pronunciation))


def _zenkaku(text: str) -> str:
    """エンジンがユーザー辞書の表記に施す変換（半角の英数字・記号を全角へ）。"""
    return "".join(chr(ord(char) + 0xFEE0) if "!" <= char <= "~" else char for char in text)


# 既定の優先度（5）では、エンジンの辞書の解析（「数テラ」＋「バイト」など）に負けて、登録した語が使われないことがある
WORD_PRIORITY = 10


def _word_query(pronunciation: str, accent: int) -> str:
    return urllib.parse.urlencode(
        {"surface": pronunciation, "pronunciation": pronunciation, "accent_type": accent, "priority": WORD_PRIORITY}
    )


def _write_word(url: str, method: str, pronunciation: str, accent: int) -> None:
    try:
        _request(url, data=b"", method=method)
    except AdapterError as e:
        raise AdapterError(f"VOICEVOX のユーザー辞書に「{pronunciation}」（アクセント {accent}）を登録できません: {e}") from None


def sync_user_dict(base: str, words: Iterable[tuple[str, int]], exclusive: bool) -> None:
    """エンジンのユーザー辞書を words（発音のカタカナ, アクセント型）に合わせる。語の表記は発音と同じカタカナ。

    exclusive なら、辞書を words ちょうどにする（words にない語と、同じ表記の重複を消す）。kataribe のコンテナ用。
    exclusive でなければ、追加と更新だけで、消さない（KATARIBE_VOICEVOX_URL の、他の人も使うエンジン用）。
    いまの辞書と比べて違う語だけを書くので、何度実行しても同じ状態になる。
    """
    wanted = {_zenkaku(pronunciation): (pronunciation, accent) for pronunciation, accent in words}
    current: dict[str, dict] = json.loads(_request(f"{base}/user_dict"))
    present: set[str] = set()
    for uuid, entry in current.items():
        surface = entry.get("surface")
        if surface not in wanted or (exclusive and surface in present):
            if exclusive:
                _request(f"{base}/user_dict_word/{urllib.parse.quote(uuid)}", method="DELETE")
            continue
        present.add(surface)
        pronunciation, accent = wanted[surface]
        if (
            entry.get("pronunciation") != pronunciation
            or entry.get("accent_type") != accent
            or entry.get("priority", WORD_PRIORITY) != WORD_PRIORITY
        ):
            url = f"{base}/user_dict_word/{urllib.parse.quote(uuid)}?{_word_query(pronunciation, accent)}"
            _write_word(url, "PUT", pronunciation, accent)
    for surface, (pronunciation, accent) in wanted.items():
        if surface not in present:
            _write_word(f"{base}/user_dict_word?{_word_query(pronunciation, accent)}", "POST", pronunciation, accent)


def prepare_engine(words: Sequence[tuple[str, int]]) -> str:
    """音声クエリの前に1回、親のプロセスで呼ぶ。エンジンを用意してユーザー辞書を合わせ、エンジンの URL を返す。

    自前のコンテナでは、辞書をこのプロジェクトの語ちょうどにする（前のプロジェクトの語を残さない）。
    KATARIBE_VOICEVOX_URL のエンジンでは、追加と更新だけ（登録する語がなければ辞書に触れない）。
    """
    base = engine_url()
    own = uses_own_container()
    if own or words:
        sync_user_dict(base, words, exclusive=own)
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kataribe-voicevox")
    parser.add_argument("--voice", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    text = sys.stdin.read()
    try:
        wav = synthesize(engine_url(), text, args.voice, args.speed)
    except AdapterError as e:
        print(e, file=sys.stderr)
        return 1
    args.output.write_bytes(wav)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
