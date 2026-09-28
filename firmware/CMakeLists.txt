cmake_minimum_required(VERSION 3.13)

# Pico SDK 2.3.1 and Arm GNU Toolchain 15.3.rel1 (plan Phase 3, 2026-09-28).
# Both live outside the tree; set PICO_SDK_PATH or keep the default checkout.
if(NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}")
endif()
if(NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "$ENV{HOME}/pico/pico-sdk")
endif()

# The control surface board, committed here: Pico 2 W (plan Shopping). It has to be set before
# the SDK is imported, which is where the SDK reads it and picks the platform from it; set any
# later, a plain configure would build for the default board, an RP2040 Pico.
if(NOT PICO_BOARD)
    set(PICO_BOARD pico2_w)
endif()

include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(pedal-firmware C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(pedal-firmware
    src/main.c
    src/protocol.c
)

# The firmware carries the commit it was built from, "-dirty" if the tree was
# (docs/working-across-repos.md, rule 5); HELLO sends it as fw_version. It is read at configure
# time, and build.sh configures on every build, so it follows the tree.
execute_process(
    COMMAND git describe --always --dirty --abbrev=7
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE PEDAL_FW_VERSION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET)
if(NOT PEDAL_FW_VERSION)
    set(PEDAL_FW_VERSION "unknown")
endif()
target_compile_definitions(pedal-firmware PRIVATE PEDAL_FW_VERSION="${PEDAL_FW_VERSION}")

# Build step 1's byte echo instead of the protocol, for tools/echo-test.py.
option(FW_ECHO "Build the UART echo (step 1) instead of the protocol firmware" OFF)
if(FW_ECHO)
    target_compile_definitions(pedal-firmware PRIVATE PEDAL_FW_ECHO=1)
endif()

# pico_cyw43_arch_none: the W board's LED, no lwIP/WiFi (D2: the Pico's link is UART).
target_link_libraries(pedal-firmware
    pico_stdlib
    pico_cyw43_arch_none
)

# USB CDC for the console. UART stdio must stay off: the link UART is ours.
pico_enable_stdio_usb(pedal-firmware 1)
pico_enable_stdio_uart(pedal-firmware 0)

pico_add_extra_outputs(pedal-firmware)
