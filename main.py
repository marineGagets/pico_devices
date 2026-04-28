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
# SCL=GPIO11, SDA=GPIO10

# multi-channel programable gain amplifier (PGA) gainamp2click
# SPI protocol
PGA8channel_address = 0x48
PGA8channel_CS_pin = 17
PGA8channel_SCK_pin = 18
PGA8channel_MOSI_pin = 16
PGA8channel_MISO_pin = 19
number_of_channels = 5  # channel 0 through channel 5




def on_adc_threshold_alert(channel, value, threshold):
    """Callback when ADC value crosses threshold."""
    print(f"ADC Ch{channel} Alert! Value: {value}, Threshold: {threshold}")
    LCD.clear()
    LCD.putstr(f"ADC{channel}: {value}")
    sleep(1)
    PiezoSPKR.play_tone(2000, 0.5)  # 2kHz alert tone for 0.5 sec

# Initialize ADC cluster with interrupt monitoring (threshold=3000, poll every 500ms)
ADC_cluster1 = ADCCluster(adc_cluster1_i2c, adc_cluster1_address, 
                          threshold=3000, callback=on_adc_threshold_alert, 
                          poll_interval=500)

# Monitor channels 0 and 1
ADC_cluster1.monitor_channel(0)
ADC_cluster1.monitor_channel(1)



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
PiezoSPKR.play_tone(1000, 5, 1.0) # Play 1kHz tone for 5 seconds at full volume

print ("LCD test starting...")
LCD_test()

print("All tests completed.")
