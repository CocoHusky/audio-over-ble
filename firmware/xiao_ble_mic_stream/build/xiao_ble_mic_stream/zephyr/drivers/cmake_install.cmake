# Install script for directory: /opt/nordic/ncs/v3.3.0/zephyr/drivers

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
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/disk/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/firmware/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/interrupt_controller/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/misc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/pcie/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/usb/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/usb_c/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/audio/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/bluetooth/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/clock_control/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/console/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/entropy/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/gpio/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/hwinfo/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/pinctrl/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/regulator/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/serial/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/timer/cmake_install.cmake")
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream/zephyr/drivers/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
