# dshPetDafeiyu — ESP32 桌面宠物

把桌面宠物插件 `dsh-pet` 的 **106 段动画**（640×360 / 24fps / VP9-alpha）搬到 ESP32-S3 驱动的
320×240 SPI 小屏上，做成一个不依赖电脑的独立硬件桌宠。

一句话方案：webm → **320×180 / 12fps / MJPEG 帧包 `.petpack`** → ESP32-S3 + LovyanGFX + JPEGDEC → 屏。

---

## 四个顶层目录

| 目录 | 放什么 | 要不要入库 |
|:---|:---|:--:|
| `firmware/` | ESP32-S3 固件源码（PlatformIO 工程） | ✅ |
| `assets/` | 素材与产物：原始 webm、预览 mp4、动画池配置、SD 卡镜像 | 部分 |
| `docs/` | 技术方案、动画清单、实测报告、调研 | ✅ |
| `tools/` | ffmpeg 与 PC 端素材流水线脚本 | 部分 |

分工细节见 **[docs/目录结构说明.md](docs/目录结构说明.md)**。

---

## 换一台电脑怎么跑起来

项目里**不含**任何大二进制（77.5MB 帧包、51.8MB webm、200MB ffmpeg 都 gitignore 了），
所以 clone 下来后必须先跑一遍流水线把素材生成出来。

```powershell
# 0) 装 PlatformIO（VS Code 装 "PlatformIO IDE" 插件即可；CLI 用户 pip install platformio）

# 1) 下载完整版 ffmpeg → tools/ffmpeg.zip，解压出 ffmpeg/ 放到 tools/ 下
node tools/pipeline/download-ffmpeg.mjs

# 2) 生成素材：106 段 webm → .petpack，输出到 assets/sdcard/
python tools/pipeline/pipeline.py --limit 3     # 先冒烟，确认路径对
python tools/pipeline/pipeline.py               # 再全量（约 2.4 分钟）
python tools/pipeline/report.py                 # 抽检 + 生成 docs/阶段0-实测报告.md

# 3) 阶段 1：挑 5 段打进 Flash（约 3.5 MB）
python tools/pipeline/pick_flash.py

# 4) 编译并烧录
pio run                     # 编译固件
pio run -t uploadfs         # 把 firmware/data/ 烧成 LittleFS 动画分区
```

> ⚠️ PlatformIO 不在 PATH 时用绝对路径：
> `& $env:USERPROFILE\.platformio\penv\Scripts\pio.exe run`
>
> ⚠️ 别用 `C:\Users\...\.dsh\dsh-runtimes\...\python.exe` 跑 pio，那个解释器没装 platformio。

---

## 当前进度

| 阶段 | 内容 | 状态 |
|:---|:---|:--:|
| 阶段 0 | 素材流水线：106 段 → 12,764 帧 → **77.5 MB**，平均 **6.22 KB/帧** | ✅ 完成 |
| 阶段 1 | Flash 播放：5 段烧进 Flash，跑通「取帧 → 解码 → 刷屏 → 循环」 | 🔧 骨架已搭 |
| 阶段 2 | SD 卡：106 段全部上卡，多段调度 + 点击/拖拽交互 | ⬜ |
| 阶段 3 | 打磨：开关机动画、掉帧自适应、亮度、WiFi 推包 | ⬜ |

---

## 关键结论（实测，不是估算）

| 项 | 值 |
|:---|:---|
| 单帧大小 | 平均 **6.22 KB**，峰值 13 KB → 32 KB 缓冲留 2× 余量 |
| 解码缓冲 | 320×180×2B = **113 KB**/帧，PSRAM 放双缓冲 226 KB |
| 全量体积 | **77.5 MB** → 16MB Flash 放不下，**最终必须 SD 卡** |
| Flash 阶段 | 自定义分区表给 storage **11.9 MB** → 约 16 段完整动画 |
| 解码耗时 | JPEGDEC @57,600px：**解码 28.9ms + 刷屏 28.1ms**（串行 57ms） |
| 12fps 预算 | 83ms/帧 → 串行余量 31%；**双核并行后约 30ms，余量 64%** |

数据来源见 **[docs/调研-同类项目与解码库实测.md](docs/调研-同类项目与解码库实测.md)**。
