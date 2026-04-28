import machine
import time

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
