"""VOICEVOX（Docker 上のエンジン）を使う TTSアダプター。

契約: テキストを stdin、--voice、--speed、--output（WAV）。
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IMAGE = "voicevox/voicevox_engine:cpu-ubuntu24.04-0.25.2"
CONTAINER = "kataribe-voicevox"
LABEL = "kataribe=voicevox"
STYLE = "ノーマル"
STARTUP_TIMEOUT = 120.0


class AdapterError(Exception):
    pass


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


def _request(url: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as e:
        raise AdapterError(f"VOICEVOX に接続できません ({url}): {e}") from None


def _speaker_id(base: str, voice: str) -> int:
    speakers = json.loads(_request(f"{base}/speakers"))
    for speaker in speakers:
        if speaker["name"] == voice:
            for style in speaker["styles"]:
                if style["name"] == STYLE:
                    return style["id"]
    names = ", ".join(speaker["name"] for speaker in speakers)
    raise AdapterError(f"VOICEVOX に声「{voice}」（スタイル {STYLE}）がありません。使える声: {names}")


def synthesize(base: str, text: str, voice: str, speed: float) -> bytes:
    speaker = _speaker_id(base, voice)
    query_url = f"{base}/audio_query?" + urllib.parse.urlencode({"speaker": speaker, "text": text})
    query = json.loads(_request(query_url, data=b""))
    query["speedScale"] = speed
    return _request(
        f"{base}/synthesis?" + urllib.parse.urlencode({"speaker": speaker}),
        data=json.dumps(query).encode("utf-8"),
        content_type="application/json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kataribe-voicevox")
    parser.add_argument("--voice", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    text = sys.stdin.read()
    try:
        base = os.environ.get("KATARIBE_VOICEVOX_URL") or _ensure_container()
        wav = synthesize(base, text, args.voice, args.speed)
    except AdapterError as e:
        print(e, file=sys.stderr)
        return 1
    args.output.write_bytes(wav)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
