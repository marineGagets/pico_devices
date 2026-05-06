#pragma once

// ADC_api.hpp - C++ wrapper for the ADS1115 4-channel I2C ADC.
//
// Mirrors the MicroPython ADCCluster API:
//   - construct with i2c bus + 7-bit address (+ optional ALERT/RDY pin)
//   - set_gain() / get_gain() / raw_to_volts()
//   - read_channel(channel) for single-shot conversions on AIN0..AIN3
//   - threshold-based callback monitoring via ALERT/RDY (optional)

#include "hardware/i2c.h"
#include "pico/stdlib.h"

#include <cstdint>
#include <functional>

namespace pico_api {

class ADCCluster {
public:
    // ADS1115 PGA full-scale ranges (volts).
    enum class Gain : uint8_t {
        FS_6_144V = 0x00,
        FS_4_096V = 0x01,
        FS_2_048V = 0x02, // default
        FS_1_024V = 0x03,
        FS_0_512V = 0x04,
        FS_0_256V = 0x05,
    };

    // callback(channel, raw_value, threshold)
    using ThresholdCallback = std::function<void(uint8_t, int16_t, int16_t)>;

    // i2c:    initialised i2c_inst_t* (e.g. i2c0)
    // addr:   7-bit ADS1115 address (0x48..0x4B)
    // irq_gpio: ALERT/RDY pin, or -1 to disable IRQ-driven mode
    ADCCluster(i2c_inst_t* i2c, uint8_t addr, int irq_gpio = -1);

    // Set / query PGA full-scale range.
    void  set_gain(Gain g);
    Gain  get_gain() const { return _gain; }

    // Convert raw 16-bit signed count to volts using current gain.
    float raw_to_volts(int16_t raw) const;

    // Single-shot read of AIN0..AIN3. Returns true on success.
    bool  read_channel(uint8_t channel, int16_t& out_raw);

    // Threshold-callback monitoring (requires irq_gpio set in ctor).
    void  set_threshold(int16_t threshold) { _threshold = threshold; _have_threshold = true; }
    void  clear_threshold()                { _have_threshold = false; }
    void  set_callback(ThresholdCallback cb) { _callback = std::move(cb); }
    void  monitor_channel(uint8_t channel);
    void  stop_interrupt();

    // Pump pending IRQ-triggered work from the main loop.
    // (Call regularly when using monitor_channel().)
    void  service();

private:
    static constexpr uint8_t REG_CONVERSION = 0x00;
    static constexpr uint8_t REG_CONFIG     = 0x01;
    static constexpr uint8_t REG_LO_THRESH  = 0x02;
    static constexpr uint8_t REG_HI_THRESH  = 0x03;

    bool  write_reg(uint8_t reg, uint16_t value);
    bool  read_reg (uint8_t reg, uint16_t& value);

    void  configure_alert_ready_mode();
    void  check_threshold();

    static void gpio_irq_trampoline(uint gpio, uint32_t events);

    i2c_inst_t* _i2c;
    uint8_t     _addr;
    int         _irq_gpio;       // -1 if unused

    Gain        _gain            = Gain::FS_2_048V;

    ThresholdCallback _callback;
    int16_t     _threshold       = 0;
    bool        _have_threshold  = false;

    // monitored channel mask: bit n => AIN n
    uint8_t     _monitored_mask  = 0;
    uint8_t     _last_crossed_mask = 0;
    uint8_t     _last_known_mask   = 0;

    volatile bool _irq_pending          = false;
    volatile bool _conversion_ready     = false;
    bool          _awaiting_conversion  = false;
};

} // namespace pico_api
