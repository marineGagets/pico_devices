import machine
import time
import _thread

# Piezo Speaker
class PiezoSpeaker:
    def __init__(self, pin):
        self.pin = machine.Pin(pin, machine.Pin.OUT)
        self.speaker = machine.PWM(self.pin)
        self.speaker.duty_u16(0)  # Start with speaker off

    def on(self, frequency):
        self.speaker.freq(frequency)
        self.speaker.duty_u16(32768)  # 50% Duty Cycle

    def off(self):
        self.speaker.duty_u16(0)  # Turn off the speaker

    def play_tone(self, frequency, duration, volume=0.5):
        if frequency == 0:
            self.speaker.duty_u16(0)
        else:
            self.speaker.freq(frequency)
            self.speaker.duty_u16(int(32768 * volume))  # Set duty cycle based on volume
        time.sleep(duration)
        self.speaker.duty_u16(0)  # Turn off


class DifferentialTone:
	def __init__(self, pin1, pin2):
		self.pin1 = machine.Pin(pin1, machine.Pin.OUT)
		self.pin2 = machine.Pin(pin2, machine.Pin.OUT)
		self._stop = False

	def play(self, freq_Hz, duration_ms):
		self._stop = False
		_thread.start_new_thread(self._run, (freq_Hz, duration_ms))

	def stop(self):
		self._stop = True

	def _run(self, freq_Hz, duration_ms):
		half_period_us = int(500_000 / freq_Hz)
		end_ms = time.ticks_add(time.ticks_ms(), duration_ms)
		while time.ticks_diff(end_ms, time.ticks_ms()) > 0 and not self._stop:
			self.pin1.on()
			self.pin2.off()
			time.sleep_us(half_period_us)
			self.pin1.off()
			self.pin2.on()
			time.sleep_us(half_period_us)
		self.pin1.off()
		self.pin2.off()

