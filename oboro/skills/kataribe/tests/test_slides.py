import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import make_project, run_build, run_lint
from pptx import Presentation
from pptx.oxml.ns import qn

SLIDES_SCRIPT = {
    "title": "テストのスライド",
    "description": "説明文",
    "sources": [{"title": "出典の題", "url": "https://example.com/"}],
    "chapters": [
        {
            "id": "c1",
            "title": "最初の章",
            "scenes": [
                {
                    "id": "s1",
                    "title": "一枚目",
                    "lines": [
                        {"text": "地の文の一段落目です。"},
                        {"speaker": "ずんだもん", "expression": "smile", "text": "なるほどなのだ"},
                        {"speaker": "四国めたん", "text": "そうね"},
                        {"text": "地の文の二段落目です。"},
                        {"speaker": "四国めたん", "expression": "angry", "text": "違うわ"},
                    ],
                },
                {"id": "s2", "lines": [{"text": "二枚目の地の文です。"}, {"speaker": "ずんだもん", "text": "おしまいなのだ"}]},
            ],
        }
    ],
}


def make_slides(root: Path, script: dict | None = None) -> Path:
    """スライドのプロジェクト。readings.json も scenes.html も置かない（スライドでは使わない）。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "script.json").write_text(json.dumps(script or SLIDES_SCRIPT, ensure_ascii=False), encoding="utf-8")
    return root


def run_slides(project: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KATARIBE_TTS_CMD"] = "/nonexistent/kataribe-tts"  # 音声を合成しないことを確かめる
    return subprocess.run([sys.executable, "-m", "kataribe", *args, str(project)], capture_output=True, text=True, env=env)


def narration(slide) -> list[str]:
    """地の文の段落（上から）。"""
    return [shape.text_frame.text for shape in slide.shapes if shape.name.startswith("地の文 ")]


def texts(slide) -> dict[str, list[str]]:
    """図形の名前 → 段落の文字列。"""
    return {shape.name: [p.text for p in shape.text_frame.paragraphs] for shape in slide.shapes if shape.has_text_frame}


def run_colors(slide, name: str) -> list[str]:
    shape = next(s for s in slide.shapes if s.name == name)
    return [str(p.runs[0].font.color.rgb) for p in shape.text_frame.paragraphs if p.runs]


def pictures(slide) -> list[str]:
    return [shape.name for shape in slide.shapes if shape.shape_type == 13]  # MSO_SHAPE_TYPE.PICTURE


def built(tmp_path) -> Presentation:
    project = make_slides(tmp_path / "p")
    result = run_slides(project, "slides")
    assert result.returncode == 0, result.stderr
    return Presentation(str(project / "out" / "slides.pptx"))


def test_slidesは_音声を合成せず_readingsとscenesがなくても_slides_pptxを作る(tmp_path):
    project = make_slides(tmp_path / "p")

    result = run_slides(project, "slides")

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (project / "out").iterdir()) == ["slides.pptx"]


def test_表紙と_台本の1行ごとに1枚と_クレジットのスライドができる(tmp_path):
    prs = built(tmp_path)

    assert len(prs.slides) == 1 + 7 + 1
    assert prs.slide_width / prs.slide_height == 16 / 9
    cover = texts(prs.slides[0])["表紙"]
    assert cover == ["テストのスライド", "説明文"]
    credits = "\n".join(texts(prs.slides[-1])["クレジット"])
    assert "非商用" in credits
    assert "出典の題" in credits


def test_地の文は積み上がり_今の地の文だけ濃く_後の地の文はまだ出ない(tmp_path):
    prs = built(tmp_path)
    first, second_narration = prs.slides[1], prs.slides[4]

    assert texts(first)["見出し"] == ["最初の章", "一枚目"]
    assert narration(first) == ["地の文の一段落目です。"]
    assert narration(second_narration) == ["地の文の一段落目です。", "地の文の二段落目です。"]
    assert run_colors(second_narration, "地の文 1") != run_colors(second_narration, "地の文 2")
    names = [s.name for s in second_narration.shapes]
    assert names.count("解説の枠") == 1 and names.index("解説の枠") < names.index("見出し")  # 見出しと地の文を白い枠で囲む
    assert names.count("番号 2") == 1


def telops(slide) -> list[tuple[str, str, int, int]]:
    """前面のテロップの (話者（行ID）, 文字, 上端, 下端)。上から順。"""
    found = [
        (shape.name.removeprefix("テロップ "), shape.text_frame.text, shape.top, shape.top + shape.height)
        for shape in slide.shapes
        if shape.name.startswith("テロップ ")
    ]
    return sorted(found, key=lambda t: t[2])


def test_同じ解説へのコメントは消さずに積み_位置はめくっても動かない(tmp_path):
    prs = built(tmp_path)
    narration_slide, zunda, metan, next_narration, angry = (prs.slides[i] for i in range(1, 6))

    assert telops(narration_slide) == []
    assert pictures(narration_slide) == ["立ち絵 ずんだもん（normal）", "立ち絵 四国めたん（normal）"]

    [first] = telops(zunda)
    assert first[:2] == ("ずんだもん（s1-1）", "なるほどなのだ")
    assert "立ち絵 ずんだもん（smile）" in pictures(zunda)

    upper, lower = telops(metan)
    assert upper == first  # 先のコメントは、同じ位置に残る
    assert lower[:2] == ("四国めたん（s1-2）", "そうね")
    assert upper[3] <= lower[2]  # 重ならない
    assert pictures(metan) == ["立ち絵 ずんだもん（smile）", "立ち絵 四国めたん（normal）"]  # 話していない人は最後の表情のまま

    assert telops(next_narration) == []  # 次の地の文で消える
    [only] = telops(angry)
    assert only[:2] == ("四国めたん（s1-4）", "違うわ")
    assert only[3] == lower[3]  # かたまりの最後のコメントの下端は、いつも同じ
    assert "立ち絵 四国めたん（angry）" in pictures(angry)
    assert angry.notes_slide.notes_text_frame.text == "四国めたん: 違うわ"


def test_コメントが帯に入らなければ_そのかたまりだけ文字を小さくする():
    from kataribe.slides import TELOP_BOTTOM, TELOP_MIN_PT, TELOP_PT, TELOP_TOP, telop_layout

    pt, slots, fits = telop_layout(["短い", "短い"])
    assert (pt, fits) == (TELOP_PT, True)

    pt, slots, fits = telop_layout(["あ" * 25] * 3)
    assert TELOP_MIN_PT <= pt < TELOP_PT and fits
    assert slots[0][0] >= TELOP_TOP - 1e-9
    assert slots[-1][0] + slots[-1][1] == pytest.approx(TELOP_BOTTOM)
    assert all(a[0] + a[1] <= b[0] for a, b in zip(slots, slots[1:]))

    assert telop_layout(["あ" * 80] * 4)[2] is False


def test_テロップは_枠を中央にそろえ_文字を話者の側に詰めて_テーマカラーで書き_解説の枠の下に出す(tmp_path):
    from kataribe.slides import PANEL, SLIDE_W, telop_color
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    slide = built(tmp_path).slides[3]  # ずんだもん（右）と四国めたん（左）のコメント
    names = [shape.name for shape in slide.shapes]
    shapes = {shape.name: shape for shape in slide.shapes}
    zunda, metan = shapes["テロップ ずんだもん（s1-1）"], shapes["テロップ 四国めたん（s1-2）"]

    assert not any(name.startswith("テロップの") for name in names)  # 縁取りの重ね（Google スライドで消える）は使わない
    assert zunda.text_frame.paragraphs[0].runs[0]._r.find(qn("a:rPr")).find(qn("a:ln")) is None
    for telop in (zunda, metan):
        assert telop.left + telop.width / 2 == pytest.approx(Inches(SLIDE_W) / 2, abs=2)  # 枠はスライドの中央
        assert telop.top >= Inches(PANEL[3])  # 解説の枠の下
        assert telop.text_frame.paragraphs[0].runs[0].font.color.rgb == telop_color("#888888")  # テスト用の定義は color なし（既定の灰色）
    assert zunda.text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT  # 右に立つ人は右詰め
    assert metan.text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT  # 左に立つ人は左詰め
    assert names.index("立ち絵 ずんだもん（smile）") < names.index("テロップ ずんだもん（s1-1）")


def test_シーンにtitleがなければ_章の題名を見出しにする(tmp_path):
    prs = built(tmp_path)

    assert texts(prs.slides[6])["見出し"] == ["", "最初の章"]


def test_slidesは_動画の出力に触らない(tmp_path):
    project = make_project(tmp_path / "p")
    assert run_build(project).returncode == 0
    video = (project / "out" / "video.html").read_bytes()

    result = run_slides(project, "slides")

    assert result.returncode == 0, result.stderr
    assert (project / "out" / "video.html").read_bytes() == video
    assert (project / "out" / "slides.pptx").is_file()


def test_地の文は動画のlintでは_slidesでだけ使えると示して失敗する(tmp_path):
    scenes = '<section data-scene="s1"></section><section data-scene="s2"></section>'
    project = make_project(tmp_path / "p", script=SLIDES_SCRIPT, scenes=scenes)

    result = run_lint(project)

    assert result.returncode == 1
    assert "slides" in result.stderr
    assert "chapters[0].scenes[0].lines[0].speaker" in result.stderr


def test_地の文に表情を付けると失敗する(tmp_path):
    script = json.loads(json.dumps(SLIDES_SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][0]["expression"] = "smile"
    project = make_slides(tmp_path / "p", script)

    result = run_slides(project, "lint", "--slides")

    assert result.returncode == 1
    assert "地の文" in result.stderr
    assert "lines[0].expression" in result.stderr


def test_lint_slidesは_長いコメントと_詰め込みすぎた地の文を警告して続行する(tmp_path):
    script = json.loads(json.dumps(SLIDES_SCRIPT, ensure_ascii=False))
    lines = script["chapters"][0]["scenes"][0]["lines"]
    lines[1]["text"] = "あ" * 200
    lines[3]["text"] = "い" * 700
    project = make_slides(tmp_path / "p", script)

    result = run_slides(project, "lint", "--slides")

    assert result.returncode == 0, result.stderr
    assert "s1-1〜s1-2: 同じ解説へのコメントが多く" in result.stderr
    assert "s1-3: 地の文が長く、1枚に収まりません" in result.stderr
    assert not (project / "out").exists()


def test_コメントが多すぎてテロップが帯に入らなければ_かたまりの範囲を示して警告する(tmp_path):
    script = json.loads(json.dumps(SLIDES_SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][1]["text"] = "あ" * 200
    project = make_slides(tmp_path / "p", script)

    result = run_slides(project, "lint", "--slides")

    assert result.returncode == 0, result.stderr
    assert "s1-1〜s1-2: 同じ解説へのコメントが多く" in result.stderr


def test_強調は太字の別の色になり_記号は残らない(tmp_path):
    script = json.loads(json.dumps(SLIDES_SCRIPT, ensure_ascii=False))
    script["chapters"][0]["scenes"][0]["lines"][0]["text"] = "ここが**大事**です"
    project = make_slides(tmp_path / "p", script)
    assert run_slides(project, "slides").returncode == 0
    slide = Presentation(str(project / "out" / "slides.pptx")).slides[1]

    shape = next(s for s in slide.shapes if s.name == "地の文 1")
    runs = shape.text_frame.paragraphs[0].runs
    assert [r.text for r in runs] == ["ここが", "大事", "です"]
    assert runs[1].font.bold and not runs[0].font.bold
    assert runs[1].font.color.rgb != runs[0].font.color.rgb
    assert slide.notes_slide.notes_text_frame.text == "地の文: ここが大事です"


DIAGRAM_SCENES = """<section data-scene="s1">
  <img src="figures/dot.png" style="width:200px">
  <p data-at="3" style="font-size:60px">あとから出る</p>
