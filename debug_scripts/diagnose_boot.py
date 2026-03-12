#!/usr/bin/env python3
"""
Diagnostic script for Xiaomi MJSXJ05CM SPI flash.
Scans the boot area for partition tables, CRC values, and magic bytes.
"""

import sys
import struct
import binascii

if len(sys.argv) < 2:
    print("Usage: python3 diagnose_boot.py <SPI_original.bin>")
    sys.exit(1)

with open(sys.argv[1], "rb") as f:
    data = f.read()

total_size = len(data)
print(f"File size: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")
print()

# ============================================================
# 1. Scan boot area (0x0 - 0x30000) for known partition offsets
# ============================================================
print("=" * 70)
print("SCAN 1: Looking for partition offset references in boot area")
print("=" * 70)

# Known partition offsets to search for (as 32-bit LE values)
known_offsets = {
    0x30000: "uImage_firmware",
    0x50000: "uImage_kernel",
    0x250000: "SquashFS",
    0x9B0000: "JFFS2/data",
}

boot_area = data[:0x30000]
for offset_val, label in known_offsets.items():
    # Search as both little-endian and big-endian 32-bit
    le_bytes = struct.pack("<I", offset_val)
    be_bytes = struct.pack(">I", offset_val)
    
    for pos in range(len(boot_area) - 4):
        if boot_area[pos:pos+4] == le_bytes:
            print(f"  Found {hex(offset_val)} ({label}) as LE32 at boot offset {hex(pos)}")
        if boot_area[pos:pos+4] == be_bytes:
            print(f"  Found {hex(offset_val)} ({label}) as BE32 at boot offset {hex(pos)}")

print()

# ============================================================
# 2. Scan for potential CRC32 values stored in boot area
# ============================================================
print("=" * 70)
print("SCAN 2: Computing CRC32 of each partition")
print("=" * 70)

partitions_to_check = [
    ("boot",            0x000000, 0x030000),
    ("uImage_firmware", 0x030000, 0x050000 - 0x030000),
    ("uImage_kernel",   0x050000, 0x250000 - 0x050000),
    ("squashfs",        0x250000, 0x9B0000 - 0x250000),
    ("data",            0x9B0000, total_size - 0x9B0000),
]

partition_crcs = {}
for name, off, size in partitions_to_check:
    chunk = data[off:off+size]
    crc = binascii.crc32(chunk) & 0xFFFFFFFF
    partition_crcs[name] = crc
    print(f"  {name:20s} @ {hex(off):10s}  CRC32: {hex(crc)}")

print()

# Now search if any of these CRC values appear in the boot area
print("  Searching boot area for these CRC32 values...")
for name, crc in partition_crcs.items():
    le_bytes = struct.pack("<I", crc)
    be_bytes = struct.pack(">I", crc)
    for pos in range(len(boot_area) - 4):
        if boot_area[pos:pos+4] == le_bytes:
            print(f"    CRC of {name} ({hex(crc)}) found as LE32 at boot offset {hex(pos)}")
        if boot_area[pos:pos+4] == be_bytes:
            print(f"    CRC of {name} ({hex(crc)}) found as BE32 at boot offset {hex(pos)}")

print()

# ============================================================
# 3. Check uImage headers for integrity
# ============================================================
print("=" * 70)
print("SCAN 3: uImage header analysis")
print("=" * 70)

