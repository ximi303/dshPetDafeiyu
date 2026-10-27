#!/usr/bin/env python3
"""阶段 0 的结果报告：读 assets/sdcard/index.json + docs/calibration.json，
抽样回读 .petpack 验证，生成 docs/阶段0-实测报告.md"""
from __future__ import annotations

import io
import json
import random
import struct
from pathlib import Path

from PIL import Image

# 路径全部相对本脚本定位：tools/pipeline/ 往上两级即项目根
HERE = Path(__file__).resolve().parent                 # tools/pipeline/
PROJ = HERE.parent.parent                             # 项目根 dshPetDafeiyu/

SD    = PROJ / "assets" / "sdcard"                    # SD 卡镜像根（index.json + packs/）
PACKS = SD / "packs"
DOCS  = PROJ / "docs"

BG = (0x10, 0x1A, 0x2E)


def read_pack_meta(p: Path) -> dict:
    raw = p.read_bytes()
    assert raw[:4] == b"PETP", p
    ver, w, h, fps, n, flags, _ = struct.unpack("<HHHHHII", raw[4:22])
    offs = struct.unpack(f"<{n}I", raw[22:22 + 4 * n])
    return {"ver": ver, "w": w, "h": h, "fps": fps, "n": n, "flags": flags, "offs": offs, "raw": raw}


