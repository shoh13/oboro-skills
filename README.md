# oboro-skills

shoh13 の自作エージェントスキルを 1 つのプラグイン `oboro` にまとめたリポジトリです。Claude Code と Codex の両方のマーケットプレイス形式を持っています。

## 中身

`oboro/skills/` に 18 件あります。

- 16 件は、2026-11-19 に Notion の `[DB]スキル v2` の `original` パックから移しました。本文と補助ファイルはパックのままで、frontmatter だけを書き直しています（2026-11-28 に、Notion の描画の残りと v2 の DB にしかない記述を本文から外しました。`docs/sources.md`）。`notion_page_id` を外し、v2 の `user-invocable` と `disable-model-invocation` の値を frontmatter に移しました。このうち discussion-synthesis は、2026-11-28 に summarize-slack-conversation の `references/構造化の規則.md` に移しました。workflow-router と notion-slide-layout は、2026-11-28 に持ち主の判断で外しました。
- 5 件（apply-research-to-project、evidence-research、format-project-page、gas-typescript、summarize-technical-discussion）は、2026-11-25 に同じやり方で戻しました。同じ日に戻した ja-lint-register は 2026-11-26 に、format-project-page と summarize-technical-discussion は 2026-11-28 に、持ち主の判断で外しました。
- resolving-merge-conflicts は mattpocock/skills から消えたスキルを書き直したもので、本家の MIT ライセンスを同梱しています。
- setup-oboro は 2026-11-28 に足した自作のスキルで、端末ごとの設定ファイルを書きます（下の「端末ごとの設定」）。

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

## 端末ごとの設定

端末によって違うパス（org-roam のノートの置き場など）は、スキルに書かず、リポジトリの外の設定ファイルに置きます。

- 場所は `~/.config/oboro/config.toml`（環境変数 `OBORO_CONFIG` があればそのパス）。
- `/setup-oboro`（Codex では `$setup-oboro`）が端末を調べ、確かめてから書きます。パスと名前だけを書き、秘密の値は書きません。各キーの上には、意味と使うスキルをコメントで書きます。
- これを読むのは、org-file-conventions（`[org]`）、artifact-destination と adr-recorder（`[destination]`）、kataribe と kataribe-slides（`[kataribe]`）です。
- 値がないときの動きはスキルごとに違います。org-file-conventions は、決まったパスを読みに行かずに、設定するか尋ねます。artifact-destination と adr-recorder は、指示ファイルやルールのページが示す保存先を先に使い、設定はそれがない端末の既定にだけ使います。どちらもなければ、これまでどおり尋ねます。kataribe は、環境変数 `KATARIBE_CHAR_SOURCES` を設定より先に使い、どちらもなければ既定の `~/Documents/kataribe-assets` を使います。

## 変えるとき

`oboro/` を変えたら、`oboro/.claude-plugin/plugin.json` と `oboro/.codex-plugin/plugin.json` の `version` を同じ値に上げます。上げないと、入れてある写しが更新されません（CI の plugin-version が確かめます）。
