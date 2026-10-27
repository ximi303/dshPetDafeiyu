#include "player.h"

#include <Arduino.h>

#include "decoder.h"
#include "display.h"
#include "petpack.h"
#include "storage.h"

namespace pet::player {

// TODO(阶段 1)：真正的播放循环。
// 骨架阶段只把状态和帧率账算清楚，不真的取帧解码。

static bool     s_playing = false;
static uint16_t s_frameIndex = 0;
static uint16_t s_frameCount = 0;
static uint32_t s_nextFrameUs = 0;
static uint32_t s_dropped = 0;

bool begin() {
    s_playing = false;
    s_frameIndex = 0;
    s_frameCount = 0;
    s_dropped = 0;
    return true;
}

bool play(const char* path) {
    if (!path) {
        return false;
    }
    // TODO(阶段 1)：Pack::open(*storage::mount(), path) 拿到 frameCount/fps
    s_frameIndex = 0;
    s_frameCount = 0;
    s_playing = true;
    s_nextFrameUs = micros();
    Serial.printf("[player] play %s (TODO: 阶段 1 实现)\n", path);
    return true;
}

void stop() {
    s_playing = false;
}

void tick() {
    if (!s_playing) {
        return;
    }

    const uint32_t now = micros();
    if (static_cast<int32_t>(now - s_nextFrameUs) < 0) {
        return;  // 还没到这一帧的时间点
    }

    // 落后超过一整帧就直接跳帧，不补播
    if (s_nextFrameUs + kFrameBudgetUs <= now && s_frameIndex > 0) {
        s_dropped++;
    }

    // TODO(阶段 1)：
    //   1) uint16_t* back = display::acquireBack();
    //      拿不到 nullptr 就 ++s_dropped 并直接 return（不排队）
    //   2) int n = pack.readFrame(s_frameIndex, jpegBuf, kJpegBufBytes);
    //   3) decoder.decode(jpegBuf, n, back);
    //   4) display::present();

    s_frameIndex++;
    if (s_frameCount > 0 && s_frameIndex >= s_frameCount) {
        s_frameIndex = 0;  // TODO: 按 Pack::loop() 决定是不是重头播
    }
    s_nextFrameUs += kFrameBudgetUs;  // 按时间轴推进，不按实际耗时
}

bool playing() {
    return s_playing;
}

uint32_t droppedFrames() {
    return s_dropped;
}

}  // namespace pet::player
