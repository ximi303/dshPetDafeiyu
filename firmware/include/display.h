#pragma once

// ============================================================
// 刷屏：双核 + 双缓冲
//
// 为什么必须并行（实测，见 docs/调研-同类项目与解码库实测.md）：
//   串行：decode 28.91ms + draw 28.10ms = 57.01ms  → 12fps(83ms) 余量 31%
//   并行：max(28.91, 28.10) ≈ 29ms                → 12fps(83ms) 余量 64%
//
// core 1（Arduino 的 loop）  ：解码，写「后缓冲」，写完 present()
// core 0（本模块的任务）     ：把「前缓冲」DMA 推到屏
// 两块缓冲都在 PSRAM，靠 swap 交换，不拷贝。
// ============================================================

#include <cstdint>

#include "config.h"

namespace pet::display {

bool begin();  // 初始化屏 + 分配双缓冲 + 创建 core0 刷屏任务
void end();

// 取可写的后缓冲；上一帧还没刷出去时返回 nullptr —— 调用方应当丢帧，不要排队
uint16_t* acquireBack(uint32_t timeoutMs = 0);

// 提交后缓冲并通知 core0 去刷（内部交换前后缓冲）
void present();

uint32_t framesShown();  // 已刷帧数（统计/诊断用）

}  // namespace pet::display
