// main.cpp - Parent demo program for pico_api_cppLib.
//
// Exercises each API library that lives in its own subfolder.
// First API: ADC_api (ADS1115 ADC cluster over I2C).

#include "ADC_api.hpp"

#include "pico/stdlib.h"
#include "hardware/i2c.h"
#include <cstdio>

// ---- I2C wiring (adjust to your board) ----
static constexpr uint   I2C_SDA_PIN     = 4;
static constexpr uint   I2C_SCL_PIN     = 5;
static constexpr uint   I2C_BAUD_HZ     = 400'000;
static constexpr uint8_t ADS1115_ADDR   = 0x48;
static constexpr uint   ADS1115_IRQ_PIN = 9;

int main() {
    stdio_init_all();

    // Bring up I2C0 on the configured pins.
    i2c_init(i2c0, I2C_BAUD_HZ);
    gpio_set_function(I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(I2C_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(I2C_SDA_PIN);
    gpio_pull_up(I2C_SCL_PIN);

    // Construct the ADC cluster (no IRQ pin in this minimal demo).
    pico_api::ADCCluster adc(i2c0, ADS1115_ADDR);
    adc.set_gain(pico_api::ADCCluster::Gain::FS_4_096V);

    printf("pico_api_cppLib demo - ADC_api\n");

    while (true) {
        for (uint8_t ch = 0; ch < 4; ++ch) {
            int16_t raw = 0;
            if (adc.read_channel(ch, raw)) {
                printf("AIN%u: raw=%6d  V=%.4f\n",
                       ch, raw, adc.raw_to_volts(raw));
            } else {
                printf("AIN%u: read failed\n", ch);
            }
        }
        printf("---\n");
        sleep_ms(1000);
    }
}
