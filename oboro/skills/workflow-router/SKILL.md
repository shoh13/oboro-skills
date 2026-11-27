---
name: workflow-router
description: "ユーザーの望む完了状態と現在地から候補を絞り、実Skill本文を検証した上位3件を比較表示し、明示確認後だけ選択Skillへ共通実行コンテキストを渡して起動する。成果物作成や保存先解決は行わない。"
disable-model-invocation: true
---

ユーザーが開始する仕事の入口を選ぶためのルーター。推薦前に候補の実Skill本文を確認し、承認前には何も起動しない。

## 完了条件

- 適格候補を最大3件まで順位付きで示し、各候補の適合理由、他候補に劣る理由、不足前提、引き渡す入力が分かる。3件未満でも対象外候補で埋めない。
- 最終候補の実Skill本文、起動主体、ライフサイクル、必要入力、完了条件が確認されている。
- ユーザーが1件を明示確認した場合だけ、tail-dispatchによりRouterの実行フレームを終了し、そのSkillが新しいトップレベルのユーザー承認済み起動として1回だけ開始される。
- Router自身は成果物を作らず、保存先を解決せず、選択Skillの仕事を代行しない。

## Router dispatch exception

- この例外を使えるのは`workflow-router`だけとする。
- 「呼び出すスキル」Relationは合成依存ではなく、承認後にdispatchできる候補集合を表す。
- ユーザー起動Skillを自動起動しない。候補を1件に確定しても、起動前に必ず明示確認を得る。
- 承認後のdispatchは`tail-dispatch`とする。Routerは、選択Skill、共通実行コンテキスト7項目、固有入力、既知の不足、確認済み事項、禁止範囲を`Launch Contract`として確定する。
- Routerの実行フレームを終了してから、選択Skillを新しいトップレベルのユーザー承認済み起動として1回だけ開始する。
- Routerを親にした子セッションまたはsubagentとして選択Skillを起動しない。選択Skillは通常の委譲深度をすべて使える。
- ランタイムがトップレベル移行を提供できない場合は、`Launch Contract`を返して停止し、ユーザーまたはランタイムに再起動を求める。ネスト実行やRouterによる代行はしない。
- Router以外のユーザー起動Skillからユーザー起動Skillへの依存は禁止のままとする。
- 最終候補は索引だけで確定せず、実Skill本文を検証する。
- Primitiveを直接推薦する例外は、次の3条件をすべて満たす場合だけ許可する。
  1. 仕事全体がPrimitiveの完了条件と一致する。
  2. 同じ仕事全体を所有する利用可能なWorkflowがない。
  3. 単なるWorkflowの下流工程ではない。
- Primitiveを例外推薦する場合は、3条件を満たした理由を出力へ明記する。

## 共通実行コンテキスト

- 環境：既知の実行環境。未確認なら不足として残す。
- 対象：ユーザーが扱いたいRepo、ページ、DB、会話、写真、期間など。
- 基準保存先：Routerでは解決しない。明示済みの値だけを渡す。
- 適用ポリシー：ユーザー指定、プロジェクト規則、組織規則、共有範囲。
- 確認済み事項：Routerで確認した候補選択と、既に承認済みの範囲。
- 作業範囲：今回扱ってよい対象。
- 禁止範囲：変更禁止、公開禁止、自動開始禁止など。

追加で、望む完了状態、現在地、阻害要因、規模、必要成果物、環境・前提を構造化して引き渡す。

## Routing index

索引は絞り込み専用。推薦確定前に実Skill本文で補正する。

