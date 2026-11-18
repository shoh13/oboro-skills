#!/usr/bin/env node
// build と domcheck を、検証用データ・従来のデータ・不正なデータ・完成例に対して実行し、期待値と照合する。
// 使い方: NODE_PATH=<jsdom を含む node_modules> node tests/run.mjs
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const BUILD = join(root, 'scripts', 'build.mjs'), DOM = join(root, 'scripts', 'domcheck.cjs');
const out = mkdtempSync(join(tmpdir(), 'doc-state-machine-'));
const strict = process.argv.includes('--strict');
let fails = 0, optionalFails = 0, optional = false;

const show = x => JSON.stringify(x);
function check(name, cond, detail = '') {
  console.log(`${cond ? 'ok  ' : optional ? 'WARN' : 'FAIL'} ${name}${!cond && detail ? `\n       ${detail}` : ''}`);
  if (!cond) optional ? optionalFails++ : fails++;
  return cond;
}
const eq = (name, got, want) => check(`${name}: ${show(got)}`, show(got) === show(want), `期待値 ${show(want)}`);
const section = t => console.log(`\n# ${t}`);
const sorted = o => Object.fromEntries(Object.entries(o || {}).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));

function build(dir, name) {
  const html = join(out, `${name.replace(/\//g, '-')}.html`);
  const r = spawnSync(process.execPath, [BUILD, dir, html], { encoding: 'utf8' });
  return { code: r.status, stdout: r.stdout, stderr: r.stderr, html };
}
function dom(html, expr) {
  const r = spawnSync(process.execPath, [DOM, html, ...(expr ? [expr] : [])], { encoding: 'utf8' });
  try { return JSON.parse(r.stdout); }
  catch { return { errors: [`domcheck の出力を解析できない: ${(r.stdout + r.stderr).slice(0, 400)}`] }; }
}
const json = (dir, name) => JSON.parse(readFileSync(join(dir, name), 'utf8'));
const opt = (dir, name) => (existsSync(join(dir, name)) ? json(dir, name) : undefined);
const toks = s => (typeof s === 'string' ? s.split(/\s+/).filter(Boolean) : []);
const parseH = b => toks(b.h).map(t => { const [sha, x] = t.split(':'); return { sha, k: x[0], i: +x.slice(1) }; });