def parse_uimage(data, offset, label):
    hdr = data[offset:offset+64]
    if len(hdr) < 64:
        print(f"  {label}: Too short for uImage header")
        return
    
    magic = struct.unpack(">I", hdr[0:4])[0]
    if magic != 0x27051956:
        print(f"  {label}: No uImage magic at {hex(offset)} (got {hex(magic)})")
        return
    
    hdr_crc = struct.unpack(">I", hdr[4:8])[0]
    timestamp = struct.unpack(">I", hdr[8:12])[0]
    data_size = struct.unpack(">I", hdr[12:16])[0]
    load_addr = struct.unpack(">I", hdr[16:20])[0]
    entry_addr = struct.unpack(">I", hdr[20:24])[0]
    data_crc = struct.unpack(">I", hdr[24:28])[0]
    os_type = hdr[28]
    arch = hdr[29]
    img_type = hdr[30]
    comp = hdr[31]
    name = hdr[32:64].split(b'\x00')[0].decode('ascii', errors='replace')
    
    print(f"  {label} @ {hex(offset)}:")
    print(f"    Header CRC:  {hex(hdr_crc)}")
    print(f"    Data size:   {data_size} bytes")
    print(f"    Data CRC:    {hex(data_crc)}")
    print(f"    Load addr:   {hex(load_addr)}")
    print(f"    Entry addr:  {hex(entry_addr)}")
    print(f"    OS/Arch/Type/Comp: {os_type}/{arch}/{img_type}/{comp}")
    print(f"    Name:        '{name}'")
    
    # Verify data CRC
    actual_data = data[offset+64:offset+64+data_size]
    actual_data_crc = binascii.crc32(actual_data) & 0xFFFFFFFF
    if actual_data_crc == data_crc:
        print(f"    Data CRC:    VALID")
    else:
        print(f"    Data CRC:    MISMATCH! Expected {hex(data_crc)}, got {hex(actual_data_crc)}")
    
    # Verify header CRC (zero out the hdr_crc field first)
    hdr_check = bytearray(hdr)
    hdr_check[4:8] = b'\x00\x00\x00\x00'
    actual_hdr_crc = binascii.crc32(bytes(hdr_check)) & 0xFFFFFFFF
    if actual_hdr_crc == hdr_crc:
        print(f"    Header CRC:  VALID")
    else:
        print(f"    Header CRC:  MISMATCH! Expected {hex(hdr_crc)}, got {hex(actual_hdr_crc)}")
    
    print()

parse_uimage(data, 0x30000, "Firmware uImage")
parse_uimage(data, 0x50000, "Linux Kernel uImage")

# ============================================================
# 4. Look for partition table structures near known locations
# ============================================================
print("=" * 70)
print("SCAN 4: Hex dump around potential partition table areas")
print("=" * 70)

# Common places for partition tables: near end of boot, at specific aligned offsets
interesting_areas = [
    (0x0, 64, "Very start of boot"),
    (0x10000, 128, "0x10000 area"),
    (0x13D00, 256, "Near CRC32 table"),
    (0x20000, 128, "0x20000 area"),
    (0x2F000, 256, "End of boot area"),
]

for off, length, label in interesting_areas:
    if off + length > len(data):
        continue
    chunk = data[off:off+length]
    
    # Check if it's not all 0x00 or 0xFF
    if chunk == b'\x00' * length or chunk == b'\xFF' * length:
        continue
    
    print(f"\n  {label} ({hex(off)} - {hex(off+length)}):")
    for i in range(0, length, 16):
        hex_str = ' '.join(f'{b:02x}' for b in chunk[i:i+16])
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk[i:i+16])
        print(f"    {hex(off+i):8s}: {hex_str:48s} {ascii_str}")

# ============================================================
# 5. Compare bytes at critical boundaries
# ============================================================
print()
print("=" * 70)
print("SCAN 5: Boundary analysis")
print("=" * 70)

# Check what's right before each partition
boundaries = [0x30000, 0x50000, 0x250000, 0x9B0000]
for b in boundaries:
    before = data[b-16:b]
    after = data[b:b+16]
    print(f"  Boundary at {hex(b)}:")
    print(f"    Before: {' '.join(f'{x:02x}' for x in before)}")
    print(f"    After:  {' '.join(f'{x:02x}' for x in after)}")

print()
print("=" * 70)
print("DONE. Run this on both SPI_original.bin and your modified firmware")
print("to compare the outputs.")
print("=" * 70)