| Skill | Use when | Do not use when | Required input | Completion | Prerequisites |
| --- | --- | --- | --- | --- | --- |
| apply-research-to-project | 完了済み調査を親プロジェクトへ反映する | 新規調査や未確定仮説の昇格 | 調査記録、対象プロジェクト、承認範囲 | 持続する結論だけが承認どおり反映 | 調査が完了済み |
| evidence-code-review | 変更が導入した対応可能な問題だけを、因果を証明してMUST/SHOULD/BETTER/NITSで指摘する | 全体評価・方案判断、修正まで必要 | diff/PR、比較ベース、リポジトリ指示 | 5要素と因果が検証済みの指摘（修正しない） | レビュー対象へアクセス |
| find-skills | 外部のスキルエコシステムからインストール可能なSkillを探す | 既存Skillの選択、Skillの作成 | 探したい機能・分野 | 品質確認済みの候補とインストールコマンド提示 | npx skills CLI・外部ネットワーク |
| format-project-page | 既存ページの意味を変えず構造だけ整える | 内容の再設計・補完 | 対象ページ、変更禁止範囲 | 文言・参照を保持して読みやすい | 編集可能な既存ページ |
| grill-with-docs | 計画や設計を問い詰めて詰め、その場で用語集（`GLOSSARY.md`）とADRを書く | 合意済み内容の仕様化 | 計画・設計、対象Repo | 詰めた計画と、更新した`GLOSSARY.md`・`docs/adr/` | 対話できる。本文は`grilling`と`domain-modeling`を呼ぶだけ |
| guided-retrospective | 期間やプロジェクトを本人の意味づけまで振り返る | 単なる活動報告・他者評価 | 期間、目的、参照記録 | 学び・課題・次の行動が確認済み | 本人が対話できる |
| implement | 仕様またはチケットに書かれた作業を実装する | 仕様・チケットが未確定 | 仕様、またはissue trackerのチケット参照 | `tdd`で実装し、型検査とテストを通し、`code-review`でレビューし、今のブランチへcommit | 仕様かチケットがある。Claude Codeでは本文の`code-review`は組み込みの`/code-review`に当たる。Codexには当たる先がないので、レビューが要るときは`code-review-mp`を直接呼ぶ |
| improve-codebase-architecture | コードベースを走査して深くできる箇所を探し、HTMLレポートで示し、選んだ1件を詰める | 1つのモジュールの設計だけ、既知のバグ | Repo、`GLOSSARY.md`、`docs/adr/` | OSの一時ディレクトリのHTMLレポートと、選んだ候補の詰め。必要なら`GLOSSARY.md`とADRを更新 | 読めるコードベース |
| notion-slide-layout | Notion内容をスライド風に再配置する | PPTX作成、追加調査 | 対象ページまたは選択範囲 | 内容保持したスライド風レイアウト | Notion上の入力がある |
| photo-poster | 入力写真を3:4のミニマルポスターへ変換する | 写真なし生成、補正だけ、コラージュ | 写真、任意の文字、配置先 | 写真ごとの完成ポスター | 入力写真がある |
| profile-deep-dive | 本人の1テーマを掘り下げプロフィールへ反映する | 人物調査・第三者評価 | テーマ、本人回答、対象プロフィール | 確認済み差分だけ反映 | 本人が対話できる |
| research | 問いを一次情報で調べ、出典つきの結果をRepoのMarkdownファイル1つに残す。調べるのはバックグラウンドのエージェント | 単発の事実確認、意思決定の代行 | 問い | 各主張に出典がついたMarkdownファイルが、Repoの既存の置き場に保存されている | 書き込めるRepo、バックグラウンドのエージェントを起動できる |
| setup-matt-pocock-skills | Repoを本家のengineeringスキル向けに設定する（issue tracker、triageのラベル、domain docsの置き方）。ほかのengineeringスキルを初めて使う前に1回 | 個別機能の実装、ほかのサービスの設定 | 対象Repo | `docs/agents/`の`issue-tracker.md`、`triage-labels.md`、`domain.md`が書かれている | 対象Repoに書き込める |
| solution-review | 実装の細部より先に技術方案の妥当性を判断し、妥当なら実装レビューへ進む | 差分のみの行レベルレビュー、コード修正 | Repo/ブランチ、目標・要件資料 | 11節の所見とルート結論（修正しない） | 読取可能なRepo |
| summarize-slack-conversation | Notionに貼られたSlack原文を同ページで要約する | Slackから取得・投稿する | 原文を含むNotionページ | 原文保持の追跡可能な要約 | 会話原文が貼付済み |
| summarize-technical-discussion | AI meeting notesの技術議論をsummaryへ整理する | 一般会議、別ページ作成 | meeting notesと文字起こし | 技術論点・決定・未決が追跡可能 | transcriptまたはnotesがある |
| teach | 新しい技能や概念を、このワークスペースのレッスンで教える | 事実確認・資料作成だけ | 学ぶ目的（mission） | `./lessons/`に1テーマずつ自己完結したHTMLのレッスン | 対話でき、ワークスペースに書き込める |
| to-questionnaire | 自分では答えきれない判断を、ほかの人が埋める質問票にする | ユーザー自身で完結する判断 | 受け手の役割・専門・関係、必要な回答 | カレントディレクトリの`to-questionnaire-<slug>.md` | 受け手を特定できる |
| to-spec | これまでの会話を仕様にまとめ、issue trackerへ公開する。聞き取りはしない | 未決事項の議論 | これまでの会話、Repo | 仕様のissueが`ready-for-agent`ラベルつきで公開されている | `setup-matt-pocock-skills`で設定済み |
| to-tickets | 計画・仕様・会話を、ブロック関係を宣言したtracer-bulletのチケットに分ける | 仕様が未確定 | 計画・仕様、またはこれまでの会話 | 設定済みのtrackerに、依存の順でチケットが公開されている | `setup-matt-pocock-skills`で設定済み |
| triage | issueと外部のPRをtriageの役割の状態機械で進め、分類・検証し、エージェント向けのbriefを書く | 新しい作業の分解 | issue tracker、対象のissue・PR | 役割ラベルの更新と、免責文つきのtriageコメント・brief | `setup-matt-pocock-skills`で設定済み |
| wait-what | 直前の説明が伝わらなかったとき、文脈を足し、Simplified Technical Englishと`GLOSSARY.md`の用語で言い直させる | 新しい設計の議論 | 伝わらなかった直前の説明 | 言い直した説明 | 直前の説明がある |
| wayfinder | 1セッションに収まらない大きな仕事を、issue tracker上の決定チケットの地図にし、1件ずつ解いて道筋を明らかにする | 小規模・道筋が明確・実装の分解 | 目的地（destination） | `wayfinder:map`ラベルの地図issueと子チケット、決定の記録 | `setup-matt-pocock-skills`で設定済みのissue tracker |
| wizard | 人にしかできない手順（インフラの用意、認証情報やCIシークレット、外部ダッシュボード、一度きりの移行）を案内するbashウィザードを作る | エージェント自身でできる手順 | 手順の目的、Repoの`.env`やCI設定 | `bash -n`を通ったウィザードと実行方法の案内。最後まで自分では実行しない | 人が操作できる |
| yomiyasu | 名前を出して頼まれたときに、AIが書いた日本語を推敲する | 名前を出さない執筆の依頼、コード・設定・ドキュメントの更新 | 推敲する日本語 | 意味と条件を保ち、不自然な比喩、曖昧な主述関係、装飾を整えた文 | 利用者が名前を出して頼んだ |
| diagnosing-bugs | 難しいバグや性能劣化を、フィードバックループを作って診断する | 原因と修正が既知 | 症状、Repo、再現情報 | 再現、仮説の検証、修正と回帰テスト、後片付けまで終わっている | 再現するループを作れる |
| prototype | 設計上の問い（ロジックや状態モデル、UIの見た目）に、捨てる前提の試作で答える | 本番実装・出荷品質 | 問い、周りのコード | 試作と答えを、捨てるブランチとissueに残している | 永続化しない。DBを使うならscratch |
| code-review-mp | 固定点（commit、branch、tag、merge-base）からの変更を、Standards（Repoの規約）とSpec（元のissue・仕様）の2軸でレビューする | 修正まで必要、方案の判断 | 固定点、仕様の出所、規約の出所 | 2つのサブエージェントの結果を並べた報告 | `setup-matt-pocock-skills`で設定済みのissue tracker |
| resolving-merge-conflicts | 進行中merge/rebaseの競合を解消する | 競合のない通常マージ | Repo、競合状態、両側の意図 | 競合解消と既定検査完了 | merge/rebaseが進行中 |
| handoff | 今の会話を、別のエージェントが続けられる引き継ぎ文書にまとめる | 仕様書・タスク分解の代用 | 今の会話、次のセッションの焦点（任意） | OSの一時ディレクトリの引き継ぎ文書。推奨スキルの節があり、秘密は伏せてある | 今の会話がある |
| writing-for-agents | エージェント向けの文書（スキル、AGENTS.md、CLAUDE.md）を作る・直す | 人間向けの業務マニュアル | 対象の文書 | 手順と完了条件、情報の階層が整った文書 | 対象の文書を編集できる |
| gas-typescript | GASをTypeScriptで開発・移行する | GASまたはTypeScriptを使わない | Repo、GAS入口、build/clasp条件 | 型検査・テスト・build・配布確認 | GASプロジェクトがある |
| codebase-design | 深いモジュールを設計するときの共通の語彙。interface、シームの位置、テストしやすさを決める | コードベース全体の候補探索（improve-codebase-architecture） | 対象モジュール | 深さ、シーム、テストの表面についての判断 | 対象コードがある |
| domain-modeling | プロジェクトのドメインモデルを作って詰め、用語集（`GLOSSARY.md`）とADRに書く | 既存用語の参照だけ | 対象ドメイン、既存の`GLOSSARY.md` | 解決した用語が`GLOSSARY.md`に、必要な判断が`docs/adr/`にある | 対象Repo |

