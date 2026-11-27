---
name: evidence-research
description: "親ワークフローから渡された明確な問いを、指定範囲・基準日・証拠水準に従って一次情報中心に調査し、主張、根拠、相違、不確実性を構造化した副作用なしの証拠パケットとして返す。保存先決定、成果物の永続化、意思決定、次工程の開始には使わない。"
user-invocable: false
---

明確な問いを一次情報へ遡って調べ、親ワークフローが判断や成果物に利用できる証拠パケットを返す。書き込みはしない。

## 完了条件

- 問い、対象範囲、基準日、必要な証拠水準が明確である。
- 親がsource scopeを指定した場合、Hard Source Allowlistと`source_scope_hash`が起動時に凍結されている。同じsource集合なら、問い、test condition、label、取得順に関係なく同じhashになる。
- 重要な主張がHard Source Allowlist内の一次情報源または実物のソースコードへ直接結び付いている。
- すべてのclaimのsource pointerがHard Source Allowlist内の安定識別子と一致している。
- 情報源間の相違、適用条件、未確認事項が区別されている。
- 親がそのまま利用できる構造化された証拠パケットを返している。
- 保存、公開、意思決定、次工程の開始を行っていない。

## 入力Contract

親から次を受け取る。

- 調査する1つの問い。
- 対象範囲と対象外。
- 時間的な基準日または対象バージョン。
- 必要な証拠水準。
- source scope。指定する場合は、許可するURL、Notion page ID、Repoとpath、添付本文またはそのcontent hash、ドメインallowlistなどを列挙する。
- 親の共通実行コンテキストのうち、環境、対象、適用ポリシー、確認済み事項、作業範囲、禁止範囲。
- 任意の時間・件数・ソース制約。

問いが複数の独立した判断を含む場合は、親へ分割案を返す。対象範囲または証拠水準が不足し、結果を大きく変える場合だけユーザーへ確認する。指定済みsource scopeへのアクセス不能、不存在、権限不足は確認や代替探索へ進めず、`source_unavailable`として停止する。

## 出力Contract

次の証拠パケットを親へ返す。

- **Question：**調査した問い。
- **Scope：**対象、対象外、基準日、バージョン、凍結したHard Source Allowlist、`source_scope_hash`。source scope未指定で探索した場合は、探索範囲と各sourceの採用理由も含める。
- **Target identity：**調査対象のサービス、アカウント、環境、Repo、pageなど、後続がpacketの対象一致を検査できる安定識別子。
- **Retrieved at：**各sourceを取得・確認した時点。
- **Findings：**結論候補ではなく、根拠で確認できたclaims。
- **Evidence：**各claimに対応するallowlist内の安定識別子、該当箇所、確認日、source pointer。
- **Conflicts：**情報源間の差と、差が生じる条件。
- **Uncertainty：**未確認、推測、証拠不足。
- **Implications：**親の判断へ与える影響。判断そのものは行わない。
- **Next lookup：**証拠不足を解消する追加調査案。現在のallowlist外は候補として示すだけで、同一実行では取得・採用しない。

`source_unavailable`または範囲外pointerを検出した場合は証拠パケットを返さず、failure type、対象descriptor、停止理由、再開条件だけを返す。

## 手順

1. 入力Contractを検査し、問いを1つの検証可能な形へ言い換える。
2. 親からsource scopeが渡された場合、各sourceをsource typeと安定識別子だけからなるcanonical descriptorへ正規化する。Notionはcanonical page UUID、Webはnormalized URL、Repoはrepo identity＋refまたはcommit＋normalized path、attachmentはcontent hashを使う。descriptorを完全一致でdedupeし、lexicographic sortした配列をcanonical JSONへ直列化し、そのUTF-8 bytesをhashして`source_scope_hash`とする。表示名、問い、claim、権限状態、test condition、label、取得順はhash入力へ含めない。正規化結果をHard Source Allowlistとして凍結し、descriptorの名前一致だけで同一sourceとみなさない。

`MockCtl`の同じNotion pageだけをscopeにする静的例では、問いが「導入手順」でも「必要権限」でも、test conditionやlabel、取得順が異なっても、canonical descriptorは常に`{"source_type":"notion","stable_id":"<canonical MockCtl page UUID>"}`の1件だけになり、同じ`source_scope_hash`を返す。

