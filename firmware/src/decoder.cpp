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
    // 输出小端（内存里的 uint16_t 就是真实 RGB565 值）。
    //
    // 不能直接输出大端的理由：缩放要做逐像素通道插值，必须在"值域"里运算；
    // 大端存储时 uint16_t 读出来是错的值，通道解包会全乱。
    //
    // 转大端的工作统一放到 display::scaleFrame() 写回时做（每像素一次 bswap），
    // 因为 pushImage 是 DMA 直发内存字节，而 ST7789 的 SPI 按大端收。
    _jpeg.setPixelType(RGB565_LITTLE_ENDIAN);

    const int rc = _jpeg.decode(0, 0, 0);
    _jpeg.close();

    _lastUs = micros() - t0;
    return rc == 1;
}

}  // namespace pet::decoder
