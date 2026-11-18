# 履歴の収集

GitHub の API から、年表（`timeline.json`）の材料を取得する。`OWNER`、`REPO`、`SCOPE`（年表の範囲とするパス）、`FILE`（原文のパス）を置換して実行する。

`gh` を別のプロセスから呼び出せない環境や、出力をファイルへ書き出せない環境がある。その場合は、コマンドを直接実行し、表示された結果から `timeline.json` を作成する。

## 1. 範囲内の全コミット

```sh
gh api --paginate "repos/OWNER/REPO/commits?path=SCOPE&per_page=100" \
  --jq '.[] | [.sha[0:10], .commit.committer.date[0:10], (.commit.message | split("\n")[0])] | @tsv'
```

新しい順に、sha（10文字）・日付・件名が出力される。件数がそのまま年表の件数になる。

## 2. 対象ファイルを変更したコミット

同じコマンドの `path` を `FILE` にする。この一覧が、変更の抽出（`hist.json`）の対象である。

## 3. コミットごとの規模、バージョン、名前付きの単位の増減

GraphQL で、1回に100件まで取得できる。`VERSION_FILE` は `version` を持つ JSON ファイル（`package.json`、`plugin.json` など）、`UNITS_DIR` は名前付きの単位（スキルなど）が1件ずつ並ぶディレクトリである。バージョンや単位を持たない対象では、該当の行を削除する。

```sh
gh api graphql -f query='query { repository(owner:"OWNER", name:"REPO") { object(expression:"BRANCH") { ... on Commit {
  history(path:"SCOPE", first:100) { pageInfo { endCursor hasNextPage } nodes {
    oid additions deletions changedFilesIfAvailable
    v: file(path:"VERSION_FILE") { object { ... on Blob { text } } }
    s: file(path:"UNITS_DIR") { object { ... on Tree { entries { name } } } }
  } } } } } }' \
  --jq '.data.repository.object.history as $h | $h.nodes as $n | ("cursor " + $h.pageInfo.endCursor), (range(0; $n|length) as $i | $n[$i] as $c | $n[$i+1] as $q | [ $c.oid[0:10], (($c.v.object.text // "{}") | fromjson | .version // ""), $c.changedFilesIfAvailable, $c.additions, $c.deletions, (if $q == null then "?" else ("+" + (([$c.s.object.entries[]?.name] - [$q.s.object.entries[]?.name]) | join(",")) + " -" + (([$q.s.object.entries[]?.name] - [$c.s.object.entries[]?.name]) | join(","))) end) ] | @tsv)'
```

- 各行は、sha・バージョン・変更ファイル数・追加行数・削除行数・単位の増減である。増減は、1つ古いコミットとの差で求めている。
- 100件を超える場合は、`history(path:"SCOPE", first:100, after:"CURSOR")` として続きを取得する。カーソルは `<先頭の sha（40文字）> <番号>` の形式で、1ページ目の末尾の1件を重複させる（例: 1ページ目が `... 99` で終了した場合は `... 98` を指定する）と、ページの境界のコミットにも増減を計算できる。
- 最も古いコミット（`$q == null`）は `?` になる。その時点の単位の一覧を初期値として、`meta.json` の `series` の `start` に件数を記載する。
- `additions` と `deletions` はコミット全体の値で、範囲外のファイルを含む場合がある。報告でその旨を示す。

## 4. timeline.json へ整形する

- `type`: 件名の接頭辞から決定する。`feat` → `f`、`fix` → `x`、`docs` → `d`、`refactor` → `r`、`test` → `t`。バージョンの更新だけのコミットは `c` とする。接頭辞がない場合や、接頭辞がチケットの番号（`PROJ-2073`、`fix #10957` など）の場合は、内容から判断する。
- `pr`: 件名の末尾の `(#123)` から取得する。件名にない場合は記載しない。
- `title`: 読み手の言語へ翻訳する。種別の接頭辞（`feat:`・`fix(scope):` などの Conventional Commits の形式）・チケットの番号・PR 番号は除外する。対象を示す接頭辞（`orch:`、`AI推進:` など）は件名の一部として保持する。原文にない補足（括弧書きの説明など）を追加しない。バージョンの更新だけのコミットは「0.15.34 へ更新」のように記載する。
- `tags`: 手順3の増減から作成する。種別は `skill`・`prin`・`pb` のいずれかで、全履歴の色に使用する。

## ローカルの clone を使用する場合

リポジトリが手元にある場合は、API の代わりに `git` を使用できる。最新の状態へ更新されていることを先に確認する。fetch できない環境では、ローカルの `origin/<既定のブランチ>` との比較だけを実施し、GitHub 上の最新の状態を確認していないことを報告する。手元が `origin` より新しい場合（利用者自身のリポジトリなど）は手元を正とし、push 前のコミットへのリンクが解決しない可能性を報告する。

```sh
git -C <repo> log --format='%h%x09%cs%x09%s' --abbrev=10 -- SCOPE
git -C <repo> log --format='%h' --abbrev=10 -- FILE
git -C <repo> show <sha> -- FILE
git -C <repo> show <sha>:FILE
git -C <repo> show <sha>:VERSION_FILE
```

- 対象のコミットは `--follow` を付けずに取得する。`--follow` は名前の変更を追跡するが、別のブランチで変更され、マージで消失した変更を含むことがある。原文の名前が変更されている場合だけ `--follow` を使用し、追加されたコミットの差分を確認する。範囲をディレクトリとした場合、`git log -- SCOPE` は変更前のパスのコミットを含まないため、`--follow` で得た変更前のコミットを年表に追加する。
- `add`・`del`:
  - 範囲を原文の1ファイルとした場合（原文だけの行数）:

    ```sh
    git -C <repo> log --numstat --format='%h' --abbrev=10 -- FILE
    ```

  - 範囲をディレクトリとした場合（コミット全体の行数。範囲外のファイルを含むことを報告する）:

    ```sh
    git -C <repo> log --numstat --full-diff --format='%h' --abbrev=10 -- SCOPE
    ```

    `--full-diff` を付けないと、範囲外からの移動が全行の追加として集計される。
  - コミットの行の次の行が「追加行数・削除行数・パス」で、パスごとに合計する。節の移動も追加と削除に計上される。
- 名前付きの単位の増減: 単位のディレクトリがない場合（原文が1ファイルの場合）は、`tags` と `series` を記載しない。原文の最上位の節を単位とする場合は、版ごとに `git show <sha>:FILE` の見出しを比較して増減を求め、種別を `pb` とする。
