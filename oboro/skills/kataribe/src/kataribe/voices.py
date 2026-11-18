from kataribe.definitions import load_definitions

# 声のクレジット。台本で使えるのは、ここにあり、かつ立ち絵の定義もある話者（allowed_voices）。
VOICES: dict[str, str] = {
    "ずんだもん": "VOICEVOX:ずんだもん",
    "四国めたん": "VOICEVOX:四国めたん",
    "春日部つむぎ": "VOICEVOX:春日部つむぎ",
    "雨晴はう": "VOICEVOX:雨晴はう",
    "あんこもん": "VOICEVOX:あんこもん",
}

VOICEVOX_TERMS: tuple[tuple[str, str], ...] = (("VOICEVOX ソフトウェア利用規約", "https://voicevox.hiroshiba.jp/term/"),)

_ZUNKO_TERMS: tuple[tuple[str, str], ...] = (("東北ずん子・ずんだもんプロジェクト 音源利用規約", "https://zunko.jp/con_ongen_kiyaku.html"),)

# 声ごとの規約。VOICES の話者すべてに入れる（テストで確かめる）。
_VOICE_TERMS: dict[str, tuple[tuple[str, str], ...]] = {
    "ずんだもん": _ZUNKO_TERMS,
    "四国めたん": _ZUNKO_TERMS,
    "春日部つむぎ": (("VOICEVOX「春日部つむぎ」利用規約", "https://tsumugi-official.studio.site/rule"),),
    "雨晴はう": (("雨晴はう 公式サイト（利用規約あり）", "https://amehau.com/"),),
    "あんこもん": _ZUNKO_TERMS,
}


def allowed_voices() -> tuple[str, ...]:
    """台本で使える声。声と立ち絵の定義の両方がそろった話者だけ（VOICES の順）。"""
    defined = load_definitions()
    return tuple(voice for voice in VOICES if voice in defined)


def terms_links(voices: tuple[str, ...]) -> list[tuple[str, str]]:
    """共通の規約と、使った声の規約を、初めて出た順に重複なく並べる。"""
    links = list(VOICEVOX_TERMS)
    for voice in voices:
        for link in _VOICE_TERMS[voice]:
            if link not in links:
                links.append(link)
    return links
