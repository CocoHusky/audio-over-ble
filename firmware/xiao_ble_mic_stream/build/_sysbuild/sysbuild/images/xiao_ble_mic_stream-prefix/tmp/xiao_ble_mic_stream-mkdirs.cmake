# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file LICENSE.rst or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION ${CMAKE_VERSION}) # this file comes with cmake

# If CMAKE_DISABLE_SOURCE_CHANGES is set to true and the source directory is an
# existing directory in our source tree, calling file(MAKE_DIRECTORY) on it
# would cause a fatal error, even though it would be a no-op.
if(NOT EXISTS "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream")
  file(MAKE_DIRECTORY "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream")
endif()
file(MAKE_DIRECTORY
  "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/xiao_ble_mic_stream"
  "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/_sysbuild/sysbuild/images/xiao_ble_mic_stream-prefix"
  "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/_sysbuild/sysbuild/images/xiao_ble_mic_stream-prefix/tmp"
  "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/_sysbuild/sysbuild/images/xiao_ble_mic_stream-prefix/src/xiao_ble_mic_stream-stamp"
  "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/_sysbuild/sysbuild/images/xiao_ble_mic_stream-prefix/src"
  "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/_sysbuild/sysbuild/images/xiao_ble_mic_stream-prefix/src/xiao_ble_mic_stream-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/_sysbuild/sysbuild/images/xiao_ble_mic_stream-prefix/src/xiao_ble_mic_stream-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/Users/alexburton/Documents/GitHub/audio-over-ble/firmware/xiao_ble_mic_stream/build/_sysbuild/sysbuild/images/xiao_ble_mic_stream-prefix/src/xiao_ble_mic_stream-stamp${cfgdir}") # cfgdir has leading slash
endif()
