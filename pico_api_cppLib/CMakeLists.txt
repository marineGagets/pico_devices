cmake_minimum_required(VERSION 3.13)

# ----------------------------------------------------------------------------
# Board selection
#   Default board is "pico". Build for Pico W with:  -DPICO_BOARD=pico_w
# ----------------------------------------------------------------------------
if(NOT DEFINED PICO_BOARD)
    set(PICO_BOARD "pico" CACHE STRING "Target board (pico, pico_w, pico2, pico2_w)")
endif()

# Pull in the Pico SDK (must come before project())
include(pico_sdk_import.cmake)

project(pico_api_cppLib
    VERSION     0.2.0
    DESCRIPTION "C++ API library for Raspberry Pi Pico / Pico W"
    LANGUAGES   C CXX ASM
)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Initialise the Pico SDK
pico_sdk_init()

# ----------------------------------------------------------------------------
# Per-API subfolders. Add a new line here for each new API.
# ----------------------------------------------------------------------------
add_subdirectory(ADC_api)
add_subdirectory(SDCard_api)
add_subdirectory(LCD_api)

# ----------------------------------------------------------------------------
# Parent demo executable (main.cpp at project root).
# Links every API library so main.cpp can exercise them.
# ----------------------------------------------------------------------------
add_executable(pico_api_demo
    main.cpp
)

target_link_libraries(pico_api_demo PRIVATE
    adc_api
    sdcard_api
    lcd_api
)

# Pico W: link the CYW43 driver if you need the on-board LED.
if(PICO_BOARD STREQUAL "pico_w" OR PICO_BOARD STREQUAL "pico2_w")
    target_link_libraries(pico_api_demo PRIVATE pico_cyw43_arch_none)
    target_compile_definitions(pico_api_demo PRIVATE PICO_API_HAS_CYW43=1)
endif()

# Enable USB stdio, disable UART stdio (change to taste)
pico_enable_stdio_usb(pico_api_demo  1)
pico_enable_stdio_uart(pico_api_demo 0)

# Generate UF2, BIN, HEX, MAP outputs
pico_add_extra_outputs(pico_api_demo)
