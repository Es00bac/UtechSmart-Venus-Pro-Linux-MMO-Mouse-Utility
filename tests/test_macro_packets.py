#!/usr/bin/env python3
"""Debug script to compare our macro packets vs USB captures."""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp

# From USB capture: "wired - rebind 1 to macro called testing"
# Name: "testing" (14 bytes UTF-16LE)
# Events: t-dn 14ms, t-up 93ms, e-dn 157ms, e-up 93ms, ... (see capture filename)

# Expected packets from USB capture (page 0x03 for button 1):
EXPECTED_PACKETS = [
    "08070003000a0e74006500730074006902",  # offset 00: name
    "080700030a0a006e00670000000000005a",  # offset 0a: rest of name
    "08070003140a0000000000000000000025",  # offset 14: zeros
    "080700031e0a000e811700005d411700c0",  # offset 1e: events
    "08070003280a009d810800005d41080045",  # offset 28: events
    "08070003320a00bc811600006d411600f0",  # offset 32: events
    "080700033c0a009c811700005e41170013",  # offset 3c: events
    "08070003460a009c810c00005e410c001f",  # offset 46: events
    "08070003500a00bc811100004e411100fb",  # offset 50: events
    "080700035a0a00cb810a00005e410a00e0",  # offset 5a: events
    "080700036406000369000000000000006d",  # offset 64: terminator
]

# Bind packet:
EXPECTED_BIND = "0807000060040600014e0000000000008d"

def build_test_macro():
    """Build macro data like Windows software does for 'testing' macro."""
    name = "testing"
    
    # Events from the filename: t-dn 93ms t-up 157ms e-dn 93ms e-up 188ms ...
    # But looking at the packet data, events start at offset 0x1e
    # The hex there is: 00 0e 81 17 00 00 5d 41 17 00
    # 00 0e = delay 14 (0x000e), 81 = down, 17 = T
    # 00 5d = delay 93 (0x005d), 41 = up, 17 = T
    
    # Let me decode the actual events from the capture:
    # offset 0x1e: 00 0e 81 17 00 - T down, 14ms delay
    #              00 5d 41 17 00 - T up, 93ms delay  
    # offset 0x28: 00 9d 81 08 00 - E(0x08) down, 157(0x9d)ms delay
    #              00 5d 41 08 00 - E up, 93ms delay
    # offset 0x32: 00 bc 81 16 00 - S(0x16) down, 188(0xbc)ms delay
    #              00 6d 41 16 00 - S up, 109(0x6d)ms delay
    # offset 0x3c: 00 9c 81 17 00 - T down, 156(0x9c)ms delay
    #              00 5e 41 17 00 - T up, 94(0x5e)ms delay
    # offset 0x46: 00 9c 81 0c 00 - I(0x0c) down, 156ms delay
    #              00 5e 41 0c 00 - I up, 94ms delay
    # offset 0x50: 00 bc 81 11 00 - N(0x11) down, 188ms delay
    #              00 4e 41 11 00 - N up, 78(0x4e)ms delay
    # offset 0x5a: 00 cb 81 0a 00 - G(0x0a) down, 203(0xcb)ms delay
    #              00 5e 41 0a 00 - G up, 94ms delay
    
    # Create events matching capture exactly
    events = [
        vp.MacroEvent(keycode=0x17, is_down=True, delay_ms=14),   # T down
        vp.MacroEvent(keycode=0x17, is_down=False, delay_ms=93),  # T up
        vp.MacroEvent(keycode=0x08, is_down=True, delay_ms=157),  # E down
        vp.MacroEvent(keycode=0x08, is_down=False, delay_ms=93),  # E up
        vp.MacroEvent(keycode=0x16, is_down=True, delay_ms=188),  # S down
        vp.MacroEvent(keycode=0x16, is_down=False, delay_ms=109), # S up
        vp.MacroEvent(keycode=0x17, is_down=True, delay_ms=156),  # T down
        vp.MacroEvent(keycode=0x17, is_down=False, delay_ms=94),  # T up
        vp.MacroEvent(keycode=0x0c, is_down=True, delay_ms=156),  # I down
        vp.MacroEvent(keycode=0x0c, is_down=False, delay_ms=94),  # I up
        vp.MacroEvent(keycode=0x11, is_down=True, delay_ms=188),  # N down
        vp.MacroEvent(keycode=0x11, is_down=False, delay_ms=78),  # N up
        vp.MacroEvent(keycode=0x0a, is_down=True, delay_ms=203),  # G down
        vp.MacroEvent(keycode=0x0a, is_down=False, delay_ms=94),  # G up
    ]
    
    return name, events


def main():
    name, events = build_test_macro()
    
    # Build macro buffer just like the GUI does
    name_bytes = name.encode("utf-16le")
    print(f"Name: '{name}' = {name_bytes.hex()} ({len(name_bytes)} bytes)")
    
    buf = bytearray(0x70)
    buf[0] = len(name_bytes)
    buf[1:1+len(name_bytes)] = name_bytes
    
    # Pack events starting at 0x1E
    event_offset = 0x1E
    for event in events:
        event_data = event.to_bytes()
        if event_offset + len(event_data) > 0x64:
            print("Warning: Macro events truncated")
            break
        buf[event_offset:event_offset + len(event_data)] = event_data
        event_offset += len(event_data)
    
    print(f"\nBuffer (0x70 bytes):")
    for i in range(0, len(buf), 16):
        hex_str = buf[i:i+16].hex()
        print(f"  {i:02x}: {hex_str}")
    
    # Build packets for button 1 (page 0x03)
    macro_page = 0x03
    print(f"\n\nPackets we generate (page 0x{macro_page:02x}):")
    
    our_packets = []
    for offset in range(0x00, 0x64, 0x0A):
        chunk = bytes(buf[offset:offset + 10])
        pkt = vp.build_macro_chunk(offset, chunk, macro_page)
        our_packets.append(pkt.hex())
        print(f"  offset {offset:02x}: {pkt.hex()}")
    
    term_pkt = vp.build_macro_terminator(macro_page)
    our_packets.append(term_pkt.hex())
    print(f"  terminator: {term_pkt.hex()}")
    
    # Compare with expected
    print(f"\n\nComparison:")
    all_match = True
    for i, (ours, expected) in enumerate(zip(our_packets, EXPECTED_PACKETS)):
        match = "✓" if ours == expected else "✗"
        if ours != expected:
            all_match = False
            print(f"  [{match}] Packet {i}:")
            print(f"      Ours:     {ours}")
            print(f"      Expected: {expected}")
            # Find differences
            for j, (a, b) in enumerate(zip(ours, expected)):
                if a != b:
                    print(f"      Diff at byte {j//2}: ours={a}{ours[j+1] if j+1 < len(ours) else ''}, expected={b}{expected[j+1] if j+1 < len(expected) else ''}")
        else:
            print(f"  [{match}] Packet {i}: OK")
    
    # Check bind packet
    apply_offset = 0x60  # Button 1
    bind_pkt = vp.build_macro_bind(apply_offset, macro_index=1)
    print(f"\n\nBind packet:")
    print(f"  Ours:     {bind_pkt.hex()}")
    print(f"  Expected: {EXPECTED_BIND}")
    print(f"  Match: {'✓' if bind_pkt.hex() == EXPECTED_BIND else '✗'}")
    
    if all_match and bind_pkt.hex() == EXPECTED_BIND:
        print("\n\n✓ All packets match USB capture!")
    else:
        print("\n\n✗ Some packets don't match - investigate differences above")


if __name__ == "__main__":
    main()
