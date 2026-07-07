# audio-over-ble

Stream microphone audio from a Seeed XIAO nRF52840 Sense's onboard PDM microphone to a Mac/PC over BLE, and play it live.

This is the **simple u-law stability baseline**: the XIAO captures 16 kHz mono 16-bit PCM from the onboard PDM mic, compresses each 10 ms block to 8-bit u-law, sends it over a custom BLE notify characteristic, and the Python client decodes it for live speaker playback.

This path intentionally avoids LC3 for now. LC3 was bandwidth-efficient but too heavy during bring-up. The earlier ADPCM baseline proved the BLE stream, but it had audible artifacts and could stall when BLE blocked the mic loop. The current u-law path uses larger but still MTU-safe packets, is stateless across packets, and moves BLE sending onto a separate firmware thread so mic capture does not wait on Bluetooth.

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

Expected transport numbers:

```text
pps ≈ 100
lost=0
bad=0
decode_fail=0
queued≈150-250ms
```

If `pps` is only around 8, the old firmware is still flashed or the firmware is not producing packets fast enough.

For lower delay once stable:

```bash
python play_ble_audio.py --buffer-ms 120 --blocksize 128 --latency low --gain 3
```

For safer playback if it cuts out:

```bash
python play_ble_audio.py --buffer-ms 250 --blocksize 256 --latency low --gain 3
```

For capture/debug:

```bash
python play_ble_audio.py --save capture.wav --gain 1
```

The saved WAV is decoded mic audio before Mac speaker output. Use `--gain 1` when recording/debugging so you do not confuse real mic noise with playback gain.

## Firmware setup (`firmware/xiao_ble_mic_stream/`)

The firmware is a Nordic nRF Connect SDK application built on Zephyr. It no longer uses Arduino.

Open the serial console at 115200 baud. You should see the device advertising as `CocoHusky-AudioStream` and logging a 16 kHz u-law microphone stream.

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

- **Firmware capture** reads 16 kHz mono PDM samples from Zephyr's DMIC driver.
- **Firmware queue** copies each 10 ms PCM block into a small message queue and frees the PDM slab immediately.
- **BLE sender thread** pulls queued PCM frames, encodes each frame to u-law, and sends one notification per 10 ms audio frame.
- **Packet format** is `[uint16 seq][uint16 decoded_samples][uint16 payload_bytes][u-law payload]`.
- **u-law payload** is 160 bytes for 160 decoded samples.
- **PC client** uses `bleak` to subscribe to notifications, decodes u-law to NumPy `int16`, queues samples, and `sounddevice` pulls from that queue in a real-time audio callback.

## Bandwidth math

Raw 16 kHz mono 16-bit PCM is about 256 kbps before BLE overhead:

```text
16,000 samples/s * 16 bits/sample = 256,000 bits/s
```

u-law cuts that to about 128 kbps before BLE overhead:

```text
16,000 samples/s * 8 bits/sample = 128,000 bits/s
```

Each 10 ms audio block is one 166-byte BLE notification:

```text
6-byte app header + 160-byte u-law payload = 166 bytes
```

That is heavier than ADPCM but still under the 247 MTU path and should sound less artifacty.

## If audio is noisy or cuts out

- First test with `python play_ble_audio.py --gain 3 --buffer-ms 250`.
- Do not enable AGC or noise gate until the raw stream is stable.
- If it is too quiet, raise gain slowly: `--gain 4`, then `--gain 6`.
- If `underflows` increases, raise `--buffer-ms`.
- If `lost`, `bad`, or `decode_fail` increase, rebuild/flash firmware and keep the XIAO close to the Mac.
- Watch firmware serial logs for `Dropped u-law packets`, `queue_drop`, or a BLE disconnect reason code.

This is still a bring-up path, not Bluetooth LE Audio. A production BLE audio product would use LC3 over isochronous channels. This repo intentionally keeps the custom GATT service so the XIAO can stream directly to the Python client on a Mac.
