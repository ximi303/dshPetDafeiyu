#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 AI 酱（AI Buddy）安装目录抽取角色桌宠动作，生成 assets/<角色>/ 预览页。

源素材是 VP9-alpha 的 motion.webm（576x624，透明背景），原样复制不转码，
浏览器可直接透明播放。

用法：
    python tools/build_character_preview.py claude
    python tools/build_character_preview.py claude deepseek
    python tools/build_character_preview.py claude --force

输出结构：
    assets/<角色>/source-webm/<分组>/<中文名>.webm
    assets/<角色>/posters/<中文名>.webp
    assets/<角色>/预览.html
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL_ROOT = ROOT / "references" / "AIBuddy" / "builds"
FFPROBE = ROOT / "tools" / "ffmpeg" / "bin" / "ffprobe.exe"
FFMPEG = ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"

# 角色 id -> (显示名, 中文名/来源)
# 预览页标题和总览页都用这个，避免只有英文 id 不好认。
DISPLAY_NAMES: dict[str, tuple[str, str]] = {
    "claude": ("Claude", "Anthropic · 克劳德"),
    "deepseek": ("DeepSeek", "深度求索 · 蓝鲸"),
    "chatgpt": ("ChatGPT", "OpenAI"),
    "gemini": ("Gemini", "Google"),
    "glm": ("GLM", "智谱清言"),
    "grok": ("Grok", "xAI"),
    "hunyuan": ("Hunyuan", "腾讯混元"),
    "kimi": ("Kimi", "月之暗面"),
    "minimax": ("MiniMax", "稀宇科技"),
    "qwen": ("Qwen", "通义千问"),
    "seed": ("Seed", "字节跳动"),
}


def display_name(character: str) -> tuple[str, str]:
    return DISPLAY_NAMES.get(character, (character.capitalize(), ""))


# 动作目录 -> (中文名, 分组, 说明)
# 分组顺序决定预览页的章节顺序，见 GROUPS。
ACTIONS: dict[str, tuple[str, str, str]] = {
    "idle": ("待机呼吸", "待机", "空闲循环，权重最高"),
    "wave": ("挥手问候", "点击回应", "点按宠物时随机抽 1 个"),
    "jump": ("雀跃跳跃", "点击回应", "点按宠物时随机抽 1 个"),
    "emotion-cheerful": ("开心大笑", "情绪表情", "按事件类型选播"),
    "emotion-angry": ("生气鼓脸", "情绪表情", "按事件类型选播"),
    "emotion-confused": ("困惑歪头", "情绪表情", "按事件类型选播"),
    "emotion-exasperated": ("无奈叹气", "情绪表情", "按事件类型选播"),
    "emotion-serious": ("严肃凝视", "情绪表情", "按事件类型选播"),
    "emotion-shy": ("害羞脸红", "情绪表情", "按事件类型选播"),
    "emotion-starry": ("星星眼", "情绪表情", "按事件类型选播"),
    "emotion-frightened": ("惊恐发抖", "情绪表情", "按事件类型选播"),
    "move-left": ("向左奔跑", "移动", "带位移，向左移动时播放"),
    "move-right": ("向右奔跑", "移动", "带位移，向右移动时播放"),
    "look": ("十六方向张望", "视线", "空闲时跟随目光，16 个方向"),
    "working": ("专注工作", "工作状态", "DSH 有会话在跑时播放"),
    "reviewing": ("托腮审查", "工作状态", "回复生成后的展示阶段"),
    "waiting": ("摊手等待", "工作状态", "等待授权或用户回应"),
    "fail": ("垂头失败", "异常", "任务出错或对话失败"),
}

# 段数由模板按实际条目自动算，note 里不要再写
GROUPS: list[tuple[str, str]] = [
    ("待机", "随机链·待机档"),
    ("点击回应", "点按时从中随机抽 1 个"),
    ("情绪表情", "按事件类型索引选播"),
    ("移动", "带位移参数"),
    ("视线", "空闲跟随目光，16 方向"),
    ("工作状态", "DSH 工作状态联动"),
    ("异常", "任务出错时播放"),
]


def find_source(character: str) -> Path:
    """定位 AI 酱安装目录里的角色动作目录。"""
    if not INSTALL_ROOT.is_dir():
        sys.exit(f"找不到安装目录：{INSTALL_ROOT}")
    builds = [p for p in INSTALL_ROOT.iterdir() if p.is_dir()]
    if not builds:
        sys.exit(f"安装目录下没有 build：{INSTALL_ROOT}")
    # 取修改时间最新的一个 build
    build = max(builds, key=lambda p: p.stat().st_mtime)
    src = build / "assets" / "pet-characters" / character
    if not src.is_dir():
        available = sorted(
            p.name for p in (build / "assets" / "pet-characters").iterdir() if p.is_dir()
        )
        sys.exit(f"没有角色 {character}，可选：{', '.join(available)}")
    return src


