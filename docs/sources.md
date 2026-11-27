# 出どころの調査（2026-11-19）

仕分けで「元ネタがあったはず」とメモした 5 件を調べた結果です。

| スキル | 判定 | 出どころ | 根拠 |
| --- | --- | --- | --- |
| cognitive-rhythm-writing | 外部（ほぼそのまま） | Keiichiro Shikano（k16shikano）の gist `eb2929f13ed19c97188393d297be8432`。Unlicense。takuan-osho/ccmarketplace の `plugins/cognitive-rhythm-writing` に再配布されている | ccmarketplace 版（85bdfa9）と本文の行の一致率 0.97。違いは、併用スキルへの参照が Notion のメンションになっている点と、太字が 1 か所外れている点だけ |
| japanese-tech-writing | 外部（ほぼそのまま、1 規則追加） | 同じく k16shikano の gist `fd287c3133457c4fd8f5601d34aa817d`。Unlicense。ccmarketplace の `plugins/japanese-tech-writing` | 一致率 0.89。違いの多くは Notion の描画による `<p>` の混入、記号の全角化、太字の欠落。中身の違いは「イ形容詞＋です」の規則が 1 つ足されていること。この規則は gist の後の版にあるもので、持ち主の追加ではなかった（下の「k16shikano の 2 件の扱い」） |
| guided-setup | 外部由来の派生 | mattpocock/skills の `skills/engineering/wizard`（MIT）から、手動セットアップの責務を切り出したもの | Notion v2 の出典欄「既存 wizard の手動セットアップ責務を Phase 9 合成 Contract に基づき抽出」。抽出元の wizard は mattpocock 由来 |
| audit-security-exposure | 自作（文書を素材にした手順化） | IPA「不正アクセスによる漏えい等の事案を踏まえ、速やかに実施すべき対策等について」（2026-10-09） | 本文の「根拠と適用範囲」で URL 付きで明記済み。実行分担・承認・記録方法は自作の運用規則と本文が区別している |
| solution-review | 未確定 | 見つからず | 「技術方案」という中国語由来の語と、11 節の出力形式から、中国語のレビュー用プロンプトの翻訳ではないかと推測（推測）。中国語での検索では一致するものが見つからなかった |

## k16shikano の 2 件の扱い（2026-11-25 に決定）

このリポジトリから外し、takuan-osho/ccmarketplace から `npx skills add` で入れ直しました。持ち主が足した中身がなかったためです。

- **gist は読めます。** 11-19 に 404 と書きましたが、2026-11-25 には `gh api gists/<id>` で取れました。
- **このリポジトリの写しは gist の版そのものです。** japanese-tech-writing は gist の版 `c7189cd`（2026-07-24）、cognitive-rhythm-writing は `a3b1e26`（2026-07-09）と一致しました。Notion の描画による `<p>` の混入、太字の欠落、全角化、空行を正規化して比べています。残る違いは、frontmatter（`user-invocable: false` と短くした description）と、cognitive-rhythm-writing の参照が Notion のメンションになっていた 1 行だけです。
- **「イ形容詞＋です」の規則は k16shikano さんのものです。** 11-19 には足された規則と書きましたが、gist の `c7189cd` で入っています。持ち主の追加ではありません。
- **ccmarketplace の版は古いです。** ccmarketplace は 2026-07-16 に取り込んだ版（`736fdb0`、HEAD は `85bdfa9`）で、「イ形容詞＋です」の規則がありません。gist の方はその後も更新され、整形の節を別の gist `67625f2a7d96e3bbdfae8d571a936063` に分けています。

## resolving-merge-conflicts（2026-11-25 に追加）

- **出どころ。** mattpocock/skills の `skills/engineering/resolving-merge-conflicts`（MIT）を、Notion v2 で日本語の共通の型に書き直したものです。v2 の出典欄は「mattpocock/skills engineering/resolving-merge-conflicts（MIT）」です。
- **本家ではもうありません。** `daa01d8`（2026-09-24、「Remove resolving-merge-conflicts」）で消えました。最後にあった版は `153fc1b` です。本家から入れる手段がないので、持ち主の版をここに置きます。
- **取り込み元。** `~/.agents/skill-inventory-20261118/backup/01-from-mattpocock.tar.gz`。v2 の `from-mattpocock` パック（2026-11-19）と差分 0 です。
- **ライセンス。** 本家の `LICENSE`（`153fc1b` の時点）を `oboro/skills/resolving-merge-conflicts/LICENSE` に同梱しています。

## 2026-11-25 に戻した自作 6 件

11-19 の仕分けで「捨てる」にしたものを、`~/.agents/skill-inventory-20261118/backup/08-phase4/agents-skills/` から戻しました。中身は v2 の `original` パック（2026-11-19 22:33）と差分 0 です。frontmatter は 18 件と同じ書き方にしました。`user-invocable` と `disable-model-invocation` は、v2 の行のプロパティを `ntn api /v1/pages/<id>` で 11-25 に読んだ値です。本文の Notion 由来の崩れは直していません。

