cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_ble_mic_stream)

set(LC3_DIR "$ENV{LC3_DIR}" CACHE PATH "Path to SDK modules/lib/lc3")

if(NOT LC3_DIR)
  get_filename_component(NCS_ROOT "$ENV{ZEPHYR_BASE}/.." ABSOLUTE)
  set(LC3_DIR "${NCS_ROOT}/modules/lib/lc3")
endif()

if(NOT EXISTS "${LC3_DIR}/include/lc3.h")
  message(FATAL_ERROR "lc3.h not found. Re-run with -DLC3_DIR=/path/to/modules/lib/lc3")
endif()

message(STATUS "Using LC3_DIR=${LC3_DIR}")

target_include_directories(app PRIVATE "${LC3_DIR}/include")
target_sources(app PRIVATE src/main.c)
