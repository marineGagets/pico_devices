# LCD_api - HD44780 character LCD via PCF8574 I2C backpack
#
# Defines the static library `lcd_api`. Other targets link with:
#     target_link_libraries(<your_target> PRIVATE lcd_api)
# and #include "LCD_api.hpp".

add_library(lcd_api STATIC
    LCD_api.cpp
)

target_include_directories(lcd_api PUBLIC
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(lcd_api PUBLIC
    pico_stdlib
    hardware_i2c
    hardware_gpio
)
