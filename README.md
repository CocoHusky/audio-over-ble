# audio-over-ble

Stream microphone audio from a Seeed XIAO nRF52840 Sense's onboard PDM microphone to a Mac/PC over BLE, and play it live.

This is the **simple ADPCM baseline**: the XIAO captures 16 kHz mono 16-bit PCM from the onboard PDM mic, compresses each 10 ms block with lightweight IMA ADPCM, sends it over a custom BLE notify characteristic, and the Python client decodes it for live speaker playback.

This path intentionally avoids LC3 for now. LC3 is bandwidth-efficient, but the current nRF52840/Zephyr bring-up was producing only a few frames per second and causing buzzy underflow audio. ADPCM is much lighter on the MCU and keeps the BLE bitrate practical while we verify the real microphone signal.

## Hardware

- Seeed XIAO nRF52840 **Sense** (needs the onboard PDM mic — the non-Sense variant does not have one)
- USB-C cable
- Mac or PC with Bluetooth 4.2+ (BLE)

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

Then run the simple terminal player first:

```bash
cd /Users/alexburton/Documents/GitHub/audio-over-ble/pc_client
bash setup_pc.sh
source venv/bin/activate
python play_ble_audio.py
```

The key number is `pps`.

Expected rate:

```text
pps ≈ 100
packets ≈ 100 after 1 sec
packets ≈ 200 after 2 sec
packets ≈ 300 after 3 sec
```

If `pps` is only around 8, the firmware is still not streaming fast enough or the old firmware is still flashed.

For the GUI monitor:

```bash
python ble_audio_control.py
```

For capture/debug without the GUI:

```bash
python ble_audio_receiver.py --save capture.wav
```

The device should advertise as `CocoHusky-AudioStream`. The PC client should connect, buffer ADPCM audio, decode it to PCM, play it through the Mac output, and show packet/loss counters increasing.

## Firmware setup (`firmware/xiao_ble_mic_stream/`)

The firmware is a Nordic nRF Connect SDK application built on Zephyr. It no longer uses Arduino.

Open the serial console at 115200 baud. You should see the device advertising as `CocoHusky-AudioStream` and logging a 16 kHz ADPCM microphone stream.

## PC client setup (`pc_client/`)

The helper script recreates the local Python environment after a clean or fresh clone:

```bash
cd pc_client
bash setup_pc.sh
source venv/bin/activate
python play_ble_audio.py
```

It installs the required packages from `requirements.txt` and compile-checks the client scripts. If `sounddevice` fails to install on macOS, install PortAudio first:

```bash
brew install portaudio
bash setup_pc.sh
```

## How it is structured

- **Firmware** captures PDM samples at 16 kHz mono with Zephyr's DMIC driver and creates one 10 ms frame at a time.
- **Compression** uses IMA ADPCM, 4 bits/sample, with a predictor/index header in every packet so packet loss does not poison the next frame.
- **Packet format** is `[uint16 seq][uint16 decoded_samples][uint16 payload_bytes][ADPCM payload]`.
- **ADPCM payload** is `[int16 predictor][uint8 step_index][uint8 reserved][80 packed nibble bytes]`.
- **PC client** uses `bleak` to subscribe to notifications, decodes ADPCM to NumPy `int16`, queues the samples, and `sounddevice` pulls from that queue in a real-time audio callback.

## Bandwidth math

Raw 16 kHz mono 16-bit PCM is about 256 kbps before BLE overhead:

```text
16,000 samples/s * 16 bits/sample = 256,000 bits/s
```

ADPCM cuts that to about 64 kbps before BLE overhead:

```text
16,000 samples/s * 4 bits/sample = 64,000 bits/s
```

Each 10 ms audio block is one 90-byte BLE notification:

```text
6-byte app header + 84-byte ADPCM payload = 90 bytes
```

That is the current baseline for live mic → BLE → Mac speaker playback.

## If you still hear buzzing

- First look at `pps` in `python play_ble_audio.py`.
- `pps ≈ 100` means the transport is keeping up and remaining noise is likely mic gain, PDM config, or acoustic/mechanical noise.
- `pps` far below 100 means packet production is still too slow or the old firmware is still on the board.
- Rebuild pristine and flash again: `rm -rf build && west build -p always -b xiao_ble/nrf52840/sense && west flash`.
- Keep the XIAO close to the Mac for the first test.
- Watch firmware serial logs for `Dropped ADPCM packets` or a BLE disconnect reason code.

This is still a bring-up path, not Bluetooth LE Audio. A production BLE audio product would use LC3 over isochronous channels. This repo intentionally keeps the custom GATT service so the XIAO can stream directly to the Python client on a Mac.
