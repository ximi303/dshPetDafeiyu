#!/usr/bin/env python3
"""阶段 0 素材流水线：webm → JPEG 帧 → .petpack

用法（在 tools/pipeline 目录下；路径全部相对本脚本定位，从任意 cwd 跑都可以）：
    python pipeline.py --calibrate          # 只跑 5 段样本 × 3 种分辨率，测体积
    python pipeline.py --limit 3            # 只跑前 3 段（冒烟测试）
    python pipeline.py                      # 全量 106 段 → assets/sdcard/packs/

产物：
    assets/sdcard/packs/<分类>/<动画名>.petpack   带偏移表的 MJPEG 容器（阶段 2 整目录拷进 SD 卡）
    assets/sdcard/index.json                      全部素材的索引与统计
    docs/calibration.json                         分辨率实测校准表（--calibrate）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

# 路径全部相对本脚本定位：tools/pipeline/ 往上两级即项目根，整目录拷到别的机器也能直接跑
HERE = Path(__file__).resolve().parent                 # tools/pipeline/
PROJ = HERE.parent.parent                             # 项目根 dshPetDafeiyu/

SRC    = PROJ / "assets" / "source-webm"              # 输入：106 段 VP9-alpha 原始素材
FFMPEG = PROJ / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
BUILD  = HERE / "build"                               # 中间 JPEG 帧（跑完即清）
SD     = PROJ / "assets" / "sdcard"                   # 输出：SD 卡镜像根（目录结构 = 卡根）
PACKS  = SD / "packs"
DOCS   = PROJ / "docs"

# ---- 编码参数（阶段 0 的默认决策，实测后再调）----
WIDTH, HEIGHT = 320, 180
FPS = 12
QSCALE = 3                     # ffmpeg -q:v 3 ≈ JPEG q75~80
BG = "0x101A2E"                # 预合成背景色（深蓝，与预览页一致）
LOOP_FLAG = 1

MAGIC = b"PETP"
VERSION = 1


def ffmpeg_bin() -> Path:
    if FFMPEG.exists():
        return FFMPEG
    alt = shutil.which("ffmpeg")
    if alt:
        return Path(alt)
    sys.exit(f"找不到 ffmpeg：{FFMPEG}（先跑 node scripts/download-ffmpeg.mjs）")


def run_ffmpeg(args: list[str]) -> tuple[bool, str]:
    """调用 ffmpeg。不捕获管道（沙箱下 piped stdio 会 EPERM），错因写到文件里读回。"""
    log = BUILD / "ffmpeg.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "wb") as fh:
        proc = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=fh, creationflags=0)
    if proc.returncode != 0:
        try:
            tail = log.read_text(encoding="utf-8", errors="replace")[-1200:]
        except OSError:
            tail = "(无日志)"
        return False, tail
    return True, ""


def extract_frames(src: Path, frames_dir: Path, w: int, h: int, fps: int,
                   q: int, bg: str, max_seconds: float | None) -> tuple[bool, str, float]:
    """把一段 webm 转成 JPEG 帧序列，透明区压到背景色上。"""
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(ffmpeg_bin()), "-hide_banner", "-loglevel", "error", "-y",
        # 0: 固定背景色源；1: 原始动画（必须用 libvpx-vp9 解，原生 vp9 解码器会丢掉 alpha 侧数据）
        "-f", "lavfi", "-i", f"color=c={bg}:s={w}x{h}:r={fps}",
        "-c:v", "libvpx-vp9", "-i", str(src),
        "-filter_complex",
        # 先缩放前景再叠到背景上（顺序反了会变成"裁剪"，只剩画面左上角一块）
        f"[1:v]scale={w}:{h}:flags=lanczos[fg];[0:v][fg]overlay=shortest=1:format=auto,format=yuvj420p",
        "-an", "-fps_mode", "passthrough", "-q:v", str(q),
    ]
    if max_seconds:
        args += ["-t", str(max_seconds)]
    args += ["-start_number", "1", "-c:v", "mjpeg", str(frames_dir / "%05d.jpg")]
    t0 = time.time()
    ok, err = run_ffmpeg(args)
    return ok, err, time.time() - t0


def build_pack(frames_dir: Path, dst: Path, w: int, h: int, fps: int) -> dict:
    """把 JPEG 帧打成 .petpack：固定头 + 偏移表 + 连续 JPEG 数据。"""
    files = sorted(frames_dir.glob("*.jpg"))
    if not files:
        raise RuntimeError(f"没有产出帧：{frames_dir}")
    blobs = [f.read_bytes() for f in files]
    n = len(blobs)
    header_len = 22 + 4 * n
    offsets, cur = [], header_len
    for b in blobs:
        offsets.append(cur)
        cur += len(b)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<HHHHHII", VERSION, w, h, fps, n, LOOP_FLAG, 0))
        fh.write(struct.pack(f"<{n}I", *offsets))
        for b in blobs:
            fh.write(b)
    sizes = [len(b) for b in blobs]
    return {
        "frames": n,
        "duration_sec": round(n / fps, 2),
        "bytes": dst.stat().st_size,
        "data_bytes": sum(sizes),
        "avg_frame": round(sum(sizes) / n, 1),
        "min_frame": min(sizes),
        "max_frame": max(sizes),
    }


def verify_pack(pack: Path, w: int, h: int, fps: int) -> dict:
    """回读容器头，确认偏移表与 JPEG 边界自洽（这是固件侧唯一的读取契约）。"""
    raw = pack.read_bytes()
    assert raw[:4] == MAGIC, "magic 不对"
    ver, pw, ph, pfps, n, flags, _ = struct.unpack("<HHHHHII", raw[4:22])
    offsets = struct.unpack(f"<{n}I", raw[22:22 + 4 * n])
    assert ver == VERSION and pw == w and ph == h and pfps == fps, "头部字段不对"
    for i, off in enumerate(offsets):
        assert raw[off:off + 2] == b"\xff\xd8", f"第 {i} 帧不是 JPEG 开头"
        end = offsets[i + 1] if i + 1 < n else len(raw)
        assert raw[end - 2:end] == b"\xff\xd9", f"第 {i} 帧不是 JPEG 结尾"
    return {"verified": True, "frames": n, "flags": flags}


def iter_sources() -> list[tuple[str, str, Path]]:
    out = []
    for group_dir in sorted(SRC.iterdir()):
        if not group_dir.is_dir():
            continue
        for f in sorted(group_dir.glob("*.webm")):
            out.append((group_dir.name, f.stem, f))
    return out


# 校准样本：覆盖"小动作/玩耍/吃什么/待机/工作状态"五类，各取一段
CALIB_SAMPLES = ["待机呼吸休闲", "原地专心玩魔方", "吃西瓜", "写代码", "工作状态-思考冒泡"]
CALIB_SIZES = [(320, 180), (240, 135), (160, 90)]


def cmd_calibrate() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    srcs = {name: p for _, name, p in iter_sources()}
    rows = []
    for name in CALIB_SAMPLES:
        src = srcs.get(name)
        if not src:
            print(f"跳过（找不到素材）：{name}")
            continue
        for (w, h) in CALIB_SIZES:
            fdir = BUILD / "calib" / f"{name}_{w}x{h}"
            ok, err, secs = extract_frames(src, fdir, w, h, FPS, QSCALE, BG, 3.0)
            if not ok:
                print(f"[FAIL] {name} {w}x{h}\n{err}")
                continue
            files = sorted(fdir.glob("*.jpg"))
            sizes = [f.stat().st_size for f in files]
            row = {
                "clip": name,
                "w": w, "h": h,
                "frames": len(files),
                "avg_frame": round(sum(sizes) / len(sizes), 1),
                "kbps": round(sum(sizes) / 3.0 / 1024, 1),
                "3s_mb": round(sum(sizes) / 1048576, 2),
                "secs_taken": round(secs, 1),
            }
            rows.append(row)
            print(f"{name:<12} {w}x{h}: 平均 {row['avg_frame']/1024:.1f} KB/帧 · "
                  f"{row['kbps']} KB/s · 3 秒 {row['3s_mb']} MB · 转码 {secs:.1f}s")
            shutil.rmtree(fdir, ignore_errors=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "calibration.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n校准结果写入 {DOCS / 'calibration.json'}")


def cmd_full(limit: int | None, max_seconds: float | None, keep_frames: bool) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    PACKS.mkdir(parents=True, exist_ok=True)
    srcs = iter_sources()
    if limit:
        srcs = srcs[:limit]
    total = len(srcs)
    print(f"开始处理 {total} 段（{WIDTH}x{HEIGHT} / {FPS}fps / q{QSCALE}）")
    index, t_all, fails = [], time.time(), []
    for i, (group, name, src) in enumerate(srcs, 1):
        fdir = BUILD / "frames" / f"{group}_{name}"
        ok, err, secs = extract_frames(src, fdir, WIDTH, HEIGHT, FPS, QSCALE, BG, max_seconds)
        if not ok:
            fails.append({"clip": name, "error": err[-400:]})
            print(f"[{i}/{total}] FAIL {name}")
            shutil.rmtree(fdir, ignore_errors=True)
            continue
        dst = PACKS / group / f"{name}.petpack"
        info = build_pack(fdir, dst, WIDTH, HEIGHT, FPS)
        check = verify_pack(dst, WIDTH, HEIGHT, FPS)
        index.append({"group": group, "name": name, "pack": str(dst.relative_to(SD)),
                      **info, **check, "encode_sec": round(secs, 1)})
        if not keep_frames:
            shutil.rmtree(fdir, ignore_errors=True)
        if i % 5 == 0 or i == total:
            done_mb = sum(r["bytes"] for r in index) / 1048576
            print(f"[{i}/{total}] {name}: {info['frames']} 帧 · "
                  f"平均 {info['avg_frame']/1024:.1f}KB · 累计 {done_mb:.1f}MB · "
                  f"已用 {time.time()-t_all:.0f}s")

    if limit:
        # 冒烟测试：--limit 只处理前 N 段，此时绝不能覆盖全量 index.json，
        # 否则 106 段的索引会被 3 段的覆盖掉。索引另存一份到 docs/ 供核对。
        DOCS.mkdir(parents=True, exist_ok=True)
        (DOCS / "smoke_index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n[冒烟模式] 未覆盖 assets/sdcard/index.json，本次 {len(index)} 段的"
              f"统计写在 docs/smoke_index.json")
    else:
        SD.mkdir(parents=True, exist_ok=True)
        (SD / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    total_bytes = sum(r["bytes"] for r in index)
    total_frames = sum(r["frames"] for r in index)
    print(f"\n完成：{len(index)} 段 / {total_frames} 帧 / {total_bytes/1048576:.1f} MB / "
          f"耗时 {(time.time()-t_all)/60:.1f} 分钟")
    if fails:
        print(f"失败 {len(fails)} 段，见 docs/fails.json")
        (DOCS / "fails.json").write_text(json.dumps(fails, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true", help="只做 3 种分辨率的体积校准")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 段（冒烟测试）")
    ap.add_argument("--max-seconds", type=float, default=None, help="每段最多截取多少秒")
    ap.add_argument("--keep-frames", action="store_true", help="保留中间 JPEG 帧")
    args = ap.parse_args()
    if not SRC.exists():
        sys.exit(f"素材目录不存在：{SRC}")
    if args.calibrate:
        cmd_calibrate()
    else:
        cmd_full(args.limit, args.max_seconds, args.keep_frames)


if __name__ == "__main__":
    main()
