// 立ち絵の canvas を作って描く（動画のプレーヤーとスライドが使う）。どの表情・口・目にするかは cast.js が決める。
//
// 1280x720 のステージで、高さ 530px、上端 390px（上半身を見せる）、中心は端から 150px（yes と同じ比率）。
// 縮小した画像の重ね合わせはブラウザの描画のタイミングで端の画素が揺れるので、ステージの実際の画素に合わせた
// canvas に自分で描く。同じ時刻なら毎回同じ画素になり、shoot と mp4 の撮影も揃う。
window.KataribeFigures = (() => {
  const CHAR_HEIGHT = 530 / 720, CHAR_TOP = 390 / 720, CHAR_CENTER = 150 / 1280;

  function create(container, cast) {
    const characters = [];
    for (const entry of cast) {
      const boxes = Object.values(entry.layers);
      const left = Math.min(...boxes.map((b) => b.x)), top = Math.min(...boxes.map((b) => b.y));
      const bounds = { left, top, width: Math.max(...boxes.map((b) => b.x + b.w)) - left, height: Math.max(...boxes.map((b) => b.y + b.h)) - top };
      const canvas = document.createElement("canvas");
      canvas.className = "kataribe-character";
      canvas.dataset.speaker = entry.speaker;
      const images = {};
      for (const [path, layer] of Object.entries(entry.layers)) {
        const image = new Image();
        image.src = layer.src;
        images[path] = image;
      }
      container.appendChild(canvas);
      characters.push({
        entry,
        canvas,
        images,
        bounds,
        mirrored: KataribeCast.mirrored(entry.side, entry.facing),
        seed: KataribeCast.seedOf(entry.speaker),
        drawn: "",
      });
    }

    function layout() {
      const stageWidth = container.clientWidth, stageHeight = container.clientHeight;
      const ratio = window.devicePixelRatio || 1;
      for (const c of characters) {
        const height = Math.round(stageHeight * CHAR_HEIGHT);
        const width = Math.round((height * c.bounds.width) / c.bounds.height);
        const center = (c.entry.side === "left" ? CHAR_CENTER : 1 - CHAR_CENTER) * stageWidth;
        Object.assign(c.canvas.style, {
          left: `${Math.round(center - width / 2)}px`,
          top: `${Math.round(stageHeight * CHAR_TOP)}px`,
          width: `${width}px`,
          height: `${height}px`,
        });
        c.canvas.width = Math.round(width * ratio);
        c.canvas.height = Math.round(height * ratio);
        c.drawn = "";
      }
    }

    function draw(c, active) {
      const key = `${active.join("\n")}|${c.canvas.width}x${c.canvas.height}`;
      if (c.drawn === key) return;
      c.drawn = key;
      const ctx = c.canvas.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, c.canvas.width, c.canvas.height);
      const sx = c.canvas.width / c.bounds.width, sy = c.canvas.height / c.bounds.height;
      if (c.mirrored) ctx.setTransform(-sx, 0, 0, sy, c.canvas.width, 0);
      else ctx.setTransform(sx, 0, 0, sy, 0, 0);
      ctx.translate(-c.bounds.left, -c.bounds.top);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      for (const path of active) {
        const layer = c.entry.layers[path];
        ctx.globalCompositeOperation = layer.blend === "normal" ? "source-over" : layer.blend;
        ctx.drawImage(c.images[path], layer.x, layer.y, layer.w, layer.h);
      }
      ctx.globalCompositeOperation = "source-over";
    }

    const allImages = characters.flatMap((c) => Object.values(c.images));
    const ready = Promise.all(allImages.map((image) => image.decode().catch(() => {})));
    return { characters, layout, draw, ready };
  }

  return { create };
})();
