#include "input.h"

#include <Arduino.h>

namespace pet::input {

static bool     s_ready = false;
static bool     s_down = false;         // 消抖后的稳定电平
static bool     s_lastRaw = false;
static uint32_t s_changeMs = 0;         // 上次电平变化时间（消抖用）
static uint32_t s_downMs = 0;           // 按下起点（判长按用）
static bool     s_longFired = false;

bool begin() {
    pinMode(kTouchPin, INPUT_PULLUP);
    s_ready = true;
    return true;
}

KeyEvent poll() {
    if (!s_ready) {
        return KeyEvent::None;
    }

    const bool raw = (digitalRead(kTouchPin) == HIGH);
    const uint32_t now = millis();

    // 消抖：电平必须稳定 kDebounceMs 才算数
    if (raw != s_lastRaw) {
        s_lastRaw = raw;
        s_changeMs = now;
    }
    if (raw != s_down && (now - s_changeMs) >= kDebounceMs) {
        s_down = raw;
        if (s_down) {
            s_downMs = now;
            s_longFired = false;
        }
    }

    // 长按到了就先报一次，避免松开时再报一次短按
    if (s_down && !s_longFired && (now - s_downMs) >= kLongPressMs) {
        s_longFired = true;
        return KeyEvent::LongPress;
    }

    // 松开：没报过长按就算短按
    static bool s_prevDown = false;
    if (s_prevDown && !s_down) {
        s_prevDown = s_down;
        if (!s_longFired) {
            return KeyEvent::ShortPress;
        }
    }
    s_prevDown = s_down;

    return KeyEvent::None;
}

}  // namespace pet::input
