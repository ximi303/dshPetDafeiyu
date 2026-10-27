#include "display.h"

#include <cstring>

#include <Arduino.h>
#include <LovyanGFX.hpp>

#include <esp_heap_caps.h>
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
    lgfx::Light_PWM    _light;

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
            cfg.invert = true;
            cfg.rgb_order = false;      // 偏色就翻这个
            cfg.dlen_16bit = false;
            cfg.bus_shared = true;
            _panel.config(cfg);
        }
        {
            auto cfg = _light.config();
            cfg.pin_bl = kPinBl;
            cfg.invert = false;
            cfg.freq = 44100;
            cfg.pwm_channel = 7;
            _light.config(cfg);
            _panel.setLight(&_light);
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

        // 整帧 DMA 推出去，别用逐像素画点
        s_lcd.startWrite();
        s_lcd.pushImage(kFrameX, kFrameY, kFrameW, kFrameH, s_buf[idx]);
        s_lcd.endWrite();

        s_frames++;
        s_pending = false;
    }
}

bool begin() {
    s_lcd.init();
    s_lcd.setRotation(1);       // 240×320 → 320×240 横屏
    s_lcd.setBrightness(255);
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
