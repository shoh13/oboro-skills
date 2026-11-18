// examples/fixture をコピーし、1か所だけ改変した不正なデータの事例を tests/invalid/<事例名>/ に生成する。
import { mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const fx = join(root, 'examples', 'fixture');
const files = ['meta.json', 'machine.json', 'sections.json', 'issues.json'];
const raw = Object.fromEntries(files.map(f => [f, readFileSync(join(fx, f), 'utf8')]));

// 改変は元のファイルの文字列置換で行い、それ以外の箇所の書式を保つ。
const cases = {
  'state-target-missing': ['machine.json', '{"g":"Web からの要求","to":[["state","受付"]]', '{"g":"Web からの要求","to":[["state","受付X"]]', '遷移先の状態「受付X」が存在しない'],
  'flow-with-state': ['meta.json', '"transitions": "explicit"', '"transitions": "flow"', 'transitions が "flow" なのに遷移先 ["state"'],
  'src-missing': ['machine.json', '{"g":"署名の検証","to":[["act","実施"]],"for":["dev"],"src":"s5"', '{"g":"署名の検証","to":[["act","実施"]],"for":["dev"],"src":"s9"', 'src の節「s9」が存在しない'],
  'section-duplicate': ['sections.json', '{ "id": "s6"', '{ "id": "s5"', 'sections[6]: id「s5」が重複'],
  'section-unreferenced':['sections.json', '  { "id": "s6"', '  { "id": "s7", "tab": "端末用", "level": 3, "title": "未対応の節", "url": "https://example.com/spec#s7", "text": "どの枝からも参照しない規定。" },\n  { "id": "s6"', '節「s7」(未対応の節) がどの枝・エラー・判定表の欄の src からも参照されていない'],
  'for-missing': ['machine.json', '"to":[["ticket","整理券","受付後に発行する"],["m","30 分"]],"for":["web","dev"],', '"to":[["ticket","整理券","受付後に発行する"],["m","30 分"]],', 'meta.variants があるのに for がない'],
  'variant-undefined': ['machine.json', '"to":[["ticket","整理券","受付後に発行する"],["m","30 分"]],"for":["web","dev"],', '"to":[["ticket","整理券","受付後に発行する"],["m","30 分"]],"for":["web","dev","tv"],', 'for の用途「tv」が未定義'],
  'cell-out-of-range': ['machine.json', '{ "r": 2, "c": 0, "to": [["m", "1 日"]]', '{ "r": 3, "c": 0, "to": [["m", "1 日"]]', '(r 3, c 0) が判定表の範囲 (3 行 × 2 列) の外'],
  'h-without-timeline': ['machine.json', '{"g":"Web からの要求","to":[["state","受付"]],"for":["web"],"src":"s0"}', '{"g":"Web からの要求","to":[["state","受付"]],"for":["web"],"src":"s0","h":"abcdef1:a0"}', 'timeline.json がないのに h (対応付け) がある'],
  'level-invalid': ['machine.json', '"src":"s5","level":"should"', '"src":"s5","level":"recommended"', 'level「recommended」は'],
  'inferred-empty': ['machine.json', '"inferred":"原文は Web 用の POST を明記していない"', '"inferred":""', 'inferred は空でない文字列にする'],
  'cell-for-overlap': ['machine.json', '        { "r": 0, "c": 1,', '        { "r": 0, "c": 0, "to": [["m", "3 日"]], "for": ["web"], "src": "s4" },\n        { "r": 0, "c": 1,', 'と for が重なる'],
  'state-duplicate': ['machine.json', '{ "state": "入口"', '{ "state": "受付"', 'state「受付」が重複'],
  'kind-undefined': ['machine.json', '[["ticket","整理券"', '[["tkt","整理券"', '遷移先の種別「tkt」が未定義'],
  'issue-missing': ['machine.json', '"level":"should","issue":"i3"', '"level":"should","issue":"i9"', 'issue の指摘「i9」が存在しない'],
  'std-invalid': ['machine.json', '"std":["eq"]', '"std":["same"]', 'std は [種類, 説明] または [種類] にする'],
  'state-not-last': ['machine.json', '"to":[["act","受け付ける"],["state","発行"]]', '"to":[["state","発行"],["act","受け付ける"]]', '遷移先 ["state", "発行"] は配列の末尾に置く'],
  'issue-type-invalid': ['issues.json', '"id": "i3", "type": "note"', '"id": "i3", "type": "memo"', 'type「memo」は'],
  'state-empty': ['machine.json', '"any": [\n', '"any": [\n  { "state": "空" },\n', 'state「空」: rules・errors・table が全て空'],
};

const base = join(root, 'tests', 'invalid');
rmSync(base, { recursive: true, force: true });
for (const [name, [file, from, to, expect]] of Object.entries(cases)) {
  const dir = join(base, name);
  mkdirSync(dir, { recursive: true });
  for (const f of files) {
    let s = raw[f];
    if (f === file) {
      const n = s.split(from).length - 1;
      if (n !== 1) throw new Error(`${name}: 置換対象が ${n} 件`);
      s = s.replace(from, () => to);
    }
    writeFileSync(join(dir, f), s);
  }
  writeFileSync(join(dir, 'expect.txt'), expect + '\n');
}
console.log(Object.keys(cases).length, 'cases');
