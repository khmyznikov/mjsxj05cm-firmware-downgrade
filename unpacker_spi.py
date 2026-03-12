#!/usr/bin/env python3
"""
Unpacker v3 for SPI flash dumps (Xiaomi MJSXJ05CM / MStar SigmaStar)

Auto-parses the MXPT partition table at 0x20000 to extract all partitions.

MXPT entry structure (0x88 bytes stride):
  +0x00  4B  Magic "MXPT"
  +0x04  1B  Version
  +0x05  1B  Type (0x01=boot-level, 0x03=MTD-level, 0x07=special, 0x00=empty)
  +0x06  2B  Reserved
  +0x08  8B  Partition offset (LE64)
  +0x10  8B  Partition size (LE64)
  +0x18  8B  Padding
  +0x20  16B Partition name (null-terminated ASCII)
  +0x30  76B Padding
  +0x7C  5B  Footer ("\\0TPXM")
  +0x81  7B  Padding

Typical SPI Layout (16 MB):
  Boot-level (type 0x01):
    IPL        0x000000  64 KB   Initial Program Loader
    IPL_CUST   0x010000  60 KB   IPL customization
    KEY_CUST   0x01F000   4 KB   Key storage
    MXPT       0x020000   4 KB   Partition table
    UBOOT      0x030000 124 KB   U-Boot bootloader
    UBOOT_ENV  0x04F000   4 KB   U-Boot environment

  MTD-level (type 0x03/0x07):
    BOOT       0x000000 320 KB   Full boot area (encompasses above)
    KERNEL     0x050000   2 MB   Linux kernel uImage
    ROOTFS     0x250000 7.4 MB   SquashFS root filesystem
    DATA       0x9B0000 6.2 MB   JFFS2 config/data
    CONFIG     0xFE0000  64 KB   Device config
    FACTORY    0xFF0000  64 KB   WiFi MAC, calibration, device token

packer_v2 compatibility:
  The BOOT MTD partition (320 KB) is split at the UBOOT offset into:
    boot            0x000000 192 KB  (IPL + IPL_CUST + KEY_CUST + MXPT)
    uImage_firmware 0x030000 128 KB  (UBOOT + UBOOT_ENV)
"""

import sys
import os
import struct

MXPT_MAGIC = b'MXPT'
MXPT_TABLE_OFFSET = 0x20000
MXPT_ENTRY_STRIDE = 0x88
MAX_ENTRIES = 32

# Map MXPT names to output filenames for packer_v2 compatibility
NAME_MAP = {
    # MTD-level (BOOT handled specially — split into boot + uImage_firmware)
    "KERNEL":    "uImage_kernel",
    "ROOTFS":    "squashfs",
    "DATA":      "data",
    "CONFIG":    "config",
    "FACTORY":   "factory",
    # Boot-level
    "IPL":       "ipl",
    "IPL_CUST":  "ipl_cust",
    "KEY_CUST":  "key_cust",
    "MXPT":      "mxpt_table",
    "UBOOT":     "uboot",
    "UBOOT_ENV": "uboot_env",
}

TYPE_NAMES = {
    0x01: "boot-level",
    0x03: "MTD",
    0x07: "MTD-special",
}


def parse_mxpt(firmware):
    """Parse MXPT partition entries from firmware binary."""
    entries = []
    for i in range(MAX_ENTRIES):
        pos = MXPT_TABLE_OFFSET + i * MXPT_ENTRY_STRIDE
        firmware.seek(pos)
        raw = firmware.read(MXPT_ENTRY_STRIDE)
        if len(raw) < 0x30:
            break

        magic = raw[0:4]
        if magic != MXPT_MAGIC:
            continue

        ptype = raw[5]
        if ptype == 0x00:
            continue  # empty/unused entry

        offset = struct.unpack_from('<Q', raw, 0x08)[0]
        size = struct.unpack_from('<Q', raw, 0x10)[0]
        name_raw = raw[0x20:0x30]
        name = name_raw.split(b'\x00')[0].decode('ascii', errors='replace').strip()

        if size == 0 or not name:
            continue

        entries.append({
            'name': name,
            'offset': offset,
            'size': size,
            'type': ptype,
            'index': i,
        })

    return entries


