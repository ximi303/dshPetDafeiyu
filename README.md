# dshPetDafeiyu — ESP32 桌面宠物

一块 2.0 寸 SPI 屏循环播放角色动画，做成不依赖电脑的独立硬件摆件。

素材有两条线：

| 素材线 | 规模 | 状态 |
|:---|:---|:---|
| **西米**（原创单角色） | 106 段，约 1060 秒 | ✅ 已转 petpack 并上屏 |
| **11 个 AI 角色**（ChatGPT / Claude / DeepSeek / Gemini / GLM / Grok / Hunyuan / Kimi / MiniMax / Qwen / Seed） | 每角色 27 段（18 基础 + 6 互动 + 3 喂食），共 **297 段** | 🔧 素材层完成，待转 petpack |

核心链路：

```
webm(VP9-alpha)
   │ tools/pipeline/pipeline.py
   ▼
.petpack（JPEG 序列，320×240 / 12fps，与屏幕 1:1）
   │
   ├─ SD 卡 → /packs      （全量 106 段，当前默认）
   └─ Flash → LittleFS    （预置 8 段，SD 挂载失败时回退）
   ▼
core1 读帧 → JPEGDEC 解码 → PSRAM 双缓冲 → core0 DMA pushImage @40MHz → ST7789
```

---

## 一、直接烧来玩（不用装编译环境）

`releases/v1.0.0/` 里已有现成烧写文件：

| 文件 | 烧写地址 | 说明 |
|:---|:---|:---|
| `dshpet-v1.0.0-merged.bin` | **0x0** | 固件，bootloader + 分区表 + app 已合并，一键烧 |
| `dshpet-v1.0.0-littlefs.bin` | **0x410000** | Flash 动画包（预置 8 段），SD 卡方案的备用 |

步骤见 **[releases/v1.0.0/烧写说明.md](releases/v1.0.0/烧写说明.md)**，全部历史版本见 **[releases/README.md](releases/README.md)**。

---

## 二、五个顶层目录

| 目录 | 放什么 | 要不要入库 |
|:---|:---|:--:|
| `firmware/` | ESP32-S3 固件源码（PlatformIO 工程） | ✅ |
| `assets/` | 素材与产物：原始 webm、11 个角色素材、SD 卡镜像、预览页 | 部分 |
| `docs/` | 技术方案、动画清单、实测报告、接线教程 | ✅ |
| `releases/` | **正式版归档**：可烧写 bin + 变更记录 + 烧写说明 | ✅（含 bin） |
| `tools/` | ffmpeg、素材流水线、多角色构建、发布脚本 | 部分 |

分工细节见 **[docs/目录结构说明.md](docs/目录结构说明.md)**。

---

## 三、硬件（全部已实测）

| 部件 | 型号 / 规格 | 关键点 |
|:---|:---|:---|
| 主控 | ESP32-S3-WROOM-1 **N16R8** | 16MB Flash + 8MB Octal PSRAM，必须是 Octal 版本 |
| 屏幕 | 2.0 寸 **ST7789** SPI 240×320 | VCC 接 3V3，横屏 320×240；SCLK 12 / MOSI 11 / DC 10 / CS 9 / RST 8 / BL 13 |
| TF 卡模块 | Micro SD Adapter（V717 同类） | **独立 SPI**：SCK 14 / MOSI 15 / MISO 16 / CS 5，20MHz；**VCC 必须独立 5V 且共地** |
| TF 卡 | ≤32GB **FAT32** | exFAT 挂不上；16GB SDHC 实测通过 |
| 触摸 | TTP223 → GPIO 4 | 代码就绪，**尚未接线** |
| 串口 | 板载 CH343 | 115200 日志 / 921600 烧写 |

接线表与排障见 **[docs/阶段1-硬件接线教程.md](docs/阶段1-硬件接线教程.md)**。

---

## 四、换一台电脑怎么跑起来

项目里**不含**任何大二进制（素材 webm、petpack、ffmpeg 都 gitignore 了），
clone 下来后必须先跑流水线把素材生成出来。`releases/` 里的 bin 除外，那是入库的。

