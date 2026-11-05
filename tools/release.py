#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固件正式版一键发布：记录变更 + 构建烧写文件 + 归档。

一个正式版 = releases/vX.Y.Z/ 目录，内含：
    CHANGELOG.md                      版本号 / 日期 / 功能变更 / ⚠硬件变更备注
    烧写说明.md                        用户视角的烧写教程
    dshpet-vX.Y.Z-merged.bin          合并固件（bootloader+分区表+app），地址 0 一键烧写
    dshpet-vX.Y.Z-littlefs.bin        Flash 动画包，烧到 0x410000
    MD5SUMS.txt                       校验和

同时：
    - 覆写 firmware/src/version.h，把版本号编译进固件（开机日志自报版本）
    - 追加 releases/README.md 版本索引
    - 可选打 git tag vX.Y.Z

用法：
    python tools/release.py                       全交互式
    python tools/release.py v1.2.3                指定版本号，交互录入变更
    python tools/release.py v1.2.3 --features "新增xxx; 修复yyy" --hardware "无" --tag
    python tools/release.py v1.2.3 --skip-build   复用 .pio 已有产物（调试用）

版本规则（语义化）：
    主版本 = 大功能架构调整或硬件方案变更；次版本 = 新功能；修订号 = bug 修复
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT / "firmware"

# 与 firmware/platformio.ini 的 [env:esp32-s3-n16r8] 保持一致
ENV = "esp32-s3-n16r8"
BUILD_DIR = FIRMWARE_DIR / ".pio" / "build" / ENV

# PlatformIO 安装位置（本机固定路径，与 docs/阶段0-实测报告.md 记录一致）
PENV = Path(r"C:\Users\PC207\.platformio\penv\Scripts")
PIO = PENV / "pio.exe"
PYEXE = PENV / "python.exe"
ESPTOOL = Path(r"C:\Users\PC207\.platformio\packages\tool-esptoolpy\esptool.py")

# 与 firmware/partitions.csv 对应：bootloader 0x0 / 分区表 0x8000 / app 0x10000 / storage 0x410000
# flash_size 16MB 来自 platformio.ini 的 board_upload.flash_size，勿改
OFFSETS = {"bootloader.bin": "0x0", "partitions.bin": "0x8000", "firmware.bin": "0x10000"}
LITTLEFS_OFFSET = "0x410000"
FLASH_SIZE = "16MB"

RELEASES = ROOT / "releases"
README = RELEASES / "README.md"
INDEX_MARK = "<!-- release.py 会在上方表格追加新版本，请勿删除本行标记 -->"
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

HARD_TARGET = "ESP32-S3-WROOM-1-N16R8 · 320×240 ST7789/ILI9341(SPI) · CH343 串口 921600"


def fail(msg: str) -> None:
    print(f"\n[release] ✗ {msg}")
    sys.exit(1)


def run(cmd: list[str], label: str, timeout: int = 1200) -> str:
    """跑外部命令，失败时打印输出尾部并退出。"""
    print(f"[release] {label} ...")
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        tail = (r.stdout or "")[-3000:] + (r.stderr or "")[-1500:]
        print(tail)
        fail(f"{label} 失败（exit {r.returncode}），输出见上")
    return r.stdout or ""


# ---------------------------------------------------------------- 版本校验

def check_version(version: str) -> None:
    if not SEMVER.match(version):
        fail(f"版本号 {version!r} 不符合语义化格式 vX.Y.Z")
    if (RELEASES / version).exists():
        fail(f"版本已存在：releases/{version}/（换个号，或先删掉旧目录）")
    r = subprocess.run(["git", "tag", "--list", version], cwd=ROOT,
                       capture_output=True, text=True)
    if version in (r.stdout or "").split():
        fail(f"git tag {version} 已存在")


# ---------------------------------------------------------------- 交互录入

