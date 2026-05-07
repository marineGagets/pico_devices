# pico_api_cppLib

A C++17 library and demo executable for the Raspberry Pi **Pico** and **Pico W**, built on the official [pico-sdk](https://github.com/raspberrypi/pico-sdk).

## Layout

Each API lives in its own subfolder and builds as a small static library.
`main.cpp` at the project root is the parent demo program that links every
API library and exercises them.

```
pico_api_cppLib/
├── CMakeLists.txt
├── pico_sdk_import.cmake
├── main.cpp                # parent demo (pico_api_demo)
├── ADC_api/                # first API: ADS1115 4-ch I2C ADC
│   ├── CMakeLists.txt
│   ├── ADC_api.hpp
│   └── ADC_api.cpp
├── SDCard_api/             # SD card block driver over SPI
│   ├── CMakeLists.txt
│   ├── SDCard_api.hpp
│   └── SDCard_api.cpp
├── pico-sdk/               # vendored Pico SDK (gitignored, see Prerequisites)
└── .vscode/                # CMake Tools + cortex-debug settings
```

### Adding a new API

1. Create a new folder, e.g. `PWM_api/`, with `<name>.hpp`, `<name>.cpp`,
   and a `CMakeLists.txt` that defines a static library target.
2. In the top-level `CMakeLists.txt`, add `add_subdirectory(PWM_api)` and
   `target_link_libraries(pico_api_demo PRIVATE pwm_api)`.
3. Include and use the new API from `main.cpp`.

## Prerequisites

Install once on your machine:

- **ARM GCC toolchain** — `arm-none-eabi-gcc`, `arm-none-eabi-g++`, `arm-none-eabi-gdb`
- **CMake** ≥ 3.13
- **Ninja** (recommended generator)
- **Python 3** (used by some SDK build steps)
- VS Code extensions: *CMake Tools*, *C/C++*, and (optional) *Cortex-Debug*

You also need the Pico SDK. This repo includes a local shallow clone at
`pico-sdk/` (excluded from git via `.gitignore`). Pick one of:

1. **Use the bundled local clone** (default once present): point CMake at it
   by setting `PICO_SDK_PATH` to the absolute path of `pico-sdk/` in this
   repo, e.g. in PowerShell:
   ```powershell
   $env:PICO_SDK_PATH = "$PWD\pico-sdk"
   ```
   Or set it in `.vscode/settings.json` under `cmake.environment`.
2. **Use a system-wide SDK clone** by setting `PICO_SDK_PATH` to that path.
3. **Let CMake fetch it** by setting `PICO_SDK_FETCH_FROM_GIT=ON` (legacy
   fallback in `pico_sdk_import.cmake`).

> Note: the bundled `pico-sdk/` is a shallow clone **without submodules**.
> Submodules (`btstack`, `cyw43-driver`, `lwip`, `mbedtls`, `tinyusb`) are
> only required for Wi-Fi/Bluetooth/USB features. Fetch them on demand:
> ```powershell
> cd pico-sdk
> git submodule update --init --depth 1 lib/tinyusb        # USB stack
> git submodule update --init --depth 1 lib/cyw43-driver   # Pico W Wi-Fi/BT
> git submodule update --init --depth 1 lib/lwip           # TCP/IP
> ```

## Build

### From VS Code

1. Open this folder (or the multi-root workspace).
2. CMake Tools will prompt for a kit — pick **Pico ARM GCC (pico)** or **Pico ARM GCC (pico_w)**.
3. Run **CMake: Configure**, then **CMake: Build**.

### From the command line (PowerShell)

```powershell
# Pico
cmake -S . -B build -G Ninja -DPICO_BOARD=pico
cmake --build build

# Pico W
cmake -S . -B build-w -G Ninja -DPICO_BOARD=pico_w
cmake --build build-w
```

The build produces `build/pico_api_demo.uf2`. Hold BOOTSEL, plug in the board, and copy the `.uf2` to the **RPI-RP2** drive.

## Switching between Pico and Pico W

Either:

- Pick a different CMake kit in VS Code (defined in `.vscode/cmake-kits.json`), or
- Re-run CMake configure with `-DPICO_BOARD=pico_w`.

The library detects Pico W at configure time and links `pico_cyw43_arch_none`, so `pico_api::set_onboard_led()` works on both boards.
