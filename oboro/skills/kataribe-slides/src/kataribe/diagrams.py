"""スライドの図（scenes.html のシーンの section）を、行ごとの状態で画像にする。

動画のステージと同じ 1280x720 の箱（余白 24px、CSS の変数と行単位の出現・強調の規則も同じ）に置いて撮るので、
動画用に書いた scenes.html が、そのままスライドの図になる。背景は透明にして、スライドの地に重ねる。
"""

import html

from kataribe.browser import FREEZE_CSS, launch
from kataribe.project import Project
from kataribe.scenes import section_ids

STAGE_W, STAGE_H = 1280, 720
SCALE = 1.5  # 撮る画像は 1920x1080

PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>{title}</title><style>
:root {{ --bg: #ffffff; --fg: #1c1c1c; --muted: #666; --line: #d9d6cc; }}
html, body {{ margin: 0; background: transparent; color: var(--fg); font-family: system-ui, "Hiragino Sans", "Noto Sans JP", sans-serif; }}
#kataribe-stage {{ position: relative; width: {w}px; height: {h}px; padding: 24px; box-sizing: border-box; overflow: hidden; }}
#kataribe-stage section[data-scene]:not(.kataribe-active) {{ display: none; }}
#kataribe-stage [data-kataribe-state="hidden"] {{ visibility: hidden; }}
#kataribe-stage [data-kataribe-focus-state="active"] {{ outline: 3px solid var(--fg); outline-offset: 3px; }}
#kataribe-stage [data-kataribe-focus-state="dim"] {{ opacity: 0.35; }}
{freeze}
</style></head><body><div id="kataribe-stage">
{scenes}
</div></body></html>
"""

# 行 at（シーンの中の番号）の見た目にする。規則は player.js と同じ。進行変数は、その行が終わった時点の値。
APPLY = """([scene, at, count]) => {
  const stage = document.getElementById('kataribe-stage');
  let active = null;
  for (const section of stage.querySelectorAll(':scope > section[data-scene]')) {
    const on = section.dataset.scene === scene;
    section.classList.toggle('kataribe-active', on);
    if (on) active = section;
  }
  if (!active) return false;
  for (const el of active.querySelectorAll('[data-at],[data-out]')) {
    const from = el.hasAttribute('data-at') ? Number(el.dataset.at) : 0;
    const until = el.hasAttribute('data-out') ? Number(el.dataset.out) : Infinity;
    if (at >= from && at < until) el.removeAttribute('data-kataribe-state');
    else el.setAttribute('data-kataribe-state', 'hidden');
  }
  const groups = new Map();
  for (const el of active.querySelectorAll('[data-focus]')) {
    const members = groups.get(el.parentElement) ?? [];
    members.push({ el, lines: new Set(el.dataset.focus.split(',').map((n) => Number(n.trim()))) });
    groups.set(el.parentElement, members);
  }
  for (const members of groups.values()) {
    const any = members.some((m) => m.lines.has(at));
    for (const m of members) {
      if (!any) m.el.removeAttribute('data-kataribe-focus-state');
      else m.el.setAttribute('data-kataribe-focus-state', m.lines.has(at) ? 'active' : 'dim');
    }
  }
  active.style.setProperty('--p', String((at + 1) / count));
  active.style.setProperty('--lp', '1');
  active.style.setProperty('--gp', '0');
  return true;
}"""


def scenes_with_diagram(project: Project) -> set[str]:
    """図のあるシーン（台本にあり、scenes.html に section もあるシーン）。"""
    return section_ids(project.scenes_html) & {scene.id for scene in project.scenes}


def render_diagrams(project: Project) -> dict[int, bytes]:
    """行の番号（project.lines の添字）→ その行の時点の図の PNG。図のあるシーンの行だけ。"""
    wanted = scenes_with_diagram(project)
    if not wanted:
        return {}
    from playwright.sync_api import sync_playwright

    scene_lines: dict[str, list[int]] = {}
    for index, line in enumerate(project.lines):
        scene_lines.setdefault(line.scene_id, []).append(index)
    page_html = PAGE.format(title=html.escape(project.title), w=STAGE_W, h=STAGE_H, freeze=FREEZE_CSS, scenes=project.scenes_html)
    images: dict[int, bytes] = {}
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            page = browser.new_page(viewport={"width": STAGE_W, "height": STAGE_H}, device_scale_factor=SCALE, color_scheme="light")
            page.set_content(page_html, wait_until="load")
            page.evaluate("document.fonts.ready")
            stage = page.locator("#kataribe-stage")
            for scene, indexes in scene_lines.items():
                if scene not in wanted:
                    continue
                for at, index in enumerate(indexes):
                    page.evaluate(APPLY, [scene, at, len(indexes)])
                    images[index] = stage.screenshot(omit_background=True, animations="disabled")
        finally:
            browser.close()
    return images
