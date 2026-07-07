#!/usr/bin/env python3
"""
Minimal ctypes binding for the libopus decoder used by the BLE receiver.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from pathlib import Path

import numpy as np


SAMPLE_RATE_HZ = 16000
CHANNELS = 1


class OpusError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_libopus():
    candidates = [
        _repo_root() / "third_party" / "opus-1.6.1" / "build-host-make" / "libopus.dylib",
        _repo_root() / "third_party" / "opus-1.6.1" / "build-host-make" / "libopus.so",
        _repo_root() / "third_party" / "opus-1.6.1" / "build-host" / "libopus.dylib",
        _repo_root() / "third_party" / "opus-1.6.1" / "build-host" / "libopus.so",
    ]
    system_name = ctypes.util.find_library("opus")
    if system_name:
        candidates.append(Path(system_name))

    for candidate in candidates:
        try:
            return ctypes.CDLL(str(candidate))
        except OSError:
            continue

    raise OpusError(
        "Could not load libopus. Run pc_client/build_opus_host.sh first."
    )


class OpusDecoder:
    def __init__(self, sample_rate_hz: int = SAMPLE_RATE_HZ, channels: int = CHANNELS):
        self._lib = _load_libopus()

        self._lib.opus_decoder_create.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._lib.opus_decoder_create.restype = ctypes.c_void_p
        self._lib.opus_decode.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._lib.opus_decode.restype = ctypes.c_int
        self._lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
        self._lib.opus_decoder_destroy.restype = None
        self._lib.opus_strerror.argtypes = [ctypes.c_int]
        self._lib.opus_strerror.restype = ctypes.c_char_p

        error = ctypes.c_int()
        self._decoder = self._lib.opus_decoder_create(sample_rate_hz, channels, ctypes.byref(error))
        if error.value != 0 or not self._decoder:
            raise OpusError(self._error_text(error.value))

    def decode(self, payload: bytes | None, frame_samples: int) -> np.ndarray:
        pcm = np.zeros(frame_samples * CHANNELS, dtype=np.int16)
        pcm_ptr = pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))

        if payload is None:
            decoded = self._lib.opus_decode(
                self._decoder,
                None,
                0,
                pcm_ptr,
                frame_samples,
                0,
            )
        else:
            payload_buf = ctypes.create_string_buffer(payload)
            decoded = self._lib.opus_decode(
                self._decoder,
                ctypes.cast(payload_buf, ctypes.c_void_p),
                len(payload),
                pcm_ptr,
                frame_samples,
                0,
            )

        if decoded < 0:
            raise OpusError(self._error_text(decoded))

        return pcm[: decoded * CHANNELS]

    def close(self):
        if self._decoder:
            self._lib.opus_decoder_destroy(self._decoder)
            self._decoder = None

    def _error_text(self, code: int) -> str:
        text = self._lib.opus_strerror(code)
        return text.decode("utf-8", errors="replace") if text else f"Opus error {code}"
