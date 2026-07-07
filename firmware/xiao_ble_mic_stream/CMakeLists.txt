cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_ble_mic_stream)

set(LC3_DIR "$ENV{LC3_DIR}" CACHE PATH "Path to SDK liblc3 directory")

if(NOT LC3_DIR)
  get_filename_component(NCS_ROOT "$ENV{ZEPHYR_BASE}/.." ABSOLUTE)
  file(GLOB_RECURSE LC3_HEADER_CANDIDATES
    "${NCS_ROOT}/modules/lib/*/include/lc3.h"
    "${NCS_ROOT}/nrf/modules/lib/*/include/lc3.h"
    "${NCS_ROOT}/zephyr/modules/lib/*/include/lc3.h"
    "${NCS_ROOT}/**/include/lc3.h"
  )
  list(GET LC3_HEADER_CANDIDATES 0 LC3_HEADER)
  if(LC3_HEADER)
    get_filename_component(LC3_INCLUDE_DIR "${LC3_HEADER}" DIRECTORY)
    get_filename_component(LC3_DIR "${LC3_INCLUDE_DIR}" DIRECTORY)
  endif()
endif()

if(NOT LC3_DIR OR NOT EXISTS "${LC3_DIR}/include/lc3.h")
  message(FATAL_ERROR "lc3.h not found in the NCS tree. Run: find /opt/nordic/ncs -path '*/include/lc3.h' -print")
endif()

file(GLOB LC3_SOURCES CONFIGURE_DEPENDS "${LC3_DIR}/src/*.c")
if(NOT LC3_SOURCES)
  message(FATAL_ERROR "LC3 sources not found at ${LC3_DIR}/src/*.c")
endif()

message(STATUS "Using LC3_DIR=${LC3_DIR}")
message(STATUS "Compiling LC3 sources: ${LC3_SOURCES}")

target_sources(app PRIVATE src/main.c ${LC3_SOURCES})
target_include_directories(app PRIVATE
  "${LC3_DIR}/include"
  "${LC3_DIR}/src"
)
target_compile_definitions(app PRIVATE "lc3_encoder_disable_ltpf(x)=((void)0)")