直接候補から除外する内部基盤Primitive：`artifact-destination`、`evidence-research`、`guided-setup`、`discussion-synthesis`、`adr-recorder`。これらは直接は推薦しない。

## 手順

1. 既知コンテキストから、望む完了状態、現在地、阻害要因、規模、必要成果物、環境・前提を抽出する。未記載は推測せず不足として保持する。
2. Routing indexで候補を絞る。原則はユーザー起動Workflowとし、仕事全体がPrimitiveの責務に一致し、適切なWrapperがない場合だけ直接Primitiveを残す。
3. 順位が決まらない場合だけ、1ラウンド最大3問を提示する。質問は具体的で選択可能にし、既知事項を聞き直さない。会話整理の同率では、入力源（Notion貼付Slack／AI meeting notes／その他記録）と目的（同じ場所への要約／再開用handoff）の2軸を優先し、最大2問で判定する。
4. 上位3件を仮順位する。3件未満しか適格でなければ不足分を対象外候補で埋めない。比較のため対象外候補を示す場合は、`dispatch不可`と明記して順位へ含めない。
5. 各最終候補の実Skill本文とDBプロパティを読み、起動主体、ライフサイクル、必要入力、完了条件、対象外、利用可否を確認する。索引が古い場合は実Skillを優先して順位を補正する。
6. 次の列で提示する：`rank / Skill / 適合理由 / 他候補に劣る理由 / 不足前提 / 引き渡す入力`。Primitive例外では適合理由に例外3条件の判定を含める。前提不足時は、(a) 本命ランキングと、(b) 開始可能にする先行経路を二層で示し、順位と先行工程を混同しない。先行経路を自動起動しない。
7. 起動する1件をユーザーへ確認する。確認前はSkillを起動せず、成果物作成、保存先解決、外部操作を行わない。
8. 承認後、選択Skill、共通実行コンテキスト7項目、固有入力、既知の不足、確認済み事項、禁止範囲を`Launch Contract`として確定する。
9. Routerの実行フレームを終了し、選択Skillを新しいトップレベルのユーザー承認済み起動として1回だけtail-dispatchする。Routerを親にした子セッション／subagentとして起動せず、Routerは処理を代行しない。
10. ランタイムがトップレベル移行を提供できない場合は、`Launch Contract`を返して停止し、ユーザーまたはランタイムに再起動を求める。ネスト実行や代行へフォールバックしない。

