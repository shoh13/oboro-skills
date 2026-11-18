(() => {
  const timeline = JSON.parse(document.getElementById("kataribe-timeline").textContent);
  const audio = document.getElementById("kataribe-audio");
  const chapterEl = document.getElementById("kataribe-chapter");
  const captionEl = document.getElementById("kataribe-caption");
  const playButton = document.getElementById("kataribe-play");
  const playLabel = playButton.querySelector(".kataribe-label");
  const captionsButton = document.getElementById("kataribe-captions-toggle");
  const scenes = Array.from(document.querySelectorAll("#kataribe-stage section[data-scene]"));
  const chapterTitles = Object.fromEntries(timeline.chapters.map((c) => [c.id, c.title]));
  const chapterBar = document.getElementById("kataribe-chapter-bar");
  const transcript = document.getElementById("kataribe-transcript");
  const transcriptButton = document.getElementById("kataribe-transcript-toggle");
  const seekBar = document.getElementById("kataribe-seek-bar");
  const seekCurrent = document.getElementById("kataribe-seek-current");
  const seekDuration = document.getElementById("kataribe-seek-duration");
  let captionsOn = true;

  const sceneSpans = Object.fromEntries(timeline.scenes.map((scene) => [scene.id, scene]));
  const clamp01 = (value) => Math.min(Math.max(value, 0), 1);
  const sceneLineIndex = {};
  const sceneLineCounts = {};
  for (const line of timeline.lines) {
    sceneLineIndex[line.id] = sceneLineCounts[line.scene] ?? 0;
    sceneLineCounts[line.scene] = (sceneLineCounts[line.scene] ?? 0) + 1;
  }

  const timedElements = [];
  for (const section of scenes) {
    for (const el of section.querySelectorAll("[data-at],[data-out]")) {
      if (!(el instanceof HTMLElement)) continue;
      timedElements.push({
        el,
        scene: section.dataset.scene,
        at: el.hasAttribute("data-at") ? Number(el.dataset.at) : 0,
        out: el.hasAttribute("data-out") ? Number(el.dataset.out) : Infinity,
      });
    }
  }

  const focusGroups = new Map();
  for (const section of scenes) {
    for (const el of section.querySelectorAll("[data-focus]")) {
      if (!(el instanceof HTMLElement) || !el.parentElement) continue;
      const members = focusGroups.get(el.parentElement) ?? [];
      members.push({
        el,
        scene: section.dataset.scene,
        lines: new Set((el.dataset.focus ?? "").split(",").map((part) => Number(part.trim()))),
      });
      focusGroups.set(el.parentElement, members);
    }
  }

  for (const line of timeline.lines) {
    const item = document.createElement("button");
    item.type = "button";
    item.dataset.lineId = line.id;
    item.textContent = line.text;
    item.addEventListener("click", () => {
      audio.currentTime = line.start;
    });
    transcript.appendChild(item);
  }

  for (const chapter of timeline.chapters) {
    const item = document.createElement("button");
    item.type = "button";
    item.dataset.chapterId = chapter.id;
    item.textContent = chapter.title;
    item.style.flexGrow = String(Math.max(chapter.end - chapter.start, 0.001));
    item.addEventListener("click", () => {
      audio.currentTime = chapter.start;
    });
    chapterBar.appendChild(item);
  }

  // 立ち絵（figures.js）。
  const cast = JSON.parse(document.getElementById("kataribe-cast").textContent);
  const speakers = cast.map((entry) => entry.speaker);
  const figures = KataribeFigures.create(document.getElementById("kataribe-characters"), cast);
  const characters = figures.characters;
  let charactersReady = false;

  function renderCharacters(index, now) {
    const faces = KataribeCast.facesAt(timeline.lines, index, speakers);
    const line = timeline.lines[index];
    for (const c of characters) {
      // 話している人だけ、時刻に応じた口にする。話していない人は閉じる。
      const mouth = c.entry.speaker === line.speaker ? KataribeCast.mouthLevel(line, now) : 0;
      const face = faces[c.entry.speaker];
      const blinking = Boolean(c.entry.faces[face].blink) && KataribeCast.blinkClosed(now, c.seed);
      const active = KataribeCast.activeLayers(c.entry, face, mouth, blinking);
      c.canvas.dataset.face = face;
      c.canvas.dataset.mouth = String(mouth);
      c.canvas.dataset.blink = blinking ? "1" : "0";
      c.canvas.dataset.layers = JSON.stringify(active);
      if (charactersReady) figures.draw(c, active);
    }
  }

  const BOUNDARY_TOLERANCE = 0.005;

  function lineIndexAt(seconds) {
    let found = 0;
    for (let i = 0; i < timeline.lines.length; i++) {
      if (timeline.lines[i].start <= seconds + BOUNDARY_TOLERANCE) found = i;
      else break;
    }
    return found;
  }

  function moveToLine(offset) {
    const index = lineIndexAt(audio.currentTime);
    if (offset > 0 && index === timeline.lines.length - 1) return;
    const target = Math.max(index + offset, 0);
    audio.currentTime = timeline.lines[target].start;
  }

  function formatTime(seconds) {
    const whole = Math.floor(Math.max(seconds, 0));
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  }

  function renderSeekBar() {
    const total = Number.isFinite(audio.duration) ? audio.duration : timeline.lines[timeline.lines.length - 1].end;
    seekBar.max = String(total);
    seekBar.value = String(audio.currentTime);
    seekCurrent.textContent = formatTime(audio.currentTime);
    seekDuration.textContent = formatTime(total);
    seekBar.setAttribute("aria-valuetext", `${seekCurrent.textContent} / ${seekDuration.textContent}`);
  }

  function render() {
    renderSeekBar();
    const lineIndex = lineIndexAt(audio.currentTime);
    const line = timeline.lines[lineIndex];
    renderCharacters(lineIndex, audio.currentTime);
    for (const section of scenes) {
      section.classList.toggle("kataribe-active", section.dataset.scene === line.scene);
    }
    const sceneIndex = sceneLineIndex[line.id];
    for (const item of timedElements) {
      if (item.scene !== line.scene) continue;
      if (sceneIndex >= item.at && sceneIndex < item.out) item.el.removeAttribute("data-kataribe-state");
      else item.el.setAttribute("data-kataribe-state", "hidden");
    }
    for (const members of focusGroups.values()) {
      if (members[0].scene !== line.scene) continue;
      const anyFocused = members.some((member) => member.lines.has(sceneIndex));
      for (const member of members) {
        if (!anyFocused) member.el.removeAttribute("data-kataribe-focus-state");
        else member.el.setAttribute("data-kataribe-focus-state", member.lines.has(sceneIndex) ? "active" : "dim");
      }
    }
    const now = audio.currentTime;
    for (const section of scenes) {
      const span = sceneSpans[section.dataset.scene];
      if (!span) continue;
      const sceneLength = span.end - span.start;
      const lineLength = line.end - line.start;
      const sceneProgress = sceneLength > 0 ? clamp01((now - span.start) / sceneLength) : 0;
      let lineProgress;
      if (section.dataset.scene === line.scene) lineProgress = lineLength > 0 ? clamp01((now - line.start) / lineLength) : 0;
      else lineProgress = now < span.start ? 0 : 1;
      section.style.setProperty("--p", String(sceneProgress));
      section.style.setProperty("--lp", String(lineProgress));
      section.style.setProperty("--gp", "0");
    }
    chapterEl.textContent = chapterTitles[line.chapter] ?? "";
    for (const item of transcript.children) {
      if (item instanceof HTMLElement) {
        if (item.dataset.lineId === line.id) item.setAttribute("aria-current", "true");
        else item.removeAttribute("aria-current");
      }
    }
    for (const item of chapterBar.children) {
      if (item instanceof HTMLElement) {
        if (item.dataset.chapterId === line.chapter) {
          item.setAttribute("aria-current", "true");
          const bar = chapterBar.getBoundingClientRect();
          const box = item.getBoundingClientRect();
          chapterBar.scrollLeft += box.left - bar.left - (bar.width - box.width) / 2;
        } else item.removeAttribute("aria-current");
      }
    }
    captionEl.textContent = captionsOn ? line.text : "";
  }

  function loop() {
    render();
    if (!audio.paused && !audio.ended) requestAnimationFrame(loop);
  }

  playButton.addEventListener("click", () => {
    if (audio.paused) audio.play();
    else audio.pause();
  });
  document.getElementById("kataribe-prev").addEventListener("click", () => moveToLine(-1));
  document.getElementById("kataribe-next").addEventListener("click", () => moveToLine(1));
  seekBar.addEventListener("input", () => {
    audio.currentTime = Number(seekBar.value);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    const target = event.target;
    // 再生位置のバーでも、他のボタンと同じく矢印キーは行の移動にする（バー自身の刻みは細かすぎる）
    if (target instanceof HTMLElement && target !== seekBar && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
    event.preventDefault();
    moveToLine(event.key === "ArrowRight" ? 1 : -1);
  });
  const rateSelect = document.getElementById("kataribe-rate");
  rateSelect.addEventListener("change", () => {
    // defaultPlaybackRate も揃えて、音声の読み込み直しがあっても速度を保つ
    audio.defaultPlaybackRate = audio.playbackRate = Number(rateSelect.value);
  });
  transcriptButton.addEventListener("click", () => {
    const open = transcript.hidden;
    transcript.hidden = !open;
    transcriptButton.setAttribute("aria-expanded", String(open));
  });
  captionsButton.addEventListener("click", () => {
    captionsOn = !captionsOn;
    captionsButton.setAttribute("aria-pressed", String(captionsOn));
    render();
  });
  audio.addEventListener("play", () => {
    playLabel.textContent = "一時停止";
    playButton.dataset.playing = "true";
    loop();
  });
  for (const type of ["pause", "ended"]) {
    audio.addEventListener(type, () => {
      playLabel.textContent = "再生";
      delete playButton.dataset.playing;
      render();
    });
  }
  for (const type of ["timeupdate", "seeked", "loadedmetadata", "durationchange"]) audio.addEventListener(type, render);
  render();
  figures.ready.then(() => {
    charactersReady = true;
    figures.layout();
    render();
    document.documentElement.dataset.kataribeCast = "ready"; // shoot と mp4 は、これを待ってから撮る
  });
  window.addEventListener("resize", () => {
    if (!charactersReady) return;
    figures.layout();
    render();
  });
})();
