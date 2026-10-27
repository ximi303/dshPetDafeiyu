#pragma once

// ============================================================
// 输入：电容触摸（TTP223）或板载 BOOT 键
// 防抖 + 短按 / 长按区分
// ============================================================

#include <cstdint>

#include "config.h"

namespace pet::input {

enum class KeyEvent : uint8_t {
    None = 0,
    ShortPress,
    LongPress,
};

bool begin();

// 在 loop() 里调用，返回本次轮询到的事件（没有就 None）
KeyEvent poll();

}  // namespace pet::input
