# Usage:
# 1) Create I2C, IRQ pin, and ADCCluster
#    irq = Pin(9, Pin.IN)
#    adc = ADCCluster(i2c, 0x48, irq_pin=irq)
#
# 2) Optional: set ADS1115 PGA full-scale range (volts)
#    adc.set_gain(4.096)
#
# 3) Read a single channel (0-3)
#    value = adc.read_channel(0)
#
# 4) Optional: threshold callback monitoring on IRQ events
#    def on_alert(channel, value, threshold):
#        print("ADC{} crossed {} with {}".format(channel, threshold, value))
#
#    adc = ADCCluster(i2c, 0x48, irq_pin=irq, threshold=12000, callback=on_alert)
#    adc.monitor_channel(0)
#    adc.monitor_channel(1)
#
# 5) Stop IRQ monitoring when done
#    adc.stop_interrupt()

import micropython
from machine import Pin
from utime import sleep_ms

micropython.alloc_emergency_exception_buf(100)

class ADCCluster:
    # ADS1115 register pointers
    _REG_CONVERSION = 0x00
    _REG_CONFIG = 0x01
    _REG_LO_THRESH = 0x02
    _REG_HI_THRESH = 0x03

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

    def __init__(self, i2c, address, irq_pin=None, threshold=None, callback=None):
        """
        Initialize ADC Cluster with optional IRQ-based threshold callback.
        
        Args:
            i2c: I2C bus object
            address: I2C address of the ADC cluster
            irq_pin: GPIO Pin object connected to ADS1115 ALERT/RDY output.
            threshold: Value threshold to trigger callback. None triggers callback for every IRQ event.
            callback: Function to call when threshold is crossed: callback(channel, value, threshold)
        """
        self.i2c = i2c
        self.address = address
        self._irq_pin = irq_pin
        self._threshold = threshold
        self._callback = callback
        self._last_state = {}
        self._irq_pending = False
        self._awaiting_conversion = False
        self._conversion_ready = False
        self._monitored_channels = []
        self._pga_bits = self._PGA_GAIN_MAP[2.048]  # Default ADS1115 full-scale range
        self._gain = 2.048
        
        if self._irq_pin is not None:
            self._setup_interrupt()
            self._configure_alert_ready_mode()

    def set_gain(self, gain):
        """Set ADS1115 PGA full-scale range in volts."""
        if gain not in self._PGA_GAIN_MAP:
            raise ValueError("Gain must be one of: 6.144, 4.096, 2.048, 1.024, 0.512, 0.256")
        self._gain = gain
        self._pga_bits = self._PGA_GAIN_MAP[gain]

    def get_gain(self):
        """Return current ADS1115 PGA full-scale range in volts."""
        return self._gain

    def raw_to_volts(self, raw_count):
        """
        Convert raw ADC count to voltage using current gain setting.
        
        Args:
            raw_count: Raw 16-bit signed ADC value (-32768 to 32767)
        
        Returns:
            Voltage in volts (float)
        """
        return (raw_count * self._gain) / 32767.0

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
            | 0x0000  # COMP_QUE: assert ALERT after one conversion
        )

        self._conversion_ready = False
        self._awaiting_conversion = self._irq_pin is not None

        self.i2c.writeto(self.address, bytes([
            self._REG_CONFIG,
            (config >> 8) & 0xFF,
            config & 0xFF,
        ]))

        if self._awaiting_conversion:
            timeout_ms = 25
            while not self._conversion_ready and timeout_ms > 0:
                sleep_ms(1)
                timeout_ms -= 1
            self._awaiting_conversion = False
            if not self._conversion_ready:
                raise OSError("ADC conversion timeout waiting for ALERT/RDY")
        else:
            # Fallback when no IRQ pin is connected.
            sleep_ms(9)

        self.i2c.writeto(self.address, bytes([self._REG_CONVERSION]))
        data = self.i2c.readfrom(self.address, 2)
        value = int.from_bytes(data, 'big')
        if value > 32767:
            value -= 65536
        return value

    def _configure_alert_ready_mode(self):
        if self._irq_pin is None:
            return
        # Enable pull-up so open-drain ALERT/RDY pin idles high.
        self._irq_pin.init(Pin.IN, Pin.PULL_UP)
        # ADS1115 conversion-ready mode: Lo_thresh MSB=0, Hi_thresh MSB=1.
        self.i2c.writeto(self.address, bytes([
            self._REG_LO_THRESH,
            0x00,
            0x00,
        ]))
        self.i2c.writeto(self.address, bytes([
            self._REG_HI_THRESH,
            0x80,
            0x00,
        ]))

    def _setup_interrupt(self):
        """Set up GPIO IRQ and defer ADC reads out of the ISR."""
        if self._irq_pin is None:
            return
        self._irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=self._irq_handler)

    def _irq_handler(self, pin):
        if self._awaiting_conversion:
            self._conversion_ready = True
            return

        if self._irq_pending:
            return
        self._irq_pending = True
        try:
            micropython.schedule(self._scheduled_check, 0)
        except RuntimeError:
            self._irq_pending = False

    def _scheduled_check(self, _):
        self._check_threshold()
        self._irq_pending = False

    def _check_threshold(self):
        """Check monitored channels after an IRQ event and trigger callback."""
        threshold = self._threshold
        if not self._monitored_channels:
            return

        for channel in self._monitored_channels:
            try:
                value = self.read_channel(channel)
                if threshold is None:
                    if self._callback:
                        self._callback(channel, value, threshold)
                    continue

                crossed = value >= threshold
                
                if channel not in self._last_state or crossed != self._last_state[channel]:
                    self._last_state[channel] = crossed
                    if self._callback and crossed:
                        self._callback(channel, value, threshold)
            except:
                pass

    def monitor_channel(self, channel):
        """
        Add a channel to the interrupt monitoring list and trigger initial conversion.
        
        Args:
            channel: Channel number (0-3)
        """
        if channel < 0 or channel > 3:
            raise ValueError("Channel must be between 0 and 3")
        if channel not in self._monitored_channels:
            self._monitored_channels.append(channel)
        # Trigger initial conversion using fallback (sleep) path so IRQ wiring
        # is not required to complete the seed read that starts the IRQ chain.
        saved_irq_pin = self._irq_pin
        self._irq_pin = None
        try:
            self.read_channel(channel)
        finally:
            self._irq_pin = saved_irq_pin

    def unmonitor_channel(self, channel):
        """
        Remove a channel from the interrupt monitoring list.
        
        Args:
            channel: Channel number (0-3)
        """
        if channel in self._monitored_channels:
            self._monitored_channels.remove(channel)

    def stop_interrupt(self):
        """Disable IRQ monitoring."""
        if self._irq_pin:
            self._irq_pin.irq(handler=None)
