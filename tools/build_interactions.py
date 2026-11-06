#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给角色补「互动动作」（复制）与「喂食动画」（程序合成），不改动已有素材。

产出：
    assets/<角色>/interactions/<中文名>.webm     6 段现成交互动作，直接复制
    assets/<角色>/posters/互动-<中文名>.webp      每段一张首帧
    assets/<角色>/food/<食物>-喂食.webm           静态食物图 + 程序位移合成（可选）

跑完自动调用 build_character_preview 刷新 assets/<角色>/预览.html —— 它会把
interactions/ 和 food/ 里的素材并进页面，不会漏掉。

喂食动画的时间线：
    0.00 ~ 0.35s   食物从画面顶部外落到嘴前（重力加速）
    0.35 ~ 0.55s   停住，完全静止
    0.55 ~ 0.88s   第一口：左侧圆咬下去
    0.88 ~ 1.22s   第二口：右侧圆咬下去
    1.22 ~ 1.51s   保持被咬两口的样子
    1.51 ~ 2.20s   缩小 + 淡出
    2.20 ~ 2.60s   空镜

用法：
    python tools/build_interactions.py claude
    python tools/build_interactions.py claude deepseek qwen kimi
    python tools/build_interactions.py claude --foods rice pudding --force
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "references" / "AIBuddy" / "builds"
FFMPEG = ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"

FPS = 30
FEED_FRAMES = 78          # 2.6s
FOOD_RATIO = 0.145        # 食物最大边长 = 角色 alpha 高度 × 0.145（claude 实测 80px/557px）
MOUTH_RATIO = 0.42        # 落点在 bbox 高度的 42%：下巴下方、胸前上方

# 各角色头身比不同，落点按角色微调（不列出的用 MOUTH_RATIO）
# 值 = 食物中心在 alpha 高度上的位置。下巴大致在 0.34~0.40，
# 再让出半个碗的高度（约 0.05~0.07）才不盖住嘴。
MOUTH_RATIO_BY_CHAR: dict[str, float] = {
    "chatgpt": 0.50,
    "claude": 0.42,      # 头小身长，0.42 已经落在下巴下方
    "deepseek": 0.52,
    "gemini": 0.50,
    "glm": 0.50,
    "grok": 0.52,
    "hunyuan": 0.52,
    "kimi": 0.50,
    "minimax": 0.53,
    "qwen": 0.51,
    "seed": 0.51,
}

# 互动动作目录名（带版本后缀） -> (中文名, 说明)
INTERACTIONS = {
    "throw-start": ("抛出-起手", "抓起瞬间，1.2s"),
    "throw-loop": ("抛出-飞行", "被拎在空中晃动，可循环"),
    "land-recover": ("抛出-落地起身", "松手落地、踉跄站起"),
    "sleep-enter": ("睡眠-入睡", "空闲超时后睡着"),
    "sleep-loop": ("睡眠-循环", "睡着后的呼吸循环"),
    "wake": ("睡眠-唤醒", "点击唤醒"),
}


def find_build() -> Path:
    builds = [p for p in BUILD.iterdir() if p.is_dir()]
    if not builds:
        sys.exit(f"找不到 build 目录：{BUILD}")
    return max(builds, key=lambda p: p.stat().st_mtime)


def stage_interactions(character: str, build: Path, out_dir: Path,
                       force: bool) -> list[dict]:
    """复制 6 段现成交互动作。"""
    src_root = build / "assets" / "interaction-samples" / character
    if not src_root.is_dir():
        print(f"  {character} 没有互动素材目录，跳过")
        return []

    rows: list[dict] = []
    for d in sorted(src_root.iterdir()):
        if not d.is_dir():
            continue
        key = next((k for k in INTERACTIONS if d.name.startswith(k)), None)
        if not key:
            print(f"  未知动作，跳过：{d.name}")
            continue
        cn, note = INTERACTIONS[key]
        src_webm = d / "motion.webm"
        if not src_webm.exists():
            print(f"  {cn} 跳过：没有 motion.webm")
            continue

        dst = out_dir / "interactions" / f"{cn}.webm"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if force or not dst.exists():
            shutil.copy2(src_webm, dst)
        poster = out_dir / "posters" / f"互动-{cn}.webp"
        if force or not poster.exists():
            first = d / "first.webp"
            if first.exists():
                poster.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(first, poster)
        print(f"  {cn:14} <- {d.name[:22]:24} {dst.stat().st_size/1024:6.0f} KB")
        rows.append({"cn": cn, "note": note, "path": dst, "poster": poster.exists()})
    return rows


def _ease_in(t: float) -> float:
    """重力下落：二次加速。"""
    return t * t


