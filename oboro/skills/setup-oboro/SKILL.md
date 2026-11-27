---
name: setup-oboro
description: "この端末での oboro の環境設定（org-roam のノートの置き場、capture テンプレートの正本など）を調べ、ユーザーに確かめてから、リポジトリの外の設定ファイルに書く。秘密の値は書かない。「oboro の設定をして」「/setup-oboro」で使う。"
disable-model-invocation: true
---

# setup-oboro

oboro のスキルのうち、端末ごとに違う値を使うものは、この設定ファイルを読む。今は org-file-conventions が `[org]` を使う。

## 設定ファイル

- **場所。** `~/.config/oboro/config.toml`。環境変数 `OBORO_CONFIG` があれば、そのパス。`printenv OBORO_CONFIG` をこのまま実行して確かめる（変数展開を含むコマンドは Claude Code が事前に検査できない）。`OBORO_CONFIG` は、別の場所に置くときや試験のときだけ使う。
- **形式。** TOML。キーは下の表のものだけ。パスと名前だけを書き、トークン、パスワード、API キーなどの秘密の値は書かない。`~` は読む側がホームに展開する。
- **dotfiles での管理。** このファイルを dotfiles に置き、home-manager なら `xdg.configFile."oboro/config.toml".source` で置ける。

| キー | 意味 | 例 |
| --- | --- | --- |
| `org.dir` | org-roam のノートの置き場（`org-roam-directory`） | `"~/repo/05_org"` |
| `org.memo_dir` | 手でタイトルを入れて作るメモの置き場 | `"~/repo/05_org/roam"` |
| `org.capture_config` | capture テンプレートを定義しているファイル | `"~/dotfiles/home-manager/doom.d/config.org"` |
| `org.memo_template` | `org-capture-templates` の、手でタイトルを入れて作るメモのキー | `"m"` |
| `org.node_template` | `org-roam-capture-templates` の、ノード検索から作るときのキー | `"d"` |
| `org.shell_init` | org-babel の shell ブロックで `source` するファイル（非対話シェルで PATH を通すため） | `["~/.local/share/google-cloud-sdk/path.zsh.inc"]` |

## 手順

1. 設定ファイルのパスを確かめ、あれば読む。ある値は今の値として扱う。
2. 足りない値を、この端末から調べる。推測で書かず、見つけた根拠（ファイルと行）を添えて候補にする。
   - `org.dir`：Emacs の設定（`config.org`、`config.el`、`init.el` など）の `org-roam-directory` と `org-directory`。
   - `org.capture_config`：`org-capture-templates` を定義しているファイル。
   - `org.memo_template`・`org.node_template`：そのファイルにあるテンプレートのキーと説明。
   - `org.memo_dir`：メモのテンプレートがファイルを作る先。
   - `org.shell_init`：`.zshrc` などでだけ PATH を通しているコマンドの初期化ファイル（gcloud の `path.zsh.inc` など）。
   見つからない値は空のままにして、ユーザーに聞く。使わない値は書かない。
3. すべての値と根拠を表で示し、そのまま書くか、直すかを確かめる。
4. 確かめた値だけで、ファイル全体を書き直す（何度実行しても同じ結果になる）。冒頭に「setup-oboro が書く。秘密の値は書かない。」とコメントを書く。表にないキーは足さない。
5. 書いたパスと、次のセッションから使われることを伝える。dotfiles で管理するときの置き方も 1 行で示す。

## 禁止事項

- 秘密の値を書く、または聞き出す。
- 確かめていない値を書く。
- 設定ファイル以外のファイル（Emacs の設定、dotfiles など）を書き換える。
