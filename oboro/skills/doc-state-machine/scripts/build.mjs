#!/usr/bin/env node
// データ (meta / machine / sections / issues / timeline / hist) を検査し、テンプレートへ埋め込んで単一の HTML を出力する。
// 使い方: node build.mjs <data-dir> <out.html>
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const [dataDir, outPath] = process.argv.slice(2);
if (!dataDir || !outPath) {
  console.error('usage: node build.mjs <data-dir> <out.html>');
  process.exit(2);
}
const here = dirname(fileURLToPath(import.meta.url));
const dir = resolve(dataDir);
const load = (name, optional) => {
  const p = join(dir, name);
  if (optional && !existsSync(p)) return undefined;
  try { return JSON.parse(readFileSync(p, 'utf8')); }
  catch (e) { console.error(`${name}: ${e.message}`); process.exit(2); }
};
const meta = load('meta.json'), machine = load('machine.json');
const timeline = load('timeline.json', true), hist = load('hist.json', true);
const sections = load('sections.json', true), issues = load('issues.json', true);
const HAS_TL = timeline !== undefined;

const errors = [], notes = [];
const err = m => errors.push(m);
const BUILTIN = ['skill', 'prin', 'pb', 'act', 'stop', 'm'];
const LEVELS = ['must', 'should', 'may', 'deferred', 'trial'];
const STD = ['eq', 'strict', 'dev'];
const ISSUE_TYPES = ['conflict', 'gap', 'ambiguous', 'note'];
const isObj = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const isStr = x => typeof x === 'string' && x.length > 0;
const toks = s => (typeof s === 'string' ? s.split(/\s+/).filter(Boolean) : []);

/* ---------- meta ---------- */
if (!isObj(meta)) { console.error('meta.json はオブジェクトにする'); process.exit(1); }
if (!isStr(meta.title)) err('meta.title がない');
for (const k of ['brand', 'name', 'anyLabel', 'slug', 'fileLabel', 'file', 'repoUrl']) {
  if (meta[k] !== undefined && typeof meta[k] !== 'string') err(`meta.${k} は文字列にする`);
}
if (meta.source !== undefined && (!isObj(meta.source) || !isStr(meta.source.title) || !isStr(meta.source.url))) err('meta.source は { "title", "url" } にする');
if (meta.transitions !== undefined && !['flow', 'explicit'].includes(meta.transitions)) err(`meta.transitions は "flow" か "explicit" にする (${JSON.stringify(meta.transitions)})`);
const EXPLICIT = meta.transitions === 'explicit';

const kindIds = new Set(BUILTIN);
if (meta.kinds !== undefined) {
  if (!Array.isArray(meta.kinds)) err('meta.kinds は配列にする');
  else {
    const seen = new Set();
    meta.kinds.forEach((k, i) => {
      const at = `meta.kinds[${i}]`;
      if (!Array.isArray(k) || k.length !== 3) return err(`${at}: [ID, 表示名, 外観] にする`);
      const [id, label, look] = k;
      if (typeof id !== 'string' || !/^[a-z][a-z0-9_-]*$/.test(id)) err(`${at}: ID「${id}」は ^[a-z][a-z0-9_-]*$ にする`);
      if (id === 'state') err(`${at}: ID に state は使用できない`);
      if (seen.has(id)) err(`${at}: ID「${id}」が重複`);
      seen.add(id);
      if (!isStr(label)) err(`${at}: 表示名がない`);
      if (!BUILTIN.includes(look)) err(`${at}: 外観「${look}」は ${BUILTIN.join(' / ')} のいずれかにする`);
      kindIds.add(id);
    });
  }
}
if (meta.legend !== undefined) {
  if (!Array.isArray(meta.legend)) err('meta.legend は配列にする');
  else meta.legend.forEach((l, i) => {
    if (!Array.isArray(l) || !isStr(l[0]) || !isStr(l[1])) err(`meta.legend[${i}]: [種別, 表示名] にする`);
    else if (!kindIds.has(l[0])) err(`meta.legend[${i}]: 種別「${l[0]}」が未定義`);
  });
}
const variantIds = new Set();
if (meta.variants !== undefined) {
  if (!Array.isArray(meta.variants) || !meta.variants.length) err('meta.variants は空でない配列にする');
  else meta.variants.forEach((v, i) => {
    if (!isObj(v) || !isStr(v.id) || !isStr(v.label)) return err(`meta.variants[${i}]: { "id", "label" } にする`);
    if (variantIds.has(v.id)) err(`meta.variants[${i}]: id「${v.id}」が重複`);
    variantIds.add(v.id);
  });
}
const HAS_VAR = meta.variants !== undefined;
if (meta.levelLabels !== undefined) {
  if (!isObj(meta.levelLabels)) err('meta.levelLabels はオブジェクトにする');
  else for (const [k, v] of Object.entries(meta.levelLabels)) {
    if (!LEVELS.includes(k)) err(`meta.levelLabels: 「${k}」は ${LEVELS.join(' / ')} のいずれかにする`);
    if (!isStr(v)) err(`meta.levelLabels.${k} は文字列にする`);
  }
}
if (meta.link !== undefined) {
  if (!isObj(meta.link) || !isStr(meta.link.commit)) err('meta.link は { "commit", "pr" } にする (commit は必須)');
  else {
    if (!meta.link.commit.includes('{sha}')) err('meta.link.commit に {sha} がない');
    if (meta.link.pr !== undefined && (!isStr(meta.link.pr) || !meta.link.pr.includes('{pr}'))) err('meta.link.pr は {pr} を含む文字列にする');
  }
}
if (HAS_TL && !meta.repoUrl && !meta.link) err('timeline.json があるのに meta.repoUrl も meta.link もない');
if (hist !== undefined && !Array.isArray(meta.areas)) err('hist.json があるのに meta.areas (配列) がない');
if (meta.areas !== undefined && !Array.isArray(meta.areas)) err('meta.areas は配列にする');