## 停止条件

- No match：該当なしの理由と不足している能力を示し、起動せず停止する。
- 同率：差を決める質問を最大3問行う。解消しなければ同率のまま選択を求める。
- 前提不足：本命ランキングを維持し、不足と開始可能にする先行経路を別層で示す。`setup-matt-pocock-skills`を含む先行工程へ自動差し替え・自動起動しない。
- Skill unavailable：非推奨・廃止・アクセス不能・必要入力欠落を示し、利用可能な代替だけを再順位する。
- Top-level transition unavailable：`Launch Contract`を返して停止し、ユーザーまたはランタイムによるトップレベル再起動を求める。
- ユーザー却下：別候補を自動起動せず、再順位・追加質問・停止のどれを望むか確認する。

## 禁止事項

- Router自身が成果物を作成、保存、更新、実装、調査、設定する。
- `artifact-destination`を呼ぶ、または保存先を新たに解決する。
- 索引だけを根拠に最終推薦する。
- 確認前に候補Skillを起動する。
- 選択SkillをRouter配下の子セッション／subagentとしてネスト起動する。
- トップレベル移行失敗時に、Routerが選択Skillまたはその子Skillの固有手順を代行する。
- 前提不足を隠す、または本命を別Skillへ自動差し替えする。
- 候補Skillの手順をRouter本文へ複製する。

