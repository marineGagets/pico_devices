#pragma once

// SDCard_api.hpp - C++ SPI driver for SD / SDHC / SDXC cards.
//
// Block-level interface, ported from the MicroPython sdcard.py driver:
//   - construct with an initialised spi_inst_t* + CS GPIO
//   - init() probes the card (CMD0/CMD8/ACMD41/CMD9/CMD16) and sets
//     byte vs block addressing automatically
//   - read_blocks() / write_blocks() operate on 512-byte sectors
//
// This driver does NOT include a filesystem layer; pair it with FatFs
// (or similar) if you need files and directories.

#include "hardware/spi.h"
#include "pico/stdlib.h"

#include <cstddef>
#include <cstdint>

namespace pico_api {

class SDCard {
public:
    static constexpr size_t   BLOCK_SIZE      = 512;
    static constexpr uint32_t INIT_BAUD_HZ    =   400'000;  // CMD0..ACMD41
    static constexpr uint32_t DEFAULT_BAUD_HZ = 1'320'000;  // run-mode

    // spi:       initialised spi_inst_t* (e.g. spi0). The driver re-inits
    //            the bus baud rate during card init and after init() returns.
    // cs_gpio:   chip-select GPIO (driver configures it as output)
    // baud_hz:   target run-mode SPI baud rate
    SDCard(spi_inst_t* spi, uint cs_gpio, uint32_t baud_hz = DEFAULT_BAUD_HZ);

    // Probe and initialise the card. Returns true on success.
    // Safe to call again after a card swap.
    bool init();

    // Number of 512-byte sectors reported by the card (valid after init()).
    uint32_t sector_count() const { return _sectors; }

    // Read / write contiguous 512-byte blocks. nblocks must be >= 1.
    // Returns true on success.
    bool read_blocks (uint32_t block_num, uint8_t* buf, size_t nblocks);
    bool write_blocks(uint32_t block_num, const uint8_t* buf, size_t nblocks);

    // Convenience single-block helpers.
    bool read_block (uint32_t block_num, uint8_t*       buf) { return read_blocks (block_num, buf, 1); }
    bool write_block(uint32_t block_num, const uint8_t* buf) { return write_blocks(block_num, buf, 1); }

private:
    // SPI helpers ------------------------------------------------------------
    void cs_low()  { gpio_put(_cs, 0); }
    void cs_high() { gpio_put(_cs, 1); }
    void set_baud(uint32_t baud_hz);

    void     spi_write_byte(uint8_t b);
    uint8_t  spi_read_byte();                              // sends 0xFF
    void     spi_write(const uint8_t* buf, size_t n);
    void     spi_read (uint8_t* buf, size_t n);            // sends 0xFF per byte

    // Card protocol ----------------------------------------------------------
    // Send a command. final = number of trailing data bytes to consume.
    // If release is true, CS is raised after the command. Returns the R1
    // response byte (0..0xFF) or -1 on timeout.
    int  cmd(uint8_t cmd_idx, uint32_t arg, int final = 0,
             bool release = true, bool skip1 = false);

    bool init_card_v1();
    bool init_card_v2();
    bool read_data (uint8_t* buf, size_t n);               // wait token + read
    bool write_data(uint8_t token, const uint8_t* buf, size_t n);
    bool write_stop_token();

    static uint8_t crc7(const uint8_t* buf, size_t n);

    // State ------------------------------------------------------------------
    spi_inst_t* _spi;
    uint        _cs;
    uint32_t    _baud_hz;

    uint32_t    _sectors = 0;
    // Block-addressing divisor: 1 for SDHC/SDXC (block addressing),
    // 512 for SDSC (byte addressing). Multiplied with block_num.
    uint32_t    _cdv     = 512;
    uint8_t     _token   = 0;
};

} // namespace pico_api