/* ---------- timeline / hist ---------- */
const pos = new Map();
let items = 0;
if (HAS_TL) {
  if (hist === undefined) err('timeline.json があるのに hist.json がない');
  if (!Array.isArray(timeline) || !timeline.length) err('timeline.json が空');
  else timeline.forEach((e, i) => {
    const at = `timeline[${i}] ${e.sha}`;
    if (!/^[0-9a-f]{7,40}$/.test(e.sha || '')) err(`${at}: sha が不正`);
    if (pos.has(e.sha)) err(`${at}: sha が重複`);
    pos.set(e.sha, timeline.length - 1 - i);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(e.date || '')) err(`${at}: date は YYYY-MM-DD`);
    if (i && timeline[i - 1].date < e.date) err(`${at}: 新しい順になっていない`);
    if (!e.title) err(`${at}: title がない`);
    if (!Number.isFinite(e.add) || !Number.isFinite(e.del)) err(`${at}: add / del は数値`);
    for (const t of e.tags || []) if (!Array.isArray(t) || !t[0] || !t[1]) err(`${at}: tags は [種別, 名前, 削除?]`);
  });
} else if (hist !== undefined) err('hist.json は timeline.json と組で配置する');
// hist: [kind, area, title, was, now]
if (hist !== undefined) {
  if (!isObj(hist)) err('hist.json はオブジェクトにする');
  else for (const [sha, list] of Object.entries(hist)) {
    if (!pos.has(sha)) err(`hist ${sha}: timeline にない sha`);
    if (!Array.isArray(list) || !list.length) { err(`hist ${sha}: 変更が空`); continue; }
    list.forEach((it, j) => {
      const at = `hist ${sha}[${j}]`, [k, ar, t, was, now] = it;
      items++;
      if (typeof k !== 'string' || k.length !== 1 || !'acd'.includes(k)) err(`${at}: 種別は a / c / d`);
      if (!Number.isInteger(ar) || !meta.areas || !meta.areas[ar]) err(`${at}: area ${ar} が meta.areas にない`);
      if (!t) err(`${at}: 題がない`);
      if (typeof was !== 'string' || typeof now !== 'string') err(`${at}: was / now は文字列`);
      if (k === 'a' && !now) err(`${at}: 追加には now が必要`);
      if (k === 'd' && !was) err(`${at}: 削除には was が必要`);
      if (k === 'c' && (!was || !now)) notes.push(`${at}: 変更の was / now の片方が空`);
    });
  }
}
const H = hist && isObj(hist) ? hist : {};

