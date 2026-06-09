// main.cpp - Parent demo program for pico_api_cppLib.
//
// Exercises each API library that lives in its own subfolder:
//   - ADC_api    (ADS1115 ADC cluster over I2C)
//   - SDCard_api (SD card block-level driver over SPI)
//   - LCD_api    (HD44780 16x2 LCD via PCF8574 I2C backpack)

#include "ADC_api.hpp"
#include "SDCard_api.hpp"
#include "LCD_api.hpp"

#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "hardware/spi.h"

#include <array>
#include <cstdio>
#include <cstring>

// Scan an I2C bus for responding devices and print the addresses found.
static void i2c_scan(i2c_inst_t* bus, const char* label) {
    printf("I2C scan on %s: ", label);
    int found = 0;
    for (uint8_t addr = 0x08; addr < 0x78; ++addr) {
        uint8_t rxdata = 0;
        // 0-byte writes are ambiguous on RP2040; use a 1-byte read instead.
        int r = i2c_read_blocking(bus, addr, &rxdata, 1, false);
        if (r >= 0) {
            printf("0x%02X ", addr);
            ++found;
        }
    }
    if (!found) printf("(no devices)");
    printf("\n");
}

// ---- I2C1 wiring (ADS1115) -----------------------------------------------
// main.py: SoftI2C(scl=Pin(11), sda=Pin(10)), ALERT/RDY=Pin(9).
static constexpr uint    I2C_SDA_PIN     = 10;
static constexpr uint    I2C_SCL_PIN     = 11;
static constexpr uint    I2C_BAUD_HZ     = 400'000;
static constexpr uint8_t ADS1115_ADDR    = 0x48;
static constexpr uint    ADS1115_IRQ_PIN = 9;

// ---- I2C0 wiring (HD44780 LCD via PCF8574) -------------------------------
// LCD on GP12/GP13 (i2c0 hardware pins on the RP2040), addr 0x27.
static constexpr uint    LCD_SDA_PIN  = 12;
static constexpr uint    LCD_SCL_PIN  = 13;
static constexpr uint    LCD_BAUD_HZ  = 400'000;
static constexpr uint8_t LCD_ADDR     = 0x27;
static constexpr uint8_t LCD_ROWS     = 2;
static constexpr uint8_t LCD_COLS     = 16;

// ---- SPI wiring (SD card) ------------------------------------------------
static constexpr uint    SD_SCK_PIN  = 18;
static constexpr uint    SD_MOSI_PIN = 19;
static constexpr uint    SD_MISO_PIN = 16;
static constexpr uint    SD_CS_PIN   = 17;
static constexpr uint32_t SD_BAUD_HZ = 12'500'000;

static void demo_adc(pico_api::ADCCluster& adc) {
    for (uint8_t ch = 0; ch < 4; ++ch) {
        int16_t raw = 0;
        if (adc.read_channel(ch, raw)) {
            printf("AIN%u: raw=%6d  V=%.4f\n",
                   ch, raw, adc.raw_to_volts(raw));
        } else {
            printf("AIN%u: read failed\n", ch);
        }
    }
}

static void demo_sdcard(pico_api::SDCard& sd) {
    static bool probed = false;
    static bool ok     = false;
    if (!probed) {
        probed = true;
        ok = sd.init();
        if (ok) {
            printf("SD: init OK, %lu sectors (%.1f MiB)\n",
                   static_cast<unsigned long>(sd.sector_count()),
                   sd.sector_count() / 2048.0f);
        } else {
            printf("SD: init failed (no card or wiring issue)\n");
        }
    }
    if (!ok) return;

    std::array<uint8_t, pico_api::SDCard::BLOCK_SIZE> buf{};
    if (sd.read_block(0, buf.data())) {
        printf("SD: block 0 first bytes: %02X %02X %02X %02X %02X %02X %02X %02X\n",
               buf[0], buf[1], buf[2], buf[3],
               buf[4], buf[5], buf[6], buf[7]);
    } else {
        printf("SD: read block 0 failed\n");
    }
}

int main() {
    stdio_init_all();

    // Give the host USB-CDC enumerator a moment to attach so the early
    // printf() lines aren't lost. ~3 s is plenty for a freshly-flashed Pico.
    sleep_ms(3000);
    printf("\n=== pico_api_cppLib demo boot ===\n");

    // ---- I2C1 for ADS1115 (GP10/GP11) ----
    i2c_init(i2c1, I2C_BAUD_HZ);
    gpio_set_function(I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(I2C_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(I2C_SDA_PIN);
    gpio_pull_up(I2C_SCL_PIN);

    pico_api::ADCCluster adc(i2c1, ADS1115_ADDR);
    adc.set_gain(pico_api::ADCCluster::Gain::FS_4_096V);

    // ---- I2C0 for LCD (GP12/GP13) ----
    i2c_init(i2c0, LCD_BAUD_HZ);
    gpio_set_function(LCD_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(LCD_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(LCD_SDA_PIN);
    gpio_pull_up(LCD_SCL_PIN);

    // Scan both buses BEFORE constructing the LCD - that way if the LCD
    // is mis-wired (or pins reversed) we find out from the scan instead of
    // the constructor hanging in i2c_write_blocking().
    i2c_scan(i2c1, "i2c1 (ADC, GP10/GP11)");
    i2c_scan(i2c0, "i2c0 (LCD, GP12/GP13)");

    pico_api::I2cLcd lcd(i2c0, LCD_ADDR, LCD_ROWS, LCD_COLS);

    // ---- SPI0 for SD card ----
    spi_init(spi0, pico_api::SDCard::INIT_BAUD_HZ);
    gpio_set_function(SD_SCK_PIN,  GPIO_FUNC_SPI);
    gpio_set_function(SD_MOSI_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SD_MISO_PIN, GPIO_FUNC_SPI);

    pico_api::SDCard sd(spi0, SD_CS_PIN, SD_BAUD_HZ);

    printf("pico_api_cppLib demo - ADC_api + SDCard_api + LCD_api\n");

    // Demo the printLCD scrolling helper at startup.
    lcd.printLCD("one");
    lcd.printLCD("two");
    lcd.printLCD("three");

    while (true) {
        demo_adc(adc);
        demo_sdcard(sd);
        printf("---\n");
        sleep_ms(1000);
    }
}