```powershell
# 0) 装 PlatformIO（VS Code 装 "PlatformIO IDE" 插件；CLI 用户 pip install platformio）

# 1) 下载完整版 ffmpeg
node tools/pipeline/download-ffmpeg.mjs      # 解压出 ffmpeg/ 放到 tools/ 下

# 2) 生成素材：106 段 webm → .petpack，输出到 assets/sdcard/
python tools/pipeline/pipeline.py --limit 3  # 先冒烟
python tools/pipeline/pipeline.py            # 再全量（约 3 分钟）
python tools/pipeline/report.py              # 抽检 + 生成 docs/阶段0-实测报告.md

# 3) 选 8 段打进 Flash（约 10.7MB）
python tools/pipeline/pick_flash.py

# 4) 编译并烧录
pio run                     # 编译固件
pio run -t uploadfs         # 把 firmware/data/ 烧成 LittleFS 动画分区

# 5) 106 段全部上卡：把 assets/sdcard/packs 整个拷到 FAT32 卡根目录
```

> ⚠️ PlatformIO 不在 PATH 时用绝对路径：`& $env:USERPROFILE\.platformio\penv\Scripts\pio.exe run`
>
> ⚠️ Windows 终端跑 Python 前设 `$env:PYTHONIOENCODING='utf-8'`，否则中文素材名乱码。

**多角色素材**（11 个 AI 角色，与西米那套完全独立）：

```powershell
python tools/build_character_preview.py claude          # 抽取动作 + 生成预览页
python tools/build_interactions.py claude --foods rice  # 互动素材 + 合成喂食动画
```

跑完打开 `assets/角色总览.html` 看全部 11 个角色。

---

## 五、当前进度

| 阶段 | 内容 | 状态 |
|:---|:---|:--:|
| 阶段 0 | 素材流水线：106 段 → 12,764 帧 → **77.5 MB**，平均 **6.22 KB/帧**（320×180 时期） | ✅ 完成 |
| 阶段 1 | 显示链路：双核 + 双缓冲 + DMA，320×240 素材 1:1，Flash 播放 8 段 | ✅ 完成 |
| 阶段 2 | SD 卡后端：106 段全部识别、连续播放丢帧 **0.8%** | ✅ 已验证（2026-11） |
| 阶段 2b | 点击 / 拖拽 / 事件触发分池抽签 | 🔧 事件已接入，抽签逻辑未做 |
| 阶段 3 | 打磨：开关机动画、掉帧自适应、调光、WiFi 推包 | ⬜ |
| 版本管理 | `releases/` + `tools/release.py`，已发布 v1.0.0 | ✅ |
| 多角色素材 | 11 角色 × 27 段 = 297 段，预览页与总览页 | 🔧 素材完成，未转 petpack |

---

## 六、关键结论（实测，不是估算）

| 项 | 值 |
|:---|:---|
| 单帧大小（320×240） | 平均约 **11 KB**，峰值 28 KB → 32 KB 缓冲留余量 |
| 解码缓冲 | 320×240×2B = **150 KB**/帧，PSRAM 双缓冲 **300 KB** |
| 全量体积 | **77.5 MB**（106 段，320×180）/ 升级 320×240 后约 **138 MB** → 16MB Flash 放不下，**必须 SD 卡** |
| Flash 分区 | 自定义 16MB：app0 4MB + storage **11.93MB**（去掉 OTA slot）→ 预置 8 段 10.69MB |
| 解码耗时 | JPEGDEC：**解码 28.9ms + 刷屏 28.1ms**（串行 57ms） |
| 12fps 预算 | 83ms/帧 → 双核并行后约 30ms，实测 **13fps**，余量 64% |
| SD 卡播放 | 20MHz SPI，顺序读约 2MB/s，106 段连续播放丢帧 **0.8%** |

数据来源见 **[docs/调研-同类项目与解码库实测.md](docs/调研-同类项目与解码库实测.md)**。

---

## 七、版本发布

```powershell
python tools/release.py v1.1.0 --tag
```

脚本会：写 `firmware/src/version.h`（版本号编进固件，开机日志自报）→ 编译 → esptool 合并 →
生成 CHANGELOG（含 ⚠ 硬件变更特别备注）+ 烧写说明 + MD5 → 追加 `releases/README.md` 索引 → 打 tag。

---

## 八、文档

| 文档 | 看它做什么 |
|:---|:---|
| **[docs/项目记忆.md](docs/项目记忆.md)** | **AI 上下文恢复**：结论、决策理由、踩过的坑 |
| [docs/目录结构说明.md](docs/目录结构说明.md) | 目录职责划分、数据流向、gitignore 策略 |
| [docs/阶段1-硬件接线教程.md](docs/阶段1-硬件接线教程.md) | 接线表、SD 卡供电坑、排障速查 |
| [docs/ESP32桌宠技术方案.md](docs/ESP32桌宠技术方案.md) | 整体方案与选型论证 |
| [docs/动画清单.md](docs/动画清单.md) | 106 段素材清单与分类权重 |
| [releases/README.md](releases/README.md) | 正式版索引 |
