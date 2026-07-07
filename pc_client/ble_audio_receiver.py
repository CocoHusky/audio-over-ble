#!/usr/bin/env python3
"""audio-over-ble ADPCM PC client."""

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
SAMPLE_RATE_HZ = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
FRAME_SAMPLES = 160
FRAME_BYTES = 84
APP_HEADER_SIZE = 6
JITTER_BUFFER_MS = 350
JITTER_BUFFER_SAMPLES = int(SAMPLE_RATE_HZ * JITTER_BUFFER_MS / 1000)
PLAYBACK_BLOCKSIZE = 512

_IMA_STEP_TABLE = np.array(
    [
        7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
        19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
        50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
        130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
        337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
        876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
        2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
        5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
        15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
    ],
    dtype=np.int32,
)
_IMA_INDEX_TABLE = np.array(
    [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8],
    dtype=np.int32,
)


def decode_adpcm_frame(payload: bytes) -> np.ndarray:
    if len(payload) != FRAME_BYTES:
        raise ValueError(f"expected {FRAME_BYTES} ADPCM bytes, got {len(payload)}")

    predictor = int.from_bytes(payload[0:2], byteorder="little", signed=True)
    index = int(payload[2])
    index = max(0, min(88, index))

    out = np.empty(FRAME_SAMPLES, dtype=np.int16)
    out[0] = predictor

    for i in range(FRAME_SAMPLES - 1):
        packed = payload[4 + (i >> 1)]
        nibble = (packed >> 4) & 0x0F if (i & 1) else packed & 0x0F

        step = int(_IMA_STEP_TABLE[index])
        diffq = step >> 3
        if nibble & 4:
            diffq += step
        if nibble & 2:
            diffq += step >> 1
        if nibble & 1:
            diffq += step >> 2

        if nibble & 8:
            predictor -= diffq
        else:
            predictor += diffq
        predictor = max(-32768, min(32767, predictor))

        index += int(_IMA_INDEX_TABLE[nibble])
        index = max(0, min(88, index))
        out[i + 1] = predictor

    return out


