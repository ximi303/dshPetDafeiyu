#pragma once

// ============================================================
// JPEG 解码：JPEGDEC → RGB565，直接写进 display 给的后缓冲
//
// 选 JPEGDEC 的理由（实测，见 docs/调研-同类项目与解码库实测.md）：
//   - 生态成熟，PlatformIO 一行引入，自带 ESP32-S3 SIMD 汇编
//   - 支持从 FLASH / RAM / SD 读数据，阶段 1 放 Flash 时能内存直解，省一次拷贝
//   - esp_new_jpeg 快约 17%，但 Arduino 封装库已停更三年，要引官方 IDF 组件才有加速
//     → 真机实测帧率不够再迁，本模块就是替换点
// ============================================================

#include <cstdint>

#include <JPEGDEC.h>

#include "config.h"

namespace pet::decoder {

class Decoder {
public:
    bool begin();

    // 解一帧 JPEG 到 dst（RGB565 小端），dst 容量至少 kFrameBytes
    bool decode(const uint8_t* jpeg, int len, uint16_t* dst);

    uint32_t lastDecodeUs() const { return _lastUs; }

private:
    JPEGDEC  _jpeg;
    uint32_t _lastUs = 0;
    bool     _ready = false;
};

}  // namespace pet::decoder
