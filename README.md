# Xiaomi MJSXJ05CM Firmware Downgrade

Tools and pre-built firmware for downgrading the **Xiaomi MJSXJ05CM** security camera from the locked 2025 firmware back to the hackable 2019 version.

## Why?

Recent firmware updates (2025+) for the MJSXJ05CM lock down the camera — disabling telnet, hardening the root filesystem, and blocking custom modifications. The 2019 recovery firmware still ships on the TF recovery image and contains an open SquashFS rootfs and JFFS2 data partition that can be modified for custom use (telnet, RTSP, etc.).

This project takes the **kernel, rootfs, and data partitions from the 2019 recovery image** and combines them with the **bootloader and device-specific partitions from your original SPI dump** to produce a flashable 16 MB SPI image that effectively downgrades the camera.

## What's Included

| File / Directory | Description |
|---|---|
| `downgraded_firmware.bin` | **Ready-to-flash** 16 MB SPI firmware (already built) |
| `original_spi_dump.bin` | Original SPI flash dump (2025 firmware, for reference) |
| `tf_recovery.img` | TF card recovery image (contains 2019 kernel/rootfs/data) |
| `packer.py` | Packs extracted partitions into a flashable 16 MB SPI image |
| `unpacker_spi.py` | Unpacks a raw SPI flash dump using the MXPT partition table |
| `unpacker_recovery.py` | Unpacks `tf_recovery.img` into kernel, rootfs, and data |
| `original_spi_unpacked/` | Extracted partitions from the original SPI dump |
| `recovery_unpacked/` | Extracted partitions from the TF recovery image |
| `original_spi_binwalk.txt` | Binwalk analysis of the original SPI dump |
| `commands.txt` | Full terminal log of the unpack/pack process |
| `hacks/` | MJSXJ05CM-hacks release and source repo (zip archives) |
| `debug_scripts/` | Diagnostic scripts for MXPT analysis and boot verification |
| `Pasted image.png` | Reference image |

### SPI Flash Layout (16 MB)

```
Offset      Size     Partition         Source (in downgraded firmware)
──────────  ───────  ────────────────  ────────────────────────────────
0x000000    192 KB   boot              Original SPI (IPL + bootloader)
0x030000    128 KB   uImage_firmware   Original SPI (U-Boot)
0x050000      2 MB   uImage_kernel     Recovery image (2019 Linux kernel)
0x250000    7.4 MB   squashfs          Recovery image (2019 SquashFS rootfs)
0x9B0000    6.2 MB   data              Recovery image (2019 JFFS2 data)
0xFE0000     64 KB   config            Original SPI (device config)
0xFF0000     64 KB   factory           Original SPI (WiFi MAC + calibration)
```

## Quick Start (Use Pre-Built Firmware)

If you just want to flash the included downgraded firmware:

1. **Disassemble** the camera — the SPI chip is on the back of the main board, so the camera needs to be nearly fully taken apart. Unscrew and shift the camera lens out of the way to get the SOIC clip/clamps on the chip properly.

