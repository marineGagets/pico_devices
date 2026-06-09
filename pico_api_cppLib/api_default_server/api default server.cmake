cmake_minimum_required(VERSION 3.13)

# Pull in the required SDK configurations
include(pico_sdk_import.cmake)

project(pico_api_server C CXX)
set(CMAKE_CXX_STANDARD 17)

# Initialize target SDK components
pico_sdk_init()

add_executable(pico_api_server
    main.cpp
)

# Pull in the required thread-safe background network architecture linkages
target_link_libraries(pico_api_server
    pico_stdlib
    pico_cyw43_arch_lwip_threadsafe_background
)

# Enable USB serial output monitoring support configurations
pico_enable_stdio_usb(pico_api_server 1)
pico_enable_stdio_uart(pico_api_server 0)

pico_add_extra_outputs(pico_api_server)