/* ---------- sections / issues ---------- */
const secIds = new Map();
if (sections !== undefined) {
  if (!Array.isArray(sections)) err('sections.json は配列にする');
  else sections.forEach((s, i) => {
    const at = `sections[${i}]`;
    if (!isObj(s)) return err(`${at}: オブジェクトにする`);
    if (!isStr(s.id)) err(`${at}: id がない`);
    else if (secIds.has(s.id)) err(`${at}: id「${s.id}」が重複`);
    else secIds.set(s.id, s);
    if (!isStr(s.title)) err(`${at} ${s.id}: title がない`);
    if (typeof s.text !== 'string') err(`${at} ${s.id}: text は文字列にする`);
    for (const k of ['tab', 'url']) if (s[k] !== undefined && typeof s[k] !== 'string') err(`${at} ${s.id}: ${k} は文字列にする`);
    if (s.level !== undefined && !Number.isInteger(s.level)) err(`${at} ${s.id}: level は整数にする`);
    if (s.skip !== undefined && !isStr(s.skip)) err(`${at} ${s.id}: skip は空でない文字列にする`);
  });
}
const issueIds = new Map();
if (issues !== undefined) {
  if (!Array.isArray(issues)) err('issues.json は配列にする');
  else issues.forEach((s, i) => {
    const at = `issues[${i}]`;
    if (!isObj(s)) return err(`${at}: オブジェクトにする`);
    if (!isStr(s.id)) err(`${at}: id がない`);
    else if (issueIds.has(s.id)) err(`${at}: id「${s.id}」が重複`);
    else issueIds.set(s.id, s);
    if (!ISSUE_TYPES.includes(s.type)) err(`${at} ${s.id}: type「${s.type}」は ${ISSUE_TYPES.join(' / ')} のいずれかにする`);
    if (!isStr(s.title)) err(`${at} ${s.id}: title がない`);
    if (!isStr(s.body)) err(`${at} ${s.id}: body がない`);
    if (s.src !== undefined && typeof s.src !== 'string') err(`${at} ${s.id}: src は文字列にする`);
    for (const id of toks(s.src)) if (!secIds.has(id)) err(`${at} ${s.id}: src の節「${id}」が sections にない`);
  });
}

/* ---------- machine ---------- */
if (!isObj(machine)) { console.error('machine.json はオブジェクトにする'); process.exit(1); }
const names = new Set(), mapped = new Set(), mappedItems = new Set(), referenced = new Set();
const cnt = { rules: 0, errors: 0, cells: 0, cellTo: 0, cellNa: 0, und: 0, inferred: 0, unmapped: 0, branches: 0 };
const undList = [], noSrc = [];
for (const region of ['flow', 'any']) {
  if (!Array.isArray(machine[region])) continue;
  for (const st of machine[region]) if (isObj(st) && isStr(st.state)) names.add(st.state);
}

function checkH(r, at) {
  const ev = [];
  if (r.h !== undefined && typeof r.h !== 'string') return err(`${at}: h は文字列にする`), ev;
  const list = toks(r.h);
  if (list.length && !HAS_TL) { err(`${at}: timeline.json がないのに h (対応付け) がある`); return ev; }
  for (const tok of list) {
    const m = /^([0-9a-f]{7,40}):([acd])(\d+)$/.exec(tok);
    if (!m) { err(`${at}: 対応付け「${tok}」の形式が不正 (sha:種別+番号)`); continue; }
    const [, sha, k, idx] = m;
    if (!H[sha]) { err(`${at}: ${sha} は hist にない`); continue; }
    if (+idx >= H[sha].length) err(`${at}: ${tok} の番号が hist の件数 (${H[sha].length}) を超えている`);
    if (ev.some(x => x.sha === sha)) err(`${at}: ${sha} が重複`);
    ev.push({ sha, k, p: pos.get(sha) });
    mapped.add(sha); mappedItems.add(`${sha}:${idx}`);
  }
  const adds = ev.filter(x => x.k === 'a'), dels = ev.filter(x => x.k === 'd');
  if (adds.length > 1 || dels.length > 1) err(`${at}: 追加・削除は各1回まで`);
  if (ev.length && !adds.length) err(`${at}: 対応付けには追加 (a) が必要`);
  if (adds.length && ev.some(x => x.p < adds[0].p)) err(`${at}: 追加より前のコミットへの対応付けがある`);
  if (dels.length && ev.some(x => x.p > dels[0].p)) err(`${at}: 削除より後のコミットへの対応付けがある`);
  return ev;
}

