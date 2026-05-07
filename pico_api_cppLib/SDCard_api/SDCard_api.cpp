#include "SDCard_api.hpp"

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"

#include <cstring>

namespace pico_api {

namespace {
    constexpr int     CMD_TIMEOUT     = 100;

    constexpr uint8_t R1_IDLE_STATE       = 1u << 0;
    constexpr uint8_t R1_ILLEGAL_COMMAND  = 1u << 2;

    constexpr uint8_t TOKEN_CMD25         = 0xFC;
    constexpr uint8_t TOKEN_STOP_TRAN     = 0xFD;
    constexpr uint8_t TOKEN_DATA          = 0xFE;
}

SDCard::SDCard(spi_inst_t* spi, uint cs_gpio, uint32_t baud_hz)
    : _spi(spi), _cs(cs_gpio), _baud_hz(baud_hz)
{
    gpio_init(_cs);
    gpio_set_dir(_cs, GPIO_OUT);
    gpio_put(_cs, 1);
}

uint8_t SDCard::crc7(const uint8_t* buf, size_t n) {
    uint8_t crc = 0;
    for (size_t i = 0; i < n; ++i) {
        crc ^= buf[i];
        for (int j = 0; j < 8; ++j) {
            crc = static_cast<uint8_t>((crc << 1) ^ (0x12 * (crc >> 7)));
        }
    }
    return crc;
}

void SDCard::set_baud(uint32_t baud_hz) {
    spi_set_baudrate(_spi, baud_hz);
}

void SDCard::spi_write_byte(uint8_t b) {
    spi_write_blocking(_spi, &b, 1);
}

uint8_t SDCard::spi_read_byte() {
    uint8_t tx = 0xFF, rx = 0xFF;
    spi_write_read_blocking(_spi, &tx, &rx, 1);
    return rx;
}

void SDCard::spi_write(const uint8_t* buf, size_t n) {
    spi_write_blocking(_spi, buf, n);
}

void SDCard::spi_read(uint8_t* buf, size_t n) {
    // Clock out 0xFF for each byte to receive.
    spi_read_blocking(_spi, 0xFF, buf, n);
}

bool SDCard::init() {
    // 1) Initial low-speed SPI clocking with CS high to wake the card.
    set_baud(INIT_BAUD_HZ);
    cs_high();
    for (int i = 0; i < 16; ++i) spi_write_byte(0xFF);

    // 2) CMD0: go idle (allow up to 5 attempts).
    bool idle = false;
    for (int i = 0; i < 5; ++i) {
        if (cmd(0, 0) == R1_IDLE_STATE) { idle = true; break; }
    }
    if (!idle) return false;

    // 3) CMD8: ask for v2 voltage range / pattern.
    int r = cmd(8, 0x000001AA, 4);
    bool ok = false;
    if (r == R1_IDLE_STATE) {
        ok = init_card_v2();
    } else if (r == (R1_IDLE_STATE | R1_ILLEGAL_COMMAND)) {
        ok = init_card_v1();
    }
    if (!ok) return false;

    // 4) CMD9: read CSD to derive sector count.
    if (cmd(9, 0, 0, /*release=*/false) != 0) return false;
    uint8_t csd[16];
    if (!read_data(csd, sizeof(csd))) return false;

    if ((csd[0] & 0xC0) == 0x40) {
        // CSD v2.0 (SDHC/SDXC): C_SIZE in bits [69:48].
        uint32_t c_size =
              (static_cast<uint32_t>(csd[7]) << 16)
            | (static_cast<uint32_t>(csd[8]) <<  8)
            |  static_cast<uint32_t>(csd[9]);
        _sectors = (c_size + 1) * 1024;
    } else if ((csd[0] & 0xC0) == 0x00) {
        // CSD v1.0 (SDSC, <=2 GB).
        uint32_t c_size      = (static_cast<uint32_t>(csd[6] & 0x03) << 10)
                             | (static_cast<uint32_t>(csd[7]) << 2)
                             | (static_cast<uint32_t>(csd[8]) >> 6);
        uint32_t c_size_mult = static_cast<uint32_t>((csd[9] & 0x03) << 1)
                             | static_cast<uint32_t>(csd[10] >> 7);
        uint32_t read_bl_len = csd[5] & 0x0F;
        uint64_t capacity = (static_cast<uint64_t>(c_size + 1)
                          << (c_size_mult + 2 + read_bl_len));
        _sectors = static_cast<uint32_t>(capacity / BLOCK_SIZE);
    } else {
        return false;
    }

    // 5) CMD16: force 512-byte block length.
    if (cmd(16, BLOCK_SIZE) != 0) return false;

    // 6) Switch to run-mode baud.
    set_baud(_baud_hz);
    return true;
}

bool SDCard::init_card_v1() {
    for (int i = 0; i < CMD_TIMEOUT; ++i) {
        sleep_ms(50);
        cmd(55, 0);
        if (cmd(41, 0) == 0) {
            _cdv = BLOCK_SIZE; // SDSC: byte addressing
            return true;
        }
    }
    return false;
}

bool SDCard::init_card_v2() {
    for (int i = 0; i < CMD_TIMEOUT; ++i) {
        sleep_ms(50);
        cmd(58, 0, 4);
        cmd(55, 0);
        if (cmd(41, 0x40000000) == 0) {
            // Read OCR; bit 30 (CCS) tells us SDHC/SDXC vs SDSC.
            // Use cmd() with final<0 trick: store first response byte to _token.
            cmd(58, 0, -4);
            uint8_t ocr = _token;
            _cdv = (ocr & 0x40) ? 1u : BLOCK_SIZE;
            return true;
        }
    }
    return false;
}

int SDCard::cmd(uint8_t cmd_idx, uint32_t arg, int final, bool release, bool skip1) {
    cs_low();

    uint8_t buf[6];
    buf[0] = 0x40 | cmd_idx;
    buf[1] = static_cast<uint8_t>(arg >> 24);
    buf[2] = static_cast<uint8_t>(arg >> 16);
    buf[3] = static_cast<uint8_t>(arg >>  8);
    buf[4] = static_cast<uint8_t>(arg);
    buf[5] = static_cast<uint8_t>(crc7(buf, 5) | 0x01);
    spi_write(buf, 6);

    if (skip1) (void)spi_read_byte();

    for (int i = 0; i < CMD_TIMEOUT; ++i) {
        uint8_t response = spi_read_byte();
        if ((response & 0x80) == 0) {
            if (final < 0) {
                // Stash first trailing byte (used for OCR), discard the rest.
                _token = spi_read_byte();
                final = -1 - final;
            }
            for (int j = 0; j < final; ++j) spi_write_byte(0xFF);
            if (release) {
                cs_high();
                spi_write_byte(0xFF);
            }
            return response;
        }
    }

    // Timeout
    cs_high();
    spi_write_byte(0xFF);
    return -1;
}

bool SDCard::read_data(uint8_t* buf, size_t n) {
    cs_low();

    // Wait for the data start token.
    bool got_token = false;
    for (int i = 0; i < CMD_TIMEOUT; ++i) {
        uint8_t b = spi_read_byte();
        if (b == TOKEN_DATA) { got_token = true; break; }
        sleep_ms(1);
    }
    if (!got_token) {
        cs_high();
        return false;
    }

    spi_read(buf, n);

    // Discard 16-bit CRC.
    (void)spi_read_byte();
    (void)spi_read_byte();

    cs_high();
    spi_write_byte(0xFF);
    return true;
}

bool SDCard::write_data(uint8_t token, const uint8_t* buf, size_t n) {
    cs_low();

    spi_write_byte(token);
    spi_write(buf, n);
    spi_write_byte(0xFF);
    spi_write_byte(0xFF);

    // Data response: low 5 bits == 0b00101 means accepted.
    uint8_t resp = spi_read_byte();
    if ((resp & 0x1F) != 0x05) {
        cs_high();
        spi_write_byte(0xFF);
        return false;
    }

    // Wait while the card is busy (returns 0x00).
    while (spi_read_byte() == 0x00) { /* spin */ }

    cs_high();
    spi_write_byte(0xFF);
    return true;
}

bool SDCard::write_stop_token() {
    cs_low();
    spi_write_byte(TOKEN_STOP_TRAN);
    spi_write_byte(0xFF);
    while (spi_read_byte() == 0x00) { /* spin */ }
    cs_high();
    spi_write_byte(0xFF);
    return true;
}

bool SDCard::read_blocks(uint32_t block_num, uint8_t* buf, size_t nblocks) {
    if (nblocks == 0) return false;

    // Ensure MOSI idles high before starting (shared-bus workaround).
    spi_write_byte(0xFF);

    if (nblocks == 1) {
        if (cmd(17, block_num * _cdv, 0, /*release=*/false) != 0) {
            cs_high();
            return false;
        }
        return read_data(buf, BLOCK_SIZE);
    }

    if (cmd(18, block_num * _cdv, 0, /*release=*/false) != 0) {
        cs_high();
        return false;
    }
    for (size_t i = 0; i < nblocks; ++i) {
        if (!read_data(buf + i * BLOCK_SIZE, BLOCK_SIZE)) return false;
    }
    if (cmd(12, 0, 0, /*release=*/true, /*skip1=*/true) != 0) return false;
    return true;
}

bool SDCard::write_blocks(uint32_t block_num, const uint8_t* buf, size_t nblocks) {
    if (nblocks == 0) return false;

    spi_write_byte(0xFF);

    if (nblocks == 1) {
        if (cmd(24, block_num * _cdv) != 0) return false;
        return write_data(TOKEN_DATA, buf, BLOCK_SIZE);
    }

    if (cmd(25, block_num * _cdv) != 0) return false;
    for (size_t i = 0; i < nblocks; ++i) {
        if (!write_data(TOKEN_CMD25, buf + i * BLOCK_SIZE, BLOCK_SIZE)) return false;
    }
    return write_stop_token();
}

} // namespace pico_api