def prompt_meta(args: argparse.Namespace) -> dict:
    """录入功能变更与硬件变更。CLI 给了参数就跳过交互。"""
    print("\n───── 版本信息录入 ─────")
    if args.features:
        features = [s.strip() for s in args.features.split(";") if s.strip()]
    else:
        print("本次改了什么？逐行输入（新增/修复/优化都可以写），空行结束：")
        features = []
        while True:
            try:
                line = input("  > ").strip()
            except EOFError:
                break
            if not line:
                break
            features.append(line)
        if not features:
            fail("至少写一条变更，否则没有发布记录的意义")

    if args.hardware is not None:
        hardware = args.hardware.strip()
    else:
        hardware = input("\n硬件有变更吗？（换屏/加传感器/改接线，没有直接回车）\n  > ").strip()

    if hardware.lower() in ("", "无", "no", "n", "none"):
        hardware = ""
    elif len(hardware) < 8:
        # 硬件变更是主版本级事件，备注太短说明没写清，逼着补
        detail = input("  ⚠ 请写清楚：外设型号、接了哪些引脚、供电有无变化\n  > ").strip()
        hardware = f"{hardware}（{detail}）" if detail else hardware

    meta = {"version": args.version, "date": date.today().isoformat(),
            "features": features, "hardware": hardware}
    print(f"\n  版本 {meta['version']}  日期 {meta['date']}")
    for f in features:
        print(f"    · {f}")
    print(f"    硬件变更：{hardware or '无'}\n")
    return meta


# ---------------------------------------------------------------- version.h

def write_version_header(meta: dict) -> Path:
    """版本号必须在构建前写好，才会被编进固件（开机日志自报版本）。"""
    dst = FIRMWARE_DIR / "src" / "version.h"
    dst.write_text(
        "#pragma once\n"
        "// 本文件由 tools/release.py 在发布时生成，请勿手改。\n"
        f'// 对应版本归档：releases/{meta["version"]}/\n'
        f'#define FW_VERSION      "{meta["version"]}"\n'
        f'#define FW_RELEASE_DATE "{meta["date"]}"\n',
        encoding="utf-8")
    print(f"[release] 已写入 {dst.relative_to(ROOT)}")
    return dst


# ---------------------------------------------------------------- 构建

def build_firmware() -> None:
    run([str(PIO), "run", "-d", str(FIRMWARE_DIR), "-e", ENV], "pio 编译固件")
    for name in OFFSETS:
        if not (BUILD_DIR / name).exists():
            fail(f"构建产物缺失：{BUILD_DIR / name}")


def build_fs() -> Path:
    run([str(PIO), "run", "-d", str(FIRMWARE_DIR), "-e", ENV, "-t", "buildfs"],
        "pio 打包 littlefs 动画包")
    out = BUILD_DIR / "littlefs.bin"
    if not out.exists():
        fail(f"动画包未生成：{out}")
    return out


def merge_bin(dst: Path) -> None:
    """bootloader+分区表+app 合成单 bin，flash_download_tool 从 0 一键烧写。

    不传 --fill-flash-size：产物只到 app 段结束（约 600KB），不把 16MB 填满。
    烧写工具烧写前会整片擦除，后面的空白区无需 0xFF 填充。
    不传 --flash_mode/--flash_freq 则保留 bootloader 头里的原值；
    --flash_size 16MB 必须与实盘一致（platformio.ini 的 board_upload.flash_size）。
    """
    args = [str(PYEXE), str(ESPTOOL), "--chip", "esp32s3", "merge_bin",
            "-o", str(dst), "--flash_size", FLASH_SIZE]
    for name, offset in OFFSETS.items():
        args += [offset, str(BUILD_DIR / name)]
    run(args, "esptool 合并烧写文件", timeout=300)
    if not dst.exists():
        fail("合并产物未生成")


# ---------------------------------------------------------------- 文档