function checkBranch(r, at, cell) {
  if (!isObj(r)) return err(`${at}: オブジェクトにする`);
  cnt.branches++;
  if (!cell && !isStr(r.g)) err(`${at}: g (条件) がない`);
  if (cell && r.g !== undefined) err(`${at}: 判定表の欄に g は使用できない`);
  const hasTo = r.to !== undefined;
  if (!cell && !hasTo) err(`${at}: to (遷移先) がない`);
  if (hasTo) {
    if (!Array.isArray(r.to) || !r.to.length) err(`${at}: to は空でない配列にする`);
    else r.to.forEach((t, i) => {
      if (!Array.isArray(t) || t.length < 2 || t.length > 3 || !isStr(t[1]) || (t[2] !== undefined && typeof t[2] !== 'string')) {
        return err(`${at}: 遷移先 ${JSON.stringify(t)} は [種別, 表示名] または [種別, 表示名, 補足] にする`);
      }
      if (t[0] === 'state') {
        if (!EXPLICIT) err(`${at}: transitions が "flow" なのに遷移先 ["state", "${t[1]}"] を使用している`);
        if (!names.has(t[1])) err(`${at}: 遷移先の状態「${t[1]}」が存在しない`);
        if (i !== r.to.length - 1) err(`${at}: 遷移先 ["state", "${t[1]}"] は配列の末尾に置く`);
      } else if (!kindIds.has(t[0])) err(`${at}: 遷移先の種別「${t[0]}」が未定義 (定義済み: ${[...kindIds, ...(EXPLICIT ? ['state'] : [])].join(' / ')})`);
    });
  }
  if (cell && r.na !== undefined) {
    if (!isStr(r.na)) err(`${at}: na は空でない文字列にする`);
    if (hasTo) err(`${at}: to と na の両方がある`);
  }
  const needFor = !cell || hasTo;
  if (r.for === undefined) {
    if (HAS_VAR && needFor) err(`${at}: meta.variants があるのに for がない`);
  } else if (!Array.isArray(r.for) || !r.for.length) err(`${at}: for は空でない配列にする`);
  else {
    if (new Set(r.for).size !== r.for.length) err(`${at}: for が重複`);
    for (const v of r.for) if (!variantIds.has(v)) err(`${at}: for の用途「${v}」が未定義${HAS_VAR ? '' : ' (meta.variants がない)'}`);
  }
  if (r.src !== undefined) {
    if (typeof r.src !== 'string') err(`${at}: src は文字列にする`);
    for (const id of toks(r.src)) {
      if (!secIds.has(id)) err(`${at}: src の節「${id}」が存在しない${sections === undefined ? ' (sections.json がない)' : ''}`);
      referenced.add(id);
    }
  }
  if (r.issue !== undefined) {
    if (typeof r.issue !== 'string') err(`${at}: issue は文字列にする`);
    for (const id of toks(r.issue)) if (!issueIds.has(id)) err(`${at}: issue の指摘「${id}」が存在しない${issues === undefined ? ' (issues.json がない)' : ''}`);
  }
  if (r.why !== undefined && !isStr(r.why) && !(Array.isArray(r.why) && r.why.length === 2 && isStr(r.why[0]) && isStr(r.why[1]))) {
    err(`${at}: why は文字列または [短い名前, 詳細] にする`);
  }
  if (r.level !== undefined && !LEVELS.includes(r.level)) err(`${at}: level「${r.level}」は ${LEVELS.join(' / ')} のいずれかにする`);
  if (r.std !== undefined && !(Array.isArray(r.std) && r.std.length >= 1 && r.std.length <= 2 && STD.includes(r.std[0]) && (r.std[1] === undefined || isStr(r.std[1])))) {
    err(`${at}: std は [種類, 説明] または [種類] にする (種類: ${STD.join(' / ')})`);
  }
  if (r.inferred !== undefined) {
    if (!isStr(r.inferred)) err(`${at}: inferred は空でない文字列にする`);
    else cnt.inferred++;
  }
  if (r.gap !== undefined && typeof r.gap !== 'boolean') err(`${at}: gap は true / false にする`);
  const ev = checkH(r, at);
  if ((!cell || hasTo) && !toks(r.src).length && !ev.some(x => x.k === 'd')) noSrc.push(at);
  return ev.length;
}

