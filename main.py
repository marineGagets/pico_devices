import machine
from machine import Pin, SoftI2C
from utime import sleep
from cpu_temperature import CPU_Temperature 
from pico_LCD_I2c import I2cLcd
from piezo_SPKR import PiezoSpeaker
from ADC_api import ADCCluster


SysLED = Pin("LED", Pin.OUT) # GPIO25
PiezoSPKR = PiezoSpeaker(8) # GPIO8

# LCD display I2C pins
LCD_addr = 0x27
LCD_i2c = SoftI2C(scl=Pin(15), sda=Pin(14), freq=400000) # SCL=GPIO15, SDA=GPIO14
LCD = I2cLcd(LCD_i2c, LCD_addr, 2, 16) # 2 lines, 16 columns

# ADC Cluster 1 (4 channels) ADC1115 I2C address and pins
adc_cluster1_address = 0x48 
adc_cluster1_i2c = SoftI2C(scl=Pin(11), sda=Pin(10), freq=400000) 
adc_cluster1_irq = Pin(9, Pin.IN)  # ALERT/RDY is open-drain; pull-up also configured in ADC_api
# SCL=GPIO11, SDA=GPIO10

# multi-channel programable gain amplifier (PGA) gainamp2click
# SPI protocol
PGA8channel_address = 0x48
PGA8channel_CS_pin = 17
PGA8channel_SCK_pin = 18
PGA8channel_MOSI_pin = 16
PGA8channel_MISO_pin = 19
number_of_channels = 5  # channel 0 through channel 5


# SD card SPI pins
SD_CS_pin = 5
SD_SCK_pin = 6
SD_MOSI_pin = 7
SD_MISO_pin = 4

import sd_card as sdcard

"""
import uos
import vfs


# Setup SPI and CS
spi = machine.SPI(0, baudrate=1000000, polarity=0, phase=0, sck=SD_SCK_pin)

#     baudrate=1000000, polarity=0, phase=0, sck=machine.Pin(10), mosi=machine.Pin(11), miso=machine.Pin(12))
cs = machine.Pin(13, SD_CS_pin)

# Initialize SD Card
sd = sdcard.SDCard(spi, cs)
vfs = vfs.VfsFat(sd)
uos.mount(vfs, "/sd")

# Write Binary Data
data = bytes([0x00, 0x01, 0x02, 0x03, 0xFF])
with open("/sd/data.bin", "wb") as f:
    f.write(data)
print("Binary data written")

"""


import os
print("connecting to sd card... ")
sd_spi = machine.SPI(
    0,
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=machine.Pin(SD_SCK_pin),
    mosi=machine.Pin(SD_MOSI_pin),
    miso=machine.Pin(SD_MISO_pin),
)
sd_cs = machine.Pin(SD_CS_pin, machine.Pin.OUT)
sd = sdcard.SDCard(sd_spi, sd_cs)
os.mount(sd, '/sd')
print ("Read sd card directory: ")
print(os.listdir('/sd'))

'''
def test_irq(pin):
    print("IRQ fired!")

irq = Pin(9, Pin.IN, Pin.PULL_UP)
irq.irq(trigger=Pin.IRQ_FALLING, handler=test_irq)

# Now manually trigger a conversion without waiting
adc = ADCCluster(adc_cluster1_i2c, 0x48, irq_pin=irq, threshold=None, callback=test_irq)
# Don't use monitor_channel yet; just read manually to see if IRQ fires
try:
    val = adc.read_channel(0)
except OSError as e:
    print(f"Error: {e}")


def on_adc_threshold_alert(channel, value, threshold):
    """Callback when ADC value crosses threshold."""
    print(f"ADC Ch{channel} Alert! Value: {ADC_cluster1.raw_to_volts(value)}, Threshold: {threshold}")
    LCD.clear()
    LCD.putstr(f"ADC{channel}: {value}")
    sleep(1)
    PiezoSPKR.play_tone(2000, 0.5)  # 2kHz alert tone for 0.5 sec

# Initialize ADC cluster with GPIO9 IRQ monitoring (threshold=3000)
ADC_cluster1 = ADCCluster(adc_cluster1_i2c, adc_cluster1_address,
                          irq_pin=adc_cluster1_irq,
                          threshold=None, callback=on_adc_threshold_alert)

# Monitor channels 0 and 1
ADC_cluster1.monitor_channel(0)
ADC_cluster1.monitor_channel(1)
'''

from adc_api2 import SimpleADC

ADC_TYPE = "ads1115"  # "ads1115" or "internal"
ADC_ASYNC_BACKEND = "thread"  # "thread" or "uasyncio" (ADS1115 continuous mode only)
# Pass the existing SoftI2C object to avoid a conflicting second I2C instance on the same pins.
adc = SimpleADC(adc_type=ADC_TYPE, i2c=adc_cluster1_i2c, alert_pin=9)
if ADC_TYPE == "ads1115":
    adc.set_gain(4.096)
