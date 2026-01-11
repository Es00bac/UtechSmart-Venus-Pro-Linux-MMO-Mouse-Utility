from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

# Decoded Packet Sequence from tshark output

# 1. Initialization / Prepare?
# 09 04 ... 
# 09: Report ID (Output Report for Wireless Receiver / Wired Mouse?)
# 04: Command ID (Transaction Start/End?)
# Payload: 00 00 00 02 0a 01 ... 3b (Checksum)
PKT_1 = "0904000000020a0100000000000000003b"

# ... (Repeated Cmd 04s - maybe retries or keepalives?)

# 2. Start Transaction?
# 09 03 ...
# 03: Handshake? Or new command?
PKT_start = "0903000000010100000000000000000047"

# 3. Write Macro Header (Page 03, Offset 00)
# 09 07 00 03 00 0a ...
# 09: Report ID
# 07: Write Cmd
# 00: ?
# 03: Page
# 00: Offset
# 0a: Length (10 bytes)
# Data: 18 (Len=24 bytes?) 73 00 69 00 6d 00 70 00 6c (s i m p l)
PKT_write1 = "09070003000a18730069006d0070006cfb"

# 4. Write Macro Name Cont. (Page 03, Offset 0A)
# Data: 00 65 00 5f 00 6d 00 61 00 63 (e _ m a c)
PKT_write2 = "090700030a0a0065005f006d0061006339"

# 5. Write Macro Name Cont. (Page 03, Offset 14)
# Data: 00 72 00 6f 00 00 ... (r o \0 ...)
PKT_write3 = "09070003140a0072006f00000000000043"

# 6. Write Events (Page 03, Offset 1E)
# Data: 
# [1E]: 02 (Count = 2 events)
# [1F]: 81 (Down) 
# [20]: 1e (Key '1')
# [21]: 00 
# [22]: 00 03 (Delay 3ms)
# [24]: 41 (Up)
# [25]: 1e (Key '1')
# [26]: 00
# [27]: 17 (Next byte of delay?)
PKT_write4 = "090700031e0a0002811e000003411e0017"
# Wait, let's re-parse payload:
# 00 02 81 1e 00 00 03 41 1e 00
# Byte 0 (offset 1E): 00 ?? (Padding/Divider?)
# Byte 1 (offset 1F): 02 (Count!) -> CONFIRMED 0x1F alignment
# Event 1: 81 1e 00 00 03 (Dn '1', 3ms)
# Event 2: 41 1e 00 (Partial Event 2)

# 7. Write Terminator (Page 03, Offset 28)
# Data: 00 03 4f ...
# [28]: 00 (Rest of Event 2 delay)
# [29]: 03 (Wait, 03 was usually delay but here?)
# [2A]: 4f (Checksum?)
# [2B-2F]: 00 ...
PKT_write5 = "09070003280600034f00000000000000c2"
# Payload: 00 03 4f 00 00 00 (6 bytes)
# Byte 0 (Offset 28): 00 (Finish Event 2 Delay: 1e 00 00 -> 00) ? 
# Event 2 was: 41 1e 00. Next is 00 03.
# So Event 2 is 41 1e 00 00 03 (Up '1', 3ms).
# Terminator starts at 2D? 
# Ah, verify length.
# Pkt 4 ended at Offset 1E + 10 = 28.
# Pkt 5 starts at Offset 28.
# Bytes at 28: 00 03.
# This completes Event 2: 41 1e 00 00 03.
# Bytes at 2A: 4f 00 00 00. -> TERMINATOR!
# Checksum = 0x4F.
# Zeros padding.

# 8. Bind to Button 1 (Page 00, Offset 60)
# 09 07 00 00 60 ...
# Data: 04 06 00 01 4e ...
# 04 (Len)
# 06 (Type Macro)
# 00 (Index 0)
# 01 (Mode 1 - Once / Windows Default) -- Wait, current code uses 01 (Once).
# 4e (Checksum: 55 - (6+0+1) = 4E) -> Matches.
PKT_bind = "0907000060040600014e0000000000008c"

# 9. Final Commit (Cmd 04)
PKT_final = "0904000000020a0100000000000000003b"


# KEY FINDINGS:
# 1. Report ID is 0x09 (Output Report), NOT 0x08 (Feature Report).
# 2. Structure is identical to protocol (Page, Offset, Len, Data).
# 3. Count is definitely at Offset 0x1F (Byte 1 of Pkt 4 payload).
# 4. Terminator follows immediately after last event bytes.
# 5. Checksum logic needs to match 0x4F for that data.

# Checksum Verification:
# Data: [Name...] [00] [02] [Evt1] [Evt2]
# Sum of data?
# Terminator Checksum: 4F.