class AudioStreamState:
    def __init__(self, save_path=None, gain=1.0):
        self.lock = threading.RLock()
        self.sample_queue = deque()
        self.last_seq = None
        self.samples_dropped = 0
        self.samples_trimmed = 0
        self.packets_received = 0
        self.packets_lost = 0
        self.underflows = 0
        self.buffer_refills = 0
        self.bad_packets = 0
        self.decode_failures = 0
        self.refilling_buffer = False
        self.gain = gain
        self.muted = False
        self.adaptive_buffer_enabled = True
        self.latency_trim_enabled = True
        self.target_queue_samples = JITTER_BUFFER_SAMPLES
        self.agc_enabled = False
        self.agc_target_rms = 2200.0
        self.agc_max_gain = 24.0
        self.agc_gain = 1.0
        self.highpass_enabled = True
        self.highpass_alpha = 0.97
        self.noise_gate_enabled = False
        self.noise_gate_threshold = 120.0
        self.noise_gate_attenuation = 0.08
        self.declick_enabled = True
        self.declick_max_step = 6000.0
        self.limiter_enabled = True
        self.max_queue_samples = SAMPLE_RATE_HZ
        self._last_processed_tail = np.zeros(0, dtype=np.int16)
        self._last_output_sample = 0.0
        self._hp_prev_x = 0.0
        self._hp_prev_y = 0.0
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
        if len(data) < APP_HEADER_SIZE:
            self.bad_packets += 1
            return

        seq = data[0] | (data[1] << 8)
        decoded_samples = data[2] | (data[3] << 8)
        payload_bytes = data[4] | (data[5] << 8)
        payload = bytes(data[APP_HEADER_SIZE:])

        if decoded_samples != FRAME_SAMPLES or payload_bytes != len(payload) or payload_bytes != FRAME_BYTES:
            self.bad_packets += 1
            return

        decoded_blocks = []
        with self.lock:
            if self.last_seq is not None:
                expected = (self.last_seq + 1) & 0xFFFF
                if seq != expected:
                    gap = (seq - expected) & 0xFFFF
                    if 0 < gap < 100:
                        self.packets_lost += gap
                        for _ in range(min(gap, 5)):
                            decoded_blocks.append(self._decode_plc())
            self.last_seq = seq

            try:
                decoded_blocks.append(decode_adpcm_frame(payload))
            except Exception:
                self.decode_failures += 1
                decoded_blocks.append(self._decode_plc())

            for block in decoded_blocks:
                if len(block):
                    block_i32 = block.astype(np.int32)
                    self.last_rms = float(np.sqrt(np.mean(block_i32.astype(np.float64) ** 2)))
                    self.last_peak = int(np.max(np.abs(block_i32)))
                processed = self._process_samples(block)
                self.sample_queue.extend(processed.tolist())
                self._last_processed_tail = processed[-min(len(processed), FRAME_SAMPLES):].copy()
                if block is not decoded_blocks[-1]:
                    self.samples_dropped += len(processed)

            self.packets_received += 1
            while len(self.sample_queue) > self.max_queue_samples:
                self.sample_queue.popleft()
                self.samples_trimmed += 1

        if self.wav_writer is not None and decoded_blocks:
            self.wav_writer.writeframes(decoded_blocks[-1].astype("<i2").tobytes())

    def _decode_plc(self):
        return self._conceal_samples(FRAME_SAMPLES)

    def _highpass(self, x: np.ndarray) -> np.ndarray:
        y = np.empty_like(x)
        prev_x = self._hp_prev_x
        prev_y = self._hp_prev_y
        alpha = self.highpass_alpha
        for i, sample in enumerate(x):
            out = sample - prev_x + alpha * prev_y
            y[i] = out
            prev_x = sample
            prev_y = out
        self._hp_prev_x = float(prev_x)
        self._hp_prev_y = float(prev_y)
        return y

    def _process_samples(self, samples: np.ndarray) -> np.ndarray:
        x = samples.astype(np.float64)
        if not len(x):
            return samples

        if self.highpass_enabled:
            x = self._highpass(x)

        block_rms = float(np.sqrt(np.mean(x ** 2)))

        if self.agc_enabled and block_rms > 1.0:
            target_gain = min(self.agc_target_rms / block_rms, self.agc_max_gain)
            self.agc_gain = 0.95 * self.agc_gain + 0.05 * target_gain
            x *= self.agc_gain
        else:
            self.agc_gain = 0.98 * self.agc_gain + 0.02

        if self.noise_gate_enabled and block_rms < self.noise_gate_threshold:
            x *= self.noise_gate_attenuation

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
            if self.adaptive_buffer_enabled and self.latency_trim_enabled:
                keep = max(self.target_queue_samples, n * 2)
                trim_count = len(self.sample_queue) - keep
                if trim_count > max(FRAME_SAMPLES, n):
                    for _ in range(trim_count):
                        self.sample_queue.popleft()
                    self.samples_trimmed += trim_count

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
                self.samples_trimmed += 1
            if n:
                self._last_output_sample = float(out[-1])
        return out

    def close(self):
        if self.wav_writer is not None:
            self.wav_writer.close()


async def find_device(timeout=8.0):
    print(f"Scanning for '{DEVICE_NAME}' ({timeout:.0f}s timeout)...")
    return await BleakScanner.find_device_by_filter(
        lambda d, adv: d.name == DEVICE_NAME or adv.local_name == DEVICE_NAME,
        timeout=timeout,
    )


async def run(address: str | None, save_path: str | None, gain: float):
    if address is None:
        device = await find_device()
        if device is None:
            print(f"Could not find '{DEVICE_NAME}'.", file=sys.stderr)
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
        print(f"Connected to {address}; reported MTU={getattr(client, 'mtu_size', 'unknown')}")
        await client.start_notify(AUDIO_CHAR_UUID, state.handle_notification)
        print("Subscribed to ADPCM audio characteristic. Buffering...")
        for _ in range(150):
            if len(state.sample_queue) >= JITTER_BUFFER_SAMPLES:
                break
            await asyncio.sleep(0.02)
        stream.start()
        print("Playback started. Ctrl+C to stop.")
        last_packets = 0
        try:
            while True:
                await asyncio.sleep(1.0)
                packet_rate = state.packets_received - last_packets
                last_packets = state.packets_received
                print(
                    f"\rpackets={state.packets_received} pps={packet_rate} lost={state.packets_lost} "
                    f"bad={state.bad_packets} decode_fail={state.decode_failures} "
                    f"queued={len(state.sample_queue)} trimmed={state.samples_trimmed} underflows={state.underflows} "
                    f"rms={state.last_rms:.0f} peak={state.last_peak}",
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
    parser.add_argument("--address", default=None)
    parser.add_argument("--save", default=None, metavar="FILE.wav")
    parser.add_argument("--gain", type=float, default=6.0)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.address, args.save, args.gain))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
