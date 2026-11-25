# oboro-skills

shoh13 の自作エージェントスキルを 1 つのプラグイン `oboro` にまとめたリポジトリです。Claude Code と Codex の両方のマーケットプレイス形式を持っています。

## 中身

`oboro/skills/` に 23 件あります。

- 16 件は、2026-11-19 に Notion の `[DB]スキル v2` の `original` パックから移しました。本文と補助ファイルはパックのままで、frontmatter だけを書き直しています。`notion_page_id` を外し、v2 の `user-invocable` と `disable-model-invocation` の値を frontmatter に移しました。
- 6 件（apply-research-to-project、evidence-research、format-project-page、gas-typescript、ja-lint-register、summarize-technical-discussion）は、2026-11-25 に同じやり方で戻しました。
- resolving-merge-conflicts は mattpocock/skills から消えたスキルを書き直したもので、本家の MIT ライセンスを同梱しています。

外部のスキルの出どころと、このリポジトリから外したもの（k16shikano さんの 2 件）は `docs/sources.md` にあります。

## 入れ方

まだどの端末にも入れていません。入れるときは次のとおりです。

```sh
claude plugin marketplace add shoh13/oboro-skills
claude plugin install oboro@oboro-skills

codex plugin marketplace add shoh13/oboro-skills
codex plugin add oboro@oboro-skills
```
