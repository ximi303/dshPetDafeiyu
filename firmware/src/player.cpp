#include "player.h"

#include <Arduino.h>
#include <esp_heap_caps.h>

#include "config.h"
#include "decoder.h"
#include "display.h"
#include "petpack.h"
#include "storage.h"

namespace pet::player {

// ============================================================
// 播放器：读 .petpack → JPEGDEC 解码 → 写后缓冲 → present 交换
//
// 线程模型：
//   tick() 跑在 loop()（core 1），负责读帧 + 解码 + CPU 写内存
//   displayTask 跑在 core 0，负责 DMA 刷屏
//   两者通过双缓冲 + 信号量解耦，所以「解码 29ms + 刷屏 28ms」能重叠成 max()
// ============================================================

static bool     s_playing = false;
static bool     s_forceOnce = false;   // true：忽略包内 loop 标志，播完就停
static uint16_t s_frameIndex = 0;
static uint16_t s_frameCount = 0;
static uint32_t s_nextFrameUs = 0;
static uint32_t s_dropped = 0;

static Pack             s_pack;
static decoder::Decoder s_decoder;
static uint8_t*         s_jpegBuf = nullptr;  // kJpegBufBytes，放 PSRAM

bool begin() {
    s_playing = false;
    s_frameIndex = 0;
    s_frameCount = 0;
    s_dropped = 0;

    if (!s_decoder.begin()) {
        Serial.println("[player] 解码器初始化失败");
        return false;
    }

    if (!s_jpegBuf) {
        // 32KB JPEG 缓冲放 PSRAM：内部 RAM 留给 DMA 描述符、任务栈和 WiFi 栈
        s_jpegBuf = static_cast<uint8_t*>(
            heap_caps_malloc(kJpegBufBytes, MALLOC_CAP_SPIRAM));
        if (!s_jpegBuf) {
            Serial.printf("[player] JPEG 缓冲分配失败：需要 %lu 字节\n",
                          static_cast<unsigned long>(kJpegBufBytes));
            return false;
        }
    }
    return true;
}

bool play(const char* path, bool once) {
    if (!path) {
        return false;
    }

    fs::FS* fs = storage::mount();
    if (!fs) {
        Serial.println("[player] 存储未挂载");
        return false;
    }

    if (!s_pack.open(*fs, path)) {
        Serial.printf("[player] 打不开：%s\n", path);
        return false;
    }

    s_frameIndex = 0;
    s_frameCount = s_pack.frameCount();
    s_forceOnce  = once;
    s_playing = true;
    s_nextFrameUs = micros();

    // 打印的是"实际生效"的模式，不是包内 loop 标志。
    // 素材包里 loop=1，但 once 模式只会播一轮；照抄标志会写成"循环"，误导排查。
    const bool willLoop = s_pack.loop() && !s_forceOnce;
    Serial.printf("[player] 播放 %s  %ux%u  %ufps  %u 帧%s\n",
                  path,
                  static_cast<unsigned>(s_pack.width()),
                  static_cast<unsigned>(s_pack.height()),
                  static_cast<unsigned>(s_pack.fps()),
                  static_cast<unsigned>(s_frameCount),
                  willLoop ? "（循环）" : "（单次）");
    return true;
}

void stop() {
    s_playing = false;
    s_pack.close();
}

void tick() {
    if (!s_playing || s_frameCount == 0) {
        return;
    }

    const uint32_t now = micros();
    if (static_cast<int32_t>(now - s_nextFrameUs) < 0) {
        return;  // 还没到这一帧的时间点
    }

    // 这一帧的预算已经用光了 → 记一次丢帧，但时间轴照走
    if (s_nextFrameUs + kFrameBudgetUs <= now && s_frameIndex > 0) {
        s_dropped++;
    }

    // 1) 取后缓冲。拿不到说明上一帧还在刷，直接丢这一帧（不排队，否则越播越慢）
    uint16_t* back = display::acquireBack();
    if (!back) {
        s_dropped++;
        s_nextFrameUs += kFrameBudgetUs;
        return;
    }

    // 2) 从容器读一帧 JPEG（一次顺序读，不分块）
    const int n = s_pack.readFrame(s_frameIndex, s_jpegBuf, kJpegBufBytes);
    if (n <= 0) {
        s_dropped++;
        s_nextFrameUs += kFrameBudgetUs;
        return;
    }

    // 3) 解码到后缓冲（JPEGDEC 直接 memcpy 进 dst，不再中转）
    if (!s_decoder.decode(s_jpegBuf, n, back)) {
        s_dropped++;
        s_nextFrameUs += kFrameBudgetUs;
        return;
    }

    // 4) 交换缓冲，刷屏任务立刻接手
    display::present();

    // 5) 推进帧号与时间轴
    s_frameIndex++;
    if (s_frameIndex >= s_frameCount) {
        if (s_pack.loop() && !s_forceOnce) {
            s_frameIndex = 0;
        } else {
            s_frameIndex = static_cast<uint16_t>(s_frameCount - 1);
            s_playing = false;  // once 模式（或非循环段）播完就停，等 animator 接下一段
        }
    }

    const uint16_t fps = s_pack.fps();
    s_nextFrameUs += 1000000UL / (fps ? fps : kFps);
}

bool playing() {
    return s_playing;
}

uint32_t droppedFrames() {
    return s_dropped;
}

}  // namespace pet::player
