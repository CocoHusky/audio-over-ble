# Install script for directory: /opt/nordic/ncs/v3.3.0/zephyr

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "TRUE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/opt/nordic/ncs/toolchains/0c0f19d91c/opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/arch/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/lib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/soc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/boards/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/subsys/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/nrf/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/mcuboot/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/mbedtls/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/trusted-firmware-m/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/cjson/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/azure-sdk-for-c/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/cirrus-logic/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/openthread/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/memfault-firmware-sdk/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/hostap/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/canopennode/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/chre/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/cmsis/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/cmsis-dsp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/cmsis-nn/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/cmsis_6/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/fatfs/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/hal_nordic/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/hal_st/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/hal_tdk/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/hal_wurthelektronik/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/liblc3/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/libmetal/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/libsbc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/littlefs/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/loramac-node/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/lvgl/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/mipi-sys-t/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/nanopb/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/nrf_wifi/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/open-amp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/percepio/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/picolibc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/segger/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/uoscore-uedhoc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/zcbor/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/nrfxlib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/nrf_hw_models/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/modules/connectedhomeip/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/kernel/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/cmake/flash/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/cmake/usage/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/cmake/reports/cmake_install.cmake")
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
