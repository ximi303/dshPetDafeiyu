#pragma once

// ============================================================
// 桌宠状态机：决定「下一播什么」
//
// 逻辑照搬桌面插件 dsh-pet（见 assets/animations.json）：
//   动画池：idle(权重10) / turn(5) / moves(5) / drag / clicks(5 选 1)
//   随机分类：小动作 20 / 玩耍 20 / 吃什么 16 / 时节 14 / 文字 10
//   事件档位：balance 6 档 / whisper 3 / workState 6 档
//   抽签规则：按权重抽，且不与上一段重复（不连续重复）
// ============================================================

#include <cstdint>

namespace pet::animator {

// 触发来源
enum class Trigger : uint8_t {
    Idle,    // 待机链
    Click,   // 点击宠物
    Drag,    // 拖拽中
    Move,    // 走动
    Event,   // 余额 / 工作状态等档位事件
};

// 事件档位（events 数组下标即档位）
enum class EventKind : uint8_t {
    Balance = 0,    // 0-20% / 20-40% / 40-60% / 60-80% / 80-100% / 100%
    Whisper = 1,    // 碎碎念，默认每 300s 抽一段
    WorkState = 2,  // 思考 / 工具调用 / 工具完成 / 等待批准 / 完成 / 出错
};

bool begin();

// 在 loop() 里调用：当前这段播完了就按权重抽下一段
void tick();

// 外部输入
void onClick();
void onDrag(bool dragging);
void onEvent(EventKind kind, uint8_t level);

// 当前选中的 pack 路径（交给 player::play）
const char* currentPack();

}  // namespace pet::animator
