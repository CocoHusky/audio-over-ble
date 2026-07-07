#!/usr/bin/env python3
"""Simple terminal player: XIAO BLE LC3 mic -> Mac speaker output."""

from __future__ import annotations

import argparse
import asyncio
import math
import sys

import numpy as np
import sounddevice as sd
from bleak import BleakClient
from bleak.exc import BleakError

from ble_audio_receiver import (
    AUDIO_CHAR_UUID,
    DEVICE_NAME,
    JITTER_BUFFER_SAMPLES,
    SAMPLE_RATE_HZ,
    AudioStreamState,
    find_device,
)


def default_output_rate() -> int:
    try:
        device = sd.query_devices(kind="output")
        return int(device.get("default_samplerate") or 48000)
    except Exception:
        return 48000


class ResampledPlayer:
    def __init__(self, state: AudioStreamState, output_rate: int):
        self.state = state
        self.output_rate = float(output_rate)
        self.source = np.zeros(2, dtype=np.float32)
        self.position = 0.0

    def pull(self, frames: int) -> np.ndarray:
        if frames <= 0:
            return np.zeros(0, dtype=np.float32)

        step = SAMPLE_RATE_HZ / self.output_rate
        last_needed = self.position + step * max(frames - 1, 0)
        needed_len = int(math.ceil(last_needed)) + 2

        if len(self.source) < needed_len:
            missing = needed_len - len(self.source)
            samples = self.state.pull(max(missing, 256)).astype(np.float32) / 32768.0
            self.source = np.concatenate((self.source, samples))

        positions = self.position + step * np.arange(frames, dtype=np.float32)
        indexes = np.arange(len(self.source), dtype=np.float32)
        out = np.interp(positions, indexes, self.source).astype(np.float32)

        self.position += step * frames
        drop = int(self.position)
        if drop > 0:
            self.source = self.source[drop:]
            if len(self.source) < 2:
                self.source = np.pad(self.source, (0, 2 - len(self.source)))
            self.position -= drop

        return out


async def main_async(args: argparse.Namespace) -> int:
    address = args.address
    if address is None:
        device = await find_device(timeout=args.scan_seconds)
        if device is None:
            print(f"Could not find {DEVICE_NAME}. Is the board flashed, powered, and not already connected?", file=sys.stderr)
            return 1
        address = device.address
        print(f"Found {DEVICE_NAME}: {address}")

    state = AudioStreamState(save_path=args.save, gain=args.gain)
    state.adaptive_buffer_enabled = True
    state.target_queue_samples = int(SAMPLE_RATE_HZ * args.buffer_ms / 1000)
    state.max_queue_samples = int(SAMPLE_RATE_HZ * 2.0)

    output_rate = args.output_rate or default_output_rate()
    player = ResampledPlayer(state, output_rate)

    def audio_callback(outdata, frames, time_info, status):
        del time_info
        if status:
            print(status, file=sys.stderr)
        outdata[:, 0] = player.pull(frames)

    stream = None
    try:
        async with BleakClient(address) as client:
            print(f"Connected. MTU={getattr(client, 'mtu_size', 'unknown')}")
            await client.start_notify(AUDIO_CHAR_UUID, state.handle_notification)
            print("Subscribed. Buffering...")

            for _ in range(200):
                if len(state.sample_queue) >= state.target_queue_samples:
                    break
                await asyncio.sleep(0.02)

            stream = sd.OutputStream(
                samplerate=output_rate,
                channels=1,
                dtype="float32",
                callback=audio_callback,
                blocksize=0,
                latency="high",
            )
            stream.start()
            print(f"Playing to Mac output at {output_rate} Hz. Ctrl+C to stop.")

            while True:
                await asyncio.sleep(1.0)
                print(
                    f"\rpackets={state.packets_received} lost={state.packets_lost} "
                    f"bad={state.bad_packets} decode_fail={state.decode_failures} "
                    f"queued={len(state.sample_queue)} rms={state.last_rms:.0f} peak={state.last_peak}",
                    end="",
                    flush=True,
                )
    except KeyboardInterrupt:
        pass
    finally:
        if stream is not None:
            stream.stop()
            stream.close()
        try:
            state.close()
        except Exception:
            pass
        print("\nStopped.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default=None)
    parser.add_argument("--scan-seconds", type=float, default=10.0)
    parser.add_argument("--gain", type=float, default=1.0)
    parser.add_argument("--buffer-ms", type=float, default=350.0)
    parser.add_argument("--output-rate", type=int, default=None)
    parser.add_argument("--save", default=None, metavar="FILE.wav")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
