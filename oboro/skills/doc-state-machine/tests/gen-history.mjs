// examples/fixture に版の履歴を加えたデータを tests/history/ に生成する。
// 通常の枝・エラー・判定表の欄のそれぞれに、追加 (a)・変更 (c)・削除 (d) の対応付けを1件以上持たせる。
// 版の位置: aaaaaaa (0) → ddddddd (1, 枝に対応しない) → bbbbbbb (2) → ccccccc (3, 最新)。
import { mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const fx = join(root, 'examples', 'fixture');
const dir = join(root, 'tests', 'history');
rmSync(dir, { recursive: true, force: true });
mkdirSync(dir, { recursive: true });
const rep = (s, from, to) => {
  const n = s.split(from).length - 1;
  if (n !== 1) throw new Error(`置換対象が ${n} 件: ${from}`);
  return s.replace(from, () => to);
};
let meta = readFileSync(join(fx, 'meta.json'), 'utf8');
meta = rep(meta, '  "levelLabels": { "should": "望ましい" }\n', '  "levelLabels": { "should": "望ましい" },\n  "link": { "commit": "https://example.com/spec/commit/{sha}", "pr": "https://example.com/spec/pull/{pr}" },\n  "areas": ["受付", "更新"]\n');

let machine = readFileSync(join(fx, 'machine.json'), 'utf8');
// 通常の枝: 変更 (ccccccc) と、src を持たない削除済みでない枝。削除 (bbbbbbb) の枝は src を持たない。
machine = rep(machine, '{"g":"署名の検証","to":[["act","実施"]],"for":["dev"],"src":"s5","level":"should","issue":"i3","gap":true}',
  '{"g":"署名の検証","to":[["act","実施"]],"for":["dev"],"level":"should","issue":"i3","gap":true,"h":"aaaaaaa:a0 ccccccc:c2"}');
machine = rep(machine, '{"g":"拡張ヘッダ","to":[["act","対応してもよい"]],"for":["web"],"src":"s2","level":"may","inferred":"検証用の例"}',
  '{"g":"拡張ヘッダ","to":[["act","対応してもよい"]],"for":["web"],"src":"s2","level":"may","inferred":"検証用の例"},\n      {"g":"GET リクエスト","to":[["act","受け付ける"]],"for":["web"],"h":"aaaaaaa:a0 bbbbbbb:d4"}');
// エラー: 追加 (bbbbbbb)・変更 (ccccccc)・削除 (bbbbbbb)。削除するエラーは単独の群にする。
machine = rep(machine, '"src":"s2","issue":"i1"}', '"src":"s2","issue":"i1","h":"bbbbbbb:a0"}');
machine = rep(machine, '"why":"RFC 9999","inferred":"検証用の例"}', '"why":"RFC 9999","inferred":"検証用の例","h":"aaaaaaa:a0 ccccccc:c0"}');
machine = rep(machine, '"std":["dev","RFC 9999 では無視すると規定"],"inferred":"検証用の例"}',
  '"std":["dev","RFC 9999 では無視すると規定"],"inferred":"検証用の例"},\n      {"g":"id が旧形式","to":[["stop","旧形式のエラー"]],"for":["web"],"h":"aaaaaaa:a0 bbbbbbb:d2"}');
// 判定表の欄: 追加 (bbbbbbb)・変更 (ccccccc)・削除 (bbbbbbb)。
machine = rep(machine, '{ "r": 0, "c": 0, "to": [["m", "7 日"]], "for": ["web"], "src": "s4" }', '{ "r": 0, "c": 0, "to": [["m", "7 日"]], "for": ["web"], "src": "s4", "h": "bbbbbbb:a1" }');
machine = rep(machine, '{ "r": 2, "c": 0, "to": [["m", "1 日"]], "for": ["web"], "src": "s4" }', '{ "r": 2, "c": 0, "to": [["m", "1 日"]], "for": ["web"], "src": "s4", "h": "aaaaaaa:a0 ccccccc:c1" }');
machine = rep(machine, '{ "r": 1, "c": 0, "na": "期限の設定がない場合は発行時の規定の対象外" },',
  '{ "r": 1, "c": 0, "na": "期限の設定がない場合は発行時の規定の対象外" },\n        { "r": 1, "c": 0, "to": [["m", "14 日"]], "for": ["web"], "h": "aaaaaaa:a0 bbbbbbb:d3" },');

writeFileSync(join(dir, 'meta.json'), meta);
writeFileSync(join(dir, 'machine.json'), machine);
for (const f of ['sections.json', 'issues.json']) writeFileSync(join(dir, f), readFileSync(join(fx, f), 'utf8'));
writeFileSync(join(dir, 'timeline.json'), `[
  {"sha":"ccccccc","date":"2026-03-01","title":"\`id\` の空白の扱い・非会員の期限・署名の検証を変更","add":3,"del":3,"star":true},
  {"sha":"bbbbbbb","date":"2026-02-01","title":"\`id\` の文字数のエラーと更新の期限を追加し、旧形式と GET を削除","add":12,"del":6,"pr":12,"star":true},
  {"sha":"ddddddd","date":"2026-01-15","title":"用語の表記を統一","add":2,"del":2},
  {"sha":"aaaaaaa","date":"2026-01-01","title":"初版","add":120,"del":0,"star":true}
]
`);
writeFileSync(join(dir, 'hist.json'), `{
"ccccccc": [
  ["c",0,"\`id\` に空白を含む場合の結果を変更","\`id\` に空白を含む場合は 400 エラーとする。","\`id\` に空白を含む場合はエラーとする。"],
  ["c",1,"非会員の発行時の期限を変更","非会員は発行時の期限を 2 日とする。","非会員は発行時の期限を 1 日とする。"],
  ["c",0,"署名の検証を望ましいへ変更","端末用は署名を検証する。","端末用は署名を検証することが望ましい。"]
],
"bbbbbbb": [
  ["a",0,"\`id\` の文字数のエラーを追加","","\`id\` が3文字未満の場合はエラーとする。"],
  ["a",1,"会員の発行時の期限を追加","","会員で期限の設定ありは、発行時の期限を 7 日とする。"],
  ["d",0,"旧形式の \`id\` のエラーを削除","旧形式の \`id\` はエラーとする。",""],
  ["d",1,"期限の設定なしの発行時の期限を削除","会員で期限の設定なしは、発行時の期限を 14 日とする。",""],
  ["d",0,"GET リクエストの受け付けを削除","Web 用は GET リクエストを受け付ける。",""]
],
"ddddddd": [
  ["c",0,"用語の表記を統一","「受け付け」と「受付」が混在している。","「受付」に統一する。"]
],
"aaaaaaa": [
  ["a",0,"初版","","受付と発行の規定を記載する。"]
]
}
`);
console.log('ok', dir);