function checkTable(t, st) {
  const at = `「${st}」table`;
  if (!isObj(t)) return err(`${at}: オブジェクトにする`);
  const axis = (a, k) => {
    if (!isObj(a) || !isStr(a.label) || !Array.isArray(a.values) || !a.values.length || !a.values.every(isStr)) {
      err(`${at}.${k}: { "label", "values": [文字列, …] } にする`);
      return 0;
    }
    return a.values.length;
  };
  const R = axis(t.rows, 'rows'), Cn = axis(t.cols, 'cols');
  if (!Array.isArray(t.cells)) return err(`${at}.cells は配列にする`);
  const at2 = new Map();
  t.cells.forEach((c, i) => {
    const cat = `${at}.cells[${i}]`;
    cnt.cells++;
    if (!isObj(c)) return err(`${cat}: オブジェクトにする`);
    if (!Number.isInteger(c.r) || !Number.isInteger(c.c)) err(`${cat}: r / c は整数にする`);
    else if (R && Cn && (c.r < 0 || c.r >= R || c.c < 0 || c.c >= Cn)) err(`${cat}: (r ${c.r}, c ${c.c}) が判定表の範囲 (${R} 行 × ${Cn} 列) の外`);
    checkBranch(c, cat, true);
    if (c.to !== undefined) cnt.cellTo++; else if (c.na !== undefined) cnt.cellNa++;
    const key = `${c.r},${c.c}`;
    if (!at2.has(key)) at2.set(key, []);
    at2.get(key).push([c, cat]);
  });
  for (const list of at2.values()) {
    const tos = list.filter(([c]) => c.to !== undefined);
    for (let i = 0; i < tos.length; i++) for (let j = i + 1; j < tos.length; j++) {
      const a = tos[i][0].for, b = tos[j][0].for;
      const overlap = !Array.isArray(a) || !Array.isArray(b) || a.some(v => b.includes(v));
      if (overlap) err(`${tos[j][1]}: 同じ欄 (r ${tos[j][0].r}, c ${tos[j][0].c}) の ${tos[i][1]} と for が重なる`);
    }
  }
  for (let r = 0; r < R; r++) for (let c = 0; c < Cn; c++) {
    const list = (at2.get(`${r},${c}`) || []).map(([x]) => x);
    if (list.some(x => x.to !== undefined || x.na !== undefined)) continue;
    cnt.und++;
    const iss = [...new Set(list.flatMap(x => toks(x.issue)))];
    undList.push({ where: `「${st}」${t.rows.values[r]} × ${t.cols.values[c]}`, iss });
  }
}

let states = 0;
const seenNames = new Set();
for (const region of ['flow', 'any']) {
  if (!Array.isArray(machine[region])) { err(`machine.${region} は配列にする`); continue; }
  machine[region].forEach((st, si) => {
    if (!isObj(st)) return err(`machine.${region}[${si}]: オブジェクトにする`);
    states++;
    const name = st.state;
    if (!isStr(name)) err(`machine.${region}[${si}]: state の名前がない`);
    if (seenNames.has(name)) err(`state「${name}」が重複`);
    seenNames.add(name);
    if (st.code !== undefined && typeof st.code !== 'boolean') err(`state「${name}」: code は true / false にする`);
    for (const k of ['rules', 'errors']) if (st[k] !== undefined && !Array.isArray(st[k])) err(`state「${name}」: ${k} は配列にする`);
    const rules = Array.isArray(st.rules) ? st.rules : [], errs = Array.isArray(st.errors) ? st.errors : [];
    if (!rules.length && !errs.length && st.table === undefined) err(`state「${name}」: rules・errors・table が全て空`);
    rules.forEach((r, i) => { cnt.rules++; if (!checkBranch(r, `「${name}」rule[${i}]`, false)) cnt.unmapped++; });
    errs.forEach((r, i) => { cnt.errors++; checkBranch(r, `「${name}」error[${i}]`, false); });
    if (st.table !== undefined) checkTable(st.table, name);
  });
}
if (!Array.isArray(machine.flow) || !machine.flow.length) err('machine.flow が空');

/* ---------- 節の網羅 ---------- */
const cov = { target: 0, hit: 0, skip: 0, head: 0 }, missing = [];
for (const s of secIds.values()) {
  if (s.skip) { cov.skip++; continue; }
  if (typeof s.text !== 'string' || !s.text) { cov.head++; continue; }
  cov.target++;
  if (referenced.has(s.id)) cov.hit++; else missing.push(s);
}
for (const s of missing) err(`節「${s.id}」(${s.title}) がどの枝・エラー・判定表の欄の src からも参照されていない`);

