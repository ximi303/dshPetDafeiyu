#include "decoder.h"

#include <cstring>

namespace pet::decoder {

// JPEGDEC 的绘制回调：把解码出来的 RGB565 块直接 memcpy 进目标缓冲。
// 不在中间再拷一次 —— 全屏遍历一次就要几毫秒，能省就省。
static int jpegDraw(JPEGDRAW* pDraw) {
    uint16_t* dst = reinterpret_cast<uint16_t*>(pDraw->pUser);
    if (!dst || !pDraw->pPixels) {
        return 0;
    }

    const uint16_t* src = pDraw->pPixels;
    const int w = pDraw->iWidth;
    const int h = pDraw->iHeight;

    for (int y = 0; y < h; ++y) {
        std::memcpy(dst + (static_cast<size_t>(pDraw->y) + y) * kFrameW + pDraw->x,
                    src + static_cast<size_t>(y) * w,
                    static_cast<size_t>(w) * sizeof(uint16_t));
    }
    return 1;
}

bool Decoder::begin() {
    _ready = true;
    return true;
}

bool Decoder::decode(const uint8_t* jpeg, int len, uint16_t* dst) {
    if (!_ready || !jpeg || len <= 0 || !dst) {
        return false;
    }

    const uint32_t t0 = micros();

    if (!_jpeg.openRAM(const_cast<uint8_t*>(jpeg), len, jpegDraw)) {
        return false;
    }

    _jpeg.setUserPointer(dst);               // 回调里靠 pDraw->pUser 找回目标缓冲
    // 必须输出大端（高字节在前）。
    // ESP32 是小端 CPU，pushImage 走 DMA 直接发内存字节、不做任何转换；
    // 而 ST7789 的 SPI 按大端收数据。用小端的实测后果：
    // 红显示成蓝、绿显示成红、蓝显示成绿（通道循环错位，看起来又糊又花）。
    //
    // 注意：素材现在与屏幕 1:1，固件不再做缩放插值，所以这里输出大端不会有
    // 副作用（早期做缩放时需要小端真值来算通道，那条路径已经删掉了）。
    _jpeg.setPixelType(RGB565_BIG_ENDIAN);

    const int rc = _jpeg.decode(0, 0, 0);
    _jpeg.close();

    _lastUs = micros() - t0;
    return rc == 1;
}

}  // namespace pet::decoder