print("ADC initialized: {}".format(ADC_TYPE))


def test_internal_adcs(adc_obj, samples=5, interval_s=1):
    print("Testing Pico internal ADC channels...")
    print("CH0=GP26, CH1=GP27, CH2=GP28, CH3=TEMP_SENSOR_ADC")
    for index in range(samples):
        values = adc_obj.read_all_channels_volts()
        print(
            "Sample {}: CH0={:.3f}V  CH1={:.3f}V  CH2={:.3f}V  CH3={:.3f}V".format(
                index + 1,
                values[0],
                values[1],
                values[2],
                values[3],
            )
        )
        sleep(interval_s)


def test_ads1115_alert_status(adc_obj, samples=5, interval_s=1):
    print("Testing ADS1115 with ALERT pin status...")
    print("ALERT states: 0=LOW (asserted), 1=HIGH (idle)")
    for index in range(samples):
        print("Sample {}".format(index + 1))
        for channel in range(4):
            value_v = adc_obj.read_channel_volts(channel)
            alert_trace = adc_obj.get_last_alert_trace()
            print(
                "CH{}={:.3f}V  ALERT b/d/a/post={} / {} / {} / {}  seen_low={}  os_ready={}".format(
                    channel,
                    value_v,
                    alert_trace["before"],
                    alert_trace["during"],
                    alert_trace["after"],
                    alert_trace["post_read"],
                    alert_trace["seen_low"],
                    alert_trace["ready_by_os"],
                )
            )
        sleep(interval_s)


#from itertools import repeat

def benchmark_ads1115(adc_obj, total_samples=100):
    from utime import ticks_ms, ticks_diff
    print("Benchmarking ADS1115: {} sets of 4 channels...".format(total_samples))
    listOfData = []
    start = ticks_ms()
    progress_step = 10
    for i in range(total_samples):
        listOfData.append(adc_obj.read_all_channels_volts())
        if (i + 1) % progress_step == 0:
            x=1
 #           print("  Completed {} samples...".format(i + 1))    
    elapsed_ms = ticks_diff(ticks_ms(), start)
    rate = (total_samples * 4) / (elapsed_ms / 1000.0)
    print("Done. {} sets in {}ms  ({:.1f} total reads/sec,  {:.2f} ms/4-ch set)".format(
        total_samples, elapsed_ms, rate, elapsed_ms / total_samples
    ))


def _volts_cell_text(voltage):
    centivolts = int(voltage * 100 + 0.5)
    whole = centivolts // 100
    frac = centivolts % 100
    return "{}.{:02d}".format(whole, frac)


def _raw_cell_text(raw_value):
    return "{:04X}".format(raw_value & 0xFFFF)


def _write_adc_table(lcd, values, display_mode):
    if display_mode == "raw":
        lcd.move_to(0, 0)
        lcd.putstr("0:{} 1:{} ".format(
            _raw_cell_text(values[0]),
            _raw_cell_text(values[1]),
        ))
        lcd.move_to(0, 1)
        lcd.putstr("2:{} 3:{} ".format(
            _raw_cell_text(values[2]),
            _raw_cell_text(values[3]),
        ))
    else:
        lcd.move_to(0, 0)
        lcd.putstr("0:{} 1:{}   ".format(
            _volts_cell_text(values[0]),
            _volts_cell_text(values[1]),
        ))
        lcd.move_to(0, 1)
        lcd.putstr("2:{} 3:{}   ".format(
            _volts_cell_text(values[2]),
            _volts_cell_text(values[3]),
        ))


def _write_adc_stats(lcd, count, elapsed_ms, display_mode):
    if elapsed_ms > 0:
        sets_per_sec = count * 1000.0 / elapsed_ms
    else:
        sets_per_sec = 0
    lcd.move_to(0, 0)
    lcd.putstr("Sets:{:<10}".format(count))
    lcd.move_to(0, 1)
    lcd.putstr("Hz:{:<6.1f} {:4}".format(sets_per_sec, display_mode))
    return sets_per_sec


def read_continuous_ads1115(adc_obj, lcd, refresh_ms=100, display_mode="raw", stats_period_ms=1000):
    from utime import ticks_ms, ticks_diff, ticks_add, sleep_ms
    if not adc_obj.start_background(display_mode=display_mode, refresh_ms=refresh_ms,
                                     stats_period_ms=stats_period_ms):
        return
    # All LCD writes happen here on core 0; background thread only reads ADC.
    lcd.clear()
    start = ticks_ms()
    next_stats = ticks_add(start, stats_period_ms)
    _copy = [0, 0, 0, 0]  # pre-allocated copy buffer — no heap allocation in loop
    count = 0
    rate = 0
    print("ADC continuous display running. Press Ctrl+C to stop.")
    try:
        while adc_obj.is_background_running():
            src = adc_obj.get_latest_values()
            _copy[0] = src[0]
            _copy[1] = src[1]
            _copy[2] = src[2]
            _copy[3] = src[3]
            status = adc_obj.get_background_status()
            count = status["count"]
            rate = status["last_rate"]
            display_mode = status["display_mode"]
            now = ticks_ms()
            if ticks_diff(now, next_stats) >= 0:
                _write_adc_stats(lcd, count, ticks_diff(now, start), display_mode)
                next_stats = ticks_add(now, stats_period_ms)
            else:
                _write_adc_table(lcd, _copy, display_mode)
            sleep_ms(refresh_ms)
    except KeyboardInterrupt:
        adc_obj.stop_background()
        elapsed_ms = ticks_diff(ticks_ms(), start)
        _write_adc_stats(lcd, count, elapsed_ms, display_mode)
        print("\nStopped after {} sets in {}ms  ({:.1f} sets/sec)".format(
            count, elapsed_ms, rate
        ))


