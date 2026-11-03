#include "storage.h"

#include <Arduino.h>
#include <LittleFS.h>
#include <SD.h>
#include <SPI.h>

namespace pet::storage {

static fs::FS* s_fs = nullptr;
static String s_root;
static std::vector<PackEntry> s_packs;

// SD 专用 SPI 总线（SPI3/HSPI），与屏的 SPI2 物理隔离。
// 不能用默认的 SPI 对象：那是 SPI2，和 LovyanGFX 刷屏是同一控制器。
static SPIClass s_sdSpi(HSPI);

// ------------------------------------------------------------
// 裸 GPIO 探测：绕开 SPI 外设和 SD 库，直接用 bit-bang 发 CMD0
//
// 目的：把「接线/供电问题」和「SPI 外设配置问题」分开。
//   MISO 读到 0x01  → 卡在线，问题在库或外设配置
//   MISO 一直 0xFF  → 卡完全没回应，查 VCC/线序
//   MISO 一直 0x00  → MISO 被拉死，可能短路或接错
// ------------------------------------------------------------
static uint8_t spiXfer(uint8_t out) {
    uint8_t in = 0;
    for (int i = 7; i >= 0; --i) {
        digitalWrite(kSdMosiPin, (out >> i) & 1);
        delayMicroseconds(2);
        digitalWrite(kSdSckPin, HIGH);
        delayMicroseconds(2);
        in = static_cast<uint8_t>((in << 1) | (digitalRead(kSdMisoPin) ? 1 : 0));
        digitalWrite(kSdSckPin, LOW);
        delayMicroseconds(2);
    }
    return in;
}

static void probeSdPins() {
    // 先把四根线全部设为带上拉输入，读一遍静态电平。
    // 正常情况（模块接对、卡未选中）四根都应读到 1（上拉为高）。
    // 哪根读到 0，那根就被外部拉死在低电平：要么短到 GND，要么接到了输出低的脚。
    {
        const int   pins[]  = {kSdSckPin, kSdMosiPin, kSdMisoPin, kSdCsPin};
        const char* names[] = {"SCK ", "MOSI", "MISO", "CS  "};
        for (int i = 0; i < 4; ++i) {
            pinMode(pins[i], INPUT_PULLUP);
        }
        delay(10);
        for (int i = 0; i < 4; ++i) {
            Serial.printf("[storage] %s(GPIO%d) 静态电平 = %d\n",
                          names[i], pins[i], digitalRead(pins[i]));
        }
    }

    pinMode(kSdSckPin, OUTPUT);
    pinMode(kSdMosiPin, OUTPUT);
    pinMode(kSdCsPin, OUTPUT);
    pinMode(kSdMisoPin, INPUT_PULLUP);
    digitalWrite(kSdCsPin, HIGH);
    digitalWrite(kSdSckPin, LOW);
    delay(5);

    // 至少 74 个时钟，让卡进入 SPI 模式（CS 高电平期间发 0xFF）
    for (int i = 0; i < 10; ++i) {
        spiXfer(0xFF);
    }

    digitalWrite(kSdCsPin, LOW);
    delayMicroseconds(10);
    const uint8_t cmd0[6] = {0x40, 0x00, 0x00, 0x00, 0x00, 0x95};  // CMD0 + CRC7
    for (int i = 0; i < 6; ++i) {
        spiXfer(cmd0[i]);
    }
    uint8_t r = 0xFF;
    for (int i = 0; i < 16; ++i) {
        r = spiXfer(0xFF);
        if (r != 0xFF) {
            break;
        }
    }
    digitalWrite(kSdCsPin, HIGH);
    digitalWrite(kSdMisoPin, INPUT_PULLUP);

    Serial.printf("[storage] 裸 SPI 探测: SCK=%d MISO=%d MOSI=%d CS=%d\n",
                  kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    Serial.printf("[storage] CMD0 响应 = 0x%02X  (0x01=卡正常, 0xFF=无响应)\n", r);
}

// 运行期实际使用的后端。它不一定等于编译期的 kBackend：
// kBackend 只是"首选"，首选挂不上时会自动换成另一个。
static Backend s_active = kBackend;

static bool mountFlash() {
    // 按分区 label 挂载（partitions.csv 里的 "storage"）。
    // 注意第 4 个参数是 partitionLabel，不是挂载点 —— 写错会挂到默认分区上。
    if (!LittleFS.begin(false, kFlashMount, kFlashMaxOpenFiles, kFlashPartLabel)) {
        Serial.println("[storage] Flash(LittleFS) 挂载失败");
        return false;
    }
    s_fs = &LittleFS;
    // 注意：Arduino-ESP32 的 FS::open() 会自动把 mountpoint（kFlashMount）拼在路径前面，
    // 所以这里只能写 FS 内部路径 "/packs"。若写成 "/storage/packs"，
    // 实际访问会变成 "/storage/storage/packs" 而永远打不开。
    s_root = String(kPackRoot);
    return true;
}

static bool mountSd() {
    // 必须先显式 begin 指定引脚，再交给 SD.begin。
    // 参数顺序是 (sck, miso, mosi, ss)，别按 SPI 平时的 mosi/miso 习惯写反。
    s_sdSpi.begin(kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    // 返回 0 表示失败；成功返回卡类型（1=MMC 2=SDSC 3=SDHC/SDXC）
    const uint8_t cardType = SD.begin(kSdCsPin, s_sdSpi, kSdSpiHz, kSdMount);
    if (!cardType) {
        Serial.println("[storage] SD 挂载失败：查 VCC 是否接 5V、卡是否 FAT32");
        s_sdSpi.end();       // 释放 SPI 外设占用的引脚，下面用裸 GPIO 探测
        probeSdPins();
        return false;
    }
    static const char* kTypeName[] = {"", "MMC", "SDSC", "SDHC/SDXC"};
    Serial.printf("[storage] SD 已挂载：%s  容量 %llu MB\n",
                  kTypeName[cardType > 3 ? 0 : cardType],
                  static_cast<unsigned long long>(SD.cardSize()) / (1024ULL * 1024ULL));
    s_fs = &SD;
    s_root = String(kPackRoot);  // 同理，SD 的 mountpoint 也由 FS 层自动拼接
    return true;
}

fs::FS* mount() {
    if (s_fs) {
        return s_fs;
    }

    // 先试首选后端；挂不上就自动换成另一个，保证程序总能跑起来。
    // 场景价值：卡没插/接触不良/线接错时，退回 Flash 里的预置素材继续播放，
    // 屏幕上照样有动画，只是素材数量少，不至于黑屏等死。
    const bool preferSd = (kBackend == Backend::SD);

    if (preferSd) {
        if (mountSd()) {
            s_active = Backend::SD;
            return s_fs;
        }
        Serial.println("[storage] → 回退到 Flash(LittleFS)");
        if (mountFlash()) {
            s_active = Backend::Flash;
            return s_fs;
        }
    } else {
        if (mountFlash()) {
            s_active = Backend::Flash;
            return s_fs;
        }
        Serial.println("[storage] → 回退到 SD 卡");
        if (mountSd()) {
            s_active = Backend::SD;
            return s_fs;
        }
    }

    Serial.println("[storage] 两个后端都挂载失败");
    return nullptr;
}

bool mounted() {
    return s_fs != nullptr;
}

Backend activeBackend() {
    return s_active;
}

const char* packRootPath() {
    return s_root.c_str();
}

static void scanDir(fs::FS& fs, const String& dir, std::vector<PackEntry>& out) {
    File root = fs.open(dir, "r");
    if (!root) {
        return;
    }
    if (!root.isDirectory()) {
        root.close();
        return;
    }

    while (true) {
        File f = root.openNextFile();
        if (!f) {
            break;
        }
        const String name = String(f.name());
        const String child = dir + "/" + name;
        if (f.isDirectory()) {
            scanDir(fs, child, out);
        } else if (name.endsWith(".petpack")) {
            PackEntry e;
            e.path = child;
            // dir 形如 /storage/packs/<分类>，最后一段就是分类名
            const int slash = dir.lastIndexOf('/');
            e.group = (slash >= 0) ? dir.substring(slash + 1) : String("");
            // 段名 = 文件名去掉 .petpack
            const int dot = name.lastIndexOf('.');
            e.name = (dot > 0) ? name.substring(0, dot) : name;
            out.push_back(e);
        }
        f.close();
    }
    root.close();
}

size_t scanPacks() {
    s_packs.clear();
    if (!mount()) {
        return 0;
    }
    scanDir(*s_fs, String(packRootPath()), s_packs);
    return s_packs.size();
}

const std::vector<PackEntry>& packs() {
    return s_packs;
}

}  // namespace pet::storage
