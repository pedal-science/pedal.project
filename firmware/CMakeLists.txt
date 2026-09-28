cmake_minimum_required(VERSION 3.13)

# Pico SDK 2.3.1 and Arm GNU Toolchain 15.3.rel1 (plan Phase 3, 2026-09-28).
# Both live outside the tree; set PICO_SDK_PATH or keep the default checkout.
if(NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}")
endif()
if(NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "$ENV{HOME}/pico/pico-sdk")
endif()

include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(pedal-firmware C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

# The control surface board, committed here: Pico 2 W (plan Shopping).
if(NOT PICO_BOARD)
    set(PICO_BOARD pico2_w)
endif()

add_executable(pedal-firmware
    src/main.c
)

# pico_cyw43_arch_none: the W board's LED, no lwIP/WiFi (D2: the Pico's link is UART).
target_link_libraries(pedal-firmware
    pico_stdlib
    pico_cyw43_arch_none
)

# USB CDC for the console. UART stdio must stay off: the link UART is ours.
pico_enable_stdio_usb(pedal-firmware 1)
pico_enable_stdio_uart(pedal-firmware 0)

pico_add_extra_outputs(pedal-firmware)
