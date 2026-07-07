# audio-over-ble

Stream raw microphone audio from a Seeed XIAO nRF52840 Sense's onboard PDM
microphone to a PC over BLE, and play it live.

This is now a **raw 16-bit PCM baseline**. The XIAO captures 16 kHz mono PCM and
sends it directly over a custom BLE notify characteristic. There is no Opus
firmware build, no host-side Opus build, and no audio compression in this path.
That makes it easier to debug true microphone quality before adding compression
back later.

## Hardware

- Seeed XIAO nRF52840 **Sense** (needs the onboard PDM mic — the non-Sense
  variant doesn't have one)
- USB-C cable
- Any PC with Bluetooth 4.2+ (BLE)

## Firmware setup (`firmware/xiao_ble_mic_stream/`)

The firmware is a Nordic nRF Connect SDK application built on Zephyr. It no
longer uses Arduino.

Install nRF Connect SDK first. The easiest path is Nordic's Toolchain Manager,
then open the SDK terminal it provides. From that terminal:

```bash
cd /path/to/audio-over-ble/firmware/xiao_ble_mic_stream
west build -b xiao_ble/nrf52840/sense
west flash
```

If your installed SDK is older and does not recognize the qualified board
target, try the older target spelling:

```bash
west build -b xiao_ble
west flash
```

Open the serial console at 115200 baud. You should see the device advertising
as `CocoHusky-AudioStream`.

## PC client setup (`pc_client/`)

```bash
cd pc_client
python3 -m venv venv
source venv/bin/activate      # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python ble_audio_receiver.py
```

The client scans for the device, connects, buffers raw PCM audio, then starts
live playback. You'll see a running counter of packets received/lost.

Optional: record what you hear to a WAV file at the same time:

```bash
python ble_audio_receiver.py --save capture.wav
```

If auto-scan doesn't find the device, pass its address directly:

```bash
python ble_audio_receiver.py --address AA:BB:CC:DD:EE:FF
```

## How it's structured

- **Firmware** captures PDM samples at 16 kHz mono with Zephyr's DMIC driver and
  sends raw 16-bit little-endian PCM frames over BLE notifications.
- **Packet format** is:
  `[uint16 seq][uint16 sample_count][int16 PCM samples...]`.
  The sequence number lets the PC side detect missing BLE packets and conceal
  short gaps during playback.
- **PC client** uses `bleak` to subscribe to notifications, converts the PCM
  payload directly into NumPy `int16` samples, queues them, and `sounddevice`
  pulls from that queue in a real-time audio callback.

## Bandwidth math

Raw 16 kHz mono 16-bit PCM is about 256 kbps before BLE overhead:

```text
16,000 samples/s * 16 bits/sample = 256,000 bits/s
```

The firmware uses 120-sample packets so the full notification is 244 bytes:

```text
4-byte app header + 120 samples * 2 bytes/sample = 244 bytes
```

This intentionally pushes BLE harder than the Opus path. If you see `lost=` or
`bad=` climbing in the PC client's status line:

- Move the board closer to the PC / reduce RF interference first
- Confirm your PC's BLE adapter/driver supports the 2M PHY and data-length
  extension
- Lower the sample rate or add compression after confirming the raw mic signal
  sounds clean

This is still a bring-up path, not Bluetooth LE Audio. A production BLE audio
product would use LC3 over isochronous channels. This repo intentionally keeps
the custom GATT service so the XIAO can stream directly to the Python client on
a Mac.

## Next steps

- Use this raw PCM path to judge microphone quality, gain, clipping, noise, and
  packet loss without codec artifacts.
- After the raw path sounds correct, add compression back with a smaller embedded
  codec path or LC3/ISO if you want to follow the standard BLE audio
  architecture.
