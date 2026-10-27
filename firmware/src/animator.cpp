#include "animator.h"

#include <Arduino.h>

#include "storage.h"

namespace pet::animator {

// TODO(阶段 2)：把 assets/animations.json 的动画池与权重固化进来，
// 实现加权抽签 + 不连续重复。骨架阶段只维护状态。

static Trigger s_trigger = Trigger::Idle;
static const char* s_current = "";

bool begin() {
    s_trigger = Trigger::Idle;
    s_current = "";

    // 有素材就先选第一段，方便阶段 1 直接拿来播
    if (!storage::packs().empty()) {
        s_current = storage::packs().front().path.c_str();
    }
    return true;
}

void tick() {
    // TODO(阶段 2)：player 播完 → 按当前 trigger 从对应池子加权抽签
}

void onClick() {
    s_trigger = Trigger::Click;
    // TODO(阶段 2)：从 clicks 池 5 选 1
    Serial.println("[animator] click (TODO: 阶段 2 实现抽签)");
}

void onDrag(bool dragging) {
    s_trigger = dragging ? Trigger::Drag : Trigger::Idle;
}

void onEvent(EventKind kind, uint8_t level) {
    s_trigger = Trigger::Event;
    Serial.printf("[animator] event kind=%u level=%u (TODO: 阶段 2 实现)\n",
                  static_cast<unsigned>(kind), static_cast<unsigned>(level));
}

const char* currentPack() {
    return s_current;
}

}  // namespace pet::animator
