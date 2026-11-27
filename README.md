# oboro-skills

shoh13 の自作エージェントスキルを 1 つのプラグイン `oboro` にまとめたリポジトリです。Claude Code と Codex の両方のマーケットプレイス形式を持っています。

## 中身

`oboro/skills/` に 17 件あります。

- 16 件は、2026-11-19 に Notion の `[DB]スキル v2` の `original` パックから移しました。本文と補助ファイルはパックのままで、frontmatter だけを書き直しています（2026-11-28 に、Notion の描画の残りと v2 の DB にしかない記述を本文から外しました。`docs/sources.md`）。`notion_page_id` を外し、v2 の `user-invocable` と `disable-model-invocation` の値を frontmatter に移しました。このうち discussion-synthesis は、2026-11-28 に summarize-slack-conversation の `references/構造化の規則.md` に移しました。workflow-router と notion-slide-layout は、2026-11-28 に持ち主の判断で外しました。
- 5 件（apply-research-to-project、evidence-research、format-project-page、gas-typescript、summarize-technical-discussion）は、2026-11-25 に同じやり方で戻しました。同じ日に戻した ja-lint-register は 2026-11-26 に、format-project-page と summarize-technical-discussion は 2026-11-28 に、持ち主の判断で外しました。
- resolving-merge-conflicts は mattpocock/skills から消えたスキルを書き直したもので、本家の MIT ライセンスを同梱しています。

外部のスキルの出どころと、このリポジトリから外したもの（k16shikano さんの 2 件、ja-lint-register、2026-11-28 の 5 件）は `docs/sources.md` にあります。

## 入れ方

持ち主の Claude Code（2026-11-26）と Codex に入っています。入れ方は次のとおりです。

ユーザーが名前で呼ぶスキル（frontmatter に `disable-model-invocation: true` があるもの）は、Codex では `agents/openai.yaml` の `allow_implicit_invocation: false` で一覧から外してあります。Codex では `$kataribe` のように名前で呼びます。

```sh
claude plugin marketplace add shoh13/oboro-skills
claude plugin install oboro@oboro-skills

codex plugin marketplace add shoh13/oboro-skills
codex plugin add oboro@oboro-skills
```
