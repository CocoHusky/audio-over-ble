#!/usr/bin/env python3
"""
audio-over-ble — stable raw PCM PC client.

Packet format expected from firmware:
    [uint16 LE seq][uint16 LE sample_count][signed 16-bit LE PCM payload...]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import wave
from collections import deque

import numpy as np
import sounddevice as sd
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

SERVICE_UUID = "04a77077-8d9a-4cd2-bf83-f7adafa02251"
AUDIO_CHAR_UUID = "30fafbf6-9ec3-41ae-86b9-60cbf31328bb"
DEVICE_NAME = "CocoHusky-AudioStream"

# Stability-first baseline. This must match firmware SAMPLE_RATE_HZ.
SAMPLE_RATE_HZ = 8000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
RAW_HEADER_SIZE = 4

JITTER_BUFFER_MS = 350
JITTER_BUFFER_SAMPLES = int(SAMPLE_RATE_HZ * JITTER_BUFFER_MS / 1000)
PLAYBACK_BLOCKSIZE = 256


class AudioStreamState:
    def __init__(self, save_path=None, gain=1.0):
        self.lock = threading.RLock()
        self.sample_queue = deque()
        self.last_seq = None
        self.samples_dropped = 0
        self.packets_received = 0
        self.packets_lost = 0
        self.underflows = 0
        self.buffer_refills = 0
        self.bad_packets = 0
        self.started_playback = False
        self.refilling_buffer = False
        self.gain = gain
        self.muted = False
        self.adaptive_buffer_enabled = True
        self.target_queue_samples = JITTER_BUFFER_SAMPLES
        self.highpass_enabled = False
        self.highpass_cutoff_hz = 80.0
        self.lowpass_enabled = False
        self.lowpass_cutoff_hz = 3600.0
        self.noise_gate_enabled = False
        self.noise_gate_threshold = 80.0
        self.noise_gate_attenuation = 0.15
        self.noise_suppression_enabled = False
        self.noise_floor = 40.0
        self.noise_suppression_strength = 0.55
        self.agc_enabled = False
        self.agc_target_rms = 1800.0
        self.agc_max_gain = 18.0
        self.agc_gain = 1.0
        self.compressor_enabled = False
        self.compressor_threshold = 9000.0
        self.compressor_ratio = 3.0
        self.compressor_makeup_gain = 1.0
        self.declick_enabled = True
        self.declick_max_step = 6000.0
        self.limiter_enabled = True
        self.max_queue_samples = SAMPLE_RATE_HZ
        self._last_processed_tail = np.zeros(0, dtype=np.int16)
        self._last_output_sample = 0.0
        self.last_rms = 0.0
        self.last_peak = 0
        self.output_rms = 0.0
        self.output_peak = 0
        self.wav_writer = None
        if save_path:
            self.wav_writer = wave.open(save_path, "wb")
            self.wav_writer.setnchannels(CHANNELS)
            self.wav_writer.setsampwidth(BYTES_PER_SAMPLE)
            self.wav_writer.setframerate(SAMPLE_RATE_HZ)

    def handle_notification(self, _handle, data: bytearray):
        if len(data) < RAW_HEADER_SIZE:
            self.bad_packets += 1
            return

        seq = data[0] | (data[1] << 8)
        frame_samples = data[2] | (data[3] << 8)
        payload = bytes(data[RAW_HEADER_SIZE:])
        expected_bytes = frame_samples * BYTES_PER_SAMPLE

        if frame_samples <= 0 or len(payload) != expected_bytes:
            self.bad_packets += 1
            return

        sample_array = np.frombuffer(payload, dtype="<i2").copy()
        if len(sample_array) != frame_samples:
            self.bad_packets += 1
            return

        if len(sample_array):
            sample_i32 = sample_array.astype(np.int32)
            self.last_rms = float(np.sqrt(np.mean(sample_i32.astype(np.float64) ** 2)))
            self.last_peak = int(np.max(np.abs(sample_i32)))

        with self.lock:
            if self.last_seq is not None:
                expected = (self.last_seq + 1) & 0xFFFF
                if seq != expected:
                    gap = (seq - expected) & 0xFFFF
                    if 0 < gap < 100:
                        self.packets_lost += gap
                        conceal_count = min(gap, 5)
                        for _ in range(conceal_count):
                            concealment = self._conceal_samples(frame_samples)
                            self.sample_queue.extend(concealment.tolist())
                            self.samples_dropped += len(concealment)
            self.last_seq = seq
            self.packets_received += 1

            processed = self._process_samples(sample_array)
            self.sample_queue.extend(processed.tolist())
            self._last_processed_tail = processed[-min(len(processed), frame_samples):].copy()
            while len(self.sample_queue) > self.max_queue_samples:
                self.sample_queue.popleft()

        if self.wav_writer is not None:
            self.wav_writer.writeframes(sample_array.astype("<i2").tobytes())

    def _process_samples(self, samples: np.ndarray) -> np.ndarray:
        x = samples.astype(np.float64)
        if not len(x):
            return samples

        block_rms = float(np.sqrt(np.mean(x ** 2)))

        if self.noise_suppression_enabled:
            if block_rms < max(self.noise_gate_threshold * 2.0, self.noise_floor * 4.0):
                self.noise_floor = 0.98 * self.noise_floor + 0.02 * block_rms
            suppression_point = max(self.noise_floor * 2.5, 1.0)
            if block_rms < suppression_point:
                reduction = self.noise_suppression_strength * (1.0 - block_rms / suppression_point)
                x *= max(0.0, 1.0 - reduction)

        if self.noise_gate_enabled and block_rms < self.noise_gate_threshold:
            x *= self.noise_gate_attenuation

        if self.agc_enabled and block_rms > 1.0:
            target_gain = min(self.agc_target_rms / block_rms, self.agc_max_gain)
            self.agc_gain = 0.95 * self.agc_gain + 0.05 * target_gain
            x *= self.agc_gain
        else:
            self.agc_gain = 0.98 * self.agc_gain + 0.02

        if self.compressor_enabled:
            abs_x = np.abs(x)
            over = abs_x > self.compressor_threshold
            compressed = np.copy(abs_x)
            compressed[over] = self.compressor_threshold + (
                abs_x[over] - self.compressor_threshold
            ) / max(self.compressor_ratio, 1.0)
            x = np.sign(x) * compressed * self.compressor_makeup_gain

        if self.muted:
            x *= 0.0
        else:
            x *= self.gain

        if self.declick_enabled:
            prev = self._last_output_sample
            for i, sample in enumerate(x):
                delta = sample - prev
                if delta > self.declick_max_step:
                    sample = prev + self.declick_max_step
                elif delta < -self.declick_max_step:
                    sample = prev - self.declick_max_step
                x[i] = sample
                prev = sample

        if self.limiter_enabled:
            x = np.clip(x, -30000, 30000)
        else:
            x = np.clip(x, np.iinfo(np.int16).min, np.iinfo(np.int16).max)

        self.output_rms = float(np.sqrt(np.mean(x ** 2)))
        self.output_peak = int(np.max(np.abs(x)))
        self._last_output_sample = float(x[-1])
        return x.astype(np.int16)

    def _conceal_samples(self, count):
        if count <= 0:
            return np.zeros(0, dtype=np.int16)
        if len(self._last_processed_tail) == 0:
            base = np.full(count, int(self._last_output_sample), dtype=np.float64)
        else:
            repeats = int(np.ceil(count / len(self._last_processed_tail)))
            base = np.tile(self._last_processed_tail, repeats)[:count].astype(np.float64)
        fade = np.linspace(1.0, 0.15, count)
        return (base * fade).astype(np.int16)

    def pull(self, n):
        out = np.empty(n, dtype=np.int16)
        with self.lock:
            if self.adaptive_buffer_enabled:
                low_watermark = max(n * 2, self.target_queue_samples // 3)
                if len(self.sample_queue) < low_watermark:
                    if not self.refilling_buffer:
                        self.buffer_refills += 1
                    self.refilling_buffer = True
                if self.refilling_buffer and len(self.sample_queue) < self.target_queue_samples:
                    out[:] = self._conceal_samples(n)
                    if n:
                        self._last_output_sample = float(out[-1])
                    return out
                self.refilling_buffer = False

            avail = min(n, len(self.sample_queue))
            for i in range(avail):
                out[i] = self.sample_queue.popleft()
            if avail < n:
                self.underflows += 1
                out[avail:] = self._conceal_samples(n - avail)
            while len(self.sample_queue) > self.max_queue_samples:
                self.sample_queue.popleft()
            if n:
                self._last_output_sample = float(out[-1])
        return out

    def close(self):
        if self.wav_writer is not None:
            self.wav_writer.close()


async def find_device(timeout=8.0):
    print(f"Scanning for '{DEVICE_NAME}' ({timeout:.0f}s timeout)...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: d.name == DEVICE_NAME or adv.local_name == DEVICE_NAME,
        timeout=timeout,
    )
    return device


async def run(address: str | None, save_path: str | None, gain: float):
    if address is None:
        device = await find_device()
        if device is None:
            print(f"Could not find a device named '{DEVICE_NAME}'. Is the XIAO powered on and advertising?", file=sys.stderr)
            sys.exit(1)
        address = device.address
        print(f"Found device at {address}")

    state = AudioStreamState(save_path=save_path, gain=gain)

    def audio_callback(outdata, frames, time_info, status):
        del time_info
        if status:
            print(status, file=sys.stderr)
        outdata[:, 0] = state.pull(frames)

    stream = sd.OutputStream(
        samplerate=SAMPLE_RATE_HZ,
        channels=CHANNELS,
        dtype="int16",
        callback=audio_callback,
        blocksize=PLAYBACK_BLOCKSIZE,
    )

    async with BleakClient(address) as client:
        mtu = getattr(client, "mtu_size", "unknown")
        print(f"Connected to {address}; reported MTU={mtu}")
        await client.start_notify(AUDIO_CHAR_UUID, state.handle_notification)
        print("Subscribed to raw PCM audio characteristic. Buffering...")

        for _ in range(150):
            if len(state.sample_queue) >= JITTER_BUFFER_SAMPLES:
                break
            await asyncio.sleep(0.02)

        stream.start()
        print("Playback started. Ctrl+C to stop.")

        try:
            while True:
                await asyncio.sleep(1.0)
                print(
                    f"\rpackets={state.packets_received} "
                    f"lost={state.packets_lost} "
                    f"bad={state.bad_packets} "
                    f"queued_samples={len(state.sample_queue)} "
                    f"concealed={state.samples_dropped} "
                    f"underflows={state.underflows} "
                    f"refills={state.buffer_refills} "
                    f"rms={state.last_rms:.0f} "
                    f"peak={state.last_peak} "
                    f"out_rms={state.output_rms:.0f} "
                    f"out_peak={state.output_peak}",
                    end="", flush=True,
                )
        except asyncio.CancelledError:
            pass
        finally:
            stream.stop()
            stream.close()
            try:
                await client.stop_notify(AUDIO_CHAR_UUID)
            except BleakError:
                pass
            state.close()
            print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default=None, help="BLE MAC/UUID address (skip auto-scan)")
    parser.add_argument("--save", default=None, metavar="FILE.wav", help="Also save incoming audio to a WAV file")
    parser.add_argument("--gain", type=float, default=1.0, help="Playback-only digital gain multiplier")
    args = parser.parse_args()

    try:
        asyncio.run(run(args.address, args.save, args.gain))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