/* ---------- データから期待値を導出する ---------- */
// build の集計と同じ値を、契約の定義からデータを直接数えて求める。
function summarize(dir) {
  const m = json(dir, 'machine.json'), sts = [...m.flow, ...m.any];
  const tl = opt(dir, 'timeline.json'), hist = opt(dir, 'hist.json') || {}, secs = opt(dir, 'sections.json');
  const branches = sts.flatMap(s => [
    ...(s.rules || []).map((b, i) => ({ b, kind: 'rule', at: `「${s.state}」rule[${i}]` })),
    ...(s.errors || []).map((b, i) => ({ b, kind: 'err', at: `「${s.state}」error[${i}]` })),
    ...((s.table && s.table.cells) || []).map((b, i) => ({ b, kind: 'cell', at: `「${s.state}」table.cells[${i}]` })),
  ]);
  const of = k => branches.filter(x => x.kind === k), cells = of('cell');
  let und = 0;
  for (const { table: t } of sts) if (t) for (let r = 0; r < t.rows.values.length; r++) for (let c = 0; c < t.cols.values.length; c++) {
    if (!t.cells.some(x => x.r === r && x.c === c && (x.to || x.na))) und++;
  }
  const mapped = new Set(branches.flatMap(({ b }) => parseH(b).map(e => `${e.sha}:${e.i}`)));
  const s = {
    tl, hist, branches,
    states: sts.length, rules: of('rule').length, errors: of('err').length,
    cells: cells.length, cellTo: cells.filter(x => x.b.to).length, cellNa: cells.filter(x => !x.b.to && x.b.na).length, und,
    inferred: branches.filter(x => x.b.inferred).length,
    noSrc: branches.filter(x => (x.kind !== 'cell' || x.b.to) && !toks(x.b.src).length && !parseH(x.b).some(e => e.k === 'd')).map(x => x.at),
  };
  const lines = [];
  if (tl) {
    lines.push(`commits: ${tl.length} (対象ファイルを変更: ${Object.keys(hist).length}, 注目: ${tl.filter(e => e.star).length})`);
    lines.push(`changes: ${Object.values(hist).reduce((n, l) => n + l.length, 0)} (枝に対応: ${mapped.size})`);
    lines.push(`states: ${s.states}, rules: ${s.rules} (対応付けなし: ${of('rule').filter(x => !toks(x.b.h).length).length})`);
    const noMap = Object.keys(hist).filter(sha => !hist[sha].some((_, i) => mapped.has(`${sha}:${i}`)));
    lines.push(`枝に対応しないコミット: ${noMap.length ? noMap.join(' ') : 'なし'}`);
  } else lines.push(`states: ${s.states}, rules: ${s.rules}`);
  lines.push(`errors: ${s.errors}, cells: ${s.cells} (記載 ${s.cellTo} / 該当なし ${s.cellNa} / 未規定 ${s.und})`);
  lines.push(`inferred: ${s.inferred}`);
  if (secs) {
    const ref = new Set(branches.flatMap(x => toks(x.b.src)));
    const target = secs.filter(x => !x.skip && x.text), hit = target.filter(x => ref.has(x.id)).length;
    lines.push(`sections: ${secs.length} (網羅の対象 ${target.length}: 参照あり ${hit} / 参照なし ${target.length - hit}, 除外 ${secs.filter(x => x.skip).length}, 見出しのみ ${secs.filter(x => !x.skip && !x.text).length})`);
    lines.push(`src を持たない枝: ${s.noSrc.length} (削除済みを除く)`);
  }
  s.lines = lines;
  return s;
}
function checkLines(b, s) {
  const got = b.stdout.split('\n');
  for (const l of s.lines) check(`build の出力: ${l}`, got.includes(l), b.stdout.trim().split('\n').join('\n       '));
}
// 契約の「版の履歴」の表示の規則から、版ごとの記号・⟳・取り消し線を導出する。キーは「種類 h」。
function expectMarks(s) {
  const pos = Object.fromEntries(s.tl.map((e, i) => [e.sha, s.tl.length - 1 - i]));
  const G = { a: '+', c: '~', d: '−' }, want = {};
  for (const { sha } of [...s.tl].reverse().filter(e => s.hist[e.sha])) {
    const X = pos[sha];
    want[sha] = {};
    for (const { b, kind } of s.branches) {
      const ev = parseH(b).map(e => ({ ...e, p: pos[e.sha] }));
      if (!ev.length) continue;
      const add = ev.find(e => e.k === 'a').p, del = (ev.find(e => e.k === 'd') || { p: Infinity }).p;
      const k = (ev.find(e => e.sha === sha) || {}).k;
      want[sha][`${kind} ${b.h}`] = add <= X && X <= del ? { mk: k ? G[k] : '', lt: ev.some(e => e.k === 'c' && e.p > X), strike: k === 'd' } : { off: true };
    }
  }
  return want;
}

const probe = spawnSync(process.execPath, ['-e', 'require("jsdom")'], { encoding: 'utf8' });
if (probe.status !== 0) {
  console.error('jsdom を読み込めない。NODE_PATH に jsdom を含む node_modules を指定する。');
  process.exit(2);
}
console.log(`出力先: ${out}`);

