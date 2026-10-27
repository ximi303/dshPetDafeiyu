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

// 开始播一段（路径来自 storage::packs()）；播完按 flags 决定是否循环
bool play(const char* path);
void stop();

// 在 loop() 里调用：到点了就推进一帧，落后太多就跳帧
void tick();

bool     playing();
uint32_t droppedFrames();  // 累计丢帧数（诊断用）

}  // namespace pet::player
