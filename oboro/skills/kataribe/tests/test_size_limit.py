from conftest import SCENES, make_project, run_build

LIMIT = 16 * 1024 * 1024
STALE = "前回の out/ は古いままです"


def pad_scenes(project, size):
    (project / "scenes.html").write_text(SCENES + f"<!--{'x' * (size - 7)}-->", encoding="utf-8")


def html_size(project):
    return (project / "out" / "video.html").stat().st_size


def padding_to(project, target):
    """video.html がちょうど target バイトになる、scenes.html に足す詰め物の長さ。"""
    assert run_build(project).returncode == 0
    return target - html_size(project)


def test_単一HTMLがちょうど16MiBなら_buildは成功する(tmp_path):
    project = make_project(tmp_path / "p")
    pad_scenes(project, padding_to(project, LIMIT))

    result = run_build(project)

    assert result.returncode == 0, result.stderr
    assert html_size(project) == LIMIT


def test_16MiBを1バイトでも超えたら_buildは失敗し_前回のoutを残す(tmp_path):
    project = make_project(tmp_path / "p")
    padding = padding_to(project, LIMIT + 1)
    before = (project / "out" / "video.html").read_bytes()
    pad_scenes(project, padding)

    result = run_build(project)

    assert result.returncode == 1
    assert "16,777,217 バイト" in result.stderr
    assert "上限 16,777,216 バイト" in result.stderr
    assert STALE in result.stderr
    assert (project / "out" / "video.html").read_bytes() == before
    assert [p.name for p in project.iterdir() if p.name.startswith(".kataribe")] == []


def test_初回のbuildで16MiBを超えたら_outを作らない(tmp_path):
    project = make_project(tmp_path / "p")
    pad_scenes(project, LIMIT)

    result = run_build(project)

    assert result.returncode == 1
    assert "上限 16,777,216 バイト" in result.stderr
    assert STALE not in result.stderr
    assert not (project / "out").exists()
