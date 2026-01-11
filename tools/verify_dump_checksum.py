from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

from venus_protocol import VenusDevice

# Dump data from 300 to 398 (Header + Name + Data)
# Note: Dump starts at 0x300. 
# Length: 0x98 bytes = 152 bytes.
# Content: 
# 300: 04 6d 00 31 00 (Len=4, Name="1")
# 305: 02 81 1e 00 00 10 41 1e 00 00 10 (Event 1)
# ... padding ...
# 398: 03 5A 00 ... (Terminator)

# Reconstruct buffer from dump output at Step 2758
# 04 6d 00 31 00 
# 02 81 1e 00 00 10 41 1e 00 00 10
# (Padding FF or 00? Dump shows FF at 310, but 00 later? Let's check closely)
# 310: ff ff ff ff ff ff ff ff ff ff 
# 31A: 00 00 00 00 00 18 (Event Count = 0x18 = 24 events?)
# 320: 81 3a ...

# Wait. Offset 0x1F (31F) is Event Count. 
# Dump at 31F is '00'? No.
# 300 + 1F = 31F.
# Dump line 310: ff ff ff ff ff ff ff ff ff ff 00 00 00 00 00 18
# 310..319 = FFs
# 31A..31E = 00s
# 31F = 18 (Event count 24 dec?)

data = bytes([
    0x04, 0x6d, 0x00, 0x31, 0x00, # Name
    0x02, 0x81, 0x1e, 0x00, 0x00, 0x10, 0x41, 0x1e, 0x00, 0x00, 0x10, # Events in header gap? No.
])

# Wait, protocol says events start at 0x20.
# Dump shows bytes at 305..30F! "02 81 1e..."
# This contradicts my "Events start at 0x20" rule.
# Is "artifacts/bin/odd_macro_behavior.bin" a different format? Or does the mouse pack data differently?

# Windows capture showed: Header(30 bytes) -> Events.
# Dump shows: Header(5 bytes) -> Events(10 bytes) -> Padding -> EventCount(1B) -> Events?
# Let's interpret the dump strictly.

dump_hex = """
04 6d 00 31 00 02 81 1e 00 00 10 41 1e 00 00 10
ff ff ff ff ff ff ff ff ff ff 00 00 00 00 00 18
81 3a 00 00 3f 41 3a 00 00 8c 81 3b 00 00 3f 41
3b 00 00 8c 81 3c 00 00 4e 41 3c 00 00 9d 81 3d
00 00 4e 41 3d 00 00 8c 81 3e 00 00 4f 41 3e 00
00 8c 81 3f 00 00 4e 41 3f 00 00 9d 81 40 00 00
4e 41 40 00 00 9c 81 41 00 00 4e 41 41 00 00 9c
81 42 00 00 3f 41 42 00 00 9c 81 43 00 00 4e 41
43 00 00 9c 81 44 00 00 3f 41 44 00 00 9c 81 45
00 00 3f 41 45 00 00
"""
# This covers 0x300 to 0x397 (0x98 bytes)
# Terminator at 0x398: 03 5A 00 ...

raw_bytes = bytes.fromhex(dump_hex.replace('\n', ''))
# Checksum is at index 0x99 of the page (offset 1 in terminator)
# But my calculator expects "Data Buffer" excluding terminator.

# Expected Checksum: 0x5A
# Macro Index: Assume 0 (Address 0x300 is Slot 1)


def calculate_checksum(data, macro_index=0):
    # Strategy 1: Sum EVERYTHING (including padding 00s and FFs)
    # Strategy 2: Sum only up to Terminator (exclude terminator)
    # Strategy 3: Sum only valid packets? No, fw just sums blindly usually.
    
    # Try multiple strategies
    s_sum_all = sum(data) & 0xFF
    inv_sum_all = (~s_sum_all) & 0xFF
    
    count = data[0x1F] if len(data) >= 32 else 0
    correction = (macro_index + 1) ** 2
    
    res1 = (inv_sum_all - count + correction) & 0xFF
    
    # Strategy 2: Treat FF as 00?
    data_no_ff = bytes([b if b != 0xFF else 0x00 for b in data])
    s_sum_noff = sum(data_no_ff) & 0xFF
    inv_sum_noff = (~s_sum_noff) & 0xFF
    res2 = (inv_sum_noff - count + correction) & 0xFF
    
    # Strategy 3: Only sum bytes that are part of valid packets?
    # No, too complex.
    
    print(f"Strategy 1 (All Bytes): Sum={s_sum_all:02X}, Inv={inv_sum_all:02X} -> Result={res1:02X}")
    print(f"Strategy 2 (FF=00):     Sum={s_sum_noff:02X}, Inv={inv_sum_noff:02X} -> Result={res2:02X}")
    
    return res1 # Default return


# Run calculation
chk = calculate_checksum(raw_bytes, macro_index=0)
print(f"Calculated: {chk:02X}")
print(f"Expected:   5A")
print(f"Match:      {chk == 0x5A}")

# Detailed debug
total = sum(raw_bytes)
count = raw_bytes[0x1F] # Event count
print(f"Sum: {total}")
print(f"InvSum: {(~total)&0xFF}")
print(f"Count: {count}")
print(f"Correction: 1")
