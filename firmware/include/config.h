#pragma once

// ============================================================
// 桌宠固件全局常量 —— 所有可调参数集中在这里
// 改引脚 / 分辨率 / 帧率 / 存储后端，只动本文件
// ============================================================

#include <cstdint>

namespace pet {

// ------------------------------------------------------------
// 存储后端（阶段 1 Flash / 阶段 2 SD）
// 由 platformio.ini 的 -DSTORAGE_BACKEND=0|1 传入
// ------------------------------------------------------------
#ifndef STORAGE_BACKEND
#define STORAGE_BACKEND 0
#endif

enum class Backend : uint8_t { Flash = 0, SD = 1 };
static constexpr Backend kBackend = static_cast<Backend>(STORAGE_BACKEND);

// ------------------------------------------------------------
// 屏幕
// ------------------------------------------------------------
static constexpr uint16_t kScreenW = 320;
static constexpr uint16_t kScreenH = 240;

// ---- 内容区：.petpack 的实际尺寸（16:9，上下各留 30px）----
static constexpr uint16_t kFrameW = 320;
static constexpr uint16_t kFrameH = 180;
static constexpr uint16_t kFrameX = 0;
static constexpr uint16_t kFrameY = 30;  // (240 - 180) / 2

// ------------------------------------------------------------
// 播放
// ------------------------------------------------------------
static constexpr uint16_t kFps = 12;
static constexpr uint32_t kFrameBudgetUs = 1000000UL / kFps;  // 83333 us

// ------------------------------------------------------------
// 缓冲
// ------------------------------------------------------------
// 实测：平均 6.22 KB/帧、峰值 13 KB → 32 KB 留 2 倍余量
static constexpr uint32_t kJpegBufBytes = 32 * 1024;
// 一帧 RGB565：320 * 180 * 2 = 115200 B ≈ 113 KB
static constexpr uint32_t kFrameBytes = static_cast<uint32_t>(kFrameW) * kFrameH * 2;
// 双缓冲共约 226 KB，分配在 PSRAM
static constexpr uint8_t kBufferCount = 2;

// ------------------------------------------------------------
// 存储
// ------------------------------------------------------------
// Flash（LittleFS）—— 分区表 partitions.csv 里的 label
static constexpr const char* kFlashPartLabel = "storage";
static constexpr const char* kFlashMount = "/storage";
static constexpr uint8_t kFlashMaxOpenFiles = 10;

// SD 卡（阶段 2）
static constexpr int kSdCsPin = 5;
static constexpr uint32_t kSdSpiHz = 20000000UL;  // 20MHz，顺序读约 2MB/s
static constexpr const char* kSdMount = "/sdcard";

// 两种后端上目录名保持一致，切换后端不用改上层代码
static constexpr const char* kPackRoot = "/packs";

// ------------------------------------------------------------
// 双核分工
// Arduino 的 loop() 默认跑 core 1（解码），刷屏任务 pin 到 core 0
// ------------------------------------------------------------
static constexpr uint8_t kDisplayCore = 0;
static constexpr uint8_t kDecoderCore = 1;
static constexpr uint32_t kDisplayTaskStack = 4096;
static constexpr uint8_t kDisplayTaskPrio = 2;

// ------------------------------------------------------------
// 屏引脚（SPI，按实际接线改）
// 屏物理上是 240×320，横屏显示 320×240，所以 panel 宽高写 240×320 + setRotation(1)
// ------------------------------------------------------------
static constexpr int kPinSclk = 12;
static constexpr int kPinMosi = 11;
static constexpr int kPinMiso = -1;
static constexpr int kPinDc = 10;
static constexpr int kPinCs = 9;
static constexpr int kPinRst = 8;
static constexpr int kPinBl = 13;
static constexpr uint32_t kSpiWriteHz = 80000000UL;
static constexpr uint32_t kSpiReadHz = 16000000UL;

// ------------------------------------------------------------
// 输入（触摸 / 按键）
// ------------------------------------------------------------
static constexpr int kTouchPin = 4;  // TTP223，高电平有效
static constexpr uint32_t kDebounceMs = 30;
static constexpr uint32_t kLongPressMs = 800;

// ------------------------------------------------------------
// 性能预算（实测校准，见 docs/调研-同类项目与解码库实测.md）
//
// 320×180 = 57,600 px，与公开实测的 240×240 同像素数，可直接套用：
//   串行：解码 28.91ms + 刷屏 28.10ms = 57.01ms → 12fps(83ms) 余量 31%
//   并行：max(28.91, 28.10) ≈ 29ms            → 12fps(83ms) 余量 64%
// 所以 display 必须跑独立任务核 + 双缓冲，把 sum 变成 max。
// ------------------------------------------------------------
static constexpr uint32_t kDecodeMsSerial = 29;
static constexpr uint32_t kDrawMsSerial = 28;

}  // namespace pet
