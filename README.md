# audio-over-ble

Stream raw microphone audio from a Seeed XIAO nRF52840 Sense's onboard PDM microphone to a PC over BLE, and play it live.

This is the **known-good raw 16-bit PCM baseline**. The XIAO captures 16 kHz mono PCM and sends it directly over a custom BLE notify characteristic. There is no Opus firmware build, no host-side Opus build, and no audio compression in this path. That makes it easier to debug true microphone quality before adding compression back later.

The previous real-Opus experiment is archived on `archive/real-opus-implementation`. Use `main` for bring-up, flashing, and baseline audio testing.

## Hardware

- Seeed XIAO nRF52840 **Sense** (needs the onboard PDM mic — the non-Sense variant does not have one)
- USB-C cable
- Any PC with Bluetooth 4.2+ (BLE)

## Pull, build, flash, test

Use the Nordic nRF Connect SDK terminal for firmware commands so `west` can find the Zephyr workspace and flash runner.

```bash
cd /Users/alexburton/Documents/GitHub/audio-over-ble
git fetch origin
git checkout main
git pull --ff-only

cd firmware/xiao_ble_mic_stream
rm -rf build
west build -p always -b xiao_ble/nrf52840/sense
west flash
```

If your installed SDK does not recognize the qualified board target, try:

```bash
west build -p always -b xiao_ble
west flash
```

Then set up and run the PC client:

```bash
cd /Users/alexburton/Documents/GitHub/audio-over-ble/pc_client
bash setup_pc.sh
source venv/bin/activate
python ble_audio_control.py
```

For the simpler terminal receiver:

```bash
python ble_audio_receiver.py --save capture.wav
```

The device should advertise as `CocoHusky-AudioStream`. The PC client should connect, buffer raw PCM audio, and show packet/loss counters increasing.

## Firmware setup (`firmware/xiao_ble_mic_stream/`)

The firmware is a Nordic nRF Connect SDK application built on Zephyr. It no longer uses Arduino.

Open the serial console at 115200 baud. You should see the device advertising as `CocoHusky-AudioStream`.

## PC client setup (`pc_client/`)

The helper script recreates the local Python environment after a clean or fresh clone:

```bash
cd pc_client
bash setup_pc.sh
source venv/bin/activate
python ble_audio_control.py
```

It installs the required packages from `requirements.txt` and compile-checks the client scripts. If `sounddevice` fails to install on macOS, install PortAudio first:

```bash
brew install portaudio
bash setup_pc.sh
```

## How it is structured

- **Firmware** captures PDM samples at 16 kHz mono with Zephyr's DMIC driver and sends raw 16-bit little-endian PCM frames over BLE notifications.
- **Packet format** is `[uint16 seq][uint16 sample_count][int16 PCM samples...]`.
- **PC client** uses `bleak` to subscribe to notifications, converts the PCM payload directly into NumPy `int16` samples, queues them, and `sounddevice` pulls from that queue in a real-time audio callback.

## Bandwidth math

Raw 16 kHz mono 16-bit PCM is about 256 kbps before BLE overhead:

```text
16,000 samples/s * 16 bits/sample = 256,000 bits/s
```

The firmware uses 88-sample packets so each notification is 180 bytes:

```text
4-byte app header + 88 samples * 2 bytes/sample = 180 bytes
```

That packet size intentionally stays below the common 182-byte macOS CoreBluetooth notification payload limit while still keeping each packet large enough for live testing.

This raw PCM path pushes BLE harder than the old Opus path. If you see `lost=` or `bad=` climbing in the PC client's status line:

- Move the board closer to the PC / reduce RF interference first
- Confirm your PC's BLE adapter/driver supports the 2M PHY and data-length extension
- Lower the sample rate or add compression after confirming the raw mic signal sounds clean

This is still a bring-up path, not Bluetooth LE Audio. A production BLE audio product would use LC3 over isochronous channels. This repo intentionally keeps the custom GATT service so the XIAO can stream directly to the Python client on a Mac.

## Next steps

- Use this raw PCM path to judge microphone quality, gain, clipping, noise, and packet loss without codec artifacts.
- After the raw path sounds correct, add compression back with a smaller embedded codec path or LC3/ISO if you want to follow the standard BLE audio architecture.
