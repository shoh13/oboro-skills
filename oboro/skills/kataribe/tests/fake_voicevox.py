"""テスト用の偽の VOICEVOX エンジン（HTTP）。conftest.py がフィクスチャ engine を登録する。"""

import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest


FRAME = 256 / 24000  # 音声クエリの長さは、このフレームの整数倍にして、計算の期待値を読みやすくする
SPEAKERS = [
    {"name": "ずんだもん", "styles": [{"name": "あまあま", "id": 1}, {"name": "ノーマル", "id": 3}]},
    {"name": "四国めたん", "styles": [{"name": "ノーマル", "id": 2}]},
]


def silent_wav(seconds: float) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(b"\x00\x00" * int(24000 * seconds))
    return buffer.getvalue()


def fake_query(text: str) -> dict:
    """偽のエンジンの音声クエリ。「、」で区切ったアクセント句にし、文字をそのままモーラとする（読みは表示文と同じ）。"""
    segments = text.split("、")
    phrases = []
    for index, segment in enumerate(segments):
        moras = [{"text": char, "consonant_length": 4 * FRAME, "vowel_length": 5 * FRAME} for char in segment]
        phrase = {"moras": moras, "accent": 1, "pause_mora": None}
        if index < len(segments) - 1:
            phrase["pause_mora"] = {"text": "、", "consonant_length": None, "vowel_length": 45 * FRAME}
        phrases.append(phrase)
    return {"speedScale": 1.0, "prePhonemeLength": 9 * FRAME, "postPhonemeLength": 9 * FRAME, "text": text, "accent_phrases": phrases}


@pytest.fixture
def engine():
    requests: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send(self, body: bytes, content_type: str):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/speakers":
                self._send(json.dumps(SPEAKERS).encode(), "application/json")
            elif path == "/version":
                self._send(b'"0.25.2"', "application/json")
            elif path == "/user_dict":
                self._send(b"{}", "application/json")
            else:
                self.send_error(404)

        def do_POST(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)  # 空の text= も、実際のエンジンと同じく届く
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            requests.append({"path": parsed.path, "query": query, "body": body})
            if parsed.path == "/audio_query":
                self._send(json.dumps(fake_query(query["text"][0])).encode(), "application/json")
            elif parsed.path == "/synthesis":
                self._send(silent_wav(0.3), "audio/wav")
            else:
                self.send_error(404)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", requests
    server.shutdown()
