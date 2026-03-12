#!/usr/bin/env python3
"""
Packer for Xiaomi MJSXJ05CM modified firmware (I6 / LX409).

Combines:
  - boot            from ORIGINAL SPI  (bootloader + IPL)
  - uImage_firmware from ORIGINAL SPI  (HW init, load addr 0x0)
  - uImage_kernel   from RECOVERY      (Linux kernel, I6/LX409, 2019)
  - squashfs        from RECOVERY      (SquashFS rootfs, 2019)
  - data            from RECOVERY      (JFFS2 config, 2019)
  - config          from ORIGINAL SPI  (device config, 64 KB)
  - factory         from ORIGINAL SPI  (WiFi MAC + calibration, 64 KB)

SPI Layout (16 MB, from kernel MXP partition table):
  0x000000  boot            (192 KB)
  0x030000  uImage_firmware (128 KB)
  0x050000  uImage_kernel   (  2 MB)
  0x250000  squashfs        (7.4 MB)
  0x9B0000  data            (6.2 MB)   <- stops at 0xFE0000
  0xFE0000  config          ( 64 KB)
  0xFF0000  factory         ( 64 KB)

Usage:
  1. python3 unpacker_spi_v3.py SPI_original.bin orignal_SPI_unpacked/
  2. python3 recovery_img/unpacker_new.py tf_recovery.img recovery_img/
  3. python3 packer_v2.py <output_firmware.bin> <original_spi_dir> <recovery_dir>

Example:
  python3 packer_v2.py firmware_downgraded.bin orignal_SPI_unpacked recovery_img
"""

import sys
import os

SPI_SIZE = 16 * 1024 * 1024  # 16 MB
FILL_BYTE = b'\xFF'           # SPI flash erased state

if len(sys.argv) < 4:
    print("Usage: python3 packer_v2.py <output_firmware.bin> <original_spi_dir> <recovery_dir>")
    sys.exit(1)

out_file = sys.argv[1]
spi_dir = sys.argv[2]
rec_dir = sys.argv[3]

# (label, source_file, offset, max_size)
partitions = [
    ("boot",            os.path.join(spi_dir, "boot"),            0x000000, 0x030000),
    ("uImage_firmware", os.path.join(spi_dir, "uImage_firmware"), 0x030000, 0x050000 - 0x030000),
    ("uImage_kernel",   os.path.join(rec_dir, "uImage_kernel"),   0x050000, 0x250000 - 0x050000),
    ("squashfs",        os.path.join(rec_dir, "squashfs"),        0x250000, 0x9B0000 - 0x250000),
    ("data",            os.path.join(rec_dir, "data"),            0x9B0000, 0xFE0000 - 0x9B0000),
    ("config",          os.path.join(spi_dir, "config"),          0xFE0000, 0xFF0000 - 0xFE0000),
    ("factory",         os.path.join(spi_dir, "factory"),         0xFF0000, 0x1000000 - 0xFF0000),
]

print(f"Building {out_file} ({SPI_SIZE} bytes = {SPI_SIZE // 1024 // 1024} MB)")
print(f"{'Partition':20s} {'Source':42s} {'Offset':>10s} {'DataSize':>10s} {'MaxSlot':>10s} {'Fill%':>6s}")
print("-" * 100)

errors = []

with open(out_file, "wb") as fw:
    # Pre-fill entire image with 0xFF (erased SPI flash state)
    fw.write(FILL_BYTE * SPI_SIZE)

    for label, src, offset, max_size in partitions:
        if not os.path.isfile(src):
            print(f"  ERROR: '{src}' not found!")
            errors.append(src)
            continue

        with open(src, "rb") as f:
            data = f.read()

        if len(data) > max_size:
            print(f"  FATAL: {label} is {len(data)} bytes, exceeds slot of {max_size} bytes!")
            sys.exit(1)

        fw.seek(offset)
        fw.write(data)

        fill_pct = len(data) / max_size * 100
        print(f"  {label:20s} {src:42s} {hex(offset):>10s} {len(data):>10d} {max_size:>10d} {fill_pct:>5.1f}%")

print("-" * 100)

