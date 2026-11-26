"""テスト用のTTSアダプター。stdin のテキストの長さに比例した無音WAV（FAKE_TTS_TONE があれば440Hzの音）を --output に書く。"""
import argparse
import json
import math
import os
import struct
import sys
import wave

SAMPLE_RATE = 24000
SECONDS_PER_CHAR = float(os.environ.get("FAKE_TTS_SECONDS_PER_CHAR", "0.02"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    text = sys.stdin.read()
    log = os.environ.get("FAKE_TTS_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(text, ensure_ascii=False) + "\n")
    voice_log = os.environ.get("FAKE_TTS_VOICE_LOG")
    if voice_log:
        with open(voice_log, "a", encoding="utf-8") as f:
            f.write(args.voice + "\n")
    frames = round(len(text) * SECONDS_PER_CHAR * SAMPLE_RATE)
    with wave.open(args.output, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        if os.environ.get("FAKE_TTS_TONE"):
            out.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE))) for i in range(frames)))
        else:
            out.writeframes(b"\x00\x00" * frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
