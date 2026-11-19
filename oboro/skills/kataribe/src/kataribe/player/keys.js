// player.js の操作とキー一覧は、どちらもこの表から作る（一覧と実際の動作が食い違わないため）。DOM に触れない。
window.KataribeKeys = (() => {
  const DIGITS = [..."0123456789"];

  // keys は KeyboardEvent.key の値で、英字は小文字で書く（decide が小文字にして引く）
  const BINDINGS = [
    { keys: [" ", "k"], action: "play", label: "再生・一時停止" },
    { keys: ["j"], action: "back", label: "5秒戻る", repeat: true },
    { keys: ["l"], action: "forward", label: "5秒進む", repeat: true },
    { keys: ["ArrowLeft"], action: "prev-line", label: "前の行", repeat: true },
    { keys: ["ArrowRight"], action: "next-line", label: "次の行", repeat: true },
    { keys: ["ArrowUp"], action: "prev-chapter", label: "前の章", repeat: true },
    { keys: ["ArrowDown"], action: "next-chapter", label: "次の章", repeat: true },
    { keys: ["Home"], action: "first", label: "先頭" },
    { keys: ["End"], action: "last", label: "最後の行" },
    { keys: DIGITS, names: ["0–9"], action: "percent", label: "0〜90%の位置" },
    { keys: ["["], action: "slower", label: "再生速度を下げる", repeat: true },
    { keys: ["]"], action: "faster", label: "再生速度を上げる", repeat: true },
    { keys: ["c"], action: "captions", label: "字幕の表示切替" },
    { keys: ["t"], action: "transcript", label: "文字起こしの開閉" },
    { keys: ["?"], action: "keys", label: "キー一覧" },
  ];

  const BY_KEY = new Map(BINDINGS.flatMap((binding) => binding.keys.map((key) => [key, binding])));
  const TEXT_ENTRY = ["INPUT", "TEXTAREA", "SELECT"];
  const ACTIVATES_ON_SPACE = ["BUTTON", "A", "SUMMARY"];
  const SEEK_BAR = "kataribe-seek-bar";
  const SEEK_BAR_ACTIONS = ["prev-line", "next-line"];
  const DISPLAY = { " ": "Space", ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓" };
  const CHAPTER_RESTART = 2;

  const normalize = (key) => (key.length === 1 ? key.toLowerCase() : key);

  // Esc は表に入れない（開いた dialog は Esc で自分で閉じる。閉じているときの Esc は奪わない）
  function decide(event, listOpen = false) {
    // 自動入力は key のない keydown を出す
    if (typeof event.key !== "string" || event.ctrlKey || event.metaKey || event.altKey) return null;
    const key = normalize(event.key);
    const binding = BY_KEY.get(key);
    if (!binding || (event.shiftKey && key !== "?")) return null;
    if (listOpen) return binding.action === "keys" ? binding : null;
    const target = event.target ?? {};
    // 再生位置のバーは、バー自身の刻みが細かすぎるので、← → だけは行の移動にする
    if (target.id === SEEK_BAR) return SEEK_BAR_ACTIONS.includes(binding.action) ? binding : null;
    if (target.isContentEditable || TEXT_ENTRY.includes(target.tagName)) return null;
    if (key === " " && ACTIVATES_ON_SPACE.includes(target.tagName)) return null;
    return binding;
  }

  function keyNames(binding) {
    return binding.names ?? binding.keys.map((key) => DISPLAY[key] ?? (key.length === 1 ? key.toUpperCase() : key));
  }

  function ariaShortcuts(actions) {
    return BINDINGS.filter((binding) => actions.includes(binding.action))
      .flatMap((binding) => binding.keys)
      .map((key) => (key === " " ? "Space" : key.length === 1 ? key.toUpperCase() : key))
      .join(" ");
  }

  // offset 1 で null は、最後の章（動かない）
  function chapterStart(chapters, index, now, offset) {
    if (offset > 0) return index + 1 < chapters.length ? chapters[index + 1].start : null;
    const target = now - chapters[index].start > CHAPTER_RESTART ? index : Math.max(index - 1, 0);
    return chapters[target].start;
  }

  return { BINDINGS, decide, keyNames, ariaShortcuts, chapterStart };
})();