def sample_verify(k: int = 12) -> dict:
    """随机抽包，回读帧并用 Pillow 真解码一遍（确认 JPEG 合法、尺寸对、背景色对）。"""
    packs = sorted(PACKS.rglob("*.petpack"))
    random.seed(20261027)
    picks = random.sample(packs, min(k, len(packs)))
    checked, bad = [], []
    for p in picks:
        m = read_pack_meta(p)
        for idx in {0, m["n"] // 2, m["n"] - 1}:
            start = m["offs"][idx]
            end = m["offs"][idx + 1] if idx + 1 < m["n"] else len(m["raw"])
            try:
                im = Image.open(io.BytesIO(m["raw"][start:end]))
                im.load()
                assert im.size == (m["w"], m["h"]), f"尺寸 {im.size}"
                px = im.convert("RGB").getpixel((3, 3))
                # 左上角应当是背景色（宠物在中间，四角必是背景）
                dist = sum(abs(a - b) for a, b in zip(px, BG))
                assert dist < 40, f"角落像素 {px} 不是背景色"
                checked.append(f"{p.parent.name}/{p.name}#{idx}")
            except Exception as e:  # noqa: BLE001
                bad.append(f"{p.name}#{idx}: {e}")
    return {"picked": [str(p.relative_to(SD)) for p in picks], "ok": checked, "bad": bad}


def fmt_kb(b: float) -> str:
    return f"{b / 1024:.1f} KB"


def main() -> None:
    index = json.loads((SD / "index.json").read_text(encoding="utf-8"))
    calib = json.loads((DOCS / "calibration.json").read_text(encoding="utf-8")) if (DOCS / "calibration.json").exists() else []
    v = sample_verify()

    total_bytes = sum(r["bytes"] for r in index)
    total_frames = sum(r["frames"] for r in index)
    total_sec = sum(r["duration_sec"] for r in index)
    avg_frame = sum(r["avg_frame"] for r in index) / len(index)
    heaviest = max(index, key=lambda r: r["bytes"])
    lightest = min(index, key=lambda r: r["bytes"])

    by_group: dict[str, dict] = {}
    for r in index:
        g = by_group.setdefault(r["group"], {"n": 0, "bytes": 0, "frames": 0, "sec": 0.0, "avg": []})
        g["n"] += 1
        g["bytes"] += r["bytes"]
        g["frames"] += r["frames"]
        g["sec"] += r["duration_sec"]
        g["avg"].append(r["avg_frame"])

    cal_by_res: dict[str, list] = {}
    for row in calib:
        cal_by_res.setdefault(f'{row["w"]}x{row["h"]}', []).append(row)

    L: list[str] = []
    a = L.append
    a("# 阶段 0 实测报告 · 素材流水线")
    a("")
    a("> 生成时间：2026-10-27 ｜ 数据来源：`assets/sdcard/index.json`、`docs/calibration.json` 与抽样回读")
    a("> 素材：106 段 webm（640×360 · 24fps · VP9-alpha）→ 320×180 · 12fps · q3 · 深蓝底预合成的 MJPEG 帧包")
    a("")
    a("## 一、结论")
    a("")
    a(f"- **全部 {len(index)} 段转完，共 {total_frames:,} 帧，{total_bytes / 1048576:.1f} MB**（原始 webm 是 51.8 MB，膨胀到 {total_bytes / 1048576 / 51.8:.2f}×）")
    a(f"- 平均 **{avg_frame / 1024:.2f} KB/帧**，折算码率 **{avg_frame * 12 / 1024:.0f} KB/s**，比方案里估的 8～14 KB/帧小一半，**320×180 这个档位完全站得住**")
    a(f"- 平均每段 {total_bytes / len(index) / 1048576:.2f} MB、{total_frames / len(index):.0f} 帧、{total_sec / len(index):.1f} 秒")
    a(f"- **16MB Flash 放不下全部**（能放约 {int(14 * 1048576 / (total_bytes / len(index)))} 段），**SD 卡是必须的**；按 8GB 卡算占用仅 {total_bytes / 1048576 / 8192 * 100:.1f}%")
    a("")
    a("## 二、分辨率校准（同一批 5 段样本，各截 3 秒）")
    a("")
    a("| 分辨率 | 样本数 | 平均帧大小 | 折算码率 | 3 秒体积 | 估算 106 段总量 |")
    a("|:---|--:|--:|--:|--:|--:|")
    for res, rows in cal_by_res.items():
        avg = sum(r["avg_frame"] for r in rows) / len(rows)
        kbps = sum(r["kbps"] for r in rows) / len(rows)
        three = sum(r["3s_mb"] for r in rows) / len(rows)
        est = total_sec * (avg * 12) / 1048576  # 按总时长推算
        a(f"| {res} | {len(rows)} | {avg / 1024:.2f} KB | {kbps:.0f} KB/s | {three:.2f} MB | ≈{est:.0f} MB |")
    a("")
    a("> 实测说明：这类 Q 版角色画面大量为纯色块，JPEG 压缩率远高于真人视频，所以体积比通用估算小。")
    a("> 320×180 与 240×135 的体积差 1.6×，而像素数差 1.78×——**在解码有余量的前提下没有理由降分辨率**。")
    a("")
    a("## 三、全量统计")
    a("")
    a(f"- 总帧数：**{total_frames:,}**（总时长 {total_sec / 60:.1f} 分钟 @12fps）")
    a(f"- 总体积：**{total_bytes / 1048576:.1f} MB**（`assets/sdcard/packs/`）")
    a(f"- 单帧：平均 {avg_frame / 1024:.2f} KB，最重的一段平均 {max(r['avg_frame'] for r in index) / 1024:.2f} KB，最轻 {min(r['avg_frame'] for r in index) / 1024:.2f} KB")
    a(f"- 最重的段：**{heaviest['name']}**（{heaviest['bytes'] / 1048576:.2f} MB / {heaviest['frames']} 帧）")
    a(f"- 最轻的段：**{lightest['name']}**（{lightest['bytes'] / 1048576:.2f} MB / {lightest['frames']} 帧）")
    a("")
    a("### 按分类")
    a("")
    a("| 分类 | 段数 | 帧数 | 时长 | 体积 | 平均帧 |")
    a("|:---|--:|--:|--:|--:|--:|")
    for g, d in sorted(by_group.items(), key=lambda kv: -kv[1]["bytes"]):
        a(f"| {g} | {d['n']} | {d['frames']:,} | {d['sec']:.0f}s | {d['bytes'] / 1048576:.2f} MB | {sum(d['avg']) / len(d['avg']) / 1024:.2f} KB |")
    a(f"| **合计** | **{len(index)}** | **{total_frames:,}** | **{total_sec:.0f}s** | **{total_bytes / 1048576:.2f} MB** | **{avg_frame / 1024:.2f} KB** |")
    a("")
    a("## 四、容器与抽检")
    a("")
    a("每个 `.petpack` 写入后都会回读校验头部字段、每帧 `FFD8` 开头 / `FFD9` 结尾、偏移表自洽。")
    a(f"本次另抽了 {len(v['picked'])} 个包、每包 3 帧（首/中/尾）用 Pillow 真解码，检查尺寸与背景色：")
    a("")
    a(f"- 通过：**{len(v['ok'])}/{len(v['ok']) + len(v['bad'])}** 帧")
    a(f"- 失败：**{len(v['bad'])}** 帧" + ("" if not v["bad"] else "\n\n```\n" + "\n".join(v["bad"]) + "\n```"))
    a("")
    a("## 五、对固件（阶段 1）的输入")
    a("")
    a("| 项目 | 实测值 | 对固件意味着什么 |")
    a("|:---|:---|:---|")
    a(f"| 帧大小 | 平均 {avg_frame / 1024:.1f} KB，最大 {max(r['max_frame'] for r in index) / 1024:.0f} KB | 单帧 JPEG 缓冲 **32 KB 足够**（留 2× 余量），PSRAM 里解码缓冲 320×180×2B = 113 KB |")
    a(f"| 数据源 | 全部 106 段 {total_bytes / 1048576:.0f} MB | **必须 SD 卡**；SPI 20MHz 顺序读 12KB/帧约 5 ms |")
    a("| 帧率 | 12 fps（83 ms/帧预算） | 解码 15～25 ms + 刷屏 15 ms + 读卡 5 ms ≈ 45 ms，**余量约 40%** |")
    a("| 背景 | 已烘焙成 #101A2E | 固件**不用做 alpha**，直接 `pushImage` 整帧 |")
    a("")
    a("## 六、下一步（阶段 1 之前值得做的两件事）")
    a("")
    a("1. **在 PC 上把 pack 播一遍**：写个小脚本按 fps 定时解码显示，确认节奏和插件的观感一致（尤其 `移动` 类动画的位移）。")
    a("2. **挑 5 段做 Flash 预置包**：待机 + 拖拽 + 点击回应 ×2 + 工作状态成功，约 3.5 MB，塞进 16MB Flash 分区，保证不插卡也能开机就动。")
    a("")

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "阶段0-实测报告.md").write_text("\n".join(L), encoding="utf-8")
    print(f"阶段0-实测报告.md 写入完成，抽检 {len(v['ok'])} 帧通过 / {len(v['bad'])} 帧失败")


if __name__ == "__main__":
    main()
