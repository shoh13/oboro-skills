# kataribe

台本（`script.json`）と画面（`scenes.html`）から、VOICEVOX のキャラクター2人（ずんだもんと四国めたんなど）の掛け合いの解説動画を作るプラグインです。字幕・シーン・章・立ち絵が、音声の実際の長さに合わせて切り替わる単一HTML（`out/video.html`）を出力します。MP4 も作れます。

音声は VOICEVOX（ずんだもん・四国めたん・春日部つむぎ・雨晴はう・あんこもん）で合成します。立ち絵は、話している人の表情と口パク、まばたきがあります。

## できること

- `out/video.html`: 単一HTMLの動画プレーヤー。再生・再生位置のシークバー（モバイル幅ではボタンがアイコンに替わる）・再生速度の切替（0.5〜2倍）・章バー・文字起こし・概要欄つき。2人の立ち絵が、行ごとに表情を変え、話している人の口が音声に合わせて動き、ときどきまばたきする。音声は AAC で埋め込み、16 MiB まで（立ち絵ありで約30分）。
- `out/transcript.md`: 文字起こし。
- `out/slides.pptx`（`slides`）: 音声なしの PowerPoint のスライド。地の文の解説に、2人が表情を変えながら、バラエティ番組のテロップのような大きな文字でコメントしていく。台本の1行が1枚。
- `out/extras/`（`build --extras`）: MP4化向けの音声、字幕（VTT）、タイムライン、利用条件。
- `out/frames/`（`shoot`）: シーンごとのスクリーンショット。
- `out/mp4/video.mp4`（`mp4`）: 画面と字幕を焼き込んだ MP4。
- 台本の検査（`lint`）と、再生の検証（`verify`。字幕・シーン・章・行単位の出現・進行変数・立ち絵の表情と口の7項目）。

## 必要なもの

