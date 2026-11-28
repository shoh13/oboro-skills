import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from kataribe.config import kataribe_path


class BuildError(Exception):
    pass


def _install(stage: Path, out: Path) -> None:
    created_out = not out.exists()
    out.mkdir(exist_ok=True)
    backups = stage / ".backups"
    backups.mkdir()
    installed: list[tuple[Path, Path | None]] = []
    try:
        for item in sorted(stage.iterdir()):
            if item.name == ".backups":
                continue
            target = out / item.name
            backup = None
            if target.exists():
                backup = backups / item.name
                os.replace(target, backup)
            installed.append((target, backup))
            os.replace(item, target)
    except OSError:
        for target, backup in reversed(installed):
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
            if backup is not None and backup.exists():
                os.replace(backup, target)
        if created_out:
            shutil.rmtree(out, ignore_errors=True)
        raise


def out_dir(root: Path, out: Path | None = None) -> Path:
    """出力先。指定がなければ <project>/out。"""
    return root / "out" if out is None else out


def configured_out(root: Path) -> Path | None:
    """oboro の設定ファイルの kataribe.output_dir の下の出力先。設定がなければ None。

    フォルダ名は <プロジェクトのディレクトリ名>-<絶対パスの SHA-256 の先頭8文字>。名前の同じ別のプロジェクト（/a/demo と /b/demo）が、
    同じフォルダに解決されて互いの成果物を置き換えないようにする。
    """
    parent = kataribe_path("output_dir")
    if parent is None:
        return None
    project = root.resolve()
    return parent / f"{project.name}-{hashlib.sha256(str(project).encode()).hexdigest()[:8]}"


def default_out_note() -> str:
    """--out を付けないときの出力先（kataribe assets が出す）。"""
    parent = kataribe_path("output_dir")
    if parent is None:
        return "出力先の既定: <プロジェクト>/out"
    return f"出力先の既定: {parent}/<プロジェクトのディレクトリ名>-<パスから作る8文字>（oboro の設定ファイルの kataribe.output_dir）"


def build_hint(root: Path, out: Path | None = None, extras: bool = False) -> str:
    """出力を作り直すコマンド（エラーの案内用）。"""
    return f"kataribe build {root}" + (" --extras" if extras else "") + ("" if out is None else f" --out {out}")


def write_output(root: Path, write: Callable[[Path], None], out: Path | None = None) -> None:
    """一時ディレクトリに全部作ってから出力先（既定は out/）へ差し替える。途中で失敗したら出力先は前回のまま。"""
    target = out_dir(root, out)
    stage = None
    try:
        # 差し替えを os.replace で行うので、一時ディレクトリは出力先と同じディレクトリに作る
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".kataribe-out-", dir=target.parent))
        write(stage)
        _install(stage, target)
    except OSError as e:
        raise BuildError(f"出力を書き込めません: {e}") from None
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
