"""ブラウザの起動の失敗を、未導入と起動の拒否に分けて示す（shoot・verify・mp4 共通）。"""

from types import SimpleNamespace

import pytest
from playwright.sync_api import Error

from kataribe.browser import BrowserError, launch

CHROME_MISSING = "BrowserType.launch: Chromium distribution 'chrome' is not found at /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\nRun \"playwright install chrome\""
CHROMIUM_MISSING = "BrowserType.launch: Executable doesn't exist at /cache/chrome-headless-shell\nLooks like Playwright was just installed"
DENIED = "BrowserType.launch: Target page, context or browser has been closed\nBrowser logs:\n<launching> /Applications/Google Chrome\n[pid=1][err] sandbox_init: Operation not permitted\n[pid=1][err] second"


def fake_playwright(chrome, chromium):
    def start(channel=None, headless=True):
        outcome = chrome if channel == "chrome" else chromium
        if isinstance(outcome, str):
            raise Error(outcome)
        return outcome  # 起動できたブラウザの代わり

    return SimpleNamespace(chromium=SimpleNamespace(launch=start))


def failure(chrome: str, chromium: str) -> str:
    with pytest.raises(BrowserError) as caught:
        launch(fake_playwright(chrome, chromium))
    return str(caught.value)


def test_どちらも未導入なら_未導入と入れ方を示す():
    message = failure(CHROME_MISSING, CHROMIUM_MISSING)

    assert "Google Chrome: 未導入" in message
    assert "Playwright Chromium: 未導入" in message
    assert "playwright install chromium" in message


def test_Chrome_の起動の拒否は未導入と区別し_理由を示す():
    message = failure(DENIED, CHROMIUM_MISSING)

    assert "Google Chrome: 入っていますが、起動を拒否されたか、起動に失敗しました" in message
    assert "sandbox_init: Operation not permitted" in message
    assert "second" not in message
    assert "Playwright Chromium: 未導入" in message


def test_Chromium_の起動の拒否も区別する():
    assert "Playwright Chromium: 入っていますが" in failure(CHROME_MISSING, DENIED)


def test_Chrome_が使えれば_それを使う():
    chrome = object()

    assert launch(fake_playwright(chrome, CHROMIUM_MISSING)) is chrome


def test_Chrome_が使えなければ_Chromium_に切り替える():
    chromium = object()

    assert launch(fake_playwright(CHROME_MISSING, chromium)) is chromium
