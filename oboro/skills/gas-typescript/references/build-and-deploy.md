# GAS + TypeScript ビルドと配布

## ビルド境界

```text
TypeScript source → bundler/build → GAS向けJavaScript + appsscript.json → clasp push
```

## 必須確認

- 使用中のclasp、バンドラ、GASランタイムのバージョンを確認する。
- `doGet`、`doPost`、トリガー、手動実行関数の一覧を作る。
- ビルド後に公開関数がトップレベルへ残る設定を使う。
- tree-shakingで消える関数は明示的な公開一覧へ追加する。
- claspのroot directoryをビルド成果物へ限定する。
- 既存のscript IDとデプロイ識別子を維持する。

## 成果物検査

- import、export、requireなど、GAS実行時に解決できない記法が残っていない。
- ソースマップ、テスト、秘密情報、ローカル設定が配布対象へ入っていない。
- `appsscript.json`が成果物と同じ配布ルートにある。
- 公開関数名がビルド前後で一致する。

## 配布前確認

1. 型検査、テスト、ビルドを実行する。
2. 配布されるファイル一覧を表示する。
3. script ID、デプロイ先、既存URLへの影響を確認する。
4. ユーザー確認後にpushまたはdeployする。
5. 本番の入口関数をスモークテストする。

## 移行

既存の単一ファイルGASをTypeScriptへ移す場合も、半端な状態を配布しない。純粋ロジック、adapter、service、entrypointの順に構築し、旧実装は本番スモークテストが通るまで削除しない。