def probe_duration(webm: Path) -> float:
    """读视频时长（秒），失败返回 0。"""
    if not FFPROBE.exists():
        return 0.0
    try:
        out = subprocess.run(
            [str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(webm)],
            capture_output=True, text=True, timeout=20,
        )
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def pick_poster(action_dir: Path) -> Path | None:
    """找一张首帧当 poster。

    各角色资源结构不一样，按优先级尝试：
      1. static-*.webp   新版：video + 关键帧
      2. stills/*.webp   旧版：逐帧静图
      3. 都没有           返回 None，由调用方从 webm 抽首帧
    """
    statics = sorted(action_dir.glob("static-*.webp"))
    if statics:
        return statics[0]
    stills_dir = action_dir / "stills"
    if stills_dir.is_dir():
        stills = sorted(stills_dir.glob("*.webp"))
        if stills:
            return stills[0]
    return None


def extract_poster(webm: Path, dst: Path) -> bool:
    """从视频抽第一帧存成 webp（用于没有静帧的角色）。

    两个必须踩准的点：
      1. 必须显式 `-c:v libvpx-vp9`，否则默认解码器丢掉 alpha 轨，
         抽出来是黑底不透明图（实测 alpha 全 255）。
      2. ffmpeg 的 libwebp 编码器不保留 alpha，所以先落 PNG 再用 PIL 转 webp。
    """
    if not FFMPEG.exists():
        return False
    tmp = dst.with_suffix(".tmp.png")
    try:
        subprocess.run(
            [str(FFMPEG), "-v", "error", "-c:v", "libvpx-vp9", "-i", str(webm),
             "-frames:v", "1", "-pix_fmt", "rgba", "-y", str(tmp)],
            capture_output=True, text=True, timeout=60,
        )
        if not tmp.exists():
            return False
        try:
            from PIL import Image
        except ImportError:
            # 没有 PIL 就退化成 png 直接当 poster（浏览器同样能显示）
            tmp.replace(dst.with_suffix(".png"))
            return True
        with Image.open(tmp) as im:
            im.convert("RGBA").save(dst, "WEBP", quality=90, method=4)
        return dst.exists()
    except Exception:
        return False
    finally:
        if tmp.exists():
            tmp.unlink()


def copy_action(src: Path, out_dir: Path, action: str, cn: str, group: str,
                force: bool) -> tuple[Path, Path | None, float] | None:
    """复制一个动作的 webm 与首帧 poster，返回 (webm, poster, 时长)。"""
    action_dir = src / action
    webm_src = action_dir / "motion.webm"
    if not webm_src.exists():
        print(f"  {action:20} 跳过：没有 motion.webm")
        return None

    webm_dst = out_dir / "source-webm" / group / f"{cn}.webm"
    poster_dst = out_dir / "posters" / f"{cn}.webp"
    webm_dst.parent.mkdir(parents=True, exist_ok=True)
    poster_dst.parent.mkdir(parents=True, exist_ok=True)

    if force or not webm_dst.exists():
        shutil.copy2(webm_src, webm_dst)

    poster_written = False
    if force or not poster_dst.exists():
        src_poster = pick_poster(action_dir)
        if src_poster:
            shutil.copy2(src_poster, poster_dst)
            poster_written = True
        else:
            poster_written = extract_poster(webm_dst, poster_dst)
    else:
        poster_written = True

    size_kb = webm_dst.stat().st_size / 1024
    tag = "" if poster_written else "  [无 poster]"
    print(f"  {action:20} -> {group}/{cn}.webm   {size_kb:6.0f} KB{tag}")
    return webm_dst, poster_dst if poster_written else None, probe_duration(webm_dst)


def scan_extras(out_dir: Path) -> tuple[list[dict], list[dict]]:
    """扫描角色目录下额外生成的素材，有就并入预览页。

    这两类由 tools/build_claude_interactions.py 产出，和本脚本的 18 段基础动作
    分属不同来源，所以不写死在 ACTIONS 表里，而是按目录实际内容拾取。
    """
    interactions: list[dict] = []
    idir = out_dir / "interactions"
    if idir.is_dir():
        for f in sorted(idir.glob("*.webm")):
            poster = out_dir / "posters" / f"互动-{f.stem}.webp"
            interactions.append({
                "cn": f.stem,
                "src": f"interactions/{f.name}",
                "poster": f"posters/互动-{f.stem}.webp" if poster.exists() else "",
                "duration": probe_duration(f),
                "kb": f.stat().st_size / 1024,
            })

    foods: list[dict] = []
    fdir = out_dir / "food"
    if fdir.is_dir():
        for f in sorted(fdir.glob("*-喂食.webm")):
            name = f.stem.replace("-喂食", "")
            poster = out_dir / "posters" / f"喂食-{name}.webp"
            foods.append({
                "cn": name,
                "src": f"food/{f.name}",
                "poster": f"posters/喂食-{name}.webp" if poster.exists() else "",
                "duration": probe_duration(f),
                "kb": f.stat().st_size / 1024,
            })
    return interactions, foods


