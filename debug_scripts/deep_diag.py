#!/usr/bin/env python3
"""
Deep analysis of MXPT (MStar/SigmaStar partition table) and uImage names.
Compares original vs modified firmware for Xiaomi MJSXJ05CM.
"""

import sys
import struct

if len(sys.argv) < 2:
    print("Usage: python3 deep_diag.py <firmware.bin>")
    sys.exit(1)

with open(sys.argv[1], "rb") as f:
    data = f.read()

print(f"=== Analyzing: {sys.argv[1]} ({len(data)} bytes) ===\n")

# ============================================================
# 1. Full MXPT partition table dump (0x20000 area)
# ============================================================
print("=" * 70)
print("MXPT PARTITION TABLE (full dump 0x20000 - 0x20600)")
print("=" * 70)

# MXPT entries are typically 0x80 bytes each
mxpt_start = 0x20000
mxpt_len = 0x600  # dump enough to see all entries

for i in range(0, mxpt_len, 16):
    addr = mxpt_start + i
    chunk = data[addr:addr+16]
    if all(b == 0xFF for b in chunk):
        # Still print to show gaps
        pass
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f"  {hex(addr):8s}: {hex_str:48s} {ascii_str}")

print()

# ============================================================
# 2. Parse MXPT entries
# ============================================================
print("=" * 70)
print("MXPT PARSED ENTRIES")
print("=" * 70)

# MXPT header: "MXPT" magic, then version info
magic = data[mxpt_start:mxpt_start+4]
print(f"  Magic: {magic} ({magic.hex()})")
print(f"  Version bytes: {data[mxpt_start+4:mxpt_start+8].hex()}")
print()

# Typical MXPT entry structure (SigmaStar):
# Each entry at 0x80-byte boundaries after header
# Name (16 bytes), offset (4 bytes), size (4 bytes), ...
# But layout varies. Let's scan for readable partition names.

entry_size = 0x80
num_entries = 16  # check up to 16 entries

for idx in range(num_entries):
    entry_off = mxpt_start + (idx * entry_size)
    entry = data[entry_off:entry_off + entry_size]
    
    # Check if entry has readable ASCII name in first 16 bytes
    name_bytes = entry[:16]
    name = name_bytes.split(b'\x00')[0].decode('ascii', errors='replace')
    
    if name and any(c.isalpha() for c in name) and name not in ['MXPT']:
        # Try to find offset/size fields at common positions
        print(f"  Entry {idx} @ {hex(entry_off)}:")
        print(f"    Name: '{name}'")
        print(f"    Raw hex:")
        for j in range(0, len(entry), 16):
            h = ' '.join(f'{b:02x}' for b in entry[j:j+16])
            a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in entry[j:j+16])
            print(f"      +{hex(j):5s}: {h:48s} {a}")
        print()

# ============================================================
# 3. Decode uImage names (version encoding)
# ============================================================
print("=" * 70)
print("uImage NAME ANALYSIS (version/hardware encoding)")
print("=" * 70)

for label, offset in [("Firmware uImage (0x30000)", 0x30000), ("Linux Kernel (0x50000)", 0x50000)]:
    hdr = data[offset:offset+64]
    if struct.unpack(">I", hdr[0:4])[0] != 0x27051956:
        print(f"  {label}: No uImage magic")
        continue
    
    name = hdr[32:64].split(b'\x00')[0].decode('ascii', errors='replace')
    data_size = struct.unpack(">I", hdr[12:16])[0]
    timestamp = struct.unpack(">I", hdr[8:12])[0]
    
    print(f"\n  {label}:")
    print(f"    Full name:  '{name}'")
    print(f"    Data size:  {data_size} bytes")
    
    # Parse the encoded name format: MVX{n}##{tag}g{githash}{type}_{info}
    # MVX1##I6g46ec744CM_UBT1501###XVM  (firmware)
    # MVX2##I6g6cdcdf5KL_LX409####[BR:  (kernel original)
    # MVX2##I3g60b5603KL_LX318####[BR:  (kernel recovery)
    if name.startswith('MVX'):
        mvx_num = name[3]
        hw_rev = name[6:8]  # I3 or I6
        git_hash = name[9:17]  # 8 char git hash
        suffix = name[17:]
        
        print(f"    MVX type:   {mvx_num}")
        print(f"    HW Rev:     {hw_rev}  {'<-- THIS IS THE KEY FIELD' if mvx_num == '2' else ''}")
        print(f"    Git hash:   {git_hash}")
        print(f"    Suffix:     {suffix}")

print()

# ============================================================
# 4. CRITICAL: scan 0x20000-0x30000 for size/CRC fields
# ============================================================
print("=" * 70)
print("MXPT AREA: Looking for partition size values")
print("=" * 70)

# Search for known sizes as 32-bit values in the MXPT area
known_sizes = {
    # Original SPI
    107120: "firmware uImage data (original)",
    1569792: "kernel data size (original/2024)",
    5751770: "squashfs size (original/2024)",
    4390924: "JFFS2 size (original/2024)",
    # Recovery
    1724412: "kernel data size (recovery/2018)",
    6502290: "squashfs size (recovery/2018)",
    2536640: "JFFS2 size (recovery/2018)",
}

mxpt_area = data[0x20000:0x30000]
for size_val, label in known_sizes.items():
    le = struct.pack("<I", size_val)
    be = struct.pack(">I", size_val)
    for pos in range(len(mxpt_area) - 4):
        if mxpt_area[pos:pos+4] == le:
            print(f"  Found {size_val} ({label}) as LE32 at {hex(0x20000 + pos)}")
        if mxpt_area[pos:pos+4] == be:
            print(f"  Found {size_val} ({label}) as BE32 at {hex(0x20000 + pos)}")

print()

# ============================================================
# 5. Full diff-relevant area: dump 0x20000 - 0x20800 
#    with emphasis on non-FF, non-00 areas
# ============================================================
print("=" * 70)
print("NON-EMPTY REGIONS in 0x20000-0x30000")
print("=" * 70)

for block in range(0x20000, 0x30000, 0x100):
    chunk = data[block:block+0x100]
    if all(b == 0xFF for b in chunk) or all(b == 0x00 for b in chunk):
        continue
    print(f"\n  Block {hex(block)}:")
    for j in range(0, 0x100, 16):
        row = chunk[j:j+16]
        if all(b == 0xFF for b in row) or all(b == 0x00 for b in row):
            continue
        h = ' '.join(f'{b:02x}' for b in row)
        a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        print(f"    {hex(block+j):8s}: {h:48s} {a}")

print()
print("=" * 70)
print("DONE")
print("=" * 70)