async def read_continuous_ads1115_async(adc_obj, lcd, refresh_ms=100, display_mode="raw", stats_period_ms=1000):
    import uasyncio as asyncio
    from utime import ticks_ms, ticks_diff, ticks_add
    if not await adc_obj.start_background_async(display_mode=display_mode, refresh_ms=refresh_ms,
                                                 stats_period_ms=stats_period_ms):
        return
    # All LCD writes happen here on core 0/task context; async worker only reads ADC.
    lcd.clear()
    start = ticks_ms()
    next_stats = ticks_add(start, stats_period_ms)
    _copy = [0, 0, 0, 0]
    count = 0
    rate = 0
    print("ADC continuous async display running. Press Ctrl+C to stop.")
    try:
        while adc_obj.is_background_running():
            src = adc_obj.get_latest_values()
            _copy[0] = src[0]
            _copy[1] = src[1]
            _copy[2] = src[2]
            _copy[3] = src[3]
            status = adc_obj.get_background_status()
            count = status["count"]
            rate = status["last_rate"]
            display_mode = status["display_mode"]
            now = ticks_ms()
            if ticks_diff(now, next_stats) >= 0:
                _write_adc_stats(lcd, count, ticks_diff(now, start), display_mode)
                next_stats = ticks_add(now, stats_period_ms)
            else:
                _write_adc_table(lcd, _copy, display_mode)
            await asyncio.sleep_ms(refresh_ms)
    except KeyboardInterrupt:
        pass
    finally:
        await adc_obj.stop_background_async(wait_ms=1000)
        elapsed_ms = ticks_diff(ticks_ms(), start)
        _write_adc_stats(lcd, count, elapsed_ms, display_mode)
        print("\nStopped after {} sets in {}ms  ({:.1f} sets/sec)".format(
            count, elapsed_ms, rate
        ))


def run_continuous_ads1115(adc_obj, lcd, refresh_ms=100, display_mode="raw", stats_period_ms=1000, async_backend="thread"):
    if async_backend == "thread":
        read_continuous_ads1115(adc_obj, lcd, refresh_ms=refresh_ms,
                                display_mode=display_mode,
                                stats_period_ms=stats_period_ms)
        return
    if async_backend == "uasyncio":
        import uasyncio as asyncio
        asyncio.run(read_continuous_ads1115_async(adc_obj, lcd, refresh_ms=refresh_ms,
                                                  display_mode=display_mode,
                                                  stats_period_ms=stats_period_ms))
        return
    raise ValueError("async_backend must be 'thread' or 'uasyncio'")


def SysLED_test(Duration=10):
    print("LED starts flashing...")
    while Duration > 0:
        try:
            SysLED.toggle()
            sleep(1) # sleep 1sec
            Duration -= 1
        except KeyboardInterrupt:
            break
    SysLED.off()
    print("Finished LED test.")


def LCD_test():
    print("LCD starts displaying...")
    LCD.putstr("Hello, World!")
    sleep(3)
    LCD.clear()
    LCD.putstr("Raspberry Pi Pico")
    sleep(3)
    LCD.clear()
    print("Finished LCD test.")


cpu_temp = CPU_Temperature()
print("CPU Temperature: {:.2f}°C".format(cpu_temp.temp()))

print("Starting SysLED test...")
SysLED_test()

print("Playing tone on Piezo Speaker...")
PiezoSPKR.play_tone(1000, 5, 0.5) # Play 1kHz tone for 5 seconds at full volume

'''
if __name__ == '__main__':
	tone = DifferentialTone(23, 24)
	thread = tone.play(5000, 500)
	print('After tone start')
	thread.join()
	print('After tone complete')
'''

print ("LCD test starting...")
LCD_test()

if ADC_TYPE == "internal":
    test_internal_adcs(adc)
else:
    print("ADS1115 backend:", ADC_ASYNC_BACKEND)
    run_continuous_ads1115(adc, LCD, refresh_ms=100, display_mode="raw",
                           stats_period_ms=1000, async_backend=ADC_ASYNC_BACKEND)

print("All tests completed. ADC background status:", adc.get_background_status())
