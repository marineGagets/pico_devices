#include "LCD_api.hpp"

#include "pico/stdlib.h"

#include <cstdarg>
#include <cstdio>
#include <string>

namespace pico_api {

namespace {
    // PCF8574 -> HD44780 pin mapping (matches the MicroPython driver).
    constexpr uint8_t MASK_RS         = 0x01; // P0
    [[maybe_unused]] constexpr uint8_t MASK_RW = 0x02; // P1 (unused, kept for parity)
    constexpr uint8_t MASK_E          = 0x04; // P2
    constexpr uint8_t SHIFT_BACKLIGHT = 3;    // P3
    constexpr uint8_t SHIFT_DATA      = 4;    // P4-P7
}

// ---------------------------------------------------------------------------
// LCD_api (controller-level logic, bus-agnostic)
// ---------------------------------------------------------------------------

LCD_api::LCD_api(uint8_t num_lines, uint8_t num_columns)
    : _num_lines(num_lines > 4 ? 4 : num_lines),
      _num_columns(num_columns > 40 ? 40 : num_columns)
{}

void LCD_api::hal_sleep_us(uint32_t us) { sleep_us(us); }

void LCD_api::clear() {
    hal_write_command(LCD_CLR);
    hal_write_command(LCD_HOME);
    _cursor_x = 0;
    _cursor_y = 0;
}

void LCD_api::show_cursor() {
    hal_write_command(LCD_ON_CTRL | LCD_ON_DISPLAY | LCD_ON_CURSOR);
}

void LCD_api::hide_cursor() {
    hal_write_command(LCD_ON_CTRL | LCD_ON_DISPLAY);
}

void LCD_api::blink_cursor_on() {
    hal_write_command(LCD_ON_CTRL | LCD_ON_DISPLAY | LCD_ON_CURSOR | LCD_ON_BLINK);
}

void LCD_api::blink_cursor_off() {
    hal_write_command(LCD_ON_CTRL | LCD_ON_DISPLAY | LCD_ON_CURSOR);
}

void LCD_api::display_on() {
    hal_write_command(LCD_ON_CTRL | LCD_ON_DISPLAY);
}

void LCD_api::display_off() {
    hal_write_command(LCD_ON_CTRL);
}

void LCD_api::backlight_on() {
    _backlight = true;
    hal_backlight_on();
}

void LCD_api::backlight_off() {
    _backlight = false;
    hal_backlight_off();
}

void LCD_api::move_to(uint8_t col, uint8_t row) {
    _cursor_x = col;
    _cursor_y = row;
    uint8_t addr = col & 0x3f;
    if (row & 1) addr += 0x40;
    if (row & 2) addr += _num_columns;
    hal_write_command(LCD_DDRAM | addr);
}

void LCD_api::putchar(char ch) {
    if (ch == '\n') {
        if (!_implied_newline) {
            _cursor_x = _num_columns;
        }
    } else {
        hal_write_data(static_cast<uint8_t>(ch));
        _cursor_x += 1;
    }
    if (_cursor_x >= _num_columns) {
        _cursor_x = 0;
        _cursor_y += 1;
        _implied_newline = (ch != '\n');
    } else {
        _implied_newline = false;
    }
    if (_cursor_y >= _num_lines) {
        _cursor_y = 0;
    }
    move_to(_cursor_x, _cursor_y);
}

void LCD_api::putstr(std::string_view s) {
    for (char ch : s) putchar(ch);
}

void LCD_api::custom_char(uint8_t location, const uint8_t charmap[8]) {
    location &= 0x07;
    hal_write_command(LCD_CGRAM | (location << 3));
    hal_sleep_us(40);
    for (size_t i = 0; i < 8; ++i) {
        hal_write_data(charmap[i]);
        hal_sleep_us(40);
    }
    move_to(_cursor_x, _cursor_y);
}

void LCD_api::scrollLCD(std::string_view text,
                        uint8_t row, uint32_t step_ms, uint8_t tail_pad) {
    if (row >= _num_lines) row = 0;
    const uint8_t cols = _num_columns;

    // Build a padded buffer: `cols` leading blanks + text + `tail_pad` blanks.
    // Sliding a `cols`-wide window across this buffer makes the text enter
    // from the right and exit to the left.
    std::string buf;
    buf.reserve(text.size() + cols + tail_pad);
    buf.append(cols, ' ');
    buf.append(text.data(), text.size());
    buf.append(tail_pad, ' ');

    if (buf.size() < cols) buf.append(cols - buf.size(), ' ');

    const size_t frames = buf.size() - cols + 1;
    for (size_t f = 0; f < frames; ++f) {
        move_to(0, row);
        for (uint8_t i = 0; i < cols; ++i) putchar(buf[f + i]);
        hal_sleep_us(step_ms * 1000u);
    }
}

int LCD_api::printLCD(const char* fmt, ...) {
    char stack_buf[128];
    va_list ap;
    va_start(ap, fmt);
    int n = std::vsnprintf(stack_buf, sizeof stack_buf, fmt, ap);
    va_end(ap);
    if (n < 0) return n;

    std::string msg;
    if (static_cast<size_t>(n) < sizeof stack_buf) {
        msg.assign(stack_buf, static_cast<size_t>(n));
    } else {
        // Message larger than the stack buffer - reformat into a sized string.
        msg.resize(static_cast<size_t>(n));
        va_list ap2;
        va_start(ap2, fmt);
        std::vsnprintf(msg.data(), static_cast<size_t>(n) + 1, fmt, ap2);
        va_end(ap2);
    }

    clear();
    if (msg.size() <= _num_columns) {
        move_to(0, 0);
        putstr(msg);
        // Hold short messages briefly so they remain readable.
        hal_sleep_us(800u * 1000u);
    } else {
        scrollLCD(msg, 0, 250, _num_columns);
    }
    return n;
}

// ---------------------------------------------------------------------------
// I2cLcd (PCF8574 backpack HAL)
// ---------------------------------------------------------------------------

I2cLcd::I2cLcd(i2c_inst_t* i2c, uint8_t i2c_addr,
               uint8_t num_lines, uint8_t num_columns)
    : LCD_api(num_lines, num_columns), _i2c(i2c), _i2c_addr(i2c_addr)
{
    // Wake up the PCF8574.
    write_byte(0x00);
    sleep_ms(20);

    // Three resets per HD44780 init sequence.
    hal_write_init_nibble(LCD_FUNCTION_RESET);
    sleep_ms(5);
    hal_write_init_nibble(LCD_FUNCTION_RESET);
    sleep_ms(1);
    hal_write_init_nibble(LCD_FUNCTION_RESET);
    sleep_ms(1);

    // Switch to 4-bit mode.
    hal_write_init_nibble(LCD_FUNCTION);
    sleep_ms(1);

    // Now finish the standard init sequence (display off, clear, entry mode,
    // display on) - the LCD_api ctor in MicroPython did this; we emulate by
    // running the same commands here.
    uint8_t cmd = LCD_FUNCTION;
    if (num_lines > 1) cmd |= LCD_FUNCTION_2LINES;
    hal_write_command(cmd);

    display_off();
    backlight_on();
    clear();
    hal_write_command(LCD_ENTRY_MODE | LCD_ENTRY_INC);
    hide_cursor();
    display_on();
}

void I2cLcd::write_byte(uint8_t byte) {
    i2c_write_blocking(_i2c, _i2c_addr, &byte, 1, false);
}

void I2cLcd::hal_write_init_nibble(uint8_t nibble) {
    uint8_t byte = static_cast<uint8_t>(((nibble >> 4) & 0x0f) << SHIFT_DATA);
    write_byte(byte | MASK_E);
    write_byte(byte);
}

void I2cLcd::hal_backlight_on() {
    write_byte(static_cast<uint8_t>(1u << SHIFT_BACKLIGHT));
}

void I2cLcd::hal_backlight_off() {
    write_byte(0x00);
}

void I2cLcd::hal_write_command(uint8_t cmd) {
    uint8_t bl = _backlight ? (1u << SHIFT_BACKLIGHT) : 0u;
    uint8_t hi = static_cast<uint8_t>(bl | (((cmd >> 4) & 0x0f) << SHIFT_DATA));
    write_byte(hi | MASK_E);
    write_byte(hi);
    uint8_t lo = static_cast<uint8_t>(bl | ((cmd & 0x0f) << SHIFT_DATA));
    write_byte(lo | MASK_E);
    write_byte(lo);
    if (cmd <= 3) {
        // CLR / HOME need >= 4.1 ms.
        sleep_ms(5);
    }
}

void I2cLcd::hal_write_data(uint8_t data) {
    uint8_t bl = _backlight ? (1u << SHIFT_BACKLIGHT) : 0u;
    uint8_t hi = static_cast<uint8_t>(MASK_RS | bl | (((data >> 4) & 0x0f) << SHIFT_DATA));
    write_byte(hi | MASK_E);
    write_byte(hi);
    uint8_t lo = static_cast<uint8_t>(MASK_RS | bl | ((data & 0x0f) << SHIFT_DATA));
    write_byte(lo | MASK_E);
    write_byte(lo);
}

} // namespace pico_api
