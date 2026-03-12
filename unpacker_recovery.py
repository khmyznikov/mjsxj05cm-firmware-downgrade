#!/usr/bin/env python3
"""
Unpacker for tf_recovery.img (Xiaomi MJSXJ05CM - I6 / LX409 variant)

Recovery layout (from binwalk):
  0x000000  uImage kernel  (header 64 + data 1,570,356 = 1,570,420 bytes)
  0x200000  SquashFS       (5,716,954 bytes)
  0x960000  JFFS2 data     (3,803,240 bytes)
"""

import sys
import os

# Format: (filename, offset, size)
partitions = [
    ("uImage_kernel", 0x0,      1570356 + 64),  # uImage header (64) + data
    ("squashfs",      0x200000, 5716954),        # SquashFS image
    ("data",          0x960000, 3803240),         # JFFS2 filesystem
]

if len(sys.argv) < 2:
    print("Usage: python3 unpacker_recovery.py <tf_recovery.img> [output_dir]")
    sys.exit(1)

input_file = sys.argv[1]
output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

if not os.path.isdir(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}")

try:
    with open(input_file, "rb") as firmware:
        for part, offset, size in partitions:
            firmware.seek(offset, 0)
            data = firmware.read(size)

            out_path = os.path.join(output_dir, part)
            with open(out_path, "wb") as output:
                output.write(data)

            print(f"  {part:20s} @ {hex(offset):10s}  size: {len(data):>8d} bytes")

    print(f"\nDone. Extracted {len(partitions)} partitions from {input_file}")
except FileNotFoundError:
    print(f"Error: '{input_file}' not found.")

