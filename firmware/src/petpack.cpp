#include "petpack.h"

#include <cstdlib>
#include <cstring>

namespace pet {

void Pack::_reset() {
    if (_offsets) {
        free(_offsets);
        _offsets = nullptr;
    }
    _hdr = PackHeader{};
    _fileSize = 0;
    _valid = false;
}

void Pack::close() {
    if (_file) {
        _file.close();
    }
    _reset();
}

bool Pack::open(fs::FS& fs, const char* path) {
    close();

    _file = fs.open(path, "r");
    if (!_file) {
        return false;
    }

    _fileSize = _file.size();
    if (_fileSize < kPackHeaderSize) {
        close();
        return false;
    }

    // 头部：22 字节（PackHeader 是 packed，可以直接读进去）
    if (_file.read(reinterpret_cast<uint8_t*>(&_hdr), kPackHeaderSize) != static_cast<int>(kPackHeaderSize)) {
        close();
        return false;
    }
    if (std::memcmp(_hdr.magic, kPackMagic, 4) != 0) {
        close();
        return false;
    }
    if (_hdr.version != kPackVersion) {
        close();
        return false;
    }
    if (_hdr.frameCount == 0) {
        close();
        return false;
    }
    // 只支持与 config.h 一致的尺寸；换分辨率要同步改 config.h 并重跑流水线
    if (_hdr.width != kFrameW || _hdr.height != kFrameH) {
        close();
        return false;
    }

    // 偏移表：4 字节/帧，一次性读进来
    // 实测最长一段约 121 帧 → 484 字节，放堆里毫无压力
    const uint32_t tableBytes = 4u * _hdr.frameCount;
    if (_fileSize < kPackHeaderSize + tableBytes) {
        close();
        return false;
    }
    _offsets = static_cast<uint32_t*>(malloc(tableBytes));
    if (!_offsets) {
        close();
        return false;
    }
    if (_file.read(reinterpret_cast<uint8_t*>(_offsets), tableBytes) != static_cast<int>(tableBytes)) {
        close();
        return false;
    }

    // 自洽性检查：偏移必须严格递增，且落在文件范围内
    // （等价于 PC 端 verify_pack() 校验 FFD8/FFD9 的固件侧版本）
    uint32_t prev = kPackHeaderSize + tableBytes;
    for (uint16_t i = 0; i < _hdr.frameCount; ++i) {
        if (_offsets[i] < prev || _offsets[i] >= _fileSize) {
            close();
            return false;
        }
        prev = _offsets[i];
    }

    _valid = true;
    return true;
}

int Pack::readFrame(uint16_t index, uint8_t* out, uint32_t cap) {
    uint32_t offset = 0;
    uint32_t length = 0;
    if (!frameRange(index, offset, length)) {
        return kErrNotOpen;
    }
    if (length > cap) {
        return kErrBufSmall;
    }
    if (!_file.seek(offset)) {
        return kErrSeek;
    }
    // 一帧在容器里是连续的，一次 f_read 读完 → 保住顺序读的速度
    const int n = _file.read(out, length);
    if (n < 0 || static_cast<uint32_t>(n) != length) {
        return kErrRead;
    }
    return n;
}

bool Pack::frameRange(uint16_t index, uint32_t& offset, uint32_t& length) const {
    if (!_valid || !_offsets || index >= _hdr.frameCount) {
        return false;
    }
    offset = _offsets[index];
    length = (static_cast<uint32_t>(index) + 1u < _hdr.frameCount)
                 ? (_offsets[index + 1] - offset)
                 : (_fileSize - offset);
    return length > 0;
}

}  // namespace pet
