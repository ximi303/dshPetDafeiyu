#!/usr/bin/env python3
"""把开机 logo 文字渲染成点阵，生成 C 头文件。

LovyanGFX 内置字体只有 ASCII，中文必须自带点阵。这里用系统黑体渲染成
32x32 的 1bpp 位图（每行 4 字节，MSB first），供 drawBitmap() 直接使用。

用法（任意目录均可）：
    python tools/gen_boot_logo.py

产物：
    firmware/include/boot_logo.h

改文字只需改下面的 TEXT，重新跑一次。
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXT = "西米造物"
GLYPH = 32                                    # 单字边长（像素）
FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"    # 黑体
FONT_SIZE = 30                                # 略小于 32，留出上下留白
ROW_BYTES = GLYPH // 8                        # 32px → 4 字节/行

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "firmware" / "include" / "boot_logo.h"


def render_glyph(ch: str, font) -> list[int]:
    """渲染单个字符为行优先的字节序列。"""
    img = Image.new("1", (GLYPH, GLYPH), 0)
    draw = ImageDraw.Draw(img)

    # 按实际墨迹范围居中，避免不同字形的左/上边距差异导致视觉不齐
    left, top, right, bottom = draw.textbbox((0, 0), ch, font=font)
    x = (GLYPH - (right - left)) // 2 - left
    y = (GLYPH - (bottom - top)) // 2 - top
    draw.text((x, y), ch, font=font, fill=1)

    rows: list[int] = []
    for row in range(GLYPH):
        for byte_idx in range(ROW_BYTES):
            value = 0
            for bit in range(8):
                if img.getpixel((byte_idx * 8 + bit, row)):
                    value |= 0x80 >> bit
            rows.append(value)
    return rows


def preview(glyphs: list[list[int]]) -> None:
    """在终端用 ASCII 打出点阵，确认字形没糊。"""
    for ch, rows in zip(TEXT, glyphs):
        print(f"--- {ch} ---")
        for row in range(GLYPH):
            line = ""
            for byte_idx in range(ROW_BYTES):
                byte = rows[row * ROW_BYTES + byte_idx]
                for bit in range(8):
                    line += "#" if byte & (0x80 >> bit) else "."
            print(line)
        print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="终端打印点阵预览")
    args = ap.parse_args()

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    glyphs = [render_glyph(ch, font) for ch in TEXT]

    if args.preview:
        preview(glyphs)

    lines = [
        "// 自动生成，请勿手改。",
        "// 生成脚本：tools/gen_boot_logo.py",
        f"// 文字：{TEXT}   点阵：{GLYPH}x{GLYPH} 1bpp（每行 {ROW_BYTES} 字节，MSB first）",
        "#pragma once",
        "",
        "#include <cstdint>",
        "",
        "namespace pet {",
        "namespace boot_logo {",
        "",
        f"static constexpr int kGlyphSize  = {GLYPH};",
        f"static constexpr int kGlyphCount = {len(TEXT)};",
        "",
        f"static const uint8_t kGlyphs[kGlyphCount][{GLYPH * ROW_BYTES}] = {{",
    ]
    for ch, rows in zip(TEXT, glyphs):
        lines.append(f"    {{  // '{ch}'")
        for start in range(0, len(rows), ROW_BYTES):
            chunk = ", ".join(f"0x{v:02X}" for v in rows[start:start + ROW_BYTES])
            lines.append(f"        {chunk},")
        lines.append("    },")
    lines += [
        "};",
        "",
        "}  // namespace boot_logo",
        "}  // namespace pet",
        "",
    ]

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成 {OUT}")
    print(f"  {len(TEXT)} 个字，每字 {GLYPH * ROW_BYTES} 字节，合计 {len(TEXT) * GLYPH * ROW_BYTES} 字节")


if __name__ == "__main__":
    main()
