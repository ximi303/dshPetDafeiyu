#pragma once

// ============================================================
// .petpack v1 —— 固件侧唯一的素材读取契约
//
// 必须与 tools/pipeline/pipeline.py 的 build_pack() 严格对应：
//   struct.pack("<HHHHHII", VERSION, w, h, fps, n, LOOP_FLAG, 0)
//   struct.pack(f"<{n}I", *offsets)
//   然后逐帧 JPEG 相接
//
// 之所以敢让 Flash 与 SD 两个阶段共用这一份契约：
// ESP32 Arduino 下 LittleFS 和 SD 都实现了 fs::FS，
// 所以本文件完全不关心数据来自哪个介质。
// ============================================================

#include <cstdint>

#include <FS.h>

#include "config.h"

namespace pet {

// 小端序、定长 22 字节：4 + 2*5 + 4 + 4
struct PackHeader {
    char     magic[4];     // "PETP"
    uint16_t version;      // 1
    uint16_t width;        // 320
    uint16_t height;       // 180
    uint16_t fps;          // 12
    uint16_t frameCount;   // 帧数
    uint32_t flags;        // bit0 = 循环播放
    uint32_t reserved;     // 0
} __attribute__((packed));

static constexpr char     kPackMagic[4] = {'P', 'E', 'T', 'P'};
static constexpr uint16_t kPackVersion = 1;
static constexpr uint32_t kPackHeaderSize = 22;
static constexpr uint32_t kPackFlagLoop = 0x1u;

// readFrame 的负返回值
enum : int {
    kErrNotOpen = -1,   // 未打开 / index 越界
    kErrBufSmall = -2,  // 目标缓冲装不下这一帧
    kErrSeek = -3,
    kErrRead = -4,
};

class Pack {
public:
    Pack() = default;
    ~Pack() { close(); }
    Pack(const Pack&) = delete;
    Pack& operator=(const Pack&) = delete;

    // fs 由 storage 模块给出（LittleFS 或 SD），失败返回 false
    bool open(fs::FS& fs, const char* path);
    void close();
    bool valid() const { return _valid; }

    // 按偏移表定位第 index 帧，整帧顺序读入 out。
    // 帧长 = offs[i+1] - offs[i]，末帧为 fileSize - offs[i]。
    // 成功返回实际字节数，失败返回上面那几个负值。
    int readFrame(uint16_t index, uint8_t* out, uint32_t cap);

    // 只想要「这一帧在文件里的位置和长度」时用（比如交给解码库流式读）
    bool frameRange(uint16_t index, uint32_t& offset, uint32_t& length) const;

    uint16_t width() const { return _hdr.width; }
    uint16_t height() const { return _hdr.height; }
    uint16_t fps() const { return _hdr.fps; }
    uint16_t frameCount() const { return _hdr.frameCount; }
    bool     loop() const { return (_hdr.flags & kPackFlagLoop) != 0u; }

private:
    void _reset();

    fs::File   _file;
    PackHeader _hdr{};
    uint32_t*  _offsets = nullptr;
    uint32_t   _fileSize = 0;
    bool       _valid = false;
};

}  // namespace pet