def extract_partitions(firmware, entries, output_dir, boot_sub_dir):
    """Extract partitions from firmware based on parsed MXPT entries."""
    boot_level = [e for e in entries if e['type'] == 0x01]
    mtd_level = [e for e in entries if e['type'] in (0x03, 0x07)]

    # Find UBOOT offset to split BOOT into boot + uImage_firmware (packer_v2 layout)
    uboot_entry = next((e for e in boot_level if e['name'] == 'UBOOT'), None)
    split_offset = uboot_entry['offset'] if uboot_entry else 0x030000

    results = []

    # Extract MTD-level partitions (main partitions)
    for entry in sorted(mtd_level, key=lambda e: e['offset']):
        # Split BOOT into boot + uImage_firmware for packer_v2 compatibility
        if entry['name'] == 'BOOT':
            boot_size = split_offset - entry['offset']
            fw_size = entry['size'] - boot_size

            # boot: IPL + IPL_CUST + KEY_CUST + MXPT (pre-UBOOT area)
            firmware.seek(entry['offset'])
            boot_data = firmware.read(boot_size)
            out_path = os.path.join(output_dir, 'boot')
            with open(out_path, "wb") as out:
                out.write(boot_data)
            non_ff = sum(1 for b in boot_data if b != 0xFF)
            boot_entry = {**entry, 'name': 'BOOT(pre)', 'size': boot_size}
            results.append((boot_entry, 'boot', len(boot_data), non_ff, output_dir))

            # uImage_firmware: UBOOT + UBOOT_ENV
            firmware.seek(split_offset)
            fw_data = firmware.read(fw_size)
            out_path = os.path.join(output_dir, 'uImage_firmware')
            with open(out_path, "wb") as out:
                out.write(fw_data)
            non_ff = sum(1 for b in fw_data if b != 0xFF)
            fw_entry = {**entry, 'name': 'BOOT(fw)', 'offset': split_offset, 'size': fw_size}
            results.append((fw_entry, 'uImage_firmware', len(fw_data), non_ff, output_dir))
            continue

        filename = NAME_MAP.get(entry['name'], entry['name'].lower())
        out_path = os.path.join(output_dir, filename)

        firmware.seek(entry['offset'])
        data = firmware.read(entry['size'])

        with open(out_path, "wb") as out:
            out.write(data)

        non_ff = sum(1 for b in data if b != 0xFF)
        results.append((entry, filename, len(data), non_ff, output_dir))

    # Extract boot-level sub-partitions
    if boot_level:
        if not os.path.isdir(boot_sub_dir):
            os.makedirs(boot_sub_dir, exist_ok=True)

        for entry in sorted(boot_level, key=lambda e: e['offset']):
            filename = NAME_MAP.get(entry['name'], entry['name'].lower())
            out_path = os.path.join(boot_sub_dir, filename)

            firmware.seek(entry['offset'])
            data = firmware.read(entry['size'])

            with open(out_path, "wb") as out:
                out.write(data)

            non_ff = sum(1 for b in data if b != 0xFF)
            results.append((entry, filename, len(data), non_ff, boot_sub_dir))

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 unpacker_spi_v3.py <SPI_dump.bin> [output_dir]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    boot_sub_dir = os.path.join(output_dir, "boot_parts")

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")

    try:
        file_size = os.path.getsize(input_file)
        print(f"Input: {input_file} ({file_size} bytes, {file_size / 1024 / 1024:.1f} MB)")
        if file_size != 16 * 1024 * 1024:
            print(f"  WARNING: Expected 16 MB (16777216 bytes), got {file_size} bytes!")
        print()

        with open(input_file, "rb") as firmware:
            # Parse MXPT partition table
            entries = parse_mxpt(firmware)

            if not entries:
                print("ERROR: No MXPT partition entries found at 0x20000!")
                print("This file may not be a valid SPI dump, or the MXPT table is at a different offset.")
                sys.exit(1)

            boot_level = [e for e in entries if e['type'] == 0x01]
            mtd_level = [e for e in entries if e['type'] in (0x03, 0x07)]

            print(f"MXPT partition table: {len(entries)} entries "
                  f"({len(boot_level)} boot-level, {len(mtd_level)} MTD-level)")
            print()

            # Show parsed table
            print(f"  {'#':>2s}  {'Type':12s} {'Name':12s} {'Offset':>10s} {'End':>10s} "
                  f"{'Size':>10s} {'Size':>8s}")
            print(f"  {'-'*72}")
            for e in sorted(entries, key=lambda x: (x['type'], x['offset'])):
                end = e['offset'] + e['size']
                type_name = TYPE_NAMES.get(e['type'], f"0x{e['type']:02x}")
                if e['size'] >= 1024 * 1024:
                    human = f"{e['size'] / 1024 / 1024:.1f} MB"
                else:
                    human = f"{e['size'] / 1024:.0f} KB"
                print(f"  {e['index']:2d}  {type_name:12s} {e['name']:12s} "
                      f"{hex(e['offset']):>10s} {hex(end):>10s} {e['size']:>10d} {human:>8s}")
            print()

            # Extract
            print("Extracting partitions...")
            print(f"  {'Partition':12s} {'File':>20s} {'Offset':>10s} "
                  f"{'Size':>10s} {'Non-FF':>10s}  Notes")
            print(f"  {'-'*78}")

            results = extract_partitions(firmware, entries, output_dir, boot_sub_dir)

            for entry, filename, size, non_ff, dest in results:
                note = ""
                if non_ff == 0:
                    note = "** EMPTY (all 0xFF) **"
                elif entry['name'] in ("CONFIG", "FACTORY"):
                    if non_ff < 32:
                        note = "** SUSPICIOUS - very little data **"
                    else:
                        note = "OK"

                rel_path = os.path.join(os.path.basename(dest), filename) \
                    if dest != output_dir else filename
                print(f"  {entry['name']:12s} {rel_path:>20s} {hex(entry['offset']):>10s} "
                      f"{size:>10d} {non_ff:>10d}  {note}")

        mtd_count = len(mtd_level) + 1  # BOOT split into boot + uImage_firmware
        boot_count = len(boot_level)
        print(f"\nDone. Extracted {mtd_count} partitions to {output_dir}/")
        if boot_count:
            print(f"     Extracted {boot_count} boot sub-partitions to {boot_sub_dir}/")
        print(f"\nFor packer_v2, use:  python3 unpacker_spi_v3.py SPI_original.bin orignal_SPI_unpacked/")

    except FileNotFoundError:
        print(f"Error: '{input_file}' not found.")
        sys.exit(1)


if __name__ == "__main__":
    main()
