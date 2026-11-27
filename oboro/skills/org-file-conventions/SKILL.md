---
name: org-file-conventions
description: "org-roam で管理している org ノート（置き場は oboro の設定ファイルの `[org]`。setup-oboro が書く）を作る・追記するときの書式ガイド。装飾記号の前後スペース、コードブロックのresults指定、frontmatterの生成元（capture テンプレート）、id:リンクによるバックリンクなど、踏みがちな罠をまとめる。その置き場の外の org ファイルには使わない。"
user-invocable: false
---

# org ファイルの書き方

ユーザーの org-roam のノート群に、新規作成・追記のたびに踏みがちな罠を要点としてまとめる。置き場とテンプレートの場所は端末ごとに違うので、oboro の設定ファイルから読む。

## 0. 設定を読む

1. 設定ファイルは `~/.config/oboro/config.toml`。環境変数 `OBORO_CONFIG` があれば、そのパスを使う。`printenv OBORO_CONFIG` をこのまま実行して確かめ、変数展開を含むコマンドにしない（Claude Code が事前に検査できず、毎回確認を求めるため）。ファイルがあれば `[org]` を読む（キーの意味は setup-oboro の表）。以下の `org.dir` などは、その値を指す。
2. **値が欠けているとき**は、作業に要る値がそろっているかを下の表で確かめる。欠けた値は、ほかの端末の置き場や dotfiles などの決まったパスで補わず、推測もしない。欠けている値の名前を伝え、setup-oboro で足すか、その値なしで進めるかを尋ねる。

   | 欠けているもの | その値なしで進めるとき |
   | --- | --- |
   | 設定ファイル、`[org]`、または `org.dir` | 依頼がこのスキルの対象か決められない。1〜3 と 5〜7 の一般的な書き方だけを使い、frontmatter はユーザーに確かめた形で書く（4 と 4.5 は使わない） |
   | 新規作成で、`org.capture_config` か、作り方に合うテンプレートのキー（`org.memo_template` か `org.node_template`） | frontmatter はユーザーに確かめた形で書く（4 と 4.5 は使わない）。追記には影響しない |
   | 手でタイトルを入れてメモを作るときの `org.memo_dir` | 置き場をユーザーに確かめる |
   | shell ブロックで PATH が要るときの `org.shell_init` | 7 の A は使わない。source するファイルを推測しない |

3. **依頼の対象が `org.dir` の外のとき**は、このスキルの対象ではない。org-mode の一般的な書き方だけを使い、capture テンプレートと `:ai:` タグを当てはめない。

## 1. テキスト装飾は前後にスペースが要る

`*太字*` `/斜体/` `_下線_` `~コード~` `=逐語=` `+取り消し線+` の装飾記号は、開始側の直前・終了側の直後が英数字や日本語の文字に直接くっついていると認識されない。前後に半角スペース（または行頭・行末・括弧などの区切り文字）が必要。

`~コード~` はメソッド名、コマンド、識別子などコードの記法で、`=逐語=` はファイルパス、コミットハッシュ、書き写した文字列などの記法。どちらも等幅表示になるが、テーマによって色が変わる。

```org
NG: 本文*太字*本文
OK: 本文 *太字* 本文
```

日本語の地の文で装飾を使うときは、句読点や全角スペースは区切り文字として機能しないことがあるため、迷ったら半角スペースを挟む。

## 2. コードブロックの結果はデフォルトでファイル内に書かれる

`#+begin_src lang :results output` は追加オプション不要で、実行結果は同じ org ファイル内の `#+RESULTS:` に書き込まれる。「結果をファイルに出力したい」という依頼だった場合、まず今の動作（org ファイル自体への書き込み）で十分かをユーザーに確認する。本当に別ファイルへ書き出したい場合だけ `:file` ヘッダー引数を足す。

```org
#+begin_src shell :results output :file output.txt
echo hello
#+end_src
```

`:file` を付けると `#+RESULTS:` には `[[file:output.txt]]` というリンクだけが挿入され、実体は `output.txt`（org ファイルと同じディレクトリ基準）に書かれる。既存ファイルは毎回上書きされる。

## 3. コードブロック内の値は :var で変数化できる

同じ値（リポジトリ名など）を複数ブロックで繰り返すときは `:var` ヘッダー引数を使う。

ブロック単位:

```org
#+begin_src shell :var repo="owner/repo"
gh issue list --repo $repo --state all
#+end_src
```

ファイル全体で使い回すなら、ファイル冒頭に共通プロパティを1回書けば以降の同言語ブロック全部に効く（個別ブロックだけ別の値にしたい場合はそのブロックにだけ `:var` を書けば上書きできる）:

```org
#+PROPERTY: header-args:shell :var repo="owner/repo"
```

## 4. 新規ファイルの frontmatter は `org.capture_config` のファイルが SSoT

新規 .org ファイルの frontmatter（`:ID:` / `#+TITLE:` / `#+OPTIONS:` / `#+DATE:` / `#+LANGUAGE:` / `#+FILETAGS:` の型）は、このユーザーが実際に手で打たず org-capture / org-roam-capture 経由で自動生成しているため、その生成元である `org.capture_config` のファイルが唯一の正となる。ここに書き写したコピーではなく、必ず作業のたびにそのファイルを読んで現在のテンプレートを確認すること（テンプレートの正本が更新されればテンプレートも変わるため、このファイルに固定のひな形を書いてしまうと乖離する）。

