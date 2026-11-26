import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from conftest import SCRIPT, make_project, run_build, run_verify
from test_appearance import SCRIPT_4

SCENES_WITH_TIMED = """\
<section data-scene="s1">
  <p data-at="1">1行目から</p>
  <p data-out="2">2行目で消える</p>
  <div data-focus="0,3">強調</div>
</section>
<section data-scene="s2"><p data-at="0">別のシーン</p></section>
"""


@pytest.fixture
def timed_project(tmp_path):
    project = make_project(tmp_path / "p", script=SCRIPT_4, scenes=SCENES_WITH_TIMED)
    assert run_build(project).returncode == 0
    return project


RUNNER = """
import json, sys
from pathlib import Path
from kataribe.verify import verify
result = verify(Path(sys.argv[1]), end_margin=float(sys.argv[2]))
print(json.dumps([[c.number, c.problems] for c in result.checks]))
"""


def results(project, end_margin=10.0):
    # セッション共有の同期Playwrightと衝突するので、別プロセスで verify() を呼ぶ
    out = subprocess.run([sys.executable, "-c", RUNNER, str(project), str(end_margin)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return {number: SimpleNamespace(ok=not problems, problems=problems) for number, problems in json.loads(out.stdout)}


def tamper(project, old, new):
    html = project / "out" / "video.html"
    text = html.read_text(encoding="utf-8")
    assert old in text, old
    html.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_正常な動画では_7項目すべてOKで_終了コードは0(timed_project):
    result = run_verify(timed_project)

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 7
    assert lines[0].startswith("① 再生が最後まで進む: OK")
    assert all(line.endswith(": OK") for line in lines)
    assert [line[0] for line in lines] == list("①②③④⑤⑥⑦")


def test_壊れた動画では_該当の項目だけNGで_終了コードは1(timed_project):
    tamper(timed_project, 'section.dataset.scene === line.scene)', 'section.dataset.scene === timeline.lines[0].scene)')

    result = run_verify(timed_project)

    assert result.returncode == 1
    status = {line[0]: line.rsplit(": ", 1)[1] for line in result.stdout.splitlines() if line[0] in "①②③④⑤⑥⑦"}
    assert status == {"①": "OK", "②": "NG", "③": "OK", "④": "OK", "⑤": "OK", "⑥": "OK", "⑦": "OK"}
    assert "表示されたシーンの順" in result.stdout


@pytest.mark.parametrize(
    "old, new, broken",
    [
        ("item.el.removeAttribute(\"data-kataribe-state\");", "item.el.setAttribute(\"data-kataribe-state\", \"hidden\");", 5),
        ("String(sceneProgress)", "String(1 - sceneProgress)", 6),
        ("captionEl.textContent = captionsOn ? line.text : \"\";", "captionEl.textContent = captionsOn ? line.text + '!' : \"\";", 3),
    ],
)
def test_動画のJSを壊すと_その項目だけがNGになる(timed_project, old, new, broken):
    tamper(timed_project, old, new)

    got = results(timed_project)

    assert [n for n, check in got.items() if not check.ok] == [broken]


def test_再生が最後まで進まない動画では_1がNGになる(timed_project):
    tamper(timed_project, 'playLabel.textContent = "一時停止";', 'playLabel.textContent = "一時停止"; setTimeout(() => audio.pause(), 150);')

    got = results(timed_project, end_margin=0.5)

    assert not got[1].ok
    assert got[4].ok


def test_台本の行を増やすと_文字起こしの数が合わず_4がNGになる(timed_project):
    script = json.loads((timed_project / "script.json").read_text(encoding="utf-8"))
    script["chapters"][0]["scenes"][0]["lines"].append({"speaker": "ずんだもん", "text": "ああ"})
    (timed_project / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    got = results(timed_project)

    assert not got[4].ok
    assert "文字起こし" in got[4].problems[0]


def test_buildしていないときは_先にbuildするよう示して失敗する(tmp_path):
    project = make_project(tmp_path / "p")

    result = run_verify(project)

    assert result.returncode == 1
    assert "build" in result.stderr
    assert "Traceback" not in result.stderr


def test_台本が不正なときは_lintと同じエラーで失敗する(timed_project):
    (timed_project / "script.json").write_text("{壊れたJSON", encoding="utf-8")

    result = run_verify(timed_project)

    assert result.returncode == 1
    assert "script.json" in result.stderr
    assert "Traceback" not in result.stderr


def test_検証できない行の警告は_標準エラーに出し_失敗にしない(timed_project, monkeypatch, capsys):
    from kataribe import cli
    from kataribe.verify import Check, VerifyResult

    monkeypatch.setattr(cli, "verify", lambda root, out=None: VerifyResult([Check(n) for n in range(1, 7)], ["行 s1-0 は、検証できませんでした"]))

    code = cli.main(["verify", str(timed_project)])

    out = capsys.readouterr()
    assert code == 0
    assert "s1-0" in out.err
    assert "s1-0" not in out.out


DIALOGUE = {
    "title": "掛け合い",
    "chapters": [
        {
            "id": "c1",
            "title": "章",
            "scenes": [
                {
                    "id": "s1",
                    "lines": [
                        {"speaker": "四国めたん", "text": "はじめるわね"},
                        {"speaker": "ずんだもん", "expression": "smile", "text": "たのしみなのだ"},
                        {"speaker": "四国めたん", "expression": "angry", "text": "まじめにやるわよ"},
                    ],
                }
            ],
        }
    ],
}


@pytest.fixture
def dialogue_project(tmp_path):
    """表情を変え、音（440Hz）のある掛け合い。話している人の口が開く。"""
    project = make_project(tmp_path / "dialogue", script=DIALOGUE, scenes='<section data-scene="s1"><h1>掛け合い</h1></section>\n')
    result = run_build(project, extra_env={"FAKE_TTS_TONE": "1", "FAKE_TTS_SECONDS_PER_CHAR": "0.1"})
    assert result.returncode == 0, result.stderr
    return project


def test_掛け合いの動画は_立ち絵の表情と口も含めて7項目すべてOK(dialogue_project):
    got = results(dialogue_project)

    assert [n for n, check in got.items() if not check.ok] == [], {n: c.problems for n, c in got.items()}


@pytest.mark.parametrize(
    "old, new",
    [
        ("c.canvas.dataset.face = face;", 'c.canvas.dataset.face = "normal";'),
        ("c.canvas.dataset.mouth = String(mouth);", 'c.canvas.dataset.mouth = "0";'),
    ],
    ids=["face", "mouth"],
)
def test_立ち絵の表情や口を壊すと_7だけがNGになる(dialogue_project, old, new):
    tamper(dialogue_project, old, new)

    got = results(dialogue_project)

    assert [n for n, check in got.items() if not check.ok] == [7]