def _extra_section(title: str, note: str, items: list[dict]) -> str:
    cards = []
    for r in items:
        poster_attr = f'poster="{r["poster"]}" ' if r["poster"] else ""
        cards.append(
            f'<div class="card"><video muted loop playsinline preload="none" '
            f'{poster_attr}src="{r["src"]}"></video>'
            f'<div class="name">{r["cn"]}<em>{r["duration"]:.1f}s</em></div></div>'
        )
    return (f'<h2>{title} <span>{len(items)} 段 · {note}</span></h2>\n'
            f'<div class="grid">\n' + "\n".join(cards) + "\n</div>")


def render_html(character: str, rows: list[dict],
                extras: tuple[list[dict], list[dict]] = ([], [])) -> str:
    """生成与 assets/预览.html 同款样式的预览页。"""
    interactions, foods = extras
    display, cn_label = display_name(character)
    by_group: dict[str, list[dict]] = {}
    for row in rows:
        by_group.setdefault(row["group"], []).append(row)

    total = len(rows) + len(interactions) + len(foods)
    total_mb = (sum(r["kb"] for r in rows)
                + sum(r["kb"] for r in interactions)
                + sum(r["kb"] for r in foods)) / 1024

    sections: list[str] = []
    for group, note in GROUPS:
        items = by_group.get(group)
        if not items:
            continue
        cards = []
        for r in items:
            poster_attr = f'poster="posters/{r["cn"]}.webp" ' if r["poster"] else ""
            cards.append(
                f'<div class="card"><video muted loop playsinline preload="none" '
                f'{poster_attr}'
                f'src="source-webm/{r["group"]}/{r["cn"]}.webm"></video>'
                f'<div class="name">{r["cn"]}<em>{r["duration"]:.1f}s</em></div></div>'
            )
        sections.append(
            f'<h2>{group} <span>{len(items)} 段 · {note}</span></h2>\n'
            f'<div class="grid">\n' + "\n".join(cards) + "\n</div>"
        )

    if interactions:
        sections.append(_extra_section("互动动作", "抛掷 / 睡眠 / 唤醒 完整链路", interactions))
    if foods:
        sections.append(_extra_section("喂食动画", "静态食物图 + 程序位移合成", foods))

    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{display} 桌宠动作预览（{total} 段）</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;padding:28px;background:#0e1220;color:#e8ecf6;font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif}}
