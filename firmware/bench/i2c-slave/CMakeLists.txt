cmake_minimum_required(VERSION 3.13)

# The bench I2C slave: a separate project on purpose, so nobody flashes it into the pedal's Pico by
# accident (it is a different UF2 in a different build directory). Same environment as the pedal
# firmware: Pico SDK 2.3.1 and Arm GNU Toolchain 15.3.rel1, board pico2_w.
if(NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}")
endif()
if(NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "$ENV{HOME}/pico/pico-sdk")
endif()

if(NOT PICO_BOARD)
    set(PICO_BOARD pico2_w)
endif()

include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(i2c-slave C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

set(SLAVE_I2C 0 CACHE STRING "I2C block the slave answers on (0 or 1)")
set(SLAVE_SDA 4 CACHE STRING "slave SDA pin")
set(SLAVE_SCL 5 CACHE STRING "slave SCL pin")
set(SLAVE_SELFTEST 0 CACHE STRING "1: drive the other I2C pair as a master to test this slave")

add_executable(i2c-slave i2c-slave.c)

target_compile_definitions(i2c-slave PRIVATE
    SLAVE_I2C=${SLAVE_I2C} SDA_PIN=${SLAVE_SDA} SCL_PIN=${SLAVE_SCL}
    SLAVE_SELFTEST=${SLAVE_SELFTEST})

target_link_libraries(i2c-slave
    pico_stdlib
    hardware_i2c
    pico_i2c_slave
    pico_cyw43_arch_none
)

# USB CDC for the console, no UART stdio: on this board the UART pins are free, but the console over
# USB is what makes the banner readable while it sits on vip's 5 V.
pico_enable_stdio_usb(i2c-slave 1)
pico_enable_stdio_uart(i2c-slave 0)

pico_add_extra_outputs(i2c-slave)
