// 立ち絵の見た目を決める純粋な関数（DOM に触れない）。player.js が使い、テストはブラウザで直接呼ぶ。
window.KataribeCast = (() => {
  const DEFAULT_FACE = "normal";

  // 行 index の時点の、話者ごとの表情。話している人はその行の表情（省略なら既定）、
  // 話していない人は最後に話した行の表情（まだ話していなければ既定）。
  function facesAt(lines, index, speakers) {
    const faces = Object.fromEntries(speakers.map((speaker) => [speaker, DEFAULT_FACE]));
    for (let i = 0; i <= index && i < lines.length; i++) {
      faces[lines[i].speaker] = lines[i].expression ?? DEFAULT_FACE;
    }
    return faces;
  }

  // 表示するレイヤーのパス。体・表情・口の段階のレイヤーを、重ねる順（entry.layers のキーの順）に並べる。
  // まばたき中は、表情の目のレイヤー（閉じ目と同じグループのもの）を閉じ目に替える。閉じ目のない表情は替えない。
  function activeLayers(entry, face, mouthLevel, blinking = false) {
    const resolved = entry.faces[face];
    let faceLayers = resolved.layers;
    if (blinking && resolved.blink) {
      const group = resolved.blink.slice(0, resolved.blink.lastIndexOf("/") + 1);
      faceLayers = [...faceLayers.filter((path) => !path.startsWith(group)), resolved.blink];
    }
    const active = new Set([...entry.base, ...faceLayers, resolved.mouth[mouthLevel]]);
    return Object.keys(entry.layers).filter((path) => active.has(path));
  }

  // まばたき。4秒ごとの区間に1回、0.12秒だけ目を閉じる。閉じる時刻は話者ごとの種（seed）と時刻だけで決まる。
  const BLINK_CELL = 4, BLINK_CLOSED = 0.12;
  function hash01(seed, k) {
    let h = Math.imul(seed ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(k + 0x632be5ab, 0xc2b2ae35);
    h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d);
    h = Math.imul(h ^ (h >>> 12), 0x297a2d39);
    return ((h ^ (h >>> 15)) >>> 0) / 4294967296;
  }
  function seedOf(name) {
    let h = 0x811c9dc5;
    for (const ch of name) h = Math.imul(h ^ ch.codePointAt(0), 0x01000193);
    return h >>> 0;
  }
  function blinkClosed(t, seed) {
    const x = t + hash01(seed, -1) * BLINK_CELL; // 話者ごとに区間の位置をずらす
    const k = Math.floor(x / BLINK_CELL);
    const at = k * BLINK_CELL + hash01(seed, k) * (BLINK_CELL - BLINK_CLOSED);
    return x >= at && x < at + BLINK_CLOSED;
  }

  // 時刻 t の口の段階（0 閉じ、1 半開き、2 開き）。行の mouth は 1/30 秒ごとの段階の文字列。
  const MOUTH_FPS = 30;
  function mouthLevel(line, t) {
    if (!line.mouth || t < line.start || t >= line.end) return 0;
    const level = Number(line.mouth[Math.floor((t - line.start) * MOUTH_FPS)]);
    return level === 1 || level === 2 ? level : 0;
  }

  // 立ち絵が画面の外側を向いているなら、左右を反転して中央を向かせる。
  function mirrored(side, facing) {
    return side === facing;
  }

  return { DEFAULT_FACE, facesAt, activeLayers, mouthLevel, blinkClosed, seedOf, mirrored };
})();