# Verify final size
final_size = os.path.getsize(out_file)
if final_size == SPI_SIZE:
    print(f"\nSUCCESS: {out_file} is exactly {SPI_SIZE} bytes (16 MB)")
else:
    print(f"\nWARNING: {out_file} is {final_size} bytes, expected {SPI_SIZE}!")

if errors:
    print(f"\nWARNING: {len(errors)} partition(s) missing — those regions are 0xFF (empty flash)")
    for e in errors:
        print(f"  - {e}")
    print("The firmware may not boot correctly with missing partitions!")
else:
    print("\nAll partitions written. Verifying...")

# Verification
with open(out_file, "rb") as fw:
    import struct, binascii

    # Check boot area starts with ARM branch + IPL magic
    fw.seek(0)
    boot_start = fw.read(8)
    if boot_start[4:8] == b'IPL_':
        print("  [OK] Boot area has IPL_ magic")
    else:
        print("  [!!] Boot area missing IPL_ magic")

    # Check firmware uImage at 0x30000
    fw.seek(0x30000)
    magic = struct.unpack(">I", fw.read(4))[0]
    if magic == 0x27051956:
        fw.seek(0x30000 + 32)
        name = fw.read(32).split(b'\x00')[0].decode('ascii', errors='replace')
        print(f"  [OK] Firmware uImage at 0x30000: '{name}'")
    else:
        print(f"  [!!] No uImage magic at 0x30000!")

    # Check Linux kernel at 0x50000
    fw.seek(0x50000)
    hdr = fw.read(64)
    magic = struct.unpack(">I", hdr[0:4])[0]
    if magic == 0x27051956:
        name = hdr[32:64].split(b'\x00')[0].decode('ascii', errors='replace')
        data_size = struct.unpack(">I", hdr[12:16])[0]
        data_crc = struct.unpack(">I", hdr[24:28])[0]
        fw.seek(0x50000 + 64)
        kernel_data = fw.read(data_size)
        actual_crc = binascii.crc32(kernel_data) & 0xFFFFFFFF
        crc_ok = "VALID" if actual_crc == data_crc else "MISMATCH!"
        print(f"  [OK] Linux kernel at 0x50000: '{name}' (CRC: {crc_ok})")

        if '##I6' in name:
            print(f"  [OK] Hardware revision: I6 (matches your camera)")
        else:
            print(f"  [!!] Hardware revision mismatch in kernel name!")
    else:
        print(f"  [!!] No uImage magic at 0x50000!")

    # Check SquashFS at 0x250000
    fw.seek(0x250000)
    sqsh_magic = fw.read(4)
    if sqsh_magic == b'hsqs':
        print(f"  [OK] SquashFS magic at 0x250000")
    else:
        print(f"  [!!] No SquashFS magic at 0x250000!")

    # Check JFFS2 at 0x9B0000
    fw.seek(0x9B0000)
    jffs2_magic = struct.unpack("<H", fw.read(2))[0]
    if jffs2_magic == 0x1985:
        print(f"  [OK] JFFS2 magic at 0x9B0000")
    else:
        print(f"  [!!] No JFFS2 magic at 0x9B0000!")

    # Check CONFIG at 0xFE0000
    fw.seek(0xFE0000)
    config_data = fw.read(0x10000)
    config_non_ff = sum(1 for b in config_data if b != 0xFF)
    if config_non_ff > 0:
        print(f"  [OK] CONFIG at 0xFE0000: {config_non_ff} non-FF bytes")
    else:
        print(f"  [!!] CONFIG at 0xFE0000 is all 0xFF — device config missing!")

    # Check FACTORY at 0xFF0000
    fw.seek(0xFF0000)
    factory_data = fw.read(0x10000)
    factory_non_ff = sum(1 for b in factory_data if b != 0xFF)
    if factory_non_ff > 0:
        print(f"  [OK] FACTORY at 0xFF0000: {factory_non_ff} non-FF bytes (WiFi MAC/cal)")
    else:
        print(f"  [!!] FACTORY at 0xFF0000 is all 0xFF — WiFi MAC & calibration missing!")

print(f"\nFirmware is ready to flash: {out_file}")