| スキル | v2 の出典欄 |
| --- | --- |
| apply-research-to-project | 自作。旧「調査結果をプロジェクトに反映する」から再設計 |
| evidence-research | 既存 research の調査責務を Phase 9 合成 Contract に基づき抽出（research は mattpocock 由来） |
| format-project-page | 自作。旧「プロジェクトページを整える」から責務を限定して再設計 |
| gas-typescript | 自作。旧 gas-typescript から再設計 |
| ja-lint-register | 自作 |
| summarize-technical-discussion | 自作。旧「技術議論を要約する」から再設計 |

ja-lint-register は、要らないという持ち主の判断で 2026-11-26 に外しました。

business-japanese-writing は戻していません。本家の coji/natural-japanese の `natural-japanese` を入れました。

## 本家の名前に合わせた参照（2026-11-25）

- workflow-router の `setup-project-workflow`（2 か所）を、本家の名前 `setup-matt-pocock-skills` に直しました。
- mattpocock の `code-review` は、Claude Code 組み込みの `/code-review` を隠すので、`code-review-mp` という名前で入れています（`npx skills add mattpocock/skills -s code-review --rename code-review-mp`、持ち主の判断）。workflow-router（1 か所）と solution-review（7 か所）の参照を `code-review-mp` に直しました。

## kataribe と kataribe-slides の取り込み（2026-11-19 22:33）

Notion v2 の `original` パック（version `7a0adaf9b6aa`）から取り込みました。Notion はページ本文を描画し直すときに、インラインコードの中身を壊します。たとえば `--out` が `-out` に、`**…**` が `*…**` に、`` `*-line*.png` `` が `` `-line*.png` `` に変わります。

- **kataribe。** 本文と補助ファイルは、ページに添付された `src.zip` の中身をそのまま使いました。zip の中の SKILL.md は崩れていません。`__MACOSX/` と `.DS_Store` は除いています。
- **kataribe-slides。** 崩れていない元がないので、ページの本文に `tools/repair-notion-body.py` の規則を当てて戻しました。この規則を kataribe（正解の zip がある）に当てると、崩れた 20 行のうち 16 行が正解と一致しました。戻せない 4 行は、どれも行頭の `*` が消えたものです。kataribe-slides には、その種類の崩れはありませんでした。

doc-state-machine の本文にも、同じ崩れ（`--follow` が `-follow` など）が残っています（未修正）。

## doc-state-machine の取り込み（2026-11-20 01:06）

Notion v2 の `original` パック（version `7a0adaf9b6aa`）から取り込みました。正本は v2 で、ほかに崩れていない元はありません。

- **本文。** `tools/repair-notion-body.py` で戻しました。戻した主な箇所は `--follow`、`--url`、`--items`、`--arrows`、`--ids`、`--tab`、コードブロックの言語名 `text`、`[検討中]` です。
- **手で直した 1 か所（推測）。** 太字の見出し語の例 `` `*名前.** 本文` `` は、`` `**名前**. 本文` `` に直しました。`scripts/extract-md.mjs` の正規表現が `**名前**` の直後に `.` が続く形を受け付けるので、それに合わせています。
- **欠けているファイル。** `tests/run.mjs` が読む `tests/fixture-dom.js` は、v2 のパックに入っていません（11-19 と 11-20 のどちらのパックにもない）。テストは build の検査 7 件が通った後、このファイルを読むところで止まります。Notion が `.js` の添付を受け付けなかった可能性があります（推測。`.mjs` と `.cjs` は入っている）。

## SKILL.md から外した Notion の記録（2026-11-28）

Notion の描画で残った記法と、Notion の `[DB]スキル v2` を前提にした記述を、各 SKILL.md から外しました。規則は変えていません。

- **記法。** 冒頭の `<callout>` の囲み（中の文は残した）、`\*\*`、`[AGENTS.md](http://AGENTS.md)` のような自動リンク、`<date start=… />`、`<b>`、evidence-research の手順 3〜10 を 1 行につないでいた `<br />`、notion-slide-layout の番号の振り直しを直しました。doc-state-machine の本文の頭に残っていた 2 つ目の frontmatter（`notion_page_id` つき）を外し、`f docx` を `-f docx` に戻しました。
- **Relation の検査。** 「本文の呼び出しと Relation が一致する」「起動主体はモデル起動である」は、v2 の DB のプロパティを確かめる項目で、このリポジトリには対応するものがないので外しました（9 件）。
- **検証の履歴。** evidence-research と guided-setup の「検証履歴」の節を外しました。どちらの証拠も Notion の [Phase 13 最終実動再試験 — evidence hash・平坦化](https://app.notion.com/p/996095336b07404eb27858f8b5dd9dbb) にあります。workflow-router の Phase 12・13 のリンクは残しています。
- **例のリポジトリ名。** org-file-conventions の `:var` の例のリポジトリ名を `owner/repo` にしました。
- **戻せなかった 1 か所。** org-file-conventions の表の `%(org-id-new)` の行は、Notion が表の中の `|` を壊していて、`uuidgen` に続く元のコマンドが分かりません。崩れていない元が見つからないので、そのままにしています。
