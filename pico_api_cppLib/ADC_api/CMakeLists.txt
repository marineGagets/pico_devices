# ADC_api - ADS1115 4-channel I2C ADC wrapper
#
# Defines the static library `adc_api`. Other targets link with:
#     target_link_libraries(<your_target> PRIVATE adc_api)
# and #include "ADC_api.hpp".

add_library(adc_api STATIC
    ADC_api.cpp
)

target_include_directories(adc_api PUBLIC
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(adc_api PUBLIC
    pico_stdlib
    hardware_i2c
    hardware_gpio
)