3. 「このREADMEのみ」「指定2ページのみ」などの限定がある場合、allowlist外の検索、同名候補、関連ドメイン、一般Web、別Repoへ探索を広げない。指定sourceへアクセスできない、不存在、権限不足のいずれかなら`source_unavailable`として即停止し、代替sourceを検索・推測・利用しない。
4. source scopeが未指定の場合だけ、公式ドキュメント、仕様、標準、ソースコード、リリースノート、第一当事者の記録を優先して探索する。二次情報または検索結果は探索の入口に限り、採用するsourceと理由を記録してからHard Source Allowlistを凍結する。
5. 凍結したallowlist内だけで調査し、各情報源について、何が分かるか、適用条件、対象バージョン、確認日を記録する。
6. 重要な主張は、allowlistが複数sourceを許可する場合に限り、可能な範囲で複数の一次情報または実物の挙動と照合する。
7. 情報源が矛盾する場合は、新しさ、権威性、対象バージョン、適用範囲を比較し、差を隠さない。
8. 証拠が不足する部分を「未確認」として分離し、もっともらしい説明で埋めない。allowlist外sourceが必要でも同一実行では自己拡張しない。親が明示的にscope拡張を承認した新しい起動だけが、変更後のallowlistを作成できる。
9. 各claimのsource pointerを安定識別子でHard Source Allowlistと完全照合する。範囲外pointerが1件でもあれば証拠パケットを返さず、fail-fastする。
10. 全pointerがallowlist内である場合だけ、出力Contractの順に証拠パケットを組み立て、親へ返す。

## 判断基準

- 親が指定したsource scopeは探索候補ではなくHard Source Allowlistである。
- sourceの同一性は名前や説明ではなく、source typeと安定識別子だけで判定する。
- `source_scope_hash`はsource集合の同一性だけを表し、問い、claim、表示情報、権限状態、test condition、label、取得順には依存させない。
- 一次情報を所有する主体に近いほど重く扱う。ただし明示allowlistの外へ出る理由にはならない。
- ソースコードと説明文が食い違う場合は、実行時バージョンとコードの状態を明示する。
- 時間依存の主張には確認日と対象バージョンを付ける。
- 親が必要とする判断に関係しない情報は集めない。
- 調査の不足と、問い自体の未決定を混同しない。
- implicationsは証拠から直接導ける範囲に留める。

## 禁止事項

- 保存先を解決する、またはNotion、Repo、Issueへ書き込む。
- 親に代わって意思決定する。
- 二次情報または検索結果の抜粋だけで重要な事実を確定する。
- 出典なしの一般知識や記憶で証拠を補う。
- 未確認事項を事実として書く。
- 明示されたHard Source Allowlistの外を検索、取得、推測、引用、採用する。
- source descriptorの名前一致だけで同一sourceとみなす。
- 同一実行でallowlistを自己拡張する。
- 別のユーザー起動ワークフローを開始する。

## 検証

- 限定READMEだけを指定した正常系で、そのREADMEだけから証拠パケットを返す。
- 限定READMEと同名の公開情報が見つかっても検索・取得・採用を拒否する。
- 指定sourceが不存在、アクセス不能、権限不足なら`source_unavailable`で即停止し、代替sourceを使わない。
- claimにallowlist外pointerを1件混入させた場合、証拠パケットを返さずfail-fastする。
- 各重要な事実からallowlist内の一次情報源へ到達できることを確認する。
- 引用または要約が元の情報源の意味を変えていないことを確認する。
- 基準日、対象バージョン、適用範囲、Hard Source Allowlist、`source_scope_hash`、Target identity、Retrieved atが明示されていることを確認する。
- 同じsource集合について問い、test condition、label、取得順を変えても`source_scope_hash`が不変であることを確認する。
- 同じMockCtl Notion page単独scopeの静的fixtureが常に同じhashになることを確認する。
- すべてのclaimのsource pointerが安定識別子でallowlist内と完全一致することを確認する。
- 事実、相違、不確実性、含意が混ざっていないことを確認する。
- 書き込み、保存先決定、意思決定を行っておらず、副作用が0であることを確認する。