## 検証

- RelationとRouting indexのdispatch候補集合が完全一致し、`workflow-router`自身を含まない。
- dispatch候補はRouting indexの34件だけである。内訳は、frontmatterに`disable-model-invocation: true`があるユーザー起動Skill 21件と、モデルからも起動できるSkill 13件（2026-11-25、本家への入れ替え後に数え直した）。
- Router dispatch edgeを通常の逆向き依存違反から除外し、例外要件として別枠検査する。
- Router以外のユーザー起動Skillからユーザー起動Skillへのedgeは0件である。
- 依存グラフに循環がない。
- 上位候補の実Skill本文確認、確認前非起動、承認後exactly-onceのトップレベルtail-dispatch、選択Skillの通常委譲深度の保持、ネスト起動・Router代行の禁止、Routerの成果物非作成を静的に確認する。
- 代表14ケースを実動検証済み。期待本命14/14一致、確認前dispatch 0、成果物作成・保存先解決・外部操作0、13ケース0問、同率ケースのみ1ラウンド2問で、質問上限を満たした。
- 実動検証では、全ケースで上位候補の実Skill本文、起動主体、ライフサイクル、入力、完了条件、対象外を確認した。
- Phase 13で確認UI、Launch Contract継承、exactly-onceのトップレベルtail-dispatch、`research`／`wayfinder`の通常委譲深度、Skill unavailable時の再順位を検証済み。トップレベル移行非提供時はLaunch Contractを返し、ネスト起動・Router代行0でfail-closedする。
- 現行証拠：[Phase 12 workflow-router設計・静的検査](https://app.notion.com/p/a6a8137c13d2427a98df640c4e16fb8e)、[Phase 13 Gate 0–1 検証ログ](https://app.notion.com/p/5e7b9e5b78a44c8a81fa7fb185e83311)、[Phase 13 Gate 2 通しシナリオ検証ログ](https://app.notion.com/p/187b320c8e0d4c1ab3005fc601ca8e4e)、[Phase 13 最終追加検証B — 画像生成境界＋Routerランタイム](https://app.notion.com/p/cdd13415f2ef4a72a5f71307fc1a7737)
- Phase 13の正常系・境界系・unavailable・tail-dispatch非提供検証に合格し、ライフサイクルは`安定版`である。
