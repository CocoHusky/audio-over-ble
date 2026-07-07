#!/usr/bin/env python3
"""Small stable desktop control panel for the raw BLE microphone stream."""

from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import sounddevice as sd
from bleak import BleakClient
from bleak.exc import BleakError

from ble_audio_receiver import (
    AUDIO_CHAR_UUID,
    CHANNELS,
    JITTER_BUFFER_SAMPLES,
    PLAYBACK_BLOCKSIZE,
    SAMPLE_RATE_HZ,
    AudioStreamState,
    find_device,
)


class BleAudioControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BLE Mic Monitor")
        self.root.geometry("760x560")
        self.root.minsize(660, 480)

        self.state: AudioStreamState | None = None
        self.worker: threading.Thread | None = None
        self.stop_requested = threading.Event()
        self.connected = False
        self.save_path: str | None = None

        self.gain = tk.DoubleVar(value=1.0)
        self.muted = tk.BooleanVar(value=False)
        self.auto_reconnect = tk.BooleanVar(value=False)
        self.adaptive_buffer_enabled = tk.BooleanVar(value=True)
        self.target_latency_ms = tk.DoubleVar(value=350.0)
        self.max_latency_ms = tk.DoubleVar(value=1200.0)
        self.declick_enabled = tk.BooleanVar(value=True)
        self.limiter_enabled = tk.BooleanVar(value=True)
        self.agc_enabled = tk.BooleanVar(value=False)
        self.agc_target = tk.DoubleVar(value=1800.0)
        self.agc_max_gain = tk.DoubleVar(value=12.0)

        self.status = tk.StringVar(value="Disconnected")
        self.device = tk.StringVar(value="")
        self.save_label = tk.StringVar(value="Not recording")
        self.packet_label = tk.StringVar(value="packets=0 lost=0 bad=0")
        self.queue_label = tk.StringVar(value="queued=0 concealed=0 underflows=0 refills=0")
        self.input_level_label = tk.StringVar(value="input rms=0 peak=0")
        self.output_level_label = tk.StringVar(value="output rms=0 peak=0")
        self.agc_label = tk.StringVar(value="agc gain=1.0x")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.refresh_stats)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        self.connect_button = ttk.Button(header, text="Connect", command=self.toggle_connection)
        self.connect_button.pack(side="left")
        ttk.Checkbutton(header, text="Auto reconnect", variable=self.auto_reconnect).pack(side="left", padx=12)
        ttk.Label(header, textvariable=self.status).pack(side="left", padx=12)

        playback = ttk.LabelFrame(outer, text=f"Playback ({SAMPLE_RATE_HZ} Hz stable raw PCM)")
        playback.pack(fill="x", pady=(14, 0))
        self._slider(playback, "Gain", self.gain, 0.0, 20.0, "x")
        row = ttk.Frame(playback, padding=(10, 0, 10, 10))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Mute", variable=self.muted, command=self.apply_realtime_controls).pack(side="left")
        ttk.Checkbutton(row, text="Limiter", variable=self.limiter_enabled, command=self.apply_realtime_controls).pack(side="left", padx=16)
        ttk.Checkbutton(row, text="De-click", variable=self.declick_enabled, command=self.apply_realtime_controls).pack(side="left", padx=16)

        stability = ttk.LabelFrame(outer, text="Stability")
        stability.pack(fill="x", pady=(14, 0))
        row = ttk.Frame(stability, padding=(10, 10, 10, 0))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Adaptive buffer", variable=self.adaptive_buffer_enabled, command=self.apply_realtime_controls).pack(side="left")
        self._slider(stability, "Target queue", self.target_latency_ms, 150.0, 1000.0, "ms")
        self._slider(stability, "Max queue", self.max_latency_ms, 300.0, 2500.0, "ms")

        agc = ttk.LabelFrame(outer, text="Optional AGC")
        agc.pack(fill="x", pady=(14, 0))
        row = ttk.Frame(agc, padding=(10, 10, 10, 0))
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Enable AGC", variable=self.agc_enabled, command=self.apply_realtime_controls).pack(side="left")
        ttk.Label(row, textvariable=self.agc_label).pack(side="left", padx=16)
        self._slider(agc, "Target RMS", self.agc_target, 300.0, 5000.0, "")
        self._slider(agc, "Max AGC gain", self.agc_max_gain, 1.0, 20.0, "x")

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

    def apply_realtime_controls(self):
        state = self.state
        if state is None:
            return
        with state.lock:
            state.gain = self.gain.get()
            state.muted = self.muted.get()
            state.adaptive_buffer_enabled = self.adaptive_buffer_enabled.get()
            state.target_queue_samples = int(SAMPLE_RATE_HZ * self.target_latency_ms.get() / 1000)
            state.max_queue_samples = int(SAMPLE_RATE_HZ * self.max_latency_ms.get() / 1000)
            state.declick_enabled = self.declick_enabled.get()
            state.limiter_enabled = self.limiter_enabled.get()
            state.agc_enabled = self.agc_enabled.get()
            state.agc_target_rms = self.agc_target.get()
            state.agc_max_gain = self.agc_max_gain.get()

    def refresh_stats(self):
        self.apply_realtime_controls()
        state = self.state
        if state is not None:
            with state.lock:
                self.packet_label.set(f"packets={state.packets_received} lost={state.packets_lost} bad={state.bad_packets}")
                self.queue_label.set(f"queued={len(state.sample_queue)} concealed={state.samples_dropped} underflows={state.underflows} refills={state.buffer_refills}")
                self.input_level_label.set(f"input rms={state.last_rms:.0f} peak={state.last_peak}")
                self.output_level_label.set(f"output rms={state.output_rms:.0f} peak={state.output_peak}")
                self.agc_label.set(f"agc gain={state.agc_gain:.1f}x")

        if self.worker and not self.worker.is_alive():
            self.worker = None
            self.connected = False
            self.connect_button.config(text="Connect")
            if self.status.get() not in {"Disconnected", "No device found"}:
                self.status.set("Disconnected")

        self.root.after(150, self.refresh_stats)

    def _run_worker(self):
        try:
            asyncio.run(self._run_loop())
        except Exception as exc:
            self.root.after(0, lambda: self.status.set(f"Error: {exc}"))
        finally:
            self.connected = False
            self.state = None

    async def _run_loop(self):
        while not self.stop_requested.is_set():
            await self._run_one_session()
            if not self.auto_reconnect.get() or self.stop_requested.is_set():
                break
            self.root.after(0, lambda: self.status.set("BLE disconnected; reconnecting..."))
            await asyncio.sleep(1.5)

    async def _run_one_session(self):
        self.root.after(0, lambda: self.status.set("Scanning..."))
        device = await find_device(timeout=6.0)
        if device is None:
            self.root.after(0, lambda: self.status.set("No device found"))
            return

        self.root.after(0, lambda: self.device.set(f"Device: {device.address}"))
        state = AudioStreamState(save_path=self.save_path, gain=self.gain.get())
        self.state = state
        self.apply_realtime_controls()

        def audio_callback(outdata, frames, time_info, status):
            del time_info
            if status:
                self.root.after(0, lambda: self.status.set(str(status)))
            outdata[:, 0] = state.pull(frames)

        stream = sd.OutputStream(samplerate=SAMPLE_RATE_HZ, channels=CHANNELS, dtype="int16", callback=audio_callback, blocksize=PLAYBACK_BLOCKSIZE)

        try:
            disconnected = asyncio.Event()
            loop = asyncio.get_running_loop()

            def on_disconnect(_client):
                loop.call_soon_threadsafe(disconnected.set)

            async with BleakClient(device.address, disconnected_callback=on_disconnect) as client:
                self.connected = True
                mtu = getattr(client, "mtu_size", "unknown")
                self.root.after(0, lambda: self.status.set(f"Connected, MTU={mtu}, buffering..."))
                await client.start_notify(AUDIO_CHAR_UUID, state.handle_notification)

                for _ in range(150):
                    if self.stop_requested.is_set() or len(state.sample_queue) >= max(JITTER_BUFFER_SAMPLES, state.target_queue_samples):
                        break
                    await asyncio.sleep(0.02)

                if self.stop_requested.is_set():
                    return

                stream.start()
                self.root.after(0, lambda: self.status.set("Playing"))

                last_packets = -1
                stalled_ticks = 0
                while not self.stop_requested.is_set():
                    try:
                        await asyncio.wait_for(disconnected.wait(), timeout=0.25)
                    except asyncio.TimeoutError:
                        pass

                    if disconnected.is_set() or not client.is_connected:
                        self.root.after(0, lambda: self.status.set("BLE disconnected"))
                        break

                    packets = state.packets_received
                    if packets == last_packets:
                        stalled_ticks += 1
                    else:
                        stalled_ticks = 0
                        if packets > 0:
                            self.root.after(0, lambda: self.status.set("Playing"))
                    last_packets = packets

                    # Important: do not disconnect/reconnect just because audio stalls.
                    # A stall may be a transient notify gap; keeping the BLE link open is
                    # much more stable than flapping the connection.
                    if stalled_ticks == 20:
                        self.root.after(0, lambda: self.status.set("Connected; waiting for audio packets"))

                try:
                    await client.stop_notify(AUDIO_CHAR_UUID)
                except BleakError:
                    pass
        finally:
            self.connected = False
            if stream.active:
                stream.stop()
            stream.close()
            state.close()
            if self.stop_requested.is_set() or not self.auto_reconnect.get():
                self.root.after(0, lambda: self.status.set("Disconnected"))

    def close(self):
        self.disconnect()
        self.root.after(200, self.root.destroy)


def main():
    root = tk.Tk()
    BleAudioControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
