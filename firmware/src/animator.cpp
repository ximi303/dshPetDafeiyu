#include "animator.h"

#include <Arduino.h>
#include <esp_random.h>
#include <utility>
#include <vector>

#include "player.h"
#include "storage.h"

namespace pet::animator {

// ============================================================
// 阶段 1：多段洗牌轮播
//
// 规则：把全部段索引洗一次牌，按顺序播；一轮播完再重新洗牌。
//   · 每段都会轮到，不会永远卡在前一两段
//   · 一轮内不重复，避免"同一段连着播两次"的突兀感
//   · player 用 once 模式，播完一轮就换，不理会包内的 loop 标志
//
// TODO(阶段 2)：按 Trigger 分池加权抽签
//   Idle  → 待机池
//   Click → 点击回应池（5 选 1）
//   Drag  → 拖拽池
//   随机  → 玩耍 / 吃什么 / 时节 按权重抽
// ============================================================

static Trigger s_trigger = Trigger::Idle;
static const char* s_current = "";

static std::vector<uint16_t> s_order;  // 段索引的播放顺序，按扫到的段数动态分配（SD 卡 106 段也全覆盖）
static size_t  s_pos = 0;
static uint32_t s_lastTryMs = 0;

static void reshuffle() {
    const size_t n = storage::packs().size();
    s_order.resize(n);

    for (size_t i = 0; i < n; ++i) {
        s_order[i] = static_cast<uint16_t>(i);
    }
    // Fisher-Yates：从末尾往前，与 [0, i] 中随机一个交换
    for (size_t i = n; i > 1; --i) {
        const size_t j = esp_random() % i;
        std::swap(s_order[i - 1], s_order[j]);
    }
    s_pos = 0;
}

static const char* pickNext() {
    const auto& packs = storage::packs();
    if (packs.empty()) {
        return nullptr;
    }
    if (s_pos >= s_order.size()) {
        reshuffle();
    }
    if (s_pos >= s_order.size()) {
        return nullptr;
    }
    const uint16_t idx = s_order[s_pos++];
    return (idx < packs.size()) ? packs[idx].path.c_str() : nullptr;
}

bool begin() {
    s_trigger = Trigger::Idle;
    s_order.clear();
    s_pos     = 0;
    s_current = pickNext();   // 先选好第一段，main 里起播
    return true;
}

void tick() {
    // player 在 once 模式播完一轮后会把 playing 置 false，这里负责接下一段
    if (player::playing()) {
        return;
    }
    if (millis() - s_lastTryMs < 300) {
        return;  // 打不开时别把日志刷爆
    }
    s_lastTryMs = millis();

    const char* next = pickNext();
    if (!next) {
        return;
    }
    s_current = next;
    Serial.printf("[animator] 切换 → %s\n", next);
    player::play(next, /*once=*/true);
}

void onClick() {
    s_trigger = Trigger::Click;
    Serial.println("[animator] click（阶段 2 再按池抽签）");
}

void onDrag(bool dragging) {
    s_trigger = dragging ? Trigger::Drag : Trigger::Idle;
}

void onEvent(EventKind kind, uint8_t level) {
    s_trigger = Trigger::Event;
    Serial.printf("[animator] event kind=%u level=%u\n",
                  static_cast<unsigned>(kind), static_cast<unsigned>(level));
}

const char* currentPack() {
    return s_current;
}

}  // namespace pet::animator
