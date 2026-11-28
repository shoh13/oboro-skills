---
name: setup-oboro
description: "この端末での oboro の環境設定（org-roam のノートの置き場、capture テンプレートの正本、個人の ADR の置き場、kataribe の立ち絵の素材と成果物の置き場など）を調べ、ユーザーに確かめてから、リポジトリの外の設定ファイルに書く。秘密の値は書かない。「oboro の設定をして」「/setup-oboro」で使う。"
disable-model-invocation: true
---

# setup-oboro

oboro のスキルのうち、端末ごとに違う値を使うものは、この設定ファイルを読む。今は org-file-conventions が `[org]`、artifact-destination と adr-recorder が `[destination]`、kataribe と kataribe-slides が `[kataribe]` を使う。

## 設定ファイル

- **場所。** `~/.config/oboro/config.toml`。環境変数 `OBORO_CONFIG` があれば、そのパス。`printenv OBORO_CONFIG` をこのまま実行して確かめる（変数展開を含むコマンドは Claude Code が事前に検査できない）。`OBORO_CONFIG` は、別の場所に置くときや試験のときだけ使う。
- **形式。** TOML。キーは下の表のものだけ。パスと名前だけを書き、トークン、パスワード、API キーなどの秘密の値は書かない。`~` は読む側がホームに展開する。
- **説明。** 各キーの直前の行に、表の「意味」と「使うスキル」を `# 意味。使うスキル: 名前` の形の TOML のコメントで書く。説明を値（`description` のキーなど）として持たないのは、読む側がキーの値を文字列として読めなくなり、表にないキーの確認にもかかるため。
- **dotfiles での管理。** このファイルを dotfiles に置き、home-manager なら `xdg.configFile."oboro/config.toml".source` で置ける。

| キー | 意味 | 使うスキル | 例 |
| --- | --- | --- | --- |
| `org.dir` | org-roam のノートの置き場（`org-roam-directory`） | org-file-conventions | `"~/repo/05_org"` |
| `org.memo_dir` | 手でタイトルを入れて作るメモの置き場 | org-file-conventions | `"~/repo/05_org/roam"` |
| `org.capture_config` | capture テンプレートを定義しているファイル | org-file-conventions | `"~/dotfiles/home-manager/doom.d/config.org"` |
| `org.memo_template` | `org-capture-templates` の、手でタイトルを入れて作るメモのキー | org-file-conventions | `"m"` |
| `org.node_template` | `org-roam-capture-templates` の、ノード検索から作るときのキー | org-file-conventions | `"d"` |
| `org.shell_init` | org-babel の shell ブロックで `source` するファイル（非対話シェルで PATH を通すため） | org-file-conventions | `["~/.local/share/google-cloud-sdk/path.zsh.inc"]` |
| `destination.adr_dir` | 個人の ADR（1つの Repo のコードに閉じない設計判断）の置き場。指示ファイルやルールのページが保存先を決めていないときだけ使う | artifact-destination、adr-recorder | `"~/notes/adr"` |
| `kataribe.char_sources` | 立ち絵の素材の zip の置き場。環境変数 `KATARIBE_CHAR_SOURCES` があれば、そちらを使う | kataribe、kataribe-slides | `"~/Documents/kataribe-assets"` |
| `kataribe.output_dir` | 成果物（動画、スライドなど）の置き場。この下の `<プロジェクトのディレクトリ名>-<パスから作る8文字>` に出す。コマンドの `--out` があれば、そちらを使う | kataribe、kataribe-slides | `"~/Movies/kataribe"` |

書いたファイルの冒頭は次の形になる。

```toml
# setup-oboro が書く。秘密の値は書かない。

[org]
# org-roam のノートの置き場（org-roam-directory）。使うスキル: org-file-conventions
dir = "~/repo/05_org"
# 手でタイトルを入れて作るメモの置き場。使うスキル: org-file-conventions
memo_dir = "~/repo/05_org/roam"
```

## 手順

1. 設定ファイルのパスを確かめ、あれば読む。ある値は今の値として扱う。
2. 足りない値を、この端末から調べる。推測で書かず、見つけた根拠（ファイルと行）を添えて候補にする。
   - `org.dir`：Emacs の設定（`config.org`、`config.el`、`init.el` など）の `org-roam-directory` と `org-directory`。
   - `org.capture_config`：`org-capture-templates` を定義しているファイル。
   - `org.memo_template`・`org.node_template`：そのファイルにあるテンプレートのキーと説明。
   - `org.memo_dir`：メモのテンプレートがファイルを作る先。
   - `org.shell_init`：`.zshrc` などでだけ PATH を通しているコマンドの初期化ファイル（gcloud の `path.zsh.inc` など）。
   - `destination.adr_dir`：個人の ADR をすでに置いているディレクトリ（Repo の `docs/adr/` ではないもの）をユーザーに尋ね、中の ADR のファイルを根拠にする。ディレクトリは作らない。指示ファイルやそれが参照するルールのページが保存先を決めている端末では、そちらが先に使われ、この値は使われないと添える。
   - `kataribe.char_sources`：立ち絵の素材の zip（kataribe の README の「立ち絵の素材」の名前）を置いているディレクトリ。`printenv KATARIBE_CHAR_SOURCES` に値があれば、それも候補にする。既定の `~/Documents/kataribe-assets` と同じなら書かない。
   - `kataribe.output_dir`：今ある成果物（`video.html` か `slides.pptx` と、隣の `script.json` の親）の場所を `mdfind -name video.html` と `mdfind -name slides.pptx` で探して根拠にする。成果物がプロジェクトの下の `out/` にあるなら、既定と同じなので書かない（書くと、次から出力先が変わる）。プロジェクトの外の 1 つのディレクトリにそろっているときと、ユーザーが置き場を指定したときだけ候補にする。
   見つからない値は空のままにして、ユーザーに聞く。使わない値は書かない。値のない節（`[destination]` など）は書かない。`org.dir` は `[org]` を書くときに必須で、決まらなければ `[org]` を書かない。ほかの値は欠けてもよい。欠けたときの動き方は、使うスキルが決める。
   - `[org]` の値：org-file-conventions の手順 0 の表。
   - `destination.adr_dir`：artifact-destination が、これまでどおり `references/保存先ポリシー.md` と確認で決める。
   - `kataribe.char_sources`：kataribe が `KATARIBE_CHAR_SOURCES`、なければ既定の `~/Documents/kataribe-assets` を使う。
   - `kataribe.output_dir`：kataribe が `--out`、なければ既定の `<project>/out` を使う。
3. すべての値と根拠を表で示し、そのまま書くか、直すかを確かめる。
4. 確かめた値だけで、ファイル全体を書き直す（何度実行しても同じ結果になる）。冒頭に「setup-oboro が書く。秘密の値は書かない。」とコメントを書き、書くキーの直前にだけ、表から作った説明のコメントを書く（書かないキーの説明は書かない）。コメントも毎回表から作り直すので、手で足したコメントは残らない。表にないキーは足さない。書いたら読み直し、TOML として読めることと、表にないキーがないことを確かめる。コメントは TOML の値にならないので、この確認には影響しない。
5. 書いたパスと、次のセッションから使われることを伝える。dotfiles で管理するときの置き方も 1 行で示す。

## 禁止事項

- 秘密の値を書く、または聞き出す。
- 確かめていない値を書く。
- 設定ファイル以外のファイル（Emacs の設定、dotfiles など）を書き換える。