/* ---------- 1. 検証用データ ---------- */
section('examples/fixture');
{
  const dir = join(root, 'examples', 'fixture'), s = summarize(dir);
  const fx = build(dir, 'fixture');
  if (check('build が成功する', fx.code === 0, fx.stderr.trim())) {
    checkLines(fx, s);
    check('build が未規定の欄を出力する', /未規定: 「更新」会員・期限の設定なし × 使用時 \(issue: i2\)/.test(fx.stdout), fx.stdout);
    const d = dom(fx.html, readFileSync(join(root, 'tests', 'fixture-dom.js'), 'utf8'));
    eq('読み込み時の例外', d.errors, []);
    if (d.exprError) check('検査式の例外', false, d.exprError);
    const x = d.expr || {};
    eq('状態への矢印', x.wires, 5);
    eq('flow の暗黙の接続 (.lead・疑似状態)', x.leads, 0);
    eq('エラーの折り畳み', x.folds, 1);
    eq('折り畳みの件数', x.foldCount, [String(s.errors)]);
    eq('同じ遷移先でまとめたエラーの群', x.errGroups, 3);
    eq('初期状態で開いている折り畳み', x.foldOpen, 0);
    eq('判定表の未規定の欄', x.und, s.und);
    eq('判定表の該当なしの欄', x.na, s.cellNa);
    eq('判定表の記載済みの欄', x.cellTo, s.cellTo);
    eq('原文タブの節', x.srcItems, 7);
    eq('原文タブの tab ごとの見出し', x.srcHeads, ['総論2', 'Web 用4', '端末用1']);
    eq('指摘タブの指摘', x.issItems, 3);
    eq('枝の属性の印 (why / std / issue / trial / inferred)', x.marks, { why: 2, std: 3, issue: 3, trial: 1, inferred: s.inferred });
    eq('「すべて」での用途の印を持つ枝', x.varMarks, 17);
    eq('「すべて」で表示中の枝', x.shownAll, s.rules + s.errors + s.cellTo);
    eq('指摘 i1 の選択で折り畳みが開く', x.afterIssue, { open: 1, pick: 1, tab: 'iss' });
    eq('状態チップの選択で対象の状態を示す', x.goState, '受付');
    eq('折り畳みの見出しの選択で開閉する', x.foldToggle, [true, false]);
    eq('枝の選択で原文の節を表示する', x.ruleToSrc, { tab: 'src', on: ['s2', 's5'] });
    const dev = x.dev || {}, web = x.web || {};
    eq('用途「端末用」で表示中の枝', dev.shown, 7);
    eq('用途「端末用」で表示中の状態', dev.states, ['入口', '受付', '発行']);
    eq('用途「端末用」での矢印', dev.wires, 2);
    eq('用途「端末用」での折り畳みの件数', dev.foldCount, ['2']);
    eq('用途「端末用」で showAt を再実行した後', x.devAfterShowAt, { shown: 7, states: 3, wires: 2 });
    eq('用途の切り替えで選択を解除する', x.varClearsPick, { pick: 0, picking: false });
    eq('用途「端末用」で非表示の状態の欄へ移動しない (指摘 i2)', x.devHiddenIssue, { hiddenPick: 0, picking: false });
    eq('用途「Web 用」で表示中の枝', web.shown, 16);
    eq('用途「Web 用」での矢印', web.wires, 4);
    eq('用途「すべて」へ戻した後', x.back, { shown: 20, states: 4, wires: 5 });
    eq('時点の UI を非表示にする', x.nohist, true);
    eq('全ての枝・エラー・欄が記号と ⟳ の実要素を持ち、履歴なしでは表示しない', x.hmarks, { each: true, shown: 0 });
    eq('凡例の符号 (使用しているものだけ)', x.legend, { std: 3, issue: 3, level: 3, und: 1 });
  }
}

