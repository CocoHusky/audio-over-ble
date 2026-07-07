from __future__ import annotations

import ctypes
import os
from pathlib import Path

import numpy as np

LC3_PCM_FORMAT_S16 = 0
LC3_FRAME_US = 10000
SAMPLE_RATE_HZ = 16000
FRAME_SAMPLES = 160
FRAME_BYTES = 40


class LC3Decoder:
    def __init__(self, library_path: str | os.PathLike | None = None):
        lib_path = Path(library_path) if library_path else Path(__file__).with_name("liblc3.dylib")
        if not lib_path.exists():
            raise FileNotFoundError(
                f"Missing {lib_path}. Run ./build_lc3_host.sh from pc_client first."
            )

        self.lib = ctypes.CDLL(str(lib_path))
        self.lib.lc3_decoder_size.argtypes = [ctypes.c_int, ctypes.c_int]
        self.lib.lc3_decoder_size.restype = ctypes.c_uint
        self.lib.lc3_setup_decoder.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        self.lib.lc3_setup_decoder.restype = ctypes.c_void_p
        self.lib.lc3_decode.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        self.lib.lc3_decode.restype = ctypes.c_int

        mem_size = self.lib.lc3_decoder_size(LC3_FRAME_US, SAMPLE_RATE_HZ)
        if mem_size <= 0:
            raise RuntimeError("lc3_decoder_size returned zero")
        self._mem = ctypes.create_string_buffer(mem_size)
        self._decoder = self.lib.lc3_setup_decoder(
            LC3_FRAME_US,
            SAMPLE_RATE_HZ,
            0,
            ctypes.cast(self._mem, ctypes.c_void_p),
        )
        if not self._decoder:
            raise RuntimeError("lc3_setup_decoder failed")

    def decode(self, payload: bytes | None) -> np.ndarray:
        out = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        out_ptr = out.ctypes.data_as(ctypes.c_void_p)

        if payload is None:
            rc = self.lib.lc3_decode(
                self._decoder,
                None,
                0,
                LC3_PCM_FORMAT_S16,
                out_ptr,
                1,
            )
        else:
            in_buf = ctypes.create_string_buffer(payload)
            rc = self.lib.lc3_decode(
                self._decoder,
                ctypes.cast(in_buf, ctypes.c_void_p),
                len(payload),
                LC3_PCM_FORMAT_S16,
                out_ptr,
                1,
            )

        if rc < 0:
            raise RuntimeError(f"lc3_decode failed: {rc}")
        return out
