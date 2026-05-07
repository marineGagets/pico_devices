# SDCard_api - SD card block-level driver over SPI
#
# Defines the static library `sdcard_api`. Other targets link with:
#     target_link_libraries(<your_target> PRIVATE sdcard_api)
# and #include "SDCard_api.hpp".

add_library(sdcard_api STATIC
    SDCard_api.cpp
)

target_include_directories(sdcard_api PUBLIC
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(sdcard_api PUBLIC
    pico_stdlib
    hardware_spi
    hardware_gpio
)
