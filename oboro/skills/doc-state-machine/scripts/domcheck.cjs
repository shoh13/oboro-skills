// 生成した HTML を jsdom で読み込み、スクリプトの例外と DOM の生成結果を出力する。
// 使い方: NODE_PATH=<jsdom を含む node_modules> node domcheck.cjs <file.html> [追加で評価する JS 式]
// jsdom はレイアウトを計算しないため、寸法は 0 になる。件数・クラス・例外の確認に限定して使用する。
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');

const [file, expr] = process.argv.slice(2);
const html = fs.readFileSync(file, 'utf8');
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push(String(e && (e.stack || e.message) || e)));
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));

const ctx2d = new Proxy({}, { get: (t, k) => (k in t ? t[k] : () => {}), set: (t, k, v) => { t[k] = v; return true; } });
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'file://' + file,
  virtualConsole: vc,
  beforeParse(w) {
    w.HTMLCanvasElement.prototype.getContext = () => ctx2d;
    w.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    w.Element.prototype.scrollIntoView = function () {};
    w.Element.prototype.setPointerCapture = function () {};
  },
});
const w = dom.window;
w.addEventListener('error', e => errors.push('window.error: ' + (e.error && e.error.stack || e.message)));

setTimeout(() => {
  const d = w.document, q = s => d.querySelectorAll(s).length;
  const out = {
    errors,
    clusters: q('.cluster'),
    clustersVisible: q('.cluster:not(.off)'),
    states: q('.state'),
    rules: q('.rule'),
    rulesVisible: q('.rule:not(.off)'),
    rulesShown: q('.rule:not(.off):not(.vx)'),
    wires: q('#wires .wire'),
  };
  if (expr) { try { out.expr = w.eval(expr); } catch (e) { out.exprError = String(e.stack || e); } }
  console.log(JSON.stringify(out, null, 2));
  w.close();
  process.exit(errors.length ? 1 : 0);
}, 1500);
