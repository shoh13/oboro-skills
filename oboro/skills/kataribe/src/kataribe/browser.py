# 撮影（shoot と mp4）のときだけ、ブラウザのページに足す。単一HTMLには入れない。
# transition は即座に最終の見た目に、animation は時間0・遅延なし・1回・終了状態を保持で最終の見た目に飛ばす。
FREEZE_CSS = """
*, *::before, *::after {
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  animation-iteration-count: 1 !important;
  animation-fill-mode: forwards !important;
}
"""


class BrowserError(Exception):
    pass


# Playwright が、実行ファイルがないときに返すエラーの文言
NOT_INSTALLED = ("is not found at", "Executable doesn't exist")


def _launch_failure(error: Exception, install: str) -> str:
    """起動の失敗を、未導入（入れれば直る）と起動の失敗（入っているが起動を拒否された、など）に分けて説明する。"""
    message = str(error)
    if any(phrase in message for phrase in NOT_INSTALLED):
        return f"未導入です。{install}"
    lines = message.splitlines()
    # 先頭行は一般的な文のことが多く、拒否の理由はブラウザの標準エラー（[err]）の行に出る
    reasons = lines[:1] + [line.strip() for line in lines[1:] if "[err]" in line][:1]
    return f"入っていますが、起動を拒否されたか、起動に失敗しました: {' / '.join(reasons)}"


def launch(playwright):
    from playwright.sync_api import Error

    try:
        return playwright.chromium.launch(channel="chrome", headless=True)
    except Error as e:
        chrome_error = e
    try:
        return playwright.chromium.launch(headless=True)
    except Error as chromium_error:
        raise BrowserError(
            "ブラウザを起動できません。\n"
            f"  Google Chrome: {_launch_failure(chrome_error, 'Google Chrome を入れてください。')}\n"
            f"  Playwright Chromium: {_launch_failure(chromium_error, '`playwright install chromium` で入れられます（AAC を再生できないことがあるので、Google Chrome を勧めます）。')}"
        ) from None


def require_aac(page) -> None:
    """単一HTMLの音声は AAC。AAC を再生できないブラウザ（Playwright の Chromium など）では、撮影も検証もできないので止める。"""
    playable = page.evaluate("document.createElement('audio').canPlayType('audio/mp4; codecs=\"mp4a.40.2\"')")
    if not playable:
        raise BrowserError(
            "このブラウザは単一HTMLの音声（AAC）を再生できません。Google Chrome を入れてください"
            "（Playwright の Chromium は AAC を再生できないことがあります）"
        )
