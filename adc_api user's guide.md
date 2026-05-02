# ADC API User's Guide

Raspberry Pi Pico — MicroPython  
Files: `adc_api2.py` (`SimpleADC`), `ADC_api.py` (`ADCCluster`)

---

## Contents

1. [Overview](#1-overview)
2. [Hardware Setup](#2-hardware-setup)
3. [SimpleADC — Quick Start](#3-simpleadc--quick-start)
4. [SimpleADC — Constructor](#4-simpleadc--constructor)
5. [SimpleADC — Synchronous Read Methods](#5-simpleadc--synchronous-read-methods)
6. [SimpleADC — Gain Control (ADS1115 only)](#6-simpleadc--gain-control-ads1115-only)
7. [SimpleADC — Threaded Background Sampling](#7-simpleadc--threaded-background-sampling)
8. [SimpleADC — uasyncio Background Sampling](#8-simpleadc--uasyncio-background-sampling)
9. [SimpleADC — Runtime Config Update](#9-simpleadc--runtime-config-update)
10. [SimpleADC — ALERT/RDY Diagnostics (ADS1115 only)](#10-simpleadc--alertrdy-diagnostics-ads1115-only)
11. [ADCCluster (Legacy API)](#11-adccluster-legacy-api)
12. [SD Card CSV Logging (main.py)](#12-sd-card-csv-logging-mainpy)
13. [Config Flags in main.py](#13-config-flags-in-mainpy)
14. [Threading Constraints](#14-threading-constraints)
15. [Error Reference](#15-error-reference)

---

## 1. Overview

| Class | File | Purpose |
|---|---|---|
| `SimpleADC` | `adc_api2.py` | Unified ADS1115 + Pico internal ADC with background sampling |
| `ADCCluster` | `ADC_api.py` | ADS1115-only, IRQ threshold callback, legacy use |

`SimpleADC` is the primary API. Use `ADCCluster` only when you need IRQ-driven threshold callbacks.

---

## 2. Hardware Setup

### ADS1115 (external 16-bit ADC)

| Signal | Pico GPIO |
|---|---|
| SDA | GP10 |
| SCL | GP11 |
| ALERT/RDY | GP9 (10 kΩ pull-up to 3.3 V) |
| ADDR (GND) | I²C address 0x48 |

I²C frequency: 400 kHz (`SoftI2C`).  
**One shared I²C instance** must be created in `main.py` and passed to `SimpleADC`. Never create a second `SoftI2C` on the same pins.

```python
from machine import Pin, SoftI2C
adc_i2c = SoftI2C(scl=Pin(11), sda=Pin(10), freq=400000)
```

### Pico Internal ADC

| Channel | GPIO / Source |
|---|---|
| ch0 | GP26 |
| ch1 | GP27 |
| ch2 | GP28 |
| ch3 | Internal temperature sensor |

No external wiring required.

---

## 3. SimpleADC — Quick Start

### ADS1115

```python
from machine import Pin, SoftI2C
from adc_api2 import SimpleADC

adc_i2c = SoftI2C(scl=Pin(11), sda=Pin(10), freq=400000)
adc = SimpleADC(adc_type="ads1115", i2c=adc_i2c, alert_pin=9)
adc.set_gain(4.096)

volts = adc.read_all_channels_volts()
print(volts)  # [ch0, ch1, ch2, ch3] in volts
```

### Pico Internal ADC

```python
from adc_api2 import SimpleADC

adc = SimpleADC(adc_type="internal")
volts = adc.read_all_channels_volts()
print(volts)
```

---

## 4. SimpleADC — Constructor

```python
SimpleADC(
    adc_type="ads1115",   # "ads1115" or "internal"
    address=0x48,         # ADS1115 I²C address (ignored for internal)
    i2c=None,             # Pass existing SoftI2C object (recommended)
    i2c_id=1,             # Hardware I²C ID if i2c=None (ads1115 only)
    sda_pin=10,           # SDA pin if i2c=None
    scl_pin=11,           # SCL pin if i2c=None
    alert_pin=9,          # ALERT/RDY GPIO number (ads1115 only)
    freq=400000,          # I²C frequency if i2c=None
)
```

**Always pass `i2c=` when sharing the bus with other devices.**  
If `i2c=None` a new hardware I²C instance is created internally.

---

## 5. SimpleADC — Synchronous Read Methods

All methods block until the conversion is complete.

| Method | Returns | Notes |
|---|---|---|
| `read_channel_raw(channel)` | `int` | Signed 16-bit for ADS1115; unsigned 16-bit for internal |
| `read_channel_volts(channel)` | `float` | Calls `raw_to_volts()` |
| `read_all_channels_raw()` | `list[int]` (reused) | All 4 channels; do not store the reference |
| `read_all_channels_volts()` | `list[float]` (reused) | All 4 channels; do not store the reference |
| `raw_to_volts(raw_count)` | `float` | Scale depends on active ADC type |

> **Reused list warning:** `read_all_channels_raw()` and `read_all_channels_volts()` return the same internal list every call to avoid heap allocation. Copy values immediately if you need to keep them.
>
> ```python
> raw = list(adc.read_all_channels_raw())  # safe copy
> ```

### Voltage scaling

| ADC type | Raw range | Formula |
|---|---|---|
| `ads1115` | −32768 … 32767 (signed) | `volts = (raw × gain) / 32767` |
| `internal` | 0 … 65535 (unsigned) | `volts = (raw × 3.3) / 65535` |

ADS1115 conversion uses a 25 ms timeout waiting for the ALERT/RDY falling edge. If the edge is not seen, the OS-ready bit is checked as a fallback before the result register is read.

---

## 6. SimpleADC — Gain Control (ADS1115 only)

Sets the PGA full-scale input range. Use the smallest range that covers your signal for best resolution.

```python
adc.set_gain(4.096)   # ±4.096 V full scale (~0.125 mV/LSB)
gain = adc.get_gain() # returns float
```

| `gain` value | Full-scale range | LSB size |
|---|---|---|
| 6.144 | ±6.144 V | ~0.1875 mV |
| 4.096 | ±4.096 V | ~0.125 mV |
| **2.048** | **±2.048 V (default)** | **~0.0625 mV** |
| 1.024 | ±1.024 V | ~0.03125 mV |
| 0.512 | ±0.512 V | ~0.015625 mV |
| 0.256 | ±0.256 V | ~0.0078125 mV |

> Do not exceed the supply voltage on ADS1115 inputs regardless of gain setting.

---

## 7. SimpleADC — Threaded Background Sampling

Runs continuous ADC reads on **core 1**. Core 0 (main thread) owns all display and I²C-LCD writes.

### Start

```python
started = adc.start_background(
    display_mode="raw",       # "raw" (int) or "volts" (float)
    refresh_ms=100,           # delay between read cycles (0 = no sleep)
    stats_period_ms=1000,     # informational; used by consumer
)
# Returns False if already running
```

### Poll latest values (core 0)

```python
if adc.is_background_running():
    values = adc.get_latest_values()       # [ch0, ch1, ch2, ch3] — copy, safe to keep
    ch2 = adc.get_latest_channel(2)        # single channel scalar

    status = adc.get_background_status()
    # {
    #   "running": bool,
    #   "count": int,           — total read cycles completed
    #   "last_rate": float,     — cycles per second
    #   "display_mode": str,
    #   "refresh_ms": int,
    #   "stats_period_ms": int,
    #   "mode": "thread",
    #   "uptime_ms": int,
    #   "error": str or None,
    # }
```

### Stop

```python
adc.stop_background()
# Signals the worker to exit; running flag clears after the current read cycle finishes.
```

### Update config at runtime (no restart needed)

```python
adc.update_background_config(
    display_mode="volts",
    refresh_ms=50,
    stats_period_ms=2000,
)
# None arguments keep the existing value unchanged.
```

### Full example — threaded display loop

```python
from utime import ticks_ms, ticks_diff, ticks_add, sleep_ms

adc.start_background(display_mode="raw", refresh_ms=100)
start = ticks_ms()

try:
    while adc.is_background_running():
        values = adc.get_latest_values()
        status = adc.get_background_status()
        print("Sets:", status["count"], "  Rate:", status["last_rate"])
        print(values)
        sleep_ms(200)
except KeyboardInterrupt:
    adc.stop_background()
```

---

## 8. SimpleADC — uasyncio Background Sampling

Requires MicroPython firmware with `uasyncio`. Functionally identical to the threaded mode but runs as a coroutine task instead of a core 1 thread.

```python
import uasyncio as asyncio

async def main():
    await adc.start_background_async(display_mode="volts", refresh_ms=100)

    for _ in range(50):
        values = adc.get_latest_values()
        print(values)
        await asyncio.sleep_ms(200)

    stopped = await adc.stop_background_async(wait_ms=1000)
    print("Stopped cleanly:", stopped)

asyncio.run(main())
```

### uasyncio-specific methods

| Method | Returns | Notes |
|---|---|---|
| `await start_background_async(display_mode, refresh_ms, stats_period_ms)` | `bool` | False if already running |
| `await stop_background_async(wait_ms=1000)` | `bool` | True if stopped within timeout |

`get_latest_values()`, `get_latest_channel()`, `get_background_status()`, `is_background_running()`, and `update_background_config()` behave identically in both modes.

---

## 9. SimpleADC — Runtime Config Update

```python
adc.update_background_config(
    display_mode="volts",   # change "raw" ↔ "volts" without restart
    refresh_ms=50,          # tighten read cadence
    stats_period_ms=None,   # None = keep current value
)
```

Takes effect on the next iteration of the worker loop. Safe to call from core 0 while the reader runs on core 1 (protected by internal lock).

---

## 10. SimpleADC — ALERT/RDY Diagnostics (ADS1115 only)

```python
level = adc.get_alert_status()
# Returns 0 (asserted/conversion ready) or 1 (idle)
# Returns None for internal ADC type

trace = adc.get_last_alert_trace()
# Returns dict from the most recent read_channel_raw() call:
# {
#   "before": int,   — ALERT level before starting conversion
#   "during": int,   — ALERT level after config write
#   "after":  int,   — ALERT level after conversion completes
# }
```

Use `get_last_alert_trace()` during bring-up to verify that ALERT/RDY is toggling correctly. If `before` and `after` are both 1 (high), the ALERT pin is wired correctly and the conversion-ready mode is active. If no falling edge is seen, check the 10 kΩ pull-up and the Lo/Hi threshold register configuration.

---

## 11. ADCCluster (Legacy API)

`ADC_api.py` — ADS1115 only, single-core, IRQ threshold callbacks.

### Constructor

```python
from ADC_api import ADCCluster

adc = ADCCluster(
    i2c,            # I²C bus object
    address,        # I²C address (0x48)
    irq_pin=None,   # Pin object for ALERT/RDY (optional)
    threshold=None, # int threshold; None fires callback on every IRQ event
    callback=None,  # fn(channel, value, threshold)
)
```

### Methods

| Method | Description |
|---|---|
| `set_gain(gain)` | Set PGA full-scale range (same values as SimpleADC) |
| `get_gain()` | Return current gain |
| `raw_to_volts(raw)` | Convert signed raw count to volts |
| `read_channel(channel)` | Blocking single-channel read (0–3) |
| `monitor_channel(channel)` | Add channel to IRQ-driven threshold check list |
| `unmonitor_channel(channel)` | Remove channel from monitoring list |
| `stop_interrupt()` | Disable IRQ handler |

### Threshold callback example

```python
def on_alert(channel, value, threshold):
    print("CH{} crossed {} raw ({} V)".format(
        channel, threshold, adc.raw_to_volts(value)
    ))

irq = Pin(9, Pin.IN)
adc = ADCCluster(adc_i2c, 0x48, irq_pin=irq, threshold=12000, callback=on_alert)
adc.monitor_channel(0)
adc.monitor_channel(1)
```

When `threshold=None`, the callback fires for every IRQ event regardless of value.

---

## 12. SD Card CSV Logging (main.py)

When `ADC_RUN_MODE = "log"`, `main.py` creates or replaces the log file on SD and writes one CSV row per sample set.

### CSV format

```
timestamp_raw,ch0_v,ch1_v,ch2_v,ch3_v
"<12345, [1024, -32, 4096, 8192]>",1.280012,0.000000,0.512001,1.024002
```

- `timestamp_raw` — quoted string containing the `ticks_ms()` timestamp and the four raw integer readings.
- `ch0_v` … `ch3_v` — floating-point voltages derived from `raw_to_volts()` at 6 decimal places.

The file is opened in write mode (`"w"`) so each run recreates it from scratch.

### Config flags

```python
ADC_RUN_MODE        = "log"           # "display" or "log"
ADC_LOG_FILE        = "/sd/adc_log.csv"
ADC_LOG_INTERVAL_MS = 100             # ms between sets (0 = as fast as possible)
ADC_LOG_MAX_SETS    = 0               # 0 = unlimited; N = stop after N sets
```

### Behaviour

- Every 10 sets the file is flushed to SD.
- `KeyboardInterrupt` (Ctrl+C) stops cleanly and flushes remaining data.
- When `ADC_LOG_MAX_SETS > 0` the logger exits automatically and prints total logged sets.

---

## 13. Config Flags in main.py

| Flag | Default | Options | Purpose |
|---|---|---|---|
| `ADC_TYPE` | `"ads1115"` | `"ads1115"`, `"internal"` | Select ADC hardware |
| `ADC_ASYNC_BACKEND` | `"thread"` | `"thread"`, `"uasyncio"` | Background sampler backend (display mode) |
| `ADC_RUN_MODE` | `"display"` | `"display"`, `"log"` | Run LCD display loop or SD CSV logger |
| `ADC_LOG_FILE` | `"/sd/adc_log.csv"` | Any SD path | CSV output file path |
| `ADC_LOG_INTERVAL_MS` | `100` | integer ≥ 0 | Logging interval in ms |
| `ADC_LOG_MAX_SETS` | `0` | 0 = unlimited, N > 0 | Auto-stop after N sets |

---

## 14. Threading Constraints

| Rule | Reason |
|---|---|
| LCD writes must happen on **core 0 only** | `pico_LCD_I2c.py` calls `gc.collect()` and allocates `bytes()` on every nibble write — unsafe from core 1 |
| Background worker must not call `I2cLcd` methods | See above |
| One `SoftI2C` instance per pin pair | Creating a second I²C on the same pins causes bus contention |
| `_thread.start_new_thread()` returns `None` | No handle; use `is_background_running()` to track state |
| Lock hold times are short | Lock is acquired only to read/write `_bg_state`; never held during I²C transactions |
| `uasyncio` and `_thread` cannot mix on core 1 | Choose one backend; never call `start_background()` and `start_background_async()` simultaneously |

---

## 15. Error Reference

| Exception | Source | Cause |
|---|---|---|
| `ValueError("adc_type must be 'ads1115' or 'internal'")` | `SimpleADC.__init__` | Invalid `adc_type` argument |
| `ValueError("Channel must be between 0 and 3")` | `read_channel_raw`, `get_latest_channel` | Channel out of range |
| `ValueError("Gain must be one of: ...")` | `set_gain` | Unsupported gain value |
| `ValueError("display_mode must be 'raw' or 'volts'")` | `start_background`, `update_background_config` | Invalid mode string |
| `RuntimeError("set_gain is only valid when adc_type='ads1115'")` | `set_gain` | Called on internal ADC instance |
| `RuntimeError("uasyncio is not available in this firmware")` | `start_background_async` | Firmware does not include `uasyncio` |
| `OSError("ADC conversion timeout waiting for ALERT/RDY")` | `ADCCluster.read_channel` | ALERT pin did not fall within 25 ms |
| Worker prints `"ADC worker error: ..."` | `_reader_worker` | Any exception inside core 1 thread; stored in `status["error"]` |