**!!MAKE SURE YOU REMOVED THE SD CARD BEFORE ASSEMBLY/DISASSEMBLY!!**
![PXL_20260124_221215632](https://github.com/user-attachments/assets/7669b0c3-48a1-430a-9415-dd91e2761edf)
![PXL_20260124_221229836](https://github.com/user-attachments/assets/0e035bf6-c495-4006-90d4-fd355e1af78c)
![PXL_20260124_221307768](https://github.com/user-attachments/assets/f1e555b5-b514-4053-867a-61459a32fa9c)

4. **Read** your camera's SPI flash using a CH341A programmer *(black one will work, don't listen the voltage issues on the internet)*
<img width="978" height="686" alt="Pasted image" src="https://github.com/user-attachments/assets/35858ba6-fa3f-4934-a77b-fa675ffad632" />

6. **Back up** the original dump — you'll need it if anything goes wrong
7. **Clear** chip to delete old firmware
8. **Flash** `downgraded_firmware.bin` to the SPI chip

> **Important:** The included `downgraded_firmware.bin` contains the `config` and `factory` partitions from my specific camera. The `factory` partition holds your WiFi MAC address and calibration data. If you flash it as-is, your camera will work but will have my MAC address. To preserve your own device identity, follow the full steps below to build your own firmware from your SPI dump.

## Full Steps (Build Your Own)

If you want to build the downgraded firmware from your own SPI dump (recommended):

### Prerequisites

- Python 3.6+
- A raw 16 MB SPI flash dump from your MJSXJ05CM camera (`original_spi_dump.bin`)
- The TF recovery image (`tf_recovery.img`) — obtained by triggering the camera's SD card recovery mode (see [Inspiration](#inspiration) section)

### Step 1: Unpack Your SPI Dump

```bash
python3 unpacker_spi.py <your_spi_dump.bin> original_spi_unpacked
```

This parses the MXPT partition table at offset `0x20000` and extracts:
- Main partitions: `boot`, `uImage_firmware`, `uImage_kernel`, `squashfs`, `data`, `config`, `factory`
- Boot sub-partitions: `boot_parts/ipl`, `boot_parts/ipl_cust`, `boot_parts/key_cust`, `boot_parts/mxpt_table`, `boot_parts/uboot`, `boot_parts/uboot_env`

### Step 2: Unpack the Recovery Image

```bash
python3 unpacker_recovery.py tf_recovery.img recovery_unpacked
```

This extracts the 2019-era partitions from the recovery image:
- `uImage_kernel` — Linux kernel (I6/LX409)
- `squashfs` — SquashFS root filesystem
- `data` — JFFS2 configuration/data partition

### Step 3: Pack the Downgraded Firmware

```bash
python3 packer.py downgraded_firmware.bin original_spi_unpacked recovery_unpacked
```

This combines:
- **From your original SPI dump:** `boot`, `uImage_firmware`, `config`, `factory` (preserving your bootloader, device config, and WiFi MAC/calibration)
- **From the recovery image:** `uImage_kernel`, `squashfs`, `data` (the 2019 hackable firmware)

The packer fills unused space with `0xFF` (erased SPI flash state) and runs verification checks on the output:
- IPL magic in boot area
- uImage headers and CRC at kernel/firmware offsets
- Hardware revision match (I6)
- SquashFS and JFFS2 magic bytes
- CONFIG and FACTORY partition presence

### Step 4: Flash

Flash the resulting `downgraded_firmware.bin` to your camera's SPI chip.

### Step 5: Install Hacks (RTSP, ONVIF, Motor Control, etc.)

After flashing the downgraded firmware, you can install the [MJSXJ05CM-hacks](https://github.com/zry98/MJSXJ05CM-hacks) package to get RTSP streaming, ONVIF support, motor control, and more. The hacks release and source repo are included in the `hacks/` directory as zip archives.

1. Unzip `hacks/hacks release from zry98.zip` — inside you'll find a `hacks` and `manu_test` directories
2. Edit `hacks/installer/config.sh` with your settings for WIFI
3. Copy the **contents** of the `hacks` and `manu_test` directories to the root of a FAT32-formatted SD card
4. Power off the camera and insert the SD card
5. Power on the camera — the LED will be solid yellow while the hacks are being installed (several minutes)
6. When the camera starts rotating, installation is done
7. Find the camera's IP address on your router — RTSP stream will be available, ONVIF on the configured port

> The `hacks/hacks repo from zry98.zip` archive contains the full source repository for reference.

### Step 6: Home Assistant Integration

See [HomeAssistant.md](HomeAssistant.md) for setting up the camera in Home Assistant with RTSP live preview (WebRTC) and PTZ controls (ONVIF).

## Debug Scripts

The `debug_scripts/` directory contains diagnostic tools useful during development or troubleshooting:

- **`diagnose_boot.py`** — Scans the boot area for partition offset references, computes CRC32 of each partition, validates uImage headers, and dumps hex at critical boundaries. Run on both original and modified firmware to compare.
  ```bash
  python3 debug_scripts/diagnose_boot.py <firmware.bin>
  ```

- **`deep_diag.py`** — Full MXPT partition table hex dump and parsed entry analysis. Decodes uImage name encoding (hardware revision, git hash, version info). Searches for known partition sizes in the MXPT area.
  ```bash
  python3 debug_scripts/deep_diag.py <firmware.bin>
  ```

## How It Works

The MJSXJ05CM uses a SigmaStar SSD201/SSD202 SoC with a 16 MB SPI NOR flash. The flash contains an MXPT (MStar eXtended Partition Table) at offset `0x20000` that defines both boot-level and MTD-level partitions.

The key insight is that the camera's TF card recovery image (`tf_recovery.img`) contains an older (2019) version of the kernel, rootfs, and data partitions that lack the security hardening of the 2024 OTA updates. By replacing only the kernel, rootfs, and data partitions while keeping the original bootloader and device-specific partitions (config, factory), we get a working camera that runs the older, more open firmware.

The bootloader (`uImage_firmware` at `0x30000`) is kept from the original SPI dump because it contains hardware initialization code specific to the I6 revision. The `factory` partition at `0xFF0000` is device-specific — it stores the WiFi MAC address and RF calibration data.

## Compatibility with MJSXJ02CM

This approach may also work on the **Xiaomi MJSXJ02CM**, since it uses a similar SigmaStar platform and the same general firmware structure (MXPT partition table, uImage kernel, SquashFS rootfs, JFFS2 data). However, the partition layout differs between the two models — offsets, sizes, and hardware revision identifiers (e.g. `I3` vs `I6` in the uImage name) will not match.

If you want to attempt this on an MJSXJ02CM:

1. Dump your SPI flash and run `binwalk` and `debug_scripts/deep_diag.py` on it to map out the actual partition table
2. Adjust the offset/size constants in `unpacker_spi.py`, `unpacker_recovery.py`, and `packer.py` to match your MXPT layout
3. Verify the hardware revision field in the uImage header name (look for the `MVX2##` prefix — the two characters after `##` are the HW revision)
4. Use the same principle: keep bootloader + config + factory from your SPI dump, swap kernel + rootfs + data from the recovery image (recovery image is different for the [MJSXJ02CM](tf_recovery_MJSXJ02CM.img))

The debug scripts are designed to help with this — feed the output of `deep_diag.py` and `diagnose_boot.py` to an LLM to help you interpret the partition table and adjust the scripts accordingly.

## Inspiration

This project was inspired by and builds upon the research from:

- **[Mi Home Security Camera MJSXJ02CM Technical Teardown & UART Boot Analysis](https://medium.com/@aaronjjose/mi-home-security-camera-mjsxj02cm-technical-teardown-uart-boot-analysis-6eb188a45678)** — Technical teardown, UART boot analysis, and firmware exploration of a similar Xiaomi camera
- **[Xiaomi Smart Camera: Recovering Firmware and Backdooring](https://sungurlabs.github.io/2021/07/14/Xiaomi-Smart-Camera-Recovering-Firmware-and-Backdooring.html)** — Detailed writeup on recovering and modifying Xiaomi camera firmware via SPI flash dumps and TF recovery
- **[mjsxj05cm-hacks](https://github.com/zry98/MJSXJ05CM-hacks)** by cmiguelcabral and zry98 — Hacks and modifications for the MJSXJ05CM camera

## License

This project is released into the public domain under [The Unlicense](LICENSE).
