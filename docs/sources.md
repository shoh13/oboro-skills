# 出どころの調査（2026-11-19）

仕分けで「元ネタがあったはず」とメモした 5 件を調べた結果です。

| スキル | 判定 | 出どころ | 根拠 |
| --- | --- | --- | --- |
| cognitive-rhythm-writing | 外部（ほぼそのまま） | Keiichiro Shikano（k16shikano）の gist `eb2929f13ed19c97188393d297be8432`。Unlicense。takuan-osho/ccmarketplace の `plugins/cognitive-rhythm-writing` に再配布されている | ccmarketplace 版（85bdfa9）と本文の行の一致率 0.97。違いは、併用スキルへの参照が Notion のメンションになっている点と、太字が 1 か所外れている点だけ |
| japanese-tech-writing | 外部（ほぼそのまま、1 規則追加） | 同じく k16shikano の gist `fd287c3133457c4fd8f5601d34aa817d`。Unlicense。ccmarketplace の `plugins/japanese-tech-writing` | 一致率 0.89。違いの多くは Notion の描画による `<p>` の混入、記号の全角化、太字の欠落。中身の違いは「イ形容詞＋です」の規則が 1 つ足されていること |
| guided-setup | 外部由来の派生 | mattpocock/skills の `skills/engineering/wizard`（MIT）から、手動セットアップの責務を切り出したもの | Notion v2 の出典欄「既存 wizard の手動セットアップ責務を Phase 9 合成 Contract に基づき抽出」。抽出元の wizard は mattpocock 由来 |
| audit-security-exposure | 自作（文書を素材にした手順化） | IPA「不正アクセスによる漏えい等の事案を踏まえ、速やかに実施すべき対策等について」（2026-10-09） | 本文の「根拠と適用範囲」で URL 付きで明記済み。実行分担・承認・記録方法は自作の運用規則と本文が区別している |
| solution-review | 未確定 | 見つからず | 「技術方案」という中国語由来の語と、11 節の出力形式から、中国語のレビュー用プロンプトの翻訳ではないかと推測（推測）。中国語での検索では一致するものが見つからなかった |

## 本家の入れ方

- k16shikano の 2 件は、takuan-osho/ccmarketplace から入れられます。`/plugin marketplace add takuan-osho/ccmarketplace` のあと、`cognitive-rhythm-writing` と `japanese-tech-writing` を入れます。
- gist 本体は 2026-11-19 時点で GitHub API から 404 でした。非公開化か削除のどちらかです。

## このリポジトリでの扱い（未決）

cognitive-rhythm-writing と japanese-tech-writing は自作ではありません。次のどちらかを選ぶ必要があります。

- このリポジトリから外し、ccmarketplace から入れる。
- 加えた変更（イ形容詞の規則など）を残したいなら、出典を明記して残す。Unlicense なので、どちらでも条件はありません。

## kataribe と kataribe-slides の取り込み（2026-11-19 22:33）

Notion v2 の `original` パック（version `7a0adaf9b6aa`）から取り込みました。Notion はページ本文を描画し直すときに、インラインコードの中身を壊します。たとえば `--out` が `-out` に、`**…**` が `*…**` に、`` `*-line*.png` `` が `` `-line*.png` `` に変わります。

- **kataribe。** 本文と補助ファイルは、ページに添付された `src.zip` の中身をそのまま使いました。zip の中の SKILL.md は崩れていません。`__MACOSX/` と `.DS_Store` は除いています。
- **kataribe-slides。** 崩れていない元がないので、ページの本文に `tools/repair-notion-body.py` の規則を当てて戻しました。この規則を kataribe（正解の zip がある）に当てると、崩れた 20 行のうち 16 行が正解と一致しました。戻せない 4 行は、どれも行頭の `*` が消えたものです。kataribe-slides には、その種類の崩れはありませんでした。

doc-state-machine の本文にも、同じ崩れ（`--follow` が `-follow` など）が残っています（未修正）。