/* ---------- 1'. 検証用データに版の履歴を加えたデータ ---------- */
section('tests/history');
{
  const dir = join(root, 'tests', 'history'), s = summarize(dir), meta = json(dir, 'meta.json');
  const b = build(dir, 'history');
  if (check('build が成功する (削除済みの枝は src を持たない)', b.code === 0, b.stderr.trim())) {
    checkLines(b, s);
    check(`build が src を持たない枝を注記する: ${s.noSrc.join(', ')}`, s.noSrc.length > 0 && b.stdout.includes(`note: src を持たない枝 (削除済みを除く) ${s.noSrc.length} 件: ${s.noSrc.join(', ')}`), b.stdout);
    const d = dom(b.html, readFileSync(join(root, 'tests', 'history-dom.js'), 'utf8'));
    eq('読み込み時の例外', d.errors, []);
    if (d.exprError) check('検査式の例外', false, d.exprError);
    const x = d.expr || {}, want = expectMarks(s);
    const newest = s.tl.find(e => s.hist[e.sha]), link = e => (e.pr ? meta.link.pr.replace('{pr}', e.pr) : meta.link.commit.replace('{sha}', e.sha));
    const marked = (sha, f) => Object.values(want[sha]).filter(f).length;
    // エラーの件数と群: 時点で表示されるエラー。「最新」では削除の時点のエラーを除く。
    const errsAt = (sha, nodiff) => s.branches.filter(e => {
      if (e.kind !== 'err') return false;
      const w = e.b.h ? want[sha][`err ${e.b.h}`] : {};
      return !w.off && !(nodiff && w.strike);
    });
    const errView = (sha, nodiff) => ({ foldCount: [String(errsAt(sha, nodiff).length)], groups: new Set(errsAt(sha, nodiff).map(e => show(e.b.to))).size });

    const seen = new Set();
    for (const t of Object.values(want)) for (const [key, v] of Object.entries(t)) {
      const kind = key.split(' ')[0];
      if (v.mk) seen.add(`${kind} ${v.mk}`);
      if (v.lt) seen.add(`${kind} ⟳`);
      if (v.strike) seen.add(`${kind} 取り消し線`);
    }
    const need = ['rule', 'err', 'cell'].flatMap(k => ['+', '~', '−', '⟳', '取り消し線'].map(m => `${k} ${m}`));
    eq('検査データが通常の枝・エラー・欄ごとに + ~ − ⟳ 取り消し線を含む (不足)', need.filter(m => !seen.has(m)), []);
    for (const sha of Object.keys(want)) eq(`版 ${sha} の記号・⟳・取り消し線`, sorted((x.marks || {})[sha]), sorted(want[sha]));

    eq('最新の版: タブ・強調・自動で開く折り畳み・meta.link', x.start, {
      cur: newest.sha, tabs: ['now', 'all', 'src', 'iss'], nohist: false, hot: marked(newest.sha, v => v.mk), cards: s.hist[newest.sha].length,
      foldAuto: 1, foldCount: errView(newest.sha).foldCount, link: link(newest),
    });
    const B = 'bbbbbbb', atB = nodiff => ({
      mk: nodiff ? 0 : marked(B, v => v.mk), lt: marked(B, v => v.lt), delShown: nodiff ? 0 : marked(B, v => v.strike), ...errView(B, nodiff),
    });
    eq('削除を含む版: 差分', x.diffAtB, { link: link(s.tl.find(e => e.sha === B)), ...atB(false) });
    eq('削除を含む版: 最新 (記号と削除の枝を非表示、⟳ は表示、エラーの件数・群から除く)', x.nodiffAtB, atB(true));
    eq('削除を含む版: 差分へ戻した後', x.backAtB, atB(false));
    eq('古い版: 時点で非表示のエラーと欄', x.older, { off: 2, shown: 21, foldCount: errView('aaaaaaa').foldCount, foldOpen: 1, void: 1 });
    eq('古い版 × 用途「Web 用」', x.olderWeb, { shown: 17, foldCount: ['4'], states: 4 });
    eq('最新の版 × 用途「Web 用」', x.newerWeb, { shown: 16, foldCount: ['4'], foldAuto: 1 });
    eq('古い版 × 用途「端末用」', x.olderDev, { shown: 7, states: 3, foldCount: ['2'] });
    eq('強調中のエラーの選択でカードを開く', x.tapHot, { tab: 'now', card: 'bbbbbbb:0' });
  }
}

/* ---------- 2・3. 従来のデータ ---------- */
// 期待値は、データの更新に追従するようデータから導出する。
function legacy(dir, name, extra = {}) {
  section(name);
  if (!check('データがある', existsSync(join(dir, 'machine.json')), dir)) return;
  const s = summarize(dir), m = json(dir, 'machine.json'), tl = s.tl, hist = s.hist;
  const newest = tl.find(e => hist[e.sha]) || tl[0];
  const b = build(dir, name);
  if (!check('build が成功する', b.code === 0, b.stderr.trim())) return;
  checkLines(b, s);
  const d = dom(b.html, '({ cur, hot: document.querySelectorAll(".rule.hot").length, mk: document.querySelectorAll(".hmk:not([hidden])").length, cards: document.querySelectorAll(".card").length, ev: document.querySelectorAll(".ev").length, leads: document.querySelectorAll(".lead").length, nohist: document.getElementById("app").classList.contains("nohist") })');
  eq('読み込み時の例外', d.errors, []);
  eq('状態', [d.states, d.clusters], [s.states, s.states + 2]);
  eq('枝', d.rules, s.rules);
  if (extra.rules) eq('枝 (件数の指定)', d.rules, extra.rules);
  eq('矢印', d.wires, 0);
  const x = d.expr || {};
  eq('最新の版を表示する', x.cur, newest.sha);
  eq('カード', x.cards, (hist[newest.sha] || []).length);
  eq('暗黙の接続 (.lead)', x.leads, m.flow.length + 1);
  eq('時点の UI を表示する', x.nohist, false);
  eq('表示中の記号の実要素 = 強調中の枝', x.mk, x.hot);
  if (extra.hot) check(`強調中の枝がある: ${x.hot}`, x.hot > 0);
  if (extra.ev) check(`全履歴の項目がある: ${x.ev}`, x.ev > 0);
}
legacy(join(root, 'tests', 'legacy', 'poteto-mode'), 'tests/legacy/poteto-mode', { rules: 139, hot: true, ev: true });

