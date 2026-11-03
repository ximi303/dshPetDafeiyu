#pragma once

// ============================================================
// 播放调度：按帧率推进、循环、超时丢帧
//
// 关键约束：解码慢就**丢帧**，绝不排队。
// 12fps = 83ms/帧；若这一帧花了 120ms，就直接跳到下一个时间点，
// 而不是排队补播 —— 否则动画会越播越慢、时间轴越拖越长。
// ============================================================

#include <cstdint>

#include "config.h"

namespace pet::player {

bool begin();

// 开始播一段（路径来自 storage::packs()）。
//   once = false：按包内 loop 标志决定是否循环（默认）
//   once = true ：忽略包内标志，播完一轮就停，playing() 变 false，
//                 由 animator 接着播下一段 —— 多段轮播用的就是这个模式
bool play(const char* path, bool once = false);
void stop();

// 在 loop() 里调用：到点了就推进一帧，落后太多就跳帧
void tick();

bool     playing();
uint32_t droppedFrames();  // 累计丢帧数（诊断用）

}  // namespace pet::player
