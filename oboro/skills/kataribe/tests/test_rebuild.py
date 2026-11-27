import json
import sys

import pytest
from conftest import FAKE_TTS, make_project, run_build, run_lint

STALE = "前回の out/ は古いままです"


def snapshot(project):
    out = project / "out"
    return {str(p.relative_to(out)): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}


def break_script(project):
    path = project / "script.json"
    script = json.loads(path.read_text(encoding="utf-8"))
    script["chapters"][0]["scenes"][0]["lines"][0].pop("speaker")
    path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")


def leftovers(project):
    return [p.name for p in project.iterdir() if p.name.startswith(".kataribe")]


def test_TTSが失敗した再ビルドは_前回のoutを変えず_古いと警告して失敗する(project):
    assert run_build(project, args=["--extras"]).returncode == 0
    before = snapshot(project)

    result = run_build(project, tts_cmd="/nonexistent/kataribe-tts")

    assert result.returncode == 1
    assert STALE in result.stderr
    assert snapshot(project) == before
    assert leftovers(project) == []


def test_検査で失敗した再ビルドも_前回のoutを変えず_古いと警告する(project):
    assert run_build(project).returncode == 0
    before = snapshot(project)
    break_script(project)

    result = run_build(project)

    assert result.returncode == 1
    assert "speaker" in result.stderr
    assert STALE in result.stderr
    assert snapshot(project) == before


def test_初回のビルドの失敗では_outを作らず_警告も出ない(project):
    result = run_build(project, tts_cmd="/nonexistent/kataribe-tts")

    assert result.returncode == 1
    assert STALE not in result.stderr
    assert not (project / "out").exists()
    assert leftovers(project) == []


def test_lintの失敗では_前回のoutがあっても警告を出さない(project):
    assert run_build(project).returncode == 0
    break_script(project)

    result = run_lint(project)

    assert result.returncode == 1
    assert STALE not in result.stderr


def test_extrasなしの再ビルドは_前回のextras_mp4_framesに触らない(project):
    assert run_build(project, args=["--extras"]).returncode == 0
    for name in ("mp4", "frames"):
        (project / "out" / name).mkdir()
        (project / "out" / name / "keep.txt").write_text(name, encoding="utf-8")
    kept = {k: v for k, v in snapshot(project).items() if k.split("/")[0] in ("extras", "mp4", "frames")}

    assert run_build(project).returncode == 0

    after = snapshot(project)
    assert {k: v for k, v in after.items() if k in kept} == kept


def test_成功した再ビルドは_video_htmlとtranscriptを新しい内容にする(project):
    assert run_build(project).returncode == 0
    script = json.loads((project / "script.json").read_text(encoding="utf-8"))
    script["title"] = "新しい題名"
    (project / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    assert run_build(project, args=["--extras"]).returncode == 0

    assert "新しい題名" in (project / "out" / "video.html").read_text(encoding="utf-8")
    assert "新しい題名" in (project / "out" / "transcript.md").read_text(encoding="utf-8")
    assert json.loads((project / "out" / "extras" / "timeline.json").read_text(encoding="utf-8"))["title"] == "新しい題名"
    assert leftovers(project) == []


@pytest.fixture
def fake_tts(monkeypatch):
    monkeypatch.setenv("KATARIBE_TTS_CMD", f"{sys.executable} {FAKE_TTS}")
    monkeypatch.setenv("KATARIBE_TTS_CACHE", "off")


def test_書き込みの差し替え中に失敗しても_outは前回のままで_一時ファイルが残らない(project, fake_tts, monkeypatch):
    from kataribe import cli, output

    cli.build(project, extras=True)
    before = snapshot(project)
    script = json.loads((project / "script.json").read_text(encoding="utf-8"))
    script["title"] = "新しい題名"
    (project / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    real, calls = output.os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 4:
            raise OSError("ディスクがいっぱいです")
        return real(src, dst)

    monkeypatch.setattr(output.os, "replace", flaky)

    with pytest.raises(output.BuildError, match="ディスクがいっぱい"):
        cli.build(project, extras=True)

    monkeypatch.undo()
    assert snapshot(project) == before
    assert leftovers(project) == []


def test_最初のビルドの差し替え中に失敗したら_outを作らない(project, fake_tts, monkeypatch):
    from kataribe import cli, output

    real, calls = output.os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("ディスクがいっぱいです")
        return real(src, dst)

    monkeypatch.setattr(output.os, "replace", flaky)

    with pytest.raises(output.BuildError):
        cli.build(project)

    monkeypatch.undo()
    assert not (project / "out").exists()
    assert leftovers(project) == []


def test_副産物の書き込みで失敗したら_outは前回のまま(project, fake_tts, monkeypatch):
    from kataribe import cli

    cli.build(project, extras=True)
    before = snapshot(project)
    script = json.loads((project / "script.json").read_text(encoding="utf-8"))
    script["title"] = "新しい題名"
    (project / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("書けません")

    monkeypatch.setattr(cli, "write_extras", boom)

    with pytest.raises(Exception, match="書けません"):
        cli.build(project, extras=True)

    monkeypatch.undo()
    assert snapshot(project) == before
    assert leftovers(project) == []


def test_outを指定したビルドは_そのディレクトリに出力し_プロジェクトのoutは作らない(project, tmp_path):
    out = tmp_path / "成果物" / "動画"

    result = run_build(project, args=["--out", str(out)])

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in out.iterdir()) == ["transcript.md", "video.html"]
    assert not (project / "out").exists()
    assert leftovers(out.parent) == []
