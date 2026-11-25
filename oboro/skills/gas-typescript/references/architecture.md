# GAS + TypeScript アーキテクチャ

## 依存方向

```text
entrypoints → services → domain
                  ↓
               adapters
```

- `domain`: 計算、検証、変換、ペイロード生成などの純粋ロジック。GASグローバルへ依存しない。
- `adapters`: `UrlFetchApp`、`PropertiesService`、`Utilities`などを薄く包む。
- `services`: domainとadaptersを組み合わせるユースケース。
- `entrypoints`: `doGet`、`doPost`、トリガー、手動実行関数と依存注入だけを持つ。

## 推奨構成

```text
src/
  entrypoints/
  services/
  domain/
  adapters/
dist/
test/
```

## 原則

- 時刻、乱数、外部I/Oを引数またはインターフェースで注入する。
- entrypointsをcomposition rootにする。
- servicesはGAS実装ではなくadapter interfaceへ依存する。
- domainは最も厚く、entrypointsは最も薄くする。
- 実行環境の都合をドメイン用語へ持ち込まない。
