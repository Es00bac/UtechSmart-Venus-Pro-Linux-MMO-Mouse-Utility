from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


# Solve Checksum for "simple_macro"
# Target: 4F
# Data up to terminator:

# Pkt 1 Payload (18 bytes name part 1): 18 73 00 69 00 6d 00 70 00 6c 00 65 00 5f 00 6d 00 61 (Corrected from earlier manual)
# Wait, let's reconstruct exact bytes from trace packets.

# PKT_write1 = "09070003000a18730069006d0070006cfb"
# Payload: 18 73 00 69 00 6d 00 70 00 6c (10 bytes) 
# Note: My decode might be off on length. 
# PKT_write1 breakdown:
# 09 07 00 03 00 0a (Len 10)
# Data: 18 73 00 69 00 6d 00 70 00 6c (10 bytes) -> Correct.

# PKT_write2 = "090700030a0a0065005f006d0061006339"
# Offset 0A, Len 10.
# Data: 00 65 00 5f 00 6d 00 61 00 63 (10 bytes) -> Correct.

# PKT_write3 = "09070003140a0072006f00000000000043"
# Offset 14, Len 10.
# Data: 00 72 00 6f 00 00 00 00 00 00 (10 bytes) -> Correct.

# PKT_write4 = "090700031e0a0002811e000003411e0017"
# Offset 1E, Len 10.
# Data: 00 02 81 1e 00 00 03 41 1e 00 (10 bytes) -> Correct.

# PKT_write5 = "09070003280600034f00000000000000c2"
# Offset 28, Len 06.
# Data: 00 03 4f 00 00 00 (6 bytes)
# Terminator is [4f 00 00 00] at offset 2A.
# Bytes BEFORE terminator:
# 00 03 (Last 2 bytes of Event 2)

# Full Data Sequence (Indices 0x00 to 0x29):
# 00-09: 18 73 00 69 00 6d 00 70 00 6c
# 0A-13: 00 65 00 5f 00 6d 00 61 00 63
# 14-1D: 00 72 00 6f 00 00 00 00 00 00
# 1E-27: 00 02 81 1e 00 00 03 41 1e 00
# 28-29: 00 03

data = [
    0x18, 0x73, 0x00, 0x69, 0x00, 0x6d, 0x00, 0x70, 0x00, 0x6c,
    0x00, 0x65, 0x00, 0x5f, 0x00, 0x6d, 0x00, 0x61, 0x00, 0x63,
    0x00, 0x72, 0x00, 0x6f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x02, 0x81, 0x1e, 0x00, 0x00, 0x03, 0x41, 0x1e, 0x00,
    0x00, 0x03
]

count = 2
macro_index = 0 # Button 1 (Slot 0)

target = 0x4F

print(f"Data Len: {len(data)}")
s_sum = sum(data) & 0xFF
print(f"Sum: {s_sum:02X}")

# Try Formula: (~Sum - Count + (Index+1)^2) & 0xFF
# Correction = 1
# InvSum = ~s_sum
calc = ((~s_sum) - count + 1) & 0xFF
print(f"Old Formula Calc: {calc:02X} (Target: {target:02X})")
if calc == target:
     print("MATCH!")
else:
     print("No Match.")
     
# Brute Force?
print("\n--- Brute Force Analysis ---")
s_sum = sum(data) & 0xFF
xor_sum = 0
for b in data: xor_sum ^= b

# 1. Base - Sum
for base in range(256):
    if (base - s_sum) & 0xFF == target:
        print(f"Match: ({base:02X} - Sum) = Target")
        
# 2. Sum + Offset
for off in range(256):
    if (s_sum + off) & 0xFF == target:
        print(f"Match: (Sum + {off:02X}) = Target")

# 3. Base - XOR
for base in range(256):
    if (base - xor_sum) & 0xFF == target:
        print(f"Match: ({base:02X} - XOR[{xor_sum:02X}]) = Target")

# 4. XOR + Offset
for off in range(256):
    if (xor_sum + off) & 0xFF == target:
        print(f"Match: (XOR + {off:02X}) = Target")
        
# 5. Length/Index involvement?
# Len=42 (0x2A). Index=0. Count=2.
# 42 + Sum(19) = 3B? No.
print(f"Len: 0x{len(data):02X} Count: 0x{count:02X} Index: 0x{macro_index:02X}")
        
