"""Temperature monitor"""

from machine import ADC


class CPU_Temperature:
    def __init__(self):
        self._sensor = ADC(4)
        self._conversion_factor = 3.3 / 65535

    def temp(self):
        reading = self._sensor.read_u16() * self._conversion_factor
        return 27 - (reading - 0.706) / 0.001721

