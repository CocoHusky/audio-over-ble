#!/usr/bin/env python3
"""Simple desktop monitor for hearing the XIAO mic over BLE ADPCM."""

from __future__ import annotations

import asyncio
import math
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import numpy as np
import sounddevice as sd
from bleak import BleakClient
from bleak.exc import BleakError

from ble_audio_receiver import (
    AUDIO_CHAR_UUID,
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
            new_samples = self.state.pull(max(needed, 256)).astype(np.float32) / 32768.0
            self.source = np.concatenate((self.source, new_samples))

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


class BleAudioControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BLE Mic Monitor")
        self.root.geometry("780x660")
        self.root.minsize(680, 560)

        self.state: AudioStreamState | None = None
        self.worker: threading.Thread | None = None
        self.stop_requested = threading.Event()
        self.connected = False
        self.save_path: str | None = None
        self.ui_events: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        self.controls_lock = threading.RLock()
        self.controls = {
            "gain": 6.0,
            "muted": False,
            "auto_reconnect": False,
            "adaptive_buffer_enabled": True,
            "latency_trim_enabled": True,
            "target_latency_ms": 350.0,
            "max_latency_ms": 1200.0,
            "highpass_enabled": True,
            "noise_gate_enabled": False,
            "noise_gate_threshold": 120.0,
            "declick_enabled": True,
            "limiter_enabled": True,
            "agc_enabled": False,
            "agc_target": 2200.0,
            "agc_max_gain": 24.0,
        }

        self.gain = tk.DoubleVar(value=6.0)
        self.muted = tk.BooleanVar(value=False)
        self.auto_reconnect = tk.BooleanVar(value=False)
        self.adaptive_buffer_enabled = tk.BooleanVar(value=True)
        self.latency_trim_enabled = tk.BooleanVar(value=True)
        self.target_latency_ms = tk.DoubleVar(value=350.0)
        self.max_latency_ms = tk.DoubleVar(value=1200.0)
        self.highpass_enabled = tk.BooleanVar(value=True)
        self.noise_gate_enabled = tk.BooleanVar(value=False)
        self.noise_gate_threshold = tk.DoubleVar(value=120.0)
        self.declick_enabled = tk.BooleanVar(value=True)
        self.limiter_enabled = tk.BooleanVar(value=True)
        self.agc_enabled = tk.BooleanVar(value=False)
        self.agc_target = tk.DoubleVar(value=2200.0)
        self.agc_max_gain = tk.DoubleVar(value=24.0)

        self.status = tk.StringVar(value="Disconnected")
        self.device = tk.StringVar(value="")
        self.save_label = tk.StringVar(value="Not recording")
        self.packet_label = tk.StringVar(value="packets=0 lost=0 bad=0 decode_fail=0")
        self.queue_label = tk.StringVar(value="queued=0 trimmed=0 concealed=0 underflows=0 refills=0")
        self.input_level_label = tk.StringVar(value="input rms=0 peak=0")
        self.output_level_label = tk.StringVar(value="output rms=0 peak=0")
        self.agc_label = tk.StringVar(value="agc gain=1.0x")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.refresh_stats)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        self.connect_button = ttk.Button(header, text="Connect", command=self.toggle_connection)
        self.connect_button.pack(side="left")
        ttk.Checkbutton(header, text="Auto reconnect", variable=self.auto_reconnect).pack(side="left", padx=12)
        ttk.Label(header, textvariable=self.status).pack(side="left", padx=12)

        playback = ttk.LabelFrame(outer, text=f"Playback ({SAMPLE_RATE_HZ} Hz ADPCM from device, Mac output auto-matched)")
        playback.pack(fill="x", pady=(14, 0))
        self._slider(playback, "Gain", self.gain, 0.0, 24.0, "x")
        row = ttk.Frame(playback, padding=(10, 0, 10, 10))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Mute", variable=self.muted, command=self.apply_realtime_controls).pack(side="left")
        ttk.Checkbutton(row, text="Limiter", variable=self.limiter_enabled, command=self.apply_realtime_controls).pack(side="left", padx=16)
        ttk.Checkbutton(row, text="De-click", variable=self.declick_enabled, command=self.apply_realtime_controls).pack(side="left", padx=16)

        cleanup = ttk.LabelFrame(outer, text="Noise cleanup")
        cleanup.pack(fill="x", pady=(14, 0))
        row = ttk.Frame(cleanup, padding=(10, 10, 10, 0))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="High-pass / DC cleanup", variable=self.highpass_enabled, command=self.apply_realtime_controls).pack(side="left")
        ttk.Checkbutton(row, text="Noise gate", variable=self.noise_gate_enabled, command=self.apply_realtime_controls).pack(side="left", padx=16)
        self._slider(cleanup, "Gate threshold", self.noise_gate_threshold, 20.0, 900.0, "")

        stability = ttk.LabelFrame(outer, text="Stability")
        stability.pack(fill="x", pady=(14, 0))
        row = ttk.Frame(stability, padding=(10, 10, 10, 0))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Adaptive buffer", variable=self.adaptive_buffer_enabled, command=self.apply_realtime_controls).pack(side="left")
        ttk.Checkbutton(row, text="Trim old queued audio", variable=self.latency_trim_enabled, command=self.apply_realtime_controls).pack(side="left", padx=16)
        self._slider(stability, "Target queue", self.target_latency_ms, 150.0, 1000.0, "ms")
        self._slider(stability, "Max queue", self.max_latency_ms, 300.0, 2500.0, "ms")

        agc = ttk.LabelFrame(outer, text="Optional AGC")
        agc.pack(fill="x", pady=(14, 0))
        row = ttk.Frame(agc, padding=(10, 10, 10, 0))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Enable AGC", variable=self.agc_enabled, command=self.apply_realtime_controls).pack(side="left")
        ttk.Label(row, textvariable=self.agc_label).pack(side="left", padx=16)
        self._slider(agc, "Target RMS", self.agc_target, 300.0, 6000.0, "")
        self._slider(agc, "Max AGC gain", self.agc_max_gain, 1.0, 32.0, "x")

        record = ttk.LabelFrame(outer, text="Recording")
        record.pack(fill="x", pady=(14, 0))
        row = ttk.Frame(record, padding=10)
        row.pack(fill="x")
        ttk.Button(row, text="Choose WAV", command=self.choose_save_path).pack(side="left")
        ttk.Button(row, text="Clear", command=self.clear_save_path).pack(side="left", padx=8)
        ttk.Label(row, textvariable=self.save_label).pack(side="left", padx=8)

        stats = ttk.LabelFrame(outer, text="Live Stats")
        stats.pack(fill="both", expand=True, pady=(14, 0))
        stats_inner = ttk.Frame(stats, padding=10)
        stats_inner.pack(fill="both", expand=True)
        ttk.Label(stats_inner, textvariable=self.device).pack(anchor="w")
        ttk.Label(stats_inner, textvariable=self.packet_label).pack(anchor="w", pady=(8, 0))
        ttk.Label(stats_inner, textvariable=self.queue_label).pack(anchor="w")
        ttk.Label(stats_inner, textvariable=self.input_level_label).pack(anchor="w")
        ttk.Label(stats_inner, textvariable=self.output_level_label).pack(anchor="w")

    def _slider(self, parent, label, variable, start, end, suffix):
        row = ttk.Frame(parent, padding=(10, 8, 10, 0))
        row.pack(fill="x")
        ttk.Label(row, text=label, width=16).pack(side="left")
        scale = ttk.Scale(row, from_=start, to=end, orient="horizontal", variable=variable, command=lambda _value: self.apply_realtime_controls())
        scale.pack(side="left", fill="x", expand=True, padx=8)
        value = ttk.Label(row, width=10)
        value.pack(side="left")

        def update_label():
            current = variable.get()
            if suffix == "x":
                text = f"{current:.1f}x"
            elif current < 10 and suffix == "":
                text = f"{current:.2f}"
            else:
                text = f"{current:.0f}{suffix}"
            value.config(text=text)
            self.root.after(150, update_label)

        update_label()

    def toggle_connection(self):
        if self.connected or self.worker:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        self.apply_realtime_controls()
        self.stop_requested.clear()
        self.status.set("Scanning...")
        self.connect_button.config(text="Disconnect")
        self.worker = threading.Thread(target=self._run_worker, daemon=True)
        self.worker.start()

    def disconnect(self):
        self.status.set("Disconnecting...")
        self.stop_requested.set()
        self.connected = False
        self.connect_button.config(text="Connect")

    def choose_save_path(self):
        if self.worker:
            return
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV files", "*.wav"), ("All files", "*.*")])
        if path:
            self.save_path = path
            self.save_label.set(path)

    def clear_save_path(self):
        if self.worker:
            return
        self.save_path = None
        self.save_label.set("Not recording")

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
                self.device.set(value)

    def _control_snapshot(self):
        with self.controls_lock:
            return dict(self.controls)

    def apply_realtime_controls(self):
        values = {
            "gain": self.gain.get(),
            "muted": self.muted.get(),
            "auto_reconnect": self.auto_reconnect.get(),
            "adaptive_buffer_enabled": self.adaptive_buffer_enabled.get(),
            "latency_trim_enabled": self.latency_trim_enabled.get(),
            "target_latency_ms": self.target_latency_ms.get(),
            "max_latency_ms": self.max_latency_ms.get(),
            "highpass_enabled": self.highpass_enabled.get(),
            "noise_gate_enabled": self.noise_gate_enabled.get(),
            "noise_gate_threshold": self.noise_gate_threshold.get(),
            "declick_enabled": self.declick_enabled.get(),
            "limiter_enabled": self.limiter_enabled.get(),
            "agc_enabled": self.agc_enabled.get(),
            "agc_target": self.agc_target.get(),
            "agc_max_gain": self.agc_max_gain.get(),
        }
        with self.controls_lock:
            self.controls.update(values)
        state = self.state
        if state is None:
            return
        with state.lock:
            state.gain = values["gain"]
            state.muted = values["muted"]
            state.adaptive_buffer_enabled = values["adaptive_buffer_enabled"]
            state.latency_trim_enabled = values["latency_trim_enabled"]
            state.target_queue_samples = int(SAMPLE_RATE_HZ * values["target_latency_ms"] / 1000)
            state.max_queue_samples = int(SAMPLE_RATE_HZ * values["max_latency_ms"] / 1000)
            state.highpass_enabled = values["highpass_enabled"]
            state.noise_gate_enabled = values["noise_gate_enabled"]
            state.noise_gate_threshold = values["noise_gate_threshold"]
            state.declick_enabled = values["declick_enabled"]
            state.limiter_enabled = values["limiter_enabled"]
            state.agc_enabled = values["agc_enabled"]
            state.agc_target_rms = values["agc_target"]
            state.agc_max_gain = values["agc_max_gain"]

    def refresh_stats(self):
        self._drain_ui_events()
        self.apply_realtime_controls()
        state = self.state
        if state is not None:
            with state.lock:
                self.packet_label.set(f"packets={state.packets_received} lost={state.packets_lost} bad={state.bad_packets} decode_fail={state.decode_failures}")
                self.queue_label.set(f"queued={len(state.sample_queue)} trimmed={state.samples_trimmed} concealed={state.samples_dropped} underflows={state.underflows} refills={state.buffer_refills}")
                self.input_level_label.set(f"input rms={state.last_rms:.0f} peak={state.last_peak}")
                self.output_level_label.set(f"output rms={state.output_rms:.0f} peak={state.output_peak}")
                self.agc_label.set(f"agc gain={state.agc_gain:.1f}x")

        if self.worker and not self.worker.is_alive():
            self.worker = None
            self.connected = False
            self.connect_button.config(text="Connect")
            if self.status.get() not in {"Disconnected", "No device found"}:
                self.status.set("Disconnected")

        self.root.after(100, self.refresh_stats)

    def _run_worker(self):
        try:
            asyncio.run(self._run_loop())
        except Exception as exc:
            self._post_ui("status", f"Error: {exc}")
        finally:
            self.connected = False
            self.state = None

    async def _run_loop(self):
        while not self.stop_requested.is_set():
            await self._run_one_session()
            controls = self._control_snapshot()
            if not controls["auto_reconnect"] or self.stop_requested.is_set():
                break
            self._post_ui("status", "BLE disconnected; reconnecting...")
            await asyncio.sleep(1.5)

    async def _run_one_session(self):
        self._post_ui("status", "Scanning...")
        device = await find_device(timeout=6.0)
        if device is None:
            self._post_ui("status", "No device found")
            return

        self._post_ui("device", f"Device: {device.address}")
        controls = self._control_snapshot()
        state = AudioStreamState(save_path=self.save_path, gain=controls["gain"])
        self.state = state
        self.apply_state_controls_from_snapshot(state, controls)

        output_rate = default_output_rate()
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
                self._post_ui("status", f"Connected, MTU={mtu}, buffering...")
                await client.start_notify(AUDIO_CHAR_UUID, state.handle_notification)

                for _ in range(150):
                    if self.stop_requested.is_set() or len(state.sample_queue) >= max(JITTER_BUFFER_SAMPLES, state.target_queue_samples):
                        break
                    await asyncio.sleep(0.02)

                if self.stop_requested.is_set():
                    return

                stream = sd.OutputStream(
                    samplerate=output_rate,
                    channels=1,
                    dtype="float32",
                    callback=audio_callback,
                    blocksize=0,
                    latency="high",
                )
                stream.start()
                self._post_ui("status", f"Playing to Mac output at {output_rate} Hz")

                last_packets = -1
                stalled_ticks = 0
                while not self.stop_requested.is_set():
                    try:
                        await asyncio.wait_for(disconnected.wait(), timeout=0.25)
                    except asyncio.TimeoutError:
                        pass

                    if disconnected.is_set() or not client.is_connected:
                        self._post_ui("status", "BLE disconnected")
                        break

                    packets = state.packets_received
                    if packets == last_packets:
                        stalled_ticks += 1
                    else:
                        stalled_ticks = 0
                        if packets > 0:
                            self._post_ui("status", f"Playing to Mac output at {output_rate} Hz")
                    last_packets = packets

                    if stalled_ticks == 20:
                        self._post_ui("status", "Connected; waiting for audio packets")

                try:
                    await client.stop_notify(AUDIO_CHAR_UUID)
                except BleakError:
                    pass
        finally:
            self.connected = False
            if stream is not None:
                try:
                    if stream.active:
                        stream.stop()
                    stream.close()
                except Exception:
                    pass
            state.close()
            controls = self._control_snapshot()
            if self.stop_requested.is_set() or not controls["auto_reconnect"]:
                self._post_ui("status", "Disconnected")

    def apply_state_controls_from_snapshot(self, state: AudioStreamState, values: dict):
        with state.lock:
            state.gain = values["gain"]
            state.muted = values["muted"]
            state.adaptive_buffer_enabled = values["adaptive_buffer_enabled"]
            state.latency_trim_enabled = values["latency_trim_enabled"]
            state.target_queue_samples = int(SAMPLE_RATE_HZ * values["target_latency_ms"] / 1000)
            state.max_queue_samples = int(SAMPLE_RATE_HZ * values["max_latency_ms"] / 1000)
            state.highpass_enabled = values["highpass_enabled"]
            state.noise_gate_enabled = values["noise_gate_enabled"]
            state.noise_gate_threshold = values["noise_gate_threshold"]
            state.declick_enabled = values["declick_enabled"]
            state.limiter_enabled = values["limiter_enabled"]
            state.agc_enabled = values["agc_enabled"]
            state.agc_target_rms = values["agc_target"]
            state.agc_max_gain = values["agc_max_gain"]

    def close(self):
        self.disconnect()
        self.root.after(200, self.root.destroy)


def main():
    root = tk.Tk()
    BleAudioControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
