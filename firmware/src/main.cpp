// ============================================================
// ESP32 桌宠 —— 主程序骨架
//
// 骨架阶段只负责「把各模块串起来 + 打印自检信息」，
// 真正的播放循环在 player.cpp 里，标着 TODO(阶段 1)。
// ============================================================

#include <Arduino.h>

#include "animator.h"
#include "config.h"
#include "decoder.h"
#include "display.h"
#include "input.h"
#include "petpack.h"
#include "player.h"
#include "storage.h"

using namespace pet;  // Backend / kFrameW 等常量在 pet 下；各模块在 pet::xxx 下

static decoder::Decoder s_decoder;
static uint32_t s_lastStatMs = 0;

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n[pet] boot");

    // ---- 1) 存储：阶段 1 是 Flash(LittleFS)，阶段 2 改成 SD 只需改 -DSTORAGE_BACKEND ----
    if (!storage::mount()) {
        Serial.println("[pet] FATAL: 存储挂载失败");
        return;
    }
    Serial.printf("[pet] backend = %s\n",
                  storage::activeBackend() == Backend::Flash ? "Flash(LittleFS)" : "SD");
    Serial.printf("[pet] root    = %s\n", storage::packRootPath());

    const size_t n = storage::scanPacks();
    Serial.printf("[pet] 扫到 %u 段\n", static_cast<unsigned>(n));
    for (const auto& e : storage::packs()) {
        Serial.printf("[pet]   %s / %s\n", e.group.c_str(), e.name.c_str());
    }
    if (n == 0) {
        Serial.println("[pet] WARN: 没有 .petpack —— 先跑 tools/pipeline/pick_flash.py 再 uploadfs");
    }

    // ---- 2) 外设 ----
    if (!display::begin()) {
        Serial.println("[pet] FATAL: 屏初始化失败（PSRAM 没起来？引脚对不对？）");
        return;
    }
    if (!s_decoder.begin()) {
        Serial.println("[pet] WARN: decoder 未就绪");
    }
    player::begin();
    animator::begin();
    input::begin();

    Serial.printf("[pet] ready: 内容 %ux%u @%ufps，帧预算 %lu us\n",
                  kFrameW, kFrameH, kFps, static_cast<unsigned long>(kFrameBudgetUs));
    Serial.printf("[pet] 缓冲: JPEG %u KB，RGB565 %u KB × %u（PSRAM）\n",
                  static_cast<unsigned>(kJpegBufBytes / 1024),
                  static_cast<unsigned>(kFrameBytes / 1024),
                  kBufferCount);

    // ---- 3) 起播第一段（阶段 1 打通后这里会真的动起来）----
    if (n > 0) {
        player::play(storage::packs().front().path.c_str());
    }
}

void loop() {
    player::tick();
    animator::tick();

    // 点击 → 触发一次点击回应
    if (input::poll() == input::KeyEvent::ShortPress) {
        animator::onClick();
    }

    // 每 5 秒打一次运行状态，方便看帧率与丢帧
    if (millis() - s_lastStatMs >= 5000) {
        s_lastStatMs = millis();
        Serial.printf("[pet] 已刷 %lu 帧，丢帧 %lu\n",
                      static_cast<unsigned long>(display::framesShown()),
                      static_cast<unsigned long>(player::droppedFrames()));
    }

    delay(1);
}