/* ---------- 4. 不正なデータ ---------- */
section('到達性 (build の出力)');
{
  const fx = join(root, 'examples', 'fixture');
  const ok = build(fx, 'reach-ok');
  check('全ての用途で到達できる場合は到達の件数を出力し、注記を出さない', ok.code === 0 && /到達 \(端末用\): (\d+) \/ \1/.test(ok.stdout) && !ok.stdout.includes('到達できない状態'), ok.stdout);
  const dir = mkdtempSync(join(tmpdir(), 'reach-'));
  for (const f of readdirSync(fx)) copyFileSync(join(fx, f), join(dir, f));
  const m = JSON.parse(readFileSync(join(dir, 'machine.json'), 'utf8'));
  m.flow[0].rules = m.flow[0].rules.filter(r => !(r.for || []).includes('dev'));
  writeFileSync(join(dir, 'machine.json'), JSON.stringify(m));
  const ng = build(dir, 'reach-ng');
  check('遷移を除去した用途で、到達できない状態を注記する', ng.code === 0 && /note: 到達できない状態 \(端末用\): 受付/.test(ng.stdout), ng.stdout + ng.stderr);
}

section('tests/md (scripts/extract-md.mjs)');
{
  const EXTRACT = join(root, 'scripts', 'extract-md.mjs'), md = join(root, 'tests', 'md', 'sample.md');
  const run = (...a) => spawnSync(process.execPath, [EXTRACT, md, ...a], { encoding: 'utf8' });
  const full = run('--items', '--arrows', '--ids', '--url', 'https://example.com/blob/abc/sample.md');
  const want = readFileSync(join(root, 'tests', 'md', 'expected.json'), 'utf8');
  check('--items --arrows --ids の出力が期待値と一致する', full.status === 0 && full.stdout === want, full.stderr || full.stdout);
  const itemsOnly = run('--items');
  const ids = itemsOnly.status === 0 ? JSON.parse(itemsOnly.stdout).map(s => s.id) : [];
  check('--arrows なしでは矢印の箇条書きを分割しない', !ids.some(id => id.endsWith('/パスエイリアス')) && ids.includes('sampledoc/規則/investigation'), ids.join(' '));
  check('--ids なしでは ID の箇条書きを分割しない', !ids.some(id => /\/r5-1$|\/ac17$/.test(id)), ids.join(' '));
  const bad = run('--itemz');
  check('未定義のオプションで失敗する', bad.status === 2 && bad.stderr.includes('未定義のオプション'), bad.stderr);
}

section('tests/invalid');
{
  const base = join(root, 'tests', 'invalid');
  for (const name of readdirSync(base).sort()) {
    const dir = join(base, name);
    if (!existsSync(join(dir, 'expect.txt'))) continue;
    const want = readFileSync(join(dir, 'expect.txt'), 'utf8').trim();
    const b = build(dir, `invalid-${name}`);
    check(`${name}: build が失敗し「${want}」を出力する`, b.code === 1 && b.stderr.includes(want), `exit ${b.code}\n       ${(b.stderr || b.stdout).trim().split('\n').join('\n       ')}`);
  }
}

/* ---------- 5. 完成例 ---------- */
section('examples/poteto-mode');
{
  const dir = join(root, 'examples', 'poteto-mode');
  const b = build(dir, 'poteto-mode');
  console.log(b.stdout.trim().split('\n').map(l => `       ${l}`).join('\n'));
  if (check('build が成功する', b.code === 0, (b.stderr || b.stdout).trim())) {
    check('原文の節の網羅が完全', /参照なし 0/.test(b.stdout), b.stdout);
    const d = dom(b.html);
    eq('読み込み時の例外', d.errors, []);
    console.log(`       states ${d.states}, rules ${d.rules}, wires ${d.wires}`);
  }
}

console.log(`\n${fails ? `FAIL ${fails} 件` : 'すべて成功'}${optionalFails ? ` (作成中の例の警告 ${optionalFails} 件)` : ''}`);
process.exit(fails ? 1 : 0);
