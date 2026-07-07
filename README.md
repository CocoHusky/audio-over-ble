# audio-over-ble

Stream audio from a Seeed XIAO nRF52840 Sense's onboard PDM microphone to a
PC over BLE, and play it live.

The current firmware uses **Opus**: the XIAO captures 16 kHz mono PCM,
encodes 20 ms frames with Xiph libopus, and sends one encoded frame per BLE
notification. The PC client decodes those Opus packets with the same libopus
implementation before playback.

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

The firmware vendors the official Xiph libopus source under
`third_party/opus-1.6.1` and links it as a fixed-point static library.

## PC client setup (`pc_client/`)

```bash
cd pc_client
python3 -m venv venv
source venv/bin/activate      # or venv\Scripts\activate on Windows
pip install -r requirements.txt
./build_opus_host.sh
python ble_audio_receiver.py
```

The `build_opus_host.sh` step builds a local `libopus.dylib` from the same
vendored Xiph source. The Python client loads that library directly through
`ctypes`.

The client will scan for the device, connect, buffer decoded audio, then start
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

- **Firmware** captures PDM samples at 16 kHz mono with Zephyr's DMIC driver,
  encodes 320-sample / 20 ms frames with libopus at 32 kbps CBR, and sends
  one Opus frame per BLE notification.
- **Packet format** is:
  `[uint16 seq][uint16 decoded_sample_count][uint16 opus_byte_count][opus payload]`.
  The sequence number lets the PC side detect missing frames and ask Opus PLC
  to conceal them.
- **PC client** uses `bleak` to subscribe to notifications, decodes Opus frames
  through libopus, queues decoded PCM, and `sounddevice` pulls from that queue
  in a real-time audio callback.

## Bandwidth math

Opus is currently configured for 32 kbps CBR. With the 6-byte application
header, that is roughly 43 kbps before BLE overhead, much lower than 256 kbps
raw PCM. If you see `lost=` climbing in the PC client's status line:

- Move the board closer to the PC / reduce RF interference first
- Confirm your PC's BLE adapter/driver actually supports the 2M PHY —
  older adapters can bottleneck here regardless of firmware settings

This is still a bring-up path, not Bluetooth LE Audio. A production BLE audio
product would use LC3 over isochronous channels. This repo intentionally keeps
the custom GATT service so the XIAO can stream directly to the Python client
on a Mac.

## Next steps

- Tune Opus bitrate and complexity after confirming the encoder can keep up on
  the nRF52840 without starving the PDM read loop.
- Move to LC3/ISO if you want to follow the standard BLE audio architecture.