h1{{font-size:26px;margin:0 0 8px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}}
h1 .cn{{font-size:13px;font-weight:400;color:#8b94ab;letter-spacing:.5px}}
h1 .badge{{font-size:12px;font-weight:500;color:#9fc0ff;background:#1b2745;
 border:1px solid #2f4a80;border-radius:99px;padding:2px 10px}}
p.sub{{color:#8b94ab;margin:0 0 22px}}
h2{{font-size:16px;margin:30px 0 12px;padding-left:10px;border-left:3px solid #4a7dff}}
h2 span{{color:#8b94ab;font-weight:400;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}}
.card{{background:#161b2e;border:1px solid #232a45;border-radius:10px;overflow:hidden;transition:.15s}}
.card:hover{{border-color:#4a7dff;transform:translateY(-2px)}}
.card video{{width:100%;display:block;background:
 conic-gradient(#1b2136 25%,#141a2b 0 50%,#1b2136 0 75%,#141a2b 0) 0 0/16px 16px}}
.card .name{{padding:6px 9px;font-size:13px;display:flex;justify-content:space-between;gap:6px}}
.card .name em{{color:#7f89a3;font-style:normal;font-size:11px;white-space:nowrap}}
</style></head><body>
<h1>{display}<span class="cn">{cn_label}</span><span class="badge">{total} 段</span></h1>
<p class="sub">角色 id <code>{character}</code> · VP9-alpha 576×624 · 共 {total_mb:.1f} MB。鼠标悬停播放，移开暂停。首帧为 poster，透明区显示为棋盘格。</p>

{body}
<script>
document.querySelectorAll('.card').forEach(c=>{{
  const v=c.querySelector('video');
  c.addEventListener('mouseenter',()=>{{v.play().catch(()=>{{}});}});
  c.addEventListener('mouseleave',()=>{{v.pause();}});
}});
</script></body></html>"""


def build(character: str, force: bool) -> None:
    src = find_source(character)
    out_dir = ROOT / "assets" / character
    print(f"\n[{character}] 源目录 {src.relative_to(ROOT)}")
    print(f"[{character}] 输出到 {out_dir.relative_to(ROOT)}")

    rows: list[dict] = []
    for action, (cn, group, note) in ACTIONS.items():
        got = copy_action(src, out_dir, action, cn, group, force)
        if not got:
            continue
        webm, poster, duration = got
        rows.append({
            "cn": cn, "group": group, "note": note, "poster": poster is not None,
            "duration": duration, "kb": webm.stat().st_size / 1024,
        })

    if not rows:
        print(f"[{character}] 警告：没有找到可用的 motion.webm，跳过该角色")
        return

    extras = scan_extras(out_dir)
    html_path = out_dir / "预览.html"
    html_path.write_text(render_html(character, rows, extras), encoding="utf-8")

    n_inter, n_food = len(extras[0]), len(extras[1])
    total_mb = (sum(r["kb"] for r in rows)
                + sum(r["kb"] for r in extras[0])
                + sum(r["kb"] for r in extras[1])) / 1024
    line = f"\n[{character}] 完成：基础动作 {len(rows)} 段"
    if n_inter or n_food:
        line += f"，互动 {n_inter} 段，喂食 {n_food} 段"
    print(line + f"，共 {total_mb:.1f} MB")
    print(f"[{character}] 预览页 {html_path.relative_to(ROOT)}")


def build_index() -> None:
    """扫描 assets/*/预览.html，生成一个角色总览索引页。"""
    cards: list[str] = []
    total_clips = 0
    total_mb = 0.0
    for d in sorted(p for p in (ROOT / "assets").iterdir() if p.is_dir()):
        page = d / "预览.html"
        if not page.exists():
            continue
        # 基础动作 + 互动 + 喂食，三段都要算进总览
        clips = list((d / "source-webm").rglob("*.webm")) if (d / "source-webm").is_dir() else []
        extras: list[Path] = []
        for sub, pattern in (("interactions", "*.webm"), ("food", "*.webm")):
            sub_dir = d / sub
            if sub_dir.is_dir():
                extras.extend(sub_dir.glob(pattern))
        clips += extras
        if not clips:
            continue
        mb = sum(f.stat().st_size for f in clips) / 1024 / 1024
        poster = d / "posters" / "待机呼吸.webp"
        poster_attr = f'<img src="{d.name}/posters/待机呼吸.webp" alt="">' if poster.exists() else ""
        display, _cn = display_name(d.name)
        cards.append(
            f'<a class="card" href="{d.name}/%E9%A2%84%E8%A7%88.html">{poster_attr}'
            f'<div class="name">{display}<em>{len(clips)} 段 · {mb:.0f} MB</em></div></a>'
        )
        total_clips += len(clips)
        total_mb += mb

    if not cards:
        return

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>角色总览 · {len(cards)} 位</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;padding:28px;background:#0e1220;color:#e8ecf6;font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif}}
h1{{font-size:22px;margin:0 0 6px}}
p.sub{{color:#8b94ab;margin:0 0 22px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:14px}}
.card{{background:#161b2e;border:1px solid #232a45;border-radius:12px;overflow:hidden;
 text-decoration:none;color:inherit;transition:.15s;display:block}}
.card:hover{{border-color:#4a7dff;transform:translateY(-3px)}}
.card img{{width:100%;display:block;background:
 conic-gradient(#1b2136 25%,#141a2b 0 50%,#1b2136 0 75%,#141a2b 0) 0 0/16px 16px}}
.card .name{{padding:8px 10px;font-size:14px;display:flex;justify-content:space-between;gap:6px}}
.card .name em{{color:#7f89a3;font-style:normal;font-size:11px;white-space:nowrap}}
</style></head><body>
<h1>桌宠角色总览 · {len(cards)} 位</h1>
<p class="sub">共 {total_clips} 段动作、{total_mb/1024:.2f} GB。点角色进入该角色预览页。素材源自 AI 酱（VP9-alpha 576×624）。</p>
<div class="grid">
{chr(10).join(cards)}
</div></body></html>"""
    (ROOT / "assets" / "角色总览.html").write_text(html, encoding="utf-8")
    print(f"\n[总览] assets/角色总览.html：{len(cards)} 位角色，{total_clips} 段")


def main() -> None:
    ap = argparse.ArgumentParser(description="从 AI 酱安装目录生成角色桌宠预览页")
    ap.add_argument("characters", nargs="+", help="角色 id，如 claude deepseek gemini")
    ap.add_argument("--force", action="store_true", help="强制重新复制（覆盖已有文件）")
    args = ap.parse_args()
    for character in args.characters:
        build(character, args.force)
    build_index()


if __name__ == "__main__":
    main()