| 用途 | 必要なもの |
| --- | --- |
| 共通 | [uv](https://docs.astral.sh/uv/)（Python 3.11 以上を使う） |
| 音声の合成（`build`） | Docker。VOICEVOX のエンジンを Docker で起動する（初回はイメージを取得する） |
| 立ち絵の素材（`build`） | ずんだもん・四国めたんは、初回だけネットワーク（配布元から取得してキャッシュする）。春日部つむぎ・雨晴はう・あんこもんは、初回だけ素材の zip を `~/Downloads` に置く（下の「立ち絵の素材」） |
| スクリーンショット・再生検証・MP4（`shoot`・`verify`・`mp4`） | Google Chrome。単一HTMLの音声は AAC なので、AAC を再生できない Playwright の Chromium では止まる |

`lint` と `slides` は音声を合成しないので、Docker は要りません。`lint` は Chrome も要りません。`slides` は、立ち絵の素材と、`scenes.html` に図があるときだけ Chrome を使います。MP4 の ffmpeg は `imageio-ffmpeg` が付けてくるため、別途入れる必要はありません。

## セットアップ

```sh
git clone <このリポジトリ>
cd kataribe
uv sync
```

Chrome がない環境では、Chromium も入れます（ただし、Playwright の Chromium は AAC を再生できないことがあり、そのときは `shoot`・`verify`・`mp4` が Chrome を入れるよう示して止まります）。

```sh
uv run playwright install chromium
```

### Claude Code に入れる

このリポジトリは、Claude Code のプラグインとマーケットプレイスを兼ねています（`.claude-plugin/`）。入れると、解説動画の `video` スキル（`/kataribe:video`）と、スライドの `slides` スキル（`/kataribe:slides`）が使えます。

```sh
claude plugin marketplace add oboro-yudachi/kataribe   # 手元のチェックアウトのパスでもよい
claude plugin install kataribe@kataribe
```

リポジトリを更新したあとは、`claude plugin marketplace update kataribe` と `claude plugin update kataribe@kataribe` で取り込みます。リポジトリは非公開なので、GitHub から入れるには、そのマシンの git がリポジトリにアクセスできる必要があります。

## プロジェクトの形

動画を作るプロジェクトのディレクトリに、次の3つのファイルを置きます。

```
<project>/script.json    台本
<project>/scenes.html    画面（シーンごとの <section data-scene="シーンID">）
<project>/readings.json  読みの辞書（必須。使わなければ {} と書く）
```

`script.json` の例:

```json
{
  "title": "動画のタイトル",
  "description": "概要欄に出す説明（任意）",
  "sources": [{"title": "出典のタイトル", "url": "https://example.com/"}],
  "chapters": [
    {"id": "c1", "title": "章のタイトル", "scenes": [
      {"id": "s1", "lines": [
        {"speaker": "四国めたん", "text": "1文ずつ書く"},
        {"speaker": "ずんだもん", "expression": "smile", "text": "話者は行ごとに決める"}
      ]}
    ]}
  ]
}
```

各行の `speaker`（必須）は `ずんだもん`、`四国めたん`、`春日部つむぎ`、`雨晴はう`、`あんこもん` のどれかです。1本の動画で使える話者は2人までです。立ち位置は、四国めたん・春日部つむぎ・雨晴はうが左、ずんだもん・あんこもんが右で、2人が同じ側になるときは、台本で後から出た人を反対側に置きます。`expression`（任意）は表情で、省略すると既定の `normal` になります。表情は `normal`、`smile`、`surprised`、`troubled`、`jito`、`panic`、`think`、`angry`、`cry` の9種です。立ち絵は、話している人がその行の表情、話していない人は最後に話した行の表情で表示されます。話している人の口は、音声の大きさに合わせて開閉します。立ち絵は、4秒に1回ほど、まばたきします（閉じ目のない表情ではしません）。

`scenes.html` の `<section data-scene="s1">` が、台本の `scenes[].id` に対応します。

```html
<section data-scene="s1">
  <h1>見出し</h1>
  <p data-at="1">行1のときに出る文</p>
</section>
```

画像ファイルは `<img src="figures/a.png">` のように、プロジェクトからの相対パスで書けます（`build` と `slides` が埋め込みます）。行単位の出現・消去・強調（`data-at`・`data-out`・`data-focus`）と、進行変数（CSS 変数 `--p`・`--lp`）の詳しい書き方は [`skills/video/SKILL.md`](skills/video/SKILL.md) を見てください。

## 使い方

以下のコマンドは、どのディレクトリからでも実行できます。`<プラグイン>` はこのリポジトリのルートです。

```sh
uv run --project <プラグイン> kataribe <コマンド> <project>
```

`build`・`slides`・`shoot`・`verify`・`mp4` は、`--out <ディレクトリ>` で出力先を変えられます（既定は `<project>/out`。下の表の `out/` はこの出力先です）。`build` で `--out` を付けたら、`shoot`・`verify`・`mp4` にも同じ `--out` を付けます。

| コマンド | 内容 |
| --- | --- |
| `build <project>` | 音声を合成して `out/video.html` と `out/transcript.md` を作る。`--extras` を付けると副産物も作る |
| `lint <project> [--slides]` | 台本と画面を検査する。音声は合成しない。`--slides` はスライドの台本として検査する |
| `slides <project>` | 地の文とコメントで進む PowerPoint のスライド `out/slides.pptx` を作る。音声は合成しない |
| `shoot <project> [--at start\|mid\|end]` | 各シーンのスクリーンショットを `out/frames/` に撮る（先に `build`） |
| `verify <project>` | `out/video.html` を実時間で再生し、7項目（字幕・シーン・章・行単位の出現・進行変数・立ち絵の表情と口など）を検証する（先に `build`） |
| `mp4 <project> [--size 1280x720\|1920x1080] [--fps 24\|30\|60]` | `out/mp4/video.mp4` を作る（先に `build --extras`） |

典型的な流れ:

```sh
uv run --project <プラグイン> kataribe lint <project>
uv run --project <プラグイン> kataribe build <project>
open <project>/out/video.html
```

MP4 まで作るときは、`build --extras` で副産物を作ってから `mp4` を実行します。

```sh
uv run --project <プラグイン> kataribe build <project> --extras
uv run --project <プラグイン> kataribe mp4 <project>
```

`build` が失敗したときは、前回の `out/` をそのまま残します。`out/` は、全部作り終えてから置き換えます。`out/video.html` が16 MiBを超えるときも、`build` は失敗します。

## スライド

`speaker` を書かない行が地の文（解説）になり、`speaker` のある行がキャラクターのコメントになります。台本の1行が1枚のスライドで、同じシーンのスライドは地の文が積み上がっていきます。シーンの `title` が見出しです。`**…**` で強調できます。`readings.json` は要りません。`scenes.html` は任意で、シーンの `section` があれば、動画と同じ図をその行の状態で撮ってスライドに置きます（図があるときは Chrome を使います）。

```json
{"id": "s1", "title": "スライドの見出し", "lines": [
  {"text": "地の文。解説はここに書く。"},
  {"speaker": "ずんだもん", "expression": "surprised", "text": "コメントはテロップで大きく出るのだ"}
]}
```

```sh
uv run --project <プラグイン> kataribe lint <project> --slides
uv run --project <プラグイン> kataribe slides <project>
open <project>/out/slides.pptx
```

詳しい規則は [`skills/slides/SKILL.md`](skills/slides/SKILL.md) を見てください。

## 設定（環境変数）

| 変数 | 内容 |
| --- | --- |
| `KATARIBE_TTS_CMD` | TTS アダプターのコマンドを差し替える。テキストを stdin で受け取り、`--voice`、`--speed`、`--output`（WAV）を受け付ける |
| `KATARIBE_VOICEVOX_URL` | Docker を使わず、起動済みの VOICEVOX エンジンの URL（例: `http://127.0.0.1:50021`）を使う |
| `KATARIBE_FFMPEG` | ffmpeg の実行ファイルを差し替える |
| `KATARIBE_CHAR_CACHE` | 立ち絵素材のキャッシュの場所を差し替える（既定は `~/.cache/kataribe/characters`） |
| `KATARIBE_CHAR_SOURCES` | 手元に落とす立ち絵素材の zip を探す場所を差し替える（既定は `~/Downloads`） |
| `KATARIBE_SLIDES_FONT` | スライドのフォントを差し替える（既定は Google スライドで使える `Noto Sans JP`） |
| `KATARIBE_CHAR_DEFS` | 立ち絵の定義のディレクトリを差し替える（開発・テスト用） |

## 利用条件

音声を配るときは、`out/extras/TERMS.txt`（`build --extras` で作られる）を必ず添えてください。声のクレジットと、次の利用規約へのリンクを載せています。キャラクターの規約は、使った声のぶんだけ載せます。

- VOICEVOX ソフトウェア利用規約
- 東北ずん子・ずんだもんプロジェクト 音源利用規約（ずんだもん・四国めたん・あんこもん）
- VOICEVOX「春日部つむぎ」利用規約（春日部つむぎ）
- 雨晴はう 公式サイト（雨晴はう）

### 立ち絵の素材

| 話者 | 素材 | 取り方 |
| --- | --- | --- |
| ずんだもん・四国めたん | 坂本アヒル氏の立ち絵素材 | `build` が配布元から取得する |
| 春日部つむぎ | 春日部つむぎ公式立ち絵素材 v2.0（春日部つくし氏） | [公式サイト](https://tsukushinyoki10.wixsite.com/ktsumugiofficial)から `春日部つむぎ立ち絵_公式_v2.0.zip` を落とす |
| 雨晴はう | 雨晴はう公式立ち絵 v2.0 | [公式サイト](https://amehau.com/)の案内から `雨晴はう_公式立ち絵_v2.0.zip` を落とす |
| あんこもん | 坂本アヒル氏のあんこもん立ち絵素材 | [配布元](https://uu.getuploader.com/s_ahiru/download/71)から `あんこもん立ち絵素材.zip` を落とす（パスワードは作者の告知を見る） |

手元に落とす素材は、zip の名前のまま `~/Downloads`（`KATARIBE_CHAR_SOURCES` で変えられる）に置きます。`build` は、MD5 で同じ版かを確かめてから使い、キャッシュに写します。一度キャッシュに入れば、zip は消して構いません。

`build` は素材をリポジトリの外のキャッシュに置きます。素材の再配布は許されていないので、素材と書き出した画像は git にも共有用の zip にも入れません。立ち絵を含む動画の利用は、非商用に限ります（[東北ずん子・ずんだもんプロジェクト キャラクターガイドライン](https://zunko.jp/guideline.html)、春日部つむぎ・雨晴はうは各素材の利用規約）。

## 開発

```sh
uv run pytest                      # 全部
uv run pytest -m "not integration" # Docker の VOICEVOX を使うテストを飛ばす
```

`integration` マーカーのテストは、実際の VOICEVOX（Docker）を使います。Docker が使えないときは自動で飛ばされます。立ち絵は、テストではネットワークから取得せず、テスト用の小さな素材（`tests/fake_art.py`）を使います。

- `src/kataribe/`: 本体。`cli.py` がコマンドの入口です。
- `src/kataribe/adapters/voicevox.py`: 既定の TTS アダプター（VOICEVOX）。
- `src/kataribe/art.py`: 立ち絵の素材の取得・検証・キャッシュ・レイヤーの書き出し。
- `src/kataribe/characters/`: 立ち絵の定義（話者ごとの表情とレイヤーの選び方）。
- `src/kataribe/mouth.py`: 音声の音量から口パクの段階を計算する。
- `src/kataribe/player/`: 単一HTMLのプレーヤー（HTML・CSS・JS）。`cast.js` は立ち絵の表情・口・まばたきを決める純粋な関数。
- `src/kataribe/slides.py`: スライド（`slides`）の PowerPoint の組み立て（python-pptx）。`diagrams.py` は図を撮る、`images.py` は `scenes.html` の画像を埋め込む。
- `skills/video/SKILL.md`・`skills/slides/SKILL.md`: このプラグインを使う Claude Code スキル（動画・スライド）の仕様。振る舞いの正本です。
- `tests/`: テスト。

## ライセンス

`.claude-plugin/plugin.json` のとおり、現在は `UNLICENSED`（ライセンスを定めていません）です。

## Notion への同期

`skills/video/SKILL.md`（kataribe）と `skills/slides/SKILL.md`（kataribe-slides）を、それぞれ実行に要るファイルと一緒に、Notion の `[DB]スキル v2` の同じ名前のページへ同期します。正本は Git で、Notion へは一方向に上書きします。Notion 側では編集しません。

同期には [notion-skill-sync](https://github.com/oboro-yudachi/notion-skill-sync) プラグインを使います。

- `notion-skill.json`: 同期の設定。`skills` に、同期するスキルを1つずつ書く。各スキルには、同期先のページ、Notion でのスキル名（`kataribe`、`kataribe-slides`）、ルートに置く SKILL.md（`skill_md`）、その横に並べるもの（`include`）を書く。`include` は `uv run --project` で動かすのに要るものだけにする（`tests/` は入れない）。ディレクトリは `/` で終える。書き方の詳細は notion-skill-sync の README を見る。
- 同期の手順: main にマージしたあと、Claude Code で `/notion-skill-sync:sync` を実行する。プラグインは次で入れる。

  ```sh
  claude plugin marketplace add oboro-yudachi/notion-skill-sync
  claude plugin install notion-skill-sync@notion-skill-sync
  ```

## 同梱している第三者の素材

- プレーヤーの操作ボタンのアイコン: [Lucide](https://lucide.dev)（ISC License）。Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2022. SVG と LICENSE は `src/kataribe/player/icons/` にあり、ビルド時に `video.html` へ埋め込む（同じ表記は HTML コメントにも残る）。アイコンを足すときは、そのフォルダに SVG を置き、`page.html` に `{{ICON:名前}}` と書く。