def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_changelog(meta: dict, bins: dict[str, Path]) -> Path:
    d = RELEASES / meta["version"]
    lines = [
        f"# {meta['version']} — {meta['date']}",
        "",
        "| 项 | 内容 |",
        "|:---|:---|",
        f"| 版本 | {meta['version']} |",
        f"| 发布日期 | {meta['date']} |",
        f"| 适配硬件 | {HARD_TARGET} |",
        f"| 存储模式 | STORAGE_BACKEND=1（SD 卡优先，Flash 兜底） |",
        "",
        "## 功能变更",
        "",
    ]
    lines += [f"- {f}" for f in meta["features"]]
    lines += [
        "",
        "## ⚠ 硬件变更",
        "",
    ]
    if meta["hardware"]:
        lines += [f"**{meta['version']} 涉及硬件改动：**", "",
                  f"> {meta['hardware']}", "",
                  "升级到此版本前先核对实际接线是否一致。"]
    else:
        lines += ["无。与上一版接线完全兼容。"]
    lines += [
        "",
        "## 兼容性",
        "",
        f"- 动画包 `{bins['littlefs'].name}` 与本版固件**配套发布**，建议同版一起烧。",
        "- Flash 动画包只含预置段，完整 106 段动画请拷贝到 SD 卡（见烧写说明）。",
        "",
        "## 校验值（MD5）",
        "",
        "| 文件 | MD5 |",
        "|:---|:---|",
    ]
    for b in bins.values():
        lines.append(f"| `{b.name}` | `{md5_of(b)}` |")
    lines.append("")
    out = d / "CHANGELOG.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_flashing_guide(meta: dict) -> Path:
    d = RELEASES / meta["version"]
    v = meta["version"]
    text = f"""# {v} 烧写说明

## 你需要

- 开发板：ESP32-S3-WROOM-1-N16R8（16MB Flash）
- 串口：板载 CH343 USB 转串口，装好 CH343/CH340 驱动后会出现 COM 口
- 烧写文件（本目录）：
  - `dshpet-{v}-merged.bin` —— 固件（bootloader+分区表+应用已合并）
  - `dshpet-{v}-littlefs.bin` —— Flash 动画包（可选，见下）

## 方式一：flash_download_tool（图形界面，推荐新手）

1. 下载乐鑫官方 flash_download_tool
2. 芯片类型选 **ESP32-S3**，工作模式 Develop
3. 只加载一个文件：`dshpet-{v}-merged.bin`，地址填 **0x0**
4. SPI Speed 40MHz / SPI Mode DIO / DoNotChkBin 勾选均可
5. 选对 COM 口，波特率 **921600**，点 START

## 方式二：esptool 命令行

```bash
python esptool.py --chip esp32s3 --port COM口 --baud 921600 \\
    write_flash 0x0 dshpet-{v}-merged.bin
```

需要动画包（Flash 模式）再加：

```bash
python esptool.py --chip esp32s3 --port COM口 --baud 921600 \\
    write_flash {LITTLEFS_OFFSET} dshpet-{v}-littlefs.bin
```

## 动画放哪里

| 方案 | 做法 | 说明 |
|:---|:---|:---|
| SD 卡（推荐） | 把发布页的 SD 卡内容拷到 FAT32 卡根目录 | 完整 106 段，固件默认从 SD 读 |
| Flash | 烧 `dshpet-{v}-littlefs.bin` 到 {LITTLEFS_OFFSET} | 只有预置段，SD 卡挂载失败时自动回退到它 |

两种都烧也没问题：固件优先 SD，SD 不在时用 Flash 里的预置段。

## 验证

烧完打开串口监视器（115200），看到：

```
[pet] boot {v} ({meta['date']})
```

即版本正确。完整启动日志还应包含 SD 挂载与扫到的段数。

## 常见问题

- **串口没有输出**：本板是 CH343 外置桥（GPIO43/44），不是原生 USB-CDC；确认驱动已装、没有打开错 COM 口
- **烧写失败 / 超时**：按住 BOOT 键再上电进下载模式
- **SD 挂载失败**：卡要 FAT32、VCC 接 5V；固件会回退到 Flash 预置段
"""
    out = d / "烧写说明.md"
    out.write_text(text, encoding="utf-8")
    return out


