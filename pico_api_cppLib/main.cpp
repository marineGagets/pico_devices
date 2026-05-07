// main.cpp - Parent demo program for pico_api_cppLib.
//
// Exercises each API library that lives in its own subfolder:
//   - ADC_api    (ADS1115 ADC cluster over I2C)
//   - SDCard_api (SD card block-level driver over SPI)

#include "ADC_api.hpp"
#include "SDCard_api.hpp"

#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "hardware/spi.h"

#include <array>
#include <cstdio>
#include <cstring>

// ---- I2C wiring (ADS1115) ------------------------------------------------
static constexpr uint    I2C_SDA_PIN     = 4;
static constexpr uint    I2C_SCL_PIN     = 5;
static constexpr uint    I2C_BAUD_HZ     = 400'000;
static constexpr uint8_t ADS1115_ADDR    = 0x48;
static constexpr uint    ADS1115_IRQ_PIN = 9;

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

    // ---- I2C0 for ADS1115 ----
    i2c_init(i2c0, I2C_BAUD_HZ);
    gpio_set_function(I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(I2C_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(I2C_SDA_PIN);
    gpio_pull_up(I2C_SCL_PIN);

    pico_api::ADCCluster adc(i2c0, ADS1115_ADDR);
    adc.set_gain(pico_api::ADCCluster::Gain::FS_4_096V);

    // ---- SPI0 for SD card ----
    spi_init(spi0, pico_api::SDCard::INIT_BAUD_HZ);
    gpio_set_function(SD_SCK_PIN,  GPIO_FUNC_SPI);
    gpio_set_function(SD_MOSI_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SD_MISO_PIN, GPIO_FUNC_SPI);

    pico_api::SDCard sd(spi0, SD_CS_PIN, SD_BAUD_HZ);

    printf("pico_api_cppLib demo - ADC_api + SDCard_api\n");

    while (true) {
        demo_adc(adc);
        demo_sdcard(sd);
        printf("---\n");
        sleep_ms(1000);
    }
}
