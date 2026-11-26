"""音声クエリから計算した音声の長さ（readings）と、build の実測長を比べる（要件 B-1 の確認用）。

使い方: uv run python tests/compare_speed.py <project> [--out <build の出力先>]
既定の VOICEVOX（Docker。KATARIBE_VOICEVOX_URL があればそのエンジン）に問い合わせる。音声は合成しない。
字幕の表示速度の警告の判定が全行で一致すれば終了コード0、不一致や比較不能なら1。
"""

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from kataribe.check import MAX_CHARS_PER_SECOND, chars_per_second
from kataribe.project import load_project
from kataribe.readcheck import ReadingRow, check_readings


@dataclass(frozen=True)
class Comparison:
    lines: int
    rmse: float
    largest_error: float
    warned_by_build: list[str]
    warned_by_readings: list[str]

    @property
    def agrees(self) -> bool:
        return self.warned_by_build == self.warned_by_readings


def read_timeline(out: Path) -> dict:
    """build の実測長が入ったタイムラインを読む。--extras がなくても video.html から読める。"""
    html = (out / "video.html").read_text(encoding="utf-8")
    match = re.search(r'id="kataribe-timeline">(.*?)</script>', html, re.S)
    if not match:
        raise ValueError(f"{out / 'video.html'} にタイムラインがありません")
    return json.loads(match.group(1))


def compare(rows: list[ReadingRow], timeline: dict) -> Comparison:
    lines = timeline["lines"]
    if [(row.id, row.text) for row in rows] != [(line["id"], line["text"]) for line in lines]:
        raise ValueError("台本と build のタイムラインの行が一致しません。build し直してください")
    errors = [row.seconds - (line["end"] - line["start"]) for row, line in zip(rows, lines, strict=True)]
    return Comparison(
        lines=len(rows),
        rmse=math.sqrt(sum(e * e for e in errors) / len(errors)),
        largest_error=max(abs(e) for e in errors),
        warned_by_build=[line["id"] for line in lines if chars_per_second(line["text"], line["end"] - line["start"]) > MAX_CHARS_PER_SECOND],
        warned_by_readings=[row.id for row in rows if chars_per_second(row.text, row.seconds) > MAX_CHARS_PER_SECOND],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = compare(check_readings(load_project(args.project)), read_timeline(args.out or args.project / "out"))
    print(f"{result.lines} 行: RMSE {result.rmse:.4f} 秒、最大の差 {result.largest_error:.4f} 秒")
    print(f"警告: build {len(result.warned_by_build)} 行、readings {len(result.warned_by_readings)} 行")
    if not result.agrees:
        print(f"build だけ: {sorted(set(result.warned_by_build) - set(result.warned_by_readings))}")
        print(f"readings だけ: {sorted(set(result.warned_by_readings) - set(result.warned_by_build))}")
    print("判定: " + ("一致" if result.agrees else "不一致"))
    return 0 if result.agrees else 1


if __name__ == "__main__":
    sys.exit(main())
