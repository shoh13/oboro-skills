// スライドのプレーヤー。台本の行（steps）を1つずつ進め、地の文は本文の段に、コメントは話者の吹き出しに出す。
// 見た目は、今の行（index）だけで決まる（まばたきだけは実時間で動く）。
(() => {
  const data = JSON.parse(document.getElementById("kataribe-data").textContent);
  const cast = JSON.parse(document.getElementById("kataribe-cast").textContent);
  const steps = data.steps;
  const stage = document.getElementById("kataribe-stage");
  const chapterEl = document.getElementById("kataribe-chapter");
  const headingEl = document.getElementById("kataribe-heading");
  const visualEl = document.getElementById("kataribe-visual");
  const narrationEl = document.getElementById("kataribe-narration");
  const bubblesEl = document.getElementById("kataribe-bubbles");
  const progressEl = document.querySelector("#kataribe-progress span");
  const counterEl = document.getElementById("kataribe-counter");
  const jumpEl = document.getElementById("kataribe-jump");
  const prevButton = document.getElementById("kataribe-prev");
  const nextButton = document.getElementById("kataribe-next");
  stage.tabIndex = 0;
  stage.dataset.cast = String(cast.length);

  // スライドごとの行。lineIndex は、スライドの中の0始まりの番号（scenes.html の data-at などが指す番号）。
  const slideById = Object.fromEntries(data.slides.map((slide, number) => [slide.id, { ...slide, number, steps: [] }]));
  const lineIndex = [];
  steps.forEach((step, index) => {
    const slide = slideById[step.slide];
    lineIndex.push(slide.steps.length);
    slide.steps.push(index);
  });
  for (const slide of data.slides) {
    const option = document.createElement("option");
    option.value = slide.id;
    option.textContent = `${slideById[slide.id].number + 1}. ${slide.title ?? slide.chapter}`;
    jumpEl.appendChild(option);
  }

  // 地の文の段落
  const paragraphs = [];
  steps.forEach((step, index) => {
    if (step.speaker != null) return;
    const p = document.createElement("p");
    p.textContent = step.text;
    p.dataset.step = step.id;
    narrationEl.appendChild(p);
    paragraphs.push({ p, index, slide: step.slide });
  });

  // scenes.html の section（任意）。行単位の出現・消去・強調は、動画と同じ規則。
  const sections = Object.fromEntries(Array.from(visualEl.querySelectorAll(":scope > section[data-scene]")).map((s) => [s.dataset.scene, s]));
  const timed = [];
  const focusGroups = new Map();
  for (const [scene, section] of Object.entries(sections)) {
    for (const el of section.querySelectorAll("[data-at],[data-out]")) {
      timed.push({
        el,
        scene,
        at: el.hasAttribute("data-at") ? Number(el.dataset.at) : 0,
        out: el.hasAttribute("data-out") ? Number(el.dataset.out) : Infinity,
      });
    }
    for (const el of section.querySelectorAll("[data-focus]")) {
      if (!el.parentElement) continue;
      const members = focusGroups.get(el.parentElement) ?? [];
      members.push({ el, scene, lines: new Set(el.dataset.focus.split(",").map((n) => Number(n.trim()))) });
      focusGroups.set(el.parentElement, members);
    }
  }

  // 立ち絵と吹き出し
  const speakers = cast.map((entry) => entry.speaker);
  const figures = KataribeFigures.create(document.getElementById("kataribe-characters"), cast);
  const bubbles = {};
  for (const entry of cast) {
    const bubble = document.createElement("div");
    bubble.className = "kataribe-bubble";
    bubble.dataset.speaker = entry.speaker;
    bubble.dataset.side = entry.side;
    bubble.dataset.state = "hidden";
    bubble.style.setProperty("--c", entry.color);
    const name = document.createElement("b");
    name.textContent = entry.speaker;
    const text = document.createElement("span");
    bubble.append(name, text);
    bubblesEl.appendChild(bubble);
    bubbles[entry.speaker] = { bubble, text };
  }
  let figuresReady = false;
  let index = 0;

  function drawFigures() {
    const faces = KataribeCast.facesAt(steps, index, speakers);
    const now = performance.now() / 1000;
    for (const c of figures.characters) {
      const face = faces[c.entry.speaker];
      const blinking = Boolean(c.entry.faces[face].blink) && KataribeCast.blinkClosed(now, c.seed);
      const active = KataribeCast.activeLayers(c.entry, face, 0, blinking);
      c.canvas.dataset.face = face;
      c.canvas.dataset.blink = blinking ? "1" : "0";
      if (figuresReady) figures.draw(c, active);
    }
  }

  function render(moved) {
    const step = steps[index];
    const slide = slideById[step.slide];
    const at = lineIndex[index];
    stage.dataset.step = step.id;
    stage.dataset.slide = slide.id;
    chapterEl.textContent = slide.title != null ? slide.chapter : "";
    headingEl.textContent = slide.title ?? slide.chapter;

    // 画面（scenes.html）
    for (const [scene, section] of Object.entries(sections)) {
      section.classList.toggle("kataribe-active", scene === slide.id);
      if (scene === slide.id) section.style.setProperty("--p", String(slide.steps.length > 1 ? at / (slide.steps.length - 1) : 1));
    }
    visualEl.hidden = !sections[slide.id];
    for (const item of timed) {
      if (item.scene !== slide.id) continue;
      if (at >= item.at && at < item.out) item.el.removeAttribute("data-kataribe-state");
      else item.el.setAttribute("data-kataribe-state", "hidden");
    }
    for (const members of focusGroups.values()) {
      if (members[0].scene !== slide.id) continue;
      const anyFocused = members.some((member) => member.lines.has(at));
      for (const member of members) {
        if (!anyFocused) member.el.removeAttribute("data-kataribe-focus-state");
        else member.el.setAttribute("data-kataribe-focus-state", member.lines.has(at) ? "active" : "dim");
      }
    }

    // 地の文。今の行までの最後の地の文が current、それより前が past、後は場所だけ取って隠す（行が進んでも段落が動かない）。
    let latest = -1;
    for (const item of paragraphs) if (item.slide === slide.id && item.index <= index) latest = item.index;
    let current = null;
    for (const item of paragraphs) {
      item.p.hidden = item.slide !== slide.id;
      item.p.dataset.state = item.index > index ? "future" : item.index === latest ? "current" : "past";
      if (item.index === latest) current = item.p;
    }
    if (current && moved) {
      const top = current.offsetTop - narrationEl.offsetTop;
      if (top + current.offsetHeight > narrationEl.scrollTop + narrationEl.clientHeight || top < narrationEl.scrollTop) {
        narrationEl.scrollTop = Math.max(top + current.offsetHeight - narrationEl.clientHeight, 0);
      }
    }

    // 吹き出し。直前の地の文（なければスライドの先頭）から今の行までの、話者ごとの最後のコメント。
    const blockStart = latest >= 0 ? latest : slide.steps[0];
    for (const speaker of speakers) {
      let said = -1;
      for (let i = blockStart; i <= index; i++) if (steps[i].speaker === speaker) said = i;
      const { bubble, text } = bubbles[speaker];
      if (said < 0) bubble.dataset.state = "hidden";
      else {
        text.textContent = steps[said].text;
        bubble.dataset.state = said === index ? "current" : "past";
      }
    }

    // 話し始めた人を、少し跳ねさせる
    for (const c of figures.characters) {
      const speaking = step.speaker === c.entry.speaker;
      if (moved || !speaking) c.canvas.removeAttribute("data-speaking");
      if (moved && speaking) {
        void c.canvas.offsetWidth; // アニメーションを最初からやり直す
        c.canvas.dataset.speaking = "1";
      }
    }
    drawFigures();

    progressEl.style.width = `${((index + 1) / steps.length) * 100}%`;
    counterEl.textContent = `${slide.number + 1} / ${data.slides.length}`;
    jumpEl.value = slide.id;
    prevButton.disabled = index === 0;
    nextButton.disabled = index === steps.length - 1;
    if (location.hash.slice(1) !== step.id) history.replaceState(null, "", `#${encodeURIComponent(step.id)}`);
  }

  function go(target) {
    const next = Math.min(Math.max(target, 0), steps.length - 1);
    if (next === index) return;
    index = next;
    render(true);
  }

  function goSlide(offset) {
    const slide = slideById[steps[index].slide];
    if (offset < 0 && index !== slide.steps[0]) return go(slide.steps[0]);
    const target = data.slides[slide.number + offset];
    if (target) go(slideById[target.id].steps[0]);
  }

  stage.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("a, button, input, select, textarea")) return;
    go(index + 1);
  });
  prevButton.addEventListener("click", () => go(index - 1));
  nextButton.addEventListener("click", () => go(index + 1));
  jumpEl.addEventListener("change", () => go(slideById[jumpEl.value].steps[0]));
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    if (target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
    if (target instanceof HTMLElement && target.tagName === "BUTTON" && (event.key === " " || event.key === "Enter")) return;
    const actions = {
      ArrowRight: () => go(index + 1),
      ArrowDown: () => go(index + 1),
      " ": () => go(event.shiftKey ? index - 1 : index + 1),
      ArrowLeft: () => go(index - 1),
      ArrowUp: () => go(index - 1),
      PageDown: () => goSlide(1),
      PageUp: () => goSlide(-1),
      Home: () => go(0),
      End: () => go(steps.length - 1),
    };
    const action = actions[event.key];
    if (!action || (event.shiftKey && event.key !== " ")) return;
    event.preventDefault();
    action();
  });

  function fromHash() {
    const id = decodeURIComponent(location.hash.slice(1));
    const found = steps.findIndex((step) => step.id === id);
    return found >= 0 ? found : null;
  }
  window.addEventListener("hashchange", () => {
    const found = fromHash();
    if (found !== null) go(found);
  });
  index = fromHash() ?? 0;
  render(false);

  function blinkLoop() {
    drawFigures();
    requestAnimationFrame(blinkLoop);
  }
  figures.ready.then(() => {
    figuresReady = true;
    figures.layout();
    drawFigures();
    document.documentElement.dataset.kataribeCast = "ready";
    requestAnimationFrame(blinkLoop);
  });
  window.addEventListener("resize", () => {
    if (!figuresReady) return;
    figures.layout();
    drawFigures();
  });
})();