/* ---------- 出力 ---------- */
const template = readFileSync(join(here, '..', 'assets', 'template.html'), 'utf8');
const LS = String.fromCharCode(0x2028), PS = String.fromCharCode(0x2029);
const data = { meta, machine, timeline: timeline || [], hist: hist || {}, sections: sections || [], issues: issues || [] };
const json = JSON.stringify(data).replace(/</g, '\\u003c').split(LS).join('\\u2028').split(PS).join('\\u2029');
if (!template.includes('/*DATA*/null') || !template.includes('__TITLE__')) err('template.html に埋め込み位置がない');
const html = template.replace('__TITLE__', () => String(meta.title || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')).replace('/*DATA*/null', () => json);
try { new Function(html.split('<script>')[1].split('</script>')[0]); }
catch (e) { err(`生成したスクリプトの構文エラー: ${e.message}`); }

if (HAS_TL && Array.isArray(timeline)) {
  const histShas = Object.keys(H);
  const noMap = histShas.filter(s => !mapped.has(s));
  console.log(`commits: ${timeline.length} (対象ファイルを変更: ${histShas.length}, 注目: ${timeline.filter(e => e.star).length})`);
  console.log(`changes: ${items} (枝に対応: ${mappedItems.size})`);
  console.log(`states: ${names.size}, rules: ${cnt.rules} (対応付けなし: ${cnt.unmapped})`);
  console.log(`枝に対応しないコミット: ${noMap.length ? noMap.join(' ') : 'なし'}`);
} else {
  console.log(`states: ${states}, rules: ${cnt.rules}`);
}
console.log(`errors: ${cnt.errors}, cells: ${cnt.cells} (記載 ${cnt.cellTo} / 該当なし ${cnt.cellNa} / 未規定 ${cnt.und})`);
console.log(`inferred: ${cnt.inferred}`);
for (const u of undList) {
  if (u.iss.length) console.log(`未規定: ${u.where} (issue: ${u.iss.join(' ')})`);
  else notes.push(`未規定 (issue なし): ${u.where}`);
}
if (sections !== undefined) {
  console.log(`sections: ${secIds.size} (網羅の対象 ${cov.target}: 参照あり ${cov.hit} / 参照なし ${missing.length}, 除外 ${cov.skip}, 見出しのみ ${cov.head})`);
  console.log(`src を持たない枝: ${noSrc.length} (削除済みを除く)`);
  const LIST = 5;
  if (noSrc.length) notes.push(`src を持たない枝 (削除済みを除く) ${noSrc.length} 件: ${noSrc.slice(0, LIST).join(', ')}${noSrc.length > LIST ? ` ほか ${noSrc.length - LIST} 件` : ''}`);
}
if (issues !== undefined) console.log(`issues: ${issueIds.size}`);
// 到達性: transitions が explicit の場合、用途ごとに flow の先頭から ["state", …] の遷移を追跡し、
// その用途の枝を持つ flow の状態へ到達できるかを出力する。版の履歴がある場合は、最新版で存在する枝（d を持たない枝）だけを対象にする。
if (EXPLICIT && Array.isArray(machine.flow) && machine.flow.length && Array.isArray(machine.any)) {
  const live = b => b && Array.isArray(b.to) && !/:d\d+/.test(b.h || '');
  const brs = s => [...(s.rules || []), ...(s.errors || []), ...((s.table && s.table.cells) || [])].filter(live);
  const groups = HAS_VAR && Array.isArray(meta.variants) ? meta.variants.map(v => ({ id: v.id, label: v.label })) : [{ id: null, label: '全体' }];
  for (const g of groups) {
    const inV = b => g.id === null || (Array.isArray(b.for) && b.for.includes(g.id));
    const edges = new Map([...machine.flow, ...machine.any].map(s => [s.state, brs(s).filter(inV).flatMap(b => b.to.filter(t => t[0] === 'state').map(t => t[1]))]));
    const start = machine.flow[0].state, seen = new Set([start]), queue = [start];
    while (queue.length) for (const n of edges.get(queue.shift()) || []) if (!seen.has(n)) { seen.add(n); queue.push(n); }
    const target = machine.flow.filter(s => brs(s).some(inV)).map(s => s.state);
    const miss = target.filter(n => !seen.has(n));
    console.log(`到達 (${g.label}): ${target.length - miss.length} / ${target.length}`);
    if (miss.length) notes.push(`到達できない状態 (${g.label}): ${miss.join(', ')}`);
  }
}
for (const n of notes) console.log(`note: ${n}`);
if (errors.length) {
  for (const e of errors) console.error(`error: ${e}`);
  console.error(`${errors.length} 件の問題があるため出力しない`);
  process.exit(1);
}
writeFileSync(resolve(outPath), html);
console.log(`ok: ${resolve(outPath)} (${Buffer.byteLength(html)} bytes)`);
