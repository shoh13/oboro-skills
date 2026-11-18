#!/usr/bin/env node
// Markdown の原文から sections.json の下書きを作成する。
// 使い方: node extract-md.mjs <file.md> [--url <原文の URL>] [--tab <分類名>] [--items] [--arrows]
//   --url    節の url を「<URL>#<見出しのアンカー>」で作成する（GitHub の blob の URL など）。
//   --items  太字の見出し語で始まる行を、直前の見出しの下位の節として分割する。
//            「- **名前.** 本文」（箇条書き）と「**名前.** 本文」（段落）が対象で、太字の直後が空白・行末・句読点の場合だけ分割する。
//            「- **範囲**が適切であること」のように太字が文の途中に続く行は分割しない。
//   --arrows 「- 条件 → 動作」の箇条書きを、矢印より前を題とする下位の節として分割する。
//            矢印が「条件 → 動作」を表す文書だけに使用する（パスの対応や変換を矢印で表す文書には使用しない）。
//   --ids    「- R5-1: 本文」「- AC3: 本文」のように、ID で始まる箇条書きを、ID を題とする下位の節として分割する。
//            ID は英大文字で始まり数字を含む語（R1、R5-1、AC17、REQ-001 など）で、直後に「:」または「：」が続くものに限る。
// 節の id は見出しの経路のスラッグ（例: playbooks/investigation）。同じ経路が重複する場合は -2, -3 を付ける。
// 項目のスラッグは題の先頭の8語まで。日本語などを含み語の区切りがない題は、先頭の24文字までとする。
// 原文の位置ではなく見出しの文字列から作成するため、節の挿入・並べ替えの後に再抽出しても既存の src が同じ節を指す。
// frontmatter とコードブロック内の行は見出しとして扱わない。
import { readFileSync } from 'node:fs';

const USAGE = 'usage: node extract-md.mjs <file.md> [--url <URL>] [--tab <name>] [--items] [--arrows] [--ids]';
const args = process.argv.slice(2), pos = [], o = {};
for (let k = 0; k < args.length; k++) {
  const a = args[k];
  if (a === '--url' || a === '--tab') {
    if (k + 1 >= args.length) { console.error(`${a} に値がない\n${USAGE}`); process.exit(2); }
    o[a.slice(2)] = args[++k];
  } else if (a === '--items' || a === '--arrows' || a === '--ids') o[a.slice(2)] = true;
  else if (a.startsWith('--')) { console.error(`未定義のオプション: ${a}\n${USAGE}`); process.exit(2); }
  else pos.push(a);
}
if (pos.length !== 1) { console.error(USAGE); process.exit(2); }
const [file] = pos;
const { url, tab, items, arrows, ids } = o;

// id 用のスラッグ。既存の src を保つため、規則を変更しない。
const slug = (s, words = Infinity) => {
  const base = s.toLowerCase().replace(/[`*_~]/g, '').replace(/[^\p{L}\p{N}\s-]/gu, '').trim().split(/\s+/).slice(0, words).join('-') || 'section';
  return /[^\x00-\x7F]/.test(base) && words !== Infinity ? [...base].slice(0, 24).join('') : base;
};
// url 用のアンカー。GitHub の見出しのアンカーと同じく、英数字・空白・ハイフン・下線だけを残す。
const anchor = s => s.toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, '').trim().replace(/\s/g, '-');
const itemOf = l => {
  if (items) {
    const m = /^[-*]\s+\*\*(.+?)\*\*(?=\s|$|[.:。：、,])\s*(.*)$/.exec(l) || /^\*\*(.+?)\*\*(?=\s|$|[.:。：、,])\s*(.*)$/.exec(l);
    if (m) return { title: m[1].replace(/[.:。：]\s*$/, ''), body: m[2].replace(/^[.:。：、,]\s*/, '') };
  }
  if (arrows) {
    const m = /^[-*]\s+(.+?)\s+→\s+(.*)$/.exec(l);
    if (m) return { title: m[1], body: '→ ' + m[2] };
  }
  if (ids) {
    const m = /^[-*]\s+([A-Z][A-Za-z]*-?\d[\w.-]*)\s*[:：]\s*(.*)$/.exec(l);
    if (m) return { title: m[1], body: m[2] };
  }
  return null;
};
const lines = readFileSync(file, 'utf8').replace(/\r\n/g, '\n').split('\n');
let i = 0;
if (lines[0] === '---') { const end = lines.indexOf('---', 1); if (end > 0) i = end + 1; }

const used = new Map(), anchors = new Map();
// GitHub は同じ見出しの2件目以降のアンカーに -1, -2 を付ける。
const anchorUniq = a => { const n = anchors.get(a) || 0; anchors.set(a, n + 1); return n === 0 ? a : `${a}-${n}`; };
// 同じ経路の2件目以降に -2, -3 を付ける。下位の節は、番号を付けた後の経路を引き継ぐ。
const uniq = id => { const n = (used.get(id) || 0) + 1; used.set(id, n); return n === 1 ? id : `${id}-${n}`; };
const top = { level: 0, title: '（冒頭）', id: 'top', anchor: '', lines: [] };
const secs = [top];
const stack = [];
const pathOf = seg => [...stack.map(s => s.seg), seg].join('/');
let fence = null;
// 項目の後に続く字下げのない行は、項目ではなく親の見出しの本文に戻す。
const sink = l => {
  const cur = secs[secs.length - 1];
  if (!cur.item || !l.trim() || /^\s+/.test(l)) return cur;
  const parent = stack.length ? stack[stack.length - 1].sec : top;
  const cont = { cont: parent, lines: [] };
  secs.push(cont);
  return cont;
};
for (; i < lines.length; i++) {
  const l = lines[i];
  if (fence) { secs[secs.length - 1].lines.push(l); if (new RegExp('^\\s*' + fence).test(l)) fence = null; continue; }
  const f = /^\s*(```|~~~)/.exec(l);
  if (f) { fence = f[1]; sink(l).lines.push(l); continue; }
  const h = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(l);
  const it = h ? null : itemOf(l);
  if (h) {
    const level = h[1].length, title = h[2];
    while (stack.length && stack[stack.length - 1].level >= level) stack.pop();
    const id = uniq(pathOf(slug(title)));
    const sec = { level, title, id, anchor: anchorUniq(anchor(title)), lines: [] };
    stack.push({ level, seg: id.split('/').pop(), sec });
    secs.push(sec);
  } else if (it) {
    const level = (stack.length ? stack[stack.length - 1].level : 0) + 1;
    secs.push({ level, title: it.title, id: uniq(pathOf(slug(it.title, 8))), anchor: '', lines: [it.body], item: true });
  } else sink(l).lines.push(l);
}
// 親へ戻した本文は、親の本文と改行1つで連結する（既存の sections.json の本文と一致させる）。
const parts = new Map();
for (const s of secs) {
  const t = s.lines.join('\n').trim();
  const key = s.cont || s;
  if (!parts.has(key)) parts.set(key, []);
  if (t || !s.cont) parts.get(key).push(t);
}
const out = secs.filter(s => !s.cont).map(s => ({ s, text: parts.get(s).filter(Boolean).join('\n') }))
  .filter(({ s, text }) => s.level > 0 || text)
  .map(({ s, text }) => ({
    id: s.id, ...(tab ? { tab } : {}), level: s.level, title: s.title,
    ...(url ? { url: url + (s.anchor ? '#' + s.anchor : '') } : {}),
    text,
  }));
console.log(JSON.stringify(out, null, 1));