読むべき箇所は2つ:

- `org-capture-templates` のキー `org.memo_template`（`org.memo_dir` 直下に手動でタイトルを入力して作る場合）
- `org-roam-capture-templates` のキー `org.node_template`（org-roam-node-find などノード検索経由で作る場合）

どちらもテンプレート文字列は Emacs Lisp の式が混ざっているので、この環境（Emacs の外）で新規ファイルを作るときは以下のように読み替える:

| テンプレート中の式 | 意味 | この環境での代用 |
| --- | --- | --- |
| `%(org-id-new)` | UUID を新規生成 | \`uuidgen \\ |
| `%<%Y-%m-%d>` | 今日の日付 | `date +%Y-%m-%d` |
| `%(org-capture-get :my-title)` / `${title}` | ユーザーが入力したタイトル | ユーザーに確認したタイトル文字列 |

`#+FILETAGS:` の区切り方（スペース区切りかコロン区切りか）や `#+OPTIONS:` の具体的な値も、`org.capture_config` のテンプレート文字列にある通りに従う。テンプレート自体を変更したい・新しい frontmatter の項目を足したいという話が出たら、このファイルではなく `org.capture_config` のファイルを編集する。

## 4.5. Claude が新規作成する org ファイルには `:ai:` タグを付ける

Claude（このスキル経由）が新規作成した org ファイルだと後から判別できるように、`org.capture_config` のテンプレートで生成した `#+FILETAGS:` に対して `:ai:` タグを追加する。既存ファイルへの追記であって新規作成でない場合は付けない。

```org
#+FILETAGS: :ai:
#+FILETAGS: :project:ai:
```

## 5. リンクは id: を使う（バックリンクが効くのは id: だけ）

他ノートへリンクするときは `[[id:UUID][表示テキスト]]` の形にする。`[[file:...]]` で書いたリンクは org-roam のバックリンク一覧（`SPC n r r`）に拾われないため、後から「このノードはどこから参照されているか」を辿れなくなる。追記中に他ファイルの見出しやノードへ言及する場合は、リンク先の `:ID:` を確認して `id:` リンクにする。

## 6. 実行結果が複数スペース区切りだと勝手にテーブル化される

`:results` の type（table/list/scalar 等）を明示しないと、org-babel は出力の見た目からテーブルかどうかを自動判定する。1行に複数スペースやタブ区切りの「単語」が並んでいると、`=== foo ===` のような見出し行や `['/assets/*', '/vite/assets/*']` のようなリスト表記まで空白単位でセルに割られ、意図しない Org テーブルに壊される。

そのまま素のテキストとして残したい場合は `:results output verbatim`（`verbatim` は `scalar` の別名）をつける。

```org
#+begin_src shell :results output verbatim
echo '=== backend services ==='
gcloud compute backend-services list --format='table(name,enableCDN)'
#+end_src
```

これで `#+RESULTS:` はテーブルではなく `#+begin_example...#+end_example` の素のテキストブロックになる。

## 7. shell コードブロックは非対話シェルなので `.zshrc` の PATH 追加が効かない

org-babel の shell コードブロックは基本的に非対話的（non-interactive）なサブシェルで実行される。zsh は非対話シェルだと `.zshenv` しか自動で読まないため、`.zshrc` で `PATH` を通しているコマンド（gcloud SDK など）はブロック内で `which` しても見つからない。

対処は2通り:

**A. 該当行だけ明示的に source する（推奨・副作用が少ない）**

source するファイルは `org.shell_init` にある（例は gcloud SDK の `path.zsh.inc`）。

```org
#+begin_src shell
source "<org.shell_init のファイル>"
which gcloud
#+end_src
```

**B. `:shebang` でログイン＋対話的シェルとして起動する**

```org
#+begin_src shell :shebang "#!/bin/zsh -i -l"
which gcloud
#+end_src
```

zsh の起動ファイルは `-l`（ログイン）だけでは `.zprofile`/`.zlogin` しか読まれず、`.zshrc` を読ませるには `-i`（対話的）も必要。ただし `-i` は `.zshrc` を丸ごと読み込むため、zle のキーバインドや starship プロンプト初期化など「本物の tty が前提」の設定がエラー（`can't change option: zle` / `Under a 'dumb' terminal` 等）を出すことがある。処理自体は継続する（exit code は 0 のまま）がミニバッファがノイズだらけになるので、PATH を通したいだけなら A の方が安全。

## 追記・新規作成後のセルフチェック

ファイルを書いた・直した後、次を軽く見直す:

- [ ] 装飾記号の前後にスペースがあるか
- [ ] コードブロックの `:results` / `:file` / `:var` は意図通りか（余計な `:file` を付けていないか）
- [ ] 複数スペース区切りの出力が出るコードブロックに `:results output verbatim` を付けたか（意図せずテーブル化されていないか）
- [ ] `.zshrc` 頼みの PATH（gcloud 等）が要るコマンドなら、source するか `:shebang "#!/bin/zsh -i -l"` を付けたか
- [ ] 新規ファイルなら frontmatter一式（`:ID:` `#+TITLE:` `#+OPTIONS:` `#+DATE:` `#+LANGUAGE:` `#+FILETAGS:`）が揃っているか
- [ ] 新規ファイルなら `#+FILETAGS:` に `:ai:` タグが入っているか
- [ ] 他ノートへの参照は `id:` リンクになっているか
