#pragma once

// LCD_api.hpp - C++ wrapper for HD44780 character LCDs driven through a
// PCF8574 I2C backpack. Mirrors the MicroPython LCD_api / I2cLcd classes:
//   - construct with i2c bus + 7-bit PCF8574 address + dimensions
//   - clear(), move_to(col, row), putchar(), putstr()
//   - display/cursor/backlight controls
//   - custom_char(location, charmap[8]) for CGRAM glyphs

#include "hardware/i2c.h"
#include "pico/stdlib.h"

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace pico_api {

class LCD_api {
public:
    // HD44780 controller command set
    static constexpr uint8_t LCD_CLR             = 0x01;
    static constexpr uint8_t LCD_HOME            = 0x02;

    static constexpr uint8_t LCD_ENTRY_MODE      = 0x04;
    static constexpr uint8_t LCD_ENTRY_INC       = 0x02;
    static constexpr uint8_t LCD_ENTRY_SHIFT     = 0x01;

    static constexpr uint8_t LCD_ON_CTRL         = 0x08;
    static constexpr uint8_t LCD_ON_DISPLAY      = 0x04;
    static constexpr uint8_t LCD_ON_CURSOR       = 0x02;
    static constexpr uint8_t LCD_ON_BLINK        = 0x01;

    static constexpr uint8_t LCD_MOVE            = 0x10;
    static constexpr uint8_t LCD_MOVE_DISP       = 0x08;
    static constexpr uint8_t LCD_MOVE_RIGHT      = 0x04;

    static constexpr uint8_t LCD_FUNCTION        = 0x20;
    static constexpr uint8_t LCD_FUNCTION_8BIT   = 0x10;
    static constexpr uint8_t LCD_FUNCTION_2LINES = 0x08;
    static constexpr uint8_t LCD_FUNCTION_10DOTS = 0x04;
    static constexpr uint8_t LCD_FUNCTION_RESET  = 0x30;

    static constexpr uint8_t LCD_CGRAM           = 0x40;
    static constexpr uint8_t LCD_DDRAM           = 0x80;

    LCD_api(uint8_t num_lines, uint8_t num_columns);
    virtual ~LCD_api() = default;

    void clear();
    void show_cursor();
    void hide_cursor();
    void blink_cursor_on();
    void blink_cursor_off();
    void display_on();
    void display_off();
    void backlight_on();
    void backlight_off();
    void move_to(uint8_t col, uint8_t row);
    void putchar(char ch);
    void putstr(std::string_view s);
    void custom_char(uint8_t location, const uint8_t charmap[8]);

    // printf-style replacement that displays the formatted message on the
    // LCD. If the message fits on a single row it is shown for `dwell_ms`;
    // otherwise the message scrolls horizontally on row 0 until the entire
    // text has been shown. Returns the number of characters formatted.
    int printLCD(const char* fmt, ...) __attribute__((format(printf, 2, 3)));

    // Scroll an arbitrary string across row `row` of the LCD. `step_ms` is
    // the delay between scroll frames; `tail_pad` controls how many blank
    // columns trail off the end before the scroll completes.
    void scrollLCD(std::string_view text,
                   uint8_t  row      = 0,
                   uint32_t step_ms  = 250,
                   uint8_t  tail_pad = 16);

    uint8_t num_lines()   const { return _num_lines; }
    uint8_t num_columns() const { return _num_columns; }

protected:
    // HAL hooks: subclasses implement these for their bus.
    virtual void hal_write_command(uint8_t cmd) = 0;
    virtual void hal_write_data(uint8_t data)   = 0;
    virtual void hal_backlight_on()  {}
    virtual void hal_backlight_off() {}
    virtual void hal_sleep_us(uint32_t us);

    bool    _backlight = true;
    uint8_t _num_lines;
    uint8_t _num_columns;
    uint8_t _cursor_x = 0;
    uint8_t _cursor_y = 0;
    bool    _implied_newline = false;
};


// HD44780 LCD connected via a PCF8574 I2C backpack.
class I2cLcd : public LCD_api {
public:
    // i2c:        initialised i2c_inst_t*
    // i2c_addr:   7-bit PCF8574 address (commonly 0x27 or 0x3F)
    // num_lines:  1..4
    // num_columns:1..40
    I2cLcd(i2c_inst_t* i2c, uint8_t i2c_addr,
           uint8_t num_lines, uint8_t num_columns);

protected:
    void hal_write_command(uint8_t cmd) override;
    void hal_write_data(uint8_t data)   override;
    void hal_backlight_on()  override;
    void hal_backlight_off() override;

private:
    void write_byte(uint8_t byte);
    void hal_write_init_nibble(uint8_t nibble);

    i2c_inst_t* _i2c;
    uint8_t     _i2c_addr;
};

} // namespace pico_api
