import json
import re

from kataribe.diagrams import PAGE
from kataribe.project import load_project
from kataribe.render import kit_css, render_html
from kataribe.timeline import build_timeline

SCENES = '<section data-scene="s1" class="kt-scene"><h2 class="kt-title">題</h2><div class="kt-body"><div class="kt-card" data-at="1">札</div></div></section>'


def _video_html(tmp_path) -> str:
    script = {
        "title": "部品の確認",
        "chapters": [
            {
                "id": "c1",
                "title": "章",
                "scenes": [{"id": "s1", "lines": [{"speaker": "四国めたん", "text": "一行目よ。"}, {"speaker": "ずんだもん", "text": "二行目なのだ。"}]}],
            }
        ],
    }
    (tmp_path / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "scenes.html").write_text(SCENES, encoding="utf-8")
    (tmp_path / "readings.json").write_text("{}", encoding="utf-8")
    project = load_project(tmp_path)
    return render_html(project, build_timeline(project, [1.0, 1.0]), b"")


def test_動画のHTMLは図の部品を画面より前に読み込む(tmp_path):
    page = _video_html(tmp_path)

    assert kit_css() in page
    assert page.index(kit_css()) < page.index('<section data-scene="s1"')


def test_動画のHTMLはキーの表を操作の処理より前に読み込む(tmp_path):
    page = _video_html(tmp_path)

    assert page.index("window.KataribeKeys") < page.index("KataribeKeys.decide(")


def test_キー一覧は既定で閉じている(tmp_path):
    page = _video_html(tmp_path)

    dialog = re.search(r"<dialog id=\"kataribe-keys\"[^>]*>", page)
    assert dialog is not None
    assert "open" not in dialog.group(0).removeprefix("<dialog")


def test_スライドの図のページにも同じ図の部品が入る():
    page = PAGE.format(title="題", w=1280, h=720, freeze="", scenes=SCENES)

    assert kit_css() in page
    assert page.index(kit_css()) < page.index('<section data-scene="s1"')


def _rules(css: str) -> list[str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [selector.strip() for selector in re.findall(r"([^{}]+)\{", css) if not selector.strip().startswith("@")]


def test_図の部品はステージの中のkt_で始まるクラスにだけ効く():
    for rule in _rules(kit_css()):
        for selector in rule.split(","):
            assert selector.strip().startswith("#kataribe-stage"), selector
        for name in re.findall(r"\.([\w-]+)", rule):
            assert name.startswith("kt-"), rule


def test_図の部品は出現と強調の規則が使う性質を指定しない():
    # 出現（visibility）と強調（outline・opacity）はプレーヤーが決め、verify は実時間で visibility を読む
    declared = re.findall(r"(?<![\w-])(visibility|opacity|outline|transition|animation)\s*:", kit_css())

    assert declared == []


def test_キー操作の一覧を開くボタンが常にあり撮影では消える():
    from kataribe.browser import FREEZE_CSS
    from kataribe.render import _asset

    page = _asset("page.html")
    assert '<button id="kataribe-keys-open"' in page
    assert 'aria-controls="kataribe-keys"' in page
    assert "#kataribe-keys-open { position: fixed; right: 16px; bottom: 16px;" in _asset("player.css")
    assert "#kataribe-keys-open { display: none !important; }" in FREEZE_CSS