</section>"""


def test_scenes_htmlの図は_行ごとの状態で撮って置き_画像ファイルも使える(tmp_path):
    from PIL import Image

    project = make_slides(tmp_path / "p")
    (project / "figures").mkdir()
    Image.new("RGB", (20, 20), (255, 0, 0)).save(project / "figures" / "dot.png")
    (project / "scenes.html").write_text(DIAGRAM_SCENES, encoding="utf-8")

    result = run_slides(project, "slides")

    assert result.returncode == 0, result.stderr
    prs = Presentation(str(project / "out" / "slides.pptx"))
    diagrams = [next((s for s in slide.shapes if s.name == "図"), None) for slide in prs.slides]
    assert [d is not None for d in diagrams] == [False, True, True, True, True, True, False, False, False]
    blobs = [d.image.blob for d in diagrams if d is not None]
    assert blobs[0] == blobs[2] != blobs[3]  # 行3で文字が出る
    first = Image.open(io.BytesIO(blobs[0])).convert("RGBA")
    assert first.getpixel((0, 0))[3] == 0  # 背景は透明
    assert (255, 0, 0) in {color for _, color in first.convert("RGB").getcolors(1 << 22)}  # 画像ファイルが写っている
    assert narration(prs.slides[4]) == ["地の文の二段落目です。"]  # 図のあるスライドは今の地の文だけ


def test_scenes_htmlの画像が見つからなければ_場所を示して失敗する(tmp_path):
    project = make_slides(tmp_path / "p")
    (project / "scenes.html").write_text(DIAGRAM_SCENES, encoding="utf-8")

    result = run_slides(project, "lint", "--slides")

    assert result.returncode == 1
    assert "figures/dot.png" in result.stderr
    assert "2行目" in result.stderr


def test_動画でも_scenes_htmlの画像ファイルを埋め込む(tmp_path):
    from PIL import Image

    project = make_project(tmp_path / "p", scenes='<section data-scene="s1"><img src="figures/dot.png"></section><section data-scene="s2"></section><section data-scene="s3"></section>')
    (project / "figures").mkdir()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(project / "figures" / "dot.png")

    result = run_build(project)

    assert result.returncode == 0, result.stderr
    html = (project / "out" / "video.html").read_text(encoding="utf-8")
    assert '<img src="data:image/png;base64,' in html
    assert "figures/dot.png" not in html


def test_テロップの色は_淡いテーマカラーだけを_白地で読める濃さまで暗くする():
    from kataribe.slides import TELOP_MIN_CONTRAST, contrast_with_white, telop_color

    yellow = telop_color("#e0a526")  # 春日部つむぎ
    assert contrast_with_white(tuple(yellow)) >= TELOP_MIN_CONTRAST
    assert tuple(yellow) != (0xE0, 0xA5, 0x26)
    assert str(telop_color("#1f2a44")) == "1F2A44"  # もとから濃い色は変えない


def test_図と地の文は_解説の領域からはみ出さず_見た目の枠はその下まで続く(tmp_path):
    from kataribe.slides import CONTENT_AREA, PANEL
    from PIL import Image
    from pptx.util import Inches

    project = make_slides(tmp_path / "p")
    (project / "figures").mkdir()
    Image.new("RGB", (20, 20), (255, 0, 0)).save(project / "figures" / "dot.png")
    (project / "scenes.html").write_text(DIAGRAM_SCENES, encoding="utf-8")
    assert run_slides(project, "slides").returncode == 0
    prs = Presentation(str(project / "out" / "slides.pptx"))

    assert PANEL[3] > CONTENT_AREA[3]  # 見た目の枠は、解説の領域より下まで（立ち絵の頭とテロップの上にかかる）
    for slide in list(prs.slides)[1:-1]:
        panel = next(s for s in slide.shapes if s.name == "解説の枠")
        assert panel.top + panel.height == pytest.approx(Inches(PANEL[3]), abs=2)
        for shape in slide.shapes:
            if shape.name == "図" or shape.name.startswith(("地の文", "番号")):
                assert shape.top + shape.height <= Inches(CONTENT_AREA[3]), (shape.name, (shape.top + shape.height) / 914400)


def test_slidesは_outを指定すると_そのディレクトリにslides_pptxを作り_プロジェクトのoutは作らない(tmp_path):
    project = make_slides(tmp_path / "p")
    out = tmp_path / "成果物" / "スライド"

    result = run_slides(project, "slides", "--out", str(out))

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in out.iterdir()) == ["slides.pptx"]
    assert not (project / "out").exists()
    assert [p.name for p in out.parent.iterdir()] == ["スライド"]  # 一時ディレクトリが残らない
