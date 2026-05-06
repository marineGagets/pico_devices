import _thread
from machine import I2C, Pin, ADC
from utime import sleep_ms, ticks_ms, ticks_us, ticks_add, ticks_diff


class SimpleADC:
	"""
	Unified ADC API for Raspberry Pi Pico.

	Use `adc_type="ads1115"` for external ADS1115 or
	`adc_type="internal"` for Pico internal ADC channels.

	ADS1115 default wiring:
	- SDA: GP10
	- SCL: GP11
	- ALERT/RDY: GP9 (with external 10k pull-up)

	Internal ADC channel mapping:
	- ch0 -> GP26
	- ch1 -> GP27
	- ch2 -> GP28
	- ch3 -> internal temperature sensor ADC channel
	"""

	_REG_CONVERSION = 0x00
	_REG_CONFIG = 0x01
	_REG_LO_THRESH = 0x02
	_REG_HI_THRESH = 0x03

	_MUX_BY_CHANNEL = (0x04, 0x05, 0x06, 0x07)

	# Full-scale voltage range -> PGA bits
	_PGA_GAIN_MAP = {
		6.144: 0x00,
		4.096: 0x01,
		2.048: 0x02,
		1.024: 0x03,
		0.512: 0x04,
		0.256: 0x05,
	}

	def __init__(
		self,
		adc_type="ads1115",
		address=0x48,
		i2c=None,
		i2c_id=1,
		sda_pin=10,
		scl_pin=11,
		alert_pin=9,
		freq=400000,
	):
		if adc_type not in ("ads1115", "internal"):
			raise ValueError("adc_type must be 'ads1115' or 'internal'")

		self.adc_type = adc_type

		# Gain applies only to ADS1115. Internal ADC uses fixed 3.3V full-scale.
		self._gain = 2.048
		self._pga_bits = self._PGA_GAIN_MAP[self._gain]

		if self.adc_type == "ads1115":
			self.address = address
			# Use provided I2C object if given, otherwise create hardware I2C.
			if i2c is not None:
				self.i2c = i2c
			else:
				self.i2c = I2C(i2c_id, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=freq)
			self.alert = Pin(alert_pin, Pin.IN)
			self._alert_fired = False
			self.alert.irq(trigger=Pin.IRQ_FALLING, handler=self._alert_handler)
			self._configure_alert_ready_mode()
			self._last_alert_trace = {
				"before": self.alert.value(),
				"during": self.alert.value(),
				"after": self.alert.value(),
			}
		else:
			self._internal_adcs = (ADC(26), ADC(27), ADC(28), ADC(4))
			self._last_alert_trace = {"before": None, "during": None, "after": None}

		# Pre-allocate reusable buffers — avoids heap allocation on every read.
		self._config_buf = bytearray(3)  # [reg, high_byte, low_byte]
		self._reg_buf = bytearray(1)     # [reg_pointer]
		self._read_buf = bytearray(2)    # raw conversion bytes
		self._raw_buf = [0, 0, 0, 0]     # reused by read_all_channels_raw
		self._volts_buf = [0.0, 0.0, 0.0, 0.0]  # reused by read_all_channels_volts

		# Background reader state — shared between core 0 and core 1.
		self._bg_lock = _thread.allocate_lock()
		self._bg_state = {
			"running": False,
			"stop": False,
			"count": 0,
			"start_ms": 0,
			"last_rate": 0,
			"refresh_ms": 100,
			"stats_period_ms": 1000,
			"display_mode": "raw",
			"mode": "none",
			"error": None,
			"values": [0, 0, 0, 0],
			"updated_seq": 0,
		}
		self._async_task = None

	def get_alert_status(self):
		"""Return current ALERT pin level (0/1). Valid for ADS1115 mode only."""
		if self.adc_type != "ads1115":
			return None
		return self.alert.value()

	def get_last_alert_trace(self):
		"""Return ALERT status captured before/during/after the last ADS1115 conversion."""
		return self._last_alert_trace

	def _alert_handler(self, pin):
		"""IRQ handler: called on falling edge of ALERT/RDY pin."""
		self._alert_fired = True

	def _configure_alert_ready_mode(self):
		"""Set ADS1115 ALERT/RDY output to conversion-ready mode."""
		# Use immutable literals — no heap allocation.
		self.i2c.writeto(self.address, b'\x02\x00\x00')
		self.i2c.writeto(self.address, b'\x03\x80\x00')

	def _read_register_u16(self, reg_addr):
		"""Read a 16-bit ADS1115 register value using pre-allocated buffers."""
		self._reg_buf[0] = reg_addr
		self.i2c.writeto(self.address, self._reg_buf)
		self.i2c.readfrom_into(self.address, self._read_buf)
		return (self._read_buf[0] << 8) | self._read_buf[1]

	def set_gain(self, gain):
		"""Set ADS1115 full-scale range (volts): 6.144, 4.096, 2.048, 1.024, 0.512, 0.256."""
		if self.adc_type != "ads1115":
			raise RuntimeError("set_gain is only valid when adc_type='ads1115'")
		if gain not in self._PGA_GAIN_MAP:
			raise ValueError("Gain must be one of: 6.144, 4.096, 2.048, 1.024, 0.512, 0.256")
		self._gain = gain
		self._pga_bits = self._PGA_GAIN_MAP[gain]

	def get_gain(self):
		"""Return current ADS1115 full-scale range in volts."""
		if self.adc_type != "ads1115":
			raise RuntimeError("get_gain is only valid when adc_type='ads1115'")
		return self._gain

	def raw_to_volts(self, raw_count):
		"""
		Convert raw ADC value to volts using active ADC type scaling.

		ADS1115: signed 16-bit (-32768..32767), scaled by gain.
		Internal: unsigned 16-bit (0..65535), scaled by 3.3V reference.
		"""
		if self.adc_type == "ads1115":
			return (raw_count * self._gain) / 32767.0
		return (raw_count * 3.3) / 65535.0

	def read_channel_raw(self, channel):
		"""Read one channel (0-3) and return raw ADC value for active ADC type."""
		if channel < 0 or channel > 3:
			raise ValueError("Channel must be between 0 and 3")

		if self.adc_type == "internal":
			return self._internal_adcs[channel].read_u16()

		mux_bits = self._MUX_BY_CHANNEL[channel]

		# Single-shot conversion, 128 SPS.
		# COMP_QUE bits [1:0] = 0b00 (0x0000) = assert ALERT after one conversion.
		# Hi_thresh MSB=1 / Lo_thresh MSB=0 set in _configure_alert_ready_mode().
		config = (
			0x8000          # OS: start single conversion
			| (mux_bits << 12)  # MUX: channel select
			| (self._pga_bits << 9)  # PGA: full-scale range
			| 0x0100        # MODE: single-shot
			| 0x0080        # DR: 128 SPS
			| 0x0000        # COMP_QUE: assert after one conversion (bits 1:0 = 00)
		)

		before_status = self.alert.value()
		self._alert_fired = False  # Clear flag before starting conversion

		self._config_buf[0] = self._REG_CONFIG
		self._config_buf[1] = (config >> 8) & 0xFF
		self._config_buf[2] = config & 0xFF
		self.i2c.writeto(self.address, self._config_buf)
		during_status = self.alert.value()

		# Wait for IRQ handler to set _alert_fired flag (ALERT falling edge).
		timeout_ms = 25
		deadline_us = ticks_add(ticks_us(), timeout_ms * 1000)
		while not self._alert_fired and ticks_diff(deadline_us, ticks_us()) > 0:
			pass

		seen_alert_low = self._alert_fired
		during_status = self.alert.value()

		# OS bit (config bit 15) is 1 when single-shot conversion is complete.
		config_status = self._read_register_u16(self._REG_CONFIG)
		ready_by_os = 1 if (config_status & 0x8000) else 0

		after_status = self.alert.value()

		self._reg_buf[0] = self._REG_CONVERSION
		self.i2c.writeto(self.address, self._reg_buf)
		self.i2c.readfrom_into(self.address, self._read_buf)
		value = (self._read_buf[0] << 8) | self._read_buf[1]
		if value > 32767:
			value -= 65536
		return value

	def read_channel_volts(self, channel):
		"""Read one channel and return float voltage."""
		return self.raw_to_volts(self.read_channel_raw(channel))

	def read_all_channels_raw(self):
		"""Read channels 0..3 and return reused list of raw ADC values."""
		for ch in range(4):
			self._raw_buf[ch] = self.read_channel_raw(ch)
		return self._raw_buf

	def read_all_channels_volts(self):
		"""Read channels 0..3 and return reused list of float voltages."""
		for ch in range(4):
			self._volts_buf[ch] = self.read_channel_volts(ch)
		return self._volts_buf


	def start_background(self, display_mode="raw", refresh_ms=100, stats_period_ms=1000):
		"""Start background ADC sampling on core 1. Returns False if already running."""
		if display_mode not in ("raw", "volts"):
			raise ValueError("display_mode must be 'raw' or 'volts'")
		self._bg_lock.acquire()
		try:
			if self._bg_state["running"]:
				print("ADC background reader already running.")
				return False
			self._bg_state["running"] = True
			self._bg_state["stop"] = False
			self._bg_state["count"] = 0
			self._bg_state["start_ms"] = ticks_ms()
			self._bg_state["last_rate"] = 0
			self._bg_state["display_mode"] = display_mode
			self._bg_state["refresh_ms"] = refresh_ms
			self._bg_state["stats_period_ms"] = stats_period_ms
			self._bg_state["mode"] = "thread"
			self._bg_state["error"] = None
			self._bg_state["updated_seq"] = 0
		finally:
			self._bg_lock.release()
		_thread.start_new_thread(self._reader_worker, ())
		print("ADC background reader starting: mode={}".format(display_mode))
		return True

	def stop_background(self):
		"""Signal the background reader to stop. Returns False if not running."""
		self._bg_lock.acquire()
		try:
			if not self._bg_state["running"]:
				print("ADC background reader is not running.")
				return False
			self._bg_state["stop"] = True
		finally:
			self._bg_lock.release()
		print("ADC background reader stop requested.")
		return True

	def get_background_status(self):
		"""Return a snapshot dict of the background reader state."""
		now_ms = ticks_ms()
		self._bg_lock.acquire()
		try:
			s = self._bg_state
			uptime_ms = 0
			if s["running"] and s["start_ms"]:
				uptime_ms = ticks_diff(now_ms, s["start_ms"])
			return {
				"running": s["running"],
				"count": s["count"],
				"last_rate": s["last_rate"],
				"display_mode": s["display_mode"],
				"refresh_ms": s["refresh_ms"],
				"stats_period_ms": s["stats_period_ms"],
				"mode": s["mode"],
				"uptime_ms": uptime_ms,
				"error": s["error"],
			}
		finally:
			self._bg_lock.release()

	def get_background_stats(self):
		"""Alias for get_background_status() to provide a clearer stats API."""
		return self.get_background_status()

	def is_background_running(self):
		"""Return True if a background reader is active."""
		self._bg_lock.acquire()
		try:
			return self._bg_state["running"]
		finally:
			self._bg_lock.release()

	def get_latest_values(self):
		"""Return a copy of latest 4-channel values produced by background sampling."""
		self._bg_lock.acquire()
		try:
			src = self._bg_state["values"]
			return [src[0], src[1], src[2], src[3]]
		finally:
			self._bg_lock.release()

	def get_latest_channel(self, channel):
		"""Return latest background value for one channel (0-3)."""
		if channel < 0 or channel > 3:
			raise ValueError("Channel must be between 0 and 3")
		self._bg_lock.acquire()
		try:
			return self._bg_state["values"][channel]
		finally:
			self._bg_lock.release()

	def update_background_config(self, display_mode=None, refresh_ms=None, stats_period_ms=None):
		"""Update running background reader settings without restart."""
		self._bg_lock.acquire()
		try:
			if display_mode is not None:
				if display_mode not in ("raw", "volts"):
					raise ValueError("display_mode must be 'raw' or 'volts'")
				self._bg_state["display_mode"] = display_mode
			if refresh_ms is not None:
				if refresh_ms < 0:
					raise ValueError("refresh_ms must be >= 0")
				self._bg_state["refresh_ms"] = refresh_ms
			if stats_period_ms is not None:
				if stats_period_ms < 0:
					raise ValueError("stats_period_ms must be >= 0")
				self._bg_state["stats_period_ms"] = stats_period_ms
		finally:
			self._bg_lock.release()

	def _require_uasyncio(self):
		try:
			import uasyncio as asyncio
			return asyncio
		except ImportError:
			raise RuntimeError("uasyncio is not available in this firmware")

	async def start_background_async(self, display_mode="raw", refresh_ms=100, stats_period_ms=1000):
		"""Start background ADC sampling as a uasyncio task. Returns False if already running."""
		if display_mode not in ("raw", "volts"):
			raise ValueError("display_mode must be 'raw' or 'volts'")
		asyncio = self._require_uasyncio()
		self._bg_lock.acquire()
		try:
			if self._bg_state["running"]:
				print("ADC background reader already running.")
				return False
			self._bg_state["running"] = True
			self._bg_state["stop"] = False
			self._bg_state["count"] = 0
			self._bg_state["start_ms"] = ticks_ms()
			self._bg_state["last_rate"] = 0
			self._bg_state["display_mode"] = display_mode
			self._bg_state["refresh_ms"] = refresh_ms
			self._bg_state["stats_period_ms"] = stats_period_ms
			self._bg_state["mode"] = "uasyncio"
			self._bg_state["error"] = None
			self._bg_state["updated_seq"] = 0
		finally:
			self._bg_lock.release()
		self._async_task = asyncio.create_task(self._reader_async_worker())
		await asyncio.sleep_ms(0)
		print("ADC async background reader starting: mode={}".format(display_mode))
		return True

	async def stop_background_async(self, wait_ms=1000):
		"""Request stop and wait until async background reader exits or timeout expires."""
		asyncio = self._require_uasyncio()
		self.stop_background()
		deadline = ticks_add(ticks_ms(), wait_ms)
		while self.is_background_running() and ticks_diff(deadline, ticks_ms()) > 0:
			await asyncio.sleep_ms(10)
		if self.is_background_running():
			return False
		return True

	def _get_bg_flag(self, name):
		self._bg_lock.acquire()
		try:
			return self._bg_state[name]
		finally:
			self._bg_lock.release()

	def _reader_worker(self):
		"""Core 1 worker: reads ADC into _bg_state['values']. No LCD access."""
		from utime import ticks_ms, ticks_diff
		start = ticks_ms()
		shared = self._bg_state["values"]
		try:
			count = 0
			while True:
				self._bg_lock.acquire()
				stop = self._bg_state["stop"]
				display_mode = self._bg_state["display_mode"]
				refresh_ms = self._bg_state["refresh_ms"]
				self._bg_lock.release()
				if stop:
					break
				if display_mode == "raw":
					values = self.read_all_channels_raw()
				else:
					values = self.read_all_channels_volts()
				count += 1
				elapsed_ms = ticks_diff(ticks_ms(), start)
				self._bg_lock.acquire()
				try:
					shared[0] = values[0]
					shared[1] = values[1]
					shared[2] = values[2]
					shared[3] = values[3]
					self._bg_state["count"] = count
					self._bg_state["updated_seq"] += 1
					if elapsed_ms > 0:
						self._bg_state["last_rate"] = (count * 1000.0) / elapsed_ms
				finally:
					self._bg_lock.release()
				if refresh_ms > 0:
					sleep_ms(refresh_ms)
		except Exception as exc:
			print("ADC worker error:", exc)
			self._bg_lock.acquire()
			self._bg_state["error"] = str(exc)
			self._bg_lock.release()
		finally:
			self._bg_lock.acquire()
			self._bg_state["running"] = False
			self._bg_state["stop"] = False
			self._bg_state["mode"] = "none"
			self._bg_lock.release()

	async def _reader_async_worker(self):
		"""uasyncio worker: reads ADC in task context and updates shared background values."""
		asyncio = self._require_uasyncio()
		start = ticks_ms()
		shared = self._bg_state["values"]
		try:
			count = 0
			while True:
				self._bg_lock.acquire()
				stop = self._bg_state["stop"]
				display_mode = self._bg_state["display_mode"]
				refresh_ms = self._bg_state["refresh_ms"]
				self._bg_lock.release()
				if stop:
					break
				if display_mode == "raw":
					values = self.read_all_channels_raw()
				else:
					values = self.read_all_channels_volts()
				count += 1
				elapsed_ms = ticks_diff(ticks_ms(), start)
				self._bg_lock.acquire()
				try:
					shared[0] = values[0]
					shared[1] = values[1]
					shared[2] = values[2]
					shared[3] = values[3]
					self._bg_state["count"] = count
					self._bg_state["updated_seq"] += 1
					if elapsed_ms > 0:
						self._bg_state["last_rate"] = (count * 1000.0) / elapsed_ms
				finally:
					self._bg_lock.release()
				if refresh_ms > 0:
					await asyncio.sleep_ms(refresh_ms)
				else:
					await asyncio.sleep_ms(0)
		except Exception as exc:
			print("ADC async worker error:", exc)
			self._bg_lock.acquire()
			self._bg_state["error"] = str(exc)
			self._bg_lock.release()
		finally:
			self._bg_lock.acquire()
			self._bg_state["running"] = False
			self._bg_state["stop"] = False
			self._bg_state["mode"] = "none"
			self._bg_lock.release()
			self._async_task = None


# Example:
# adc = SimpleADC(adc_type="ads1115")
# adc.set_gain(4.096)
# volts = adc.read_all_channels_volts()
# print(volts)
#
# adc_internal = SimpleADC(adc_type="internal")
# volts_internal = adc_internal.read_all_channels_volts()
# print(volts_internal)
