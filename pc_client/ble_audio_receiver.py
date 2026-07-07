#!/usr/bin/env python3
"""
audio-over-ble — PC client
---------------------------
Connects to the XIAO nRF52840 Sense over BLE, subscribes to the audio
characteristic, decodes Opus frames, and plays live through your default
output device.

Packet format expected (must match firmware):
    [uint16 LE seq][uint16 LE decoded_samples][uint16 LE opus_len][opus payload...]

Usage:
    python ble_audio_receiver.py                 # auto-scan for the device
    python ble_audio_receiver.py --address XX:XX:XX:XX:XX:XX
    python ble_audio_receiver.py --save out.wav   # also record to a WAV file

Install deps first:
    pip install -r requirements.txt
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

from opus_codec import OpusDecoder, OpusError

# Must match the firmware .ino exactly.
SERVICE_UUID = "04a77077-8d9a-4cd2-bf83-f7adafa02251"
AUDIO_CHAR_UUID = "30fafbf6-9ec3-41ae-86b9-60cbf31328bb"
DEVICE_NAME = "CocoHusky-AudioStream"

SAMPLE_RATE_HZ = 16000
CHANNELS = 1

# How much audio to buffer before starting playback. Bigger = more
# resistant to BLE jitter, but adds latency. 200ms is a reasonable start.
JITTER_BUFFER_MS = 200
JITTER_BUFFER_SAMPLES = int(SAMPLE_RATE_HZ * JITTER_BUFFER_MS / 1000)
PLAYBACK_BLOCKSIZE = 512


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
        self.started_playback = False
        self.refilling_buffer = False
        self.gain = gain
        self.muted = False
        self.adaptive_buffer_enabled = True
        self.target_queue_samples = JITTER_BUFFER_SAMPLES
        self.highpass_enabled = False
        self.highpass_cutoff_hz = 80.0
        self.lowpass_enabled = False
        self.lowpass_cutoff_hz = 7000.0
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
        self._hp_prev_x = 0.0
        self._hp_prev_y = 0.0
        self._lp_prev_y = 0.0
        self._last_processed_tail = np.zeros(0, dtype=np.int16)
        self._last_output_sample = 0.0
        self.decoder = OpusDecoder(SAMPLE_RATE_HZ, CHANNELS)
        self.last_rms = 0.0
        self.last_peak = 0
        self.output_rms = 0.0
        self.output_peak = 0
        self.wav_writer = None
        if save_path:
            self.wav_writer = wave.open(save_path, "wb")
            self.wav_writer.setnchannels(CHANNELS)
            self.wav_writer.setsampwidth(2)  # 16-bit
            self.wav_writer.setframerate(SAMPLE_RATE_HZ)

    def handle_notification(self, _handle, data: bytearray):
        if len(data) < 6:
            return
        seq = data[0] | (data[1] << 8)
        frame_samples = data[2] | (data[3] << 8)
        payload_len = data[4] | (data[5] << 8)
        if frame_samples <= 0 or payload_len <= 0 or len(data) < 6 + payload_len:
            return

        payload = bytes(data[6:6 + payload_len])
        try:
            sample_array = self.decoder.decode(payload, frame_samples)
        except OpusError:
            return

        if len(sample_array):
            self.last_rms = float(np.sqrt(np.mean(sample_array.astype(np.float64) ** 2)))
            self.last_peak = int(np.max(np.abs(sample_array.astype(np.int32))))

        with self.lock:
            if self.last_seq is not None:
                expected = (self.last_seq + 1) & 0xFFFF
                if seq != expected:
                    gap = (seq - expected) & 0xFFFF
                    if gap < 1000:  # sanity bound, ignore wraparound weirdness
                        self.packets_lost += gap
                        for _ in range(gap):
                            try:
                                concealment = self.decoder.decode(None, frame_samples)
                            except OpusError:
                                concealment = self._conceal_samples(frame_samples)
                            processed_concealment = self._process_samples(concealment)
                            self.sample_queue.extend(processed_concealment.tolist())
                            self.samples_dropped += len(processed_concealment)
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

        if self.highpass_enabled and self.highpass_cutoff_hz > 0:
            rc = 1.0 / (2.0 * np.pi * self.highpass_cutoff_hz)
            dt = 1.0 / SAMPLE_RATE_HZ
            alpha = rc / (rc + dt)
            y = np.empty_like(x)
            prev_x = self._hp_prev_x
            prev_y = self._hp_prev_y
            for i, sample in enumerate(x):
                prev_y = alpha * (prev_y + sample - prev_x)
                prev_x = sample
                y[i] = prev_y
            self._hp_prev_x = float(prev_x)
            self._hp_prev_y = float(prev_y)
            x = y

        if self.lowpass_enabled and 0 < self.lowpass_cutoff_hz < SAMPLE_RATE_HZ / 2:
            rc = 1.0 / (2.0 * np.pi * self.lowpass_cutoff_hz)
            dt = 1.0 / SAMPLE_RATE_HZ
            alpha = dt / (rc + dt)
            y = np.empty_like(x)
            prev_y = self._lp_prev_y
            for i, sample in enumerate(x):
                prev_y = prev_y + alpha * (sample - prev_y)
                y[i] = prev_y
            self._lp_prev_y = float(prev_y)
            x = y

        block_rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0

        if self.noise_suppression_enabled and len(x):
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

        if self.compressor_enabled and len(x):
            abs_x = np.abs(x)
            over = abs_x > self.compressor_threshold
            compressed = np.copy(abs_x)
            compressed[over] = (
                self.compressor_threshold
                + (abs_x[over] - self.compressor_threshold) / max(self.compressor_ratio, 1.0)
            )
            x = np.sign(x) * compressed * self.compressor_makeup_gain

        if self.muted:
            x *= 0.0
        else:
            x *= self.gain

        if self.declick_enabled and len(x):
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

        self.output_rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
        self.output_peak = int(np.max(np.abs(x))) if len(x) else 0
        if len(x):
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
        """Pop up to n samples for playback; fade-conceal if starved."""
        out = np.empty(n, dtype=np.int16)
        with self.lock:
            if self.adaptive_buffer_enabled:
                low_watermark = max(n * 2, self.target_queue_samples // 3)
                if len(self.sample_queue) < low_watermark:
                    self.refilling_buffer = True
                    self.buffer_refills += 1
                if self.refilling_buffer:
                    if len(self.sample_queue) >= self.target_queue_samples:
                        self.refilling_buffer = False
                    else:
                        out[:] = self._conceal_samples(n)
                        if n:
                            self._last_output_sample = float(out[-1])
                        return out

            avail = min(n, len(self.sample_queue))
            for i in range(avail):
                out[i] = self.sample_queue.popleft()
            if avail < n:
                self.underflows += 1
                missing = n - avail
                tail = self._conceal_samples(missing)
                out[avail:] = tail
            if self.adaptive_buffer_enabled:
                overflow = len(self.sample_queue) - self.max_queue_samples
                for _ in range(max(0, overflow)):
                    self.sample_queue.popleft()
            if n:
                self._last_output_sample = float(out[-1])
        return out

    def close(self):
        if self.wav_writer is not None:
            self.wav_writer.close()
        self.decoder.close()


async def find_device(timeout=8.0):
    print(f"Scanning for '{DEVICE_NAME}' ({timeout:.0f}s timeout)...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: d.name == DEVICE_NAME or (adv.local_name == DEVICE_NAME),
        timeout=timeout,
    )
    return device


async def run(address: str | None, save_path: str | None, gain: float):
    if address is None:
        device = await find_device()
        if device is None:
            print(f"Could not find a device named '{DEVICE_NAME}'. "
                  f"Is the XIAO powered on and advertising?", file=sys.stderr)
            sys.exit(1)
        address = device.address
        print(f"Found device at {address}")

    state = AudioStreamState(save_path=save_path, gain=gain)

    def audio_callback(outdata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        chunk = state.pull(frames)
        outdata[:, 0] = chunk

    stream = sd.OutputStream(
        samplerate=SAMPLE_RATE_HZ,
        channels=CHANNELS,
        dtype="int16",
        callback=audio_callback,
        blocksize=PLAYBACK_BLOCKSIZE,
    )

    async with BleakClient(address) as client:
        print(f"Connected to {address}")
        await client.start_notify(AUDIO_CHAR_UUID, state.handle_notification)
        print("Subscribed to audio characteristic. Buffering...")

        # Wait until we've got enough samples queued before starting
        # playback, so the callback doesn't starve immediately.
        while len(state.sample_queue) < JITTER_BUFFER_SAMPLES:
            await asyncio.sleep(0.02)

        stream.start()
        print("Playback started. Ctrl+C to stop.")

        try:
            while True:
                await asyncio.sleep(1.0)
                print(
                    f"\rpackets={state.packets_received} "
                    f"lost={state.packets_lost} "
                    f"queued_samples={len(state.sample_queue)} "
                    f"dropped_samples_concealed={state.samples_dropped} "
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
