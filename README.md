# oboro-skills

shoh13 の自作エージェントスキルを 1 つのプラグイン `oboro` にまとめたリポジトリです。Claude Code と Codex の両方のマーケットプレイス形式を持っています。

## 中身

`oboro/skills/` に 18 件あります。2026-11-19 に Notion の `[DB]スキル v2` の `original` パックから移しました。本文と補助ファイルはパックのままで、frontmatter だけを書き直しています。`notion_page_id` を外し、v2 の `user-invocable` と `disable-model-invocation` の値を frontmatter に移しました。

本文が移さなかったスキルを名指ししている箇所は `docs/broken-references.md` にあります。

## 入れ方

まだどの端末にも入れていません。入れるときは次のとおりです。

```sh
claude plugin marketplace add shoh13/oboro-skills
claude plugin install oboro@oboro-skills

codex plugin marketplace add shoh13/oboro-skills
codex plugin add oboro@oboro-skills
```