def write_md5sums(meta: dict, bins: dict[str, Path]) -> Path:
    d = RELEASES / meta["version"]
    out = d / "MD5SUMS.txt"
    out.write_text("\n".join(f"{md5_of(b)}  {b.name}" for b in bins.values()) + "\n",
                   encoding="utf-8")
    return out


def update_index(meta: dict, hardware: str) -> None:
    text = README.read_text(encoding="utf-8")
    if INDEX_MARK not in text:
        fail(f"{README.name} 缺少索引标记，无法追加（请恢复模板中的注释行）")
    one_line = meta["features"][0] if len(meta["features"]) == 1 \
        else f"{len(meta['features'])} 项变更（详见 CHANGELOG）"
    row = f"| {meta['version']} | {meta['date']} | {one_line} | {hardware or '无'} |"
    text = text.replace(INDEX_MARK, f"{row}\n{INDEX_MARK}", 1)
    README.write_text(text, encoding="utf-8")
    print(f"[release] 索引已追加 {row}")


# ---------------------------------------------------------------- 主流程

def main() -> None:
    ap = argparse.ArgumentParser(description="固件正式版一键发布")
    ap.add_argument("version", nargs="?", help="语义化版本号，如 v1.2.3")
    ap.add_argument("--features", default=None,
                    help="功能变更，分号分隔（不填则交互录入）")
    ap.add_argument("--hardware", default=None,
                    help="硬件变更说明，无变更传 '无' 或留空")
    ap.add_argument("--tag", action="store_true", help="发布成功后打 git tag")
    ap.add_argument("--skip-build", action="store_true",
                    help="跳过 pio/esptool，直接用 .pio 现有产物（仅调试用）")
    args = ap.parse_args()

    if not PIO.exists() or not ESPTOOL.exists():
        fail(f"找不到工具链：{PIO} / {ESPTOOL}")

    # 版本号：CLI 或交互
    if not args.version:
        args.version = input("\n版本号（如 v1.2.3）：").strip()
    check_version(args.version)

    meta = prompt_meta(args)
    d = RELEASES / args.version

    # 构建阶段：先写 version.h 再编译，版本号才会进固件
    if args.skip_build:
        print("[release] --skip-build：直接用 .pio 现有产物")
        if not (BUILD_DIR / "firmware.bin").exists():
            fail("没有现成产物，去掉 --skip-build 重跑")
    else:
        write_version_header(meta)
        build_firmware()

    d.mkdir(parents=True)
    merged = d / f"dshpet-{args.version}-merged.bin"
    littlefs = d / f"dshpet-{args.version}-littlefs.bin"

    if args.skip_build and (BUILD_DIR / "littlefs.bin").exists():
        shutil.copy2(BUILD_DIR / "littlefs.bin", littlefs)
    else:
        fs_out = build_fs()
        shutil.copy2(fs_out, littlefs)
    if not args.skip_build:
        merge_bin(merged)
    else:
        # skip-build 时也允许直接用旧 merged（仅调试）
        if merged.exists():
            print("[release] merged.bin 已在目标目录，跳过合并")
        else:
            merge_bin(merged)

    bins = {"merged": merged, "littlefs": littlefs}
    write_changelog(meta, bins)
    write_flashing_guide(meta)
    write_md5sums(meta, bins)
    update_index(meta, meta["hardware"])

    print(f"\n[release] ✓ {args.version} 发布完成：{d.relative_to(ROOT)}")
    for f in sorted(d.iterdir()):
        print(f"    {f.name:36} {f.stat().st_size/1024:8.0f} KB")

    do_tag = args.tag
    if not do_tag and not args.features:
        do_tag = input("\n打 git tag 吗？(y/N)：").strip().lower() == "y"
    if do_tag:
        run(["git", "tag", "-a", args.version, "-m", f"{args.version} {meta['date']}"],
            "git tag")
        print(f"[release] ✓ tag {args.version} 已创建（记得 git push --tags）")


if __name__ == "__main__":
    main()
