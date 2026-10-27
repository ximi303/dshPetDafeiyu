# tools/pipeline — PC 端素材流水线（阶段 0 · 已跑通）

把 `assets/source-webm/` 里的 106 段 VP9-alpha 动画，转成 ESP32 能播的 **MJPEG 帧包 `.petpack`**，
输出到 `assets/sdcard/`；再从中精选 5 段打到 `firmware/data/` 供阶段 1 烧进 Flash。

所有路径**相对本脚本定位**，整个项目目录拷到别的机器不用改任何代码。

## 执行结果（2026-10-27）

| 项目 | 结果 |
|:---|:---|
| 处理段数 | **106 / 106**（无失败） |
| 总帧数 | **12,764 帧**（17.7 分钟 @12fps） |
| 总体积 | **77.5 MB**（原始 webm 51.8 MB，膨胀 1.50×） |
| 平均帧大小 | **6.22 KB**（最重一段 8.52 KB/帧，单帧最大 13 KB） |
| 抽检 | 12 个包 × 3 帧（首/中/尾）真解码校验，**36/36 通过** |
| 耗时 | 2.4 分钟（转码 + 打包 + 每包回读校验） |

详见 **[docs/阶段0-实测报告.md](../../docs/阶段0-实测报告.md)**。

## 目录

```
tools/pipeline/
├─ download-ffmpeg.mjs   下载完整版 ffmpeg → tools/ffmpeg.zip（解压后放 tools/ffmpeg/）
├─ pipeline.py           转帧 → 打包 → 回读校验 → 统计
├─ report.py             抽样真解码 + 生成 docs/阶段0-实测报告.md
├─ pick_flash.py         ★ 从 assets/sdcard/packs 挑 5 段 → firmware/data/packs
├─ build/                中间产物（跑时占用，跑完即清）
└─ README.md             本文件
```

## 跑法

```powershell
# 一次性：下载完整版 ffmpeg 到 tools/ffmpeg.zip（解压出 ffmpeg/ 放到 tools/ 下）
node tools/pipeline/download-ffmpeg.mjs

cd tools/pipeline
python pipeline.py --calibrate    # 1) 3 种分辨率各测 5 段，先定档位
python pipeline.py --limit 3      # 2) 冒烟测试
python pipeline.py                # 3) 全量 106 段 → assets/sdcard/
python report.py                  # 4) 抽检 + 生成 docs/阶段0-实测报告.md
python pick_flash.py              # 5) 挑 5 段 → firmware/data/packs（阶段 1 用）
```

可选参数：

| 参数 | 作用 |
|:---|:---|
| `--calibrate` | 只跑 5 段样本 × 3 种分辨率，测体积 |
| `--limit N` | 只处理前 N 段（冒烟） |
| `--max-seconds 4` | 每段最多截多少秒（省空间） |
| `--keep-frames` | 保留中间 JPEG 帧（调试用） |

## 产物去哪

| 产物 | 路径 | 用途 |
|:---|:---|:---|
| 全量帧包 | `assets/sdcard/packs/<分类>/<名字>.petpack` | 阶段 2 整目录拷进 SD 卡 |
| 全量索引 | `assets/sdcard/index.json` | 固件建索引用 |
| 校准表 | `docs/calibration.json` | 分辨率档位决策依据 |
| 实测报告 | `docs/阶段0-实测报告.md` | 报告 |
| Flash 预置包 | `firmware/data/packs/` | 阶段 1 `pio run -t uploadfs` 烧进 Flash |

## `.petpack` 容器格式（v1）

小端序，固件侧按偏移表取帧，不用在 SD 里边读边找 JPEG 结束标记。

| 偏移 | 长度 | 字段 | 说明 |
|--:|--:|:---|:---|
| 0 | 4 | magic | 固定 `PETP` |
| 4 | 2 | version | 当前 1 |
| 6 | 2 | width | 320 |
| 8 | 2 | height | 180 |
| 10 | 2 | fps | 12 |
| 12 | 2 | frameCount | 帧数 |
| 14 | 4 | flags | bit0=1 循环播放 |
| 18 | 4 | reserved | 0 |
| 22 | 4×N | frameOffset[] | 每帧 JPEG 的绝对文件偏移 |
| 22+4N | … | data | 逐帧相接的 JPEG（每帧 `FFD8…FFD9`） |

读取一帧的伪代码：

```c
f_lseek(fp, 22 + 4 * i); f_read(fp, &off, 4, &n);          // 取偏移
f_lseek(fp, off);
uint32_t len = (i + 1 < frameCount) ? offs[i + 1] - off : fileSize - off;
f_read(fp, jpeg_buf, len, &n);                             // 顺序读整帧
JPEGDEC.draw(jpeg_buf, len, 0, 0);                         // 解到 RGB565 缓冲
```

## 编码参数（当前决策）

| 参数 | 值 | 备注 |
|:---|:---|:---|
| 分辨率 | 320×180 | 16:9，对应 320×240 屏 |
| 帧率 | 12 fps | 原 24fps 砍半 |
| JPEG 质量 | `-q:v 3`（≈q75–80） | 实测卡通画面体积很小，其实 q2 还能再提一档 |
| 背景 | `#101A2E` 预合成 | 透明区压到深蓝底，固件不做 alpha |
| 时长 | 整段保留 | 想省空间加 `--max-seconds 4` |

改参数：`pipeline.py` 顶部常量（`WIDTH/HEIGHT/FPS/QSCALE/BG`）。

## 踩过的坑（复用这套流水线时一定会再遇到）

1. **必须用 `-c:v libvpx-vp9` 显式指定解码器**。ffmpeg 原生的 `vp9` 解码器
   **不读 webm 的 alpha 侧数据**（`ALPHA_MODE=1` 存在 BlockAdditional 里），
   解出来是白底不透明；只有 libvpx-vp9 才能拿到 alpha。
2. **先 `scale` 前景，再 `overlay` 到背景**。写反了不报错，但会变成
   「把 640×360 裁进 320×180」——只剩画面左上角一块。
3. **ffmpeg 9 移除了 `-vsync`**，改用 `-fps_mode passthrough`，否则直接报 Unrecognized option。
4. **沙箱/受限环境下 subprocess 的管道 stdio 会 EPERM**。所以 `run_ffmpeg()` 是把
   ffmpeg 的 stderr 写进日志文件再读回，**不要改成 `subprocess.PIPE` 捕获**。

另外：系统里某些 IDE 自带的 ffmpeg 是 `--disable-everything` 的精简版
（只有 x264 编码 + mp4 封装，没有 mjpeg/image2），必须换成完整版。

5. **中文 Windows 上跑脚本报 `UnicodeDecodeError: 'gbk' codec`**：控制台默认 GBK，
   而 ffmpeg 的 stderr 里有非 GBK 字节。加个环境变量就干净了，**不影响产物**：
   ```powershell
   $env:PYTHONUTF8 = "1"
   ```
   PlatformIO 打印进度时也会撞同样的坑（`\xbc` 之类），同样设 `PYTHONUTF8=1` 即可，
   报错出现在打印环节、不影响编译结果（看最后的 `[SUCCESS]` 判断成败）。
