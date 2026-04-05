cmake_minimum_required(VERSION 3.13)

# Pull in Pico SDK (PICO_SDK_PATH must be set or pico-sdk must be a sibling dir)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(pico_synth C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

# Run Python script to generate drum sample headers from WAV files
add_custom_command(
    OUTPUT drum_samples.h drum_kick.h drum_snare.h drum_hihat.h drum_floor.h
    COMMAND python3 wav_to_c.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/audio/Rock-Kit-Kick-ff-1.wav
            ${CMAKE_CURRENT_SOURCE_DIR}/audio/Rock-Snare-ff-1.wav
            ${CMAKE_CURRENT_SOURCE_DIR}/audio/Rock-Kit-HiHat-Tip-1.wav
            ${CMAKE_CURRENT_SOURCE_DIR}/audio/Rock-Kit-Floor-1.wav
            ${CMAKE_CURRENT_SOURCE_DIR}/wav_to_c.py
    COMMENT "Generating drum sample headers from WAV files..."
)

add_executable(pico_synth main.c
    ${CMAKE_CURRENT_BINARY_DIR}/drum_samples.h
)

# Generate C header from i2s.pio (must be after add_executable)
pico_generate_pio_header(pico_synth ${CMAKE_CURRENT_LIST_DIR}/i2s.pio)

# Include generated drum sample headers
target_include_directories(pico_synth PRIVATE ${CMAKE_CURRENT_BINARY_DIR})

target_link_libraries(pico_synth
    pico_stdlib
    hardware_spi
    hardware_i2c
    hardware_adc
    hardware_dma
    hardware_pio
    hardware_clocks
    m          # math library (sinf, powf used at startup for drum tables)
)

# Produce .uf2 file (drag-and-drop onto Pico in BOOTSEL mode)
pico_add_extra_outputs(pico_synth)

# USB serial for debug prints (optional — can set to 0 to save flash)
pico_enable_stdio_usb(pico_synth 1)
pico_enable_stdio_uart(pico_synth 0)
