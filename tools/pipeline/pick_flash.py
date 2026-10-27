"""阶段 1 用：从全量产物里挑几段，放进 firmware/data/ 供 uploadfs 烧进 Flash。

用法（在 tools/pipeline 目录下，路径全部相对本脚本定位）：
    python pick_flash.py            # 按下面的 PICKS 清单挑段 → firmware/data/packs/
    python pick_flash.py --list     # 列出全量 106 段，方便挑
    python pick_flash.py --clear    # 清空 firmware/data/packs/

产物：
    firmware/data/packs/<分类>/<名字>.petpack
    firmware/data/packs/index.json

挑完之后烧录：
    pio run -t uploadfs

想换段就改下面的 PICKS。
"""

import json
import shutil
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent        # tools/pipeline/
PROJ = HERE.parent.parent                     # 项目根

SD     = PROJ / "assets" / "sdcard"           # 全量产物（阶段 2 的 SD 卡镜像根）
PACKS  = SD / "packs"
DATA   = PROJ / "firmware" / "data" / "packs" # 阶段 1 的 Flash 镜像源

MAGIC = b"PETP"
HEADER_SIZE = 22
HEADER_FMT = "<4sHHHHHII"   # magic, version, w, h, fps, frameCount, flags, reserved

# 分区表里 storage 是 11.93MB，留约 1MB 给文件系统元数据
FLASH_BUDGET_MB = 11.0

# ------------------------------------------------------------------
# 第一阶段清单：先跑通「取帧 → 解码 → 刷屏 → 循环」这条链路
#   待机 1 段（一动不动时播的）+ 点击 2 段（验证触发切换）+ 拖拽 1 段 + 工作状态 1 段
# 跑通之后想扩，往这里加即可；容量账见 docs/目录结构说明.md
# ------------------------------------------------------------------
PICKS = [
    ("待机", "待机呼吸休闲"),
    ("点击回应", "点击回应-开心跃动"),
    ("点击回应", "点击回应-元气挥手"),
    ("拖拽", "被鼠标拖拽悬空反馈"),
    ("事件-工作状态", "工作状态-雀跃庆祝"),
]


def read_header(path):
    """只读 22 字节头，拿帧数/尺寸/帧率，顺便验一下 magic。"""
    with open(path, "rb") as f:
        raw = f.read(HEADER_SIZE)
    if len(raw) < HEADER_SIZE:
        return None
    magic, version, w, h, fps, frame_count, flags, _ = struct.unpack(HEADER_FMT, raw)
    if magic != MAGIC:
        return None
    return {"version": version, "width": w, "height": h, "fps": fps,
            "frames": frame_count, "loop": bool(flags & 1)}


def cmd_list():
    if not PACKS.exists():
        sys.exit(f"全量产物目录不存在：{PACKS}\n先跑 python pipeline.py 生成。")
    print(f"全量 {len(list(PACKS.rglob('*.petpack')))} 段：\n")
    for group in sorted(p for p in PACKS.iterdir() if p.is_dir()):
        print(f"[{group.name}]")
        for f in sorted(group.glob("*.petpack")):
            print(f"    {f.stem:<24} {f.stat().st_size / 1048576:>6.2f} MB")
        print()


def cmd_clear():
    if DATA.exists():
        shutil.rmtree(DATA)
        print(f"已清空 {DATA}")
    else:
        print(f"{DATA} 本来就不存在")


def main():
    if not PACKS.exists():
        sys.exit(f"全量产物目录不存在：{PACKS}\n先跑 python pipeline.py 生成。")

    if not PICKS:
        sys.exit("PICKS 是空的，先在文件里填上要挑的段。")

    DATA.mkdir(parents=True, exist_ok=True)

    index = []
    missing = []
    total = 0

    for group, name in PICKS:
        src = PACKS / group / f"{name}.petpack"
        if not src.exists():
            missing.append(f"{group}/{name}")
            continue

        hdr = read_header(src)
        if hdr is None:
            missing.append(f"{group}/{name}（头部损坏）")
            continue

        dst_dir = DATA / group
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{name}.petpack"
        shutil.copy2(src, dst)

        size = dst.stat().st_size
        total += size
        index.append({
            "group": group,
            "name": name,
            "pack": f"packs/{group}/{name}.petpack",
            "frames": hdr["frames"],
            "fps": hdr["fps"],
            "width": hdr["width"],
            "height": hdr["height"],
            "loop": hdr["loop"],
            "bytes": size,
        })
        # 控制台是 GBK，别用 ✓/✗/⚠ 这类字符，会 UnicodeEncodeError
        print(f"  [ok] {group}/{name:<22} {hdr['frames']:>3} 帧  {size / 1048576:>6.2f} MB")

    (DATA / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    total_mb = total / 1048576
    print(f"\n挑了 {len(index)} 段，合计 {total_mb:.2f} MB → {DATA}")

    if missing:
        print(f"\n没找到 {len(missing)} 段：")
        for m in missing:
            print(f"  [miss] {m}")
        print("（用 python pick_flash.py --list 看全量清单）")

    if total_mb > FLASH_BUDGET_MB:
        print(f"\n[warn] 超出 Flash 预算 {FLASH_BUDGET_MB:.1f} MB，uploadfs 会失败，请减少段数。")
        sys.exit(1)

    print(f"Flash 预算 {FLASH_BUDGET_MB:.1f} MB，剩余 {FLASH_BUDGET_MB - total_mb:.2f} MB")
    print("\n下一步：pio run -t uploadfs")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--list" in args:
        cmd_list()
    elif "--clear" in args:
        cmd_clear()
    else:
        main()