def _ease_out(t: float) -> float:
    """咬的推进：先快后慢，模仿一口下去停住。"""
    return 1 - (1 - t) ** 3


def find_mouth(frame: Image.Image, character: str = "") -> tuple[int, int]:
    """用 alpha 包围盒估算嘴部坐标（角色为全身 Q 版，头在顶部）。

    0.22 会落在眼睛高度、0.30 仍糊住下半张脸，食物会把脸堵住；
    0.42 落到下巴下方，视觉上像食物被递到胸前。
    头身比各角色不同，所以允许按角色覆写。
    """
    bbox = frame.getchannel("A").getbbox()
    if not bbox:
        return frame.width // 2, int(frame.height * 0.5)
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) // 2
    ratio = MOUTH_RATIO_BY_CHAR.get(character, MOUTH_RATIO)
    mouth_y = y0 + int((y1 - y0) * ratio)
    return cx, mouth_y


def compose_feeding(character: str, build: Path, food_name: str, out_dir: Path,
                    tmp: Path, force: bool = False) -> Path | None:
    """用角色 idle 当底，静态食物图叠加位移，合成喂食动画。"""
    idle_webm = build / "assets" / "pet-characters" / character / "idle" / "motion.webm"
    food_src = build / "assets" / "food" / f"{food_name}.webp"
    if not idle_webm.exists() or not food_src.exists():
        print(f"  {food_name} 跳过：缺素材")
        return None

    dst = out_dir / "food" / f"{food_name}-喂食.webm"
    if dst.exists() and not force:
        print(f"  {food_name:14} 已存在，跳过（--force 可重建）")
        return dst

    # ① 抽 idle 帧（必须显式 libvpx-vp9，否则丢 alpha）
    frames_dir = tmp / f"idle_{food_name}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(FFMPEG), "-v", "error", "-c:v", "libvpx-vp9", "-i", str(idle_webm),
         "-frames:v", str(FEED_FRAMES), "-pix_fmt", "rgba",
         "-y", str(frames_dir / "f_%04d.png")],
        capture_output=True, text=True, timeout=180,
    )
    bases = sorted(frames_dir.glob("f_*.png"))
    if not bases:
        print(f"  {food_name} 跳过：抽帧失败")
        return None
    while len(bases) < FEED_FRAMES:          # idle 短于需求时循环补足
        bases = bases + bases[: FEED_FRAMES - len(bases)]

    # ② 按角色身高定食物大小（各角色在画面里占比 68%~87%，写死像素会忽大忽小）
    first = Image.open(bases[0]).convert("RGBA")
    bbox = first.getchannel("A").getbbox()
    char_h = (bbox[3] - bbox[1]) if bbox else first.height
    food_side = max(32, int(char_h * FOOD_RATIO))

    food = Image.open(food_src).convert("RGBA")
    scale = food_side / max(food.size)
    food = food.resize((max(1, int(food.width * scale)), max(1, int(food.height * scale))),
                       Image.LANCZOS)
    fw, fh = food.size

    mouth_x, mouth_y = find_mouth(first, character)
    start_y = -fh                        # 画面顶部之外
    land_y = mouth_y - fh // 2           # 停在嘴前
    land_x = mouth_x - fw // 2

    out_frames = tmp / f"feed_{food_name}"
    out_frames.mkdir(parents=True, exist_ok=True)

    # 两口咬痕的圆心与最大半径（相对食物尺寸）
    # 圆心压在上边缘之外，圆长进来时就是「从上方被咬出半圆缺口」
    bite_circles = [
        ((fw * 0.34, fh * -0.06), fh * 0.44),   # 第一口：偏左
        ((fw * 0.70, fh * 0.02), fh * 0.36),    # 第二口：偏右
    ]

    def bite_mask(r1: float, r2: float) -> Image.Image:
        """返回尺寸 fw×fh 的遮罩：白=保留，黑=被咬掉。"""
        mask = Image.new("L", (fw, fh), 255)
        draw = ImageDraw.Draw(mask)
        for (center, r_max), prog in zip(bite_circles, (r1, r2)):
            if prog <= 0:
                continue
            radius = r_max * prog
            cx, cy = center
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=0)
        return mask

    for i, base_path in enumerate(bases[:FEED_FRAMES]):
        t = i / FEED_FRAMES              # 0~1
        base = Image.open(base_path).convert("RGBA")

        # 时间线分段：下落 → 停住（不震）→ 咬两口 → 缩小淡出 → 空镜
        if t < 0.135:                    # 0.00~0.35s 下落
            p = _ease_in(t / 0.135)
            y = start_y + (land_y - start_y) * p
            x, scale_k, alpha = land_x, 1.0, 1.0
            r1 = r2 = 0.0
        elif t < 0.21:                   # 0.35~0.55s 停住，完全静止
            y, x, scale_k, alpha = land_y, land_x, 1.0, 1.0
            r1 = r2 = 0.0
        elif t < 0.34:                   # 0.55~0.88s 第一口
            p = _ease_out((t - 0.21) / 0.13)
            y, x, scale_k, alpha = land_y, land_x, 1.0, 1.0
            r1, r2 = p, 0.0
        elif t < 0.47:                   # 0.88~1.22s 第二口
            p = _ease_out((t - 0.34) / 0.13)
            y, x, scale_k, alpha = land_y, land_x, 1.0, 1.0
            r1, r2 = 1.0, p
        elif t < 0.58:                   # 1.22~1.51s 保持被咬两口的样子
            y, x, scale_k, alpha = land_y, land_x, 1.0, 1.0
            r1 = r2 = 1.0
        elif t < 0.846:                  # 1.51~2.20s 缩小淡出
            p = (t - 0.58) / 0.266
            y = land_y
            x, scale_k, alpha = land_x, max(0.05, 1 - p), max(0.0, 1 - p)
            r1 = r2 = 1.0
        else:                            # 2.20~2.60s 空镜
            base.save(out_frames / f"c_{i:04d}.png")
            continue

        if scale_k < 0.999:
            w2, h2 = max(1, int(fw * scale_k)), max(1, int(fh * scale_k))
            layer = food.resize((w2, h2), Image.LANCZOS)
            dx = x + (fw - w2) // 2
            dy = y + (fh - h2) // 2
            bite = bite_mask(r1, r2).resize((w2, h2), Image.LANCZOS)
        else:
            layer, dx, dy = food, x, y
            bite = bite_mask(r1, r2)

        # 把咬痕从食物 alpha 里挖掉，露出后面的角色
        if r1 > 0 or r2 > 0:
            layer = layer.copy()
            layer.putalpha(ImageChops.multiply(layer.getchannel("A"), bite))

        if alpha < 0.999:
            a = layer.getchannel("A").point(lambda v: int(v * alpha))
            layer = layer.copy()
            layer.putalpha(a)

        # paste 对负坐标会自己裁剪，食物从画面外落下时用得上
        base.paste(layer, (int(dx), int(dy)), layer)
        base.save(out_frames / f"c_{i:04d}.png")

    # ③ 编码回 VP9-alpha
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(FFMPEG), "-v", "error", "-framerate", str(FPS),
         "-i", str(out_frames / "c_%04d.png"),
         "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
         "-b:v", "0", "-crf", "34", "-auto-alt-ref", "0",
         "-y", str(dst)],
        capture_output=True, text=True, timeout=300,
    )
    if not dst.exists():
        print(f"  {food_name} 编码失败")
        return None

    # poster 取食物停在嘴边的帧（第 0 帧食物还在画面外，不能用）
    poster = out_dir / "posters" / f"喂食-{food_name}.webp"
    poster.parent.mkdir(parents=True, exist_ok=True)
    poster_src = out_frames / "c_0018.png"
    if not poster_src.exists():
        poster_src = out_frames / "c_0000.png"
    Image.open(poster_src).convert("RGBA").save(poster, "WEBP", quality=88)

    print(f"  {food_name:14} -> 喂食动画 {dst.stat().st_size/1024:6.0f} KB")
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description="给角色补互动动作与喂食动画")
    ap.add_argument("characters", nargs="+", help="角色 id，如 claude deepseek qwen")
    ap.add_argument("--foods", nargs="*", default=[],
                    help="要合成喂食动画的食物名（不填则只做互动）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = ap.parse_args()

    # 延迟导入，避免循环依赖
    sys.path.insert(0, str(Path(__file__).parent))
    from build_character_preview import build as build_preview
    from build_character_preview import build_index

    build = find_build()
    print(f"build {build.name}")

    for character in args.characters:
        out_dir = ROOT / "assets" / character
        print(f"\n[{character}] 互动动作")
        rows = stage_interactions(character, build, out_dir, args.force)

        if args.foods:
            print(f"\n[{character}] 喂食动画")
            with tempfile.TemporaryDirectory(prefix="feed_") as td:
                tmp = Path(td)
                for name in args.foods:
                    compose_feeding(character, build, name, out_dir, tmp, args.force)
            foods = sorted((out_dir / "food").glob("*-喂食.webm"))
        else:
            foods = []

        print(f"\n[{character}] 完成：互动 {len(rows)} 段，喂食 {len(foods)} 段")

        # 统一由 build_character_preview 生成页面，extras 会被自动扫进去
        build_preview(character, False)

    build_index()


if __name__ == "__main__":
    main()
