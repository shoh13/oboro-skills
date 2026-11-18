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


def launch(playwright):
    from playwright.sync_api import Error

    try:
        return playwright.chromium.launch(channel="chrome", headless=True)
    except Error:
        pass
    try:
        return playwright.chromium.launch(headless=True)
    except Error as e:
        raise BrowserError(
            "ブラウザを起動できません。Google Chrome を入れるか、`playwright install chromium` を実行してください: "
            f"{str(e).splitlines()[0]}"
        ) from None


def require_aac(page) -> None:
    """単一HTMLの音声は AAC。AAC を再生できないブラウザ（Playwright の Chromium など）では、撮影も検証もできないので止める。"""
    playable = page.evaluate("document.createElement('audio').canPlayType('audio/mp4; codecs=\"mp4a.40.2\"')")
    if not playable:
        raise BrowserError(
            "このブラウザは単一HTMLの音声（AAC）を再生できません。Google Chrome を入れてください"
            "（Playwright の Chromium は AAC を再生できないことがあります）"
        )
