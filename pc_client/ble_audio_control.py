#!/usr/bin/env python3
"""Exact-versioned live control UI for the XIAO BLE mic stream."""

from __future__ import annotations

import asyncio
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk

import numpy as np
import sounddevice as sd
from bleak import BleakClient
from bleak.exc import BleakError

from ble_audio_receiver import (
    AUDIO_CHAR_UUID,
    CODE_VERSION,
    CODEC_NAME,
    DEVICE_NAME,
    JITTER_BUFFER_SAMPLES,
    PACKET_BYTES,
    SAMPLE_RATE_HZ,
    AudioStreamState,
    find_device,
)


class ResampledPlayback:
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
            needed = needed_len - len(self.source)
            samples = self.state.pull(max(needed, 160)).astype(np.float32) / 32768.0
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


def default_output_rate() -> int:
    try:
        device = sd.query_devices(kind="output")
        return int(device.get("default_samplerate") or 48000)
    except Exception:
        return 48000


class BleAudioControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"BLE Mic Monitor - {CODE_VERSION}")
        self.root.geometry("820x620")
        self.root.minsize(760, 560)

        self.state: AudioStreamState | None = None
        self.worker: threading.Thread | None = None
        self.stop_requested = threading.Event()
        self.connected = False
        self.ui_events: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        self.controls_lock = threading.RLock()

        self.gain = tk.DoubleVar(value=3.0)
        self.target_latency_ms = tk.DoubleVar(value=180.0)
        self.max_latency_ms = tk.DoubleVar(value=550.0)
        self.highpass_enabled = tk.BooleanVar(value=True)
        self.limiter_enabled = tk.BooleanVar(value=True)
        self.declick_enabled = tk.BooleanVar(value=True)
        self.agc_enabled = tk.BooleanVar(value=False)
        self.agc_target = tk.DoubleVar(value=1600.0)
        self.agc_max_gain = tk.DoubleVar(value=8.0)
        self.noise_gate_enabled = tk.BooleanVar(value=False)
        self.noise_gate_threshold = tk.DoubleVar(value=180.0)
        self.muted = tk.BooleanVar(value=False)

        self.status = tk.StringVar(value="Disconnected")
        self.version_label = tk.StringVar(
            value=f"PC/UI {CODE_VERSION} | firmware BLE name must be {DEVICE_NAME} | {CODEC_NAME} | {PACKET_BYTES} bytes/packet"
        )
        self.device_label = tk.StringVar(value=f"Expected device: {DEVICE_NAME}")
        self.packet_label = tk.StringVar(value="packets=0 pps=0 lost=0 bad=0 decode_fail=0")
        self.queue_label = tk.StringVar(value="queued=0ms trimmed=0 underflows=0")
        self.level_label = tk.StringVar(value="input rms=0 peak=0 | output rms=0 peak=0")
        self.bad_shape_label = tk.StringVar(value="bad packet shape: none")
        self.agc_label = tk.StringVar(value="agc gain=1.0x")
        self.current_controls_label = tk.StringVar(value="")

        self.last_packet_count = 0
        self.last_packet_rate = 0

        self._build_ui()
        self.apply_realtime_controls()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.refresh_stats)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        version = ttk.LabelFrame(outer, text="Loaded code version")
        version.pack(fill="x")
        ttk.Label(version, textvariable=self.version_label, font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        ttk.Label(version, textvariable=self.device_label).pack(anchor="w", padx=10, pady=(0, 8))

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(12, 0))
        self.connect_button = ttk.Button(header, text="Connect", command=self.toggle_connection)
        self.connect_button.pack(side="left")
        ttk.Button(header, text="Disconnect", command=self.disconnect).pack(side="left", padx=8)
        ttk.Label(header, textvariable=self.status).pack(side="left", padx=12)

        playback = ttk.LabelFrame(outer, text="Live playback controls")
        playback.pack(fill="x", pady=(12, 0))
        self._slider(playback, "Gain", self.gain, 0.0, 12.0, "x")
        self._slider(playback, "Target buffer", self.target_latency_ms, 80.0, 400.0, "ms")
        self._slider(playback, "Max buffer", self.max_latency_ms, 180.0, 900.0, "ms")

        row = ttk.Frame(playback, padding=(10, 8, 10, 10))
        row.pack(fill="x")
        for text, var in (
            ("Mute", self.muted),
            ("High-pass", self.highpass_enabled),
            ("Limiter", self.limiter_enabled),
            ("De-click", self.declick_enabled),
        ):
            ttk.Checkbutton(row, text=text, variable=var, command=self.apply_realtime_controls).pack(side="left", padx=(0, 18))

        agc = ttk.LabelFrame(outer, text="Optional automatic gain")
        agc.pack(fill="x", pady=(12, 0))
        row = ttk.Frame(agc, padding=(10, 8, 10, 0))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Enable AGC", variable=self.agc_enabled, command=self.apply_realtime_controls).pack(side="left")
        ttk.Label(row, textvariable=self.agc_label).pack(side="left", padx=12)
        self._slider(agc, "AGC target RMS", self.agc_target, 300.0, 4000.0, "")
        self._slider(agc, "AGC max gain", self.agc_max_gain, 1.0, 12.0, "x")

        gate = ttk.LabelFrame(outer, text="Optional soft noise gate")
        gate.pack(fill="x", pady=(12, 0))
        row = ttk.Frame(gate, padding=(10, 8, 10, 0))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Enable noise gate", variable=self.noise_gate_enabled, command=self.apply_realtime_controls).pack(side="left")
        self._slider(gate, "Gate threshold", self.noise_gate_threshold, 20.0, 900.0, "")

        stats = ttk.LabelFrame(outer, text="Live status")
        stats.pack(fill="both", expand=True, pady=(12, 0))
        stats_inner = ttk.Frame(stats, padding=10)
        stats_inner.pack(fill="both", expand=True)
        ttk.Label(stats_inner, textvariable=self.packet_label).pack(anchor="w")
        ttk.Label(stats_inner, textvariable=self.queue_label).pack(anchor="w", pady=(4, 0))
        ttk.Label(stats_inner, textvariable=self.level_label).pack(anchor="w", pady=(4, 0))
        ttk.Label(stats_inner, textvariable=self.bad_shape_label).pack(anchor="w", pady=(4, 0))
        ttk.Label(stats_inner, textvariable=self.current_controls_label).pack(anchor="w", pady=(12, 0))

    def _slider(self, parent, label, variable, start, end, suffix):
        row = ttk.Frame(parent, padding=(10, 8, 10, 0))
        row.pack(fill="x")
        ttk.Label(row, text=label, width=16).pack(side="left")
        scale = ttk.Scale(
            row,
            from_=start,
            to=end,
            orient="horizontal",
            variable=variable,
            command=lambda _value: self.apply_realtime_controls(),
        )
        scale.pack(side="left", fill="x", expand=True, padx=8)
        value = ttk.Label(row, width=12)
        value.pack(side="left")

        def update_label():
            current = variable.get()
            if suffix == "x":
                value.config(text=f"{current:.1f}x")
            elif suffix == "ms":
                value.config(text=f"{current:.0f}ms")
            else:
                value.config(text=f"{current:.0f}")
            self.root.after(150, update_label)

        update_label()

    def toggle_connection(self):
        if self.worker and self.worker.is_alive():
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        if self.worker and self.worker.is_alive():
            return
        self.apply_realtime_controls()
        self.stop_requested.clear()
        self.status.set(f"Scanning for exact {DEVICE_NAME}...")
        self.connect_button.config(text="Disconnect")
        self.worker = threading.Thread(target=self._run_worker, daemon=True)
        self.worker.start()

    def disconnect(self):
        self.stop_requested.set()
        self.connected = False
        self.status.set("Disconnecting...")
        self.connect_button.config(text="Connect")

    def _control_snapshot(self) -> dict:
        return {
            "gain": self.gain.get(),
            "target_latency_ms": self.target_latency_ms.get(),
            "max_latency_ms": self.max_latency_ms.get(),
            "highpass_enabled": self.highpass_enabled.get(),
            "limiter_enabled": self.limiter_enabled.get(),
            "declick_enabled": self.declick_enabled.get(),
            "agc_enabled": self.agc_enabled.get(),
            "agc_target": self.agc_target.get(),
            "agc_max_gain": self.agc_max_gain.get(),
            "noise_gate_enabled": self.noise_gate_enabled.get(),
            "noise_gate_threshold": self.noise_gate_threshold.get(),
            "muted": self.muted.get(),
        }

    def apply_realtime_controls(self):
        values = self._control_snapshot()
        with self.controls_lock:
            self.controls = dict(values)
        state = self.state
        if state is not None:
            with state.lock:
                state.gain = values["gain"]
                state.target_queue_samples = int(SAMPLE_RATE_HZ * values["target_latency_ms"] / 1000)
                state.max_queue_samples = int(SAMPLE_RATE_HZ * values["max_latency_ms"] / 1000)
                state.highpass_enabled = values["highpass_enabled"]
                state.limiter_enabled = values["limiter_enabled"]
                state.declick_enabled = values["declick_enabled"]
                state.agc_enabled = values["agc_enabled"]
                state.agc_target_rms = values["agc_target"]
                state.agc_max_gain = values["agc_max_gain"]
                state.noise_gate_enabled = values["noise_gate_enabled"]
                state.noise_gate_threshold = values["noise_gate_threshold"]
                state.muted = values["muted"]
        self.current_controls_label.set(
            f"controls: gain={values['gain']:.1f}x, buffer={values['target_latency_ms']:.0f}/{values['max_latency_ms']:.0f}ms, "
            f"HP={values['highpass_enabled']}, AGC={values['agc_enabled']}, gate={values['noise_gate_enabled']}"
        )

    def _post_ui(self, key: str, value: str):
        self.ui_events.put((key, value))

    def _drain_ui_events(self):
        while True:
            try:
                key, value = self.ui_events.get_nowait()
            except queue.Empty:
                break
            if key == "status":
                self.status.set(value)
            elif key == "device":
                self.device_label.set(value)

    def refresh_stats(self):
        self._drain_ui_events()
        self.apply_realtime_controls()
        state = self.state
        if state is not None:
            with state.lock:
                packet_rate = state.packets_received - self.last_packet_count
                self.last_packet_count = state.packets_received
                self.last_packet_rate = packet_rate
                queued_ms = 1000.0 * len(state.sample_queue) / SAMPLE_RATE_HZ
                self.packet_label.set(
                    f"packets={state.packets_received} pps={packet_rate * 10} lost={state.packets_lost} "
                    f"bad={state.bad_packets} decode_fail={state.decode_failures}"
                )
                self.queue_label.set(
                    f"queued={len(state.sample_queue)} ({queued_ms:.0f}ms) trimmed={state.samples_trimmed} "
                    f"underflows={state.underflows} refills={state.buffer_refills}"
                )
                self.level_label.set(
                    f"input rms={state.last_rms:.0f} peak={state.last_peak} | "
                    f"output rms={state.output_rms:.0f} peak={state.output_peak}"
                )
                self.bad_shape_label.set(f"bad packet shape: {state.last_bad_shape}")
                self.agc_label.set(f"agc gain={state.agc_gain:.1f}x")

        if self.worker and not self.worker.is_alive():
            self.worker = None
            self.connected = False
            self.connect_button.config(text="Connect")
            if self.status.get().startswith("Disconnecting"):
                self.status.set("Disconnected")

        self.root.after(100, self.refresh_stats)

    def _run_worker(self):
        try:
            asyncio.run(self._run_session())
        except Exception as exc:
            self._post_ui("status", f"Error: {exc}")
        finally:
            self.connected = False
            self.state = None

    async def _run_session(self):
        self._post_ui("status", f"Scanning for exact {DEVICE_NAME}...")
        device = await find_device(timeout=8.0)
        if device is None:
            self._post_ui("status", f"No exact {DEVICE_NAME}. Flash firmware for {CODE_VERSION}.")
            self._post_ui("device", f"Expected device: {DEVICE_NAME} | PC/UI {CODE_VERSION}")
            return

        output_rate = default_output_rate()
        self._post_ui("device", f"Connected device: {device.name or DEVICE_NAME} @ {device.address} | expected {DEVICE_NAME}")

        with self.controls_lock:
            controls = dict(self.controls)
        state = AudioStreamState(gain=controls["gain"])
        self.state = state
        self.apply_realtime_controls()
        player = ResampledPlayback(state, output_rate)

        def audio_callback(outdata, frames, time_info, status):
            del time_info
            if status:
                self._post_ui("status", str(status))
            outdata[:, 0] = player.pull(frames)

        stream = None
        try:
            disconnected = asyncio.Event()
            loop = asyncio.get_running_loop()

            def on_disconnect(_client):
                loop.call_soon_threadsafe(disconnected.set)

            async with BleakClient(device.address, disconnected_callback=on_disconnect) as client:
                self.connected = True
                mtu = getattr(client, "mtu_size", "unknown")
                self._post_ui("status", f"Connected. MTU={mtu}. Buffering exact {CODE_VERSION}...")
                await client.start_notify(AUDIO_CHAR_UUID, state.handle_notification)

                for _ in range(100):
                    if self.stop_requested.is_set() or len(state.sample_queue) >= max(JITTER_BUFFER_SAMPLES, state.target_queue_samples):
                        break
                    await asyncio.sleep(0.01)

                if self.stop_requested.is_set():
                    return

                stream = sd.OutputStream(
                    samplerate=output_rate,
                    channels=1,
                    dtype="float32",
                    callback=audio_callback,
                    blocksize=256,
                    latency="low",
                )
                stream.start()
                self._post_ui("status", f"Playing. PC/UI {CODE_VERSION}. Output={output_rate} Hz")

                while not self.stop_requested.is_set():
                    try:
                        await asyncio.wait_for(disconnected.wait(), timeout=0.25)
                    except asyncio.TimeoutError:
                        pass
                    if disconnected.is_set() or not client.is_connected:
                        self._post_ui("status", "BLE disconnected")
                        break

                try:
                    await client.stop_notify(AUDIO_CHAR_UUID)
                except BleakError:
                    pass
        finally:
            if stream is not None:
                try:
                    if stream.active:
                        stream.stop()
                    stream.close()
                except Exception:
                    pass
            state.close()
            self.connected = False
            if self.stop_requested.is_set():
                self._post_ui("status", "Disconnected")

    def close(self):
        self.disconnect()
        self.root.after(200, self.root.destroy)


def main():
    root = tk.Tk()
    BleAudioControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
