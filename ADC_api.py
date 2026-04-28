# Usage:
# 1) Create I2C and ADCCluster
#    adc = ADCCluster(i2c, 0x48)
#
# 2) Optional: set ADS1115 PGA full-scale range (volts)
#    adc.set_gain(4.096)
#
# 3) Read a single channel (0-3)
#    value = adc.read_channel(0)
#
# 4) Optional: threshold callback monitoring
#    def on_alert(channel, value, threshold):
#        print("ADC{} crossed {} with {}".format(channel, threshold, value))
#
#    adc = ADCCluster(i2c, 0x48, threshold=12000, callback=on_alert, poll_interval=500)
#    adc.monitor_channel(0)
#    adc.monitor_channel(1)
#
# 5) Stop background monitoring when done
#    adc.stop_interrupt()

import machine
from machine import I2C, Timer
from utime import sleep, sleep_ms

class ADCCluster:
    # ADS1115 register pointers
    _REG_CONVERSION = 0x00
    _REG_CONFIG = 0x01

    # Single-ended channel MUX values for AIN0..AIN3
    _MUX_BY_CHANNEL = (0x04, 0x05, 0x06, 0x07)

    # PGA full-scale ranges in volts -> PGA bits (11:9)
    _PGA_GAIN_MAP = {
        6.144: 0x00,
        4.096: 0x01,
        2.048: 0x02,
        1.024: 0x03,
        0.512: 0x04,
        0.256: 0x05,
    }

    def __init__(self, i2c, address, threshold=None, callback=None, poll_interval=1000):
        """
        Initialize ADC Cluster with optional interrupt on threshold.
        
        Args:
            i2c: I2C bus object
            address: I2C address of the ADC cluster
            threshold: Value threshold to trigger callback. None = no interrupt.
            callback: Function to call when threshold is crossed: callback(channel, value, threshold)
            poll_interval: Polling interval in milliseconds (default 1000ms)
        """
        self.i2c = i2c
        self.address = address
        self._threshold = threshold
        self._callback = callback
        self._poll_interval = poll_interval
        self._last_state = {}
        self._timer = None
        self._monitored_channels = []
        self._pga_bits = self._PGA_GAIN_MAP[2.048]  # Default ADS1115 full-scale range
        self._gain = 2.048
        
        if threshold is not None and callback is not None:
            self._setup_interrupt()

    def set_gain(self, gain):
        """Set ADS1115 PGA full-scale range in volts."""
        if gain not in self._PGA_GAIN_MAP:
            raise ValueError("Gain must be one of: 6.144, 4.096, 2.048, 1.024, 0.512, 0.256")
        self._gain = gain
        self._pga_bits = self._PGA_GAIN_MAP[gain]

    def get_gain(self):
        """Return current ADS1115 PGA full-scale range in volts."""
        return self._gain

    def read_channel(self, channel):
        if channel < 0 or channel > 3:
            raise ValueError("Channel must be between 0 and 3")

        # Build single-shot config for ADS1115 and start conversion.
        mux_bits = self._MUX_BY_CHANNEL[channel]
        config = (
            0x8000  # OS: start single conversion
            | (mux_bits << 12)  # MUX: channel select
            | (self._pga_bits << 9)  # PGA: full-scale range
            | 0x0100  # MODE: single-shot
            | 0x0080  # DR: 128 SPS
            | 0x0003  # COMP_QUE: disable comparator
        )

        self.i2c.writeto(self.address, bytes([
            self._REG_CONFIG,
            (config >> 8) & 0xFF,
            config & 0xFF,
        ]))

        # 128 SPS needs up to ~7.8ms for one conversion.
        sleep_ms(9)

        self.i2c.writeto(self.address, bytes([self._REG_CONVERSION]))
        data = self.i2c.readfrom(self.address, 2)
        value = int.from_bytes(data, 'big')
        if value > 32767:
            value -= 65536
        return value

    def _setup_interrupt(self):
        """Set up timer-based polling to check value threshold."""
        self._timer = Timer(-1)
        self._timer.init(period=self._poll_interval, mode=Timer.PERIODIC, callback=self._check_threshold)

    def _check_threshold(self, timer):
        """Check if any monitored channel crosses threshold and trigger callback."""
        threshold = self._threshold
        if threshold is None:
            return

        for channel in self._monitored_channels:
            try:
                value = self.read_channel(channel)
                crossed = value >= threshold
                
                if channel not in self._last_state or crossed != self._last_state[channel]:
                    self._last_state[channel] = crossed
                    if self._callback and crossed:
                        self._callback(channel, value, threshold)
            except:
                pass

    def monitor_channel(self, channel):
        """Add a channel to the interrupt monitoring list."""
        if channel not in self._monitored_channels and 0 <= channel <= 3:
            self._monitored_channels.append(channel)

    def unmonitor_channel(self, channel):
        """Remove a channel from the interrupt monitoring list."""
        if channel in self._monitored_channels:
            self._monitored_channels.remove(channel)

    def stop_interrupt(self):
        """Stop the threshold monitoring interrupt."""
        if self._timer:
            self._timer.deinit()
            self._timer = None
