#include "ADC_api.hpp"

#include "hardware/gpio.h"
#include "pico/stdlib.h"

#include <array>

namespace pico_api {

namespace {
    // Single-ended MUX bits for AIN0..AIN3 (bits 14:12 of the config register).
    constexpr std::array<uint8_t, 4> MUX_BY_CHANNEL = {0x04, 0x05, 0x06, 0x07};

    // Full-scale voltage that corresponds to each Gain enumerator.
    float gain_to_fullscale(ADCCluster::Gain g) {
        switch (g) {
            case ADCCluster::Gain::FS_6_144V: return 6.144f;
            case ADCCluster::Gain::FS_4_096V: return 4.096f;
            case ADCCluster::Gain::FS_2_048V: return 2.048f;
            case ADCCluster::Gain::FS_1_024V: return 1.024f;
            case ADCCluster::Gain::FS_0_512V: return 0.512f;
            case ADCCluster::Gain::FS_0_256V: return 0.256f;
        }
        return 2.048f;
    }

    // Single instance pointer for the GPIO IRQ trampoline. The Pico SDK
    // GPIO IRQ callback has no user-data argument, so we route through
    // a file-scope pointer. Only one ADCCluster may use IRQs at a time.
    ADCCluster* g_irq_owner = nullptr;
}

ADCCluster::ADCCluster(i2c_inst_t* i2c, uint8_t addr, int irq_gpio)
    : _i2c(i2c), _addr(addr), _irq_gpio(irq_gpio)
{
    if (_irq_gpio >= 0) {
        gpio_init(static_cast<uint>(_irq_gpio));
        gpio_set_dir(static_cast<uint>(_irq_gpio), GPIO_IN);
        gpio_pull_up(static_cast<uint>(_irq_gpio));

        g_irq_owner = this;
        gpio_set_irq_enabled_with_callback(
            static_cast<uint>(_irq_gpio),
            GPIO_IRQ_EDGE_FALL,
            true,
            &ADCCluster::gpio_irq_trampoline);

        configure_alert_ready_mode();
    }
}

void ADCCluster::set_gain(Gain g) {
    _gain = g;
}

float ADCCluster::raw_to_volts(int16_t raw) const {
    return (static_cast<float>(raw) * gain_to_fullscale(_gain)) / 32767.0f;
}

bool ADCCluster::write_reg(uint8_t reg, uint16_t value) {
    uint8_t buf[3] = { reg,
                       static_cast<uint8_t>((value >> 8) & 0xFF),
                       static_cast<uint8_t>(value & 0xFF) };
    int n = i2c_write_blocking(_i2c, _addr, buf, 3, false);
    return n == 3;
}

bool ADCCluster::read_reg(uint8_t reg, uint16_t& value) {
    if (i2c_write_blocking(_i2c, _addr, &reg, 1, true) != 1) return false;
    uint8_t buf[2] = {0, 0};
    if (i2c_read_blocking(_i2c, _addr, buf, 2, false) != 2) return false;
    value = static_cast<uint16_t>((buf[0] << 8) | buf[1]);
    return true;
}

bool ADCCluster::read_channel(uint8_t channel, int16_t& out_raw) {
    if (channel > 3) return false;

    const uint16_t mux_bits = MUX_BY_CHANNEL[channel];
    const uint16_t pga_bits = static_cast<uint16_t>(_gain);

    const uint16_t config =
          0x8000                       // OS: start single conversion
        | (mux_bits << 12)             // MUX: channel select
        | (pga_bits << 9)              // PGA: full-scale range
        | 0x0100                       // MODE: single-shot
        | 0x0080                       // DR: 128 SPS
        | 0x0000;                      // COMP_QUE: assert ALERT after one conversion

    _conversion_ready    = false;
    _awaiting_conversion = (_irq_gpio >= 0);

    if (!write_reg(REG_CONFIG, config)) return false;

    if (_awaiting_conversion) {
        // Wait up to ~25 ms for ALERT/RDY edge.
        for (int t = 0; t < 25 && !_conversion_ready; ++t) {
            sleep_ms(1);
        }
        _awaiting_conversion = false;
        if (!_conversion_ready) return false;
    } else {
        // No IRQ pin: poll-friendly delay (>1/128 s).
        sleep_ms(9);
    }

    uint16_t raw = 0;
    if (!read_reg(REG_CONVERSION, raw)) return false;
    out_raw = static_cast<int16_t>(raw);
    return true;
}

void ADCCluster::configure_alert_ready_mode() {
    // ADS1115 conversion-ready mode: Lo_thresh MSB=0, Hi_thresh MSB=1.
    write_reg(REG_LO_THRESH, 0x0000);
    write_reg(REG_HI_THRESH, 0x8000);
}

void ADCCluster::monitor_channel(uint8_t channel) {
    if (channel > 3) return;
    _monitored_mask |= static_cast<uint8_t>(1u << channel);
}

void ADCCluster::stop_interrupt() {
    if (_irq_gpio >= 0) {
        gpio_set_irq_enabled(static_cast<uint>(_irq_gpio),
                             GPIO_IRQ_EDGE_FALL, false);
    }
    _monitored_mask    = 0;
    _last_crossed_mask = 0;
    _last_known_mask   = 0;
    if (g_irq_owner == this) g_irq_owner = nullptr;
}

void ADCCluster::service() {
    if (!_irq_pending) return;
    _irq_pending = false;
    check_threshold();
}

void ADCCluster::check_threshold() {
    if (_monitored_mask == 0) return;

    for (uint8_t ch = 0; ch < 4; ++ch) {
        const uint8_t bit = static_cast<uint8_t>(1u << ch);
        if ((_monitored_mask & bit) == 0) continue;

        int16_t value = 0;
        if (!read_channel(ch, value)) continue;

        if (!_have_threshold) {
            if (_callback) _callback(ch, value, 0);
            continue;
        }

        const bool crossed   = value >= _threshold;
        const bool was_known = (_last_known_mask & bit) != 0;
        const bool was_crossed = (_last_crossed_mask & bit) != 0;

        if (!was_known || crossed != was_crossed) {
            _last_known_mask |= bit;
            if (crossed) _last_crossed_mask |= bit;
            else         _last_crossed_mask &= static_cast<uint8_t>(~bit);

            if (_callback) _callback(ch, value, _threshold);
        }
    }
}

void ADCCluster::gpio_irq_trampoline(uint gpio, uint32_t /*events*/) {
    ADCCluster* self = g_irq_owner;
    if (!self) return;
    if (static_cast<int>(gpio) != self->_irq_gpio) return;

    if (self->_awaiting_conversion) {
        self->_conversion_ready = true;
        return;
    }
    self->_irq_pending = true;
}

} // namespace pico_api
