#include "display.h"
#include "boot_logo.h"

#include <cstring>

#include <Arduino.h>
#include <LovyanGFX.hpp>

#include <esp_heap_caps.h>
// IDF 4.4 (Arduino Core 2.x) 没有 esp_cache.h，只能直调 ROM 里的写回函数。
// 见 displayTask() 里的说明。
#if __has_include(<esp32s3/rom/cache.h>)
  #include <esp32s3/rom/cache.h>
  #define PET_HAVE_ROM_CACHE 1
#endif
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

namespace pet::display {

// ------------------------------------------------------------
// 屏（LovyanGFX）。引脚全部来自 config.h，换板子只改 config.h
// 屏物理是 240×320，横过来当 320×240 用，所以 panel 写 240×320 + setRotation(1)
// ------------------------------------------------------------
class LGFX : public lgfx::LGFX_Device {
    lgfx::Panel_ST7789 _panel;
    lgfx::Bus_SPI      _bus;
    // 背光不挂 LovyanGFX 的 Light 类：
    //   1.2.35 只有 Light_PWM / Light_CH422G，没有 Light_GPIO
    //   而 Light_PWM 实测不出电平（BL 直连 3V3 能亮，说明是高电平点亮）
    // BL 只需常亮，改由 display::begin() 里的 pinMode + digitalWrite 直接控制。

public:
    LGFX() {
        {
            auto cfg = _bus.config();
            cfg.spi_host = SPI2_HOST;
            cfg.spi_mode = 0;
            cfg.freq_write = kSpiWriteHz;   // 80MHz
            cfg.freq_read = kSpiReadHz;
            cfg.spi_3wire = false;
            cfg.use_lock = true;
            cfg.dma_channel = SPI_DMA_CH_AUTO;  // 必须开 DMA：实测 22ms vs 42ms
            cfg.pin_sclk = kPinSclk;
            cfg.pin_mosi = kPinMosi;
            cfg.pin_miso = kPinMiso;
            cfg.pin_dc = kPinDc;
            _bus.config(cfg);
            _panel.setBus(&_bus);
        }
        {
            auto cfg = _panel.config();
            cfg.pin_cs = kPinCs;
            cfg.pin_rst = kPinRst;
            cfg.pin_busy = -1;
            cfg.panel_width = 240;
            cfg.panel_height = 320;
            cfg.offset_x = 0;
            cfg.offset_rotation = 0;
            // 本屏实测标定值（2026-11-03，逐色验证得出）：
            //   invert=true   → 黑白颠倒（白刷成黑、黑刷成白）  ⇒ 必须 false
            //   rgb_order=true → 红蓝互换（发红显示蓝、发蓝显示红）⇒ 必须 false
            cfg.invert = false;
            cfg.rgb_order = false;      // RGB 排列
            cfg.dlen_16bit = false;
            cfg.bus_shared = true;
            _panel.config(cfg);
        }
        setPanel(&_panel);
    }
};

static LGFX s_lcd;

// ------------------------------------------------------------
// 双缓冲状态
// ------------------------------------------------------------
static uint16_t* s_buf[kBufferCount] = {nullptr, nullptr};
static uint8_t   s_front = 0;              // 正在/即将被刷的那一块
static volatile bool      s_pending = false;
static SemaphoreHandle_t  s_mutex = nullptr;
static SemaphoreHandle_t  s_sem = nullptr;
static TaskHandle_t       s_task = nullptr;
static volatile uint32_t  s_frames = 0;
static bool               s_ready = false;

// ------------------------------------------------------------
// 为什么固件端不做缩放
//
// 早期走过"运行时放大"这条路：素材 320×180 → 放大 1.33/1.5/2 倍 → 裁到 320×240。
// 实机结论是这条路到头了：320×180 里人物只占约 105px 高，拉到 240 就是 2.3 倍
// 上采样，插值只能抹平锯齿、造不出细节，越拉越糊，还额外吃掉每帧 15ms。
//
// 现在的做法是把放大搬到流水线：源视频 640×360 居中裁 426×320，再 lanczos
// 缩放到 320×240，全程用源视频的真实像素。素材已与屏幕 1:1，这里原样直推即可。
//
// 历史倍数与裁切尺寸的等价关系（改 pipeline 的 CROP_* 时参考）：
//   1.33 倍 ↔ 裁 480×360   人物偏小
//   1.50 倍 ↔ 裁 426×320   人物完整、大小合适  ← 当前素材就是这个裁法
//   2.00 倍 ↔ 裁 320×240   切头切脚
// ------------------------------------------------------------

static void displayTask(void* /*arg*/) {
    while (true) {
        if (xSemaphoreTake(s_sem, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        uint8_t idx;
        if (xSemaphoreTake(s_mutex, portMAX_DELAY) == pdTRUE) {
            idx = s_front;
            xSemaphoreGive(s_mutex);
        } else {
            continue;
        }

        // 【必须】把这一帧从 DCache 写回 PSRAM，再交给 DMA 读。
        //
        // 原因：ESP32-S3 的 PSRAM 走 write-back cache，CPU 解码写完的像素
        // 可能还在 cache 里没落到 PSRAM。而 LovyanGFX 的 dma_cache_sync()
        // 依赖 <esp_cache.h>（IDF 5.x），本工程是 Core 2.x(IDF 4.4)，
        // 那个 #if 不成立 → 同步函数是空实现 → DMA 读到旧数据。
        // 症状就是：画面能动能动但有彩色噪点、横向条纹、背景色错乱。
        //
        // fillScreen 之所以正常，是因为它走 CPU 直接写 LCD 命令通道，
        // 根本不经过 PSRAM 这块缓冲。
#if defined(PET_HAVE_ROM_CACHE)
        Cache_WriteBack_Addr(reinterpret_cast<uint32_t>(s_buf[idx]), kFrameBytes);
#endif

        // 整帧 DMA 推出去，别用逐像素画点。
        // 素材与屏幕 1:1（320×240），无需缩放；解码器已输出大端字节序，直发即可。
        s_lcd.startWrite();
        s_lcd.pushImage(kFrameX, kFrameY, kFrameW, kFrameH, s_buf[idx]);
        s_lcd.endWrite();

        s_frames++;
        s_pending = false;
    }
}

bool begin() {
    // 背光：直接拉高 BL（不挂 LovyanGFX 的 Light 类，原因见类定义处注释）
    pinMode(kPinBl, OUTPUT);
    digitalWrite(kPinBl, HIGH);

    s_lcd.init();

    // 关键保护：SPI 总线初始化后必须重新拉高 BL。
    // kPinBl(GPIO13) 恰好是 SPI2/FSPI 的默认 MISO 引脚，
    // 总线初始化会把这个脚重配成 SPI 功能，导致背光在 init 后熄灭。
    pinMode(kPinBl, OUTPUT);
    digitalWrite(kPinBl, HIGH);

    s_lcd.setRotation(1);       // 240×320 → 320×240 横屏
    s_lcd.setBrightness(255);   // 未挂 Light 时为空操作，保留以备将来调光
    s_lcd.fillScreen(TFT_BLACK);

    // 双缓冲放 PSRAM：2 × 113KB
    for (uint8_t i = 0; i < kBufferCount; ++i) {
        s_buf[i] = static_cast<uint16_t*>(heap_caps_malloc(kFrameBytes, MALLOC_CAP_SPIRAM));
        if (!s_buf[i]) {
            Serial.printf("[display] PSRAM 分配失败（第 %u 块，需要 %lu 字节）\n",
                          i, (unsigned long)kFrameBytes);
            return false;
        }
        std::memset(s_buf[i], 0, kFrameBytes);
    }

    // ==================================================================
    // 调试区：全部用 #if 0 关闭。需要时把对应的 0 改成 1 重新编译即可，
    // 不用重新翻历史代码。两块互不影响，也可以同时开。
    // ==================================================================

    // 调试 A —— fillScreen 六色自检
    // 验证：背光是否点亮、SPI 数据是否通、invert / rgb_order 是否正确
    // 期望：白 → 黑 → 红 → 绿 → 蓝 → 黑
    //   黑白颠倒 → cfg.invert 配反
    //   红蓝互换 → cfg.rgb_order 配反
    //   全程黑   → SPI 数据没通（查 MOSI/SCLK/DC/CS，或把 kSpiWriteHz 降到 20MHz）
#if 0
    s_lcd.fillScreen(TFT_WHITE); delay(1000);
    s_lcd.fillScreen(TFT_BLACK); delay(1000);
    s_lcd.fillScreen(TFT_RED);   delay(1000);
    s_lcd.fillScreen(TFT_GREEN); delay(1000);
    s_lcd.fillScreen(TFT_BLUE);  delay(1000);
    s_lcd.fillScreen(TFT_BLACK);
#endif

    // 调试 B —— 纯色 pushImage 通路自检
    // 验证：PSRAM 双缓冲 → cache 写回 → pushImage → DMA 整条链路
    // 期望：红 → 绿 → 蓝，三块均匀纯色（占 320×180，上下黑边）
    //   有横纹/噪点 → 传输层问题（cache 未写回，或 SPI 太快）
    //   颜色顺序错  → 解码端字节序不对（应为 RGB565_BIG_ENDIAN）
#if 0
    {
        const uint16_t kTestColors[3] = {0xF800, 0x07E0, 0x001F};  // 红 / 绿 / 蓝
        for (int c = 0; c < 3; ++c) {
            uint16_t* px = s_buf[0];
            const uint32_t total = static_cast<uint32_t>(kFrameW) * kFrameH;
            // 按大端填：内存里高字节在前，与 SPI 的发送顺序一致
            const uint16_t c16 = kTestColors[c];
            const uint16_t be = static_cast<uint16_t>((c16 >> 8) | (c16 << 8));
            for (uint32_t i = 0; i < total; ++i) {
                px[i] = be;
            }
#if defined(PET_HAVE_ROM_CACHE)
            Cache_WriteBack_Addr(reinterpret_cast<uint32_t>(s_buf[0]), kFrameBytes);
#endif
            s_lcd.fillScreen(TFT_BLACK);
            s_lcd.startWrite();
            s_lcd.pushImage(kFrameX, kFrameY, kFrameW, kFrameH, s_buf[0]);
            s_lcd.endWrite();
            delay(1500);
        }
        s_lcd.fillScreen(TFT_BLACK);
    }
#endif

    // ===== 开机画面（约 2 秒）=====
    // 上部：固件版本 + 编译日期时间，用来确认烧进去的到底是哪一版
    // 中部：打字机效果逐字打出"西米造物"（点阵见 boot_logo.h）
    s_lcd.fillScreen(TFT_BLACK);

    s_lcd.setTextColor(TFT_WHITE, TFT_BLACK);
    s_lcd.setTextSize(2);
    s_lcd.setCursor(12, 18);
    s_lcd.printf("FW %s", kFwVersion);

    s_lcd.setTextSize(1);
    s_lcd.setCursor(12, 46);
    s_lcd.print(__DATE__ "  " __TIME__);

    {
        constexpr int kGlyph   = pet::boot_logo::kGlyphSize;   // 32
        constexpr int kBaseX   = (kScreenW - kGlyph * pet::boot_logo::kGlyphCount) / 2;
        constexpr int kBaseY   = 128;
        constexpr int kCursorW = 10;
        constexpr int kCursorH = kGlyph - 12;

        // 打字机效果：每 350ms 落一个字，字右侧跟一个方块光标闪一下。
        // 每次都 waitDisplay()，确保这一帧真的推到屏上再进 delay，
        // 否则 SPI/DMA 里的数据可能攒到最后一刻才出去，看起来就是"一次性蹦出来"。
        for (int i = 0; i < pet::boot_logo::kGlyphCount; ++i) {
            const int cx = kBaseX + i * kGlyph;

            s_lcd.drawBitmap(cx, kBaseY, pet::boot_logo::kGlyphs[i],
                             kGlyph, kGlyph, TFT_WHITE);

            const int cursorX = cx + kGlyph + 2;
            s_lcd.fillRect(cursorX, kBaseY + 10, kCursorW, kCursorH, TFT_WHITE);
            s_lcd.waitDisplay();
            delay(220);

            s_lcd.fillRect(cursorX, kBaseY + 10, kCursorW, kCursorH, TFT_BLACK);
            s_lcd.waitDisplay();
            delay(130);
        }
    }

    delay(700);
    s_lcd.fillScreen(TFT_BLACK);

    s_mutex = xSemaphoreCreateMutex();
    s_sem = xSemaphoreCreateBinary();
    if (!s_mutex || !s_sem) {
        return false;
    }

    BaseType_t ok = xTaskCreatePinnedToCore(displayTask, "pet_display", kDisplayTaskStack,
                                            nullptr, kDisplayTaskPrio, &s_task, kDisplayCore);
    s_ready = (ok == pdPASS);
    return s_ready;
}

void end() {
    if (s_task) {
        vTaskDelete(s_task);
        s_task = nullptr;
    }
    for (uint8_t i = 0; i < kBufferCount; ++i) {
        if (s_buf[i]) {
            heap_caps_free(s_buf[i]);
            s_buf[i] = nullptr;
        }
    }
    s_ready = false;
}

uint16_t* acquireBack(uint32_t timeoutMs) {
    (void)timeoutMs;
    if (!s_ready) {
        return nullptr;
    }
    // 上一帧还没刷完 → 返回 nullptr，让上层丢帧（不排队，否则动画越播越慢）
    if (s_pending) {
        return nullptr;
    }
    return s_buf[1u - s_front];
}

void present() {
    if (!s_ready) {
        return;
    }
    if (xSemaphoreTake(s_mutex, portMAX_DELAY) != pdTRUE) {
        return;
    }
    s_front = static_cast<uint8_t>(1u - s_front);  // 交换前后缓冲
    s_pending = true;
    xSemaphoreGive(s_mutex);
    xSemaphoreGive(s_sem);
}

uint32_t framesShown() {
    return s_frames;
}

}  // namespace pet::display
